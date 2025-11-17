"""PDF validation utilities.

Extracted from download_team.py for reusability.
"""

from typing import List

from src.lib.logging import get_logger

logger = get_logger(__name__)


class PDFValidator:
    """Validates PDF files.

    Provides validation for PDF file structure and content.
    """

    @staticmethod
    def validate_pdf_bytes(pdf_bytes: bytes) -> List[str]:
        """Validate PDF file bytes.

        Args:
            pdf_bytes: PDF file content

        Returns:
            List of validation warnings (empty if valid)
        """
        warnings = []

        # Check if empty
        if len(pdf_bytes) == 0:
            warnings.append("PDF file is empty")
            return warnings

        # Check PDF magic bytes
        if not pdf_bytes.startswith(b'%PDF'):
            warnings.append("File does not have valid PDF magic bytes")

        # Check minimum size (valid PDFs are usually >1KB)
        if len(pdf_bytes) < 1024:
            warnings.append("PDF file is suspiciously small (<1KB)")

        # Check for PDF EOF marker
        if b'%%EOF' not in pdf_bytes[-1024:]:
            warnings.append("PDF file may be truncated (no EOF marker)")

        return warnings

    @staticmethod
    def is_valid_pdf(pdf_bytes: bytes) -> bool:
        """Check if bytes represent a valid PDF.

        Args:
            pdf_bytes: PDF file content

        Returns:
            True if valid, False otherwise
        """
        warnings = PDFValidator.validate_pdf_bytes(pdf_bytes)
        return len(warnings) == 0
