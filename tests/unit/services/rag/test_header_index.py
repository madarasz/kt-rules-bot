"""Unit tests for HeaderIndex fuzzy header lookup."""

from uuid import uuid4

import pytest

from src.models.rag_context import DocumentChunk
from src.services.rag.header_index import HeaderIndex


@pytest.fixture
def sample_chunks():
    """Create sample DocumentChunk objects for testing."""
    return [
        DocumentChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            text="## COUNTERACT\nSome content about counteract.",
            header="COUNTERACT",
            header_level=2,
            metadata={"source": "core-rules.md", "doc_type": "core-rules", "publication_date": "2024-01-01"},
            relevance_score=0.9,
            position_in_doc=1,
        ),
        DocumentChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            text="## FIREFIGHT PHASE - WHEN A FRIENDLY OPERATIVE IS ACTIVATED\nActivation rules.",
            header="FIREFIGHT PHASE - WHEN A FRIENDLY OPERATIVE IS ACTIVATED",
            header_level=2,
            metadata={"source": "core-rules.md", "doc_type": "core-rules", "publication_date": "2024-01-01"},
            relevance_score=0.85,
            position_in_doc=2,
        ),
        DocumentChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            text="## Movement: Minimum move stat\nMovement rules.",
            header="Movement: Minimum move stat",
            header_level=2,
            metadata={"source": "core-rules.md", "doc_type": "core-rules", "publication_date": "2024-01-01"},
            relevance_score=0.8,
            position_in_doc=3,
        ),
    ]


class TestHeaderIndexBuild:
    """Tests for HeaderIndex.build_from_chunks()."""

    def test_build_from_chunks_creates_index(self, sample_chunks):
        """Build creates searchable index from chunks."""
        index = HeaderIndex()
        index.build_from_chunks(sample_chunks)

        assert index.header_count == 3
        assert index._built is True

    def test_build_from_empty_chunks(self):
        """Build with empty list creates empty index."""
        index = HeaderIndex()
        index.build_from_chunks([])

        assert index.header_count == 0
        assert index._built is True

    def test_build_handles_duplicate_headers(self, sample_chunks):
        """Build keeps first occurrence when duplicate headers exist."""
        # Create duplicate
        chunk_with_same_header = DocumentChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            text="## COUNTERACT\nDifferent content.",
            header="COUNTERACT",
            header_level=2,
            metadata={"source": "faq.md", "doc_type": "faq", "publication_date": "2024-01-01"},
            relevance_score=0.7,
            position_in_doc=1,
        )
        chunks_with_dup = sample_chunks + [chunk_with_same_header]

        index = HeaderIndex()
        index.build_from_chunks(chunks_with_dup)

        # Should only have 3 unique headers (COUNTERACT counted once)
        assert index.header_count == 3

    def test_build_ignores_empty_headers(self, sample_chunks):
        """Build ignores chunks with empty headers."""
        chunk_no_header = DocumentChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            text="Some content without header.",
            header="",
            header_level=2,
            metadata={"source": "misc.md", "doc_type": "core-rules", "publication_date": "2024-01-01"},
            relevance_score=0.5,
            position_in_doc=1,
        )
        chunks_with_empty = sample_chunks + [chunk_no_header]

        index = HeaderIndex()
        index.build_from_chunks(chunks_with_empty)

        assert index.header_count == 3


class TestHeaderIndexFuzzySearch:
    """Tests for HeaderIndex.fuzzy_search()."""

    def test_exact_match_returns_chunk(self, sample_chunks):
        """Exact header match returns correct chunk with score 1.0."""
        index = HeaderIndex()
        index.build_from_chunks(sample_chunks)

        chunk, score = index.fuzzy_search("COUNTERACT")

        assert chunk is not None
        assert chunk.header == "COUNTERACT"
        assert score == 1.0

    def test_case_insensitive_match(self, sample_chunks):
        """Search is case-insensitive."""
        index = HeaderIndex()
        index.build_from_chunks(sample_chunks)

        chunk, score = index.fuzzy_search("counteract")

        assert chunk is not None
        assert chunk.header == "COUNTERACT"
        assert score == 1.0

    def test_fuzzy_match_with_typo(self, sample_chunks):
        """Fuzzy matching finds headers with minor typos."""
        index = HeaderIndex()
        index.build_from_chunks(sample_chunks)

        # "COUNTERCT" is missing one letter - should still match at high threshold
        chunk, score = index.fuzzy_search("COUNTERCT", threshold=0.8)

        assert chunk is not None
        assert chunk.header == "COUNTERACT"
        assert score >= 0.8

    def test_threshold_filters_low_matches(self, sample_chunks):
        """Matches below threshold return None."""
        index = HeaderIndex()
        index.build_from_chunks(sample_chunks)

        # Very different query should not match at 85% threshold
        chunk, score = index.fuzzy_search("XYZ123", threshold=0.85)

        assert chunk is None
        assert score == 0.0

    def test_long_header_fuzzy_match(self, sample_chunks):
        """Fuzzy matching works on long headers."""
        index = HeaderIndex()
        index.build_from_chunks(sample_chunks)

        # Partial match of long header
        chunk, score = index.fuzzy_search(
            "FIREFIGHT PHASE - WHEN A FRIENDLY OPERATIVE IS ACTIVATED",
            threshold=0.85
        )

        assert chunk is not None
        assert "FIREFIGHT" in chunk.header
        assert score >= 0.85

    def test_empty_query_returns_none(self, sample_chunks):
        """Empty query returns None."""
        index = HeaderIndex()
        index.build_from_chunks(sample_chunks)

        chunk, score = index.fuzzy_search("")

        assert chunk is None
        assert score == 0.0

    def test_whitespace_only_query_returns_none(self, sample_chunks):
        """Whitespace-only query returns None."""
        index = HeaderIndex()
        index.build_from_chunks(sample_chunks)

        chunk, score = index.fuzzy_search("   ")

        assert chunk is None
        assert score == 0.0

    def test_search_before_build_returns_none(self):
        """Search before building index returns None with warning."""
        index = HeaderIndex()

        chunk, score = index.fuzzy_search("COUNTERACT")

        assert chunk is None
        assert score == 0.0

    def test_best_match_returned_when_multiple_candidates(self, sample_chunks):
        """When multiple headers match, best one is returned."""
        index = HeaderIndex()
        index.build_from_chunks(sample_chunks)

        # "Movement" should match "Movement: Minimum move stat" better than others
        chunk, score = index.fuzzy_search("Movement: Minimum move stat", threshold=0.5)

        assert chunk is not None
        assert "Movement" in chunk.header


class TestCleanMissingQuery:
    """Tests for MultiHopRetriever._clean_missing_query()."""

    def test_simple_comma_separated(self):
        """Simple comma-separated titles are parsed correctly."""

        from src.services.rag.multi_hop_retriever import MultiHopRetriever

        retriever = MultiHopRetriever.__new__(MultiHopRetriever)

        result = retriever._clean_missing_query("Title A, Title B, Title C")

        assert result == ["Title A", "Title B", "Title C"]

    def test_removes_apostrophes(self):
        """Apostrophe-wrapped titles have apostrophes removed."""
        from src.services.rag.multi_hop_retriever import MultiHopRetriever

        retriever = MultiHopRetriever.__new__(MultiHopRetriever)

        result = retriever._clean_missing_query("'Title A', 'Title B'")

        assert result == ["Title A", "Title B"]

    def test_preserves_hyphens_in_titles(self):
        """Hyphens within titles are preserved (not treated as delimiters)."""
        from src.services.rag.multi_hop_retriever import MultiHopRetriever

        retriever = MultiHopRetriever.__new__(MultiHopRetriever)

        result = retriever._clean_missing_query(
            "FIREFIGHT PHASE - WHEN A FRIENDLY OPERATIVE IS ACTIVATED, COUNTERACT"
        )

        assert result == [
            "FIREFIGHT PHASE - WHEN A FRIENDLY OPERATIVE IS ACTIVATED",
            "COUNTERACT"
        ]

    def test_strips_whitespace(self):
        """Whitespace around titles is stripped."""
        from src.services.rag.multi_hop_retriever import MultiHopRetriever

        retriever = MultiHopRetriever.__new__(MultiHopRetriever)

        result = retriever._clean_missing_query("  Title A  ,  Title B  ")

        assert result == ["Title A", "Title B"]

    def test_ignores_empty_parts(self):
        """Empty parts from consecutive commas are ignored."""
        from src.services.rag.multi_hop_retriever import MultiHopRetriever

        retriever = MultiHopRetriever.__new__(MultiHopRetriever)

        result = retriever._clean_missing_query("Title A,, Title B,")

        assert result == ["Title A", "Title B"]
