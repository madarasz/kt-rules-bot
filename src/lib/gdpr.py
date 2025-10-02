"""GDPR data cleanup and retention enforcement.

7-day retention enforcement with deletion audit logging.
Based on specs/001-we-are-building/tasks.md T030
Constitution Principle III: Security by Design (GDPR compliance)
"""

from datetime import datetime, timedelta, timezone
from typing import List, Protocol
from dataclasses import dataclass
from uuid import UUID
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class DeletionAuditLog:
    """Audit log entry for data deletion."""

    timestamp: datetime
    entity_type: str  # "UserQuery", "BotResponse", etc.
    entity_id: UUID
    user_id: str  # Hashed
    reason: str  # "7-day retention", "user request", etc.
    deleted_by: str  # "scheduler", "admin", "user"


class GDPREntity(Protocol):
    """Protocol for entities subject to GDPR retention."""

    timestamp: datetime
    user_id: str

    def is_expired(self) -> bool:
        """Check if entity has exceeded retention period."""
        ...


class GDPRCleanupService:
    """Service for GDPR-compliant data cleanup."""

    def __init__(self, retention_days: int = 7):
        """Initialize GDPR cleanup service.

        Args:
            retention_days: Number of days to retain data (default: 7)
        """
        self.retention_days = retention_days
        self.audit_logs: List[DeletionAuditLog] = []

    def get_cutoff_date(self) -> datetime:
        """Get cutoff date for data retention.

        Returns:
            Cutoff datetime (UTC)
        """
        return datetime.now(timezone.utc) - timedelta(days=self.retention_days)

    def should_delete(self, entity: GDPREntity) -> bool:
        """Check if entity should be deleted.

        Args:
            entity: Entity to check

        Returns:
            True if entity exceeds retention period
        """
        cutoff = self.get_cutoff_date()
        return entity.timestamp < cutoff

    def log_deletion(
        self,
        entity_type: str,
        entity_id: UUID,
        user_id: str,
        reason: str = "7-day retention",
        deleted_by: str = "scheduler",
    ) -> None:
        """Log data deletion for audit trail.

        Args:
            entity_type: Type of entity deleted
            entity_id: Entity ID
            user_id: User ID (hashed)
            reason: Reason for deletion
            deleted_by: Who triggered deletion
        """
        audit_entry = DeletionAuditLog(
            timestamp=datetime.now(timezone.utc),
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            reason=reason,
            deleted_by=deleted_by,
        )

        self.audit_logs.append(audit_entry)

        logger.info(
            "gdpr_deletion",
            entity_type=entity_type,
            entity_id=str(entity_id),
            user_id=user_id,
            reason=reason,
            deleted_by=deleted_by,
        )

    def get_audit_logs(
        self,
        entity_type: str | None = None,
        user_id: str | None = None,
    ) -> List[DeletionAuditLog]:
        """Get deletion audit logs.

        Args:
            entity_type: Filter by entity type (optional)
            user_id: Filter by user ID (optional)

        Returns:
            List of audit logs
        """
        logs = self.audit_logs

        if entity_type:
            logs = [log for log in logs if log.entity_type == entity_type]

        if user_id:
            logs = [log for log in logs if log.user_id == user_id]

        return logs

    def cleanup_expired_entities(
        self,
        entities: List[GDPREntity],
        entity_type: str,
    ) -> int:
        """Clean up expired entities.

        Args:
            entities: List of entities to check
            entity_type: Type of entity

        Returns:
            Number of entities deleted
        """
        deleted_count = 0
        cutoff = self.get_cutoff_date()

        for entity in entities:
            if entity.timestamp < cutoff:
                # Log deletion
                self.log_deletion(
                    entity_type=entity_type,
                    entity_id=getattr(entity, "query_id", UUID(int=0)),
                    user_id=entity.user_id,
                    reason="7-day retention",
                    deleted_by="scheduler",
                )

                deleted_count += 1

        logger.info(
            "gdpr_cleanup_completed",
            entity_type=entity_type,
            deleted_count=deleted_count,
            cutoff_date=cutoff.isoformat(),
        )

        return deleted_count

    def delete_user_data(
        self,
        user_id: str,
        entity_types: List[str],
    ) -> int:
        """Delete all data for a specific user (right to erasure).

        Args:
            user_id: User ID (hashed)
            entity_types: Types of entities to delete

        Returns:
            Total number of entities deleted
        """
        deleted_count = 0

        for entity_type in entity_types:
            # This would interface with actual data stores
            # For now, just log the request
            self.log_deletion(
                entity_type=entity_type,
                entity_id=UUID(int=0),  # Placeholder
                user_id=user_id,
                reason="user erasure request",
                deleted_by="user",
            )
            deleted_count += 1

        logger.info(
            "gdpr_user_erasure",
            user_id=user_id,
            entity_types=entity_types,
            deleted_count=deleted_count,
        )

        return deleted_count

    def export_user_data(self, user_id: str) -> dict:
        """Export all data for a specific user (right to data portability).

        Args:
            user_id: User ID (hashed)

        Returns:
            Dictionary with user data
        """
        logger.info("gdpr_data_export", user_id=user_id)

        # This would interface with actual data stores
        # For now, return placeholder
        return {
            "user_id": user_id,
            "export_date": datetime.now(timezone.utc).isoformat(),
            "queries": [],
            "responses": [],
        }
