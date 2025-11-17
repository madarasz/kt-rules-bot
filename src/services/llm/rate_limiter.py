"""Rate limiter for LLM API calls.

Implements token bucket algorithm for per-provider, per-user throttling.
Based on specs/001-we-are-building/tasks.md T046
"""

import time
from dataclasses import dataclass

from src.lib.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""

    max_requests: int = 10  # Maximum requests
    window_seconds: int = 60  # Time window (default: 10 requests per minute)
    burst_size: int = 15  # Allow bursts up to this size


class RateLimiter:
    """Token bucket rate limiter for LLM API calls.

    Implements per-provider and per-user rate limiting to prevent abuse
    and stay within API quotas.
    """

    def __init__(self, config: RateLimitConfig = None):
        """Initialize rate limiter.

        Args:
            config: Rate limit configuration (uses defaults if None)
        """
        self.config = config or RateLimitConfig()

        # Store buckets: {(provider, user_id): (tokens, last_update)}
        self._buckets: dict[tuple[str, str], tuple[float, float]] = {}

        logger.info(
            f"Initialized RateLimiter: "
            f"{self.config.max_requests} requests per {self.config.window_seconds}s"
        )

    def check_rate_limit(self, provider: str, user_id: str) -> tuple[bool, float]:
        """Check if request is allowed under rate limit.

        Args:
            provider: LLM provider name (claude/chatgpt/gemini)
            user_id: Hashed user ID

        Returns:
            Tuple of (is_allowed: bool, retry_after_seconds: float)
        """
        key = (provider, user_id)
        current_time = time.time()

        # Initialize bucket if not exists
        if key not in self._buckets:
            self._buckets[key] = (self.config.max_requests, current_time)

        tokens, last_update = self._buckets[key]

        # Refill tokens based on time elapsed
        time_elapsed = current_time - last_update
        refill_rate = self.config.max_requests / self.config.window_seconds
        tokens = min(
            self.config.burst_size,  # Cap at burst size
            tokens + (time_elapsed * refill_rate),
        )

        # Check if request is allowed
        if tokens >= 1.0:
            # Consume one token
            self._buckets[key] = (tokens - 1.0, current_time)
            logger.debug(
                f"Rate limit passed for {provider}:{user_id[:8]}... ({tokens:.1f} tokens remaining)"
            )
            return True, 0.0

        # Request denied - calculate retry after
        tokens_needed = 1.0 - tokens
        retry_after = tokens_needed / refill_rate

        logger.warning(
            f"Rate limit exceeded for {provider}:{user_id[:8]}... Retry after {retry_after:.1f}s"
        )

        # Update bucket with current state
        self._buckets[key] = (tokens, current_time)

        return False, retry_after

    def consume(self, provider: str, user_id: str) -> None:
        """Consume a token from the rate limit bucket.

        This is automatically called by check_rate_limit when allowed.
        Only call this manually if you need to pre-consume a token.

        Args:
            provider: LLM provider name
            user_id: Hashed user ID
        """
        key = (provider, user_id)
        current_time = time.time()

        if key in self._buckets:
            tokens, _ = self._buckets[key]
            self._buckets[key] = (max(0, tokens - 1.0), current_time)

    def reset(self, provider: str, user_id: str) -> None:
        """Reset rate limit for a specific provider and user.

        Useful for administrative overrides or testing.

        Args:
            provider: LLM provider name
            user_id: Hashed user ID
        """
        key = (provider, user_id)
        if key in self._buckets:
            del self._buckets[key]
            logger.info(f"Reset rate limit for {provider}:{user_id[:8]}...")

    def get_stats(self, provider: str, user_id: str) -> dict:
        """Get current rate limit stats for a user.

        Args:
            provider: LLM provider name
            user_id: Hashed user ID

        Returns:
            Dict with tokens_remaining, last_update, retry_after
        """
        key = (provider, user_id)

        if key not in self._buckets:
            return {
                "tokens_remaining": self.config.max_requests,
                "last_update": None,
                "retry_after": 0.0,
            }

        tokens, last_update = self._buckets[key]
        current_time = time.time()

        # Calculate current tokens with refill
        time_elapsed = current_time - last_update
        refill_rate = self.config.max_requests / self.config.window_seconds
        current_tokens = min(self.config.burst_size, tokens + (time_elapsed * refill_rate))

        # Calculate retry_after if at 0 tokens
        retry_after = 0.0
        if current_tokens < 1.0:
            tokens_needed = 1.0 - current_tokens
            retry_after = tokens_needed / refill_rate

        return {
            "tokens_remaining": current_tokens,
            "last_update": last_update,
            "retry_after": retry_after,
        }

    def cleanup_old_buckets(self, max_age_seconds: int = 3600) -> int:
        """Clean up buckets that haven't been used recently.

        Args:
            max_age_seconds: Remove buckets older than this (default: 1 hour)

        Returns:
            Number of buckets removed
        """
        current_time = time.time()
        old_keys = []

        for key, (_, last_update) in self._buckets.items():
            if current_time - last_update > max_age_seconds:
                old_keys.append(key)

        for key in old_keys:
            del self._buckets[key]

        if old_keys:
            logger.info(f"Cleaned up {len(old_keys)} old rate limit buckets")

        return len(old_keys)


# Global rate limiter instance
_rate_limiter = None


def get_rate_limiter(config: RateLimitConfig = None) -> RateLimiter:
    """Get global rate limiter instance.

    Args:
        config: Rate limit configuration (only used on first call)

    Returns:
        RateLimiter singleton instance
    """
    global _rate_limiter

    if _rate_limiter is None:
        _rate_limiter = RateLimiter(config)

    return _rate_limiter
