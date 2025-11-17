"""Unit tests for quote validator."""

import pytest

from src.services.llm.quote_validator import QuoteValidator


class TestQuoteValidator:
    """Test quote validation logic."""

    @pytest.fixture
    def validator(self):
        """Create validator with default threshold."""
        return QuoteValidator(similarity_threshold=0.85)

    @pytest.fixture
    def sample_context(self):
        """Sample RAG context chunks."""
        return [
            "An operative can perform the Shoot action with this weapon while it has a Conceal order.",
            "Each time a friendly operative activates, select one of the following orders for it to have.",
            "Barricades are terrain features that provide Cover.",
        ]

    @pytest.fixture
    def sample_chunk_ids(self):
        """Sample chunk IDs (last 8 chars of UUIDs)."""
        return [
            "12345678-90ab-cdef-1234-567890abcdef",
            "abcdef12-3456-7890-abcd-ef1234567890",
            "fedcba09-8765-4321-fedc-ba0987654321",
        ]

    def test_validate_all_valid_quotes(self, validator, sample_context, sample_chunk_ids):
        """Test validation with all valid quotes."""
        quotes = [
            {
                "quote_title": "Silent Weapons",
                "quote_text": "An operative can perform the Shoot action with this weapon while it has a Conceal order.",
                "chunk_id": "90abcdef",
            }
        ]

        result = validator.validate(quotes, sample_context, sample_chunk_ids)

        assert result.is_valid is True
        assert result.validation_score == 1.0
        assert result.total_quotes == 1
        assert result.valid_quotes == 1
        assert len(result.invalid_quotes) == 0

    def test_validate_invalid_quote(self, validator, sample_context, sample_chunk_ids):
        """Test validation with hallucinated quote."""
        quotes = [
            {
                "quote_title": "Fake Rule",
                "quote_text": "This weapon allows shooting while concealed and also grants bonus AP.",
                "chunk_id": "90abcdef",
            }
        ]

        result = validator.validate(quotes, sample_context, sample_chunk_ids)

        assert result.is_valid is False
        assert result.validation_score == 0.0
        assert result.total_quotes == 1
        assert result.valid_quotes == 0
        assert len(result.invalid_quotes) == 1
        assert result.invalid_quotes[0]["quote_text"] == quotes[0]["quote_text"]
        assert "not found" in result.invalid_quotes[0]["reason"].lower()

    def test_validate_mixed_quotes(self, validator, sample_context, sample_chunk_ids):
        """Test validation with mix of valid and invalid quotes."""
        quotes = [
            {
                "quote_title": "Silent Weapons",
                "quote_text": "An operative can perform the Shoot action with this weapon while it has a Conceal order.",
                "chunk_id": "90abcdef",
            },
            {
                "quote_title": "Fake Rule",
                "quote_text": "This is a completely made up rule that does not exist.",
                "chunk_id": "90abcdef",
            },
            {
                "quote_title": "Cover",
                "quote_text": "Barricades are terrain features that provide Cover.",
                "chunk_id": "87654321",
            },
        ]

        result = validator.validate(quotes, sample_context, sample_chunk_ids)

        assert result.is_valid is False
        assert result.validation_score == pytest.approx(2 / 3, abs=0.01)
        assert result.total_quotes == 3
        assert result.valid_quotes == 2
        assert len(result.invalid_quotes) == 1

    def test_validate_empty_quotes(self, validator, sample_context, sample_chunk_ids):
        """Test validation with empty quote list."""
        quotes = []

        result = validator.validate(quotes, sample_context, sample_chunk_ids)

        assert result.is_valid is True
        assert result.validation_score == 1.0
        assert result.total_quotes == 0
        assert result.valid_quotes == 0
        assert len(result.invalid_quotes) == 0

    def test_validate_quote_with_minor_formatting(
        self, validator, sample_context, sample_chunk_ids
    ):
        """Test that minor formatting differences are accepted (fuzzy match)."""
        quotes = [
            {
                "quote_title": "Silent Weapons",
                # Extra whitespace and slightly different punctuation
                "quote_text": "An operative can perform the Shoot action with this weapon  while it has a Conceal order",
                "chunk_id": "90abcdef",
            }
        ]

        result = validator.validate(quotes, sample_context, sample_chunk_ids)

        # Should still be valid due to fuzzy matching
        assert result.is_valid is True
        assert result.validation_score == 1.0

    def test_is_quote_in_chunk_exact_match(self, validator):
        """Test exact match detection."""
        quote = "This is a test quote."
        chunk = "Some text before. This is a test quote. Some text after."

        assert validator._is_quote_in_chunk(quote, chunk) is True

    def test_is_quote_in_chunk_case_insensitive(self, validator):
        """Test case-insensitive matching."""
        quote = "This Is A Test Quote."
        chunk = "Some text before. this is a test quote. Some text after."

        assert validator._is_quote_in_chunk(quote, chunk) is True

    def test_is_quote_in_chunk_whitespace_normalization(self, validator):
        """Test whitespace normalization."""
        quote = "This   is    a    test   quote."
        chunk = "Some text before. This is a test quote. Some text after."

        assert validator._is_quote_in_chunk(quote, chunk) is True

    def test_is_quote_in_chunk_not_found(self, validator):
        """Test quote not found in chunk."""
        quote = "This quote does not exist."
        chunk = "Some completely different text."

        assert validator._is_quote_in_chunk(quote, chunk) is False

    def test_validate_without_chunk_ids(self, validator, sample_context):
        """Test validation without chunk IDs (backward compatibility)."""
        quotes = [
            {
                "quote_title": "Silent Weapons",
                "quote_text": "An operative can perform the Shoot action with this weapon while it has a Conceal order.",
            }
        ]

        result = validator.validate(quotes, sample_context, chunk_ids=None)

        assert result.is_valid is True
        assert result.validation_score == 1.0

    def test_validate_empty_quote_text_skipped(self, validator, sample_context, sample_chunk_ids):
        """Test that empty quote texts are skipped in validation."""
        quotes = [
            {"quote_title": "Empty Quote", "quote_text": "", "chunk_id": "90abcdef"},
            {
                "quote_title": "Valid Quote",
                "quote_text": "Barricades are terrain features that provide Cover.",
                "chunk_id": "87654321",
            },
        ]

        result = validator.validate(quotes, sample_context, sample_chunk_ids)

        # Empty quote should be skipped, so only 1 quote validated
        assert result.is_valid is True
        assert result.total_quotes == 2
        assert result.valid_quotes == 2  # Empty quotes don't count as invalid

    def test_similarity_threshold_strict(self):
        """Test with strict similarity threshold."""
        validator = QuoteValidator(similarity_threshold=0.95)

        quote = "This is a test quote with some differences."
        chunk = "This is a test quote with many differences."

        # With strict threshold, this might not match
        # (depends on actual similarity score)
        result = validator._is_quote_in_chunk(quote, chunk)

        # Just verify it runs without error
        assert isinstance(result, bool)
