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
    STRUCTURED_OUTPUT_SCHEMA,
    HOP_EVALUATION_SCHEMA,
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

        # GPT-5 and O-series models have limited parameter support and use reasoning tokens
        reasoning_models = ["gpt-5", "gpt-5-mini", "o3", "o3-mini", "o4-mini"]
        self.supports_logprobs = model not in reasoning_models
        self.uses_completion_tokens = model in reasoning_models
        self.supports_temperature = model not in reasoning_models  # Reasoning models only support temperature=1

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

            # Select schema based on configuration
            schema_type = request.config.structured_output_schema

            if schema_type == "hop_evaluation":
                schema = HOP_EVALUATION_SCHEMA
                function_name = "evaluate_context_sufficiency"
                function_description = "Evaluate if retrieved context is sufficient to answer the question"
                logger.debug("Using hop evaluation schema")
            else:  # "default"
                schema = STRUCTURED_OUTPUT_SCHEMA
                function_name = "format_kill_team_answer"
                function_description = "Format Kill Team rules answer with quotes and explanation"
                logger.debug("Using default answer schema")

            # Use structured output with appropriate schema
            api_params["tools"] = [{
                "type": "function",
                "function": {
                    "name": function_name,
                    "description": function_description,
                    "parameters": schema,
                    "strict": True  # Enforces 100% schema compliance
                }
            }]
            api_params["tool_choice"] = {
                "type": "function",
                "function": {"name": function_name}
            }
            api_params["parallel_tool_calls"] = False  # Required for strict mode

            # GPT-5 uses max_completion_tokens (includes both reasoning and visible output tokens)
            # Other models use max_tokens
            if self.uses_completion_tokens:
                # GPT-5 needs higher token limit to account for reasoning tokens
                # Multiply by 3 to give enough room for both reasoning and visible output
                max_tokens = request.config.max_tokens * 3
                api_params["max_completion_tokens"] = max_tokens
                logger.info(
                    f"GPT-5 / o-series: Using max_completion_tokens={max_tokens} "
                    f"(3x {request.config.max_tokens} to account for reasoning tokens)"
                )
            else:
                api_params["max_tokens"] = request.config.max_tokens

            # GPT-5 only supports temperature=1 (default)
            if self.supports_temperature:
                api_params["temperature"] = request.config.temperature

            # Note: Logprobs not available with tool use (structured output)
            # Skipping logprobs since we always use structured output

            # Call OpenAI API with timeout
            response = await asyncio.wait_for(
                self.client.chat.completions.create(**api_params),
                timeout=request.config.timeout_seconds,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            # Extract answer text from structured output
            choice = response.choices[0]

            if not choice.message.tool_calls:
                raise Exception("Expected structured output via tool calls but none returned")

            tool_call = choice.message.tool_calls[0]
            answer_text = tool_call.function.arguments  # JSON string
            logger.debug(f"Extracted structured JSON output ({schema_type}): {len(answer_text)} chars")

            # Validate it's not empty
            if not answer_text or not answer_text.strip():
                raise Exception("GPT returned empty JSON in tool call")

            # Check if citations are included (only for default schema)
            citations_included = request.config.include_citations if schema_type == "default" else False

            # Note: Logprobs are not available with structured output (function calling)
            confidence = 0.8  # Default confidence

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
