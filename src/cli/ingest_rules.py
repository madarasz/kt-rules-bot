"""CLI command to ingest markdown rules into vector database.

Usage:
    python -m src.cli.ingest_rules --source extracted-rules/
"""

import argparse
import sys
from pathlib import Path
from typing import List

from src.lib.config import get_config
from src.lib.logging import get_logger
from src.models.rule_document import RuleDocument
from src.services.rag.ingestor import RAGIngestor
from src.services.rag.validator import DocumentValidator
from src.services.rag.vector_db import VectorDBService
from src.services.rag.embeddings import EmbeddingService

logger = get_logger(__name__)


def find_markdown_files(source_dir: Path) -> List[Path]:
    """Find all markdown files in source directory.

    Args:
        source_dir: Directory to search

    Returns:
        List of markdown file paths
    """
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    md_files = list(source_dir.rglob("*.md"))
    return sorted(md_files)


def ingest_rules(source_dir: str, force: bool = False) -> None:
    """Ingest markdown rules from source directory.

    Args:
        source_dir: Path to directory containing markdown files
        force: If True, re-ingest even if document hash exists
    """
    config = get_config()
    source_path = Path(source_dir)

    logger.info(f"Starting ingestion from {source_path}")

    # Find all markdown files
    md_files = find_markdown_files(source_path)

    if not md_files:
        logger.warning(f"No markdown files found in {source_path}")
        print(f"⚠️  No markdown files found in {source_path}")
        return

    print(f"Found {len(md_files)} markdown files")

    # Initialize services
    try:
        vector_db = VectorDBService(collection_name="kill_team_rules")
        embedding_service = EmbeddingService()
        ingestor = RAGIngestor(
            vector_db_service=vector_db,
            embedding_service=embedding_service,
        )
        validator = DocumentValidator()
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}", exc_info=True)
        print(f"❌ Error initializing services: {e}")
        sys.exit(1)

    # Process each file
    documents_processed = 0
    documents_skipped = 0
    validation_errors = 0
    total_chunks = 0

    for md_file in md_files:
        try:
            # Read file
            content = md_file.read_text(encoding="utf-8")
            relative_path = md_file.relative_to(source_path)

            # Validate document
            is_valid, error, metadata = validator.validate_content(
                content, str(relative_path)
            )

            if not is_valid:
                logger.warning(f"Validation failed for {relative_path}: {error}")
                print(f"⚠️  {relative_path}: {error}")
                validation_errors += 1
                continue

            # Create RuleDocument
            rule_doc = RuleDocument.from_markdown_file(
                filename=md_file.name,
                content=content,
                metadata=metadata,
            )

            # Check if document already exists (unless force)
            if not force:
                existing_hash = ingestor.document_hashes.get(rule_doc.filename)
                if existing_hash == rule_doc.hash:
                    logger.info(
                        f"Skipping {relative_path}: unchanged (hash: {rule_doc.hash[:8]}...)"
                    )
                    print(f"⊘ {relative_path} - unchanged, skipping")
                    documents_skipped += 1
                    continue

            # Ingest document (expects a list)
            result = ingestor.ingest([rule_doc])

            documents_processed += 1
            total_chunks += result.embedding_count
            print(
                f"✓ {relative_path} - {result.documents_processed} docs, "
                f"{result.embedding_count} embeddings"
            )

        except Exception as e:
            logger.error(f"Error processing {md_file}: {e}", exc_info=True)
            print(f"❌ {md_file.name}: {str(e)}")
            documents_skipped += 1

    # Summary
    print(f"\n{'='*60}")
    print(f"Ingestion complete")
    print(f"  Documents processed: {documents_processed}")
    print(f"  Documents skipped: {documents_skipped}")
    print(f"  Validation errors: {validation_errors}")
    print(f"  Total chunks created: {total_chunks}")
    print(f"{'='*60}")

    logger.info(
        "Ingestion complete",
        extra={
            "documents_processed": documents_processed,
            "documents_skipped": documents_skipped,
            "validation_errors": validation_errors,
            "total_chunks": total_chunks,
        },
    )


def main():
    """Main entry point for ingest_rules CLI."""
    parser = argparse.ArgumentParser(
        description="Ingest Kill Team markdown rules into vector database"
    )
    parser.add_argument(
        "--source",
        "-s",
        required=True,
        help="Source directory containing markdown files",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force re-ingestion of existing documents",
    )

    args = parser.parse_args()

    try:
        ingest_rules(args.source, force=args.force)
    except Exception as e:
        logger.error(f"Ingestion failed: {e}", exc_info=True)
        print(f"❌ Ingestion failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
