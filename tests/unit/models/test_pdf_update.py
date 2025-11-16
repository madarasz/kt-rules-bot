"""Unit tests for PDFUpdate model."""

import hashlib
from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import pytest

from src.models.pdf_update import PDFUpdate


class TestPDFUpdate:
    """Test PDFUpdate model."""

    def test_compute_file_hash(self):
        """Test SHA-256 hash computation."""
        content = b"test content"
        expected = hashlib.sha256(content).hexdigest()
        assert PDFUpdate.compute_file_hash(content) == expected

    def test_compute_file_hash_empty(self):
        """Test hash of empty content."""
        content = b""
        expected = hashlib.sha256(content).hexdigest()
        assert PDFUpdate.compute_file_hash(content) == expected

    def test_validate_url_https(self):
        """Test HTTPS URL validation."""
        assert PDFUpdate.validate_url("https://example.com/file.pdf") is True

    def test_validate_url_http(self):
        """Test HTTP URL is invalid."""
        assert PDFUpdate.validate_url("http://example.com/file.pdf") is False

    def test_validate_url_invalid(self):
        """Test invalid URL format."""
        assert PDFUpdate.validate_url("not-a-url") is False

    def test_validate_version_semver(self):
        """Test semver version validation."""
        assert PDFUpdate.validate_version("1.0") is True
        assert PDFUpdate.validate_version("3.1") is True
        assert PDFUpdate.validate_version("10.25") is True

    def test_validate_version_date_based(self):
        """Test date-based version validation."""
        assert PDFUpdate.validate_version("FAQ-2024-10") is True
        assert PDFUpdate.validate_version("v2024-09") is True

    def test_validate_version_invalid(self):
        """Test invalid version formats."""
        assert PDFUpdate.validate_version("1") is False
        assert PDFUpdate.validate_version("1.0.0") is False
        assert PDFUpdate.validate_version("invalid") is False

    def test_validate_success(self):
        """Test successful validation."""
        pdf_update = PDFUpdate(
            update_id=uuid4(),
            pdf_filename="rules.pdf",
            pdf_url="https://example.com/rules.pdf",
            download_date=datetime.now(timezone.utc),
            last_update_date=date.today(),
            version="3.1",
            file_size_bytes=1024,
            file_hash="abc123",
            extraction_status="pending",
        )
        # Should not raise
        pdf_update.validate()

    def test_mark_success(self):
        """Test marking extraction as successful."""
        pdf_update = PDFUpdate(
            update_id=uuid4(),
            pdf_filename="rules.pdf",
            pdf_url="https://example.com/rules.pdf",
            download_date=datetime.now(timezone.utc),
            last_update_date=date.today(),
            version="3.1",
            file_size_bytes=1024,
            file_hash="abc123",
            extraction_status="pending",
            error_message="previous error",
        )

        pdf_update.mark_success()

        assert pdf_update.extraction_status == "success"
        assert pdf_update.error_message is None

    def test_mark_failed(self):
        """Test marking extraction as failed."""
        pdf_update = PDFUpdate(
            update_id=uuid4(),
            pdf_filename="rules.pdf",
            pdf_url="https://example.com/rules.pdf",
            download_date=datetime.now(timezone.utc),
            last_update_date=date.today(),
            version="3.1",
            file_size_bytes=1024,
            file_hash="abc123",
            extraction_status="pending",
        )

        error_msg = "Extraction failed due to timeout"
        pdf_update.mark_failed(error_msg)

        assert pdf_update.extraction_status == "failed"
        assert pdf_update.error_message == error_msg

    def test_from_download(self):
        """Test creating PDFUpdate from download."""
        file_content = b"PDF content here"
        last_update = date(2024, 10, 1)

        pdf_update = PDFUpdate.from_download(
            pdf_filename="rules.pdf",
            pdf_url="https://example.com/rules.pdf",
            file_content=file_content,
            last_update_date=last_update,
            version="3.1",
        )

        assert isinstance(pdf_update.update_id, UUID)
        assert pdf_update.pdf_filename == "rules.pdf"
        assert pdf_update.pdf_url == "https://example.com/rules.pdf"
        assert pdf_update.last_update_date == last_update
        assert pdf_update.version == "3.1"
        assert pdf_update.file_size_bytes == len(file_content)
        assert pdf_update.file_hash == PDFUpdate.compute_file_hash(file_content)
        assert pdf_update.extraction_status == "pending"
        assert pdf_update.error_message is None
        assert isinstance(pdf_update.download_date, datetime)
