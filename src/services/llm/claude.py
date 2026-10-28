"""Claude LLM adapter using Anthropic API.

Implements LLMProvider interface for Claude models.
Based on specs/001-we-are-building/contracts/llm-adapter.md
"""

import asyncio
import json
import time
from uuid import uuid4

from anthropic import Anthropic, AsyncAnthropic

from src.lib.constants import LLM_REASONING_TOKEN_MULTIPLIER
from src.lib.logging import get_logger
from src.lib.pdf_utils import decompress_pdf_with_cleanup
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
    get_schema_info,
)
from src.services.llm.base import TimeoutError as LLMTimeoutError

logger = get_logger(__name__)

# Lazy-loaded system prompt cache.  On first use we build both the stripped default
# (to detect when a caller has not overridden the system prompt) and the block list
# with cache_control markers that Anthropic uses for prompt caching.
_DEFAULT_STRIPPED: str | None = None
_DEFAULT_BLOCKS: list[dict] | None = None


def _init_system_cache() -> None:
    global _DEFAULT_STRIPPED, _DEFAULT_BLOCKS
    from src.services.llm.prompt_builder import build_claude_system_blocks, build_system_prompt

    stripped = build_system_prompt("default")
    blocks = build_claude_system_blocks("default")
    _DEFAULT_STRIPPED = stripped
    _DEFAULT_BLOCKS = blocks


def _get_system(system_prompt: str, use_cache: bool = True) -> str | list[dict]:
    """Return cache-control blocks for the default prompt; plain string otherwise."""
    if not use_cache:
        return system_prompt
    if _DEFAULT_STRIPPED is None:
        _init_system_cache()
    if system_prompt == _DEFAULT_STRIPPED:
        return _DEFAULT_BLOCKS  # type: ignore[return-value]
    return system_prompt


# Claude models that support structured outputs (beta.messages.parse)
# Models not in this list use tool use fallback
CLAUDE_MODELS_WITH_STRUCTURED_OUTPUTS = [
    "claude-sonnet-4-5-20250929",
    "claude-opus-4-1-20250805",
    # claude-haiku-4-5-20251001 not yet supported
]

# temperature/top_p/top_k removed on these models (returns 400 if sent)
CLAUDE_MODELS_WITHOUT_TEMPERATURE = {
    "claude-opus-4-7",
    "claude-opus-4-8",
    "claude-haiku-5-5",  # only temperature=1 / top_p=0.99 accepted
    "claude-sonnet-5-5",
}

# Forced tool_choice ("tool"/"any") returns 400 on these models, so they get JSON
# through structured outputs (output_config.format) instead of a forced tool call.
CLAUDE_MODELS_WITHOUT_FORCED_TOOL_CHOICE = {
    "claude-sonnet-5-5",
}

# Forced tool calls on these models get strict: true, so the tool input is decoded
# against the schema. Without it Haiku 5.5 sometimes dropped required fields
# (quote_text) or sent `quotes` as a malformed JSON string.
CLAUDE_MODELS_WITH_STRICT_TOOLS = {
    "claude-haiku-5-5",
}

# thinking.type "between_tools" = no extended thinking. Only these models accept
# it; they think by default and reject thinking.type "disabled".
CLAUDE_MODELS_WITH_BETWEEN_TOOLS = {
    "claude-sonnet-5-5",
}

# JSON Schema keywords output_config.format and strict tools reject (the SDK's
# parse() helpers strip them automatically; raw dict schemas must be stripped by hand).
_UNSUPPORTED_SCHEMA_KEYWORDS = frozenset({
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minLength", "maxLength", "minItems", "maxItems",
})


def _strip_unsupported_constraints(schema):
    """Return a copy of a JSON schema without keywords structured outputs rejects."""
    if isinstance(schema, list):
        return [_strip_unsupported_constraints(s) for s in schema]
    if not isinstance(schema, dict):
        return schema
    out = {}
    for key, value in schema.items():
        if key in _UNSUPPORTED_SCHEMA_KEYWORDS:
            continue
        if key == "properties":
            # Keys here are property names, not keywords — never strip them.
            out[key] = {name: _strip_unsupported_constraints(sub) for name, sub in value.items()}
        else:
            out[key] = _strip_unsupported_constraints(value)
    return out


def _extract_json_output(content) -> dict:
    """Return the structured JSON from a forced tool call or a structured-output text block.

    Blocks are read by type: thinking models can lead with thinking blocks.
    """
    for block in content:
        if getattr(block, "type", None) == "tool_use":
            return block.input
    for block in content:
        if getattr(block, "type", None) == "text":
            return json.loads(block.text)
    raise Exception("Expected tool_use or JSON text block but none returned")


def _effort_max_tokens(max_tokens: int) -> int:
    """Output budget to use when a reasoning effort is active.

    Anthropic bills thinking tokens against max_tokens, so leaving the default
    budget in place makes a high-effort request spend it all on reasoning and
    return a truncated (unparseable) answer.
    """
    return max_tokens * LLM_REASONING_TOKEN_MULTIPLIER

class ClaudeAdapter(LLMProvider):
    """Anthropic Claude API integration."""

    supports_batch = True

    def build_batch_request(self, request: GenerationRequest, custom_id: str) -> dict:
        """Build an Anthropic Messages Batch line for this request.

        Same JSON params as generate()'s fallback path (_json_request_params):
        a forced tool call, or output_config.format on models that reject one.
        cache_control blocks ride along.
        """
        if isinstance(request.prompt, list):
            full_prompt = request.prompt
        else:
            full_prompt = self._build_prompt(
                request.prompt, request.context, request.chunk_ids
            )
        system = _get_system(request.config.system_prompt, request.config.use_cache)
        info = get_schema_info(request.config.structured_output_schema)
        params: dict = {
            "model": self.model,
            "system": system,
            "messages": [{"role": "user", "content": full_prompt}],
            # Raw batch params are serialised straight to JSON, so output_config and
            # thinking go in directly here (unlike generate(), which needs extra_body).
            **self._json_request_params(info, request.config),
        }
        return {"custom_id": custom_id, "params": params}

    def _json_request_params(self, info, config) -> dict:
        """Wire-level request params that make this model return the schema's JSON.

        Returns JSON body keys. output_config and thinking are not named params in
        the pinned SDK (anthropic 0.74.1); generate() moves them into extra_body.
        """
        params: dict = {"max_tokens": config.max_tokens}
        output_config: dict = {}
        if self.model in CLAUDE_MODELS_WITHOUT_FORCED_TOOL_CHOICE:
            output_config["format"] = {
                "type": "json_schema",
                "schema": _strip_unsupported_constraints(info.json_schema),
            }
        else:
            tool: dict = {
                "name": info.tool_name,
                "description": info.tool_description,
                "input_schema": info.json_schema,
            }
            if self.model in CLAUDE_MODELS_WITH_STRICT_TOOLS:
                tool["strict"] = True
                tool["input_schema"] = _strip_unsupported_constraints(info.json_schema)
            params["tools"] = [tool]
            params["tool_choice"] = {"type": "tool", "name": info.tool_name}
        if self.model not in CLAUDE_MODELS_WITHOUT_TEMPERATURE:
            params["temperature"] = config.temperature
        effort = self._resolve_effort()
        if effort is not None:
            output_config["effort"] = effort
            params["max_tokens"] = _effort_max_tokens(config.max_tokens)
        elif self.model in CLAUDE_MODELS_WITH_BETWEEN_TOOLS:
            # No effort requested: keep thinking off, like the other Claude models
            params["thinking"] = {"type": "between_tools"}
        if output_config:
            params["output_config"] = output_config
        return params

    @classmethod
    def parse_batch_result(cls, raw: dict) -> LLMResponse:
        """Convert an Anthropic batch result item into an LLMResponse."""
        if raw.get("result_type") != "succeeded":
            raise RuntimeError(
                f"batch item {raw.get('custom_id')} {raw.get('result_type')}"
            )
        msg = raw["message"]
        structured = _extract_json_output(msg.content)
        answer_text = json.dumps(structured)
        u = msg.usage
        prompt_tokens = u.input_tokens
        completion_tokens = u.output_tokens
        return LLMResponse(
            response_id=uuid4(),
            answer_text=answer_text,
            confidence_score=0.8,
            token_count=prompt_tokens + completion_tokens,
            latency_ms=0,
            provider="claude",
            model_version=getattr(msg, "model", None) or "",
            citations_included=True,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
            cache_creation_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
            structured_output=structured,
        )

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5-20250929"):
        """Initialize Claude adapter.

        Args:
            api_key: Anthropic API key
            model: Claude model identifier
        """
        super().__init__(api_key, model)

        # Initialize client with PDF, Files API, and Structured Outputs beta headers
        self.client = AsyncAnthropic(
            api_key=api_key,
            default_headers={
                "anthropic-beta": "pdfs-2024-09-25,files-api-2025-04-14,structured-outputs-2025-11-13"
            },
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

        # list[dict] prompt = pre-built cache-control blocks; str = normal path via _build_prompt
        if isinstance(request.prompt, list):
            full_prompt = request.prompt
        else:
            full_prompt = self._build_prompt(request.prompt, request.context, request.chunk_ids)

        try:
            system = _get_system(request.config.system_prompt, request.config.use_cache)

            # Select schema based on configuration
            schema_type = request.config.structured_output_schema
            schema_info = get_schema_info(schema_type)
            pydantic_model = schema_info.pydantic_model
            logger.debug(f"Using {schema_type} schema (Pydantic)")

            # Check if model supports structured outputs
            supports_structured_outputs = self.model in CLAUDE_MODELS_WITH_STRUCTURED_OUTPUTS

            if supports_structured_outputs:
                # NEW API: Use Pydantic structured output with beta.messages.parse()
                logger.debug(f"Using structured outputs API for {self.model}")
                parse_kwargs = {
                    "model": self.model,
                    "max_tokens": request.config.max_tokens,
                    "system": system,
                    "messages": [{"role": "user", "content": full_prompt}],
                    "betas": ["structured-outputs-2025-11-13"],
                    "output_format": pydantic_model,
                }
                if self.model not in CLAUDE_MODELS_WITHOUT_TEMPERATURE:
                    parse_kwargs["temperature"] = request.config.temperature
                effort = self._resolve_effort()
                if effort is not None:
                    # output_config is not yet a named param in the pinned SDK
                    # (anthropic 0.74.1), so pass it through extra_body.
                    parse_kwargs["extra_body"] = {"output_config": {"effort": effort}}
                    parse_kwargs["max_tokens"] = _effort_max_tokens(request.config.max_tokens)
                response = await asyncio.wait_for(
                    self.client.beta.messages.parse(**parse_kwargs),
                    timeout=request.config.timeout_seconds,
                )

                # Extract structured output from parsed response
                parsed_output = response.parsed_output
                if not parsed_output:
                    # Try to get raw content for debugging
                    raw_content = None
                    if hasattr(response, "content") and response.content:
                        raw_content = str(response.content)
                    error_msg = "Expected parsed Pydantic output but none returned"
                    if raw_content:
                        error_msg += f"\n\nRAW RESPONSE:\n{raw_content}"
                    raise Exception(error_msg)

                answer_text = parsed_output.model_dump_json()
                logger.debug(
                    f"Extracted structured JSON from Claude (Pydantic): {len(answer_text)} chars"
                )

            else:
                # FALLBACK: forced tool call, or output_config.format on models that
                # reject forced tool use (see _json_request_params)
                logger.debug(f"Using JSON fallback (tool use / output_config) for {self.model}")
                params = self._json_request_params(schema_info, request.config)
                extra_body = {k: params.pop(k) for k in ("output_config", "thinking") if k in params}
                create_kwargs = {
                    "model": self.model,
                    "system": system,
                    "messages": [{"role": "user", "content": full_prompt}],
                    **params,
                }
                if extra_body:
                    create_kwargs["extra_body"] = extra_body
                response = await asyncio.wait_for(
                    self.client.messages.create(**create_kwargs),
                    timeout=request.config.timeout_seconds,
                )

                try:
                    tool_input = _extract_json_output(response.content)
                except json.JSONDecodeError as e:
                    raise Exception(
                        f"Claude returned invalid JSON (stop_reason: {response.stop_reason}): {e}"
                    ) from e
                answer_text = json.dumps(tool_input)
                logger.debug(
                    f"Extracted structured JSON from Claude: {len(answer_text)} chars"
                )

            latency_ms = int((time.time() - start_time) * 1000)

            # Validate it's not empty
            if not answer_text or not answer_text.strip():
                raise Exception("Claude returned empty JSON")

            # Check if citations are included (always true for structured output with quotes)
            citations_included = request.config.include_citations

            # Claude doesn't provide logprobs, use default confidence
            confidence = 0.8

            # Token count
            prompt_tokens = response.usage.input_tokens
            completion_tokens = response.usage.output_tokens
            token_count = prompt_tokens + completion_tokens
            cache_read_tokens = getattr(response.usage, "cache_read_input_tokens", 0) or 0
            cache_creation_tokens = getattr(response.usage, "cache_creation_input_tokens", 0) or 0

            # Get structured output as dict (same structure for both API paths)
            if supports_structured_outputs:
                structured_output_dict = parsed_output.model_dump()
            else:
                structured_output_dict = tool_input

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
                cache_read_tokens=cache_read_tokens,
                cache_creation_tokens=cache_creation_tokens,
                structured_output=structured_output_dict,
            )

        except TimeoutError as e:
            logger.warning(f"Claude API timeout after {request.config.timeout_seconds}s")
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
                    default_headers=self.client._custom_headers,  # Preserve beta headers
                )

                uploaded_file = None
                try:
                    with open(decompressed_pdf_path, "rb") as f:
                        uploaded_file = await asyncio.to_thread(
                            sync_client.beta.files.upload, file=f
                        )

                    logger.info(f"Uploaded PDF to Files API: {uploaded_file.id}")

                    # Use uploaded file in message
                    pdf_kwargs = {
                        "model": self.model,
                        "max_tokens": request.config.max_tokens,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "document",
                                        "source": {"type": "file", "file_id": uploaded_file.id},
                                    },
                                    {"type": "text", "text": request.extraction_prompt},
                                ],
                            }
                        ],
                    }
                    if self.model not in CLAUDE_MODELS_WITHOUT_TEMPERATURE:
                        pdf_kwargs["temperature"] = request.config.temperature
                    response = await asyncio.wait_for(
                        self.client.messages.create(**pdf_kwargs),
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

            # Read by type: adaptive-thinking models (e.g. Haiku 5.5) lead with thinking blocks
            markdown_content = next(b.text for b in response.content if b.type == "text")
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
