"""CLI command to download all team rule PDFs from Warhammer Community.

Usage:
    python -m src.cli download-all-teams
    python -m src.cli download-all-teams --dry-run
    python -m src.cli download-all-teams --force
"""

import sys

from src.cli.download.bulk_processor import BulkDownloadProcessor
from src.lib.logging import get_logger

logger = get_logger(__name__)


def download_all_teams(dry_run: bool = False, force: bool = False) -> None:
    """Download all team rule PDFs from Warhammer Community.

    Args:
        dry_run: If True, only show what would be downloaded
        force: If True, re-download all teams regardless of date
    """
    # Use bulk download processor
    processor = BulkDownloadProcessor(model="gemini-2.5-pro")

    try:
        summary = processor.process_bulk_download(
            dry_run=dry_run,
            force=force,
            verbose=True,
        )

        # Exit with error code if any downloads failed
        if summary.failed > 0:
            sys.exit(1)

    except Exception as e:
        logger.error(f"Bulk download failed: {e}", exc_info=True)
        print(f"❌ Failed: {e}")
        sys.exit(1)


def main():
    """Main entry point for download_all_teams CLI."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Download all Kill Team rule PDFs from Warhammer Community"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check what needs updating without downloading",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download all teams regardless of date",
    )

    args = parser.parse_args()

    try:
        download_all_teams(dry_run=args.dry_run, force=args.force)
    except Exception as e:
        logger.error(f"download-all-teams failed: {e}", exc_info=True)
        print(f"❌ Failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
