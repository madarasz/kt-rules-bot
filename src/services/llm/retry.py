"""LLM retry logic for handling transient ContentFilterError failures.

Automatically retries LLM requests when they fail due to content filtering
(e.g., Gemini RECITATION errors) while respecting overall timeout limits.
"""

import asyncio
from typing import Any, Callable

from src.services.llm.base import ContentFilterError
from src.lib.constants import LLM_MAX_RETRIES
from src.lib.logging import get_logger

logger = get_logger(__name__)


async def retry_on_content_filter(
    async_func: Callable,
    *args,
    timeout_seconds: int = 60,
    **kwargs
) -> Any:
    """Retry async LLM calls on ContentFilterError.

    Retries up to LLM_MAX_RETRIES times when ContentFilterError is raised.
    The timeout_seconds applies to the ENTIRE operation including all retries.

    Args:
        async_func: Async function to call (e.g., llm_provider.generate)
        *args: Positional arguments to pass to async_func
        timeout_seconds: Total timeout for all retry attempts combined
        **kwargs: Keyword arguments to pass to async_func

    Returns:
        Result from async_func

    Raises:
        ContentFilterError: If all retry attempts fail with ContentFilterError
        asyncio.TimeoutError: If total execution time exceeds timeout_seconds
        Other exceptions: Passed through immediately without retry

    Example:
        >>> llm_response = await retry_on_content_filter(
        ...     llm_provider.generate,
        ...     GenerationRequest(prompt="...", context=[...]),
        ...     timeout_seconds=60
        ... )
    """

    async def _retry_loop() -> Any:
        """Inner retry loop (without timeout wrapper)."""
        last_error = None

        for attempt in range(LLM_MAX_RETRIES + 1):  # +1 for initial attempt
            try:
                if attempt > 0:
                    logger.info(
                        f"Retrying LLM request (attempt {attempt + 1}/{LLM_MAX_RETRIES + 1})..."
                    )

                result = await async_func(*args, **kwargs)

                if attempt > 0:
                    logger.info(f"LLM request succeeded on attempt {attempt + 1}")

                return result

            except ContentFilterError as e:
                last_error = e
                logger.warning(
                    f"LLM ContentFilterError on attempt {attempt + 1}/{LLM_MAX_RETRIES + 1}: {e}"
                )

                # If this was the last attempt, re-raise
                if attempt >= LLM_MAX_RETRIES:
                    logger.error(
                        f"LLM request failed with ContentFilterError after {LLM_MAX_RETRIES + 1} attempts"
                    )
                    raise

                # Otherwise, continue to next retry
                continue

            except Exception as e:
                # Non-retryable error - fail immediately
                # This includes: AuthenticationError, RateLimitError, TimeoutError, etc.
                logger.debug(
                    f"LLM request failed with non-retryable error: {type(e).__name__}: {e}"
                )
                raise

        # Should never reach here (loop always returns or raises)
        # But if it does, raise the last error
        if last_error:
            raise last_error
        raise RuntimeError("Retry loop completed without result or error")

    # Wrap retry loop with overall timeout
    try:
        return await asyncio.wait_for(_retry_loop(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.error(
            f"LLM request timed out after {timeout_seconds}s (including retries)"
        )
        # Re-raise as asyncio.TimeoutError so caller can handle
        # Caller may convert to LLMTimeoutError if needed
        raise
