"""DeepSeek LLM adapter using OpenAI-compatible API.

Implements LLMProvider interface for DeepSeek models (deepseek-chat, deepseek-reasoner).
Based on specs/001-we-are-building/contracts/llm-adapter.md
"""

import asyncio
import time
from uuid import uuid4

from openai import AsyncOpenAI

from src.lib.logging import get_logger
from src.services.llm.base import (
    AuthenticationError,
    ContentFilterError,
    ExtractionRequest,
    ExtractionResponse,
    GenerationRequest,
    LLMProvider,
    LLMResponse,
    RateLimitError,
    TokenLimitError,
)
from src.services.llm.base import TimeoutError as LLMTimeoutError
from src.services.llm.schemas import Answer, HopEvaluation

logger = get_logger(__name__)


class DeepSeekAdapter(LLMProvider):
    """DeepSeek API integration using OpenAI-compatible endpoint."""

    DEEPSEEK_BASE_URL = "https://api.deepseek.com"

    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        """Initialize DeepSeek adapter.

        Args:
            api_key: DeepSeek API key
            model: DeepSeek model identifier (deepseek-chat or deepseek-reasoner)
        """
        super().__init__(api_key, model)

        if AsyncOpenAI is None:
            raise ImportError("openai package not installed. Run: pip install openai")

        # DeepSeek API is OpenAI-compatible, use custom base URL
        self.client = AsyncOpenAI(api_key=api_key, base_url=self.DEEPSEEK_BASE_URL)

        # deepseek-reasoner uses chain-of-thought reasoning
        self.is_reasoning_model = model == "deepseek-reasoner"

        logger.info(f"Initialized DeepSeek adapter with model {model}")

    async def generate(self, request: GenerationRequest) -> LLMResponse:
        """Generate answer using DeepSeek API.

        Args:
            request: Generation request

        Returns:
            LLMResponse with answer and metadata

        Raises:
            RateLimitError: Rate limit exceeded
            AuthenticationError: Invalid API key
            LLMTimeoutError: Response timeout
            ContentFilterError: Content blocked
        """
        start_time = time.time()

        # Build prompt with context and optional chunk IDs
        full_prompt = self._build_prompt(request.prompt, request.context, request.chunk_ids)
        token_limit = (
            request.config.max_tokens * 3
            if self.model == "deepseek-reasoner"
            else request.config.max_tokens
        )

        try:
            # Select Pydantic model based on configuration
            schema_type = request.config.structured_output_schema

            if schema_type == "hop_evaluation":
                pydantic_model = HopEvaluation
                function_name = "evaluate_context_sufficiency"
                function_description = (
                    "Evaluate if retrieved context is sufficient to answer the question"
                )
                logger.debug("Using hop evaluation schema (Pydantic)")
            else:  # "default"
                pydantic_model = Answer
                function_name = "format_kill_team_answer"
                function_description = "Format Kill Team rules answer with quotes and explanation"
                logger.debug("Using default answer schema (Pydantic)")

            # Build API call parameters with function calling (DeepSeek doesn't support parse method yet)
            # Use Pydantic model for schema generation and validation
            api_params = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": request.config.system_prompt},
                    {"role": "user", "content": full_prompt},
                ],
                "max_tokens": token_limit,
                "temperature": request.config.temperature,
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": function_name,
                            "description": function_description,
                            "parameters": pydantic_model.model_json_schema(),
                        },
                    }
                ],
                "tool_choice": {"type": "function", "function": {"name": function_name}},
            }

            # Call DeepSeek API with timeout
            response = await asyncio.wait_for(
                self.client.chat.completions.create(**api_params),
                timeout=request.config.timeout_seconds,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            # Extract structured JSON from tool calls
            choice = response.choices[0]

            # For deepseek-reasoner, also extract reasoning content if available
            reasoning_content = None
            if self.is_reasoning_model and hasattr(choice.message, "reasoning_content"):
                reasoning_content = choice.message.reasoning_content
                if reasoning_content:
                    logger.debug(
                        f"DeepSeek reasoning chain-of-thought: {reasoning_content[:200]}..."
                    )

            # Check for tool calls (structured output)
            if not choice.message.tool_calls:
                logger.warning(
                    f"DeepSeek returned no tool calls. Finish reason: {choice.finish_reason}"
                )
                # Check if there's a refusal
                refusal = getattr(choice.message, "refusal", None)
                if refusal:
                    raise ContentFilterError(f"DeepSeek refused to respond: {refusal}")
                elif choice.finish_reason == "length":
                    raise TokenLimitError("DeepSeek output was truncated due to max_tokens limit")
                else:
                    raise Exception(
                        f"Expected tool calls but none returned (finish_reason: {choice.finish_reason})"
                    )

            # Extract JSON from tool call
            tool_call = choice.message.tool_calls[0]
            function_args = tool_call.function.arguments

            if not function_args:
                raise Exception("DeepSeek tool call has empty arguments")

            # Validate with Pydantic for type safety
            try:
                parsed_output = pydantic_model.model_validate_json(function_args)
                answer_text = parsed_output.model_dump_json()
                logger.debug(
                    f"Extracted structured JSON from DeepSeek (Pydantic): {len(answer_text)} chars"
                )
            except Exception as e:
                logger.error(f"DeepSeek returned JSON that failed Pydantic validation: {e}")
                # Include the raw response in the error message for debugging
                error_msg = (
                    f"DeepSeek JSON validation error: {e}\n\n"
                    f"RAW RESPONSE:\n{function_args}"
                )
                raise ValueError(error_msg) from e

            # Check if citations are included (always true for structured output with quotes)
            citations_included = request.config.include_citations

            # Calculate confidence (DeepSeek doesn't provide logprobs, use default)
            # Reasoning models get slightly higher confidence due to chain-of-thought
            confidence = 0.85 if self.is_reasoning_model else 0.8

            # Token count
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
            token_count = response.usage.total_tokens

            logger.info(
                "DeepSeek generation completed",
                extra={
                    "latency_ms": latency_ms,
                    "token_count": token_count,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "confidence": confidence,
                    "has_reasoning": reasoning_content is not None,
                },
            )

            return LLMResponse(
                response_id=uuid4(),
                answer_text=answer_text,
                confidence_score=confidence,
                token_count=token_count,
                latency_ms=latency_ms,
                provider="deepseek",
                model_version=self.model,
                citations_included=citations_included,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        except TimeoutError as e:
            logger.warning(f"DeepSeek API timeout after {request.config.timeout_seconds}s")
            raise LLMTimeoutError(
                f"DeepSeek generation exceeded {request.config.timeout_seconds}s timeout"
            ) from e

        except Exception as e:
            error_msg = str(e).lower()

            if "rate_limit" in error_msg or "429" in error_msg:
                logger.warning(f"DeepSeek rate limit exceeded: {e}")
                raise RateLimitError(f"DeepSeek rate limit: {e}") from e

            if "authentication" in error_msg or "401" in error_msg:
                logger.error(f"DeepSeek authentication failed: {e}")
                raise AuthenticationError(f"DeepSeek auth error: {e}") from e

            if (
                "content_policy" in error_msg
                or "content_filter" in error_msg
                or "unsafe" in error_msg
            ):
                logger.warning(f"DeepSeek content filtered: {e}")
                raise ContentFilterError(f"DeepSeek content filter: {e}") from e

            logger.error(f"DeepSeek generation error: {e}")
            raise

    async def extract_pdf(self, _request: ExtractionRequest) -> ExtractionResponse:
        """Extract markdown from PDF using DeepSeek.

        Note: DeepSeek API documentation does not currently specify PDF extraction
        capabilities. This method is not implemented.

        Args:
            request: Extraction request with PDF file

        Returns:
            ExtractionResponse with markdown content

        Raises:
            NotImplementedError: PDF extraction not supported
        """
        logger.warning("DeepSeek PDF extraction is not currently supported")
        raise NotImplementedError(
            "DeepSeek PDF extraction is not documented in the API. "
            "Use gemini-2.5-pro or gemini-2.5-flash for PDF extraction instead."
        )
