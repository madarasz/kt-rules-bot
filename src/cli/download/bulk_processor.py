"""Bulk download processor for team rules.

Extracted from download_all_teams.py to follow Single Responsibility Principle.
"""

import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Tuple, Dict, Optional

from src.cli.download.api_client import WarhammerCommunityAPI
from src.cli.download.extraction_pipeline import ExtractionPipeline
from src.cli.download.team_name_extractor import TeamNameExtractor
from src.lib.logging import get_logger

logger = get_logger(__name__)


@dataclass
class BulkDownloadSummary:
    """Summary of bulk download operation.

    Attributes:
        downloaded: Number of teams downloaded
        skipped: Number of teams skipped (up-to-date)
        failed: Number of teams failed
        total_time_seconds: Total elapsed time
        total_cost_usd: Total estimated cost
        total_tokens: Total tokens used
        failed_teams: List of (team_name, error_message) tuples
    """

    downloaded: int
    skipped: int
    failed: int
    total_time_seconds: float
    total_cost_usd: float
    total_tokens: int
    failed_teams: List[Tuple[str, str]]


class BulkDownloadProcessor:
    """Processes bulk downloads of team rules.

    Orchestrates downloading multiple teams from Warhammer Community API.
    """

    def __init__(
        self,
        model: str = "gemini-2.5-pro",
        output_dir: Path = None,
    ):
        """Initialize bulk download processor.

        Args:
            model: LLM model to use for extraction
            output_dir: Output directory for markdown files
        """
        self.model = model
        self.output_dir = output_dir or Path("extracted-rules") / "team"
        self.pipeline = ExtractionPipeline(model=model, output_dir=self.output_dir)

    @staticmethod
    def get_existing_team_date(team_filename: str, output_dir: Path = None) -> Optional[date]:
        """Get last_update_date from existing team markdown file.

        Args:
            team_filename: Normalized team filename (e.g., "pathfinders")
            output_dir: Output directory for team files

        Returns:
            Date from YAML frontmatter, or None if file doesn't exist
        """
        if output_dir is None:
            output_dir = Path("extracted-rules") / "team"

        team_file = output_dir / f"{team_filename}.md"

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
            from datetime import datetime
            for line in yaml_block.split('\n'):
                if line.strip().startswith('last_update_date:'):
                    date_str = line.split(':', 1)[1].strip().strip('"')
                    return datetime.strptime(date_str, '%Y-%m-%d').date()

            logger.warning(f"{team_file} missing last_update_date field")
            return None

        except Exception as e:
            logger.error(f"Error reading {team_file}: {e}")
            return None

    @staticmethod
    def should_download_team(
        hit: Dict,
        force: bool = False,
        output_dir: Path = None
    ) -> Tuple[bool, str]:
        """Check if team should be downloaded.

        Args:
            hit: Team data from API
            force: If True, always download
            output_dir: Output directory for team files

        Returns:
            Tuple of (should_download: bool, reason: str)
        """
        title = WarhammerCommunityAPI.get_team_title(hit)
        team_filename = TeamNameExtractor.normalize_team_name(title)

        # Check if file exists
        existing_date = BulkDownloadProcessor.get_existing_team_date(
            team_filename,
            output_dir
        )

        if existing_date is None:
            return True, "new file"

        if force:
            return True, "forced"

        # Compare dates
        api_date = WarhammerCommunityAPI.parse_date(hit)

        if api_date is None:
            logger.warning(f"No API date for {title}, downloading anyway")
            return True, "no API date"

        if api_date > existing_date:
            return True, f"updated: {api_date} > {existing_date}"
        else:
            return False, f"up-to-date: {existing_date}"

    def process_bulk_download(
        self,
        dry_run: bool = False,
        force: bool = False,
        verbose: bool = True,
    ) -> BulkDownloadSummary:
        """Process bulk download of all teams.

        Args:
            dry_run: If True, only show what would be downloaded
            force: If True, re-download all teams regardless of date
            verbose: Whether to print progress messages

        Returns:
            BulkDownloadSummary with operation results

        Raises:
            Exception: If API fetch fails or other critical error
        """
        start_time = time.time()

        # Step 1: Fetch team list
        if verbose:
            print("Fetching team list from Warhammer Community...")

        hits = WarhammerCommunityAPI.fetch_team_list()
        team_rules = WarhammerCommunityAPI.filter_team_rules(hits)

        if not team_rules:
            raise ValueError("No team rules found in API results")

        if verbose:
            print(f"✓ Found {len(team_rules)} teams")

        # Step 2: Check which teams need downloading
        if verbose:
            print("\nChecking existing files...")

        teams_to_download = []
        teams_skipped = []

        for hit in team_rules:
            title = WarhammerCommunityAPI.get_team_title(hit)
            should_download, reason = self.should_download_team(hit, force=force, output_dir=self.output_dir)

            if should_download:
                teams_to_download.append((hit, reason))
            else:
                teams_skipped.append((title, reason))

        if verbose:
            print(f"  - {len(teams_skipped)} teams up-to-date (skipped)")
            print(f"  - {len(teams_to_download)} teams to download")

        # Dry-run mode: show details and return
        if dry_run:
            if verbose:
                self._print_dry_run_summary(teams_to_download, teams_skipped, team_rules)

            return BulkDownloadSummary(
                downloaded=0,
                skipped=len(teams_skipped),
                failed=0,
                total_time_seconds=time.time() - start_time,
                total_cost_usd=0.0,
                total_tokens=0,
                failed_teams=[],
            )

        # Step 3: Download teams
        if not teams_to_download:
            if verbose:
                print("\n✓ All teams are up-to-date")

            return BulkDownloadSummary(
                downloaded=0,
                skipped=len(teams_skipped),
                failed=0,
                total_time_seconds=time.time() - start_time,
                total_cost_usd=0.0,
                total_tokens=0,
                failed_teams=[],
            )

        if verbose:
            print(f"\nDownloading teams...")

        results_success = []
        results_failed = []
        total_tokens = 0
        total_cost = 0.0

        for idx, (hit, reason) in enumerate(teams_to_download, 1):
            title = WarhammerCommunityAPI.get_team_title(hit)
            url = WarhammerCommunityAPI.get_pdf_url(hit)

            if not url:
                logger.error(f"Missing file URL for {title}")
                if verbose:
                    print(f"[{idx}/{len(teams_to_download)}] {title}... ❌ Missing file URL")
                results_failed.append((title, "Missing file URL in API response"))
                continue

            normalized_team_name = TeamNameExtractor.normalize_team_name(title)
            api_date = WarhammerCommunityAPI.parse_date(hit)

            if api_date is None:
                logger.error(f"No valid date for {title}")
                if verbose:
                    print(f"[{idx}/{len(teams_to_download)}] {title}... ❌ No valid date in API")
                results_failed.append((title, "No valid date in API response"))
                continue

            if verbose:
                print(f"[{idx}/{len(teams_to_download)}] {title}...", end=" ", flush=True)

            try:
                result = self.pipeline.extract_from_url(
                    url=url,
                    team_name=normalized_team_name,
                    update_date=api_date,
                    verbose=False,
                )

                if result.success:
                    latency_s = result.latency_ms / 1000
                    if verbose:
                        print(f"✓ ({latency_s:.1f}s, ${result.cost_usd:.2f})")

                    results_success.append(title)
                    total_tokens += result.tokens
                    total_cost += result.cost_usd

                    logger.info(f"Downloaded {title}", extra={
                        "team": title,
                        "tokens": result.tokens,
                        "cost": result.cost_usd
                    })
                else:
                    if verbose:
                        print(f"❌ {result.error}")
                    results_failed.append((title, result.error))
                    logger.error(f"Failed to download {title}: {result.error}")

            except Exception as e:
                if verbose:
                    print(f"❌ Unexpected error: {e}")
                results_failed.append((title, str(e)))
                logger.error(f"Unexpected error downloading {title}: {e}", exc_info=True)

        # Step 4: Return summary
        elapsed_time = time.time() - start_time

        if verbose:
            self._print_final_summary(
                results_success,
                teams_skipped,
                results_failed,
                elapsed_time,
                total_cost,
                total_tokens
            )

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

        return BulkDownloadSummary(
            downloaded=len(results_success),
            skipped=len(teams_skipped),
            failed=len(results_failed),
            total_time_seconds=elapsed_time,
            total_cost_usd=total_cost,
            total_tokens=total_tokens,
            failed_teams=results_failed,
        )

    @staticmethod
    def _print_dry_run_summary(teams_to_download, teams_skipped, team_rules):
        """Print dry-run summary."""
        print("\n" + "=" * 60)
        print("DRY RUN - No downloads will be performed")
        print("=" * 60)

        if teams_to_download:
            print(f"\nTeams to download ({len(teams_to_download)}):")
            for hit, reason in teams_to_download:
                title = WarhammerCommunityAPI.get_team_title(hit)
                print(f"  ✓ {title} ({reason})")

        if teams_skipped:
            print(f"\nTeams up-to-date ({len(teams_skipped)}):")
            for title, reason in teams_skipped:
                print(f"  ⊘ {title} ({reason})")

        print("\n" + "=" * 60)
        print(f"Summary (dry-run):")
        print(f"  Would download: {len(teams_to_download)} teams")
        print(f"  Already up-to-date: {len(teams_skipped)} teams")
        print(f"  Total teams: {len(team_rules)} teams")
        print("=" * 60)

    @staticmethod
    def _print_final_summary(results_success, teams_skipped, results_failed, elapsed_time, total_cost, total_tokens):
        """Print final summary."""
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
