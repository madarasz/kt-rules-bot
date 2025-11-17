"""YAML frontmatter generation for markdown files.

Extracted from download_team.py for reusability.
"""

from datetime import date

from src.lib.logging import get_logger

logger = get_logger(__name__)


class FrontmatterGenerator:
    """Generates YAML frontmatter for markdown files.

    Provides consistent frontmatter generation for team rule documents.
    """

    @staticmethod
    def generate_frontmatter(
        team_name: str,
        last_update_date: date,
        source: str = "WC downloads",
        document_type: str = "team-rules",
    ) -> str:
        """Generate YAML frontmatter block.

        Args:
            team_name: Team name (lowercase)
            last_update_date: Last update date
            source: Source identifier
            document_type: Document type

        Returns:
            YAML frontmatter as string
        """
        return f"""---
source: "{source}"
last_update_date: {last_update_date.strftime('%Y-%m-%d')}
document_type: {document_type}
section: {team_name}
---

"""

    @staticmethod
    def prepend_frontmatter(
        markdown: str,
        team_name: str,
        last_update_date: date,
    ) -> str:
        """Prepend YAML frontmatter to markdown content.

        Args:
            markdown: Markdown content
            team_name: Team name (lowercase)
            last_update_date: Last update date

        Returns:
            Markdown with YAML frontmatter prepended
        """
        frontmatter = FrontmatterGenerator.generate_frontmatter(
            team_name=team_name,
            last_update_date=last_update_date
        )
        return frontmatter + markdown
