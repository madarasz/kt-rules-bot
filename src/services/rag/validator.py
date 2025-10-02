"""Document validation service for markdown files.

Validates markdown files have YAML frontmatter and correct document_type enum.
Based on specs/001-we-are-building/tasks.md T037.
"""

import re
from typing import Tuple, Dict, Any, List
from pathlib import Path
import yaml

from src.models.rule_document import DocumentType
from src.lib.logging import get_logger

logger = get_logger(__name__)


class DocumentValidator:
    """Validates markdown rule documents."""

    def __init__(self):
        """Initialize document validator."""
        self.valid_doc_types = {"core-rules", "faq", "team-rules", "ops"}

    def validate_file(self, file_path: str | Path) -> Tuple[bool, str, Dict[str, Any]]:
        """Validate a markdown file.

        Args:
            file_path: Path to markdown file

        Returns:
            Tuple of (is_valid, error_message, metadata)
        """
        file_path = Path(file_path)

        # Check file exists
        if not file_path.exists():
            return False, f"File not found: {file_path}", {}

        # Check file extension
        if file_path.suffix != ".md":
            return False, f"File must have .md extension: {file_path}", {}

        # Read file content
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            return False, f"Failed to read file: {e}", {}

        # Validate content
        return self.validate_content(content, file_path.name)

    def validate_content(
        self, content: str, filename: str = ""
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Validate markdown content.

        Args:
            content: Markdown content
            filename: Optional filename for error messages

        Returns:
            Tuple of (is_valid, error_message, metadata)
        """
        # Check for YAML frontmatter
        has_frontmatter, metadata, error = self._extract_frontmatter(content)
        if not has_frontmatter:
            return False, f"{filename}: {error}", {}

        # Validate required fields
        valid, error = self._validate_metadata(metadata, filename)
        if not valid:
            return False, error, metadata

        return True, "", metadata

    def _extract_frontmatter(
        self, content: str
    ) -> Tuple[bool, Dict[str, Any], str]:
        """Extract YAML frontmatter from markdown.

        Args:
            content: Markdown content

        Returns:
            Tuple of (success, metadata_dict, error_message)
        """
        # YAML frontmatter pattern: ---\n...\n---
        frontmatter_pattern = r"^---\s*\n(.*?)\n---\s*\n"
        match = re.match(frontmatter_pattern, content, re.DOTALL)

        if not match:
            return False, {}, "Missing YAML frontmatter (should start with ---)"

        frontmatter_text = match.group(1)

        # Parse YAML
        try:
            metadata = yaml.safe_load(frontmatter_text)
            if not isinstance(metadata, dict):
                return False, {}, "YAML frontmatter must be a dictionary"

            return True, metadata, ""

        except yaml.YAMLError as e:
            return False, {}, f"Invalid YAML syntax: {e}"

    def _validate_metadata(
        self, metadata: Dict[str, Any], filename: str
    ) -> Tuple[bool, str]:
        """Validate metadata fields.

        Args:
            metadata: Metadata dictionary
            filename: Filename for error messages

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check required fields
        required_fields = ["source", "publication_date", "document_type"]
        missing_fields = [
            field for field in required_fields if field not in metadata
        ]

        if missing_fields:
            return (
                False,
                f"{filename}: Missing required fields: {', '.join(missing_fields)}",
            )

        # Validate document_type
        doc_type = metadata.get("document_type")
        if doc_type not in self.valid_doc_types:
            return (
                False,
                f"{filename}: Invalid document_type '{doc_type}'. "
                f"Must be one of: {', '.join(self.valid_doc_types)}",
            )

        # Validate publication_date format
        pub_date = metadata.get("publication_date")
        if not self._is_valid_date(pub_date):
            return (
                False,
                f"{filename}: Invalid publication_date '{pub_date}'. "
                f"Must be YYYY-MM-DD format",
            )

        return True, ""

    def _is_valid_date(self, date_str: Any) -> bool:
        """Check if date string is valid.

        Args:
            date_str: Date string to validate (or datetime.date object from YAML)

        Returns:
            True if valid date format
        """
        # YAML safe_load automatically converts YYYY-MM-DD to datetime.date
        from datetime import date

        if isinstance(date_str, date):
            return True

        if not isinstance(date_str, str):
            return False

        # Check YYYY-MM-DD format
        date_pattern = r"^\d{4}-\d{2}-\d{2}$"
        return bool(re.match(date_pattern, date_str))

    def validate_directory(
        self, directory: str | Path
    ) -> Tuple[List[str], List[Tuple[str, str]]]:
        """Validate all markdown files in a directory.

        Args:
            directory: Path to directory

        Returns:
            Tuple of (valid_files, invalid_files_with_errors)
        """
        directory = Path(directory)

        if not directory.exists() or not directory.is_dir():
            logger.error("invalid_directory", path=str(directory))
            return [], [(str(directory), "Directory not found")]

        valid_files: List[str] = []
        invalid_files: List[Tuple[str, str]] = []

        # Find all .md files
        for md_file in directory.glob("*.md"):
            is_valid, error, metadata = self.validate_file(md_file)

            if is_valid:
                valid_files.append(str(md_file))
                logger.debug("file_validated", file=str(md_file))
            else:
                invalid_files.append((str(md_file), error))
                logger.warning("file_validation_failed", file=str(md_file), error=error)

        logger.info(
            "directory_validated",
            directory=str(directory),
            valid=len(valid_files),
            invalid=len(invalid_files),
        )

        return valid_files, invalid_files
