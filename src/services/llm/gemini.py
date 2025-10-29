"""Gemini LLM adapter using Google AI API.

Implements LLMProvider interface for Gemini models.
Based on specs/001-we-are-building/contracts/llm-adapter.md
"""

import asyncio
import time
from typing import BinaryIO
from uuid import uuid4

try:
    from google import genai
    from google import genai as genai_types
except ImportError:
    genai = None
    genai_types = None

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
import json

logger = get_logger(__name__)


# Gemini-specific schemas (Gemini doesn't support additionalProperties field)
STRUCTURED_OUTPUT_SCHEMA_GEMINI = {
    "type": "object",
    "properties": {
        "smalltalk": {
            "type": "boolean",
            "description": "True if this is casual conversation (not rules-related), False if answering a rules question"
        },
        "short_answer": {
            "type": "string",
            "description": "Direct, short answer (e.g., 'Yes.')"
        },
        "persona_short_answer": {
            "type": "string",
            "description": "Short condescending phrase after the direct answer (e.g., 'The affirmative is undeniable.')"
        },
        "quotes": {
            "type": "array",
            "description": "Relevant rule quotations from Kill Team 3rd Edition rules",
            "items": {
                "type": "object",
                "properties": {
                    "quote_title": {
                        "type": "string",
                        "description": "Rule name (e.g., 'Core Rules: Actions')"
                    },
                    "quote_text": {
                        "type": "string",
                        "description": "Relevant excerpt from the rule"
                    }
                },
                "required": ["quote_title", "quote_text"]
            }
        },
        "explanation": {
            "type": "string",
            "description": "Brief rules-based explanation using official Kill Team terminology"
        },
        "persona_afterword": {
            "type": "string",
            "description": "Dismissive concluding sentence (e.g., 'The logic is unimpeachable.')"
        }
    },
    "required": [
        "smalltalk",
        "short_answer",
        "persona_short_answer",
        "quotes",
        "explanation",
        "persona_afterword"
    ]
}

HOP_EVALUATION_SCHEMA_GEMINI = {
    "type": "object",
    "properties": {
        "can_answer": {
            "type": "boolean",
            "description": "True if the retrieved context is sufficient to answer the question, false otherwise"
        },
        "reasoning": {
            "type": "string",
            "description": "Brief explanation (1-2 sentences) of what context you have or what's missing"
        },
        "missing_query": {
            "type": ["string", "null"],
            "description": "If can_answer=false, a focused retrieval query for missing rules. If can_answer=true, null"
        }
    },
    "required": ["can_answer", "reasoning", "missing_query"]
}


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
                "google-genai package not installed. "
                "Run: pip install google-genai"
            )

        self.client = genai.Client(api_key=api_key)
        self.model = model
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
            # Select schema based on configuration
            schema_type = request.config.structured_output_schema

            if schema_type == "hop_evaluation":
                schema = HOP_EVALUATION_SCHEMA_GEMINI
                logger.debug("Using hop evaluation schema")
            else:  # "default"
                schema = STRUCTURED_OUTPUT_SCHEMA_GEMINI
                logger.debug("Using default answer schema")

            # Configure generation with JSON mode for structured output
            # Gemini requires schema without additionalProperties field
            generation_config = {
                "max_output_tokens": request.config.max_tokens,
                "temperature": request.config.temperature,
                "response_mime_type": "application/json",
                "response_schema": schema
            }

            # Call Gemini API with timeout using new API
            # Note: google-genai doesn't have native async support yet
            # We wrap it in asyncio.to_thread for async compatibility
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.models.generate_content,
                    model=self.model,
                    contents=full_prompt,
                    config=generation_config,
                ),
                timeout=request.config.timeout_seconds,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            # Check finish_reason before accessing text
            # New API uses enum strings: STOP, MAX_TOKENS, SAFETY, RECITATION, etc.
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                finish_reason = candidate.finish_reason

                # Log finish_reason for debugging
                logger.debug(f"Gemini finish_reason: {finish_reason}")

                # Get finish_reason as string for comparison (handles both enum and string)
                finish_reason_str = str(finish_reason).split('.')[-1] if hasattr(finish_reason, 'value') else str(finish_reason)

                # Check if response was blocked
                if finish_reason_str in ['SAFETY', 'RECITATION', 'BLOCKLIST', 'PROHIBITED_CONTENT', 'IMAGE_SAFETY', 'IMAGE_PROHIBITED_CONTENT']:
                    logger.warning(f"Gemini content blocked: finish_reason={finish_reason_str}")
                    raise ContentFilterError(
                        f"Gemini blocked content due to {finish_reason_str} filter. "
                        "This query may contain content flagged by safety filters. "
                        "Try rephrasing or use a different model (--provider claude-4.5-sonnet)."
                    )
                elif finish_reason_str == 'MAX_TOKENS' and not candidate.content.parts:
                    # MAX_TOKENS with no parts typically means truncation/blocking
                    logger.warning(f"Gemini content blocked: finish_reason=MAX_TOKENS (no parts)")
                    raise ContentFilterError(
                        "Gemini response was truncated or blocked (MAX_TOKENS with no content). "
                        "Try rephrasing or use a different model (--provider claude-4.5-sonnet)."
                    )
                elif finish_reason_str == 'MAX_TOKENS':  # MAX_TOKENS with parts
                    logger.warning(f"Gemini response truncated: finish_reason=MAX_TOKENS")
                elif finish_reason_str not in ['STOP', 'FINISH_REASON_UNSPECIFIED']:  # Not normal completion
                    logger.warning(f"Gemini unexpected finish_reason: {finish_reason}")

            # Extract JSON answer text (response.text is already JSON string with JSON mode)
            try:
                answer_text = response.text
            except ValueError as e:
                # response.text throws ValueError when no valid parts exist
                logger.error(f"Gemini response has no valid text parts: {e}")
                raise ContentFilterError(
                    "Gemini response was blocked. The query may have triggered safety filters. "
                    "Try rephrasing or use a different model (--provider claude-4.5-sonnet)."
                )

            # Validate JSON is parseable (Gemini can sometimes return invalid JSON)
            try:
                json.loads(answer_text)
                logger.debug(f"Extracted structured JSON from Gemini: {len(answer_text)} chars")
            except json.JSONDecodeError as e:
                logger.error(f"Gemini returned invalid JSON: {e}")
                raise ValueError(
                    f"Gemini returned invalid JSON despite JSON mode. "
                    f"Response may be malformed. Error: {e}"
                )

            # Validate it's not empty
            if not answer_text or not answer_text.strip():
                raise Exception("Gemini returned empty JSON")

            # Check if citations are included (always true for structured output with quotes)
            citations_included = request.config.include_citations

            # Map safety ratings to confidence
            # In new API, safety_ratings are on the candidate, not the response
            safety_ratings = None
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                safety_ratings = getattr(candidate, "safety_ratings", None)
            confidence = self._safety_to_confidence(safety_ratings)

            # Token count from usage metadata
            if hasattr(response, "usage_metadata"):
                prompt_tokens = response.usage_metadata.prompt_token_count
                completion_tokens = response.usage_metadata.candidates_token_count
                token_count = response.usage_metadata.total_token_count
            else:
                prompt_tokens = 0
                completion_tokens = 0
                token_count = 0

            logger.info(
                f"Gemini generation completed",
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
                provider="gemini",
                model_version=self.model,
                citations_included=citations_included,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
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
            # Get file path from the file handle
            # request.pdf_file is a BinaryIO, but upload_file expects a path
            if hasattr(request.pdf_file, 'name'):
                pdf_path = request.pdf_file.name
            else:
                raise PDFParseError("PDF file handle does not have a path attribute")

            # Read PDF bytes for validation
            pdf_bytes = request.pdf_file.read()

            if len(pdf_bytes) == 0:
                raise PDFParseError("PDF file is empty")

            # Upload PDF to Gemini using new API
            uploaded_file = await asyncio.to_thread(
                self.client.files.upload,
                file=pdf_path
            )

            # Configure generation
            generation_config = {
                "max_output_tokens": request.config.max_tokens,
                "temperature": request.config.temperature,
            }

            # Call Gemini API with PDF and extraction prompt using new API
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.models.generate_content,
                    model=self.model,
                    contents=[request.extraction_prompt, uploaded_file],
                    config=generation_config,
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
