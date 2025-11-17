"""Unit tests for Analytics Database."""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.lib.database import AnalyticsDatabase


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_analytics.db")
        db = AnalyticsDatabase(db_path=db_path, enabled=True, retention_days=30)
        yield db


@pytest.fixture
def disabled_db():
    """Create a disabled database (no-ops)."""
    db = AnalyticsDatabase(db_path=":memory:", enabled=False, retention_days=30)
    return db


def test_database_initialization(temp_db):
    """Test database schema creation."""
    # Database should be created
    assert Path(temp_db.db_path).exists()

    # Tables should exist
    with temp_db._get_connection() as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]

    assert "queries" in tables
    assert "retrieved_chunks" in tables


def test_insert_query(temp_db):
    """Test inserting a query record."""
    query_data = {
        "query_id": "test-query-123",
        "discord_server_id": "server-456",
        "discord_server_name": "Test Server",
        "channel_id": "channel-789",
        "channel_name": "general",
        "username": "testuser",
        "query_text": "Can I charge through terrain?",
        "response_text": "Yes, you can charge through terrain...",
        "llm_model": "gpt-4.1",
        "confidence_score": 0.92,
        "rag_score": 0.85,
        "validation_passed": True,
        "latency_ms": 1200,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    temp_db.insert_query(query_data)

    # Verify insertion
    query = temp_db.get_query_by_id("test-query-123")
    assert query is not None
    assert query["query_id"] == "test-query-123"
    assert query["username"] == "testuser"
    assert query["llm_model"] == "gpt-4.1"
    assert query["confidence_score"] == 0.92
    assert query["upvotes"] == 0
    assert query["downvotes"] == 0
    assert query["admin_status"] == "pending"


def test_insert_chunks(temp_db):
    """Test inserting retrieved chunks."""
    # First insert a query
    query_data = {
        "query_id": "test-query-123",
        "discord_server_id": "server-456",
        "channel_id": "channel-789",
        "username": "testuser",
        "query_text": "Test query",
        "response_text": "Test response",
        "llm_model": "gpt-4.1",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    temp_db.insert_query(query_data)

    # Insert chunks
    chunks_data = [
        {
            "query_id": "test-query-123",
            "rank": 1,
            "chunk_header": "Charge Phase",
            "chunk_text": "During the charge phase...",
            "document_name": "rules-1-phases.md",
            "document_type": "core-rules",
            "vector_similarity": 0.85,
            "bm25_score": 12.3,
            "rrf_score": 0.9,
            "final_score": 0.92,
        },
        {
            "query_id": "test-query-123",
            "rank": 2,
            "chunk_header": "Movement",
            "chunk_text": "Models can move up to their movement characteristic...",
            "document_name": "rules-2-movement.md",
            "document_type": "core-rules",
            "vector_similarity": 0.78,
            "bm25_score": 10.1,
            "rrf_score": 0.82,
            "final_score": 0.88,
        },
    ]
    temp_db.insert_chunks("test-query-123", chunks_data)

    # Verify insertion
    chunks = temp_db.get_chunks_for_query("test-query-123")
    assert len(chunks) == 2
    assert chunks[0]["rank"] == 1
    assert chunks[0]["chunk_header"] == "Charge Phase"
    assert chunks[0]["final_score"] == 0.92
    assert chunks[0]["relevant"] is None  # Default value
    assert chunks[1]["rank"] == 2


def test_increment_vote(temp_db):
    """Test incrementing upvotes and downvotes."""
    # Insert a query
    query_data = {
        "query_id": "test-query-123",
        "discord_server_id": "server-456",
        "channel_id": "channel-789",
        "username": "testuser",
        "query_text": "Test query",
        "response_text": "Test response",
        "llm_model": "gpt-4.1",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    temp_db.insert_query(query_data)

    # Increment upvotes
    temp_db.increment_vote("test-query-123", "upvote")
    temp_db.increment_vote("test-query-123", "upvote")

    # Increment downvotes
    temp_db.increment_vote("test-query-123", "downvote")

    # Verify counts
    query = temp_db.get_query_by_id("test-query-123")
    assert query["upvotes"] == 2
    assert query["downvotes"] == 1


def test_update_admin_fields(temp_db):
    """Test updating admin status and notes."""
    # Insert a query
    query_data = {
        "query_id": "test-query-123",
        "discord_server_id": "server-456",
        "channel_id": "channel-789",
        "username": "testuser",
        "query_text": "Test query",
        "response_text": "Test response",
        "llm_model": "gpt-4.1",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    temp_db.insert_query(query_data)

    # Update admin fields
    temp_db.update_query_admin_fields(
        query_id="test-query-123", admin_status="approved", admin_notes="Looks good!"
    )

    # Verify updates
    query = temp_db.get_query_by_id("test-query-123")
    assert query["admin_status"] == "approved"
    assert query["admin_notes"] == "Looks good!"


def test_update_chunk_relevance(temp_db):
    """Test updating chunk relevance flag."""
    # Insert query and chunks
    query_data = {
        "query_id": "test-query-123",
        "discord_server_id": "server-456",
        "channel_id": "channel-789",
        "username": "testuser",
        "query_text": "Test query",
        "response_text": "Test response",
        "llm_model": "gpt-4.1",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    temp_db.insert_query(query_data)

    chunks_data = [
        {"query_id": "test-query-123", "rank": 1, "chunk_text": "Test chunk", "final_score": 0.9}
    ]
    temp_db.insert_chunks("test-query-123", chunks_data)

    # Get chunk ID
    chunks = temp_db.get_chunks_for_query("test-query-123")
    chunk_id = chunks[0]["id"]

    # Mark as relevant
    temp_db.update_chunk_relevance(chunk_id, True)
    chunks = temp_db.get_chunks_for_query("test-query-123")
    assert chunks[0]["relevant"] == 1

    # Mark as not relevant
    temp_db.update_chunk_relevance(chunk_id, False)
    chunks = temp_db.get_chunks_for_query("test-query-123")
    assert chunks[0]["relevant"] == 0

    # Clear relevance
    temp_db.update_chunk_relevance(chunk_id, None)
    chunks = temp_db.get_chunks_for_query("test-query-123")
    assert chunks[0]["relevant"] is None


def test_cleanup_old_records(temp_db):
    """Test GDPR cleanup of old records."""
    # Insert an old query (31 days ago)
    old_timestamp = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    old_query_data = {
        "query_id": "old-query-123",
        "discord_server_id": "server-456",
        "channel_id": "channel-789",
        "username": "testuser",
        "query_text": "Old query",
        "response_text": "Old response",
        "llm_model": "gpt-4.1",
        "timestamp": old_timestamp,
    }
    temp_db.insert_query(old_query_data)

    # Insert a recent query
    recent_timestamp = datetime.now(UTC).isoformat()
    recent_query_data = {
        "query_id": "recent-query-456",
        "discord_server_id": "server-456",
        "channel_id": "channel-789",
        "username": "testuser",
        "query_text": "Recent query",
        "response_text": "Recent response",
        "llm_model": "gpt-4.1",
        "timestamp": recent_timestamp,
    }
    temp_db.insert_query(recent_query_data)

    # Run cleanup
    deleted_count = temp_db.cleanup_old_records()
    assert deleted_count == 1

    # Verify old query deleted
    old_query = temp_db.get_query_by_id("old-query-123")
    assert old_query is None

    # Verify recent query still exists
    recent_query = temp_db.get_query_by_id("recent-query-456")
    assert recent_query is not None


def test_get_all_queries_with_filters(temp_db):
    """Test querying with filters."""
    # Insert multiple queries
    for i in range(5):
        query_data = {
            "query_id": f"query-{i}",
            "discord_server_id": "server-456",
            "channel_id": f"channel-{i % 2}",  # Alternating channels
            "username": "testuser",
            "query_text": f"Test query {i}",
            "response_text": f"Test response {i}",
            "llm_model": "gpt-4.1" if i % 2 == 0 else "claude-sonnet",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        temp_db.insert_query(query_data)

    # Update some admin statuses
    temp_db.update_query_admin_fields("query-0", admin_status="approved")
    temp_db.update_query_admin_fields("query-1", admin_status="issues")

    # Filter by admin status
    pending_queries = temp_db.get_all_queries(filters={"admin_status": "pending"})
    assert len(pending_queries) == 3

    approved_queries = temp_db.get_all_queries(filters={"admin_status": "approved"})
    assert len(approved_queries) == 1

    # Filter by LLM model
    gpt_queries = temp_db.get_all_queries(filters={"llm_model": "gpt-4.1"})
    assert len(gpt_queries) == 3

    # Filter by channel
    channel_0_queries = temp_db.get_all_queries(filters={"channel_id": "channel-0"})
    assert len(channel_0_queries) == 3


def test_get_stats(temp_db):
    """Test getting database statistics."""
    # Insert queries with feedback
    for i in range(3):
        query_data = {
            "query_id": f"query-{i}",
            "discord_server_id": "server-456",
            "channel_id": "channel-789",
            "username": "testuser",
            "query_text": f"Test query {i}",
            "response_text": f"Test response {i}",
            "llm_model": "gpt-4.1",
            "latency_ms": 1000 + (i * 100),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        temp_db.insert_query(query_data)

        # Add some votes
        temp_db.increment_vote(f"query-{i}", "upvote")
        if i > 0:
            temp_db.increment_vote(f"query-{i}", "downvote")

    # Update admin statuses
    temp_db.update_query_admin_fields("query-0", admin_status="approved")
    temp_db.update_query_admin_fields("query-1", admin_status="issues")

    # Get stats
    stats = temp_db.get_stats()

    assert stats["total_queries"] == 3
    assert stats["avg_latency_ms"] == 1100  # (1000 + 1100 + 1200) / 3
    assert stats["total_upvotes"] == 3
    assert stats["total_downvotes"] == 2
    assert stats["helpful_rate"] == 0.6  # 3 / (3 + 2)
    assert stats["status_counts"]["approved"] == 1
    assert stats["status_counts"]["issues"] == 1
    assert stats["status_counts"]["pending"] == 1


def test_disabled_database_no_ops(disabled_db):
    """Test that disabled database performs no operations."""
    # All operations should be no-ops
    query_data = {
        "query_id": "test-query-123",
        "discord_server_id": "server-456",
        "channel_id": "channel-789",
        "username": "testuser",
        "query_text": "Test query",
        "response_text": "Test response",
        "llm_model": "gpt-4.1",
        "timestamp": datetime.now(UTC).isoformat(),
    }

    # Insert should be no-op
    disabled_db.insert_query(query_data)

    # Get should return None/empty
    query = disabled_db.get_query_by_id("test-query-123")
    assert query is None

    queries = disabled_db.get_all_queries()
    assert queries == []

    # Stats should return empty dict
    stats = disabled_db.get_stats()
    assert stats == {}

    # Cleanup should return 0
    deleted = disabled_db.cleanup_old_records()
    assert deleted == 0


def test_search_filter(temp_db):
    """Test search filter on query text."""
    # Insert queries with different text
    query_data_1 = {
        "query_id": "query-1",
        "discord_server_id": "server-456",
        "channel_id": "channel-789",
        "username": "testuser",
        "query_text": "Can I charge through terrain?",
        "response_text": "Yes you can",
        "llm_model": "gpt-4.1",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    query_data_2 = {
        "query_id": "query-2",
        "discord_server_id": "server-456",
        "channel_id": "channel-789",
        "username": "testuser",
        "query_text": "How does overwatch work?",
        "response_text": "Overwatch lets you shoot",
        "llm_model": "gpt-4.1",
        "timestamp": datetime.now(UTC).isoformat(),
    }

    temp_db.insert_query(query_data_1)
    temp_db.insert_query(query_data_2)

    # Search for "charge"
    results = temp_db.get_all_queries(filters={"search": "charge"})
    assert len(results) == 1
    assert results[0]["query_id"] == "query-1"

    # Search for "overwatch"
    results = temp_db.get_all_queries(filters={"search": "overwatch"})
    assert len(results) == 1
    assert results[0]["query_id"] == "query-2"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
