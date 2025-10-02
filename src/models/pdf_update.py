"""PDFUpdate model for official rule PDFs.

Represents an official Kill Team rules document (PDF).
Based on specs/001-we-are-building/data-model.md
"""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Literal, Optional
from uuid import UUID, uuid4
import hashlib
import re


ExtractionStatus = Literal["pending", "success", "failed"]


@dataclass
class PDFUpdate:
    """An official Kill Team rules document (PDF)."""

    update_id: UUID
    pdf_filename: str
    pdf_url: str
    download_date: datetime
    publication_date: date
    version: str
    file_size_bytes: int
    file_hash: str  # SHA-256 for duplicate detection
    extraction_status: ExtractionStatus
    error_message: Optional[str] = None

    @staticmethod
    def compute_file_hash(file_content: bytes) -> str:
        """Compute SHA-256 hash of PDF file.

        Args:
            file_content: PDF file bytes

        Returns:
            SHA-256 hash hex string
        """
        return hashlib.sha256(file_content).hexdigest()

    @staticmethod
    def validate_url(url: str) -> bool:
        """Validate PDF URL is HTTPS.

        Args:
            url: URL to validate

        Returns:
            True if valid HTTPS URL
        """
        return url.startswith("https://")

    @staticmethod
    def validate_version(version: str) -> bool:
        """Validate version format (semver or date-based).

        Args:
            version: Version string to validate

        Returns:
            True if valid format
        """
        # Semver pattern: 1.0, 3.1, etc.
        semver_pattern = r"^\d+\.\d+$"
        # Date-based pattern: FAQ-2024-10, v2024-09, etc.
        date_pattern = r"^[A-Za-z]+-?\d{4}-\d{2}$"

        return bool(re.match(semver_pattern, version)) or bool(
            re.match(date_pattern, version)
        )

    def validate(self) -> None:
        """Validate PDFUpdate fields.

        Raises:
            ValueError: If validation fails
        """
        # URL validation
        if not self.validate_url(self.pdf_url):
            raise ValueError("pdf_url must be HTTPS")

        # Version validation
        if not self.validate_version(self.version):
            raise ValueError(
                "version must be semver (e.g., '3.1') or date-based (e.g., 'FAQ-2024-10')"
            )

        # Error message required if failed
        if self.extraction_status == "failed" and not self.error_message:
            raise ValueError(
                "error_message required when extraction_status is 'failed'"
            )

        # File size validation
        if self.file_size_bytes <= 0:
            raise ValueError("file_size_bytes must be positive")

    def mark_success(self) -> None:
        """Mark extraction as successful."""
        self.extraction_status = "success"
        self.error_message = None

    def mark_failed(self, error: str) -> None:
        """Mark extraction as failed.

        Args:
            error: Error message
        """
        self.extraction_status = "failed"
        self.error_message = error

    @classmethod
    def from_download(
        cls,
        pdf_filename: str,
        pdf_url: str,
        file_content: bytes,
        publication_date: date,
        version: str,
    ) -> "PDFUpdate":
        """Create PDFUpdate from downloaded PDF.

        Args:
            pdf_filename: Original PDF filename
            pdf_url: Source URL
            file_content: PDF bytes
            publication_date: Publication date
            version: Version string

        Returns:
            PDFUpdate instance
        """
        return cls(
            update_id=uuid4(),
            pdf_filename=pdf_filename,
            pdf_url=pdf_url,
            download_date=datetime.now(timezone.utc),
            publication_date=publication_date,
            version=version,
            file_size_bytes=len(file_content),
            file_hash=cls.compute_file_hash(file_content),
            extraction_status="pending",
            error_message=None,
        )
