"""Kimi K2.5 LLM adapter using OpenAI-compatible API.

Implements LLMProvider interface for Moonshot Kimi models (kimi-k2.5, kimi-k2-0905-preview, kimi-k2-turbo-preview).
Based on specs/001-we-are-building/contracts/llm-adapter.md

Note: Kimi K2.5 has thinking mode enabled by default, which is incompatible with tool_choice.
We use JSON mode with schema in prompt instead of function calling.
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
)
from src.services.llm.base import TimeoutError as LLMTimeoutError
from src.services.llm.schemas import Answer, HopEvaluation

logger = get_logger(__name__)


class KimiAdapter(LLMProvider):
    """Kimi API integration using OpenAI-compatible endpoint."""

    KIMI_BASE_URL = "https://api.moonshot.ai/v1"

    def __init__(self, api_key: str, model: str = "kimi-k2.5"):
        """Initialize Kimi adapter.

        Args:
            api_key: Moonshot API key
            model: Kimi model identifier (kimi-k2.5, kimi-k2-0905-preview, kimi-k2-turbo-preview)
        """
        super().__init__(api_key, model)

        if AsyncOpenAI is None:
            raise ImportError("openai package not installed. Run: pip install openai")

        # Kimi API is OpenAI-compatible, use custom base URL
        self.client = AsyncOpenAI(api_key=api_key, base_url=self.KIMI_BASE_URL)

        logger.info(f"Initialized Kimi adapter with model {model}")

    async def generate(self, request: GenerationRequest) -> LLMResponse:
        """Generate answer using Kimi API.

        Uses JSON mode with schema in prompt (not function calling) because
        Kimi K2.5 has thinking mode enabled by default which is incompatible with tool_choice.

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

            if schema_type == "hop_evaluation":
                pydantic_model = HopEvaluation
                logger.debug("Using hop evaluation schema (Pydantic)")
            else:  # "default"
                pydantic_model = Answer
                logger.debug("Using default answer schema (Pydantic)")

            # Get JSON schema and add it to the system prompt
            json_schema = pydantic_model.model_json_schema()
            schema_instruction = (
                "\n\nIMPORTANT: You MUST respond with valid JSON matching this exact schema:\n"
                f"```json\n{json.dumps(json_schema, indent=2)}\n```\n"
                "Do not include any text before or after the JSON object."
            )
            system_prompt_with_schema = request.config.system_prompt + schema_instruction

            # Kimi K2.5 only supports temperature=1.0
            # Other Kimi models may support different temperatures
            temperature = request.config.temperature
            if self.model == "kimi-k2.5":
                temperature = 1.0

            # Kimi K2.5 has thinking mode enabled, which uses internal reasoning tokens
            # Multiply max_tokens by 3 to account for reasoning tokens (similar to GPT-5/o-series)
            max_tokens = request.config.max_tokens
            if self.model == "kimi-k2.5":
                max_tokens = request.config.max_tokens * 3
                logger.debug(
                    f"Kimi K2.5: Using max_tokens={max_tokens} "
                    f"(3x {request.config.max_tokens} to account for thinking tokens)"
                )

            # Use JSON mode instead of function calling
            # Kimi K2.5 has thinking enabled by default, which is incompatible with tool_choice
            api_params = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt_with_schema},
                    {"role": "user", "content": full_prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "response_format": {"type": "json_object"},
            }

            # Call Kimi API with timeout
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
                    raise TokenLimitError("Kimi output was truncated due to max_tokens limit")
                refusal = getattr(choice.message, "refusal", None)
                if refusal:
                    raise ContentFilterError(f"Kimi refused to respond: {refusal}")
                raise Exception(
                    f"Kimi returned empty content (finish_reason: {choice.finish_reason})"
                )

            # Validate with Pydantic for type safety
            try:
                parsed_output = pydantic_model.model_validate_json(content)
                answer_text = parsed_output.model_dump_json()
                logger.debug(
                    f"Extracted structured JSON from Kimi (Pydantic): {len(answer_text)} chars"
                )
            except Exception as e:
                logger.error(f"Kimi returned JSON that failed Pydantic validation: {e}")
                # Include the raw response in the error message for debugging
                error_msg = (
                    f"Kimi JSON validation error: {e}\n\n"
                    f"RAW RESPONSE:\n{content}"
                )
                raise ValueError(error_msg) from e

            # Check if citations are included (always true for structured output with quotes)
            citations_included = request.config.include_citations

            # Calculate confidence (Kimi doesn't provide logprobs, use default)
            confidence = 0.8

            # Token count
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
            token_count = response.usage.total_tokens

            logger.info(
                "Kimi generation completed",
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
                provider="moonshot",
                model_version=self.model,
                citations_included=citations_included,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        except TimeoutError as e:
            logger.warning(f"Kimi API timeout after {request.config.timeout_seconds}s")
            raise LLMTimeoutError(
                f"Kimi generation exceeded {request.config.timeout_seconds}s timeout"
            ) from e

        except Exception as e:
            error_msg = str(e).lower()

            if "rate_limit" in error_msg or "429" in error_msg:
                logger.warning(f"Kimi rate limit exceeded: {e}")
                raise RateLimitError(f"Kimi rate limit: {e}") from e

            if "authentication" in error_msg or "401" in error_msg or "invalid_api_key" in error_msg:
                logger.error(f"Kimi authentication failed: {e}")
                raise AuthenticationError(f"Kimi auth error: {e}") from e

            if (
                "content_policy" in error_msg
                or "content_filter" in error_msg
                or "unsafe" in error_msg
            ):
                logger.warning(f"Kimi content filtered: {e}")
                raise ContentFilterError(f"Kimi content filter: {e}") from e

            logger.error(f"Kimi generation error: {e}")
            raise

    async def extract_pdf(self, _request: ExtractionRequest) -> ExtractionResponse:
        """Extract markdown from PDF using Kimi.

        Note: Kimi API does not currently support vision/PDF extraction.
        This method is not implemented.

        Args:
            request: Extraction request with PDF file

        Returns:
            ExtractionResponse with markdown content

        Raises:
            NotImplementedError: PDF extraction not supported
        """
        logger.warning("Kimi PDF extraction is not currently supported")
        raise NotImplementedError(
            "Kimi does not support vision/PDF extraction. "
            "Use gemini-2.5-pro or gemini-2.5-flash for PDF extraction instead."
        )
