"""DeepSeek LLM adapter using OpenAI-compatible API.

Implements LLMProvider interface for DeepSeek models (deepseek-chat, deepseek-reasoner).
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
)
from src.lib.logging import get_logger
import json

logger = get_logger(__name__)


class DeepSeekAdapter(LLMProvider):
    """DeepSeek API integration using OpenAI-compatible endpoint."""

    DEEPSEEK_BASE_URL = "https://api.deepseek.com"

    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        """Initialize DeepSeek adapter.

        Args:
            api_key: DeepSeek API key
            model: DeepSeek model identifier (deepseek-chat or deepseek-reasoner)
        """
        super().__init__(api_key, model)

        if AsyncOpenAI is None:
            raise ImportError("openai package not installed. Run: pip install openai")

        # DeepSeek API is OpenAI-compatible, use custom base URL
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.DEEPSEEK_BASE_URL
        )

        # deepseek-reasoner uses chain-of-thought reasoning
        self.is_reasoning_model = model == "deepseek-reasoner"

        logger.info(f"Initialized DeepSeek adapter with model {model}")

    async def generate(self, request: GenerationRequest) -> LLMResponse:
        """Generate answer using DeepSeek API.

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
        token_limit = request.config.max_tokens * 3 if self.model == "deepseek-reasoner" else request.config.max_tokens

        try:
            # Build API call parameters with structured output (DeepSeek supports OpenAI-compatible function calling)
            api_params = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": request.config.system_prompt},
                    {"role": "user", "content": full_prompt},
                ],
                "max_tokens": token_limit,
                "temperature": request.config.temperature,
                "tools": [{
                    "type": "function",
                    "function": {
                        "name": "format_kill_team_answer",
                        "description": "Format Kill Team rules answer with quotes and explanation",
                        "parameters": STRUCTURED_OUTPUT_SCHEMA,
                    }
                }],
                "tool_choice": {
                    "type": "function",
                    "function": {"name": "format_kill_team_answer"}
                },
            }

            # Call DeepSeek API with timeout
            response = await asyncio.wait_for(
                self.client.chat.completions.create(**api_params),
                timeout=request.config.timeout_seconds,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            # Extract structured JSON from tool calls
            choice = response.choices[0]

            # For deepseek-reasoner, also extract reasoning content if available
            reasoning_content = None
            if self.is_reasoning_model and hasattr(choice.message, 'reasoning_content'):
                reasoning_content = choice.message.reasoning_content
                if reasoning_content:
                    logger.debug(f"DeepSeek reasoning chain-of-thought: {reasoning_content[:200]}...")

            # Check for tool calls (structured output)
            if not choice.message.tool_calls:
                logger.warning(f"DeepSeek returned no tool calls. Finish reason: {choice.finish_reason}")
                # Check if there's a refusal
                refusal = getattr(choice.message, 'refusal', None)
                if refusal:
                    raise ContentFilterError(f"DeepSeek refused to respond: {refusal}")
                elif choice.finish_reason == 'length':
                    raise TokenLimitError("DeepSeek output was truncated due to max_tokens limit")
                else:
                    raise Exception(f"Expected structured output via tool calls but none returned (finish_reason: {choice.finish_reason})")

            # Extract JSON from tool call
            tool_call = choice.message.tool_calls[0]
            function_args = tool_call.function.arguments

            if not function_args:
                raise Exception("DeepSeek tool call has empty arguments")

            # Parse and validate JSON
            try:
                json.loads(function_args)  # Validate JSON is parseable
                answer_text = function_args  # JSON string
                logger.debug(f"Extracted structured JSON from DeepSeek tool call: {len(answer_text)} chars")
            except json.JSONDecodeError as e:
                logger.error(f"DeepSeek returned invalid JSON in tool call: {e}")
                raise ValueError(f"DeepSeek returned invalid JSON: {e}")

            # Check if citations are included (always true for structured output with quotes)
            citations_included = request.config.include_citations

            # Calculate confidence (DeepSeek doesn't provide logprobs, use default)
            # Reasoning models get slightly higher confidence due to chain-of-thought
            confidence = 0.85 if self.is_reasoning_model else 0.8

            # Token count
            token_count = response.usage.total_tokens

            logger.info(
                f"DeepSeek generation completed",
                extra={
                    "latency_ms": latency_ms,
                    "token_count": token_count,
                    "confidence": confidence,
                    "has_reasoning": reasoning_content is not None,
                },
            )

            return LLMResponse(
                response_id=uuid4(),
                answer_text=answer_text,
                confidence_score=confidence,
                token_count=token_count,
                latency_ms=latency_ms,
                provider="deepseek",
                model_version=self.model,
                citations_included=citations_included,
            )

        except asyncio.TimeoutError:
            logger.warning(
                f"DeepSeek API timeout after {request.config.timeout_seconds}s"
            )
            raise LLMTimeoutError(
                f"DeepSeek generation exceeded {request.config.timeout_seconds}s timeout"
            )

        except Exception as e:
            error_msg = str(e).lower()

            if "rate_limit" in error_msg or "429" in error_msg:
                logger.warning(f"DeepSeek rate limit exceeded: {e}")
                raise RateLimitError(f"DeepSeek rate limit: {e}")

            if "authentication" in error_msg or "401" in error_msg:
                logger.error(f"DeepSeek authentication failed: {e}")
                raise AuthenticationError(f"DeepSeek auth error: {e}")

            if (
                "content_policy" in error_msg
                or "content_filter" in error_msg
                or "unsafe" in error_msg
            ):
                logger.warning(f"DeepSeek content filtered: {e}")
                raise ContentFilterError(f"DeepSeek content filter: {e}")

            logger.error(f"DeepSeek generation error: {e}")
            raise

    async def extract_pdf(self, request: ExtractionRequest) -> ExtractionResponse:
        """Extract markdown from PDF using DeepSeek.

        Note: DeepSeek API documentation does not currently specify PDF extraction
        capabilities. This method is not implemented.

        Args:
            request: Extraction request with PDF file

        Returns:
            ExtractionResponse with markdown content

        Raises:
            NotImplementedError: PDF extraction not supported
        """
        logger.warning("DeepSeek PDF extraction is not currently supported")
        raise NotImplementedError(
            "DeepSeek PDF extraction is not documented in the API. "
            "Use gemini-2.5-pro or gemini-2.5-flash for PDF extraction instead."
        )
