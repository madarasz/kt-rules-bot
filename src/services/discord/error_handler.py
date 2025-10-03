"""Centralized error handling for Discord bot."""

import discord
from discord.errors import HTTPException, Forbidden

from src.lib.logging import get_logger
from src.services.llm.base import RateLimitError

logger = get_logger(__name__)


async def handle_error(
    error: Exception,
    message: discord.Message,
    correlation_id: str,
) -> None:
    """Handle errors with appropriate user feedback.

    Args:
        error: Exception that occurred
        message: Discord message object
        correlation_id: Query correlation ID for logging
    """
    # Map error types to user-friendly messages
    if isinstance(error, RateLimitError):
        await message.channel.send(
            "⏰ The AI service is currently rate limited. "
            "Please try again in a few minutes."
        )
        logger.warning(
            "LLM rate limit hit",
            extra={"correlation_id": correlation_id, "error_type": "rate_limit"},
        )

    elif isinstance(error, TimeoutError):
        await message.channel.send(
            "⏱️ Request timed out. The query might be too complex. "
            "Try breaking it into smaller questions."
        )
        logger.warning(
            "LLM timeout",
            extra={"correlation_id": correlation_id, "error_type": "timeout"},
        )

    elif isinstance(error, Forbidden):
        logger.error(
            "Missing Discord permissions",
            extra={"correlation_id": correlation_id, "error_type": "forbidden"},
        )
        # Can't send message due to permissions - log only

    elif isinstance(error, HTTPException):
        if error.status == 429:  # Discord rate limit
            await message.channel.send("⏳ Discord rate limit reached. Slowing down...")

        logger.warning(
            f"Discord API error: {error.status}",
            extra={
                "correlation_id": correlation_id,
                "error_type": "http_exception",
                "status_code": error.status,
            },
        )

    else:
        # Generic error
        await message.channel.send(
            "❌ An unexpected error occurred. The team has been notified."
        )
        logger.error(
            f"Unexpected error: {error}",
            extra={"correlation_id": correlation_id, "error_type": type(error).__name__},
            exc_info=True,
        )
