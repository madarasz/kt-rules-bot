"""Gemini LLM adapter using Google AI API.

Implements LLMProvider interface for Gemini models.
Based on specs/001-we-are-building/contracts/llm-adapter.md
"""

import asyncio
import time
from typing import BinaryIO
from uuid import uuid4

try:
    import google.generativeai as genai
except ImportError:
    genai = None

from src.services.llm.base import (
    LLMProvider,
    GenerationRequest,
    LLMResponse,
    ExtractionRequest,
    ExtractionResponse,
    RateLimitError,
    AuthenticationError,
    TimeoutError as LLMTimeoutError,
    ContentFilterError,
    PDFParseError,
)
from src.lib.logging import get_logger

logger = get_logger(__name__)


class GeminiAdapter(LLMProvider):
    """Google Gemini API integration."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-pro"):
        """Initialize Gemini adapter.

        Args:
            api_key: Google API key
            model: Gemini model identifier
        """
        super().__init__(api_key, model)

        if genai is None:
            raise ImportError(
                "google-generativeai package not installed. "
                "Run: pip install google-generativeai"
            )

        genai.configure(api_key=api_key)
        self.client = genai.GenerativeModel(model)
        logger.info(f"Initialized Gemini adapter with model {model}")

    async def generate(self, request: GenerationRequest) -> LLMResponse:
        """Generate answer using Gemini API.

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

        # Build prompt with system message and context
        full_prompt = f"{request.config.system_prompt}\n\n{self._build_prompt(request.prompt, request.context)}"

        try:
            # Configure generation
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=request.config.max_tokens,
                temperature=request.config.temperature,
            )

            # Call Gemini API with timeout
            # Note: google-generativeai doesn't have native async support yet
            # We wrap it in asyncio.to_thread for async compatibility
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.generate_content,
                    full_prompt,
                    generation_config=generation_config,
                ),
                timeout=request.config.timeout_seconds,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            # Check finish_reason before accessing text
            # Gemini FinishReason enum values:
            # FINISH_REASON_UNSPECIFIED = 0, STOP = 1, MAX_TOKENS = 2
            # SAFETY = 3, RECITATION = 4, LANGUAGE = 6, OTHER = 5
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                finish_reason = candidate.finish_reason

                # Log finish_reason for debugging
                logger.debug(f"Gemini finish_reason: {finish_reason}")

                # Check if response was blocked
                # Note: finish_reason=2 with no parts means RECITATION block, not MAX_TOKENS
                if finish_reason in [3, 4]:  # SAFETY or RECITATION
                    finish_reason_names = {3: "SAFETY", 4: "RECITATION"}
                    reason_name = finish_reason_names.get(finish_reason, str(finish_reason))
                    logger.warning(f"Gemini content blocked: finish_reason={reason_name}")
                    raise ContentFilterError(
                        f"Gemini blocked content due to {reason_name} filters. "
                        "This query may contain content flagged by safety filters. "
                        "Try rephrasing or use a different model (--provider claude-sonnet)."
                    )
                elif finish_reason == 2 and not candidate.content.parts:
                    # finish_reason=2 with no parts typically means RECITATION
                    logger.warning(f"Gemini blocked content: finish_reason=2 (likely RECITATION)")
                    raise ContentFilterError(
                        "Gemini blocked content (likely due to RECITATION filter). "
                        "The response may be too similar to training data. "
                        "Try rephrasing or use a different model (--provider claude-sonnet)."
                    )
                elif finish_reason == 2:  # MAX_TOKENS with parts
                    logger.warning(f"Gemini response truncated: finish_reason=MAX_TOKENS")
                elif finish_reason not in [1]:  # Not STOP
                    logger.warning(f"Gemini unexpected finish_reason: {finish_reason}")

            # Extract answer text (may raise exception if no valid parts)
            try:
                answer_text = response.text
            except ValueError as e:
                # response.text throws ValueError when no valid parts exist
                logger.error(f"Gemini response has no valid text parts: {e}")
                raise ContentFilterError(
                    "Gemini response was blocked. The query may have triggered safety filters. "
                    "Try rephrasing or use a different model (--provider claude-sonnet)."
                )

            # Check if citations are included
            citations_included = (
                request.config.include_citations
                and "According to" in answer_text
            )

            # Map safety ratings to confidence
            confidence = self._safety_to_confidence(
                getattr(response, "safety_ratings", None)
            )

            # Token count from usage metadata
            token_count = (
                response.usage_metadata.total_token_count
                if hasattr(response, "usage_metadata")
                else 0
            )

            logger.info(
                f"Gemini generation completed",
                extra={
                    "latency_ms": latency_ms,
                    "token_count": token_count,
                    "confidence": confidence,
                },
            )

            return LLMResponse(
                response_id=uuid4(),
                answer_text=answer_text,
                confidence_score=confidence,
                token_count=token_count,
                latency_ms=latency_ms,
                provider="gemini",
                model_version=self.model,
                citations_included=citations_included,
            )

        except asyncio.TimeoutError:
            logger.warning(f"Gemini API timeout after {request.config.timeout_seconds}s")
            raise LLMTimeoutError(
                f"Gemini generation exceeded {request.config.timeout_seconds}s timeout"
            )

        except ContentFilterError:
            # Re-raise ContentFilterError without wrapping
            raise

        except Exception as e:
            error_msg = str(e).lower()

            if "quota" in error_msg or "429" in error_msg:
                logger.warning(f"Gemini rate limit exceeded: {e}")
                raise RateLimitError(f"Gemini rate limit: {e}")

            if "api_key" in error_msg or "authentication" in error_msg or "401" in error_msg:
                logger.error(f"Gemini authentication failed: {e}")
                raise AuthenticationError(f"Gemini auth error: {e}")

            # Check for finish_reason errors (blocked content)
            if "finish_reason" in error_msg or "safety" in error_msg or "blocked" in error_msg or "recitation" in error_msg:
                logger.warning(f"Gemini content filtered: {e}")
                raise ContentFilterError(f"Gemini content filter: {e}")

            logger.error(f"Gemini generation error: {e}")
            raise

    async def extract_pdf(self, request: ExtractionRequest) -> ExtractionResponse:
        """Extract markdown from PDF using Gemini vision.

        Args:
            request: Extraction request with PDF file

        Returns:
            ExtractionResponse with markdown content

        Raises:
            PDFParseError: PDF parsing failed
            LLMTimeoutError: Extraction timeout
        """
        start_time = time.time()

        try:
            # Read PDF bytes
            pdf_bytes = request.pdf_file.read()

            if len(pdf_bytes) == 0:
                raise PDFParseError("PDF file is empty")

            # Upload PDF to Gemini
            # Gemini can process PDFs directly
            pdf_file = genai.upload_file(request.pdf_file, mime_type="application/pdf")

            # Configure generation
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=request.config.max_tokens,
                temperature=request.config.temperature,
            )

            # Call Gemini API with PDF and extraction prompt
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.generate_content,
                    [request.extraction_prompt, pdf_file],
                    generation_config=generation_config,
                ),
                timeout=request.config.timeout_seconds,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            markdown_content = response.text
            token_count = (
                response.usage_metadata.total_token_count
                if hasattr(response, "usage_metadata")
                else 0
            )

            # Validate extracted markdown
            validation_warnings = self._validate_extraction(markdown_content)

            logger.info(
                f"Gemini PDF extraction completed",
                extra={
                    "latency_ms": latency_ms,
                    "token_count": token_count,
                    "warnings": len(validation_warnings),
                },
            )

            return ExtractionResponse(
                extraction_id=uuid4(),
                markdown_content=markdown_content,
                token_count=token_count,
                latency_ms=latency_ms,
                provider="gemini",
                model_version=self.model,
                validation_warnings=validation_warnings,
            )

        except asyncio.TimeoutError:
            logger.warning(f"Gemini PDF extraction timeout")
            raise LLMTimeoutError(
                f"Gemini extraction exceeded {request.config.timeout_seconds}s timeout"
            )

        except Exception as e:
            error_msg = str(e).lower()

            if "pdf" in error_msg or "parse" in error_msg or "upload" in error_msg:
                logger.error(f"Gemini PDF parse error: {e}")
                raise PDFParseError(f"Gemini PDF error: {e}")

            logger.error(f"Gemini extraction error: {e}")
            raise

    def _safety_to_confidence(self, safety_ratings) -> float:
        """Map Gemini safety ratings to confidence score.

        Args:
            safety_ratings: Safety ratings from Gemini response

        Returns:
            Confidence score (0-1)
        """
        if not safety_ratings:
            return 0.7  # Default confidence

        # Gemini safety ratings: NEGLIGIBLE, LOW, MEDIUM, HIGH
        # Map to confidence: HIGH_SAFE → 0.9, MEDIUM → 0.7, LOW → 0.5
        safety_map = {
            "NEGLIGIBLE": 0.9,
            "LOW": 0.8,
            "MEDIUM": 0.7,
            "HIGH": 0.5,
        }

        # Average across all safety categories
        confidences = []
        for rating in safety_ratings:
            probability = getattr(rating, "probability", "MEDIUM")
            confidences.append(safety_map.get(probability, 0.7))

        return sum(confidences) / len(confidences) if confidences else 0.7

    def _validate_extraction(self, markdown: str) -> list:
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
