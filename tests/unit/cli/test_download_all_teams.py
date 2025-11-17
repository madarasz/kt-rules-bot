"""Unit tests for download_all_teams.py CLI command."""

import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, mock_open
from urllib.error import HTTPError, URLError

import pytest

from src.cli.download_all_teams import (
    download_all_teams,
)
from src.cli.download.team_name_extractor import TeamNameExtractor
from src.cli.download.api_client import WarhammerCommunityAPI
from src.cli.download.bulk_processor import BulkDownloadProcessor


class TestNormalizeTeamName:
    """Tests for TeamNameExtractor.normalize_team_name method."""

    def test_normalizes_simple_name(self):
        """Test normalizing a simple team name."""
        result = TeamNameExtractor.normalize_team_name("Pathfinders")

        assert result == "pathfinders"

    def test_normalizes_multi_word_name(self):
        """Test normalizing multi-word team name."""
        result = TeamNameExtractor.normalize_team_name("Veteran Guardsmen")

        assert result == "veteran_guardsmen"

    def test_normalizes_with_special_chars(self):
        """Test normalizing name with special characters."""
        result = TeamNameExtractor.normalize_team_name("Angels of Death")

        assert result == "angels_of_death"

    def test_removes_apostrophes(self):
        """Test that apostrophes are removed."""
        result = TeamNameExtractor.normalize_team_name("Hunter's Mark")

        assert result == "hunters_mark"

    def test_handles_multiple_spaces(self):
        """Test handling of multiple consecutive spaces."""
        result = TeamNameExtractor.normalize_team_name("Team  Name   Here")

        assert result == "team_name_here"

    def test_handles_hyphens(self):
        """Test that hyphens are converted to underscores."""
        result = TeamNameExtractor.normalize_team_name("Team-Name")

        assert result == "team_name"


class TestFetchTeamList:
    """Tests for WarhammerCommunityAPI.fetch_team_list method."""

    @patch('src.cli.download.api_client.urlopen')
    def test_fetches_team_list_successfully(self, mock_urlopen):
        """Test successful API call."""
        api_response = {
            "hits": [
                {"id": {"title": "Team 1"}},
                {"id": {"title": "Team 2"}},
            ]
        }

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps(api_response).encode('utf-8')
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = WarhammerCommunityAPI.fetch_team_list()

        assert len(result) == 2
        assert result[0]["id"]["title"] == "Team 1"

    @patch('src.cli.download.api_client.urlopen')
    def test_handles_http_error(self, mock_urlopen):
        """Test handling of HTTP errors."""
        mock_urlopen.side_effect = HTTPError(
            "https://api.example.com", 500, "Server Error", {}, None
        )

        with pytest.raises(HTTPError):
            WarhammerCommunityAPI.fetch_team_list()

    @patch('src.cli.download.api_client.urlopen')
    def test_handles_network_error(self, mock_urlopen):
        """Test handling of network errors."""
        mock_urlopen.side_effect = URLError("Connection failed")

        with pytest.raises(URLError):
            WarhammerCommunityAPI.fetch_team_list()

    @patch('src.cli.download.api_client.urlopen')
    def test_handles_invalid_json(self, mock_urlopen):
        """Test handling of invalid JSON response."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b'invalid json'
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        with pytest.raises(json.JSONDecodeError):
            WarhammerCommunityAPI.fetch_team_list()

    @patch('src.cli.download.api_client.urlopen')
    def test_handles_missing_hits_field(self, mock_urlopen):
        """Test handling when API response missing 'hits' field."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({"data": []}).encode('utf-8')
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        with pytest.raises(ValueError, match="Invalid API response"):
            WarhammerCommunityAPI.fetch_team_list()


class TestFilterTeamRules:
    """Tests for WarhammerCommunityAPI.filter_team_rules method."""

    def test_filters_team_rules_string_format(self):
        """Test filtering with string format categories."""
        hits = [
            {"id": {"title": "Team 1"}, "download_categories": ["team-rules"]},
            {"id": {"title": "Team 2"}, "download_categories": ["other-category"]},
            {"id": {"title": "Team 3"}, "download_categories": ["team-rules", "other"]},
        ]

        result = WarhammerCommunityAPI.filter_team_rules(hits)

        assert len(result) == 2
        assert result[0]["id"]["title"] == "Team 1"
        assert result[1]["id"]["title"] == "Team 3"

    def test_filters_team_rules_object_format(self):
        """Test filtering with object format categories."""
        hits = [
            {"id": {"title": "Team 1"}, "download_categories": [{"slug": "team-rules"}]},
            {"id": {"title": "Team 2"}, "download_categories": [{"slug": "core-rules"}]},
        ]

        result = WarhammerCommunityAPI.filter_team_rules(hits)

        assert len(result) == 1
        assert result[0]["id"]["title"] == "Team 1"

    def test_filters_empty_list(self):
        """Test filtering empty hits list."""
        result = WarhammerCommunityAPI.filter_team_rules([])

        assert len(result) == 0

    def test_filters_mixed_format_categories(self):
        """Test filtering with mixed string and object categories."""
        hits = [
            {"id": {"title": "Team 1"}, "download_categories": ["team-rules"]},
            {"id": {"title": "Team 2"}, "download_categories": [{"slug": "team-rules"}]},
        ]

        result = WarhammerCommunityAPI.filter_team_rules(hits)

        assert len(result) == 2


class TestGetExistingTeamDate:
    """Tests for BulkDownloadProcessor.get_existing_team_date method."""

    def test_returns_none_if_file_does_not_exist(self):
        """Test that None is returned if file doesn't exist."""
        with patch.object(Path, 'exists', return_value=False):
            result = BulkDownloadProcessor.get_existing_team_date("pathfinders", output_dir=Path("/tmp"))
            assert result is None

    def test_extracts_date_from_frontmatter(self):
        """Test extracting date from YAML frontmatter."""
        markdown_content = """---
source: "WC downloads"
last_update_date: 2024-01-15
document_type: team-rules
---

## PATHFINDERS - Rules
"""
        with patch.object(Path, 'exists', return_value=True):
            with patch.object(Path, 'read_text', return_value=markdown_content):
                result = BulkDownloadProcessor.get_existing_team_date("pathfinders", output_dir=Path("/tmp"))
                assert result == date(2024, 1, 15)

    def test_handles_missing_frontmatter(self):
        """Test handling when YAML frontmatter is missing."""
        markdown_content = "## PATHFINDERS - Rules"
        with patch.object(Path, 'exists', return_value=True):
            with patch.object(Path, 'read_text', return_value=markdown_content):
                result = BulkDownloadProcessor.get_existing_team_date("pathfinders", output_dir=Path("/tmp"))
                assert result is None

    def test_handles_malformed_frontmatter(self):
        """Test handling when YAML frontmatter is malformed."""
        markdown_content = """---
source: "WC downloads"
no closing delimiter
"""
        with patch.object(Path, 'exists', return_value=True):
            with patch.object(Path, 'read_text', return_value=markdown_content):
                result = BulkDownloadProcessor.get_existing_team_date("pathfinders", output_dir=Path("/tmp"))
                assert result is None

    def test_handles_missing_date_field(self):
        """Test handling when last_update_date field is missing."""
        markdown_content = """---
source: "WC downloads"
document_type: team-rules
---
"""
        with patch.object(Path, 'exists', return_value=True):
            with patch.object(Path, 'read_text', return_value=markdown_content):
                result = BulkDownloadProcessor.get_existing_team_date("pathfinders", output_dir=Path("/tmp"))
                assert result is None


class TestParseApiDate:
    """Tests for WarhammerCommunityAPI.parse_date method."""

    def test_parses_last_updated_field(self):
        """Test parsing date from id.last_updated field."""
        hit = {
            "id": {"last_updated": "15/01/2024"},
            "date": 1705276800
        }

        result = WarhammerCommunityAPI.parse_date(hit)

        assert result == date(2024, 1, 15)

    def test_falls_back_to_timestamp(self):
        """Test falling back to timestamp when last_updated missing."""
        hit = {
            "date": 1705276800  # 2024-01-15 00:00:00 UTC
        }

        result = WarhammerCommunityAPI.parse_date(hit)

        assert result is not None
        assert isinstance(result, date)

    def test_handles_invalid_date_format(self):
        """Test handling invalid date format."""
        hit = {
            "id": {"last_updated": "invalid-date"},
            "date": 1705276800
        }

        # Should fall back to timestamp
        result = WarhammerCommunityAPI.parse_date(hit)

        assert result is not None

    def test_returns_none_for_missing_date(self):
        """Test that None is returned when no valid date found."""
        hit = {"id": {}}

        result = WarhammerCommunityAPI.parse_date(hit)

        assert result is None


class TestShouldDownloadTeam:
    """Tests for BulkDownloadProcessor.should_download_team method."""

    @patch('src.cli.download.bulk_processor.BulkDownloadProcessor.get_existing_team_date')
    def test_downloads_new_file(self, mock_get_date):
        """Test that new files are downloaded."""
        mock_get_date.return_value = None

        hit = {"id": {"title": "Pathfinders"}}
        should_download, reason = BulkDownloadProcessor.should_download_team(hit)

        assert should_download is True
        assert reason == "new file"

    @patch('src.cli.download.bulk_processor.BulkDownloadProcessor.get_existing_team_date')
    def test_downloads_with_force_flag(self, mock_get_date):
        """Test that force flag overrides date check."""
        mock_get_date.return_value = date(2024, 1, 1)

        hit = {"id": {"title": "Pathfinders"}}
        should_download, reason = BulkDownloadProcessor.should_download_team(hit, force=True)

        assert should_download is True
        assert reason == "forced"

    @patch('src.cli.download.bulk_processor.BulkDownloadProcessor.get_existing_team_date')
    @patch('src.cli.download.api_client.WarhammerCommunityAPI.parse_date')
    def test_downloads_updated_file(self, mock_parse_date, mock_get_date):
        """Test downloading when API date is newer."""
        mock_get_date.return_value = date(2024, 1, 1)
        mock_parse_date.return_value = date(2024, 2, 1)

        hit = {"id": {"title": "Pathfinders"}}
        should_download, reason = BulkDownloadProcessor.should_download_team(hit)

        assert should_download is True
        assert "updated" in reason

    @patch('src.cli.download.bulk_processor.BulkDownloadProcessor.get_existing_team_date')
    @patch('src.cli.download.api_client.WarhammerCommunityAPI.parse_date')
    def test_skips_up_to_date_file(self, mock_parse_date, mock_get_date):
        """Test skipping when file is up to date."""
        mock_get_date.return_value = date(2024, 2, 1)
        mock_parse_date.return_value = date(2024, 1, 1)

        hit = {"id": {"title": "Pathfinders"}}
        should_download, reason = BulkDownloadProcessor.should_download_team(hit)

        assert should_download is False
        assert "up-to-date" in reason

    @patch('src.cli.download.bulk_processor.BulkDownloadProcessor.get_existing_team_date')
    @patch('src.cli.download.api_client.WarhammerCommunityAPI.parse_date')
    def test_downloads_when_no_api_date(self, mock_parse_date, mock_get_date):
        """Test downloading when API date is missing."""
        mock_get_date.return_value = date(2024, 1, 1)
        mock_parse_date.return_value = None

        hit = {"id": {"title": "Pathfinders"}}
        should_download, reason = BulkDownloadProcessor.should_download_team(hit)

        assert should_download is True
        assert reason == "no API date"


class TestDownloadAllTeams:
    """Tests for download_all_teams function."""

    @patch('src.cli.download.bulk_processor.BulkDownloadProcessor.process_bulk_download')
    def test_handles_api_fetch_failure(self, mock_process):
        """Test handling of API fetch failure."""
        mock_process.side_effect = HTTPError("url", 500, "Error", {}, None)

        with pytest.raises(SystemExit):
            download_all_teams()

    @patch('src.cli.download.bulk_processor.BulkDownloadProcessor.process_bulk_download')
    def test_handles_download_failure(self, mock_process):
        """Test handling when download fails."""
        mock_summary = Mock()
        mock_summary.failed = 1
        mock_process.return_value = mock_summary

        with pytest.raises(SystemExit):
            download_all_teams()

    @patch('src.cli.download.bulk_processor.BulkDownloadProcessor.process_bulk_download')
    def test_dry_run_mode(self, mock_process):
        """Test dry-run mode."""
        mock_summary = Mock()
        mock_summary.failed = 0
        mock_summary.downloaded = 0
        mock_summary.skipped = 2
        mock_process.return_value = mock_summary

        # Should not raise
        download_all_teams(dry_run=True)
        mock_process.assert_called_once()
        call_kwargs = mock_process.call_args[1]
        assert call_kwargs['dry_run'] is True

    @patch('src.cli.download.bulk_processor.BulkDownloadProcessor.process_bulk_download')
    def test_all_teams_up_to_date(self, mock_process):
        """Test when all teams are up to date."""
        mock_summary = Mock()
        mock_summary.failed = 0
        mock_summary.downloaded = 0
        mock_summary.skipped = 5
        mock_process.return_value = mock_summary

        # Should not raise
        download_all_teams()

    @patch('src.cli.download.bulk_processor.BulkDownloadProcessor.process_bulk_download')
    def test_downloads_teams_successfully(self, mock_process):
        """Test successful team downloads."""
        mock_summary = Mock()
        mock_summary.failed = 0
        mock_summary.downloaded = 3
        mock_summary.skipped = 2
        mock_summary.total_tokens = 15000
        mock_summary.total_time_seconds = 60.0
        mock_summary.total_cost_usd = 0.15
        mock_process.return_value = mock_summary

        # Should complete successfully
        download_all_teams()

    @patch('src.cli.download.bulk_processor.BulkDownloadProcessor.process_bulk_download')
    def test_force_flag_passed_to_processor(self, mock_process):
        """Test that force flag is passed to bulk processor."""
        mock_summary = Mock()
        mock_summary.failed = 0
        mock_process.return_value = mock_summary

        download_all_teams(force=True)
        mock_process.assert_called_once()
        call_kwargs = mock_process.call_args[1]
        assert call_kwargs['force'] is True
