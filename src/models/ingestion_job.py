"""IngestionJob model for PDF-to-markdown conversion.

Represents automated process that converts PDFs to markdown and updates RAG.
Based on specs/001-we-are-building/data-model.md
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

JobStatus = Literal["running", "success", "failed"]


@dataclass
class IngestionJob:
    """Automated process that converts PDFs to markdown and updates RAG."""

    job_id: UUID
    update_id: UUID  # FK to PDFUpdate
    status: JobStatus
    started_at: datetime
    completed_at: datetime | None = None
    processed_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    documents_created: int = 0
    documents_updated: int = 0
    reingestion_triggered: bool = False
    extraction_token_count: int = 0
    extraction_cost_usd: float | None = None
    extraction_latency_ms: int | None = None

    def validate(self) -> None:
        """Validate IngestionJob fields.

        Raises:
            ValueError: If validation fails
        """
        # Status must be valid
        valid_statuses = {"running", "success", "failed"}
        if self.status not in valid_statuses:
            raise ValueError(f"status must be one of: {', '.join(valid_statuses)}")

        # Completed_at must be after started_at
        if self.completed_at and self.completed_at < self.started_at:
            raise ValueError("completed_at must be after started_at")

        # Errors required if failed
        if self.status == "failed" and not self.errors:
            raise ValueError("errors list must be non-empty when status is 'failed'")

        # Token count validation
        if self.extraction_token_count < 0:
            raise ValueError("extraction_token_count cannot be negative")

    def mark_success(self) -> None:
        """Mark job as successful."""
        self.status = "success"
        self.completed_at = datetime.now(UTC)

    def mark_failed(self, error: str) -> None:
        """Mark job as failed.

        Args:
            error: Error message
        """
        self.status = "failed"
        self.completed_at = datetime.now(UTC)
        if error not in self.errors:
            self.errors.append(error)

    def add_processed_file(self, filename: str) -> None:
        """Add processed file to the list.

        Args:
            filename: Processed markdown filename
        """
        if filename not in self.processed_files:
            self.processed_files.append(filename)

    def add_warning(self, warning: str) -> None:
        """Add non-fatal warning.

        Args:
            warning: Warning message
        """
        if warning not in self.warnings:
            self.warnings.append(warning)

    def add_error(self, error: str) -> None:
        """Add error message.

        Args:
            error: Error message
        """
        if error not in self.errors:
            self.errors.append(error)

    def increment_created(self) -> None:
        """Increment documents_created counter."""
        self.documents_created += 1

    def increment_updated(self) -> None:
        """Increment documents_updated counter."""
        self.documents_updated += 1

    def set_extraction_metrics(self, token_count: int, cost_usd: float, latency_ms: int) -> None:
        """Set LLM-based extraction metrics.

        Args:
            token_count: Tokens used for extraction
            cost_usd: Estimated cost
            latency_ms: Extraction time in milliseconds
        """
        self.extraction_token_count = token_count
        self.extraction_cost_usd = cost_usd
        self.extraction_latency_ms = latency_ms

    def get_duration_seconds(self) -> float | None:
        """Get job duration in seconds.

        Returns:
            Duration in seconds, or None if not completed
        """
        if not self.completed_at:
            return None

        delta = self.completed_at - self.started_at
        return delta.total_seconds()

    @classmethod
    def start(cls, update_id: UUID) -> "IngestionJob":
        """Start a new ingestion job.

        Args:
            update_id: Reference to PDFUpdate

        Returns:
            IngestionJob instance
        """
        return cls(
            job_id=uuid4(), update_id=update_id, status="running", started_at=datetime.now(UTC)
        )
