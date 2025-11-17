"""RuleDocument model for Kill Team rule markdown files.

Represents a markdown file in extracted-rules/ folder.
Based on specs/001-we-are-building/data-model.md
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

DocumentType = Literal["core-rules", "faq", "team-rules", "ops", "killzone"]


@dataclass
class RuleDocument:
    """A markdown file representing Kill Team rules."""

    document_id: UUID
    filename: str
    content: str
    metadata: dict[str, Any]  # YAML frontmatter
    version: str
    last_update_date: date
    document_type: DocumentType
    last_updated: datetime
    hash: str  # SHA-256 of content

    @staticmethod
    def compute_hash(content: str) -> str:
        """Compute SHA-256 hash of document content.

        Args:
            content: Document content

        Returns:
            SHA-256 hash hex string
        """
        return hashlib.sha256(content.encode()).hexdigest()

    @staticmethod
    def validate_filename(filename: str) -> bool:
        """Validate filename pattern.

        Args:
            filename: Filename to validate

        Returns:
            True if valid
        """
        pattern = r"^[a-z0-9-]+\.md$"
        return bool(re.match(pattern, filename))

    @staticmethod
    def validate_document_type(doc_type: str) -> bool:
        """Validate document type.

        Args:
            doc_type: Document type to validate

        Returns:
            True if valid
        """
        valid_types = {"core-rules", "faq", "team-rules", "ops", "killzone"}
        return doc_type in valid_types

    def validate(self) -> None:
        """Validate RuleDocument fields.

        Raises:
            ValueError: If validation fails
        """
        # Filename pattern validation
        if not self.validate_filename(self.filename):
            raise ValueError(f"filename '{self.filename}' must match pattern [a-z0-9-]+.md")

        # Document type validation
        if not self.validate_document_type(self.document_type):
            raise ValueError(
                "document_type must be one of: core-rules, faq, team-rules, ops, killzone"
            )

        # Required metadata fields
        required_fields = ["source", "last_update_date", "document_type"]
        for field in required_fields:
            if field not in self.metadata:
                raise ValueError(f"metadata missing required field: {field}")

        # No executable code blocks
        if "```python" in self.content or "```bash" in self.content:
            raise ValueError("content contains executable code blocks")

    def has_changed(self, new_content: str) -> bool:
        """Check if content has changed.

        Args:
            new_content: New content to compare

        Returns:
            True if content is different
        """
        new_hash = self.compute_hash(new_content)
        return new_hash != self.hash

    @classmethod
    def from_markdown_file(
        cls, filename: str, content: str, metadata: dict[str, Any]
    ) -> "RuleDocument":
        """Create RuleDocument from markdown file data.

        Args:
            filename: Markdown filename
            content: File content
            metadata: Parsed YAML frontmatter

        Returns:
            RuleDocument instance

        Raises:
            ValueError: If metadata is invalid
        """
        # Extract required fields from metadata
        version = metadata.get("source", "Unknown")
        last_update_str = metadata.get("last_update_date")
        doc_type = metadata.get("document_type")

        # Parse last update date
        if isinstance(last_update_str, str):
            last_update_date = date.fromisoformat(last_update_str)
        elif isinstance(last_update_str, date):
            last_update_date = last_update_str
        else:
            raise ValueError(f"Invalid last_update_date format: {last_update_str}")

        # Validate document type
        if not doc_type or not isinstance(doc_type, str):
            raise ValueError(f"document_type must be a non-empty string, got: {doc_type}")
        if not cls.validate_document_type(doc_type):
            raise ValueError(f"Invalid document_type: {doc_type}")

        return cls(
            document_id=uuid4(),
            filename=filename,
            content=content,
            metadata=metadata,
            version=version,
            last_update_date=last_update_date,
            document_type=doc_type,
            last_updated=datetime.now(UTC),
            hash=cls.compute_hash(content),
        )
