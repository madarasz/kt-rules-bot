"""Dial LLM adapter using EPAM AI Proxy.

Implements LLMProvider interface for Dial models.
Based on specs/001-we-are-building/contracts/llm-adapter.md
"""

import time
from uuid import uuid4

try:
    import httpx
except ImportError:
    httpx = None

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
from src.services.llm.base import (
    TimeoutError as LLMTimeoutError,
)

logger = get_logger(__name__)


class DialAdapter(LLMProvider):
    """EPAM AI Proxy Dial API integration."""

    def __init__(self, api_key: str, model: str = "gpt-4"):
        """Initialize Dial adapter.

        Args:
            api_key: Dial API key
            model: Dial model identifier
        """
        super().__init__(api_key, model)

        if httpx is None:
            raise ImportError("httpx package not installed. Run: pip install httpx")

        self.base_url = f"https://ai-proxy.lab.epam.com/openai/deployments/{model}/chat/completions"
        self.headers = {
            "Api-Key": api_key,
            "Content-Type": "application/json",
        }

        # Model capabilities
        self.supports_temperature = model != "dial-gpt-5-mini"
        self.supports_max_tokens = model != "dial-gpt-5-mini"
        self.supports_logprobs = False  # Dial doesn't support logprobs yet

        logger.info(f"Initialized Dial adapter with model {model}")

    async def generate(self, request: GenerationRequest) -> LLMResponse:
        """Generate answer using Dial API.

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

        # Build prompt with context
        full_prompt = self._build_prompt(request.prompt, request.context)

        try:
            # Build API request payload
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": request.config.system_prompt},
                    {"role": "user", "content": full_prompt},
                ],
                "stream": False,
            }

            # Add optional parameters based on model capabilities
            if self.supports_max_tokens:
                payload["max_tokens"] = request.config.max_tokens

            if self.supports_temperature:
                payload["temperature"] = request.config.temperature

            if self.supports_logprobs:
                payload["logprobs"] = True
                payload["top_logprobs"] = 5

            # Call Dial API with timeout
            async with httpx.AsyncClient(timeout=request.config.timeout_seconds) as client:
                response = await client.post(
                    self.base_url,
                    headers=self.headers,
                    json=payload,
                )

            latency_ms = int((time.time() - start_time) * 1000)

            # Handle HTTP errors
            if response.status_code == 429:
                logger.warning(f"Dial rate limit exceeded: {response.text}")
                raise RateLimitError(f"Dial rate limit: {response.text}")
            elif response.status_code == 401:
                logger.error(f"Dial authentication failed: {response.text}")
                raise AuthenticationError(f"Dial auth error: {response.text}")
            elif response.status_code >= 400:
                logger.error(f"Dial API error {response.status_code}: {response.text}")
                raise Exception(f"Dial API error {response.status_code}: {response.text}")

            # Parse response
            response_data = response.json()

            # Extract answer text
            if not response_data.get("choices") or len(response_data["choices"]) == 0:
                raise Exception("Dial returned no choices in response")

            choice = response_data["choices"][0]
            answer_text = choice.get("message", {}).get("content")

            if not answer_text:
                finish_reason = choice.get("finish_reason")
                logger.warning(f"Dial returned empty content. Finish reason: {finish_reason}")

                if finish_reason == "content_filter":
                    raise ContentFilterError("Dial content filter blocked response")
                elif finish_reason == "length":
                    raise TokenLimitError("Dial output was truncated due to max_tokens limit")
                else:
                    raise Exception(f"Dial returned empty content with finish_reason: {finish_reason}")

            # Check if citations are included
            citations_included = (
                request.config.include_citations
                and "According to" in answer_text
            )

            # Default confidence (Dial doesn't provide logprobs yet)
            confidence = 0.8

            # Token count
            usage = response_data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            token_count = usage.get("total_tokens", 0)

            logger.info(
                "Dial generation completed",
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
                provider="dial",
                model_version=self.model,
                citations_included=citations_included,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        except Exception as e:
            if isinstance(e, (RateLimitError, AuthenticationError, LLMTimeoutError, ContentFilterError, TokenLimitError)):
                raise

            error_msg = str(e).lower()

            # Check for timeout-related errors
            if ("timeout" in error_msg or hasattr(e, '__class__') and
                e.__class__.__name__ in ('TimeoutException', 'TimeoutError')):
                logger.warning(
                    f"Dial API timeout after {request.config.timeout_seconds}s"
                )
                raise LLMTimeoutError(
                    f"Dial generation exceeded {request.config.timeout_seconds}s timeout"
                ) from e

            if "rate_limit" in error_msg or "429" in error_msg:
                logger.warning(f"Dial rate limit exceeded: {e}")
                raise RateLimitError(f"Dial rate limit: {e}") from e

            if "authentication" in error_msg or "401" in error_msg:
                logger.error(f"Dial authentication failed: {e}")
                raise AuthenticationError(f"Dial auth error: {e}") from e

            if (
                "content_policy" in error_msg
                or "content_filter" in error_msg
                or "unsafe" in error_msg
            ):
                logger.warning(f"Dial content filtered: {e}")
                raise ContentFilterError(f"Dial content filter: {e}") from e

            logger.error(f"Dial generation error: {e}")
            raise

    async def extract_pdf(self, request: ExtractionRequest) -> ExtractionResponse:
        pass
