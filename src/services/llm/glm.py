"""GLM LLM adapter using Z.AI API.

Implements LLMProvider interface for GLM models (glm-5, glm-4.7).
Based on specs/001-we-are-building/contracts/llm-adapter.md

Note: GLM uses OpenAI-compatible API endpoint.
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


class GLMAdapter(LLMProvider):
    """Z.AI GLM API integration using OpenAI-compatible endpoint."""

    GLM_BASE_URL = "https://api.z.ai/api/coding/paas/v4"

    def __init__(self, api_key: str, model: str = "glm-4.7"):
        """Initialize GLM adapter.

        Args:
            api_key: Z.AI API key
            model: GLM model identifier (glm-5, glm-4.7)
        """
        super().__init__(api_key, model)

        if AsyncOpenAI is None:
            raise ImportError("openai package not installed. Run: pip install openai")

        # GLM API is OpenAI-compatible, use custom base URL
        self.client = AsyncOpenAI(api_key=api_key, base_url=self.GLM_BASE_URL)

        logger.info(f"Initialized GLM adapter with model {model}")

    async def generate(self, request: GenerationRequest) -> LLMResponse:
        """Generate answer using GLM API.

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

            # Call GLM API with timeout
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
                    raise TokenLimitError("GLM output was truncated due to max_tokens limit")
                refusal = getattr(choice.message, "refusal", None)
                if refusal:
                    raise ContentFilterError(f"GLM refused to respond: {refusal}")
                raise Exception(
                    f"GLM returned empty content (finish_reason: {choice.finish_reason})"
                )

            # Validate with Pydantic for type safety
            try:
                parsed_output = pydantic_model.model_validate_json(content)
                answer_text = parsed_output.model_dump_json()
                logger.debug(
                    f"Extracted structured JSON from GLM (Pydantic): {len(answer_text)} chars"
                )
            except Exception as e:
                logger.error(f"GLM returned JSON that failed Pydantic validation: {e}")
                # Include the raw response in the error message for debugging
                error_msg = (
                    f"GLM JSON validation error: {e}\n\n"
                    f"RAW RESPONSE:\n{content}"
                )
                raise ValueError(error_msg) from e

            # Check if citations are included (always true for structured output with quotes)
            citations_included = request.config.include_citations

            # Calculate confidence (GLM doesn't provide logprobs, use default)
            confidence = 0.8

            # Token count
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
            token_count = response.usage.total_tokens

            logger.info(
                "GLM generation completed",
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
            logger.warning(f"GLM API timeout after {request.config.timeout_seconds}s")
            raise LLMTimeoutError(
                f"GLM generation exceeded {request.config.timeout_seconds}s timeout"
            ) from e

        except Exception as e:
            error_msg = str(e).lower()

            if "rate_limit" in error_msg or "429" in error_msg:
                logger.warning(f"GLM rate limit exceeded: {e}")
                raise RateLimitError(f"GLM rate limit: {e}") from e

            if "authentication" in error_msg or "401" in error_msg or "invalid_api_key" in error_msg:
                logger.error(f"GLM authentication failed: {e}")
                raise AuthenticationError(f"GLM auth error: {e}") from e

            if (
                "content_policy" in error_msg
                or "content_filter" in error_msg
                or "unsafe" in error_msg
            ):
                logger.warning(f"GLM content filtered: {e}")
                raise ContentFilterError(f"GLM content filter: {e}") from e

            logger.error(f"GLM generation error: {e}")
            raise

    async def extract_pdf(self, _request: ExtractionRequest) -> ExtractionResponse:
        """Extract markdown from PDF using GLM.

        Note: GLM API does not currently support vision/PDF extraction.
        This method is not implemented.

        Args:
            request: Extraction request with PDF file

        Returns:
            ExtractionResponse with markdown content

        Raises:
            NotImplementedError: PDF extraction not supported
        """
        logger.warning("GLM PDF extraction is not currently supported")
        raise NotImplementedError(
            "GLM does not support vision/PDF extraction. "
            "Use gemini-2.5-pro or gemini-2.5-flash for PDF extraction instead."
        )
