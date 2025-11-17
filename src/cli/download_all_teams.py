"""CLI command to download all team rule PDFs from Warhammer Community.

Usage:
    python -m src.cli download-all-teams
    python -m src.cli download-all-teams --dry-run
    python -m src.cli download-all-teams --force
"""

import json
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.cli.download_team import download_team_internal
from src.lib.logging import get_logger

logger = get_logger(__name__)

# Warhammer Community API endpoint
WH_API_URL = "https://www.warhammer-community.com/api/search/downloads/"
WH_ASSETS_BASE = "https://assets.warhammer-community.com/"


def normalize_team_name(title: str) -> str:
    """Normalize team title to filename format.

    Args:
        title: Team title from API (e.g., "Vespid Stingwings")

    Returns:
        Normalized filename (e.g., "vespid_stingwings")
    """
    # Convert to lowercase
    normalized = title.lower()

    # Replace spaces and special characters with underscores
    normalized = re.sub(r'[^\w\s-]', '', normalized)
    normalized = re.sub(r'[\s-]+', '_', normalized)

    return normalized


def fetch_team_list() -> list[dict]:
    """Fetch list of all teams from Warhammer Community API.

    Returns:
        List of team data dicts from API

    Raises:
        HTTPError: API request failed
        URLError: Network error
    """
    payload = {
        "index": "downloads_v2",
        "searchTerm": "",
        "gameSystem": "kill-team",
        "language": "english"
    }

    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Kill-Team-Rules-Bot/1.0 (Bulk Download Tool)'
    }

    logger.info(f"Fetching team list from {WH_API_URL}")

    # Validate URL scheme (security: prevent file:// access)
    from urllib.parse import urlparse
    parsed = urlparse(WH_API_URL)
    if parsed.scheme not in ('http', 'https'):
        raise ValueError(f"Invalid URL scheme: {parsed.scheme}. Only http/https allowed.")

    request = Request(
        WH_API_URL,
        data=json.dumps(payload).encode('utf-8'),
        headers=headers,
        method='POST'
    )

    try:
        with urlopen(request, timeout=30) as response:  # nosec B310 (scheme validated above)
            if response.status != 200:
                raise HTTPError(
                    WH_API_URL,
                    response.status,
                    f"HTTP {response.status}",
                    response.headers,
                    None
                )

            data = json.loads(response.read().decode('utf-8'))

            if 'hits' not in data:
                raise ValueError("Invalid API response: missing 'hits' field")

            logger.info(f"Fetched {len(data['hits'])} results from API")
            return data['hits']

    except HTTPError as e:
        logger.error(f"HTTP error fetching team list: {e}")
        raise
    except URLError as e:
        logger.error(f"Network error fetching team list: {e}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse API response: {e}")
        raise


def filter_team_rules(hits: list[dict]) -> list[dict]:
    """Filter API results for team-rules downloads.

    Args:
        hits: Raw API results

    Returns:
        Filtered list containing only team-rules entries
    """
    team_rules = []

    for hit in hits:
        # Check if download_categories contains "team-rules"
        download_categories = hit.get('download_categories', [])

        # Check both string format and object format
        is_team_rules = False
        for category in download_categories:
            if isinstance(category, str) and category == "team-rules" or isinstance(category, dict) and category.get('slug') == "team-rules":
                is_team_rules = True
                break

        if is_team_rules:
            team_rules.append(hit)

    logger.info(f"Filtered to {len(team_rules)} team-rules entries")
    return team_rules


def get_existing_team_date(team_filename: str) -> date | None:
    """Get last_update_date from existing team markdown file.

    Args:
        team_filename: Normalized team filename (e.g., "pathfinders")

    Returns:
        Date from YAML frontmatter, or None if file doesn't exist
    """
    team_file = Path("extracted-rules") / "team" / f"{team_filename}.md"

    if not team_file.exists():
        return None

    try:
        content = team_file.read_text(encoding='utf-8')

        # Parse YAML frontmatter
        if not content.startswith('---'):
            logger.warning(f"{team_file} missing YAML frontmatter")
            return None

        # Extract YAML block
        yaml_end = content.find('---', 3)
        if yaml_end == -1:
            logger.warning(f"{team_file} malformed YAML frontmatter")
            return None

        yaml_block = content[3:yaml_end]

        # Find last_update_date field
        for line in yaml_block.split('\n'):
            if line.strip().startswith('last_update_date:'):
                date_str = line.split(':', 1)[1].strip().strip('"')
                return datetime.strptime(date_str, '%Y-%m-%d').date()

        logger.warning(f"{team_file} missing last_update_date field")
        return None

    except Exception as e:
        logger.error(f"Error reading {team_file}: {e}")
        return None


def parse_api_date(hit: dict) -> date | None:
    """Parse last_updated date from API hit.

    Args:
        hit: Team data from API

    Returns:
        Date object or None if parsing fails
    """
    # Try to get last_updated from id.last_updated (DD/MM/YYYY format)
    last_updated_str = hit.get('id', {}).get('last_updated')

    if last_updated_str:
        try:
            # Parse DD/MM/YYYY format
            return datetime.strptime(last_updated_str, '%d/%m/%Y').date()
        except ValueError:
            logger.warning(f"Failed to parse last_updated: {last_updated_str}")

    # Fallback to timestamp if last_updated not available
    api_timestamp = hit.get('date', 0)
    if api_timestamp > 0:
        return datetime.fromtimestamp(api_timestamp).date()

    logger.warning("No valid date found in API hit")
    return None


def should_download_team(
    hit: dict,
    force: bool = False
) -> tuple[bool, str]:
    """Check if team should be downloaded.

    Args:
        hit: Team data from API
        force: If True, always download

    Returns:
        Tuple of (should_download: bool, reason: str)
    """
    title = hit.get('id', {}).get('title', 'Unknown')
    team_filename = normalize_team_name(title)

    # Check if file exists
    existing_date = get_existing_team_date(team_filename)

    if existing_date is None:
        return True, "new file"

    if force:
        return True, "forced"

    # Compare dates
    api_date = parse_api_date(hit)

    if api_date is None:
        logger.warning(f"No API date for {title}, downloading anyway")
        return True, "no API date"

    if api_date > existing_date:
        return True, f"updated: {api_date} > {existing_date}"
    else:
        return False, f"up-to-date: {existing_date}"


def download_all_teams(dry_run: bool = False, force: bool = False) -> None:
    """Download all team rule PDFs from Warhammer Community.

    Args:
        dry_run: If True, only show what would be downloaded
        force: If True, re-download all teams regardless of date
    """
    start_time = time.time()

    # Step 1: Fetch team list
    print("Fetching team list from Warhammer Community...")
    try:
        hits = fetch_team_list()
    except Exception as e:
        logger.error(f"Failed to fetch team list: {e}", exc_info=True)
        print(f"❌ Failed to fetch team list: {e}")
        sys.exit(1)

    # Step 2: Filter for team-rules
    team_rules = filter_team_rules(hits)

    if not team_rules:
        print("❌ No team rules found in API results")
        sys.exit(1)

    print(f"✓ Found {len(team_rules)} teams")

    # Step 3: Check which teams need downloading
    print("\nChecking existing files...")

    teams_to_download = []
    teams_skipped = []

    for hit in team_rules:
        title = hit.get('id', {}).get('title', 'Unknown')
        should_download, reason = should_download_team(hit, force=force)

        if should_download:
            teams_to_download.append((hit, reason))
        else:
            teams_skipped.append((title, reason))

    print(f"  - {len(teams_skipped)} teams up-to-date (skipped)")
    print(f"  - {len(teams_to_download)} teams to download")

    # Dry-run mode: show details and exit
    if dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN - No downloads will be performed")
        print("=" * 60)

        if teams_to_download:
            print(f"\nTeams to download ({len(teams_to_download)}):")
            for hit, reason in teams_to_download:
                title = hit.get('id', {}).get('title', 'Unknown')
                print(f"  ✓ {title} ({reason})")

        if teams_skipped:
            print(f"\nTeams up-to-date ({len(teams_skipped)}):")
            for title, reason in teams_skipped:
                print(f"  ⊘ {title} ({reason})")

        print("\n" + "=" * 60)
        print("Summary (dry-run):")
        print(f"  Would download: {len(teams_to_download)} teams")
        print(f"  Already up-to-date: {len(teams_skipped)} teams")
        print(f"  Total teams: {len(team_rules)} teams")
        print("=" * 60)
        return

    # Step 4: Download teams
    if not teams_to_download:
        print("\n✓ All teams are up-to-date")
        return

    print("\nDownloading teams...")

    results_success = []
    results_failed = []
    total_tokens = 0
    total_cost = 0.0

    for idx, (hit, _reason) in enumerate(teams_to_download, 1):
        title = hit.get('id', {}).get('title', 'Unknown')
        file_name = hit.get('id', {}).get('file', '')

        if not file_name:
            logger.error(f"Missing file field for {title}")
            print(f"[{idx}/{len(teams_to_download)}] {title}... ❌ Missing file URL")
            results_failed.append((title, "Missing file URL in API response"))
            continue

        url = f"{WH_ASSETS_BASE}{file_name}"

        # Extract team name and date from API data
        normalized_team_name = normalize_team_name(title)
        api_date = parse_api_date(hit)

        if api_date is None:
            logger.error(f"No valid date for {title}")
            print(f"[{idx}/{len(teams_to_download)}] {title}... ❌ No valid date in API")
            results_failed.append((title, "No valid date in API response"))
            continue

        print(f"[{idx}/{len(teams_to_download)}] {title}...", end=" ", flush=True)

        try:
            result = download_team_internal(
                url,
                model="gemini-2.5-pro",
                verbose=False,
                team_name=normalized_team_name,
                update_date=api_date,
            )

            if result["success"]:
                latency_s = result["latency_ms"] / 1000
                print(f"✓ ({latency_s:.1f}s, ${result['cost_usd']:.2f})")

                results_success.append(title)
                total_tokens += result["tokens"]
                total_cost += result["cost_usd"]

                logger.info(f"Downloaded {title}", extra={
                    "team": title,
                    "tokens": result["tokens"],
                    "cost": result["cost_usd"]
                })
            else:
                print(f"❌ {result['error']}")
                results_failed.append((title, result['error']))
                logger.error(f"Failed to download {title}: {result['error']}")

        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            results_failed.append((title, str(e)))
            logger.error(f"Unexpected error downloading {title}: {e}", exc_info=True)

    # Step 5: Output summary
    elapsed_time = time.time() - start_time
    elapsed_mins = int(elapsed_time // 60)
    elapsed_secs = int(elapsed_time % 60)

    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Downloaded: {len(results_success)} teams")
    print(f"  Skipped: {len(teams_skipped)} teams (up-to-date)")
    print(f"  Failed: {len(results_failed)} teams")
    print(f"  Total time: {elapsed_mins}m {elapsed_secs}s")
    print(f"  Total cost: ${total_cost:.2f}")
    if total_tokens > 0:
        print(f"  Total tokens: {total_tokens:,}")
    print("=" * 60)

    if results_failed:
        print("\nFailed teams:")
        for title, error in results_failed:
            print(f"  - {title}: {error}")

    logger.info(
        "Bulk download complete",
        extra={
            "downloaded": len(results_success),
            "skipped": len(teams_skipped),
            "failed": len(results_failed),
            "total_time_seconds": elapsed_time,
            "total_cost_usd": total_cost,
            "total_tokens": total_tokens,
        }
    )

    # Exit with error code if any downloads failed
    if results_failed:
        sys.exit(1)


def main() -> None:
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
