#!/usr/bin/env python3
"""Reset the RAG vector database.

This script deletes all embeddings from the Chroma vector database.
Useful for clean re-ingestion after chunking or embedding changes.

Usage:
    python scripts/reset_rag_db.py [--confirm]
"""

import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.rag.vector_db import VectorDBService
from src.lib.logging import get_logger

logger = get_logger(__name__)


def reset_database(force: bool = False) -> None:
    """Reset the RAG vector database.

    Args:
        force: Skip confirmation prompt if True
    """
    try:
        # Initialize vector DB service and get config
        from src.lib.config import get_config
        config = get_config()

        vector_db = VectorDBService()
        count_before = vector_db.get_count()

        print(f"\n🗄️  Current vector database:")
        print(f"   Collection: {vector_db.collection.name}")
        print(f"   Path: {config.vector_db_path}")
        print(f"   Embeddings: {count_before}")

        if count_before == 0:
            print("\n✅ Database is already empty. Nothing to delete.")
            return

        # Confirmation prompt
        if not force:
            print(f"\n⚠️  WARNING: This will delete all {count_before} embeddings!")
            response = input("   Are you sure you want to continue? (yes/no): ")
            if response.lower() not in ["yes", "y"]:
                print("\n❌ Reset cancelled.")
                return

        # Reset the collection
        print("\n🗑️  Resetting vector database...")
        vector_db.reset()

        count_after = vector_db.get_count()
        print(f"✅ Database reset complete!")
        print(f"   Embeddings deleted: {count_before}")
        print(f"   Current embeddings: {count_after}")

        logger.info(
            "vector_db_reset_via_script",
            embeddings_deleted=count_before,
            current_count=count_after
        )

    except Exception as e:
        logger.error("vector_db_reset_failed", error=str(e), exc_info=True)
        print(f"\n❌ Error resetting database: {e}")
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Reset the RAG vector database (delete all embeddings)"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Skip confirmation prompt and reset immediately"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("RAG Vector Database Reset Script")
    print("=" * 60)

    reset_database(force=args.confirm)


if __name__ == "__main__":
    main()
