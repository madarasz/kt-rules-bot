"""LLM retry logic for handling transient failures.

Automatically retries LLM requests when they fail due to:
- Content filtering (e.g., Gemini RECITATION errors)
- Rate limiting (with exponential backoff)
while respecting overall timeout limits.
"""

import asyncio
from collections.abc import Callable
from typing import Any

from src.lib.constants import (
    LLM_GENERATION_TIMEOUT,
    LLM_MAX_RETRIES,
    QUALITY_TEST_MAX_RETRIES_ON_RATE_LIMIT,
    QUALITY_TEST_RATE_LIMIT_INITIAL_DELAY,
)
from src.lib.logging import get_logger
from src.services.llm.base import ContentFilterError, RateLimitError
from src.services.llm.base import TimeoutError as LLMTimeoutError

logger = get_logger(__name__)


async def retry_on_content_filter(
    async_func: Callable, *args, timeout_seconds: int = LLM_GENERATION_TIMEOUT, **kwargs
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
        ...     timeout_seconds=LLM_GENERATION_TIMEOUT
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
    except TimeoutError as e:
        logger.error(f"LLM request timed out after {timeout_seconds}s (including retries)")
        # Convert asyncio.TimeoutError to LLMTimeoutError for better error handling
        raise LLMTimeoutError(
            f"LLM request timed out after {timeout_seconds}s (including retries)"
        ) from e


async def retry_with_rate_limit_backoff(
    async_func: Callable,
    *args,
    max_retries: int = QUALITY_TEST_MAX_RETRIES_ON_RATE_LIMIT,
    initial_delay: float = QUALITY_TEST_RATE_LIMIT_INITIAL_DELAY,
    timeout_seconds: int = LLM_GENERATION_TIMEOUT,
    **kwargs,
) -> Any:
    """Retry async LLM calls with exponential backoff on rate limit errors.

    Retries up to max_retries times when RateLimitError is raised, with
    exponential backoff (delay doubles after each retry). Also retries on
    ContentFilterError without delay.

    Args:
        async_func: Async function to call (e.g., llm_provider.generate)
        *args: Positional arguments to pass to async_func
        max_retries: Maximum retry attempts for rate limit errors
        initial_delay: Initial delay in seconds (doubles each retry)
        timeout_seconds: Total timeout for all retry attempts combined
        **kwargs: Keyword arguments to pass to async_func

    Returns:
        Result from async_func

    Raises:
        RateLimitError: If all retry attempts fail with RateLimitError
        ContentFilterError: If all retry attempts fail with ContentFilterError
        asyncio.TimeoutError: If total execution time exceeds timeout_seconds
        Other exceptions: Passed through immediately without retry

    Example:
        >>> llm_response = await retry_with_rate_limit_backoff(
        ...     llm_provider.generate,
        ...     GenerationRequest(prompt="...", context=[...]),
        ...     max_retries=3,
        ...     initial_delay=2.0,
        ...     timeout_seconds=LLM_GENERATION_TIMEOUT
        ... )
    """

    async def _retry_loop() -> Any:
        """Inner retry loop with exponential backoff."""
        last_error = None
        delay = initial_delay
        rate_limit_attempts = 0
        content_filter_attempts = 0

        # We allow content filter retries + rate limit retries
        total_attempts = LLM_MAX_RETRIES + max_retries + 1

        for attempt in range(total_attempts):
            try:
                if attempt > 0:
                    error_type = (
                        "RateLimitError" if rate_limit_attempts > 0 else "ContentFilterError"
                    )
                    logger.info(
                        f"Retrying LLM request after {error_type} "
                        f"(attempt {attempt + 1}/{total_attempts})..."
                    )

                result = await async_func(*args, **kwargs)

                if attempt > 0:
                    logger.info(f"LLM request succeeded on attempt {attempt + 1}")

                return result

            except RateLimitError as e:
                last_error = e
                rate_limit_attempts += 1

                logger.warning(f"LLM RateLimitError on attempt {attempt + 1}: {e}")

                # If we've exhausted rate limit retries, re-raise
                if rate_limit_attempts > max_retries:
                    logger.error(
                        f"LLM request failed with RateLimitError after "
                        f"{rate_limit_attempts} rate limit retries"
                    )
                    raise

                # Exponential backoff
                logger.info(f"Waiting {delay:.1f}s before retry...")
                await asyncio.sleep(delay)
                delay *= 2  # Double the delay for next time
                continue

            except ContentFilterError as e:
                last_error = e
                content_filter_attempts += 1

                logger.warning(f"LLM ContentFilterError on attempt {attempt + 1}: {e}")

                # If we've exhausted content filter retries, re-raise
                if content_filter_attempts > LLM_MAX_RETRIES:
                    logger.error(
                        f"LLM request failed with ContentFilterError after "
                        f"{content_filter_attempts} attempts"
                    )
                    raise

                # No delay for content filter errors, just retry
                continue

            except Exception as e:
                # Non-retryable error - fail immediately
                logger.debug(
                    f"LLM request failed with non-retryable error: {type(e).__name__}: {e}"
                )
                raise

        # Should never reach here
        if last_error:
            raise last_error
        raise RuntimeError("Retry loop completed without result or error")

    # Wrap retry loop with overall timeout
    try:
        return await asyncio.wait_for(_retry_loop(), timeout=timeout_seconds)
    except TimeoutError as e:
        logger.error(f"LLM request timed out after {timeout_seconds}s (including retries)")
        # Convert asyncio.TimeoutError to LLMTimeoutError for better error handling
        raise LLMTimeoutError(
            f"LLM request timed out after {timeout_seconds}s (including retries)"
        ) from e
