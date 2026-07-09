"""DeepSeek LLM adapter using OpenAI-compatible API.

Implements LLMProvider interface for DeepSeek models (deepseek-v4-flash, deepseek-v4-pro).
Based on specs/001-we-are-building/contracts/llm-adapter.md

Note: deepseek-v4-flash and deepseek-v4-pro have thinking mode enabled by default,
which is incompatible with tool_choice. We use JSON mode with schema in prompt instead.
"""

import asyncio
import json
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
    get_pydantic_model,
    get_schema_info,
)
from src.services.llm.base import TimeoutError as LLMTimeoutError

logger = get_logger(__name__)

# These models have thinking mode enabled by default — incompatible with tool_choice
THINKING_MODELS = {"deepseek-v4-flash", "deepseek-v4-pro"}

# Set False to disable thinking-mode path (uses function calling instead — will fail on thinking models)
USE_DEEPSEEK_THINKING = False


class DeepSeekAdapter(LLMProvider):
    """DeepSeek API integration using OpenAI-compatible endpoint."""

    DEEPSEEK_BASE_URL = "https://api.deepseek.com"

    def __init__(self, api_key: str, model: str = "deepseek-v4-flash"):
        """Initialize DeepSeek adapter.

        Args:
            api_key: DeepSeek API key
            model: DeepSeek model identifier (deepseek-v4-flash or deepseek-v4-pro)
        """
        super().__init__(api_key, model)

        if AsyncOpenAI is None:
            raise ImportError("openai package not installed. Run: pip install openai")

        # DeepSeek API is OpenAI-compatible, use custom base URL
        self.client = AsyncOpenAI(api_key=api_key, base_url=self.DEEPSEEK_BASE_URL)

        self.is_reasoning_model = model in THINKING_MODELS

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

        # Thinking models use internal reasoning tokens — multiply budget to avoid truncation
        token_limit = (
            request.config.max_tokens * 3
            if USE_DEEPSEEK_THINKING and self.model in THINKING_MODELS
            else request.config.max_tokens
        )

        try:
            schema_type = request.config.structured_output_schema

            if USE_DEEPSEEK_THINKING and self.model in THINKING_MODELS:
                # Thinking mode is incompatible with tool_choice — use JSON mode + schema in prompt
                pydantic_model = get_pydantic_model(schema_type)
                logger.debug(f"Using {schema_type} schema (JSON mode, thinking model)")

                json_schema = pydantic_model.model_json_schema()
                schema_instruction = (
                    "\n\nIMPORTANT: You MUST respond with valid JSON matching this exact schema:\n"
                    f"```json\n{json.dumps(json_schema, indent=2)}\n```\n"
                    "Do not include any text before or after the JSON object."
                )
                system_prompt = request.config.system_prompt + schema_instruction

                api_params = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": full_prompt},
                    ],
                    "max_tokens": token_limit,
                    "response_format": {"type": "json_object"},
                }
            else:
                # Non-thinking models: use function calling for structured output
                schema_info = get_schema_info(schema_type)
                pydantic_model = schema_info.pydantic_model
                function_name = schema_info.tool_name
                function_description = schema_info.tool_description
                logger.debug(f"Using {schema_type} schema (function calling)")

                api_params = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": request.config.system_prompt},
                        {"role": "user", "content": full_prompt},
                    ],
                    "max_tokens": token_limit,
                    "temperature": request.config.temperature,
                    "extra_body": {"thinking": {"type": "enabled" if USE_DEEPSEEK_THINKING else "disabled"}},
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
            choice = response.choices[0]

            # Extract reasoning content if available (thinking models)
            reasoning_content = None
            if self.is_reasoning_model and hasattr(choice.message, "reasoning_content"):
                reasoning_content = choice.message.reasoning_content
                if reasoning_content:
                    logger.debug(
                        f"DeepSeek reasoning chain-of-thought: {reasoning_content[:200]}..."
                    )

            # Extract raw JSON depending on output mode
            if USE_DEEPSEEK_THINKING and self.model in THINKING_MODELS:
                raw_json = choice.message.content
                if not raw_json:
                    if choice.finish_reason == "length":
                        raise TokenLimitError(
                            "DeepSeek output was truncated due to max_tokens limit"
                        )
                    refusal = getattr(choice.message, "refusal", None)
                    if refusal:
                        raise ContentFilterError(f"DeepSeek refused to respond: {refusal}")
                    raise Exception(
                        f"DeepSeek returned empty content (finish_reason: {choice.finish_reason})"
                    )
            else:
                if not choice.message.tool_calls:
                    logger.warning(
                        f"DeepSeek returned no tool calls. Finish reason: {choice.finish_reason}"
                    )
                    refusal = getattr(choice.message, "refusal", None)
                    if refusal:
                        raise ContentFilterError(f"DeepSeek refused to respond: {refusal}")
                    elif choice.finish_reason == "length":
                        raise TokenLimitError(
                            "DeepSeek output was truncated due to max_tokens limit"
                        )
                    else:
                        raise Exception(
                            f"Expected tool calls but none returned (finish_reason: {choice.finish_reason})"
                        )
                tool_call = choice.message.tool_calls[0]
                raw_json = tool_call.function.arguments
                if not raw_json:
                    raise Exception("DeepSeek tool call has empty arguments")

            # Validate with Pydantic for type safety
            try:
                parsed_output = pydantic_model.model_validate_json(raw_json)
                answer_text = parsed_output.model_dump_json()
                logger.debug(
                    f"Extracted structured JSON from DeepSeek (Pydantic): {len(answer_text)} chars"
                )
            except Exception as e:
                logger.error(f"DeepSeek returned JSON that failed Pydantic validation: {e}")
                error_msg = (
                    f"DeepSeek JSON validation error: {e}\n\n"
                    f"RAW RESPONSE:\n{raw_json}"
                )
                raise ValueError(error_msg) from e

            citations_included = request.config.include_citations
            confidence = 0.85 if self.is_reasoning_model else 0.8

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
