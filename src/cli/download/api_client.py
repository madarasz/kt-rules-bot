"""Warhammer Community API client.

Extracted from download_all_teams.py for reusability.
"""

import json
from datetime import date, datetime
from typing import List, Dict, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from src.lib.logging import get_logger

logger = get_logger(__name__)


class WarhammerCommunityAPI:
    """Client for Warhammer Community API.

    Provides access to team rules downloads from the official API.
    """

    API_URL = "https://www.warhammer-community.com/api/search/downloads/"
    ASSETS_BASE = "https://assets.warhammer-community.com/"
    USER_AGENT = "Kill-Team-Rules-Bot/1.0 (Bulk Download Tool)"

    @staticmethod
    def fetch_team_list() -> List[Dict]:
        """Fetch list of all teams from Warhammer Community API.

        Returns:
            List of team data dicts from API

        Raises:
            HTTPError: API request failed
            URLError: Network error
            ValueError: Invalid API response
        """
        payload = {
            "index": "downloads_v2",
            "searchTerm": "",
            "gameSystem": "kill-team",
            "language": "english"
        }

        headers = {
            'Content-Type': 'application/json',
            'User-Agent': WarhammerCommunityAPI.USER_AGENT
        }

        logger.info(f"Fetching team list from {WarhammerCommunityAPI.API_URL}")

        request = Request(
            WarhammerCommunityAPI.API_URL,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST'
        )

        try:
            with urlopen(request, timeout=30) as response:
                if response.status != 200:
                    raise HTTPError(
                        WarhammerCommunityAPI.API_URL,
                        response.status,
                        f"HTTP {response.status}",
                        response.headers,
                        None
                    )

                data = json.loads(response.read().decode('utf-8'))

                if 'hits' not in data:
                    raise ValueError("Invalid API response: missing 'hits' field")

                logger.info(f"Fetched {len(data['hits'])} results from API")
                return data['hits']

        except HTTPError as e:
            logger.error(f"HTTP error fetching team list: {e}")
            raise
        except URLError as e:
            logger.error(f"Network error fetching team list: {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse API response: {e}")
            raise

    @staticmethod
    def filter_team_rules(hits: List[Dict]) -> List[Dict]:
        """Filter API results for team-rules downloads.

        Args:
            hits: Raw API results

        Returns:
            Filtered list containing only team-rules entries
        """
        team_rules = []

        for hit in hits:
            # Check if download_categories contains "team-rules"
            download_categories = hit.get('download_categories', [])

            # Check both string format and object format
            is_team_rules = False
            for category in download_categories:
                if isinstance(category, str) and category == "team-rules":
                    is_team_rules = True
                    break
                elif isinstance(category, dict) and category.get('slug') == "team-rules":
                    is_team_rules = True
                    break

            if is_team_rules:
                team_rules.append(hit)

        logger.info(f"Filtered to {len(team_rules)} team-rules entries")
        return team_rules

    @staticmethod
    def parse_date(hit: Dict) -> Optional[date]:
        """Parse last_updated date from API hit.

        Args:
            hit: Team data from API

        Returns:
            Date object or None if parsing fails
        """
        # Try to get last_updated from id.last_updated (DD/MM/YYYY format)
        last_updated_str = hit.get('id', {}).get('last_updated')

        if last_updated_str:
            try:
                # Parse DD/MM/YYYY format
                return datetime.strptime(last_updated_str, '%d/%m/%Y').date()
            except ValueError:
                logger.warning(f"Failed to parse last_updated: {last_updated_str}")

        # Fallback to timestamp if last_updated not available
        api_timestamp = hit.get('date', 0)
        if api_timestamp > 0:
            return datetime.fromtimestamp(api_timestamp).date()

        logger.warning("No valid date found in API hit")
        return None

    @staticmethod
    def get_pdf_url(hit: Dict) -> Optional[str]:
        """Get PDF URL from API hit.

        Args:
            hit: Team data from API

        Returns:
            Full PDF URL or None if not found
        """
        file_name = hit.get('id', {}).get('file', '')

        if not file_name:
            return None

        return f"{WarhammerCommunityAPI.ASSETS_BASE}{file_name}"

    @staticmethod
    def get_team_title(hit: Dict) -> str:
        """Get team title from API hit.

        Args:
            hit: Team data from API

        Returns:
            Team title or "Unknown"
        """
        return hit.get('id', {}).get('title', 'Unknown')
