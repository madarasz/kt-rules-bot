"""Integration tests for real RAG retrieval with ChromaDB.

These tests use real ChromaDB but mock LLM calls to test the RAG pipeline.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from uuid import uuid4

from src.services.rag.multi_hop_retriever import MultiHopRetriever
from src.services.rag.ingestor import RAGIngestor
from src.services.rag.retriever import RetrieveRequest


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


@pytest.mark.slow
@pytest.mark.integration
def test_real_rag_retrieval_basic(temp_chroma_db, temp_rules_dir):
    """Test real RAG retrieval with ChromaDB."""
    # Ingest test documents
    ingestor = RAGIngestor(db_path=temp_chroma_db)
    stats = ingestor.ingest_directory(temp_rules_dir)

    assert stats["files_processed"] > 0
    assert stats["chunks_created"] > 0

    # Create retriever
    retriever = MultiHopRetriever(db_path=temp_chroma_db)

    # Retrieve with query about barricades
    request = RetrieveRequest(
        query_id=uuid4(),
        query_text="Can I shoot through barricades?",
        conversation_context_id="test:123",
        top_k=5
    )

    context = retriever.retrieve(request)

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
    ingestor = RAGIngestor(db_path=temp_chroma_db)
    ingestor.ingest_directory(temp_rules_dir)

    # Create retriever
    retriever = MultiHopRetriever(db_path=temp_chroma_db)

    # Query about something not in the rules
    request = RetrieveRequest(
        query_id=uuid4(),
        query_text="What is the airspeed velocity of an unladen swallow?",
        conversation_context_id="test:456",
        top_k=5
    )

    context = retriever.retrieve(request)

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
    ingestor = RAGIngestor(db_path=temp_chroma_db)
    ingestor.ingest_directory(temp_rules_dir)

    # Create retriever
    retriever = MultiHopRetriever(db_path=temp_chroma_db)

    # Query with different capitalization
    request1 = RetrieveRequest(
        query_id=uuid4(),
        query_text="Can I shoot during the SHOOTING phase?",
        conversation_context_id="test:789",
        top_k=5
    )

    request2 = RetrieveRequest(
        query_id=uuid4(),
        query_text="Can I shoot during the shooting phase?",
        conversation_context_id="test:789",
        top_k=5
    )

    context1 = retriever.retrieve(request1)
    context2 = retriever.retrieve(request2)

    # Both should find relevant content
    assert context1.total_chunks > 0
    assert context2.total_chunks > 0

    # Should find shooting-related content
    for context in [context1, context2]:
        chunk_texts = [chunk.text.lower() for chunk in context.document_chunks]
        assert any("shoot" in text for text in chunk_texts)
