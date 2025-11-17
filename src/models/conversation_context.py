"""ConversationContext model for tracking user conversations.

Transient in-memory state for user conversations (not persisted to DB).
Based on specs/001-we-are-building/data-model.md
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

MessageRole = Literal["user", "bot"]


@dataclass
class Message:
    """A message in a conversation."""

    role: MessageRole
    text: str
    timestamp: datetime


@dataclass
class ConversationContext:
    """Transient in-memory state for user conversations."""

    context_key: str  # {channel_id}:{user_id}
    user_id: str
    channel_id: str
    message_history: list[Message] = field(default_factory=list)
    last_activity: datetime = field(default_factory=lambda: datetime.now(UTC))
    ttl_seconds: int = 1800  # 30 minutes

    @staticmethod
    def create_context_key(channel_id: str, user_id: str) -> str:
        """Create composite context key.

        Args:
            channel_id: Discord channel ID
            user_id: Discord user ID

        Returns:
            Composite key: {channel_id}:{user_id}
        """
        return f"{channel_id}:{user_id}"

    def validate(self) -> None:
        """Validate ConversationContext fields.

        Raises:
            ValueError: If validation fails
        """
        # Context key format validation
        if ":" not in self.context_key:
            raise ValueError("context_key must be format {channel_id}:{user_id}")

        # Message history limit (max 10 messages)
        if len(self.message_history) > 10:
            raise ValueError("message_history limited to 10 messages")

        # TTL validation
        if self.ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")

    def add_message(self, role: MessageRole, text: str) -> None:
        """Add message to conversation history.

        Maintains max 10 messages (FIFO).

        Args:
            role: Message role ("user" or "bot")
            text: Message text
        """
        message = Message(
            role=role,
            text=text,
            timestamp=datetime.now(UTC),
        )

        self.message_history.append(message)

        # Trim to last 10 messages
        if len(self.message_history) > 10:
            self.message_history = self.message_history[-10:]

        # Update last activity
        self.last_activity = datetime.now(UTC)

    def is_expired(self) -> bool:
        """Check if context has exceeded TTL.

        Returns:
            True if context should be cleaned up
        """
        now = datetime.now(UTC)
        expiry_time = self.last_activity + timedelta(seconds=self.ttl_seconds)
        return now > expiry_time

    def get_recent_messages(self, count: int = 5) -> list[Message]:
        """Get most recent messages.

        Args:
            count: Number of recent messages to retrieve

        Returns:
            List of recent messages
        """
        return self.message_history[-count:]

    def clear(self) -> None:
        """Clear message history."""
        self.message_history = []
        self.last_activity = datetime.now(UTC)

    @classmethod
    def create(
        cls,
        channel_id: str,
        user_id: str,
        ttl_seconds: int = 1800,
    ) -> "ConversationContext":
        """Create new conversation context.

        Args:
            channel_id: Discord channel ID
            user_id: Discord user ID
            ttl_seconds: Time-to-live in seconds (default: 30 minutes)

        Returns:
            ConversationContext instance
        """
        context_key = cls.create_context_key(channel_id, user_id)

        return cls(
            context_key=context_key,
            user_id=user_id,
            channel_id=channel_id,
            message_history=[],
            last_activity=datetime.now(UTC),
            ttl_seconds=ttl_seconds,
        )
