"""Unit tests for ConversationContext model - business logic only."""

from datetime import UTC, datetime, timedelta

from src.models.conversation_context import ConversationContext


class TestConversationContext:
    """Test ConversationContext model - critical business logic."""

    def test_add_message_trim_to_10(self):
        """Test message history is trimmed to 10 messages."""
        context = ConversationContext.create("channel123", "user456")

        # Add 15 messages
        for i in range(15):
            context.add_message("user", f"Message {i}")

        # Should only keep last 10
        assert len(context.message_history) == 10
        assert context.message_history[0].text == "Message 5"
        assert context.message_history[-1].text == "Message 14"

    def test_is_expired_not_expired(self):
        """Test context is not expired within TTL."""
        context = ConversationContext.create("channel123", "user456", ttl_seconds=1800)
        assert context.is_expired() is False

    def test_is_expired_expired(self):
        """Test context is expired after TTL."""
        context = ConversationContext.create("channel123", "user456", ttl_seconds=1)

        # Set last activity to 2 seconds ago
        context.last_activity = datetime.now(UTC) - timedelta(seconds=2)

        assert context.is_expired() is True

    def test_create(self):
        """Test creating new conversation context with factory method."""
        context = ConversationContext.create(
            channel_id="channel123",
            user_id="user456",
            ttl_seconds=3600,
        )

        assert context.context_key == "channel123:user456"
        assert context.user_id == "user456"
        assert context.channel_id == "channel123"
        assert context.message_history == []
        assert context.ttl_seconds == 3600
