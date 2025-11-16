"""Unit tests for UserQuery model."""

import hashlib
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from src.models.user_query import UserQuery


class TestUserQuery:
    """Test UserQuery model."""

    def test_hash_user_id(self):
        """Test hashing Discord user ID."""
        user_id = "123456789"
        expected = hashlib.sha256(user_id.encode()).hexdigest()

        result = UserQuery.hash_user_id(user_id)

        assert result == expected
        assert len(result) == 64  # SHA-256 hex length

    def test_hash_user_id_consistent(self):
        """Test that hashing is consistent."""
        user_id = "987654321"

        result1 = UserQuery.hash_user_id(user_id)
        result2 = UserQuery.hash_user_id(user_id)

        assert result1 == result2

    def test_hash_user_id_unique(self):
        """Test that different IDs produce different hashes."""
        hash1 = UserQuery.hash_user_id("user123")
        hash2 = UserQuery.hash_user_id("user456")

        assert hash1 != hash2

    def test_create_context_id(self):
        """Test creating composite context ID."""
        context_id = UserQuery.create_context_id("channel123", "user456")

        assert context_id == "channel123:user456"

    def test_validate_success(self):
        """Test successful validation."""
        query = UserQuery(
            query_id=UUID("12345678-1234-5678-1234-567812345678"),
            user_id="hashed_user_id",
            channel_id="channel123",
            message_text="Can I overwatch?",
            sanitized_text="Can I overwatch?",
            timestamp=datetime.now(timezone.utc),
            conversation_context_id="channel123:user456",
            pii_redacted=False,
        )
        # Should not raise
        query.validate()

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

    def test_is_expired_exactly_7_days(self):
        """Test query exactly at 7 day boundary."""
        exactly_7_days = datetime.now(timezone.utc) - timedelta(days=7, seconds=1)

        query = UserQuery(
            query_id=UUID("12345678-1234-5678-1234-567812345678"),
            user_id="hashed_user_id",
            channel_id="channel123",
            message_text="Can I overwatch?",
            sanitized_text="Can I overwatch?",
            timestamp=exactly_7_days,
            conversation_context_id="channel123:user456",
        )

        assert query.is_expired() is True

    def test_from_discord_message(self):
        """Test creating UserQuery from Discord message."""
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

    def test_from_discord_message_hashes_user_id(self):
        """Test that from_discord_message properly hashes the user ID."""
        raw_user_id = "987654321"

        query = UserQuery.from_discord_message(
            discord_user_id=raw_user_id,
            channel_id="channel123",
            message_text="Test",
            sanitized_text="Test",
        )

        # User ID should be hashed, not raw
        assert query.user_id != raw_user_id
        assert query.user_id == UserQuery.hash_user_id(raw_user_id)

    def test_from_discord_message_creates_context_id(self):
        """Test that from_discord_message creates proper context ID."""
        discord_user_id = "123456789"
        channel_id = "channel456"

        query = UserQuery.from_discord_message(
            discord_user_id=discord_user_id,
            channel_id=channel_id,
            message_text="Test",
            sanitized_text="Test",
        )

        hashed_user = UserQuery.hash_user_id(discord_user_id)
        expected_context_id = f"{channel_id}:{hashed_user}"

        assert query.conversation_context_id == expected_context_id

    def test_message_text_and_sanitized_text_different(self):
        """Test handling when message and sanitized text differ."""
        query = UserQuery.from_discord_message(
            discord_user_id="123456789",
            channel_id="channel123",
            message_text="My email is test@example.com",
            sanitized_text="My email is [REDACTED]",
            pii_redacted=True,
        )

        assert query.message_text == "My email is test@example.com"
        assert query.sanitized_text == "My email is [REDACTED]"
        assert query.pii_redacted is True
