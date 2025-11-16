"""Unit tests for RAGContext model."""

from datetime import date
from uuid import uuid4

import pytest

from src.models.rag_context import DocumentChunk, RAGContext


class TestDocumentChunk:
    """Test DocumentChunk model."""

    def test_validate_success(self):
        """Test successful chunk validation."""
        chunk = DocumentChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            text="You can move up to your Movement characteristic.",
            header="Movement Phase",
            header_level=2,
            metadata={
                "source": "Core Rules v3.1",
                "doc_type": "core-rules",
                "publication_date": "2024-10-01",
            },
            relevance_score=0.85,
            position_in_doc=1,
        )
        # Should not raise
        chunk.validate()

    def test_chunk_creation(self):
        """Test creating a document chunk."""
        chunk_id = uuid4()
        doc_id = uuid4()

        chunk = DocumentChunk(
            chunk_id=chunk_id,
            document_id=doc_id,
            text="Charge rules text",
            header="Charge Phase",
            header_level=3,
            metadata={
                "source": "FAQ",
                "doc_type": "faq",
                "publication_date": "2024-09-15",
            },
            relevance_score=0.92,
            position_in_doc=5,
        )

        assert chunk.chunk_id == chunk_id
        assert chunk.document_id == doc_id
        assert chunk.text == "Charge rules text"
        assert chunk.header == "Charge Phase"
        assert chunk.header_level == 3
        assert chunk.relevance_score == 0.92
        assert chunk.position_in_doc == 5


class TestRAGContext:
    """Test RAGContext model."""

    def _create_test_chunk(self, relevance_score: float) -> DocumentChunk:
        """Helper to create a test chunk with given relevance."""
        return DocumentChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            text=f"Test content with relevance {relevance_score}",
            header="Test Header",
            header_level=2,
            metadata={
                "source": "Test",
                "doc_type": "core-rules",
                "publication_date": "2024-10-01",
            },
            relevance_score=relevance_score,
            position_in_doc=1,
        )

    def test_validate_success(self):
        """Test successful RAGContext validation."""
        chunks = [
            self._create_test_chunk(0.9),
            self._create_test_chunk(0.8),
            self._create_test_chunk(0.7),
        ]

        context = RAGContext(
            context_id=uuid4(),
            query_id=uuid4(),
            document_chunks=chunks,
            relevance_scores=[0.9, 0.8, 0.7],
            total_chunks=3,
            avg_relevance=0.8,
            meets_threshold=True,
        )
        # Should not raise
        context.validate()

    def test_from_retrieval(self):
        """Test creating RAGContext from retrieval results."""
        query_id = uuid4()
        chunks = [
            self._create_test_chunk(0.9),
            self._create_test_chunk(0.8),
            self._create_test_chunk(0.7),
        ]

        context = RAGContext.from_retrieval(query_id, chunks)

        assert context.query_id == query_id
        assert context.document_chunks == chunks
        assert context.relevance_scores == [0.9, 0.8, 0.7]
        assert context.total_chunks == 3
        assert context.avg_relevance == pytest.approx((0.9 + 0.8 + 0.7) / 3)
        assert context.meets_threshold is True  # Above 0.45 threshold

    def test_from_retrieval_below_threshold(self):
        """Test creating RAGContext with low relevance scores."""
        query_id = uuid4()
        chunks = [
            self._create_test_chunk(0.3),
            self._create_test_chunk(0.2),
            self._create_test_chunk(0.1),
        ]

        context = RAGContext.from_retrieval(query_id, chunks)

        assert context.avg_relevance == pytest.approx((0.3 + 0.2 + 0.1) / 3)
        assert context.meets_threshold is False  # Below 0.45 threshold

    def test_from_retrieval_custom_threshold(self):
        """Test creating RAGContext with custom threshold."""
        query_id = uuid4()
        chunks = [
            self._create_test_chunk(0.5),
            self._create_test_chunk(0.4),
        ]

        # With default threshold (0.45), avg is 0.45, should meet threshold
        context = RAGContext.from_retrieval(query_id, chunks, min_relevance=0.45)
        assert context.meets_threshold is True

        # With higher threshold (0.6), should not meet
        context = RAGContext.from_retrieval(query_id, chunks, min_relevance=0.6)
        assert context.meets_threshold is False

    def test_empty(self):
        """Test creating empty RAGContext."""
        query_id = uuid4()

        context = RAGContext.empty(query_id)

        assert context.query_id == query_id
        assert context.document_chunks == []
        assert context.relevance_scores == []
        assert context.total_chunks == 0
        assert context.avg_relevance == 0.0
        assert context.meets_threshold is False

    def test_from_retrieval_single_chunk(self):
        """Test creating RAGContext with single chunk."""
        query_id = uuid4()
        chunks = [self._create_test_chunk(0.95)]

        context = RAGContext.from_retrieval(query_id, chunks)

        assert context.total_chunks == 1
        assert context.avg_relevance == 0.95
        assert context.meets_threshold is True

    def test_from_retrieval_many_chunks(self):
        """Test creating RAGContext with many chunks."""
        query_id = uuid4()
        chunks = [self._create_test_chunk(0.9 - i * 0.05) for i in range(10)]

        context = RAGContext.from_retrieval(query_id, chunks)

        assert context.total_chunks == 10
        assert len(context.document_chunks) == 10
        assert len(context.relevance_scores) == 10

    def test_avg_relevance_calculation(self):
        """Test that average relevance is calculated correctly."""
        query_id = uuid4()
        chunks = [
            self._create_test_chunk(1.0),
            self._create_test_chunk(0.8),
            self._create_test_chunk(0.6),
            self._create_test_chunk(0.4),
        ]

        context = RAGContext.from_retrieval(query_id, chunks)

        expected_avg = (1.0 + 0.8 + 0.6 + 0.4) / 4
        assert context.avg_relevance == pytest.approx(expected_avg)

    def test_threshold_boundary_conditions(self):
        """Test threshold at boundary conditions."""
        query_id = uuid4()

        # Exactly at threshold
        chunks = [self._create_test_chunk(0.45)]
        context = RAGContext.from_retrieval(query_id, chunks, min_relevance=0.45)
        assert context.meets_threshold is True

        # Just below threshold
        chunks = [self._create_test_chunk(0.44)]
        context = RAGContext.from_retrieval(query_id, chunks, min_relevance=0.45)
        assert context.meets_threshold is False

        # Just above threshold
        chunks = [self._create_test_chunk(0.46)]
        context = RAGContext.from_retrieval(query_id, chunks, min_relevance=0.45)
        assert context.meets_threshold is True

    def test_relevance_scores_match_chunks(self):
        """Test that relevance_scores list matches chunk scores."""
        query_id = uuid4()
        scores = [0.95, 0.85, 0.75, 0.65]
        chunks = [self._create_test_chunk(score) for score in scores]

        context = RAGContext.from_retrieval(query_id, chunks)

        assert context.relevance_scores == scores
        for i, chunk in enumerate(context.document_chunks):
            assert chunk.relevance_score == context.relevance_scores[i]

    def test_chunks_preserve_order(self):
        """Test that chunk order is preserved from retrieval."""
        query_id = uuid4()
        chunks = [
            self._create_test_chunk(0.9),
            self._create_test_chunk(0.8),
            self._create_test_chunk(0.7),
        ]

        context = RAGContext.from_retrieval(query_id, chunks)

        # Order should be preserved
        assert context.document_chunks[0].relevance_score == 0.9
        assert context.document_chunks[1].relevance_score == 0.8
        assert context.document_chunks[2].relevance_score == 0.7

    def test_empty_context_properties(self):
        """Test properties of empty context."""
        query_id = uuid4()
        context = RAGContext.empty(query_id)

        assert len(context.document_chunks) == 0
        assert len(context.relevance_scores) == 0
        assert context.total_chunks == 0
        assert context.avg_relevance == 0.0
        assert context.meets_threshold is False
        assert isinstance(context.context_id, type(uuid4()))
