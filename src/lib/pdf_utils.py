"""PDF utility functions.

Provides PDF processing utilities including decompression for Claude compatibility
and text extraction for providers without native PDF support.
"""

import io
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager

import pdfplumber
import pikepdf

from src.lib.logging import get_logger

logger = get_logger(__name__)


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfplumber.

    Used for LLM providers that don't support native PDF processing (e.g., Grok).
    Extracts text from each page with layout preservation.

    Args:
        pdf_bytes: PDF file content as bytes

    Returns:
        Concatenated text from all pages with page markers

    Raises:
        ValueError: If PDF is empty or has no extractable text
    """
    if len(pdf_bytes) == 0:
        raise ValueError("PDF file is empty")

    extracted_pages = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        logger.info(f"Extracting text from PDF with {len(pdf.pages)} pages")

        for i, page in enumerate(pdf.pages, start=1):
            # Extract text with layout preservation
            text = page.extract_text(layout=True)
            if text:
                extracted_pages.append(f"--- Page {i} ---\n{text}")

    if not extracted_pages:
        raise ValueError("PDF has no extractable text")

    full_text = "\n\n".join(extracted_pages)
    logger.info(f"Extracted {len(full_text)} characters from {len(extracted_pages)} pages")

    return full_text


def decompress_pdf(pdf_path: str) -> str:
    """Decompress PDF streams for Claude compatibility.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Path to decompressed PDF (or original if decompression fails)

    Note:
        Claude has issues processing PDFs with zip/deflate encoding.
        This function creates an uncompressed version that Claude can handle.
    """
    try:
        output_path = pdf_path.replace(".pdf", "_decompressed.pdf")
        original_size = os.path.getsize(pdf_path)

        logger.info(
            f"Decompressing PDF for Claude compatibility ({original_size / 1024 / 1024:.1f} MB)"
        )

        with pikepdf.Pdf.open(pdf_path) as pdf:
            pdf.save(
                output_path,
                compress_streams=False,
                stream_decode_level=pikepdf.StreamDecodeLevel.all,
            )

        decompressed_size = os.path.getsize(output_path)
        logger.info(
            f"PDF decompressed: {original_size / 1024 / 1024:.1f} MB → "
            f"{decompressed_size / 1024 / 1024:.1f} MB "
            f"({(decompressed_size / original_size - 1) * 100:+.0f}%)"
        )

        return output_path

    except Exception as e:
        logger.warning(f"PDF decompression failed: {e}, using original file")
        return pdf_path


@contextmanager
def decompress_pdf_with_cleanup(pdf_bytes: bytes) -> Iterator[tuple[str, str]]:
    """Context manager for PDF decompression with automatic cleanup.

    Creates a temporary PDF file from bytes, decompresses it, and ensures
    both files are cleaned up when done.

    Args:
        pdf_bytes: PDF file content as bytes

    Yields:
        Tuple of (temp_pdf_path, decompressed_pdf_path)

    Example:
        >>> with decompress_pdf_with_cleanup(pdf_bytes) as (temp_path, decompressed_path):
        ...     # Use decompressed_path for processing
        ...     with open(decompressed_path, 'rb') as f:
        ...         result = process_pdf(f)
    """
    temp_pdf_path = None
    decompressed_pdf_path = None

    try:
        # Create a temporary file for the original PDF
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".pdf", delete=False) as temp_pdf:
            temp_pdf.write(pdf_bytes)
            temp_pdf_path = temp_pdf.name

        # Decompress PDF to remove zip/deflate encoding (Claude compatibility)
        decompressed_pdf_path = decompress_pdf(temp_pdf_path)

        yield (temp_pdf_path, decompressed_pdf_path)

    finally:
        # Clean up temp files
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            os.unlink(temp_pdf_path)
        if (
            decompressed_pdf_path
            and decompressed_pdf_path != temp_pdf_path
            and os.path.exists(decompressed_pdf_path)
        ):
            os.unlink(decompressed_pdf_path)
