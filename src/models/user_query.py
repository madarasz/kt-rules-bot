"""UserQuery model for Discord user questions.

Represents a question from a Discord user about Kill Team rules.
Based on specs/001-we-are-building/data-model.md
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import hashlib


@dataclass
class UserQuery:
    """A question from a Discord user about Kill Team rules."""

    query_id: UUID
    user_id: str  # Hashed Discord user ID (SHA-256)
    channel_id: str
    message_text: str
    sanitized_text: str
    timestamp: datetime
    conversation_context_id: str  # Composite key: {channel_id}:{user_id}
    pii_redacted: bool = False

    @staticmethod
    def hash_user_id(discord_user_id: str) -> str:
        """Hash Discord user ID for GDPR compliance.

        Args:
            discord_user_id: Raw Discord user ID

        Returns:
            SHA-256 hashed user ID
        """
        return hashlib.sha256(discord_user_id.encode()).hexdigest()

    @staticmethod
    def create_context_id(channel_id: str, user_id: str) -> str:
        """Create composite context key for conversation tracking.

        Args:
            channel_id: Discord channel ID
            user_id: Discord user ID (raw or hashed)

        Returns:
            Composite key: {channel_id}:{user_id}
        """
        return f"{channel_id}:{user_id}"

    def validate(self) -> None:
        """Validate UserQuery fields.

        Raises:
            ValueError: If validation fails
        """
        # Message text length validation
        if len(self.message_text) > 2000:
            raise ValueError("message_text exceeds 2000 character limit")

        # Timestamp within 7 days for GDPR retention
        now = datetime.now(timezone.utc)
        seven_days_ago = now - timedelta(days=7)
        if self.timestamp < seven_days_ago:
            raise ValueError("timestamp exceeds 7-day retention period")

        # Validate conversation_context_id format
        if ":" not in self.conversation_context_id:
            raise ValueError(
                "conversation_context_id must be format {channel_id}:{user_id}"
            )

    def is_expired(self) -> bool:
        """Check if query has exceeded 7-day GDPR retention period.

        Returns:
            True if query should be deleted
        """
        now = datetime.now(timezone.utc)
        seven_days_ago = now - timedelta(days=7)
        return self.timestamp < seven_days_ago

    @classmethod
    def from_discord_message(
        cls,
        discord_user_id: str,
        channel_id: str,
        message_text: str,
        sanitized_text: str,
        pii_redacted: bool = False,
    ) -> "UserQuery":
        """Create UserQuery from Discord message data.

        Args:
            discord_user_id: Raw Discord user ID
            channel_id: Discord channel ID
            message_text: Original message text
            sanitized_text: Sanitized message text
            pii_redacted: Whether PII was detected and redacted

        Returns:
            UserQuery instance
        """
        hashed_user_id = cls.hash_user_id(discord_user_id)
        context_id = cls.create_context_id(channel_id, hashed_user_id)

        return cls(
            query_id=uuid4(),
            user_id=hashed_user_id,
            channel_id=channel_id,
            message_text=message_text,
            sanitized_text=sanitized_text,
            timestamp=datetime.now(timezone.utc),
            conversation_context_id=context_id,
            pii_redacted=pii_redacted,
        )
