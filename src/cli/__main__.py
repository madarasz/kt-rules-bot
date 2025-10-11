"""CLI main entry point - routes commands to appropriate handlers."""

import argparse
import sys

from src.cli.gdpr_delete import delete_user_data
from src.cli.health_check import health_check
from src.cli.ingest_rules import ingest_rules
from src.cli.run_bot import run_bot
from src.cli.test_query import test_query
from src.cli.quality_test import quality_test
from src.cli.rag_test import rag_test
from src.cli.download_team import download_team
from src.cli.download_all_teams import download_all_teams
from src.lib.constants import QUALITY_TEST_JUDGE_MODEL, RAG_MAX_CHUNKS, RAG_MIN_RELEVANCE


def create_parser() -> argparse.ArgumentParser:
    """Create main CLI argument parser with subcommands.

    Returns:
        Configured argument parser
    """
    parser = argparse.ArgumentParser(
        prog="kill-team-bot",
        description="Kill Team Rules Discord Bot - CLI Tools",
        epilog="For command-specific help: kill-team-bot <command> --help",
    )

    # Add version
    parser.add_argument(
        "--version",
        action="version",
        version="Kill Team Bot v1.0.0",
    )

    # Create subcommands
    subparsers = parser.add_subparsers(
        dest="command",
        help="Available commands",
        required=True,
    )

    # Command: run
    run_parser = subparsers.add_parser(
        "run",
        help="Start the Discord bot",
        description="Start the Kill Team Rules Discord bot in dev or production mode",
    )
    run_parser.add_argument(
        "--mode",
        choices=["dev", "production"],
        default="production",
        help="Runtime mode (default: production)",
    )

    # Command: ingest
    ingest_parser = subparsers.add_parser(
        "ingest",
        help="Ingest rules into vector database",
        description="Ingest markdown rules from source directory into vector database",
    )
    ingest_parser.add_argument(
        "source_dir",
        help="Directory containing markdown rule files",
    )
    ingest_parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-ingestion of all documents",
    )

    # Command: query
    query_parser = subparsers.add_parser(
        "query",
        help="Test RAG + LLM pipeline locally",
        description="Test query processing locally without Discord",
    )
    query_parser.add_argument(
        "query",
        help="Query text to test",
    )
    query_parser.add_argument(
        "--provider",
        choices=[
            "claude-sonnet",
            "claude-opus",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gpt-5",
            "gpt-5-mini",
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4o",
            "o3",
            "o3-mini",
            "o4-mini",
        ],
        help="LLM model to use (default: from config)",
    )
    query_parser.add_argument(
        "--max-chunks",
        type=int,
        default=5,
        help="Maximum RAG chunks to retrieve (default: 5)",
    )

    # Command: health
    health_parser = subparsers.add_parser(
        "health",
        help="Check system health",
        description="Check health of Discord bot, vector DB, and LLM provider",
    )
    health_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed health information",
    )
    health_parser.add_argument(
        "--wait-for-discord",
        action="store_true",
        help="Wait for Discord connection (for checking running bot)",
    )

    # Command: gdpr-delete
    gdpr_parser = subparsers.add_parser(
        "gdpr-delete",
        help="Delete user data (GDPR compliance)",
        description="Delete all data for a user (GDPR right to erasure)",
    )
    gdpr_parser.add_argument(
        "user_id",
        help="Discord user ID or hashed user ID",
    )
    gdpr_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Skip confirmation prompt",
    )

    # Command: quality-test
    quality_parser = subparsers.add_parser(
        "quality-test",
        help="Run response quality tests",
        description="Run quality tests for RAG + LLM pipeline",
    )
    quality_parser.add_argument(
        "--test",
        "-t",
        help="Specific test ID to run (default: all tests)",
    )
    quality_parser.add_argument(
        "--model",
        "-m",
        choices=[
            "claude-sonnet",
            "claude-opus",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gpt-5",
            "gpt-5-mini",
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4o",
            "o3",
            "o3-mini",
            "o4-mini",
        ],
        help="Specific model to test (default: from config)",
    )
    quality_parser.add_argument(
        "--all-models",
        action="store_true",
        help="Test all available models",
    )
    quality_parser.add_argument(
        "--judge-model",
        default=QUALITY_TEST_JUDGE_MODEL,
        help=f"Model to use for LLM-based evaluation (default: {QUALITY_TEST_JUDGE_MODEL})",
    )
    quality_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompt",
    )
    quality_parser.add_argument(
        "--runs",
        "-n",
        type=int,
        default=1,
        help="Number of times to run each test (default: 1)",
    )

    # Command: rag-test
    rag_parser = subparsers.add_parser(
        "rag-test",
        help="Test RAG chunk retrieval quality",
        description="Test RAG retrieval quality using IR metrics (MAP, Recall@k, Precision@k)",
    )
    rag_parser.add_argument(
        "--test",
        "-t",
        help="Specific test ID to run (default: all tests)",
    )
    rag_parser.add_argument(
        "--runs",
        "-n",
        type=int,
        default=1,
        help="Number of times to run each test (default: 1)",
    )
    rag_parser.add_argument(
        "--max-chunks",
        type=int,
        default=RAG_MAX_CHUNKS,
        help=f"Maximum chunks to retrieve (default: {RAG_MAX_CHUNKS})",
    )
    rag_parser.add_argument(
        "--min-relevance",
        type=float,
        default=RAG_MIN_RELEVANCE,
        help=f"Minimum relevance threshold (default: {RAG_MIN_RELEVANCE})",
    )
    rag_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompt",
    )

    # Command: download-team
    download_team_parser = subparsers.add_parser(
        "download-team",
        help="Download and extract team rule PDF",
        description="Download team rule PDF from URL and extract to markdown using LLM",
    )
    download_team_parser.add_argument(
        "url",
        help="PDF URL (must be HTTPS)",
    )
    download_team_parser.add_argument(
        "--model",
        default="gemini-2.5-pro",
        choices=["gemini-2.5-pro", "gemini-2.5-flash"],
        help="LLM model to use for extraction (default: gemini-2.5-pro)",
    )
    download_team_parser.add_argument(
        "--team-name",
        help="Team name override (default: extract from markdown)",
    )
    download_team_parser.add_argument(
        "--update-date",
        help="Update date override in YYYY-MM-DD format (default: extract from URL or use today)",
    )

    # Command: download-all-teams
    download_all_teams_parser = subparsers.add_parser(
        "download-all-teams",
        help="Download all team rule PDFs from Warhammer Community",
        description="Automatically download and extract all team rules from Warhammer Community API",
    )
    download_all_teams_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check what needs updating without downloading",
    )
    download_all_teams_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download all teams regardless of date",
    )

    return parser


def main():
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    try:
        # Route to appropriate command handler
        if args.command == "run":
            run_bot(mode=args.mode)

        elif args.command == "ingest":
            ingest_rules(source_dir=args.source_dir, force=args.force)

        elif args.command == "query":
            test_query(
                query=args.query,
                provider=args.provider,
                max_chunks=args.max_chunks,
            )

        elif args.command == "health":
            health_check(
                verbose=args.verbose,
                wait_for_discord=args.wait_for_discord,
            )

        elif args.command == "gdpr-delete":
            delete_user_data(
                user_id=args.user_id,
                confirm=args.confirm,
            )

        elif args.command == "quality-test":
            quality_test(
                test_id=args.test,
                model=args.model,
                all_models=args.all_models,
                judge_model=args.judge_model,
                skip_confirm=args.yes,
                runs=args.runs,
            )

        elif args.command == "rag-test":
            rag_test(
                test_id=args.test,
                runs=args.runs,
                max_chunks=args.max_chunks,
                min_relevance=args.min_relevance,
                yes=args.yes,
            )

        elif args.command == "download-team":
            download_team(
                url=args.url,
                model=args.model,
                team_name=args.team_name,
                update_date=args.update_date,
            )

        elif args.command == "download-all-teams":
            download_all_teams(
                dry_run=args.dry_run,
                force=args.force,
            )

        else:
            parser.print_help()
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
