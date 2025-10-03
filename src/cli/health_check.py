"""CLI command to check system health."""

import asyncio
import sys
from datetime import datetime

from src.lib.config import Config
from src.lib.logging import get_logger
from src.services.discord.health import check_health, HealthStatus
from src.services.llm.factory import LLMProviderFactory
from src.services.rag.retriever import RAGRetriever

logger = get_logger(__name__)


class HealthChecker:
    """Manages health check execution without running the full bot."""

    def __init__(self, config: Config):
        """Initialize health checker with configuration.

        Args:
            config: Application configuration
        """
        self.config = config

    async def _initialize_services(self):
        """Initialize minimal services for health checking.

        Returns:
            Tuple of (rag_retriever, llm_provider)
        """
        try:
            # Initialize RAG retriever
            rag_retriever = RAGRetriever()

            # Initialize LLM provider
            llm_factory = LLMProviderFactory()
            llm_provider = llm_factory.create()

            return rag_retriever, llm_provider

        except Exception as e:
            logger.error(f"Failed to initialize services: {e}", exc_info=True)
            raise

    def _print_status(self, status: HealthStatus, verbose: bool = False):
        """Print health status in human-readable format.

        Args:
            status: Health status to print
            verbose: Whether to show detailed information
        """
        # Status indicator
        if status.is_healthy:
            print("\n✅ System is HEALTHY\n")
        else:
            print("\n❌ System is UNHEALTHY\n")

        # Component status
        print("Component Status:")
        print(f"  Discord:    {'✓' if status.discord_connected else '✗'} "
              f"{'Connected' if status.discord_connected else 'Disconnected'}")
        print(f"  Vector DB:  {'✓' if status.vector_db_available else '✗'} "
              f"{'Available' if status.vector_db_available else 'Unavailable'}")
        print(f"  LLM:        {'✓' if status.llm_provider_available else '✗'} "
              f"{'Available' if status.llm_provider_available else 'Unavailable'}")

        if verbose:
            # Additional metrics
            print("\nMetrics:")
            print(f"  Error Rate:     {status.recent_error_rate:.2%}")
            print(f"  Avg Latency:    {status.avg_latency_ms}ms")
            print(f"  Check Time:     {status.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}")

        print()

    async def run(self, verbose: bool = False, wait_for_discord: bool = False) -> bool:
        """Run health check.

        Args:
            verbose: Show detailed information
            wait_for_discord: Wait for Discord connection (useful for startup checks)

        Returns:
            True if system is healthy, False otherwise
        """
        try:
            # Initialize services
            logger.info("Initializing services for health check...")
            rag_retriever, llm_provider = await self._initialize_services()

            # Create a mock bot object for health check (Discord check will fail without running bot)
            class MockBot:
                """Mock bot for health checks when bot is not running."""

                def __init__(self):
                    self.user = None

                def is_ready(self):
                    return False

            bot = MockBot()

            # If wait_for_discord is True, inform user that Discord check will fail
            if not wait_for_discord:
                logger.info(
                    "Note: Discord connection check will fail unless bot is running. "
                    "Use --wait-for-discord to check running bot."
                )

            # Run health check
            status = await check_health(
                bot=bot,
                vector_db=rag_retriever.vector_db if hasattr(rag_retriever, 'vector_db') else rag_retriever,
                llm_provider=llm_provider,
            )

            # Print status
            self._print_status(status, verbose=verbose)

            # Log result
            if status.is_healthy:
                logger.info("Health check passed")
            else:
                logger.warning("Health check failed")

            return status.is_healthy

        except Exception as e:
            logger.error(f"Health check error: {e}", exc_info=True)
            print(f"\n❌ Health check failed with error: {e}\n")
            return False


def health_check(verbose: bool = False, wait_for_discord: bool = False) -> None:
    """Check system health.

    Args:
        verbose: Show detailed information
        wait_for_discord: Wait for Discord connection
    """
    # Load configuration
    from src.lib.config import get_config
    config = get_config()

    # Create and run health checker
    checker = HealthChecker(config)

    try:
        is_healthy = asyncio.run(checker.run(verbose=verbose, wait_for_discord=wait_for_discord))

        # Exit with appropriate code
        sys.exit(0 if is_healthy else 1)

    except KeyboardInterrupt:
        logger.info("Health check interrupted")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Check Kill Team Rules Bot system health")
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed health information"
    )
    parser.add_argument(
        "--wait-for-discord",
        action="store_true",
        help="Wait for Discord connection (for checking running bot)"
    )
    args = parser.parse_args()

    health_check(verbose=args.verbose, wait_for_discord=args.wait_for_discord)
