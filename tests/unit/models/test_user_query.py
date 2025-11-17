"""Unit tests for UserQuery model - business logic only."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from src.models.user_query import UserQuery


class TestUserQuery:
    """Test UserQuery model - critical business logic."""

    def test_is_expired_not_expired(self):
        """Test query is not expired within retention period."""
        query = UserQuery(
            query_id=UUID("12345678-1234-5678-1234-567812345678"),
            user_id="hashed_user_id",
            channel_id="channel123",
            message_text="Can I overwatch?",
            sanitized_text="Can I overwatch?",
            timestamp=datetime.now(timezone.utc),
            conversation_context_id="channel123:user456",
        )

        assert query.is_expired() is False

    def test_is_expired_expired(self):
        """Test query is expired after 7 days."""
        old_timestamp = datetime.now(timezone.utc) - timedelta(days=8)

        query = UserQuery(
            query_id=UUID("12345678-1234-5678-1234-567812345678"),
            user_id="hashed_user_id",
            channel_id="channel123",
            message_text="Can I overwatch?",
            sanitized_text="Can I overwatch?",
            timestamp=old_timestamp,
            conversation_context_id="channel123:user456",
        )

        assert query.is_expired() is True

    def test_from_discord_message(self):
        """Test creating UserQuery from Discord message - integration of factory method."""
        discord_user_id = "123456789"
        channel_id = "channel123"
        message = "Can I use overwatch during a charge?"
        sanitized = "Can I use overwatch during a charge?"

        query = UserQuery.from_discord_message(
            discord_user_id=discord_user_id,
            channel_id=channel_id,
            message_text=message,
            sanitized_text=sanitized,
            pii_redacted=False,
        )

        assert isinstance(query.query_id, UUID)
        assert query.user_id == UserQuery.hash_user_id(discord_user_id)
        assert query.channel_id == channel_id
        assert query.message_text == message
        assert query.sanitized_text == sanitized
        assert query.pii_redacted is False
        assert isinstance(query.timestamp, datetime)
        assert query.conversation_context_id == f"{channel_id}:{query.user_id}"

    def test_from_discord_message_with_pii_redaction(self):
        """Test creating UserQuery with PII redacted."""
        query = UserQuery.from_discord_message(
            discord_user_id="123456789",
            channel_id="channel123",
            message_text="Original message",
            sanitized_text="Redacted message",
            pii_redacted=True,
        )

        assert query.pii_redacted is True
        assert query.message_text != query.sanitized_text
