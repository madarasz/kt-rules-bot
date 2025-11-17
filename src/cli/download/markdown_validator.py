"""Markdown validation utilities.

Extracted from download_team.py for reusability.
"""

from typing import List

from src.lib.logging import get_logger

logger = get_logger(__name__)


class MarkdownValidator:
    """Validates markdown content.

    Provides validation for extracted markdown with YAML frontmatter.
    """

    @staticmethod
    def validate_frontmatter_markdown(markdown: str, team_name: str) -> List[str]:
        """Validate markdown with YAML frontmatter.

        Args:
            markdown: Complete markdown with frontmatter
            team_name: Expected team name

        Returns:
            List of validation warnings (empty if all checks pass)
        """
        warnings = []

        # Check for YAML frontmatter
        if not markdown.startswith("---"):
            warnings.append("Missing YAML frontmatter")

        # Check for required YAML fields
        required_fields = ["source:", "last_update_date:", "document_type:", "section:"]
        for field in required_fields:
            if field not in markdown[:500]:
                warnings.append(f"Missing required field: {field.rstrip(':')}")

        # Check for team name in content (H2 headers with team name)
        team_name_display = team_name.replace('_', ' ').upper()
        if f"## {team_name_display}" not in markdown.upper():
            warnings.append(f"Team name heading not found in markdown")

        # Check for key sections
        if "## " not in markdown:
            warnings.append("No H2 headers found (may indicate incomplete extraction)")

        return warnings

    @staticmethod
    def validate_basic_markdown(markdown: str) -> List[str]:
        """Validate basic markdown structure.

        Args:
            markdown: Markdown content

        Returns:
            List of validation warnings (empty if valid)
        """
        warnings = []

        if not markdown or len(markdown.strip()) == 0:
            warnings.append("Markdown is empty")
            return warnings

        # Check for at least some headers
        if '##' not in markdown:
            warnings.append("No headers found in markdown")

        # Check for suspiciously short content
        if len(markdown) < 100:
            warnings.append("Markdown is suspiciously short (<100 characters)")

        return warnings
