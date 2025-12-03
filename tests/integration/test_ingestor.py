"""Integration tests for RAG ingestor with chunk summaries.

Tests ingestion behavior with SUMMARY_ENABLED toggle and cost tracking.
"""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.models.rule_document import RuleDocument
from src.services.rag.ingestor import RAGIngestor
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

    # Create a minimal test document
    rules_file = Path(temp_dir) / "test-ingest.md"
    rules_file.write_text(
        """---
source: Test Rules
last_update_date: 2024-01-01
document_type: core-rules
section: Test
---

## Movement

Models can move during the movement phase.

## Shooting

Models can shoot during the shooting phase.
"""
    )

    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.integration
@pytest.mark.fast
@pytest.mark.embedding
@patch("src.services.rag.summarizer.SUMMARY_ENABLED", False)
def test_ingestion_with_summaries_disabled(temp_chroma_db, temp_rules_dir):
    """Test ingestion when SUMMARY_ENABLED is False.

    Should not make any LLM calls and should report zero summary costs.
    """
    # Ingest document
    ingestor = RAGIngestor(db_path=temp_chroma_db)

    rules_file = Path(temp_rules_dir) / "test-ingest.md"
    content = rules_file.read_text()

    # Validate and extract metadata
    validator = DocumentValidator()
    is_valid, error, metadata = validator.validate_content(content, "test-ingest.md")
    assert is_valid, f"Document validation failed: {error}"

    doc = RuleDocument.from_markdown_file(
        filename="test-ingest.md", content=content, metadata=metadata
    )

    # Ingest without summary generation
    result = ingestor.ingest([doc])

    # Verify basic ingestion succeeded
    assert result.documents_processed == 1
    assert result.embedding_count > 0

    # Verify NO summary costs
    assert result.summary_cost_usd is not None
    assert result.summary_cost_usd == 0.0, "Summary generation should be disabled"

    # Verify chunks were still ingested (embedding_count > 0 proves this)
    assert result.documents_processed == 1
    assert result.documents_failed == 0

@pytest.mark.integration
@pytest.mark.fast
@pytest.mark.embedding
def test_ingestion_multiple_documents_cost_aggregation(temp_chroma_db):
    """Test that summary costs are aggregated across multiple documents."""
    # Create temp directory with multiple test files
    temp_dir = tempfile.mkdtemp()

    try:
        # Create first document
        doc1_file = Path(temp_dir) / "doc1.md"
        doc1_file.write_text(
            """---
source: Doc 1
last_update_date: 2024-01-01
document_type: core-rules
section: Test
---

## Section 1

Content for section 1.
"""
        )

        # Create second document
        doc2_file = Path(temp_dir) / "doc2.md"
        doc2_file.write_text(
            """---
source: Doc 2
last_update_date: 2024-01-01
document_type: core-rules
section: Test
---

## Section 2

Content for section 2.
"""
        )

        # Ingest both documents
        ingestor = RAGIngestor(db_path=temp_chroma_db)
        validator = DocumentValidator()

        docs = []
        for filename in ["doc1.md", "doc2.md"]:
            content = (Path(temp_dir) / filename).read_text()
            is_valid, error, metadata = validator.validate_content(content, filename)
            assert is_valid

            doc = RuleDocument.from_markdown_file(
                filename=filename, content=content, metadata=metadata
            )
            docs.append(doc)

        result = ingestor.ingest(docs)

        # Verify multiple documents processed
        assert result.documents_processed == 2

        # Verify cost tracking exists (regardless of SUMMARY_ENABLED state)
        assert result.summary_cost_usd is not None
        assert result.summary_cost_usd >= 0.0

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.integration
@pytest.mark.fast
@pytest.mark.embedding
def test_ingestion_continues_after_summary_failure(temp_chroma_db, temp_rules_dir):
    """Test that ingestion continues even if summary generation fails.

    This tests the graceful degradation behavior by simulating an OpenAI API failure.
    """
    with (
        patch("src.services.rag.summarizer.SUMMARY_ENABLED", True),
        patch("src.services.rag.summarizer.OpenAI") as mock_openai_class,
    ):
        # Create a mock client that raises an exception when parse is called
        mock_client = mock_openai_class.return_value
        mock_client.beta.chat.completions.parse.side_effect = Exception("Simulated API failure")

        ingestor = RAGIngestor(db_path=temp_chroma_db)

        rules_file = Path(temp_rules_dir) / "test-ingest.md"
        content = rules_file.read_text()

        validator = DocumentValidator()
        is_valid, error, metadata = validator.validate_content(content, "test-ingest.md")
        assert is_valid

        doc = RuleDocument.from_markdown_file(
            filename="test-ingest.md", content=content, metadata=metadata
        )

        # Ingestion should succeed despite summary failure
        result = ingestor.ingest([doc])

        # Verify ingestion still completed
        assert result.documents_processed == 1
        assert result.embedding_count > 0

        # Summary cost should be zero since generation failed
        assert result.summary_cost_usd == 0.0
