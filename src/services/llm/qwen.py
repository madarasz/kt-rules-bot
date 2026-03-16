"""Qwen LLM adapter using Alibaba Cloud DashScope API.

Implements LLMProvider interface for Qwen models (qwen3-max, qwen3.5-plus, qwen3-coder).
Based on specs/001-we-are-building/contracts/llm-adapter.md

Note: Qwen uses OpenAI-compatible API endpoint.
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
)
from src.services.llm.base import TimeoutError as LLMTimeoutError

logger = get_logger(__name__)


class QwenAdapter(LLMProvider):
    """Alibaba Cloud Qwen API integration using OpenAI-compatible endpoint."""

    DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    CODING_PLAN_BASE_URL = "https://coding.dashscope.aliyuncs.com/v1"

    def __init__(self, api_key: str, model: str = "qwen3.5-plus"):
        """Initialize Qwen adapter.

        Args:
            api_key: Alibaba Cloud DashScope API key
            model: Qwen model identifier (qwen3-max-2026-01-23, qwen3.5-plus, qwen3-coder-next, qwen3-coder-plus)
        """
        super().__init__(api_key, model)

        if AsyncOpenAI is None:
            raise ImportError("openai package not installed. Run: pip install openai")

        # Qwen API is OpenAI-compatible, use custom base URL
        # Use Coding Plan base URL for sk-sp-* keys, otherwise use general base URL
        base_url = self.CODING_PLAN_BASE_URL if api_key.startswith("sk-sp-") else self.DASHSCOPE_BASE_URL
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

        logger.info(f"Initialized Qwen adapter with model {model}, base_url={base_url}")

    async def generate(self, request: GenerationRequest) -> LLMResponse:
        """Generate answer using Qwen API.

        Uses JSON mode with schema in prompt for structured output.

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
            pydantic_model = get_pydantic_model(schema_type)
            logger.debug(f"Using {schema_type} schema (Pydantic)")

            # Get JSON schema and add it to the system prompt
            json_schema = pydantic_model.model_json_schema()
            schema_instruction = (
                "\n\nIMPORTANT: You MUST respond with valid JSON matching this exact schema:\n"
                f"```json\n{json.dumps(json_schema, indent=2)}\n```\n"
                "Do not include any text before or after the JSON object."
            )
            system_prompt_with_schema = request.config.system_prompt + schema_instruction

            # Use JSON mode for structured output
            api_params = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt_with_schema},
                    {"role": "user", "content": full_prompt},
                ],
                "max_tokens": request.config.max_tokens,
                "temperature": request.config.temperature,
                "response_format": {"type": "json_object"},
            }

            # Call Qwen API with timeout
            response = await asyncio.wait_for(
                self.client.chat.completions.create(**api_params),
                timeout=request.config.timeout_seconds,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            # Extract response content
            choice = response.choices[0]
            content = choice.message.content

            if not content:
                if choice.finish_reason == "length":
                    raise TokenLimitError("Qwen output was truncated due to max_tokens limit")
                refusal = getattr(choice.message, "refusal", None)
                if refusal:
                    raise ContentFilterError(f"Qwen refused to respond: {refusal}")
                raise Exception(
                    f"Qwen returned empty content (finish_reason: {choice.finish_reason})"
                )

            # Validate with Pydantic for type safety
            try:
                parsed_output = pydantic_model.model_validate_json(content)
                answer_text = parsed_output.model_dump_json()
                logger.debug(
                    f"Extracted structured JSON from Qwen (Pydantic): {len(answer_text)} chars"
                )
            except Exception as e:
                logger.error(f"Qwen returned JSON that failed Pydantic validation: {e}")
                # Include the raw response in the error message for debugging
                error_msg = (
                    f"Qwen JSON validation error: {e}\n\n"
                    f"RAW RESPONSE:\n{content}"
                )
                raise ValueError(error_msg) from e

            # Check if citations are included (always true for structured output with quotes)
            citations_included = request.config.include_citations

            # Calculate confidence (Qwen doesn't provide logprobs, use default)
            confidence = 0.8

            # Token count
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
            token_count = response.usage.total_tokens

            logger.info(
                "Qwen generation completed",
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
            logger.warning(f"Qwen API timeout after {request.config.timeout_seconds}s")
            raise LLMTimeoutError(
                f"Qwen generation exceeded {request.config.timeout_seconds}s timeout"
            ) from e

        except Exception as e:
            error_msg = str(e).lower()

            if "rate_limit" in error_msg or "429" in error_msg:
                logger.warning(f"Qwen rate limit exceeded: {e}")
                raise RateLimitError(f"Qwen rate limit: {e}") from e

            if "authentication" in error_msg or "401" in error_msg or "invalid_api_key" in error_msg:
                logger.error(f"Qwen authentication failed: {e}")
                raise AuthenticationError(f"Qwen auth error: {e}") from e

            if (
                "content_policy" in error_msg
                or "content_filter" in error_msg
                or "unsafe" in error_msg
            ):
                logger.warning(f"Qwen content filtered: {e}")
                raise ContentFilterError(f"Qwen content filter: {e}") from e

            logger.error(f"Qwen generation error: {e}")
            raise

    async def extract_pdf(self, _request: ExtractionRequest) -> ExtractionResponse:
        """Extract markdown from PDF using Qwen.

        Note: Qwen API does not currently support vision/PDF extraction.
        This method is not implemented.

        Args:
            request: Extraction request with PDF file

        Returns:
            ExtractionResponse with markdown content

        Raises:
            NotImplementedError: PDF extraction not supported
        """
        logger.warning("Qwen PDF extraction is not currently supported")
        raise NotImplementedError(
            "Qwen does not support vision/PDF extraction. "
            "Use gemini-2.5-pro or gemini-2.5-flash for PDF extraction instead."
        )
