"""Unit tests for database quote validation tracking."""

import tempfile
from pathlib import Path

import pytest

from src.lib.database import AnalyticsDatabase


class TestDatabaseQuoteValidation:
    """Test quote validation tracking in analytics database."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary test database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        db = AnalyticsDatabase(db_path=db_path, enabled=True, retention_days=30)

        yield db

        # Cleanup
        Path(db_path).unlink(missing_ok=True)

    def test_insert_query_with_quote_validation(self, temp_db):
        """Test inserting query with quote validation fields."""
        query_data = {
            "query_id": "test-query-123",
            "discord_server_id": "server123",
            "discord_server_name": "Test Server",
            "channel_id": "channel456",
            "channel_name": "general",
            "username": "testuser",
            "query_text": "Can I shoot while concealed?",
            "response_text": '{"quotes": []}',
            "llm_model": "claude-4.5-sonnet",
            "confidence_score": 0.9,
            "rag_score": 0.85,
            "validation_passed": True,
            "latency_ms": 1500,
            "timestamp": "2025-01-15T10:00:00Z",
            "multi_hop_enabled": 0,
            "hops_used": 0,
            "cost": 0.01,
            "quote_validation_score": 0.75,
            "quote_total_count": 4,
            "quote_valid_count": 3,
            "quote_invalid_count": 1,
        }

        temp_db.insert_query(query_data)

        # Retrieve query
        query = temp_db.get_query_by_id("test-query-123")

        assert query is not None
        assert query["quote_validation_score"] == 0.75
        assert query["quote_total_count"] == 4
        assert query["quote_valid_count"] == 3
        assert query["quote_invalid_count"] == 1

    def test_insert_query_without_quote_validation(self, temp_db):
        """Test inserting query without quote validation (backward compatibility)."""
        query_data = {
            "query_id": "test-query-456",
            "discord_server_id": "server123",
            "discord_server_name": "Test Server",
            "channel_id": "channel456",
            "channel_name": "general",
            "username": "testuser",
            "query_text": "Can I shoot while concealed?",
            "response_text": '{"quotes": []}',
            "llm_model": "claude-4.5-sonnet",
            "confidence_score": 0.9,
            "rag_score": 0.85,
            "validation_passed": True,
            "latency_ms": 1500,
            "timestamp": "2025-01-15T10:00:00Z",
            "multi_hop_enabled": 0,
            "hops_used": 0,
            "cost": 0.01,
            # No quote validation fields
        }

        temp_db.insert_query(query_data)

        # Retrieve query
        query = temp_db.get_query_by_id("test-query-456")

        assert query is not None
        assert query["quote_validation_score"] is None
        assert query["quote_total_count"] == 0
        assert query["quote_valid_count"] == 0
        assert query["quote_invalid_count"] == 0

    def test_insert_invalid_quotes(self, temp_db):
        """Test inserting invalid quotes."""
        # First insert a query
        query_data = {
            "query_id": "test-query-789",
            "discord_server_id": "server123",
            "discord_server_name": "Test Server",
            "channel_id": "channel456",
            "channel_name": "general",
            "username": "testuser",
            "query_text": "Can I shoot while concealed?",
            "response_text": '{"quotes": []}',
            "llm_model": "claude-4.5-sonnet",
            "confidence_score": 0.9,
            "rag_score": 0.85,
            "validation_passed": True,
            "latency_ms": 1500,
            "timestamp": "2025-01-15T10:00:00Z",
            "quote_validation_score": 0.5,
            "quote_total_count": 2,
            "quote_valid_count": 1,
            "quote_invalid_count": 1,
        }

        temp_db.insert_query(query_data)

        # Insert invalid quotes
        invalid_quotes = [
            {
                "quote_title": "Fake Rule",
                "quote_text": "This is a completely made up rule.",
                "claimed_chunk_id": "abcd1234",
                "reason": "Quote not found in any RAG context chunk",
            }
        ]

        temp_db.insert_invalid_quotes("test-query-789", invalid_quotes)

        # Retrieve invalid quotes
        retrieved_quotes = temp_db.get_invalid_quotes_for_query("test-query-789")

        assert len(retrieved_quotes) == 1
        assert retrieved_quotes[0]["quote_title"] == "Fake Rule"
        assert retrieved_quotes[0]["quote_text"] == "This is a completely made up rule."
        assert retrieved_quotes[0]["claimed_chunk_id"] == "abcd1234"
        assert "not found" in retrieved_quotes[0]["reason"].lower()

    def test_insert_multiple_invalid_quotes(self, temp_db):
        """Test inserting multiple invalid quotes for same query."""
        # First insert a query
        query_data = {
            "query_id": "test-query-multi",
            "discord_server_id": "server123",
            "discord_server_name": "Test Server",
            "channel_id": "channel456",
            "channel_name": "general",
            "username": "testuser",
            "query_text": "Can I shoot while concealed?",
            "response_text": '{"quotes": []}',
            "llm_model": "claude-4.5-sonnet",
            "confidence_score": 0.9,
            "rag_score": 0.85,
            "validation_passed": True,
            "latency_ms": 1500,
            "timestamp": "2025-01-15T10:00:00Z",
            "quote_validation_score": 0.33,
            "quote_total_count": 3,
            "quote_valid_count": 1,
            "quote_invalid_count": 2,
        }

        temp_db.insert_query(query_data)

        # Insert multiple invalid quotes
        invalid_quotes = [
            {
                "quote_title": "Fake Rule 1",
                "quote_text": "This is made up rule 1.",
                "claimed_chunk_id": "abcd1234",
                "reason": "Quote not found in any RAG context chunk",
            },
            {
                "quote_title": "Fake Rule 2",
                "quote_text": "This is made up rule 2.",
                "claimed_chunk_id": "efgh5678",
                "reason": "Quote not found in any RAG context chunk",
            },
        ]

        temp_db.insert_invalid_quotes("test-query-multi", invalid_quotes)

        # Retrieve invalid quotes
        retrieved_quotes = temp_db.get_invalid_quotes_for_query("test-query-multi")

        assert len(retrieved_quotes) == 2
        assert retrieved_quotes[0]["quote_title"] == "Fake Rule 1"
        assert retrieved_quotes[1]["quote_title"] == "Fake Rule 2"

    def test_get_invalid_quotes_for_nonexistent_query(self, temp_db):
        """Test retrieving invalid quotes for query that doesn't exist."""
        retrieved_quotes = temp_db.get_invalid_quotes_for_query("nonexistent-query")

        assert retrieved_quotes == []

    def test_cascade_delete_invalid_quotes(self, temp_db):
        """Test that invalid quotes are deleted when query is deleted."""
        # Insert query and invalid quotes
        query_data = {
            "query_id": "test-query-cascade",
            "discord_server_id": "server123",
            "discord_server_name": "Test Server",
            "channel_id": "channel456",
            "channel_name": "general",
            "username": "testuser",
            "query_text": "Can I shoot while concealed?",
            "response_text": '{"quotes": []}',
            "llm_model": "claude-4.5-sonnet",
            "confidence_score": 0.9,
            "rag_score": 0.85,
            "validation_passed": True,
            "latency_ms": 1500,
            "timestamp": "2025-01-15T10:00:00Z",
            "quote_validation_score": 0.5,
            "quote_total_count": 2,
            "quote_valid_count": 1,
            "quote_invalid_count": 1,
        }

        temp_db.insert_query(query_data)

        invalid_quotes = [
            {
                "quote_title": "Fake Rule",
                "quote_text": "This is made up.",
                "claimed_chunk_id": "abcd1234",
                "reason": "Quote not found",
            }
        ]

        temp_db.insert_invalid_quotes("test-query-cascade", invalid_quotes)

        # Verify invalid quotes exist
        retrieved_quotes = temp_db.get_invalid_quotes_for_query("test-query-cascade")
        assert len(retrieved_quotes) == 1

        # Delete query
        temp_db.delete_query("test-query-cascade")

        # Verify invalid quotes are also deleted (CASCADE)
        retrieved_quotes = temp_db.get_invalid_quotes_for_query("test-query-cascade")
        assert len(retrieved_quotes) == 0
