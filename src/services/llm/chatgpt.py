"""ChatGPT LLM adapter using OpenAI API.

Implements LLMProvider interface for GPT models.
Based on specs/001-we-are-building/contracts/llm-adapter.md
"""

import asyncio
import time
from math import exp
from uuid import uuid4

from openai import AsyncOpenAI
from openai.lib._pydantic import to_strict_json_schema

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
    get_pydantic_model,
)
from src.services.llm.base import TimeoutError as LLMTimeoutError

logger = get_logger(__name__)


class ChatGPTAdapter(LLMProvider):
    """OpenAI ChatGPT API integration."""

    supports_batch = True

    def build_batch_request(self, request: GenerationRequest, custom_id: str) -> dict:
        """Build an OpenAI /v1/batches JSONL line for this request.

        Emits a response_format json_schema body replicating what
        beta.chat.completions.parse builds under the hood (strict=True keeps the
        same validation), since the batch endpoint has no .parse helper.
        """
        full_prompt = self._build_prompt(request.prompt, request.context, request.chunk_ids)
        model_cls = get_pydantic_model(request.config.structured_output_schema)
        body: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.config.system_prompt},
                {"role": "user", "content": full_prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": model_cls.__name__,
                    "schema": to_strict_json_schema(model_cls),
                    "strict": True,
                },
            },
        }
        if self.uses_completion_tokens:
            body["max_completion_tokens"] = request.config.max_tokens * 3
        else:
            body["max_tokens"] = request.config.max_tokens
        if self.supports_temperature:
            body["temperature"] = request.config.temperature
        return {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": body,
        }

    @classmethod
    def parse_batch_result(cls, raw: dict) -> LLMResponse:
        """Convert an OpenAI batch output line into an LLMResponse."""
        import json as _json

        body = raw.get("body")
        if raw.get("status_code") not in (200, None) or body is None:
            raise RuntimeError(
                f"batch item {raw.get('custom_id')} status {raw.get('status_code')} "
                f"(no response body)"
            )
        content = body["choices"][0]["message"]["content"]
        usage = body.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
        return LLMResponse(
            response_id=uuid4(),
            answer_text=content,
            confidence_score=0.8,
            token_count=usage.get("total_tokens", prompt_tokens + completion_tokens),
            latency_ms=0,
            provider="chatgpt",
            model_version=body.get("model", ""),
            citations_included=True,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_read_tokens=cached,
            cache_creation_tokens=0,
            structured_output=_json.loads(content),
        )

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
        reasoning_models = [
            "gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano",
            "gpt-5.3-chat-latest",
            "gpt-5.2", "gpt-5.2-chat-latest",
            "gpt-5.1-chat-latest", "gpt-5.1", "gpt-5", "gpt-5-mini", "gpt-5-nano",
            "o3", "o3-mini", "o4-mini"
        ]
        self.supports_logprobs = model not in reasoning_models
        self.uses_completion_tokens = model in reasoning_models
        self.supports_temperature = (
            model not in reasoning_models
        )  # Reasoning models only support temperature=1

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

        # Build prompt with context and optional chunk IDs
        full_prompt = self._build_prompt(request.prompt, request.context, request.chunk_ids)

        try:
            # Select Pydantic model based on configuration
            schema_type = request.config.structured_output_schema
            pydantic_model = get_pydantic_model(schema_type)
            logger.debug(f"Using {schema_type} schema (Pydantic)")

            # Build API call parameters for parse method
            api_params = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": request.config.system_prompt},
                    {"role": "user", "content": full_prompt},
                ],
                "response_format": pydantic_model,
            }

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

            # Call OpenAI API with timeout using parse method for Pydantic structured outputs
            response = await asyncio.wait_for(
                self.client.beta.chat.completions.parse(**api_params),
                timeout=request.config.timeout_seconds,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            # Extract answer text from parsed Pydantic output
            choice = response.choices[0]

            # Access the parsed Pydantic model
            parsed_output = choice.message.parsed
            if not parsed_output:
                # Try to get raw content for debugging
                raw_content = getattr(choice.message, "content", None)
                error_msg = "Expected parsed Pydantic output but none returned"
                if raw_content:
                    error_msg += f"\n\nRAW RESPONSE:\n{raw_content}"
                raise Exception(error_msg)

            answer_text = parsed_output.model_dump_json()
            logger.debug(
                f"Extracted structured JSON output (Pydantic): {len(answer_text)} chars"
            )

            # Validate it's not empty
            if not answer_text or not answer_text.strip():
                raise Exception("GPT returned empty JSON in parsed output")

            # Check if citations are included (only for default schema)
            citations_included = (
                request.config.include_citations if schema_type == "default" else False
            )

            # Note: Logprobs are not available with structured output (function calling)
            confidence = 0.8  # Default confidence

            # Token count
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
            token_count = response.usage.total_tokens
            prompt_details = getattr(response.usage, "prompt_tokens_details", None)
            cache_read_tokens = 0
            if prompt_details is not None:
                cache_read_tokens = getattr(prompt_details, "cached_tokens", 0) or 0

            logger.info(
                "ChatGPT generation completed",
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
                provider="chatgpt",
                model_version=self.model,
                citations_included=citations_included,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cache_read_tokens=cache_read_tokens,
                cache_creation_tokens=0,
                structured_output=parsed_output.model_dump(),  # Add parsed Pydantic model as dict
            )

        except TimeoutError as e:
            logger.warning(f"ChatGPT API timeout after {request.config.timeout_seconds}s")
            raise LLMTimeoutError(
                f"ChatGPT generation exceeded {request.config.timeout_seconds}s timeout"
            ) from e

        except Exception as e:
            error_msg = str(e).lower()

            if "rate_limit" in error_msg or "429" in error_msg:
                logger.warning(f"ChatGPT rate limit exceeded: {e}")
                raise RateLimitError(f"ChatGPT rate limit: {e}") from e

            if "authentication" in error_msg or "401" in error_msg:
                logger.error(f"ChatGPT authentication failed: {e}")
                raise AuthenticationError(f"ChatGPT auth error: {e}") from e

            if (
                "content_policy" in error_msg
                or "content_filter" in error_msg
                or "unsafe" in error_msg
            ):
                logger.warning(f"ChatGPT content filtered: {e}")
                raise ContentFilterError(f"ChatGPT content filter: {e}") from e

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
        time.time()

        try:
            # Read PDF bytes
            pdf_bytes = request.pdf_file.read()

            if len(pdf_bytes) == 0:
                raise PDFParseError("PDF file is empty")

            # GPT-4 Vision requires images, not PDFs
            # In production, you'd convert PDF to images here
            # For now, we'll use a text-based extraction approach
            logger.warning("ChatGPT PDF extraction requires image conversion (not implemented)")

            # Placeholder: In production, convert PDF pages to base64 images
            # and send to gpt-4-vision-preview
            raise NotImplementedError("ChatGPT PDF extraction requires PDF-to-image conversion")

        except TimeoutError as e:
            logger.warning("ChatGPT PDF extraction timeout")
            raise LLMTimeoutError(
                f"ChatGPT extraction exceeded {request.config.timeout_seconds}s timeout"
            ) from e

        except NotImplementedError:
            raise

        except Exception as e:
            error_msg = str(e).lower()

            if "token" in error_msg and "limit" in error_msg:
                logger.error(f"ChatGPT token limit exceeded: {e}")
                raise TokenLimitError(f"ChatGPT token limit: {e}") from e

            if "pdf" in error_msg or "parse" in error_msg:
                logger.error(f"ChatGPT PDF parse error: {e}")
                raise PDFParseError(f"ChatGPT PDF error: {e}") from e

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
