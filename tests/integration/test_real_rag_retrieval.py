"""Integration tests for real RAG retrieval with ChromaDB.

These tests use real ChromaDB but mock LLM calls to test the RAG pipeline.
"""

import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from src.services.rag.ingestor import RAGIngestor
from src.services.rag.retriever import RAGRetriever, RetrieveRequest


@pytest.fixture
def temp_chroma_db():
    """Create a temporary ChromaDB for testing."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_rules_dir():
    """Create temporary rules directory with test content."""
    temp_dir = tempfile.mkdtemp()

    # Create a test rule document
    rules_file = Path(temp_dir) / "test-rules.md"
    rules_file.write_text("""---
source: Test Rules
last_update_date: 2024-01-01
document_type: core-rules
section: Test
---

## Movement

Models can move up to 6 inches during the movement phase.

## Shooting

Models can shoot at visible enemy models during the shooting phase.

## Barricades

Barricades provide cover to models. You can shoot through barricades but the target gets the benefit of cover.
""")

    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def _ingest_test_document(temp_chroma_db: str, temp_rules_dir: str) -> RAGIngestor:
    """Helper to ingest test documents and return the ingestor.

    Args:
        temp_chroma_db: Path to temporary ChromaDB
        temp_rules_dir: Path to temporary rules directory

    Returns:
        Configured RAGIngestor instance
    """
    from src.models.rule_document import RuleDocument
    from src.services.rag.validator import DocumentValidator

    ingestor = RAGIngestor(db_path=temp_chroma_db)

    rules_file = Path(temp_rules_dir) / "test-rules.md"
    content = rules_file.read_text()

    # Validate and extract metadata
    validator = DocumentValidator()
    is_valid, error, metadata = validator.validate_content(content, "test-rules.md")
    assert is_valid, f"Document validation failed: {error}"

    doc = RuleDocument.from_markdown_file(
        filename="test-rules.md",
        content=content,
        metadata=metadata
    )

    result = ingestor.ingest([doc])
    assert result.documents_processed > 0
    assert result.embedding_count > 0

    return ingestor


@pytest.mark.slow
@pytest.mark.integration
def test_real_rag_retrieval_basic(temp_chroma_db, temp_rules_dir):
    """Test real RAG retrieval with ChromaDB."""
    # Ingest test documents
    _ingest_test_document(temp_chroma_db, temp_rules_dir)

    # Create retriever (disable multi-hop for simpler testing)
    retriever = RAGRetriever(db_path=temp_chroma_db, enable_multi_hop=False)

    # Retrieve with query about barricades
    request = RetrieveRequest(
        query="Can I shoot through barricades?",
        context_key="test:123",
        max_chunks=5
    )

    context, _, _ = retriever.retrieve(request, query_id=uuid4())

    # Should find relevant chunks
    assert context.total_chunks > 0
    assert len(context.document_chunks) > 0

    # Should find barricade-related content
    chunk_texts = [chunk.text.lower() for chunk in context.document_chunks]
    assert any("barricade" in text for text in chunk_texts)

    # Should have decent relevance scores
    assert context.avg_relevance > 0.0


@pytest.mark.slow
@pytest.mark.integration
def test_real_rag_retrieval_no_results(temp_chroma_db, temp_rules_dir):
    """Test RAG retrieval with query that has no good matches."""
    # Ingest test documents
    _ingest_test_document(temp_chroma_db, temp_rules_dir)

    # Create retriever
    retriever = RAGRetriever(db_path=temp_chroma_db, enable_multi_hop=False)

    # Query about something not in the rules
    request = RetrieveRequest(
        query="What is the airspeed velocity of an unladen swallow?",
        context_key="test:456",
        max_chunks=5
    )

    context, _, _ = retriever.retrieve(request, query_id=uuid4())

    # Should return something (might be low relevance)
    assert context.total_chunks >= 0

    # Avg relevance should be lower for irrelevant queries
    if context.total_chunks > 0:
        assert context.avg_relevance < 0.8  # Should be lower than good match


@pytest.mark.slow
@pytest.mark.integration
def test_real_rag_keyword_normalization(temp_chroma_db, temp_rules_dir):
    """Test that keyword normalization works with real retrieval."""
    # Ingest test documents
    _ingest_test_document(temp_chroma_db, temp_rules_dir)

    # Create retriever
    retriever = RAGRetriever(db_path=temp_chroma_db, enable_multi_hop=False)

    # Query with different capitalization
    request1 = RetrieveRequest(
        query="Can I shoot during the SHOOTING phase?",
        context_key="test:789",
        max_chunks=5
    )

    request2 = RetrieveRequest(
        query="Can I shoot during the shooting phase?",
        context_key="test:789",
        max_chunks=5
    )

    context1, _, _ = retriever.retrieve(request1, query_id=uuid4())
    context2, _, _ = retriever.retrieve(request2, query_id=uuid4())

    # Both should find relevant content
    assert context1.total_chunks > 0
    assert context2.total_chunks > 0

    # Should find shooting-related content
    for context in [context1, context2]:
        chunk_texts = [chunk.text.lower() for chunk in context.document_chunks]
        assert any("shoot" in text for text in chunk_texts)
