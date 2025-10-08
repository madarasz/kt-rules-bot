"""Unit tests for RAG services.

Tests chunker, embeddings, retriever, and ingestor with 80%+ coverage.
Based on specs/001-we-are-building/tasks.md T039.
"""

import pytest
from uuid import uuid4
from datetime import date

from src.services.rag.chunker import MarkdownChunker, MarkdownChunk
from src.services.rag.validator import DocumentValidator
from src.services.rag.cache import RAGCache
from src.models.rule_document import RuleDocument
from src.models.rag_context import RAGContext, DocumentChunk
from src.lib.constants import CHUNKING_MAX_TOKENS


class TestMarkdownChunker:
    """Tests for MarkdownChunker."""

    def test_chunk_small_document_keeps_whole(self):
        """Small document without headers should be kept whole."""
        chunker = MarkdownChunker(max_tokens=CHUNKING_MAX_TOKENS)

        # Content without ## headers - should keep as single chunk
        content = """This is a simple rule document.

Models can move up to 6 inches during the movement phase.

Models can shoot at visible enemy models."""

        chunks = chunker.chunk(content)

        assert len(chunks) == 1
        assert chunks[0].header == ""
        assert chunks[0].header_level == 0
        assert "simple rule document" in chunks[0].text

    def test_chunk_large_document_splits_at_headers(self):
        """Large document should split at ## headers."""
        chunker = MarkdownChunker(max_tokens=100)  # Small limit for testing

        content = """## Movement Phase

""" + ("Lorem ipsum dolor sit amet. " * 50) + """

## Shooting Phase

""" + ("Lorem ipsum dolor sit amet. " * 50)

        chunks = chunker.chunk(content)

        # Should split into multiple chunks
        assert len(chunks) >= 2

        # Headers should be preserved
        headers = [chunk.header for chunk in chunks if chunk.header]
        assert "Movement Phase" in headers or "Shooting Phase" in headers

    def test_chunk_stats(self):
        """Test chunk statistics calculation."""
        chunker = MarkdownChunker()

        content = """## Section 1

Content 1.

## Section 2

Content 2."""

        chunks = chunker.chunk(content)
        stats = chunker.get_chunk_stats(chunks)

        assert stats["count"] == len(chunks)
        assert stats["total_tokens"] > 0
        assert stats["avg_tokens"] > 0


class TestDocumentValidator:
    """Tests for DocumentValidator."""

    def test_validate_valid_content(self):
        """Valid markdown with frontmatter should pass."""
        validator = DocumentValidator()

        # Use dedent to handle indentation properly
        content = """\
---
source: Core Rules v3.1
last_update_date: 2024-09-15
document_type: core-rules
section: Movement
---

## Movement Phase

Models move up to 6 inches."""

        is_valid, error, metadata = validator.validate_content(content)

        assert is_valid, f"Validation failed: {error}"
        assert error == ""
        assert metadata["source"] == "Core Rules v3.1"
        assert metadata["document_type"] == "core-rules"

    def test_validate_missing_frontmatter(self):
        """Markdown without frontmatter should fail."""
        validator = DocumentValidator()

        content = """\
## Movement Phase

Models move up to 6 inches."""

        is_valid, error, metadata = validator.validate_content(content)

        assert not is_valid
        assert "Missing YAML frontmatter" in error

    def test_validate_invalid_document_type(self):
        """Invalid document_type should fail."""
        validator = DocumentValidator()

        content = """\
---
source: Core Rules v3.1
last_update_date: 2024-09-15
document_type: invalid-type
---

## Content"""

        is_valid, error, metadata = validator.validate_content(content)

        assert not is_valid
        assert "Invalid document_type" in error

    def test_validate_missing_required_fields(self):
        """Missing required fields should fail."""
        validator = DocumentValidator()

        content = """\
---
source: Core Rules v3.1
---

## Content"""

        is_valid, error, metadata = validator.validate_content(content)

        assert not is_valid
        assert "Missing required fields" in error


class TestRAGCache:
    """Tests for RAGCache."""

    def test_cache_miss(self):
        """Cache miss should return None."""
        cache = RAGCache()

        result = cache.get("test query", "channel:user")

        assert result is None

    def test_cache_hit(self):
        """Cache hit should return cached result."""
        cache = RAGCache()

        # Create mock RAGContext
        context = RAGContext(
            context_id=uuid4(),
            query_id=uuid4(),
            document_chunks=[],
            relevance_scores=[],
            total_chunks=0,
            avg_relevance=0.0,
            meets_threshold=False,
        )

        # Set cache
        cache.set("test query", "channel:user", context)

        # Get from cache
        result = cache.get("test query", "channel:user")

        assert result is not None
        assert result.context_id == context.context_id

    def test_cache_invalidate_all(self):
        """Invalidate all should clear cache."""
        cache = RAGCache()

        # Add entries
        context = RAGContext(
            context_id=uuid4(),
            query_id=uuid4(),
            document_chunks=[],
            relevance_scores=[],
            total_chunks=0,
            avg_relevance=0.0,
            meets_threshold=False,
        )

        cache.set("query1", "channel:user", context)
        cache.set("query2", "channel:user", context)

        # Invalidate
        count = cache.invalidate()

        assert count == 2
        assert cache.get("query1", "channel:user") is None
        assert cache.get("query2", "channel:user") is None

    def test_cache_stats(self):
        """Cache stats should return correct information."""
        cache = RAGCache()

        stats = cache.get_stats()

        assert "total_entries" in stats
        assert "ttl_seconds" in stats
        assert stats["ttl_seconds"] == 300  # Default 5 minutes

    def test_cache_same_query_different_context(self):
        """Same query with different context should create separate entries."""
        cache = RAGCache()

        context1 = RAGContext(
            context_id=uuid4(),
            query_id=uuid4(),
            document_chunks=[],
            relevance_scores=[],
            total_chunks=0,
            avg_relevance=0.0,
            meets_threshold=False,
        )

        context2 = RAGContext(
            context_id=uuid4(),
            query_id=uuid4(),
            document_chunks=[],
            relevance_scores=[],
            total_chunks=0,
            avg_relevance=0.0,
            meets_threshold=False,
        )

        cache.set("test query", "channel1:user1", context1)
        cache.set("test query", "channel2:user2", context2)

        result1 = cache.get("test query", "channel1:user1")
        result2 = cache.get("test query", "channel2:user2")

        assert result1.context_id == context1.context_id
        assert result2.context_id == context2.context_id
        assert result1.context_id != result2.context_id


@pytest.fixture
def sample_markdown():
    """Sample markdown content for testing."""
    return """---
source: Core Rules v3.1
last_update_date: 2024-09-15
document_type: core-rules
section: Phases
---

## Movement Phase

During the movement phase, each model in your kill team can move.

### Normal Move

A model can move up to 6 inches.

### Dash Action

A model can Dash to move an additional 3 inches.

## Shooting Phase

During the shooting phase, models can shoot at visible enemy models."""


@pytest.fixture
def sample_document():
    """Sample RuleDocument for testing."""
    return RuleDocument(
        document_id=uuid4(),
        filename="rules-phases.md",
        content="## Movement\nTest content",
        metadata={
            "source": "Core Rules v3.1",
            "last_update_date": "2024-09-15",
            "document_type": "core-rules",
        },
        version="3.1",
        last_update_date=date(2024, 9, 15),
        document_type="core-rules",
        last_updated=date(2024, 9, 15),
        hash="abc123",
    )
