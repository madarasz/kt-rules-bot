"""Conversation context manager for tracking message history."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from src.lib.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Message:
    """Single message in conversation history."""

    role: str  # "user" or "bot"
    text: str
    timestamp: datetime


@dataclass
class ConversationContext:
    """Conversation context for a user in a channel."""

    context_key: str
    message_history: list[Message] = field(default_factory=list)
    last_activity: datetime = field(default_factory=lambda: datetime.now(UTC))


class ConversationContextManager:
    """Manages conversation contexts with TTL-based cleanup."""

    def __init__(self, ttl_seconds: int = 1800):
        """Initialize context manager.

        Args:
            ttl_seconds: Time-to-live for inactive contexts (default 30 minutes)
        """
        self._contexts: dict[str, ConversationContext] = {}
        self.ttl = timedelta(seconds=ttl_seconds)
        self.max_history = 10  # Keep last 10 messages only

    def get_context(self, context_key: str) -> ConversationContext:
        """Get or create conversation context.

        Args:
            context_key: Context identifier (format: "{channel_id}:{user_id}")

        Returns:
            ConversationContext instance
        """
        if context_key not in self._contexts:
            self._contexts[context_key] = ConversationContext(
                context_key=context_key,
                message_history=[],
                last_activity=datetime.now(UTC),
            )
            logger.debug(
                "Created new conversation context",
                extra={"context_key": context_key},
            )

        return self._contexts[context_key]

    def add_message(self, context_key: str, role: str, text: str) -> None:
        """Add message to conversation history.

        Args:
            context_key: Context identifier
            role: Message role ("user" or "bot")
            text: Message text
        """
        context = self.get_context(context_key)
        context.message_history.append(
            Message(
                role=role,
                text=text,
                timestamp=datetime.now(UTC),
            )
        )

        # Keep only last N messages (message history only, NOT RAG chunks)
        if len(context.message_history) > self.max_history:
            context.message_history = context.message_history[-self.max_history :]

        context.last_activity = datetime.now(UTC)

        logger.debug(
            "Added message to context",
            extra={
                "context_key": context_key,
                "role": role,
                "message_count": len(context.message_history),
            },
        )

    def get_history(self, context_key: str) -> list[Message]:
        """Get message history for context.

        Args:
            context_key: Context identifier

        Returns:
            List of Message objects (last 10 messages)
        """
        context = self.get_context(context_key)
        return context.message_history.copy()

    async def cleanup_expired(self) -> int:
        """Remove expired contexts (background task).

        Returns:
            Number of contexts cleaned up
        """
        now = datetime.now(UTC)
        expired = [
            key
            for key, ctx in self._contexts.items()
            if now - ctx.last_activity > self.ttl
        ]

        for key in expired:
            del self._contexts[key]

        if expired:
            logger.info(
                f"Cleaned up {len(expired)} expired conversation contexts",
                extra={"expired_count": len(expired)},
            )

        return len(expired)

    def get_stats(self) -> dict[str, int]:
        """Get context manager statistics.

        Returns:
            Dictionary with stats (active_contexts, total_messages)
        """
        total_messages = sum(len(ctx.message_history) for ctx in self._contexts.values())

        return {
            "active_contexts": len(self._contexts),
            "total_messages": total_messages,
        }
