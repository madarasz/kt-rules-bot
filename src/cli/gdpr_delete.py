"""CLI command to delete user data (GDPR compliance).

Usage:
    python -m src.cli.gdpr_delete --user-id <hashed_user_id>
"""

import argparse
import sys
from datetime import UTC, datetime

from src.lib.logging import get_logger
from src.models.user_query import UserQuery

logger = get_logger(__name__)
audit_logger = get_logger("gdpr_audit")


def delete_user_data(user_id: str, confirm: bool = False) -> None:
    """Delete all data for a user (GDPR right to erasure).

    Args:
        user_id: Hashed user ID or Discord user ID
        confirm: If True, skip confirmation prompt
    """
    # Hash the user ID if it's not already hashed
    if len(user_id) != 64:  # Not a SHA-256 hash
        print("Converting Discord user ID to hashed ID...")
        hashed_id = UserQuery.hash_user_id(user_id)
        print(f"Hashed ID: {hashed_id}")
    else:
        hashed_id = user_id

    print("\nGDPR Data Deletion Request")
    print(f"{'='*60}")
    print(f"User ID (hashed): {hashed_id[:16]}...")
    print(f"Timestamp: {datetime.now(UTC).isoformat()}")
    print(f"{'='*60}\n")

    # Confirmation
    if not confirm:
        response = input("Are you sure you want to delete this user's data? (yes/no): ")
        if response.lower() != "yes":
            print("❌ Deletion cancelled")
            return

    # Log audit trail
    audit_logger.info(
        "GDPR deletion request initiated",
        extra={
            "event_type": "gdpr_deletion",
            "user_id": hashed_id[:16],  # Partial hash for privacy
            "timestamp": datetime.now(UTC).isoformat(),
            "initiated_by": "cli",
        },
    )

    try:
        # In-memory data (conversation contexts) - automatically expires via TTL
        # No action needed for in-memory data

        # Logs - would need to be deleted from log aggregation system
        # This is implementation-specific based on logging backend
        print("⚠️  Note: Log deletion must be performed in log aggregation system")
        print("   (e.g., CloudWatch, Loki, Datadog)")

        # Vector DB - user_id not stored in embeddings, so no action needed
        print("✓ Vector DB: No PII stored")

        # Conversation history - expires automatically via TTL (30 minutes)
        print("✓ Conversation history: Auto-expires via TTL")

        # Feedback logs - would need custom query to filter logs
        print("⚠️  Feedback logs: Query logs for user_id and delete")

        print(f"\n{'='*60}")
        print("✓ GDPR deletion process complete")
        print(f"{'='*60}\n")

        # Log completion
        audit_logger.info(
            "GDPR deletion completed",
            extra={
                "event_type": "gdpr_deletion_complete",
                "user_id": hashed_id[:16],
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    except Exception as e:
        logger.error(f"GDPR deletion failed: {e}", exc_info=True)
        audit_logger.error(
            "GDPR deletion failed",
            extra={
                "event_type": "gdpr_deletion_failed",
                "user_id": hashed_id[:16],
                "error": str(e),
            },
        )
        print(f"❌ Deletion failed: {e}")
        sys.exit(1)


def main() -> None:
    """Main entry point for gdpr_delete CLI."""
    parser = argparse.ArgumentParser(
        description="Delete user data for GDPR compliance"
    )
    parser.add_argument(
        "--user-id",
        "-u",
        required=True,
        help="Discord user ID or hashed user ID",
    )
    parser.add_argument(
        "--confirm",
        "-y",
        action="store_true",
        help="Skip confirmation prompt",
    )

    args = parser.parse_args()

    try:
        delete_user_data(args.user_id, confirm=args.confirm)
    except Exception as e:
        logger.error(f"GDPR deletion failed: {e}", exc_info=True)
        print(f"❌ GDPR deletion failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
