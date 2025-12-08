"""Mistral LLM adapter using Mistral AI API.

Implements LLMProvider interface for Mistral models.
Based on specs/001-we-are-building/contracts/llm-adapter.md
"""

import time
from uuid import uuid4

import httpx
import pydantic

from src.lib.logging import get_logger
from src.services.llm.base import (
    AuthenticationError,
    ContentFilterError,
    ExtractionRequest,
    ExtractionResponse,
    GenerationRequest,
    LLMProvider,
    LLMResponse,
    PDFParseError,
    RateLimitError,
    TokenLimitError,
)
from src.services.llm.base import TimeoutError as LLMTimeoutError
from src.services.llm.schemas import Answer, HopEvaluation

logger = get_logger(__name__)


class MistralAdapter(LLMProvider):
    """Mistral AI API integration."""

    def __init__(self, api_key: str, model: str = "mistral-large-latest"):
        """Initialize Mistral adapter.

        Args:
            api_key: Mistral API key
            model: Mistral model identifier
        """
        super().__init__(api_key, model)

        if httpx is None:
            raise ImportError("httpx package not installed. Run: pip install httpx")

        self.base_url = "https://api.mistral.ai/v1"
        self.headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        logger.info(f"Initialized Mistral adapter with model {model}")

    async def generate(self, request: GenerationRequest) -> LLMResponse:
        """Generate answer using Mistral API.

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

            # Build API request payload with structured output using Pydantic JSON schema
            # Mistral supports OpenAI-compatible response_format for structured outputs
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": request.config.system_prompt},
                    {"role": "user", "content": full_prompt},
                ],
                "max_tokens": request.config.max_tokens,
                "temperature": request.config.temperature,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": pydantic_model.__name__,
                        "schema": pydantic_model.model_json_schema(),
                        "strict": True,
                    },
                },
            }

            # Call Mistral API with timeout
            async with httpx.AsyncClient(timeout=request.config.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions", headers=self.headers, json=payload
                )

            latency_ms = int((time.time() - start_time) * 1000)

            # Handle HTTP errors
            if response.status_code == 429:
                logger.warning(f"Mistral rate limit exceeded: {response.text}")
                raise RateLimitError(f"Mistral rate limit: {response.text}")
            elif response.status_code == 401:
                logger.error(f"Mistral authentication failed: {response.text}")
                raise AuthenticationError(f"Mistral auth error: {response.text}")
            elif response.status_code >= 400:
                logger.error(f"Mistral API error {response.status_code}: {response.text}")
                raise Exception(f"Mistral API error {response.status_code}: {response.text}")

            # Parse response
            response_data = response.json()

            # Extract structured JSON from response
            if not response_data.get("choices") or len(response_data["choices"]) == 0:
                raise Exception("Mistral returned no choices in response")

            choice = response_data["choices"][0]
            message = choice.get("message", {})

            # Check finish_reason for errors
            finish_reason = choice.get("finish_reason")
            if finish_reason == "content_filter":
                raise ContentFilterError("Mistral content filter blocked response")
            elif finish_reason == "length":
                raise TokenLimitError("Mistral output was truncated due to max_tokens limit")

            # Extract JSON content from message
            content = message.get("content", "")
            if not content:
                raise Exception(
                    f"Mistral returned no content (finish_reason: {finish_reason})"
                )

            # Parse and validate JSON with Pydantic
            try:
                # Validate with Pydantic model for type safety
                parsed_output = pydantic_model.model_validate_json(content)
                answer_text = parsed_output.model_dump_json()
                logger.debug(
                    f"Extracted structured JSON from Mistral (Pydantic): {len(answer_text)} chars"
                )
            except pydantic.ValidationError as e:
                logger.error(f"Mistral returned JSON that failed Pydantic validation: {e}")
                # Include the raw response in the error message for debugging
                error_msg = (
                    f"Mistral returned JSON that failed schema validation: {e}\n\n"
                    f"RAW RESPONSE:\n{content}"
                )
                raise ValueError(error_msg) from e
            except Exception as e:
                logger.exception("Unexpected error during Mistral response parsing")
                # Include the raw response in the error message for debugging
                error_msg = (
                    f"Unexpected error parsing Mistral response: {e}\n\n"
                    f"RAW RESPONSE:\n{content}"
                )
                raise ValueError(error_msg) from e

            # Check if citations are included (always true for structured output with quotes)
            citations_included = request.config.include_citations

            # Default confidence (Mistral doesn't provide logprobs with structured output)
            confidence = 0.8

            # Token count
            usage = response_data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            token_count = usage.get("total_tokens", 0)

            logger.info(
                "Mistral generation completed",
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
                provider="mistral",
                model_version=self.model,
                citations_included=citations_included,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        except Exception as e:
            if isinstance(
                e,
                (
                    RateLimitError,
                    AuthenticationError,
                    LLMTimeoutError,
                    ContentFilterError,
                    TokenLimitError,
                ),
            ):
                raise

            error_msg = str(e).lower()

            # Check for timeout-related errors
            if (
                "timeout" in error_msg
                or hasattr(e, "__class__")
                and e.__class__.__name__ in ("TimeoutException", "TimeoutError")
            ):
                logger.warning(f"Mistral API timeout after {request.config.timeout_seconds}s")
                raise LLMTimeoutError(
                    f"Mistral generation exceeded {request.config.timeout_seconds}s timeout"
                ) from e

            if "rate_limit" in error_msg or "429" in error_msg:
                logger.warning(f"Mistral rate limit exceeded: {e}")
                raise RateLimitError(f"Mistral rate limit: {e}") from e

            if "authentication" in error_msg or "401" in error_msg:
                logger.error(f"Mistral authentication failed: {e}")
                raise AuthenticationError(f"Mistral auth error: {e}") from e

            if (
                "content_policy" in error_msg
                or "content_filter" in error_msg
                or "unsafe" in error_msg
            ):
                logger.warning(f"Mistral content filtered: {e}")
                raise ContentFilterError(f"Mistral content filter: {e}") from e

            logger.error(f"Mistral generation error: {e}")
            raise

    async def extract_pdf(self, request: ExtractionRequest) -> ExtractionResponse:
        """Extract markdown from PDF using Mistral.

        Note: Mistral currently doesn't support direct PDF processing.
        This method is a placeholder for future implementation.

        Args:
            request: Extraction request with PDF file

        Returns:
            ExtractionResponse with markdown content

        Raises:
            PDFParseError: PDF parsing failed
            LLMTimeoutError: Extraction timeout
            TokenLimitError: PDF too large
        """
        time.time()

        try:
            # Read PDF bytes
            pdf_bytes = request.pdf_file.read()

            if len(pdf_bytes) == 0:
                raise PDFParseError("PDF file is empty")

            # Mistral doesn't currently support direct PDF processing
            # In production, you'd convert PDF to text/images first
            logger.warning("Mistral PDF extraction requires text conversion (not implemented)")

            # Placeholder: In production, convert PDF to text and send to Mistral
            raise NotImplementedError("Mistral PDF extraction requires PDF-to-text conversion")

        except TimeoutError as e:
            logger.warning("Mistral PDF extraction timeout")
            raise LLMTimeoutError(
                f"Mistral extraction exceeded {request.config.timeout_seconds}s timeout"
            ) from e

        except NotImplementedError:
            raise

        except Exception as e:
            error_msg = str(e).lower()

            if "token" in error_msg and "limit" in error_msg:
                logger.error(f"Mistral token limit exceeded: {e}")
                raise TokenLimitError(f"Mistral token limit: {e}") from e

            if "pdf" in error_msg or "parse" in error_msg:
                logger.error(f"Mistral PDF parse error: {e}")
                raise PDFParseError(f"Mistral PDF error: {e}") from e

            logger.error(f"Mistral extraction error: {e}")
            raise

    def _validate_extraction(self, markdown: str) -> list[str]:
        """Validate extracted markdown for required fields.

        Args:
            markdown: Extracted markdown content

        Returns:
            List of validation warnings
        """
        warnings = []

        # Check for YAML frontmatter
        if not markdown.startswith("---"):
            warnings.append("Missing YAML frontmatter")

        # Check for required YAML fields
        required_fields = ["source", "last_update_date", "document_type"]
        for field in required_fields:
            if f"{field}:" not in markdown[:500]:
                warnings.append(f"Missing required field: {field}")

        # Check for markdown headings
        if "##" not in markdown:
            warnings.append("No markdown headings found")

        return warnings
