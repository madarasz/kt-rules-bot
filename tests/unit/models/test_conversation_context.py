"""Unit tests for ConversationContext model."""

from datetime import datetime, timedelta, timezone

import pytest

from src.models.conversation_context import ConversationContext, Message


class TestMessage:
    """Test Message dataclass."""

    def test_message_creation(self):
        """Test creating a message."""
        timestamp = datetime.now(timezone.utc)
        message = Message(
            role="user",
            text="Can I overwatch during charge?",
            timestamp=timestamp,
        )

        assert message.role == "user"
        assert message.text == "Can I overwatch during charge?"
        assert message.timestamp == timestamp


class TestConversationContext:
    """Test ConversationContext model."""

    def test_create_context_key(self):
        """Test context key creation."""
        key = ConversationContext.create_context_key("channel123", "user456")
        assert key == "channel123:user456"

    def test_validate_success(self):
        """Test successful validation."""
        context = ConversationContext(
            context_key="channel123:user456",
            user_id="user456",
            channel_id="channel123",
            message_history=[],
            ttl_seconds=1800,
        )
        # Should not raise
        context.validate()

    def test_add_message(self):
        """Test adding a message to history."""
        context = ConversationContext.create("channel123", "user456")

        context.add_message("user", "What are the charge rules?")

        assert len(context.message_history) == 1
        assert context.message_history[0].role == "user"
        assert context.message_history[0].text == "What are the charge rules?"

    def test_add_message_multiple(self):
        """Test adding multiple messages."""
        context = ConversationContext.create("channel123", "user456")

        context.add_message("user", "Question 1")
        context.add_message("bot", "Answer 1")
        context.add_message("user", "Question 2")

        assert len(context.message_history) == 3
        assert context.message_history[0].role == "user"
        assert context.message_history[1].role == "bot"
        assert context.message_history[2].role == "user"

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
        context.last_activity = datetime.now(timezone.utc) - timedelta(seconds=2)

        assert context.is_expired() is True

    def test_get_recent_messages(self):
        """Test retrieving recent messages."""
        context = ConversationContext.create("channel123", "user456")

        for i in range(8):
            context.add_message("user", f"Message {i}")

        recent = context.get_recent_messages(count=3)

        assert len(recent) == 3
        assert recent[0].text == "Message 5"
        assert recent[1].text == "Message 6"
        assert recent[2].text == "Message 7"

    def test_get_recent_messages_fewer_than_requested(self):
        """Test retrieving recent messages when fewer exist."""
        context = ConversationContext.create("channel123", "user456")

        context.add_message("user", "Message 1")
        context.add_message("user", "Message 2")

        recent = context.get_recent_messages(count=5)

        assert len(recent) == 2

    def test_clear(self):
        """Test clearing message history."""
        context = ConversationContext.create("channel123", "user456")

        context.add_message("user", "Message 1")
        context.add_message("user", "Message 2")

        context.clear()

        assert len(context.message_history) == 0

    def test_create(self):
        """Test creating new conversation context."""
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
        assert isinstance(context.last_activity, datetime)

    def test_create_default_ttl(self):
        """Test creating context with default TTL."""
        context = ConversationContext.create("channel123", "user456")

        assert context.ttl_seconds == 1800  # 30 minutes default

    def test_add_message_updates_last_activity(self):
        """Test that adding a message updates last_activity."""
        context = ConversationContext.create("channel123", "user456")

        initial_activity = context.last_activity

        # Wait a tiny bit to ensure time difference
        import time
        time.sleep(0.01)

        context.add_message("user", "New message")

        assert context.last_activity > initial_activity
