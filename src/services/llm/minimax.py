"""MiniMax LLM adapter using MiniMax API.

Implements LLMProvider interface for MiniMax models (MiniMax-M2.5, MiniMax-M2, MiniMax-M1).
Based on specs/001-we-are-building/contracts/llm-adapter.md

Note: MiniMax uses OpenAI-compatible API endpoint with function calling for structured output.
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
    SchemaInfo,
    TokenLimitError,
    get_schema_info,
)
from src.services.llm.base import TimeoutError as LLMTimeoutError

logger = get_logger(__name__)


class MiniMaxAdapter(LLMProvider):
    """MiniMax API integration using OpenAI-compatible endpoint."""

    MINIMAX_BASE_URL = "https://api.minimax.io/v1"

    def __init__(self, api_key: str, model: str = "MiniMax-M2.5"):
        """Initialize MiniMax adapter.

        Args:
            api_key: MiniMax API key
            model: MiniMax model identifier (MiniMax-M2.5, MiniMax-M2, MiniMax-M1)
        """
        super().__init__(api_key, model)

        if AsyncOpenAI is None:
            raise ImportError("openai package not installed. Run: pip install openai")

        # MiniMax API is OpenAI-compatible, use custom base URL
        self.client = AsyncOpenAI(api_key=api_key, base_url=self.MINIMAX_BASE_URL)

        logger.info(f"Initialized MiniMax adapter with model {model}")

    async def generate(self, request: GenerationRequest) -> LLMResponse:
        """Generate answer using MiniMax API.

        Uses function calling for structured output.

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

        try:
            # Select Pydantic model based on configuration
            schema_type = request.config.structured_output_schema
            schema_info = get_schema_info(schema_type)
            logger.debug(f"Using {schema_type} schema (Pydantic)")

            # Build function calling parameters for structured output
            api_params = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": request.config.system_prompt},
                    {"role": "user", "content": full_prompt},
                ],
                "max_tokens": request.config.max_tokens,
                "temperature": request.config.temperature,
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": schema_info.tool_name,
                            "description": schema_info.tool_description,
                            "parameters": schema_info.json_schema,
                        },
                    }
                ],
                "tool_choice": {"type": "function", "function": {"name": schema_info.tool_name}},
            }

            # Call MiniMax API with timeout
            response = await asyncio.wait_for(
                self.client.chat.completions.create(**api_params),
                timeout=request.config.timeout_seconds,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            # Extract function call arguments
            choice = response.choices[0]
            message = choice.message

            # Check for refusal or empty content
            if not message.tool_calls:
                if choice.finish_reason == "length":
                    raise TokenLimitError("MiniMax output was truncated due to max_tokens limit")
                refusal = getattr(message, "refusal", None)
                if refusal:
                    raise ContentFilterError(f"MiniMax refused to respond: {refusal}")
                raise Exception(
                    f"MiniMax returned no tool calls (finish_reason: {choice.finish_reason})"
                )

            # Extract function arguments from tool call
            function_args = message.tool_calls[0].function.arguments

            # Validate with Pydantic for type safety
            try:
                parsed_output = schema_info.pydantic_model.model_validate_json(function_args)
                answer_text = parsed_output.model_dump_json()
                logger.debug(
                    f"Extracted structured JSON from MiniMax (Pydantic): {len(answer_text)} chars"
                )
            except Exception as e:
                logger.error(f"MiniMax returned JSON that failed Pydantic validation: {e}")
                # Include the raw response in the error message for debugging
                error_msg = (
                    f"MiniMax JSON validation error: {e}\n\n"
                    f"RAW RESPONSE:\n{function_args}"
                )
                raise ValueError(error_msg) from e

            # Check if citations are included (always true for structured output with quotes)
            citations_included = request.config.include_citations

            # Calculate confidence (MiniMax doesn't provide logprobs, use default)
            confidence = 0.8

            # Token count
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
            token_count = response.usage.total_tokens

            logger.info(
                "MiniMax generation completed",
                extra={
                    "latency_ms": latency_ms,
                    "token_count": token_count,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "confidence": confidence,
                },
            )

            return LLMResponse(
                response_id=uuid4(),
                answer_text=answer_text,
                confidence_score=confidence,
                token_count=token_count,
                latency_ms=latency_ms,
                provider="alibaba",
                model_version=self.model,
                citations_included=citations_included,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        except TimeoutError as e:
            logger.warning(f"MiniMax API timeout after {request.config.timeout_seconds}s")
            raise LLMTimeoutError(
                f"MiniMax generation exceeded {request.config.timeout_seconds}s timeout"
            ) from e

        except Exception as e:
            error_msg = str(e).lower()

            if "rate_limit" in error_msg or "429" in error_msg:
                logger.warning(f"MiniMax rate limit exceeded: {e}")
                raise RateLimitError(f"MiniMax rate limit: {e}") from e

            if "authentication" in error_msg or "401" in error_msg or "invalid_api_key" in error_msg:
                logger.error(f"MiniMax authentication failed: {e}")
                raise AuthenticationError(f"MiniMax auth error: {e}") from e

            if (
                "content_policy" in error_msg
                or "content_filter" in error_msg
                or "unsafe" in error_msg
            ):
                logger.warning(f"MiniMax content filtered: {e}")
                raise ContentFilterError(f"MiniMax content filter: {e}") from e

            logger.error(f"MiniMax generation error: {e}")
            raise

    async def extract_pdf(self, _request: ExtractionRequest) -> ExtractionResponse:
        """Extract markdown from PDF using MiniMax.

        Note: MiniMax API does not currently support vision/PDF extraction.
        This method is not implemented.

        Args:
            request: Extraction request with PDF file

        Returns:
            ExtractionResponse with markdown content

        Raises:
            NotImplementedError: PDF extraction not supported
        """
        logger.warning("MiniMax PDF extraction is not currently supported")
        raise NotImplementedError(
            "MiniMax does not support vision/PDF extraction. "
            "Use gemini-2.5-pro or gemini-2.5-flash for PDF extraction instead."
        )
