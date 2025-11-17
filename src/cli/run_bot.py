"""CLI command to start the Discord bot."""

import asyncio
import signal
import sys

from src.lib.config import Config
from src.lib.database import AnalyticsDatabase
from src.lib.logging import get_logger
from src.services.discord.bot import KillTeamBotOrchestrator
from src.services.discord.client import KillTeamBot
from src.services.discord.context_manager import ConversationContextManager
from src.services.discord.feedback_logger import FeedbackLogger
from src.services.llm.factory import LLMProviderFactory
from src.services.llm.rate_limiter import RateLimiter
from src.services.llm.validator import ResponseValidator
from src.services.rag.retriever import RAGRetriever

logger = get_logger(__name__)


class BotRunner:
    """Manages Discord bot lifecycle with graceful shutdown."""

    def __init__(self, config: Config):
        """Initialize bot runner with configuration.

        Args:
            config: Application configuration
        """
        self.config = config
        self.bot: KillTeamBot | None = None
        self.shutdown_event = asyncio.Event()

    def _setup_signal_handlers(self) -> None:
        """Setup graceful shutdown handlers for SIGINT and SIGTERM."""

        def shutdown_handler(signum, _frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            self.shutdown_event.set()

        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)

    async def _initialize_services(self) -> KillTeamBotOrchestrator:
        """Initialize all services required by the orchestrator.

        Returns:
            Configured orchestrator instance

        Raises:
            Exception: If service initialization fails
        """
        logger.info("Initializing services...")

        try:
            # Initialize RAG retriever
            rag_retriever = RAGRetriever()
            logger.info("✓ RAG retriever initialized")

            # Initialize LLM provider factory
            llm_factory = LLMProviderFactory()
            logger.info("✓ LLM provider factory initialized")

            # Initialize validator
            validator = ResponseValidator()
            logger.info("✓ Response validator initialized")

            # Initialize rate limiter (10 req/min per user)
            rate_limiter = RateLimiter()
            logger.info("✓ Rate limiter initialized")

            # Initialize conversation context manager (30min TTL, 10 messages)
            context_manager = ConversationContextManager(ttl_seconds=1800)
            logger.info("✓ Conversation context manager initialized")

            # Initialize analytics database (optional, env-controlled)
            analytics_db = AnalyticsDatabase.from_config()
            if analytics_db.enabled:
                logger.info(f"✓ Analytics database initialized (retention: {analytics_db.retention_days} days)")
            else:
                logger.info("✓ Analytics database disabled")

            # Initialize feedback logger
            feedback_logger = FeedbackLogger(analytics_db=analytics_db)
            logger.info("✓ Feedback logger initialized")

            # Create orchestrator
            orchestrator = KillTeamBotOrchestrator(
                rag_retriever=rag_retriever,
                llm_provider_factory=llm_factory,
                response_validator=validator,
                rate_limiter=rate_limiter,
                context_manager=context_manager,
                analytics_db=analytics_db,
                feedback_logger=feedback_logger,
            )
            logger.info("✓ Orchestrator initialized")

            return orchestrator

        except Exception as e:
            logger.error(f"Failed to initialize services: {e}", exc_info=True)
            raise

    async def _run_bot_with_shutdown(self, token: str):
        """Run bot with graceful shutdown support.

        Args:
            token: Discord bot token
        """
        async with self.bot:
            # Start bot connection in background task
            bot_task = asyncio.create_task(self.bot.start(token))

            # Wait for shutdown signal
            await self.shutdown_event.wait()

            # Graceful shutdown
            logger.info("Closing Discord connection...")
            await self.bot.close()

            # Wait for bot task to complete
            try:
                await asyncio.wait_for(bot_task, timeout=10.0)
            except TimeoutError:
                logger.warning("Bot shutdown timeout, forcing exit")
                bot_task.cancel()

    async def run(self) -> None:
        """Run the Discord bot with full initialization and graceful shutdown."""
        # Setup signal handlers
        self._setup_signal_handlers()

        # Get Discord token
        token = self.config.discord_bot_token
        if not token:
            logger.error("Discord token not found in configuration")
            sys.exit(1)

        try:
            # Initialize all services
            orchestrator = await self._initialize_services()

            # Create Discord bot with orchestrator
            self.bot = KillTeamBot(orchestrator=orchestrator)

            # Share feedback logger between client and orchestrator
            self.bot.feedback_logger = orchestrator.feedback_logger
            logger.info("Discord bot created")

            # Display startup banner
            mode = "production"
            print(f"\n{'=' * 60}")
            print(f"  Kill Team Rules Bot - Starting in {mode.upper()} mode")
            print(f"{'=' * 60}")
            print(f"  LLM Provider: {self.config.default_llm_provider}")
            print("  Rate Limit: 10 requests/minute per user")
            print("  Context TTL: 30 minutes")
            print("  Max History: 10 messages")
            print(f"{'=' * 60}\n")

            logger.info(f"Starting bot in {mode} mode...")

            # Run bot with graceful shutdown
            await self._run_bot_with_shutdown(token)

            logger.info("Bot shutdown complete")

        except Exception as e:
            logger.error(f"Fatal error running bot: {e}", exc_info=True)
            sys.exit(1)


def run_bot(_mode: str = "production") -> None:
    """Start the Discord bot.

    Args:
        _mode: Runtime mode ('dev' or 'production') - currently unused
    """
    # Load configuration
    from src.lib.config import get_config
    config = get_config()

    # Create and run bot
    runner = BotRunner(config)

    try:
        asyncio.run(runner.run())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Start the Kill Team Rules Discord bot")
    parser.add_argument(
        "--mode",
        choices=["dev", "production"],
        default="production",
        help="Runtime mode (default: production)",
    )
    args = parser.parse_args()

    run_bot(mode=args.mode)
