"""CLI main entry point - routes commands to appropriate handlers."""

import argparse
import sys

from src.cli.gdpr_delete import delete_user_data
from src.cli.health_check import health_check
from src.cli.ingest_rules import ingest_rules
from src.cli.run_bot import run_bot
from src.cli.test_query import test_query


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
            "gpt-4.1",
            "gpt-4o",
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
