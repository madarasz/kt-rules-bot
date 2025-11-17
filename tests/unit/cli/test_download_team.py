"""Unit tests for download_team.py CLI command."""

import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, mock_open
from urllib.error import HTTPError, URLError

import pytest

from src.cli.download_team import (
    extract_date_from_url,
    download_team_internal,
    download_team,
)
from src.cli.download.http_client import HTTPClient
from src.cli.download.team_name_extractor import TeamNameExtractor
from src.cli.download.frontmatter_generator import FrontmatterGenerator
from src.cli.download.markdown_validator import MarkdownValidator


class TestExtractDateFromUrl:
    """Tests for extract_date_from_url function."""

    def test_extracts_date_from_valid_url(self):
        """Test extracting date from URL with pattern."""
        url = "https://example.com/eng_jul25_teamrules.pdf"
        result = extract_date_from_url(url)

        assert result == date(2025, 7, 31)

    def test_extracts_date_jan_pattern(self):
        """Test extracting January date."""
        url = "https://example.com/eng_jan24_rules.pdf"
        result = extract_date_from_url(url)

        assert result == date(2024, 1, 31)

    def test_handles_leap_year_february(self):
        """Test leap year February handling."""
        url = "https://example.com/eng_feb24_rules.pdf"
        result = extract_date_from_url(url)

        assert result == date(2024, 2, 29)  # 2024 is leap year

    def test_handles_non_leap_year_february(self):
        """Test non-leap year February handling."""
        url = "https://example.com/eng_feb23_rules.pdf"
        result = extract_date_from_url(url)

        assert result == date(2023, 2, 28)

    def test_returns_none_for_no_pattern(self):
        """Test that None is returned when pattern not found."""
        url = "https://example.com/teamrules.pdf"
        result = extract_date_from_url(url)

        assert result is None

    def test_returns_none_for_invalid_month(self):
        """Test that None is returned for invalid month abbreviation."""
        url = "https://example.com/eng_xyz25_rules.pdf"
        result = extract_date_from_url(url)

        assert result is None


class TestDownloadPdf:
    """Tests for HTTPClient.download_pdf method."""

    def test_rejects_http_url(self):
        """Test that HTTP URLs are rejected."""
        with pytest.raises(ValueError, match="URL must be HTTPS"):
            HTTPClient.download_pdf("http://example.com/file.pdf")

    def test_rejects_non_pdf_url(self):
        """Test that non-PDF URLs are rejected."""
        with pytest.raises(ValueError, match="URL must point to a PDF file"):
            HTTPClient.download_pdf("https://example.com/file.txt")

    @patch('src.cli.download.http_client.urlopen')
    def test_downloads_valid_pdf(self, mock_urlopen):
        """Test successful PDF download."""
        # Mock response
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b'%PDF-1.4\ntest content'
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        pdf_bytes, file_size = HTTPClient.download_pdf("https://example.com/file.pdf")

        assert pdf_bytes.startswith(b'%PDF')
        assert file_size > 0

    @patch('src.cli.download.http_client.urlopen')
    def test_rejects_empty_pdf(self, mock_urlopen):
        """Test that empty downloads are rejected."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b''
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        with pytest.raises(ValueError, match="Downloaded file is empty"):
            HTTPClient.download_pdf("https://example.com/file.pdf")

    @patch('src.cli.download.http_client.urlopen')
    def test_rejects_invalid_pdf_magic_bytes(self, mock_urlopen):
        """Test that invalid PDF files are rejected."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b'not a pdf file'
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        with pytest.raises(ValueError, match="not a valid PDF"):
            HTTPClient.download_pdf("https://example.com/file.pdf")

    @patch('src.cli.download.http_client.urlopen')
    def test_handles_http_error(self, mock_urlopen):
        """Test handling of HTTP errors."""
        mock_urlopen.side_effect = HTTPError(
            "https://example.com/file.pdf", 404, "Not Found", {}, None
        )

        with pytest.raises(HTTPError):
            HTTPClient.download_pdf("https://example.com/file.pdf")

    @patch('src.cli.download.http_client.urlopen')
    def test_handles_network_error(self, mock_urlopen):
        """Test handling of network errors."""
        mock_urlopen.side_effect = URLError("Network error")

        with pytest.raises(URLError):
            HTTPClient.download_pdf("https://example.com/file.pdf")


class TestExtractTeamName:
    """Tests for TeamNameExtractor.extract_from_markdown method."""

    def test_extracts_team_name_from_h2_with_dash(self):
        """Test extracting team name from H2 header with dash separator."""
        markdown = """# Document Title

## ANGELS OF DEATH - Operative Selection

Some content here.
"""
        result = TeamNameExtractor.extract_from_markdown(markdown)

        assert result == "angels_of_death"

    def test_extracts_team_name_without_dash(self):
        """Test extracting team name from H2 header without dash."""
        markdown = """# Document Title

## Pathfinders

Some content here.
"""
        result = TeamNameExtractor.extract_from_markdown(markdown)

        assert result == "pathfinders"

    def test_handles_multiple_spaces(self):
        """Test handling team names with multiple words."""
        markdown = """## VETERAN GUARDSMEN - Rules"""
        result = TeamNameExtractor.extract_from_markdown(markdown)

        assert result == "veteran_guardsmen"

    def test_raises_error_if_no_h2_found(self):
        """Test that error is raised when no H2 header found."""
        markdown = """# Only H1 Header

Some content.
"""
        with pytest.raises(ValueError, match="Could not find team name"):
            TeamNameExtractor.extract_from_markdown(markdown)

    def test_ignores_h3_headers(self):
        """Test that H3 headers are ignored."""
        markdown = """### This is H3

## TEAM NAME - Rules
"""
        result = TeamNameExtractor.extract_from_markdown(markdown)

        assert result == "team_name"


class TestPrependYamlFrontmatter:
    """Tests for FrontmatterGenerator.prepend_frontmatter method."""

    def test_prepends_yaml_frontmatter(self):
        """Test that YAML frontmatter is correctly prepended."""
        markdown = "## Team Rules\n\nContent here."
        team_name = "pathfinders"
        update_date = date(2024, 1, 15)

        result = FrontmatterGenerator.prepend_frontmatter(markdown, team_name, update_date)

        assert result.startswith("---\n")
        assert "source: \"WC downloads\"" in result
        assert "last_update_date: 2024-01-15" in result
        assert "document_type: team-rules" in result
        assert "section: pathfinders" in result
        assert result.endswith(markdown)


class TestValidateFinalMarkdown:
    """Tests for MarkdownValidator.validate_frontmatter_markdown method."""

    def test_validates_correct_markdown(self):
        """Test validation of correctly formatted markdown."""
        markdown = """---
source: "WC downloads"
last_update_date: 2024-01-01
document_type: team-rules
section: pathfinders
---

## PATHFINDERS - Operative Selection

Content here.
"""
        warnings = MarkdownValidator.validate_frontmatter_markdown(markdown, "pathfinders")

        assert len(warnings) == 0

    def test_detects_missing_frontmatter(self):
        """Test detection of missing YAML frontmatter."""
        markdown = "## TEAM - Rules\n\nContent"
        warnings = MarkdownValidator.validate_frontmatter_markdown(markdown, "team")

        assert any("Missing YAML frontmatter" in w for w in warnings)

    def test_detects_missing_yaml_fields(self):
        """Test detection of missing YAML fields."""
        markdown = """---
source: "WC downloads"
---

## TEAM - Rules
"""
        warnings = MarkdownValidator.validate_frontmatter_markdown(markdown, "team")

        assert any("last_update_date" in w for w in warnings)
        assert any("document_type" in w for w in warnings)

    def test_detects_missing_team_heading(self):
        """Test detection when team name heading not found."""
        markdown = """---
source: "WC downloads"
last_update_date: 2024-01-01
document_type: team-rules
section: pathfinders
---

## DIFFERENT TEAM - Rules
"""
        warnings = MarkdownValidator.validate_frontmatter_markdown(markdown, "pathfinders")

        assert any("Team name heading not found" in w for w in warnings)

    def test_detects_no_headers(self):
        """Test detection when no H2 headers found."""
        markdown = """---
source: "WC downloads"
last_update_date: 2024-01-01
document_type: team-rules
section: pathfinders
---

Just content, no headers.
"""
        warnings = MarkdownValidator.validate_frontmatter_markdown(markdown, "pathfinders")

        assert any("No H2 headers found" in w for w in warnings)


class TestDownloadTeamInternal:
    """Tests for download_team_internal function."""

    @patch('src.cli.download_team.ExtractionPipeline')
    def test_successful_download_and_extraction(self, mock_pipeline_class):
        """Test successful team download and extraction."""
        # Mock extraction pipeline
        mock_pipeline = Mock()
        mock_result = Mock()
        mock_result.success = True
        mock_result.team_name = "pathfinders"
        mock_result.output_file = "/path/to/pathfinders.md"
        mock_result.tokens = 5000
        mock_result.latency_ms = 2000
        mock_result.cost_usd = 0.05
        mock_result.error = None
        mock_result.validation_warnings = []

        mock_pipeline.extract_from_url.return_value = mock_result
        mock_pipeline_class.return_value = mock_pipeline

        result = download_team_internal(
            url="https://example.com/eng_jul25_pathfinders.pdf",
            model="gemini-2.5-pro",
            verbose=False
        )

        assert result["success"] is True
        assert result["team_name"] == "pathfinders"
        assert result["tokens"] == 5000

    @patch('src.cli.download_team.ExtractionPipeline')
    def test_handles_download_failure(self, mock_pipeline_class):
        """Test handling of PDF download failure."""
        # Mock extraction pipeline to return failure
        mock_pipeline = Mock()
        mock_result = Mock()
        mock_result.success = False
        mock_result.team_name = None
        mock_result.output_file = None
        mock_result.tokens = 0
        mock_result.latency_ms = 0
        mock_result.cost_usd = 0.0
        mock_result.error = "Download failed"
        mock_result.validation_warnings = []

        mock_pipeline.extract_from_url.return_value = mock_result
        mock_pipeline_class.return_value = mock_pipeline

        result = download_team_internal(
            url="https://example.com/file.pdf",
            verbose=False
        )

        assert result["success"] is False
        assert "Download failed" in result["error"]

    @patch('src.cli.download_team.ExtractionPipeline')
    def test_handles_extraction_failure(self, mock_pipeline_class):
        """Test handling when extraction fails."""
        # Mock extraction pipeline to return failure
        mock_pipeline = Mock()
        mock_result = Mock()
        mock_result.success = False
        mock_result.team_name = None
        mock_result.output_file = None
        mock_result.tokens = 0
        mock_result.latency_ms = 0
        mock_result.cost_usd = 0.0
        mock_result.error = "Extraction failed: API error"
        mock_result.validation_warnings = []

        mock_pipeline.extract_from_url.return_value = mock_result
        mock_pipeline_class.return_value = mock_pipeline

        result = download_team_internal(
            url="https://example.com/file.pdf",
            verbose=False
        )

        assert result["success"] is False
        assert "Extraction failed" in result["error"]

    @patch('src.cli.download_team.ExtractionPipeline')
    def test_passes_update_date_to_pipeline(self, mock_pipeline_class):
        """Test that update_date is passed to pipeline."""
        # Mock extraction pipeline
        mock_pipeline = Mock()
        mock_result = Mock()
        mock_result.success = True
        mock_result.team_name = "pathfinders"
        mock_result.output_file = "/path/to/pathfinders.md"
        mock_result.tokens = 0
        mock_result.latency_ms = 0
        mock_result.cost_usd = 0.0
        mock_result.error = None
        mock_result.validation_warnings = []

        mock_pipeline.extract_from_url.return_value = mock_result
        mock_pipeline_class.return_value = mock_pipeline

        update_date = date(2024, 1, 15)
        result = download_team_internal(
            url="https://example.com/file.pdf",
            update_date=update_date,
            verbose=False
        )

        # Verify that extract_from_url was called with the update_date
        mock_pipeline.extract_from_url.assert_called_once()
        call_kwargs = mock_pipeline.extract_from_url.call_args[1]
        assert call_kwargs["update_date"] == update_date


class TestDownloadTeam:
    """Tests for download_team CLI entry point."""

    @patch('src.cli.download_team.download_team_internal')
    def test_successful_download(self, mock_internal):
        """Test successful download command."""
        mock_internal.return_value = {
            "success": True,
            "team_name": "pathfinders",
            "output_file": "extracted-rules/team/pathfinders.md",
            "tokens": 5000,
            "latency_ms": 2000,
            "cost_usd": 0.05,
            "error": None,
            "validation_warnings": []
        }

        # Should not raise
        download_team(url="https://example.com/file.pdf")

    @patch('src.cli.download_team.download_team_internal')
    def test_handles_invalid_date_format(self, mock_internal):
        """Test handling of invalid date format."""
        with pytest.raises(SystemExit):
            download_team(
                url="https://example.com/file.pdf",
                update_date="invalid-date"
            )

    @patch('src.cli.download_team.download_team_internal')
    def test_exits_on_failure(self, mock_internal):
        """Test that CLI exits with error code on failure."""
        mock_internal.return_value = {
            "success": False,
            "error": "Download failed"
        }

        with pytest.raises(SystemExit) as exc_info:
            download_team(url="https://example.com/file.pdf")

        assert exc_info.value.code == 1

    @patch('src.cli.download_team.download_team_internal')
    def test_parses_update_date(self, mock_internal):
        """Test that update_date is parsed correctly."""
        mock_internal.return_value = {"success": True}

        download_team(
            url="https://example.com/file.pdf",
            update_date="2024-01-15"
        )

        # Check that parsed date was passed to internal function
        call_args = mock_internal.call_args
        assert call_args[1]['update_date'] == date(2024, 1, 15)
