"""Team name extraction utilities.

Extracted from download_team.py and download_all_teams.py for reusability.
"""

import re

from src.lib.logging import get_logger

logger = get_logger(__name__)


class TeamNameExtractor:
    """Extracts and normalizes team names.

    Provides consistent team name extraction from various sources.
    """

    @staticmethod
    def extract_from_markdown(markdown: str) -> str:
        """Extract team name from first H2 header in markdown.

        Args:
            markdown: Extracted markdown content

        Returns:
            Team name in lowercase (e.g., "angels_of_death")

        Raises:
            ValueError: If no H2 header found

        Examples:
            "## ANGELS OF DEATH - Operative Selection" -> "angels_of_death"
            "## Pathfinders - Faction Rules" -> "pathfinders"
        """
        # Find first H2 header (## TEAM NAME - ...)
        lines = markdown.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('## ') and not line.startswith('###'):
                # Extract full header (remove '## ' prefix)
                header = line[3:].strip()

                # Extract team name (text before first ' - ')
                if ' - ' in header:
                    team_name = header.split(' - ')[0].strip()
                else:
                    # Fallback: use entire header
                    team_name = header

                # Convert to lowercase and replace spaces with underscores
                team_name_clean = team_name.lower().replace(' ', '_')
                return team_name_clean

        raise ValueError("Could not find team name in extracted markdown (no H2 header found)")

    @staticmethod
    def normalize_team_name(title: str) -> str:
        """Normalize team title to filename format.

        Args:
            title: Team title from API (e.g., "Vespid Stingwings")

        Returns:
            Normalized filename (e.g., "vespid_stingwings")
        """
        # Convert to lowercase
        normalized = title.lower()

        # Replace spaces and special characters with underscores
        normalized = re.sub(r'[^\w\s-]', '', normalized)
        normalized = re.sub(r'[\s-]+', '_', normalized)

        return normalized
