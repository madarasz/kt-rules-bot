"""CLI command to download and extract team rule PDFs.

Usage:
    python -m src.cli download-team https://assets.warhammer-community.com/.../teamrules.pdf
"""

import re
import sys
from datetime import date, datetime
from typing import Optional

from src.cli.download.extraction_pipeline import ExtractionPipeline
from src.lib.logging import get_logger
from src.lib.constants import PDF_EXTRACTION_PROVIDERS

logger = get_logger(__name__)


def extract_date_from_url(url: str) -> Optional[date]:
    """Extract date from Warhammer Community URL pattern.

    Args:
        url: PDF URL (e.g., containing 'eng_jul25_')

    Returns:
        Date object if found, None otherwise

    Examples:
        eng_jul25_ -> 2025-07-23 (last day of July 2025)
        eng_jan24_ -> 2024-01-31 (last day of January 2024)
    """
    # Pattern: eng_<month><year>_
    pattern = r'eng_([a-z]{3})(\d{2})_'
    match = re.search(pattern, url.lower())

    if not match:
        return None

    month_abbr = match.group(1)
    year_short = match.group(2)

    # Map month abbreviations
    month_map = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
        'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
        'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    }

    month = month_map.get(month_abbr)
    if not month:
        return None

    # Convert 2-digit year to 4-digit (assume 20xx)
    year = 2000 + int(year_short)

    # Use last day of month as default
    # Days in month (handle leap years for Feb)
    days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if month == 2 and year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
        day = 29  # Leap year
    else:
        day = days_in_month[month - 1]

    try:
        return date(year, month, day)
    except ValueError:
        return None


# Keep these utility functions for backward compatibility
# (used by download_all_teams.py which imports them directly)


def download_team_internal(
    url: str,
    model: str = "gemini-2.5-pro",
    verbose: bool = True,
    team_name: Optional[str] = None,
    update_date: Optional[date] = None,
) -> dict:
    """Download and extract team rule PDF (internal function).

    Args:
        url: PDF URL
        model: LLM model to use for extraction
        verbose: If True, print progress messages
        team_name: Optional team name override (if None, extracts from markdown)
        update_date: Optional update date override (if None, extracts from URL or uses today)

    Returns:
        Dictionary with results:
        {
            "success": bool,
            "team_name": str,
            "output_file": str,
            "tokens": int,
            "latency_ms": int,
            "cost_usd": float,
            "error": Optional[str],
            "validation_warnings": list[str]
        }
    """
    # Use extraction pipeline
    pipeline = ExtractionPipeline(model=model)

    # Determine update date if needed (extract from URL)
    if update_date is None and team_name is None:
        # Only extract date from URL if not provided
        update_date = extract_date_from_url(url)

    result = pipeline.extract_from_url(
        url=url,
        team_name=team_name,
        update_date=update_date,
        verbose=verbose,
    )

    # Convert ExtractionResult to dict for backward compatibility
    return {
        "success": result.success,
        "team_name": result.team_name,
        "output_file": result.output_file,
        "tokens": result.tokens,
        "latency_ms": result.latency_ms,
        "cost_usd": result.cost_usd,
        "error": result.error,
        "validation_warnings": result.validation_warnings,
    }


def download_team(
    url: str,
    model: str = "gemini-2.5-pro",
    team_name: Optional[str] = None,
    update_date: Optional[str] = None,
) -> None:
    """Download and extract team rule PDF (CLI entry point).

    Args:
        url: PDF URL
        model: LLM model to use for extraction
        team_name: Optional team name override
        update_date: Optional update date override (YYYY-MM-DD format)
    """
    # Parse update_date string to date object
    parsed_date = None
    if update_date:
        try:
            parsed_date = datetime.strptime(update_date, '%Y-%m-%d').date()
        except ValueError:
            print(f"❌ Invalid date format: {update_date}. Expected YYYY-MM-DD")
            sys.exit(1)

    result = download_team_internal(
        url,
        model,
        verbose=True,
        team_name=team_name,
        update_date=parsed_date,
    )

    if not result["success"]:
        print(f"❌ {result['error']}")
        sys.exit(1)


def main():
    """Main entry point for download_team CLI."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Download and extract Kill Team rule PDFs"
    )
    parser.add_argument(
        "url",
        help="PDF URL (must be HTTPS)",
    )
    parser.add_argument(
        "--model",
        default="gemini-2.5-pro",
        choices=PDF_EXTRACTION_PROVIDERS,
        help="LLM model to use for extraction (default: gemini-2.5-pro)",
    )
    parser.add_argument(
        "--team-name",
        help="Team name override (default: extract from markdown)",
    )
    parser.add_argument(
        "--update-date",
        help="Update date override in YYYY-MM-DD format (default: extract from URL or use today)",
    )

    args = parser.parse_args()

    try:
        download_team(
            args.url,
            model=args.model,
            team_name=args.team_name,
            update_date=args.update_date,
        )
    except Exception as e:
        logger.error(f"download-team failed: {e}", exc_info=True)
        print(f"❌ Failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
