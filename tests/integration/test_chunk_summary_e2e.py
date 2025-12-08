"""End-to-end tests for chunk summary feature.

Tests the full flow: ingestion → summary generation → storage → retrieval
Uses real OpenAI API for authentic behavior testing.
"""

import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from src.models.rag_request import RetrieveRequest
from src.models.rule_document import RuleDocument
from src.services.rag.ingestor import RAGIngestor
from src.services.rag.retriever import RAGRetriever
from src.services.rag.validator import DocumentValidator


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

    # Create a test rule document with varied content
    rules_file = Path(temp_dir) / "test-summaries.md"
    rules_file.write_text(
        """---
source: Test Rules - Summaries
last_update_date: 2024-01-01
document_type: core-rules
section: Test
---

## Movement Phase

During the Movement phase, operatives can perform Move actions up to their Movement characteristic in inches. They can also Dash to gain additional movement or Climb/Traverse to navigate terrain.

## Shooting Phase

In the Shooting phase, operatives can perform Shoot actions to attack enemy operatives. They must have line of sight to the target and be within range of their weapon.

## Overwatch

Overwatch is a powerful action that allows an operative to interrupt enemy movement. When an enemy operative performs a Move, Charge, or Fall Back action within your operative's line of sight, you can use Overwatch to shoot at them.
"""
    )

    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.llm_api
@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.embedding
def test_chunk_summary_ingestion_to_retrieval_e2e(temp_chroma_db, temp_rules_dir):
    """E2E test: Ingest with summaries → verify storage → test retrieval quality.

    This test validates the complete chunk summary pipeline:
    1. Document ingestion generates summaries via OpenAI
    2. Summaries are stored in ChromaDB metadata
    3. Summaries improve retrieval quality for semantic and keyword searches
    4. Cost tracking reports non-zero summary costs
    """
    # Step 1: Ingest document with summary generation enabled
    ingestor = RAGIngestor(db_path=temp_chroma_db)

    rules_file = Path(temp_rules_dir) / "test-summaries.md"
    content = rules_file.read_text()

    # Validate and extract metadata
    validator = DocumentValidator()
    is_valid, error, metadata = validator.validate_content(content, "test-summaries.md")
    assert is_valid, f"Document validation failed: {error}"

    doc = RuleDocument.from_markdown_file(
        filename="test-summaries.md", content=content, metadata=metadata
    )

    # Ingest with summary generation (SUMMARY_ENABLED should be True)
    result = ingestor.ingest([doc])

    # Verify basic ingestion succeeded
    assert result.documents_processed == 1
    assert result.embedding_count > 0

    # Verify summary cost tracking
    assert result.summary_cost_usd is not None
    # Should have non-zero cost since we made real OpenAI calls
    assert result.summary_cost_usd > 0, "Summary generation should incur costs"

    # Step 2: Verify summaries stored in ChromaDB
    # Retrieve some chunks and check metadata contains summaries
    retriever = RAGRetriever(db_path=temp_chroma_db, enable_multi_hop=False)

    # Query for movement content
    request = RetrieveRequest(
        query="How does movement work?",
        context_key="test:summary_check",
        max_chunks=5
    )

    context, _, _, _ = retriever.retrieve(request, query_id=uuid4())

    # Should find relevant chunks
    assert context.total_chunks > 0, "Should retrieve chunks about movement"

    # Check that at least one chunk has a summary in metadata
    chunks_with_summaries = [
        chunk for chunk in context.document_chunks
        if chunk.metadata.get("summary")
    ]
    assert len(chunks_with_summaries) > 0, "Retrieved chunks should have summaries in metadata"

    # Verify summary is not empty and is concise
    for chunk in chunks_with_summaries:
        summary = chunk.metadata.get("summary", "")
        assert len(summary) > 0, "Summary should not be empty"
        # Summaries should be concise (rough heuristic: shorter than the full text)
        assert len(summary) < len(chunk.text), "Summary should be shorter than full text"
        print(f"✓ Chunk summary: {summary[:100]}...")

    # Step 3: Test retrieval quality with summaries
    # Query using informal terminology that might appear in summaries
    request2 = RetrieveRequest(
        query="Can I interrupt enemy movement?",
        context_key="test:overwatch_query",
        max_chunks=3
    )

    context2, _, _, _ = retriever.retrieve(request2, query_id=uuid4())

    # Should find Overwatch content (summaries help with semantic understanding)
    assert context2.total_chunks > 0
    chunk_texts = [chunk.text.lower() for chunk in context2.document_chunks]
    assert any("overwatch" in text for text in chunk_texts), (
        "Should retrieve Overwatch chunk for interrupt query"
    )

    print("✅ E2E test passed:")
    print(f"  - Ingested {result.embedding_count} chunks")
    print(f"  - Summary cost: ${result.summary_cost_usd:.4f}")
    print(f"  - Retrieved {context2.total_chunks} relevant chunks")

    # Verify result has summary_cost_usd field
    assert hasattr(result, "summary_cost_usd"), "IngestionResult must have summary_cost_usd field"
    assert result.summary_cost_usd is not None, "summary_cost_usd should not be None"
    assert isinstance(result.summary_cost_usd, (int, float)), "summary_cost_usd should be numeric"
    assert result.summary_cost_usd >= 0.0, "summary_cost_usd cannot be negative"
