"""Discord client setup with raw event handlers."""

import discord

from src.lib.logging import get_logger
from src.services.discord import handlers
from src.services.discord.feedback_logger import FeedbackLogger

logger = get_logger(__name__)


class KillTeamBot(discord.Client):
    """Kill Team Rules Discord Bot using raw event handlers (Orchestrator Pattern)."""

    def __init__(self, orchestrator=None):
        """Initialize Discord client with required intents.

        Args:
            orchestrator: Optional orchestrator instance for query processing
        """
        intents = discord.Intents.default()
        intents.message_content = True  # Required to read message content
        intents.guild_messages = True  # Required to receive guild messages
        intents.guild_reactions = True  # Required for feedback buttons

        super().__init__(intents=intents)
        self.orchestrator = orchestrator
        self.feedback_logger = FeedbackLogger()

    async def on_ready(self):
        """Called when bot successfully connects to Discord."""
        logger.info(
            f"Bot connected as {self.user}",
            extra={
                "event_type": "bot_ready",
                "bot_id": str(self.user.id),
                "guild_count": len(self.guilds),
            },
        )

    async def on_message(self, message: discord.Message):
        """Handle incoming Discord messages.

        Args:
            message: Discord message object
        """
        await handlers.handle_message(self, message, self.orchestrator)

    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        """Handle reaction additions for feedback tracking.

        Args:
            reaction: Discord reaction object
            user: User who added the reaction
        """
        await self.feedback_logger.on_reaction_add(reaction, user, self.user.id)

    async def setup_hook(self):
        """Called during bot setup - initialize services here."""
        logger.info("Running bot setup hook")
        # Orchestrator and services will be injected before bot.run()
