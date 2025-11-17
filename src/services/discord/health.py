"""Health check for Discord bot and dependencies."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from src.lib.logging import get_logger

logger = get_logger(__name__)


@dataclass
class HealthStatus:
    """System health status."""

    is_healthy: bool
    discord_connected: bool
    vector_db_available: bool
    llm_provider_available: bool
    recent_error_rate: float
    avg_latency_ms: int
    timestamp: datetime


async def check_discord_connection(bot) -> bool:
    """Check if Discord bot is connected.

    Args:
        bot: Discord bot instance

    Returns:
        True if connected
    """
    try:
        return bot.is_ready() and bot.user is not None
    except Exception as e:
        logger.error(f"Discord connection check failed: {e}")
        return False


async def check_vector_db(vector_db) -> bool:
    """Check if vector database is available.

    Args:
        vector_db: Vector database instance

    Returns:
        True if available
    """
    try:
        # Simple ping/health check - implementation depends on VectorDB class
        # For Chroma, we can check if the collection exists
        if hasattr(vector_db, "health_check"):
            return await vector_db.health_check()
        return True  # Assume healthy if no health check method
    except Exception as e:
        logger.error(f"Vector DB check failed: {e}")
        return False


async def check_llm_provider(llm_provider) -> bool:
    """Check if LLM provider is available.

    Args:
        llm_provider: LLM provider instance

    Returns:
        True if available
    """
    try:
        # Simple check - could be a ping to the API
        # For now, assume healthy if provider is initialized
        return llm_provider is not None
    except Exception as e:
        logger.error(f"LLM provider check failed: {e}")
        return False


def get_error_rate() -> float:
    """Get recent error rate from metrics.

    Returns:
        Error rate (0.0 to 1.0)
    """
    # TODO: Implement metrics collection
    # For now, return 0.0 (no errors)
    return 0.0


def get_avg_latency() -> int:
    """Get average latency from metrics.

    Returns:
        Average latency in milliseconds
    """
    # TODO: Implement metrics collection
    # For now, return 0
    return 0


async def check_health(
    bot,
    vector_db,
    llm_provider,
) -> HealthStatus:
    """Check system health.

    Args:
        bot: Discord bot instance
        vector_db: Vector database instance
        llm_provider: LLM provider instance

    Returns:
        HealthStatus with all checks
    """
    checks = await asyncio.gather(
        check_discord_connection(bot),
        check_vector_db(vector_db),
        check_llm_provider(llm_provider),
        return_exceptions=True,
    )

    # Handle exceptions in gather results
    discord_ok = checks[0] if not isinstance(checks[0], Exception) else False
    vector_db_ok = checks[1] if not isinstance(checks[1], Exception) else False
    llm_ok = checks[2] if not isinstance(checks[2], Exception) else False

    is_healthy = all([discord_ok, vector_db_ok, llm_ok])

    status = HealthStatus(
        is_healthy=is_healthy,
        discord_connected=discord_ok,
        vector_db_available=vector_db_ok,
        llm_provider_available=llm_ok,
        recent_error_rate=get_error_rate(),
        avg_latency_ms=get_avg_latency(),
        timestamp=datetime.now(UTC),
    )

    logger.info(
        "Health check complete",
        extra={
            "is_healthy": status.is_healthy,
            "discord_connected": status.discord_connected,
            "vector_db_available": status.vector_db_available,
            "llm_provider_available": status.llm_provider_available,
        },
    )

    return status
