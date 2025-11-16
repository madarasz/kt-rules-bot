"""Unit tests for IngestionJob model."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from src.models.ingestion_job import IngestionJob


class TestIngestionJob:
    """Test IngestionJob model."""

    def test_validate_success(self):
        """Test successful validation."""
        job = IngestionJob(
            job_id=uuid4(),
            update_id=uuid4(),
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        # Should not raise
        job.validate()

    def test_mark_success(self):
        """Test marking job as successful."""
        job = IngestionJob.start(uuid4())

        job.mark_success()

        assert job.status == "success"
        assert job.completed_at is not None
        assert isinstance(job.completed_at, datetime)

    def test_mark_failed(self):
        """Test marking job as failed."""
        job = IngestionJob.start(uuid4())

        error_msg = "PDF parsing failed"
        job.mark_failed(error_msg)

        assert job.status == "failed"
        assert job.completed_at is not None
        assert error_msg in job.errors

    def test_mark_failed_multiple_errors(self):
        """Test marking job as failed with multiple errors."""
        job = IngestionJob.start(uuid4())

        job.mark_failed("Error 1")
        job.mark_failed("Error 2")

        assert job.status == "failed"
        assert "Error 1" in job.errors
        assert "Error 2" in job.errors

    def test_add_processed_file(self):
        """Test adding processed files."""
        job = IngestionJob.start(uuid4())

        job.add_processed_file("rules-1.md")
        job.add_processed_file("rules-2.md")

        assert len(job.processed_files) == 2
        assert "rules-1.md" in job.processed_files
        assert "rules-2.md" in job.processed_files

    def test_add_processed_file_no_duplicates(self):
        """Test that duplicate files are not added."""
        job = IngestionJob.start(uuid4())

        job.add_processed_file("rules-1.md")
        job.add_processed_file("rules-1.md")

        assert len(job.processed_files) == 1

    def test_add_warning(self):
        """Test adding warnings."""
        job = IngestionJob.start(uuid4())

        job.add_warning("Minor formatting issue")
        job.add_warning("Missing metadata")

        assert len(job.warnings) == 2
        assert "Minor formatting issue" in job.warnings

    def test_add_warning_no_duplicates(self):
        """Test that duplicate warnings are not added."""
        job = IngestionJob.start(uuid4())

        job.add_warning("Warning 1")
        job.add_warning("Warning 1")

        assert len(job.warnings) == 1

    def test_add_error(self):
        """Test adding errors."""
        job = IngestionJob.start(uuid4())

        job.add_error("Parse error")
        job.add_error("Network error")

        assert len(job.errors) == 2
        assert "Parse error" in job.errors

    def test_add_error_no_duplicates(self):
        """Test that duplicate errors are not added."""
        job = IngestionJob.start(uuid4())

        job.add_error("Error 1")
        job.add_error("Error 1")

        assert len(job.errors) == 1

    def test_increment_created(self):
        """Test incrementing documents_created counter."""
        job = IngestionJob.start(uuid4())

        assert job.documents_created == 0

        job.increment_created()
        job.increment_created()

        assert job.documents_created == 2

    def test_increment_updated(self):
        """Test incrementing documents_updated counter."""
        job = IngestionJob.start(uuid4())

        assert job.documents_updated == 0

        job.increment_updated()
        job.increment_updated()
        job.increment_updated()

        assert job.documents_updated == 3

    def test_set_extraction_metrics(self):
        """Test setting extraction metrics."""
        job = IngestionJob.start(uuid4())

        job.set_extraction_metrics(
            token_count=1500,
            cost_usd=0.05,
            latency_ms=3000,
        )

        assert job.extraction_token_count == 1500
        assert job.extraction_cost_usd == 0.05
        assert job.extraction_latency_ms == 3000

    def test_get_duration_seconds_not_completed(self):
        """Test getting duration when job not completed."""
        job = IngestionJob.start(uuid4())

        duration = job.get_duration_seconds()

        assert duration is None

    def test_get_duration_seconds_completed(self):
        """Test getting duration when job completed."""
        job = IngestionJob.start(uuid4())

        # Set completion time 5 seconds after start
        job.completed_at = job.started_at + timedelta(seconds=5)

        duration = job.get_duration_seconds()

        assert duration == 5.0

    def test_start(self):
        """Test starting a new ingestion job."""
        update_id = uuid4()

        job = IngestionJob.start(update_id)

        assert job.update_id == update_id
        assert job.status == "running"
        assert isinstance(job.started_at, datetime)
        assert job.completed_at is None
        assert job.processed_files == []
        assert job.errors == []
        assert job.warnings == []
        assert job.documents_created == 0
        assert job.documents_updated == 0
        assert job.reingestion_triggered is False
        assert job.extraction_token_count == 0

    def test_complete_workflow(self):
        """Test a complete ingestion workflow."""
        job = IngestionJob.start(uuid4())

        # Add some files
        job.add_processed_file("rules-1.md")
        job.add_processed_file("rules-2.md")

        # Add some warnings
        job.add_warning("Minor issue")

        # Update counters
        job.increment_created()
        job.increment_created()

        # Set metrics
        job.set_extraction_metrics(1000, 0.03, 2000)

        # Mark as successful
        job.mark_success()

        # Verify final state
        assert job.status == "success"
        assert len(job.processed_files) == 2
        assert len(job.warnings) == 1
        assert job.documents_created == 2
        assert job.extraction_token_count == 1000
        assert job.completed_at is not None

    def test_failed_workflow(self):
        """Test a failed ingestion workflow."""
        job = IngestionJob.start(uuid4())

        # Add some processing before failure
        job.add_processed_file("rules-1.md")
        job.increment_created()

        # Add error
        job.add_error("Critical error occurred")

        # Mark as failed
        job.mark_failed("Job failed due to critical error")

        # Verify final state
        assert job.status == "failed"
        assert len(job.errors) == 2
        assert job.completed_at is not None
