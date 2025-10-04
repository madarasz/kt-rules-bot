"""ChatGPT LLM adapter using OpenAI API.

Implements LLMProvider interface for GPT models.
Based on specs/001-we-are-building/contracts/llm-adapter.md
"""

import asyncio
import time
from math import exp
from typing import BinaryIO
from uuid import uuid4

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

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
    TokenLimitError,
)
from src.lib.logging import get_logger

logger = get_logger(__name__)


class ChatGPTAdapter(LLMProvider):
    """OpenAI ChatGPT API integration."""

    def __init__(self, api_key: str, model: str = "gpt-4-turbo"):
        """Initialize ChatGPT adapter.

        Args:
            api_key: OpenAI API key
            model: GPT model identifier
        """
        super().__init__(api_key, model)

        if AsyncOpenAI is None:
            raise ImportError("openai package not installed. Run: pip install openai")

        self.client = AsyncOpenAI(api_key=api_key)

        # GPT-5 has limited parameter support and uses reasoning tokens
        self.supports_logprobs = model not in ["gpt-5"]
        self.uses_completion_tokens = model in ["gpt-5"]
        self.supports_temperature = model not in ["gpt-5"]  # GPT-5 only supports temperature=1

        logger.info(f"Initialized ChatGPT adapter with model {model}")

    async def generate(self, request: GenerationRequest) -> LLMResponse:
        """Generate answer using ChatGPT API.

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
            # Build API call parameters
            api_params = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": request.config.system_prompt},
                    {"role": "user", "content": full_prompt},
                ],
            }

            # GPT-5 uses max_completion_tokens (includes both reasoning and visible output tokens)
            # Other models use max_tokens
            if self.uses_completion_tokens:
                # GPT-5 needs higher token limit to account for reasoning tokens
                # Multiply by 3 to give enough room for both reasoning and visible output
                max_tokens = request.config.max_tokens * 3
                api_params["max_completion_tokens"] = max_tokens
                logger.info(
                    f"GPT-5: Using max_completion_tokens={max_tokens} "
                    f"(3x {request.config.max_tokens} to account for reasoning tokens)"
                )
            else:
                api_params["max_tokens"] = request.config.max_tokens

            # GPT-5 only supports temperature=1 (default)
            if self.supports_temperature:
                api_params["temperature"] = request.config.temperature

            # Only request logprobs if model supports it
            if self.supports_logprobs:
                api_params["logprobs"] = True
                api_params["top_logprobs"] = 5

            # Call OpenAI API with timeout
            response = await asyncio.wait_for(
                self.client.chat.completions.create(**api_params),
                timeout=request.config.timeout_seconds,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            # Extract answer text
            choice = response.choices[0]
            answer_text = choice.message.content

            # Debug logging for GPT-5 issues
            logger.debug(f"GPT-5 response - finish_reason: {choice.finish_reason}, content_length: {len(answer_text) if answer_text else 0}")

            # GPT-5 sometimes returns None or empty content - check for refusal or other issues
            if not answer_text:
                logger.warning(f"GPT-5 returned empty content. Finish reason: {choice.finish_reason}, Refusal: {getattr(choice.message, 'refusal', None)}")
                # Check if there's a refusal
                refusal = getattr(choice.message, 'refusal', None)
                if refusal:
                    raise ContentFilterError(f"GPT-5 refused to respond: {refusal}")
                elif choice.finish_reason == 'length':
                    raise TokenLimitError("GPT-5 output was truncated due to max_completion_tokens limit")
                else:
                    raise Exception(f"GPT-5 returned empty content with finish_reason: {choice.finish_reason}")

            # Check if citations are included
            citations_included = (
                request.config.include_citations
                and "According to" in answer_text
            )

            # Calculate confidence from logprobs (if available)
            if self.supports_logprobs:
                confidence = self._calculate_confidence(response.choices[0].logprobs)
            else:
                confidence = 0.8  # Default confidence for models without logprobs

            # Token count
            token_count = response.usage.total_tokens

            logger.info(
                f"ChatGPT generation completed",
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
                provider="chatgpt",
                model_version=self.model,
                citations_included=citations_included,
            )

        except asyncio.TimeoutError:
            logger.warning(
                f"ChatGPT API timeout after {request.config.timeout_seconds}s"
            )
            raise LLMTimeoutError(
                f"ChatGPT generation exceeded {request.config.timeout_seconds}s timeout"
            )

        except Exception as e:
            error_msg = str(e).lower()

            if "rate_limit" in error_msg or "429" in error_msg:
                logger.warning(f"ChatGPT rate limit exceeded: {e}")
                raise RateLimitError(f"ChatGPT rate limit: {e}")

            if "authentication" in error_msg or "401" in error_msg:
                logger.error(f"ChatGPT authentication failed: {e}")
                raise AuthenticationError(f"ChatGPT auth error: {e}")

            if (
                "content_policy" in error_msg
                or "content_filter" in error_msg
                or "unsafe" in error_msg
            ):
                logger.warning(f"ChatGPT content filtered: {e}")
                raise ContentFilterError(f"ChatGPT content filter: {e}")

            logger.error(f"ChatGPT generation error: {e}")
            raise

    async def extract_pdf(self, request: ExtractionRequest) -> ExtractionResponse:
        """Extract markdown from PDF using ChatGPT vision.

        Note: GPT-4 Turbo with vision can process images, but not PDFs directly.
        This method would require converting PDF pages to images first.

        Args:
            request: Extraction request with PDF file

        Returns:
            ExtractionResponse with markdown content

        Raises:
            PDFParseError: PDF parsing failed
            LLMTimeoutError: Extraction timeout
            TokenLimitError: PDF too large
        """
        start_time = time.time()

        try:
            # Read PDF bytes
            pdf_bytes = request.pdf_file.read()

            if len(pdf_bytes) == 0:
                raise PDFParseError("PDF file is empty")

            # GPT-4 Vision requires images, not PDFs
            # In production, you'd convert PDF to images here
            # For now, we'll use a text-based extraction approach
            logger.warning(
                "ChatGPT PDF extraction requires image conversion (not implemented)"
            )

            # Placeholder: In production, convert PDF pages to base64 images
            # and send to gpt-4-vision-preview
            raise NotImplementedError(
                "ChatGPT PDF extraction requires PDF-to-image conversion"
            )

        except asyncio.TimeoutError:
            logger.warning(f"ChatGPT PDF extraction timeout")
            raise LLMTimeoutError(
                f"ChatGPT extraction exceeded {request.config.timeout_seconds}s timeout"
            )

        except NotImplementedError:
            raise

        except Exception as e:
            error_msg = str(e).lower()

            if "token" in error_msg and "limit" in error_msg:
                logger.error(f"ChatGPT token limit exceeded: {e}")
                raise TokenLimitError(f"ChatGPT token limit: {e}")

            if "pdf" in error_msg or "parse" in error_msg:
                logger.error(f"ChatGPT PDF parse error: {e}")
                raise PDFParseError(f"ChatGPT PDF error: {e}")

            logger.error(f"ChatGPT extraction error: {e}")
            raise

    def _calculate_confidence(self, logprobs) -> float:
        """Calculate confidence from logprobs.

        Args:
            logprobs: Logprobs from OpenAI response

        Returns:
            Confidence score (0-1)
        """
        if not logprobs or not logprobs.content:
            return 0.7  # Default if logprobs unavailable

        # Average top token probabilities across response
        probs = []
        for token_logprob in logprobs.content:
            if token_logprob.logprob is not None:
                probs.append(exp(token_logprob.logprob))

        if not probs:
            return 0.7

        return sum(probs) / len(probs)

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
