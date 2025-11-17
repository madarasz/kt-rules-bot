"""HTTP client for downloading files.

Extracted from download_team.py to reduce code duplication.
"""

from typing import Tuple
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from src.lib.logging import get_logger

logger = get_logger(__name__)


class HTTPClient:
    """HTTP client for downloading files.

    Provides a reusable interface for HTTP downloads with proper
    error handling and logging.
    """

    DEFAULT_TIMEOUT = 30
    USER_AGENT = "Kill-Team-Rules-Bot/1.0"

    @staticmethod
    def download_file(
        url: str,
        timeout: int = DEFAULT_TIMEOUT,
        headers: dict = None
    ) -> Tuple[bytes, int]:
        """Download a file from URL.

        Args:
            url: File URL
            timeout: Request timeout in seconds
            headers: Additional HTTP headers

        Returns:
            Tuple of (file bytes, file size in bytes)

        Raises:
            HTTPError: HTTP error occurred
            URLError: Network error occurred
            ValueError: Invalid response
        """
        logger.info(f"Downloading file from {url}")

        # Build headers
        request_headers = {
            'User-Agent': f"{HTTPClient.USER_AGENT} (File Download Tool)"
        }
        if headers:
            request_headers.update(headers)

        # Create request
        request = Request(url, headers=request_headers)

        try:
            with urlopen(request, timeout=timeout) as response:
                if response.status != 200:
                    raise HTTPError(
                        url,
                        response.status,
                        f"HTTP {response.status}",
                        response.headers,
                        None
                    )

                file_bytes = response.read()

                if len(file_bytes) == 0:
                    raise ValueError("Downloaded file is empty")

                logger.info(f"Downloaded {len(file_bytes)} bytes")
                return file_bytes, len(file_bytes)

        except HTTPError as e:
            logger.error(f"HTTP error downloading file: {e}")
            raise
        except URLError as e:
            logger.error(f"Network error downloading file: {e}")
            raise

    @staticmethod
    def download_pdf(url: str, timeout: int = DEFAULT_TIMEOUT) -> Tuple[bytes, int]:
        """Download a PDF file from URL with validation.

        Args:
            url: PDF URL (must be HTTPS and end with .pdf)
            timeout: Request timeout in seconds

        Returns:
            Tuple of (PDF bytes, file size in bytes)

        Raises:
            ValueError: Invalid URL or not a PDF
            HTTPError: HTTP error occurred
            URLError: Network error occurred
        """
        if not url.startswith('https://'):
            raise ValueError("URL must be HTTPS")

        if not url.lower().endswith('.pdf'):
            raise ValueError("URL must point to a PDF file")

        pdf_bytes, size = HTTPClient.download_file(url, timeout)

        # Basic PDF validation (check magic bytes)
        if not pdf_bytes.startswith(b'%PDF'):
            raise ValueError("Downloaded file is not a valid PDF")

        return pdf_bytes, size
