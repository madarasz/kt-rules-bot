"""Tests for ErrorMessageBuilder service."""

import pytest

from src.services.discord.error_message_builder import ErrorMessageBuilder


class TestErrorMessageBuilder:
    """Test error message building business logic."""

    def test_build_error_message_credit_error(self):
        """Test that credit balance errors are detected."""
        error = Exception("API error: credit balance insufficient")
        message = ErrorMessageBuilder.build_error_message(error)

        assert "💰" in message
        assert "credit balance" in message.lower()

    def test_build_error_message_auth_error(self):
        """Test that authentication errors are detected."""
        error = Exception("invalid api key provided")
        message = ErrorMessageBuilder.build_error_message(error)

        assert "🔑" in message
        assert "api key" in message.lower()

    def test_build_error_message_rate_limit_error(self):
        """Test that rate limit errors are detected."""
        error = Exception("rate limit exceeded")
        message = ErrorMessageBuilder.build_error_message(error)

        assert "⏳" in message
        assert "rate limit" in message.lower()

    def test_build_error_message_content_filter_error(self):
        """Test that content filter errors are detected."""
        error = Exception("content policy violation detected")
        message = ErrorMessageBuilder.build_error_message(error)

        assert "⚠️" in message
        assert "safety" in message.lower() or "filter" in message.lower()

    def test_build_error_message_generic_error(self):
        """Test that unknown errors get generic message."""
        error = Exception("some unknown error occurred")
        message = ErrorMessageBuilder.build_error_message(error)

        assert "❌" in message
        assert "error occurred" in message.lower()

    def test_build_error_message_case_insensitive(self):
        """Test that error detection is case-insensitive."""
        error = Exception("INVALID API KEY PROVIDED")
        message = ErrorMessageBuilder.build_error_message(error)

        assert "🔑" in message
        assert "api key" in message.lower()

    @pytest.mark.parametrize(
        "error_text,expected_icon",
        [
            ("insufficient funds available", "💰"),
            ("quota exceeded for this key", "💰"),
            ("authentication failed", "🔑"),
            ("unauthorized access", "🔑"),
            ("too many requests", "⏳"),
            ("content safety filter triggered", "⚠️"),
        ],
    )
    def test_build_error_message_variations(self, error_text, expected_icon):
        """Test various error message variations are detected correctly."""
        error = Exception(error_text)
        message = ErrorMessageBuilder.build_error_message(error)

        assert expected_icon in message
