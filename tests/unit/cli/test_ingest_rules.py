"""Unit tests for ingest_rules.py CLI command."""

from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

import pytest

from src.cli.ingest_rules import find_markdown_files, ingest_rules


class TestFindMarkdownFiles:
    """Tests for find_markdown_files function."""

    @patch('src.cli.ingest_rules.Path')
    def test_finds_markdown_files(self, mock_path):
        """Test finding markdown files in directory."""
        mock_dir = Mock()
        mock_dir.exists.return_value = True
        mock_dir.rglob.return_value = [
            Path("rules/file1.md"),
            Path("rules/subfolder/file2.md"),
        ]
        mock_path.return_value = mock_dir

        result = find_markdown_files(mock_dir)

        assert len(result) == 2

    @patch('src.cli.ingest_rules.Path')
    def test_raises_error_if_directory_not_found(self, mock_path):
        """Test that error is raised if directory doesn't exist."""
        mock_dir = Mock()
        mock_dir.exists.return_value = False
        mock_path.return_value = mock_dir

        with pytest.raises(FileNotFoundError):
            find_markdown_files(mock_dir)

    @patch('src.cli.ingest_rules.Path')
    def test_returns_sorted_files(self, mock_path):
        """Test that files are returned sorted."""
        mock_dir = Mock()
        mock_dir.exists.return_value = True
        mock_dir.rglob.return_value = [
            Path("rules/zebra.md"),
            Path("rules/alpha.md"),
            Path("rules/beta.md"),
        ]
        mock_path.return_value = mock_dir

        result = find_markdown_files(mock_dir)

        # Should be sorted
        assert str(result[0]) == "rules/alpha.md"
        assert str(result[1]) == "rules/beta.md"
        assert str(result[2]) == "rules/zebra.md"


class TestIngestRules:
    """Tests for ingest_rules function."""

    @patch('src.cli.ingest_rules.get_config')
    @patch('src.cli.ingest_rules.find_markdown_files')
    @patch('src.cli.ingest_rules.VectorDBService')
    @patch('src.cli.ingest_rules.EmbeddingService')
    @patch('src.cli.ingest_rules.RAGIngestor')
    @patch('src.cli.ingest_rules.DocumentValidator')
    def test_successful_ingestion(
        self,
        mock_validator_class,
        mock_ingestor_class,
        mock_embedding_class,
        mock_vectordb_class,
        mock_find_files,
        mock_config
    ):
        """Test successful rule ingestion."""
        # Mock configuration
        mock_config.return_value = Mock()

        # Mock file finding
        mock_file = Mock()
        mock_file.read_text.return_value = """---
source: "Test"
last_update_date: 2024-01-01
document_type: core-rules
---

## Test Rule

Content here.
"""
        mock_file.name = "test.md"
        mock_file.relative_to.return_value = Path("test.md")
        mock_find_files.return_value = [mock_file]

        # Mock validator
        mock_validator = Mock()
        mock_validator.validate_content.return_value = (
            True,
            None,
            {"source": "Test", "document_type": "core-rules"}
        )
        mock_validator_class.return_value = mock_validator

        # Mock ingestor
        mock_ingestor = Mock()
        mock_ingestor.document_hashes = {}
        mock_result = Mock()
        mock_result.documents_processed = 1
        mock_result.embedding_count = 5
        mock_ingestor.ingest.return_value = mock_result
        mock_ingestor_class.return_value = mock_ingestor

        # Mock services
        mock_vectordb_class.return_value = Mock()
        mock_embedding_class.return_value = Mock()

        # Should not raise
        ingest_rules(source_dir="./rules", force=False)

    @patch('src.cli.ingest_rules.get_config')
    @patch('src.cli.ingest_rules.find_markdown_files')
    def test_handles_no_markdown_files(self, mock_find_files, mock_config):
        """Test handling when no markdown files found."""
        mock_config.return_value = Mock()
        mock_find_files.return_value = []

        # Should not raise, just print warning
        ingest_rules(source_dir="./rules")

    @patch('src.cli.ingest_rules.get_config')
    @patch('src.cli.ingest_rules.find_markdown_files')
    @patch('src.cli.ingest_rules.VectorDBService')
    def test_handles_service_initialization_failure(
        self,
        mock_vectordb_class,
        mock_find_files,
        mock_config
    ):
        """Test handling of service initialization failure."""
        mock_config.return_value = Mock()
        mock_find_files.return_value = [Mock()]
        mock_vectordb_class.side_effect = Exception("Service init failed")

        with pytest.raises(SystemExit):
            ingest_rules(source_dir="./rules")

    @patch('src.cli.ingest_rules.get_config')
    @patch('src.cli.ingest_rules.find_markdown_files')
    @patch('src.cli.ingest_rules.VectorDBService')
    @patch('src.cli.ingest_rules.EmbeddingService')
    @patch('src.cli.ingest_rules.RAGIngestor')
    @patch('src.cli.ingest_rules.DocumentValidator')
    def test_validates_documents(
        self,
        mock_validator_class,
        mock_ingestor_class,
        mock_embedding_class,
        mock_vectordb_class,
        mock_find_files,
        mock_config
    ):
        """Test that documents are validated before ingestion."""
        mock_config.return_value = Mock()

        # Mock file
        mock_file = Mock()
        mock_file.read_text.return_value = "Invalid content"
        mock_file.name = "test.md"
        mock_file.relative_to.return_value = Path("test.md")
        mock_find_files.return_value = [mock_file]

        # Mock validator - validation fails
        mock_validator = Mock()
        mock_validator.validate_content.return_value = (
            False,
            "Missing frontmatter",
            {}
        )
        mock_validator_class.return_value = mock_validator

        # Mock services
        mock_vectordb_class.return_value = Mock()
        mock_embedding_class.return_value = Mock()
        mock_ingestor = Mock()
        mock_ingestor.document_hashes = {}
        mock_ingestor_class.return_value = mock_ingestor

        # Should not raise, but should skip invalid document
        ingest_rules(source_dir="./rules")

        # Ingestor should not be called for invalid document
        assert not mock_ingestor.ingest.called

    @patch('src.cli.ingest_rules.get_config')
    @patch('src.cli.ingest_rules.find_markdown_files')
    @patch('src.cli.ingest_rules.VectorDBService')
    @patch('src.cli.ingest_rules.EmbeddingService')
    @patch('src.cli.ingest_rules.RAGIngestor')
    @patch('src.cli.ingest_rules.DocumentValidator')
    def test_skips_unchanged_documents(
        self,
        mock_validator_class,
        mock_ingestor_class,
        mock_embedding_class,
        mock_vectordb_class,
        mock_find_files,
        mock_config
    ):
        """Test that unchanged documents are skipped unless force=True."""
        mock_config.return_value = Mock()

        # Mock file
        mock_file = Mock()
        mock_file.read_text.return_value = """---
source: "Test"
last_update_date: 2024-01-01
document_type: core-rules
---

## Test
"""
        mock_file.name = "test.md"
        mock_file.relative_to.return_value = Path("test.md")
        mock_find_files.return_value = [mock_file]

        # Mock validator
        mock_validator = Mock()
        mock_validator.validate_content.return_value = (
            True,
            None,
            {"source": "Test", "document_type": "core-rules"}
        )
        mock_validator_class.return_value = mock_validator

        # Mock ingestor with existing hash
        mock_ingestor = Mock()
        mock_ingestor.document_hashes = {"test.md": "existing_hash"}
        mock_ingestor_class.return_value = mock_ingestor

        # Mock services
        mock_vectordb_class.return_value = Mock()
        mock_embedding_class.return_value = Mock()

        with patch('src.models.rule_document.RuleDocument.compute_hash', return_value="existing_hash"):
            ingest_rules(source_dir="./rules", force=False)

        # Should skip unchanged document
        assert not mock_ingestor.ingest.called

    @patch('src.cli.ingest_rules.get_config')
    @patch('src.cli.ingest_rules.find_markdown_files')
    @patch('src.cli.ingest_rules.VectorDBService')
    @patch('src.cli.ingest_rules.EmbeddingService')
    @patch('src.cli.ingest_rules.RAGIngestor')
    @patch('src.cli.ingest_rules.DocumentValidator')
    def test_force_flag_reingest_all(
        self,
        mock_validator_class,
        mock_ingestor_class,
        mock_embedding_class,
        mock_vectordb_class,
        mock_find_files,
        mock_config
    ):
        """Test that force flag causes re-ingestion of all documents."""
        mock_config.return_value = Mock()

        # Mock file
        mock_file = Mock()
        mock_file.read_text.return_value = """---
source: "Test"
last_update_date: 2024-01-01
document_type: core-rules
---

## Test
"""
        mock_file.name = "test.md"
        mock_file.relative_to.return_value = Path("test.md")
        mock_find_files.return_value = [mock_file]

        # Mock validator
        mock_validator = Mock()
        mock_validator.validate_content.return_value = (
            True,
            None,
            {"source": "Test", "document_type": "core-rules"}
        )
        mock_validator_class.return_value = mock_validator

        # Mock ingestor
        mock_ingestor = Mock()
        mock_ingestor.document_hashes = {"test.md": "existing_hash"}
        mock_result = Mock()
        mock_result.documents_processed = 1
        mock_result.embedding_count = 5
        mock_ingestor.ingest.return_value = mock_result
        mock_ingestor_class.return_value = mock_ingestor

        # Mock services
        mock_vectordb_class.return_value = Mock()
        mock_embedding_class.return_value = Mock()

        # Force re-ingestion
        ingest_rules(source_dir="./rules", force=True)

        # Should ingest even though hash exists
        assert mock_ingestor.ingest.called

    @patch('src.cli.ingest_rules.get_config')
    @patch('src.cli.ingest_rules.find_markdown_files')
    @patch('src.cli.ingest_rules.VectorDBService')
    @patch('src.cli.ingest_rules.EmbeddingService')
    @patch('src.cli.ingest_rules.RAGIngestor')
    @patch('src.cli.ingest_rules.DocumentValidator')
    def test_handles_file_processing_errors(
        self,
        mock_validator_class,
        mock_ingestor_class,
        mock_embedding_class,
        mock_vectordb_class,
        mock_find_files,
        mock_config
    ):
        """Test handling of errors during file processing."""
        mock_config.return_value = Mock()

        # Mock file that raises error when read
        mock_file = Mock()
        mock_file.read_text.side_effect = Exception("Read error")
        mock_file.name = "test.md"
        mock_find_files.return_value = [mock_file]

        # Mock services
        mock_vectordb_class.return_value = Mock()
        mock_embedding_class.return_value = Mock()
        mock_validator = Mock()
        mock_validator_class.return_value = mock_validator
        mock_ingestor = Mock()
        mock_ingestor.document_hashes = {}
        mock_ingestor_class.return_value = mock_ingestor

        # Should not raise, should continue processing
        ingest_rules(source_dir="./rules")
