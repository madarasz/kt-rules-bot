"""Unit tests for RuleDocument model."""

import hashlib
from datetime import date, datetime, timezone
from uuid import UUID

import pytest

from src.models.rule_document import RuleDocument


class TestRuleDocument:
    """Test RuleDocument model."""

    def test_compute_hash(self):
        """Test computing SHA-256 hash of content."""
        content = "# Rules\n\nSome rule content here."
        expected = hashlib.sha256(content.encode()).hexdigest()

        result = RuleDocument.compute_hash(content)

        assert result == expected
        assert len(result) == 64  # SHA-256 hex length

    def test_compute_hash_consistent(self):
        """Test that hash computation is consistent."""
        content = "Test content"

        hash1 = RuleDocument.compute_hash(content)
        hash2 = RuleDocument.compute_hash(content)

        assert hash1 == hash2

    def test_compute_hash_different_content(self):
        """Test that different content produces different hashes."""
        hash1 = RuleDocument.compute_hash("Content 1")
        hash2 = RuleDocument.compute_hash("Content 2")

        assert hash1 != hash2

    def test_validate_filename_valid(self):
        """Test validating valid filenames."""
        assert RuleDocument.validate_filename("rules-1-phases.md") is True
        assert RuleDocument.validate_filename("faq.md") is True
        assert RuleDocument.validate_filename("team-greenskins.md") is True

    def test_validate_filename_invalid(self):
        """Test validating invalid filenames."""
        assert RuleDocument.validate_filename("Rules.md") is False  # Capital letter
        assert RuleDocument.validate_filename("rules_1.md") is False  # Underscore
        assert RuleDocument.validate_filename("rules.txt") is False  # Wrong extension
        assert RuleDocument.validate_filename("rules") is False  # No extension

    def test_validate_document_type_valid(self):
        """Test validating valid document types."""
        assert RuleDocument.validate_document_type("core-rules") is True
        assert RuleDocument.validate_document_type("faq") is True
        assert RuleDocument.validate_document_type("team-rules") is True
        assert RuleDocument.validate_document_type("ops") is True
        assert RuleDocument.validate_document_type("killzone") is True

    def test_validate_document_type_invalid(self):
        """Test validating invalid document types."""
        assert RuleDocument.validate_document_type("invalid") is False
        assert RuleDocument.validate_document_type("Core-Rules") is False
        assert RuleDocument.validate_document_type("") is False

    def test_validate_success(self):
        """Test successful document validation."""
        doc = RuleDocument(
            document_id=UUID("12345678-1234-5678-1234-567812345678"),
            filename="rules-1-phases.md",
            content="# Rules\n\nContent here.",
            metadata={
                "source": "Core Rules v3.1",
                "last_update_date": "2024-10-01",
                "document_type": "core-rules",
            },
            version="3.1",
            last_update_date=date(2024, 10, 1),
            document_type="core-rules",
            last_updated=datetime.now(timezone.utc),
            hash="abc123",
        )
        # Should not raise
        doc.validate()

    def test_has_changed_no_change(self):
        """Test detecting no change in content."""
        content = "# Original content"
        doc = RuleDocument(
            document_id=UUID("12345678-1234-5678-1234-567812345678"),
            filename="rules.md",
            content=content,
            metadata={
                "source": "Core Rules",
                "last_update_date": "2024-10-01",
                "document_type": "core-rules",
            },
            version="3.1",
            last_update_date=date(2024, 10, 1),
            document_type="core-rules",
            last_updated=datetime.now(timezone.utc),
            hash=RuleDocument.compute_hash(content),
        )

        # Same content should return False
        assert doc.has_changed(content) is False

    def test_has_changed_content_changed(self):
        """Test detecting changed content."""
        original_content = "# Original content"
        doc = RuleDocument(
            document_id=UUID("12345678-1234-5678-1234-567812345678"),
            filename="rules.md",
            content=original_content,
            metadata={
                "source": "Core Rules",
                "last_update_date": "2024-10-01",
                "document_type": "core-rules",
            },
            version="3.1",
            last_update_date=date(2024, 10, 1),
            document_type="core-rules",
            last_updated=datetime.now(timezone.utc),
            hash=RuleDocument.compute_hash(original_content),
        )

        new_content = "# Updated content"

        # Different content should return True
        assert doc.has_changed(new_content) is True

    def test_from_markdown_file(self):
        """Test creating RuleDocument from markdown file."""
        filename = "rules-1-phases.md"
        content = "# Movement Phase\n\nYou can move up to your Movement characteristic."
        metadata = {
            "source": "Core Rules v3.1",
            "last_update_date": "2024-10-01",
            "document_type": "core-rules",
        }

        doc = RuleDocument.from_markdown_file(
            filename=filename,
            content=content,
            metadata=metadata,
        )

        assert isinstance(doc.document_id, UUID)
        assert doc.filename == filename
        assert doc.content == content
        assert doc.metadata == metadata
        assert doc.version == "Core Rules v3.1"
        assert doc.last_update_date == date(2024, 10, 1)
        assert doc.document_type == "core-rules"
        assert isinstance(doc.last_updated, datetime)
        assert doc.hash == RuleDocument.compute_hash(content)

    def test_from_markdown_file_with_date_object(self):
        """Test creating RuleDocument when metadata has date object."""
        metadata = {
            "source": "FAQ v2024-10",
            "last_update_date": date(2024, 10, 15),  # Already a date object
            "document_type": "faq",
        }

        doc = RuleDocument.from_markdown_file(
            filename="faq.md",
            content="# FAQ",
            metadata=metadata,
        )

        assert doc.last_update_date == date(2024, 10, 15)
        assert doc.document_type == "faq"

    def test_from_markdown_file_all_document_types(self):
        """Test creating documents with all valid document types."""
        doc_types = ["core-rules", "faq", "team-rules", "ops", "killzone"]

        for doc_type in doc_types:
            metadata = {
                "source": "Test",
                "last_update_date": "2024-10-01",
                "document_type": doc_type,
            }

            doc = RuleDocument.from_markdown_file(
                filename="test.md",
                content="Content",
                metadata=metadata,
            )

            assert doc.document_type == doc_type

    def test_version_from_metadata_source(self):
        """Test that version is extracted from metadata source."""
        metadata = {
            "source": "Team Rules: Greenskins v1.5",
            "last_update_date": "2024-10-01",
            "document_type": "team-rules",
        }

        doc = RuleDocument.from_markdown_file(
            filename="team-greenskins.md",
            content="# Greenskins",
            metadata=metadata,
        )

        assert doc.version == "Team Rules: Greenskins v1.5"

    def test_hash_matches_content(self):
        """Test that document hash matches the content."""
        content = "# Test Content\n\nSome rules here."
        metadata = {
            "source": "Test",
            "last_update_date": "2024-10-01",
            "document_type": "core-rules",
        }

        doc = RuleDocument.from_markdown_file(
            filename="test.md",
            content=content,
            metadata=metadata,
        )

        expected_hash = RuleDocument.compute_hash(content)
        assert doc.hash == expected_hash
