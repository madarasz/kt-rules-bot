"""Download subsystem for team rule PDFs."""

from src.cli.download.http_client import HTTPClient
from src.cli.download.pdf_validator import PDFValidator
from src.cli.download.team_name_extractor import TeamNameExtractor
from src.cli.download.frontmatter_generator import FrontmatterGenerator
from src.cli.download.markdown_validator import MarkdownValidator
from src.cli.download.extraction_pipeline import ExtractionPipeline, ExtractionResult
from src.cli.download.api_client import WarhammerCommunityAPI
from src.cli.download.bulk_processor import BulkDownloadProcessor

__all__ = [
    "HTTPClient",
    "PDFValidator",
    "TeamNameExtractor",
    "FrontmatterGenerator",
    "MarkdownValidator",
    "ExtractionPipeline",
    "ExtractionResult",
    "WarhammerCommunityAPI",
    "BulkDownloadProcessor",
]
