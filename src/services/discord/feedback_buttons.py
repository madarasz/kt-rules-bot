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
        self.voters = {}  # Track votes: {user_id: feedback_type}
        self.helpful_count = 0
        self.not_helpful_count = 0

    @discord.ui.button(label="Helpful 👍", style=discord.ButtonStyle.success, custom_id="helpful")
    async def helpful_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        """Handle 'Helpful' button click."""
        await self._handle_feedback(interaction, "helpful")

    @discord.ui.button(
        label="Not Helpful 👎", style=discord.ButtonStyle.secondary, custom_id="not_helpful"
    )
    async def not_helpful_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        """Handle 'Not Helpful' button click."""
        await self._handle_feedback(interaction, "not_helpful")

    async def _handle_feedback(self, interaction: discord.Interaction, feedback_type: str):
        """Process feedback from button interaction.

        Args:
            interaction: Discord interaction from button click
            feedback_type: 'helpful' or 'not_helpful'
        """
        user_id = str(interaction.user.id)
        previous_feedback = self.voters.get(user_id)

        # Same button clicked again - silently ignore
        if previous_feedback == feedback_type:
            await interaction.response.defer()
            return

        # Changing vote - decrement old count
        if previous_feedback:
            if previous_feedback == "helpful":
                self.helpful_count = max(0, self.helpful_count - 1)
            else:
                self.not_helpful_count = max(0, self.not_helpful_count - 1)

        # Increment new vote count
        if feedback_type == "helpful":
            self.helpful_count += 1
        else:
            self.not_helpful_count += 1

        # Update vote tracking
        self.voters[user_id] = feedback_type

        # Update button labels with new counts and edit message
        self._update_button_labels()
        await interaction.response.edit_message(view=self)

        # Log to feedback logger
        if self.feedback_logger:
            await self.feedback_logger.record_button_feedback(
                query_id=self.query_id,
                response_id=self.response_id,
                user_id=user_id,
                feedback_type=feedback_type,
                previous_feedback_type=previous_feedback,
            )

        logger.info(
            f"Feedback button clicked: {feedback_type}",
            extra={
                "query_id": self.query_id,
                "response_id": self.response_id,
                "feedback_type": feedback_type,
                "previous_feedback": previous_feedback,
                "user_id": user_id[:16],  # Partial for privacy
                "helpful_count": self.helpful_count,
                "not_helpful_count": self.not_helpful_count,
            },
        )

    def _update_button_labels(self):
        """Update button labels with current vote counts."""
        for child in self.children:
            if child.custom_id == "helpful":
                count_str = f" [{self.helpful_count}]" if self.helpful_count > 0 else ""
                child.label = f"Helpful 👍{count_str}"
            elif child.custom_id == "not_helpful":
                count_str = f" [{self.not_helpful_count}]" if self.not_helpful_count > 0 else ""
                child.label = f"Not Helpful 👎{count_str}"

    async def on_timeout(self):
        """Disable buttons when view times out."""
        for item in self.children:
            item.disabled = True

        logger.debug("Feedback view timed out", extra={"response_id": self.response_id})
