"""Feedback logging service for tracking user reactions."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import discord

from src.lib.database import AnalyticsDatabase
from src.lib.logging import get_logger
from src.models.user_query import UserQuery

logger = get_logger(__name__)


class FeedbackLogger:
    """Logs user feedback from reaction buttons (👍👎) for analytics."""

    def __init__(self, analytics_db: AnalyticsDatabase | None = None):
        """Initialize feedback logger.

        Args:
            analytics_db: Optional analytics database instance
        """
        self.feedback_cache = {}  # Optional: track feedback to prevent duplicates
        self.analytics_db = analytics_db or AnalyticsDatabase.from_config()
        self.response_to_query_map = {}  # response_id -> query_id mapping

    async def on_reaction_add(
        self, reaction: discord.Reaction, user: discord.User, bot_user_id: int
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

        # Map response_id to query_id (1:1 mapping)
        query_id = self.response_to_query_map.get(str(response_id))

        if not query_id:
            logger.warning(
                "Could not map response_id to query_id", extra={"response_id": str(response_id)}
            )
            # Continue anyway for structured logging

        # Create feedback log entry
        feedback_id = uuid4()
        hashed_user_id = UserQuery.hash_user_id(str(user.id))

        # Update database vote count (if enabled and query_id found)
        if query_id and self.analytics_db.enabled:
            try:
                vote_type = "upvote" if reaction.emoji == "👍" else "downvote"
                self.analytics_db.increment_vote(query_id, vote_type)
                logger.debug(
                    "Vote incremented in analytics DB",
                    extra={"query_id": query_id, "vote_type": vote_type},
                )
            except Exception as e:
                logger.error(f"Failed to increment vote in DB: {e}", exc_info=True)

        # Log to structured logs
        logger.info(
            "User feedback received",
            extra={
                "event_type": "user_feedback",
                "feedback_id": str(feedback_id),
                "response_id": str(response_id),
                "query_id": query_id,
                "user_id": hashed_user_id[:16],  # Partial hash for privacy
                "feedback_type": feedback_type,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

        # Optional: Store in feedback_cache for deduplication
        cache_key = f"{response_id}:{hashed_user_id}"
        self.feedback_cache[cache_key] = {
            "feedback_id": feedback_id,
            "feedback_type": feedback_type,
            "timestamp": datetime.now(UTC),
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
            # Extract short ID from footer (first 8 chars of UUID)
            short_id = footer_text.split("ID:")[1].split("|")[0].strip()

            # Search through response_to_query_map for matching UUID
            for response_id in self.response_to_query_map:
                if response_id.startswith(short_id):
                    logger.debug(f"Matched short ID {short_id} to full response_id")
                    try:
                        return UUID(response_id)
                    except ValueError:
                        logger.warning(f"Invalid UUID format: {response_id}")
                        continue

            logger.warning(
                f"Could not find full response_id for short ID: {short_id}",
                extra={"short_id": short_id},
            )
            return None

        except Exception as e:
            logger.warning(f"Error extracting response_id: {e}")
            return None

    def register_response(self, query_id: str, response_id: str) -> None:
        """Map response_id to query_id for feedback tracking.

        Args:
            query_id: Query UUID (from UserQuery)
            response_id: Response UUID (from BotResponse)
        """
        self.response_to_query_map[response_id] = query_id
        logger.debug(
            "Response registered for feedback tracking",
            extra={"query_id": query_id, "response_id": response_id},
        )

    async def record_button_feedback(
        self,
        query_id: str,
        response_id: str,
        user_id: str,
        feedback_type: str,
        previous_feedback_type: str | None = None,
    ) -> None:
        """Record feedback from Discord UI button interaction.

        Args:
            query_id: Query UUID (from UserQuery)
            response_id: Response UUID (from BotResponse)
            user_id: Discord user ID (raw, will be hashed)
            feedback_type: 'helpful' or 'not_helpful'
            previous_feedback_type: Previous feedback type if user is changing vote
        """
        feedback_id = uuid4()
        hashed_user_id = UserQuery.hash_user_id(user_id)

        # Update database vote count (if enabled)
        if self.analytics_db.enabled:
            try:
                # If user is changing their vote, decrement the old vote first
                if previous_feedback_type and previous_feedback_type != feedback_type:
                    old_vote_type = "upvote" if previous_feedback_type == "helpful" else "downvote"
                    self.analytics_db.decrement_vote(query_id, old_vote_type)
                    logger.debug(
                        "Previous vote decremented in analytics DB",
                        extra={"query_id": query_id, "vote_type": old_vote_type},
                    )

                # Increment the new vote (or same vote if clicking again)
                if previous_feedback_type != feedback_type:
                    vote_type = "upvote" if feedback_type == "helpful" else "downvote"
                    self.analytics_db.increment_vote(query_id, vote_type)
                    logger.debug(
                        "Button vote incremented in analytics DB",
                        extra={"query_id": query_id, "vote_type": vote_type},
                    )
            except Exception as e:
                logger.error(f"Failed to update vote in DB: {e}", exc_info=True)

        # Log to structured logs
        logger.info(
            "Button feedback received",
            extra={
                "event_type": "button_feedback",
                "feedback_id": str(feedback_id),
                "response_id": response_id,
                "query_id": query_id,
                "user_id": hashed_user_id[:16],  # Partial hash for privacy
                "feedback_type": feedback_type,
                "previous_feedback_type": previous_feedback_type,
                "vote_changed": previous_feedback_type != feedback_type,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

        # Optional: Store in feedback_cache
        cache_key = f"{response_id}:{hashed_user_id}"
        self.feedback_cache[cache_key] = {
            "feedback_id": feedback_id,
            "feedback_type": feedback_type,
            "timestamp": datetime.now(UTC),
        }

    def get_feedback_stats(self) -> dict[str, object]:
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
            1 for f in self.feedback_cache.values() if f["feedback_type"] == "not_helpful"
        )

        return {
            "total_feedback": len(self.feedback_cache),
            "helpful": helpful_count,
            "not_helpful": not_helpful_count,
            "helpful_rate": (
                helpful_count / len(self.feedback_cache) if self.feedback_cache else 0.0
            ),
        }
