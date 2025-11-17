"""Claude LLM adapter using Anthropic API.

Implements LLMProvider interface for Claude models.
Based on specs/001-we-are-building/contracts/llm-adapter.md
"""

import asyncio
import json
import time
from uuid import uuid4

from anthropic import Anthropic, AsyncAnthropic

from src.lib.logging import get_logger
from src.lib.pdf_utils import decompress_pdf_with_cleanup
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
)
from src.services.llm.base import (
    TimeoutError as LLMTimeoutError,
)

logger = get_logger(__name__)


class ClaudeAdapter(LLMProvider):
    """Anthropic Claude API integration."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5-20250929"):
        """Initialize Claude adapter.

        Args:
            api_key: Anthropic API key
            model: Claude model identifier
        """
        super().__init__(api_key, model)

        # Initialize client with PDF and Files API beta headers
        self.client = AsyncAnthropic(
            api_key=api_key,
            default_headers={"anthropic-beta": "pdfs-2024-09-25,files-api-2025-04-14"}
        )
        logger.info(f"Initialized Claude adapter with model {model}")

    async def generate(self, request: GenerationRequest) -> LLMResponse:
        """Generate answer using Claude API.

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
                tool_name = "evaluate_context_sufficiency"
                tool_description = "Evaluate if retrieved context is sufficient to answer the question"
                logger.debug("Using hop evaluation schema")
            else:  # "default"
                schema = STRUCTURED_OUTPUT_SCHEMA
                tool_name = "format_kill_team_answer"
                tool_description = "Format Kill Team rules answer with quotes and explanation"
                logger.debug("Using default answer schema")

            # Use tool use for structured JSON output
            response = await asyncio.wait_for(
                self.client.messages.create(
                    model=self.model,
                    max_tokens=request.config.max_tokens,
                    temperature=request.config.temperature,
                    system=request.config.system_prompt,
                    messages=[{"role": "user", "content": full_prompt}],
                    tools=[{
                        "name": tool_name,
                        "description": tool_description,
                        "input_schema": schema
                    }],
                    tool_choice={
                        "type": "tool",
                        "name": tool_name
                    }
                ),
                timeout=request.config.timeout_seconds,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            # Extract JSON from tool use
            # Claude returns tool_use block in content
            tool_use_block = None
            for block in response.content:
                if hasattr(block, 'type') and block.type == 'tool_use':
                    tool_use_block = block
                    break

            if not tool_use_block:
                raise Exception("Expected tool_use block but none returned")

            # tool_use_block.input is a dict with structured data
            tool_input = tool_use_block.input
            answer_text = json.dumps(tool_input)  # Convert to JSON string
            logger.debug(f"Extracted structured JSON from Claude tool use: {len(answer_text)} chars")

            # Validate it's not empty
            if not answer_text or not answer_text.strip():
                raise Exception("Claude returned empty JSON in tool use")

            # Check if citations are included (always true for structured output with quotes)
            citations_included = request.config.include_citations

            # Claude doesn't provide logprobs, use default confidence
            confidence = 0.8

            # Token count
            prompt_tokens = response.usage.input_tokens
            completion_tokens = response.usage.output_tokens
            token_count = prompt_tokens + completion_tokens

            logger.info(
                "Claude generation completed",
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
                provider="claude",
                model_version=self.model,
                citations_included=citations_included,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        except TimeoutError as e:
            logger.warning(
                f"Claude API timeout after {request.config.timeout_seconds}s"
            )
            raise LLMTimeoutError(
                f"Claude generation exceeded {request.config.timeout_seconds}s timeout"
            ) from e

        except Exception as e:
            error_msg = str(e).lower()

            if "rate_limit" in error_msg or "429" in error_msg:
                logger.warning(f"Claude rate limit exceeded: {e}")
                raise RateLimitError(f"Claude rate limit: {e}") from e

            if "authentication" in error_msg or "401" in error_msg:
                logger.error(f"Claude authentication failed: {e}")
                raise AuthenticationError(f"Claude auth error: {e}") from e

            if "content_filter" in error_msg or "blocked" in error_msg:
                logger.warning(f"Claude content filtered: {e}")
                raise ContentFilterError(f"Claude content filter: {e}") from e

            logger.error(f"Claude generation error: {e}")
            raise

    async def extract_pdf(self, request: ExtractionRequest) -> ExtractionResponse:
        """Extract markdown from PDF using Claude Files API.

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

            pdf_size_mb = len(pdf_bytes) / (1024 * 1024)
            logger.info(f"Extracting PDF ({pdf_size_mb:.1f} MB) using Claude Files API")

            # Upload PDF using Files API (better for large documents)
            # Use context manager for automatic cleanup of temporary files
            with decompress_pdf_with_cleanup(pdf_bytes) as (_, decompressed_pdf_path):
                # Upload file using Files API (in beta namespace)
                # Note: Need to use synchronous client for file upload
                sync_client = Anthropic(
                    api_key=self.client.api_key,
                    default_headers=self.client._custom_headers  # Preserve beta headers
                )

                uploaded_file = None
                try:
                    with open(decompressed_pdf_path, 'rb') as f:
                        uploaded_file = await asyncio.to_thread(
                            sync_client.beta.files.upload,
                            file=f
                        )

                    logger.info(f"Uploaded PDF to Files API: {uploaded_file.id}")

                    # Use uploaded file in message
                    response = await asyncio.wait_for(
                        self.client.messages.create(
                            model=self.model,
                            max_tokens=request.config.max_tokens,
                            temperature=request.config.temperature,
                            messages=[
                                {
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "document",
                                            "source": {
                                                "type": "file",
                                                "file_id": uploaded_file.id,
                                            },
                                        },
                                        {"type": "text", "text": request.extraction_prompt},
                                    ],
                                }
                            ],
                        ),
                        timeout=request.config.timeout_seconds,
                    )

                finally:
                    # Clean up uploaded file
                    if uploaded_file:
                        try:
                            await asyncio.to_thread(sync_client.beta.files.delete, uploaded_file.id)
                            logger.info(f"Deleted uploaded file: {uploaded_file.id}")
                        except Exception as e:
                            logger.warning(f"Failed to delete uploaded file: {e}")

            latency_ms = int((time.time() - start_time) * 1000)

            markdown_content = response.content[0].text
            prompt_tokens = response.usage.input_tokens
            completion_tokens = response.usage.output_tokens
            token_count = prompt_tokens + completion_tokens

            # Validate extracted markdown
            validation_warnings = self._validate_extraction(markdown_content)

            logger.info(
                "Claude PDF extraction completed",
                extra={
                    "latency_ms": latency_ms,
                    "token_count": token_count,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "warnings": len(validation_warnings),
                },
            )

            return ExtractionResponse(
                extraction_id=uuid4(),
                markdown_content=markdown_content,
                token_count=token_count,
                latency_ms=latency_ms,
                provider="claude",
                model_version=self.model,
                validation_warnings=validation_warnings,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        except TimeoutError as e:
            logger.warning("Claude PDF extraction timeout")
            raise LLMTimeoutError(
                f"Claude extraction exceeded {request.config.timeout_seconds}s timeout"
            ) from e

        except Exception as e:
            error_msg = str(e).lower()

            if "pdf" in error_msg or "parse" in error_msg:
                logger.error(f"Claude PDF parse error: {e}")
                raise PDFParseError(f"Claude PDF error: {e}") from e

            logger.error(f"Claude extraction error: {e}")
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
            if f"{field}:" not in markdown[:500]:  # Check first 500 chars
                warnings.append(f"Missing required field: {field}")

        # Check for markdown headings
        if "##" not in markdown:
            warnings.append("No markdown headings found")

        return warnings
