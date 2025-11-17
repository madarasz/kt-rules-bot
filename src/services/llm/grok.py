"""Grok LLM adapter using X API.

Implements LLMProvider interface for Grok models.
Based on specs/001-we-are-building/contracts/llm-adapter.md
"""

import json
import time
from uuid import uuid4

import httpx

from src.lib.logging import get_logger
from src.services.llm.base import (
    HOP_EVALUATION_SCHEMA,
    STRUCTURED_OUTPUT_SCHEMA,
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
from src.services.llm.base import (
    TimeoutError as LLMTimeoutError,
)

logger = get_logger(__name__)


class GrokAdapter(LLMProvider):
    """X/Twitter Grok API integration."""

    def __init__(self, api_key: str, model: str = "grok-3"):
        """Initialize Grok adapter.

        Args:
            api_key: X API key
            model: Grok model identifier
        """
        super().__init__(api_key, model)

        if httpx is None:
            raise ImportError("httpx package not installed. Run: pip install httpx")

        self.base_url = "https://api.x.ai/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        logger.info(f"Initialized Grok adapter with model {model}")

    async def generate(self, request: GenerationRequest) -> LLMResponse:
        """Generate answer using Grok API.

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

            # Build API request payload with structured output (Grok supports OpenAI-compatible function calling)
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": request.config.system_prompt},
                    {"role": "user", "content": full_prompt},
                ],
                "max_tokens": request.config.max_tokens,
                "temperature": request.config.temperature,
                "stream": False,
                "tools": [{
                    "type": "function",
                    "function": {
                        "name": function_name,
                        "description": function_description,
                        "parameters": schema,
                    }
                }],
                "tool_choice": {
                    "type": "function",
                    "function": {"name": function_name}
                },
            }

            # Call Grok API with timeout
            async with httpx.AsyncClient(timeout=request.config.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=payload,
                )

            latency_ms = int((time.time() - start_time) * 1000)

            # Handle HTTP errors
            if response.status_code == 429:
                logger.warning(f"Grok rate limit exceeded: {response.text}")
                raise RateLimitError(f"Grok rate limit: {response.text}")
            elif response.status_code == 401:
                logger.error(f"Grok authentication failed: {response.text}")
                raise AuthenticationError(f"Grok auth error: {response.text}")
            elif response.status_code >= 400:
                logger.error(f"Grok API error {response.status_code}: {response.text}")
                raise Exception(f"Grok API error {response.status_code}: {response.text}")

            # Parse response
            response_data = response.json()

            # Extract structured JSON from tool calls
            if not response_data.get("choices") or len(response_data["choices"]) == 0:
                raise Exception("Grok returned no choices in response")

            choice = response_data["choices"][0]
            message = choice.get("message", {})

            # Check for tool calls (structured output)
            tool_calls = message.get("tool_calls")
            if not tool_calls or len(tool_calls) == 0:
                # Check finish_reason for errors
                finish_reason = choice.get("finish_reason")
                logger.warning(f"Grok returned no tool calls. Finish reason: {finish_reason}")

                if finish_reason == "content_filter":
                    raise ContentFilterError("Grok content filter blocked response")
                elif finish_reason == "length":
                    raise TokenLimitError("Grok output was truncated due to max_tokens limit")
                else:
                    raise Exception(f"Expected structured output via tool calls but none returned (finish_reason: {finish_reason})")

            # Extract JSON from tool call
            tool_call = tool_calls[0]
            function_args = tool_call.get("function", {}).get("arguments", "")

            if not function_args:
                raise Exception("Grok tool call has empty arguments")

            # Parse and validate JSON
            try:
                json.loads(function_args)  # Validate JSON is parseable
                answer_text = function_args  # JSON string
                logger.debug(f"Extracted structured JSON from Grok tool call: {len(answer_text)} chars")
            except json.JSONDecodeError as e:
                logger.error(f"Grok returned invalid JSON in tool call: {e}")
                raise ValueError(f"Grok returned invalid JSON: {e}") from e

            # Check if citations are included (always true for structured output with quotes)
            citations_included = request.config.include_citations

            # Default confidence (Grok doesn't provide logprobs yet)
            confidence = 0.8

            # Token count
            usage = response_data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            token_count = usage.get("total_tokens", 0)

            logger.info(
                "Grok generation completed",
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
                provider="grok",
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
                    f"Grok API timeout after {request.config.timeout_seconds}s"
                )
                raise LLMTimeoutError(
                    f"Grok generation exceeded {request.config.timeout_seconds}s timeout"
                ) from e

            if "rate_limit" in error_msg or "429" in error_msg:
                logger.warning(f"Grok rate limit exceeded: {e}")
                raise RateLimitError(f"Grok rate limit: {e}") from e

            if "authentication" in error_msg or "401" in error_msg:
                logger.error(f"Grok authentication failed: {e}")
                raise AuthenticationError(f"Grok auth error: {e}") from e

            if (
                "content_policy" in error_msg
                or "content_filter" in error_msg
                or "unsafe" in error_msg
            ):
                logger.warning(f"Grok content filtered: {e}")
                raise ContentFilterError(f"Grok content filter: {e}") from e

            logger.error(f"Grok generation error: {e}")
            raise

    async def extract_pdf(self, request: ExtractionRequest) -> ExtractionResponse:
        """Extract markdown from PDF using Grok.

        Note: Grok currently doesn't support direct PDF processing.
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

            # Grok doesn't currently support direct PDF processing
            # In production, you'd convert PDF to text/images first
            logger.warning(
                "Grok PDF extraction requires text conversion (not implemented)"
            )

            # Placeholder: In production, convert PDF to text and send to Grok
            raise NotImplementedError(
                "Grok PDF extraction requires PDF-to-text conversion"
            )

        except TimeoutError as e:
            logger.warning("Grok PDF extraction timeout")
            raise LLMTimeoutError(
                f"Grok extraction exceeded {request.config.timeout_seconds}s timeout"
            ) from e

        except NotImplementedError:
            raise

        except Exception as e:
            error_msg = str(e).lower()

            if "token" in error_msg and "limit" in error_msg:
                logger.error(f"Grok token limit exceeded: {e}")
                raise TokenLimitError(f"Grok token limit: {e}") from e

            if "pdf" in error_msg or "parse" in error_msg:
                logger.error(f"Grok PDF parse error: {e}")
                raise PDFParseError(f"Grok PDF error: {e}") from e

            logger.error(f"Grok extraction error: {e}")
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
