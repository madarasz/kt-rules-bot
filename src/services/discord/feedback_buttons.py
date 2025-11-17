"""Discord UI components for user feedback."""

import discord

from src.lib.logging import get_logger

logger = get_logger(__name__)


class FeedbackView(discord.ui.View):
    """Discord UI View with feedback buttons (Helpful/Not Helpful)."""

    def __init__(self, feedback_logger, query_id: str, response_id: str, timeout: int = 86400):
        """Initialize feedback view.

        Args:
            feedback_logger: FeedbackLogger instance for tracking feedback
            query_id: Query UUID for database tracking
            response_id: Response UUID for database tracking
            timeout: Button timeout in seconds (default 24 hours)
        """
        super().__init__(timeout=timeout)
        self.feedback_logger = feedback_logger
        self.query_id = query_id
        self.response_id = response_id
        self.voters = set()  # Track who voted to prevent duplicates

    @discord.ui.button(label="Helpful 👍", style=discord.ButtonStyle.success, custom_id="helpful")
    async def helpful_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        """Handle 'Helpful' button click."""
        await self._handle_feedback(interaction, "helpful", "👍")

    @discord.ui.button(
        label="Not Helpful 👎", style=discord.ButtonStyle.danger, custom_id="not_helpful"
    )
    async def not_helpful_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        """Handle 'Not Helpful' button click."""
        await self._handle_feedback(interaction, "not_helpful", "👎")

    async def _handle_feedback(
        self, interaction: discord.Interaction, feedback_type: str, emoji: str
    ):
        """Process feedback from button interaction.

        Args:
            interaction: Discord interaction from button click
            feedback_type: 'helpful' or 'not_helpful'
            emoji: Emoji for user confirmation
        """
        user_id = str(interaction.user.id)

        # Prevent duplicate votes from same user
        if user_id in self.voters:
            await interaction.response.send_message(
                "You've already provided feedback on this response!", ephemeral=True
            )
            return

        # Record vote
        self.voters.add(user_id)

        # Log to feedback logger
        if self.feedback_logger:
            await self.feedback_logger.record_button_feedback(
                query_id=self.query_id,
                response_id=self.response_id,
                user_id=user_id,
                feedback_type=feedback_type,
            )

        # Send ephemeral acknowledgement
        await interaction.response.send_message(
            f"Thanks for your feedback! {emoji}", ephemeral=True
        )

        logger.info(
            f"Feedback button clicked: {feedback_type}",
            extra={
                "query_id": self.query_id,
                "response_id": self.response_id,
                "feedback_type": feedback_type,
                "user_id": user_id[:16],  # Partial for privacy
            },
        )

    async def on_timeout(self):
        """Disable buttons when view times out."""
        for item in self.children:
            item.disabled = True

        logger.debug("Feedback view timed out", extra={"response_id": self.response_id})
