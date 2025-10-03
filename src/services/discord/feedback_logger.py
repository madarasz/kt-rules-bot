"""Feedback logging service for tracking user reactions."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import discord

from src.lib.logging import get_logger
from src.models.user_query import UserQuery

logger = get_logger(__name__)


class FeedbackLogger:
    """Logs user feedback from reaction buttons (👍👎) for analytics."""

    def __init__(self):
        """Initialize feedback logger."""
        self.feedback_cache = {}  # Optional: track feedback to prevent duplicates

    async def on_reaction_add(
        self,
        reaction: discord.Reaction,
        user: discord.User,
        bot_user_id: int,
    ) -> None:
        """Log feedback from reaction buttons.

        Args:
            reaction: Discord reaction object
            user: User who added the reaction
            bot_user_id: Bot's user ID (to filter bot messages only)
        """
        # Only process bot's own messages
        if reaction.message.author.id != bot_user_id:
            return

        # Only process thumbs up/down
        if reaction.emoji not in ["👍", "👎"]:
            return

        # Don't log bot's own reactions
        if user.id == bot_user_id:
            return

        # Map emoji to feedback type
        feedback_type = "helpful" if reaction.emoji == "👍" else "not_helpful"

        # Extract response_id from message footer
        response_id = self._extract_response_id(reaction.message)

        if not response_id:
            logger.warning(
                "Could not extract response_id from message",
                extra={"message_id": str(reaction.message.id)},
            )
            return

        # Create feedback log entry
        feedback_id = uuid4()
        hashed_user_id = UserQuery.hash_user_id(str(user.id))

        # Log to structured logs
        logger.info(
            "User feedback received",
            extra={
                "event_type": "user_feedback",
                "feedback_id": str(feedback_id),
                "response_id": str(response_id),
                "user_id": hashed_user_id[:16],  # Partial hash for privacy
                "feedback_type": feedback_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        # Optional: Store in feedback_cache for deduplication
        cache_key = f"{response_id}:{hashed_user_id}"
        self.feedback_cache[cache_key] = {
            "feedback_id": feedback_id,
            "feedback_type": feedback_type,
            "timestamp": datetime.now(timezone.utc),
        }

    def _extract_response_id(self, message: discord.Message) -> UUID | None:
        """Extract response_id from message footer.

        Args:
            message: Discord message with embed

        Returns:
            Response UUID or None if not found
        """
        if not message.embeds:
            return None

        embed = message.embeds[0]
        if not embed.footer or not embed.footer.text:
            return None

        # Footer format: "ID: 12345678 | Provider: claude | ..."
        footer_text = embed.footer.text
        if "ID:" not in footer_text:
            return None

        try:
            # Extract short ID from footer
            id_part = footer_text.split("ID:")[1].split("|")[0].strip()

            # NOTE: This is a shortened ID - in production you'd need a mapping
            # from short ID to full UUID, or store full UUID in footer
            # For now, we'll create a UUID from the short ID (hacky but works for logging)
            # Better: Store full UUID in message or use a database lookup

            # For proper implementation, you'd do:
            # return await db.get_response_id_by_short_id(id_part)

            # For now, just log the short ID
            logger.debug(f"Extracted short response_id: {id_part}")
            return None  # Can't reconstruct full UUID from short ID

        except Exception as e:
            logger.warning(f"Error extracting response_id: {e}")
            return None

    def get_feedback_stats(self) -> dict:
        """Get feedback statistics from cache.

        Returns:
            Dictionary with feedback stats
        """
        if not self.feedback_cache:
            return {"total_feedback": 0, "helpful": 0, "not_helpful": 0}

        helpful_count = sum(
            1 for f in self.feedback_cache.values() if f["feedback_type"] == "helpful"
        )
        not_helpful_count = sum(
            1
            for f in self.feedback_cache.values()
            if f["feedback_type"] == "not_helpful"
        )

        return {
            "total_feedback": len(self.feedback_cache),
            "helpful": helpful_count,
            "not_helpful": not_helpful_count,
            "helpful_rate": (
                helpful_count / len(self.feedback_cache)
                if self.feedback_cache
                else 0.0
            ),
        }
