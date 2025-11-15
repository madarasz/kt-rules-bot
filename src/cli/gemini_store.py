"""CLI commands for Gemini File Search store management.

Commands:
- create: Create a new file search store
- upload: Upload markdown documents to store
- refresh: Re-upload changed documents
- info: Display store information
- delete: Delete the file search store
"""

import sys
from pathlib import Path

from src.lib.config import get_config
from src.lib.logging import get_logger
from src.services.llm.gemini_file_search import (
    GeminiFileSearchService,
    FileSearchStoreError,
)

logger = get_logger(__name__)


def cmd_create():
    """Create a new file search store."""
    print("🔍 Creating Gemini File Search store...")

    config = get_config()

    if not config.google_api_key:
        print("❌ Error: GOOGLE_API_KEY not found in config/.env")
        print("   Add your Google API key to config/.env:")
        print("   GOOGLE_API_KEY=AIza...")
        sys.exit(1)

    try:
        service = GeminiFileSearchService(api_key=config.google_api_key)
        store_id = service.create_store(display_name="kill-team-rules")

        print(f"✅ Store created successfully!")
        print(f"   Store ID: {store_id}")
        print(f"   Saved to: data/gemini_file_search_store_id.txt")
        print()
        print("Next step: Upload documents with:")
        print("  python -m src.cli gemini-store upload")

    except FileSearchStoreError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        logger.exception("gemini_store_create_failed")
        sys.exit(1)


def cmd_upload(documents_dir: str = "extracted-rules"):
    """Upload documents to file search store.

    Args:
        documents_dir: Path to directory containing markdown files
    """
    print(f"📤 Uploading documents from {documents_dir}...")

    config = get_config()

    if not config.google_api_key:
        print("❌ Error: GOOGLE_API_KEY not found in config/.env")
        sys.exit(1)

    try:
        service = GeminiFileSearchService(api_key=config.google_api_key)
        stats = service.upload_documents(documents_dir=documents_dir)

        print()
        print("📊 Upload Statistics:")
        print(f"   Files uploaded: {stats.files_uploaded}")
        print(f"   Files skipped:  {stats.files_skipped} (unchanged)")
        print(f"   Files failed:   {stats.files_failed}")
        print()
        print("💰 Cost Estimation:")
        print(f"   Estimated tokens: {stats.total_tokens:,}")
        print(f"   Estimated cost:   ${stats.estimated_cost_usd:.4f} USD")
        print(f"   (Embeddings: $0.15 per 1M tokens)")

        if stats.errors:
            print()
            print("⚠️  Errors:")
            for error in stats.errors:
                print(f"   - {error}")

        if stats.files_uploaded > 0:
            print()
            print("✅ Upload complete!")
            print("   You can now use file-search models:")
            print("   - gemini-2.5-pro-file-search")
            print("   - gemini-2.5-flash-file-search")

    except FileSearchStoreError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        logger.exception("gemini_store_upload_failed")
        sys.exit(1)


def cmd_refresh(documents_dir: str = "extracted-rules"):
    """Refresh documents in file search store (upload only changed files).

    Args:
        documents_dir: Path to directory containing markdown files
    """
    print(f"🔄 Refreshing documents from {documents_dir}...")
    print("   (Only changed files will be re-uploaded)")
    print()

    # Refresh is the same as upload (upload_documents already handles hashing)
    cmd_upload(documents_dir=documents_dir)


def cmd_info():
    """Display file search store information."""
    print("ℹ️  File Search Store Information")
    print()

    config = get_config()

    if not config.google_api_key:
        print("❌ Error: GOOGLE_API_KEY not found in config/.env")
        sys.exit(1)

    try:
        service = GeminiFileSearchService(api_key=config.google_api_key)
        info = service.get_store_info()

        print(f"   Store ID:      {info['store_id']}")
        print(f"   Display Name:  {info['display_name']}")
        print(f"   Created:       {info['create_time']}")
        print(f"   Last Updated:  {info['update_time']}")
        print()
        print("To upload documents:")
        print("  python -m src.cli gemini-store upload")

    except FileSearchStoreError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        logger.exception("gemini_store_info_failed")
        sys.exit(1)


def cmd_delete():
    """Delete file search store."""
    print("⚠️  Warning: This will permanently delete the file search store!")
    print("   You will need to create a new store and re-upload all documents.")
    print()

    response = input("Are you sure? (type 'yes' to confirm): ")

    if response.lower() != "yes":
        print("❌ Deletion cancelled")
        return

    config = get_config()

    if not config.google_api_key:
        print("❌ Error: GOOGLE_API_KEY not found in config/.env")
        sys.exit(1)

    try:
        service = GeminiFileSearchService(api_key=config.google_api_key)
        service.delete_store()

        print("✅ Store deleted successfully")

    except FileSearchStoreError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        logger.exception("gemini_store_delete_failed")
        sys.exit(1)


def main():
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        print("Gemini File Search Store Management")
        print()
        print("Usage:")
        print("  python -m src.cli.gemini_store <command> [options]")
        print()
        print("Commands:")
        print("  create              Create a new file search store")
        print("  upload [dir]        Upload documents to store (default: extracted-rules/)")
        print("  refresh [dir]       Re-upload changed documents (default: extracted-rules/)")
        print("  info                Display store information")
        print("  delete              Delete the file search store")
        print()
        print("Examples:")
        print("  python -m src.cli.gemini_store create")
        print("  python -m src.cli.gemini_store upload")
        print("  python -m src.cli.gemini_store upload custom-rules/")
        print("  python -m src.cli.gemini_store info")
        sys.exit(1)

    command = sys.argv[1]

    if command == "create":
        cmd_create()
    elif command == "upload":
        documents_dir = sys.argv[2] if len(sys.argv) > 2 else "extracted-rules"
        cmd_upload(documents_dir=documents_dir)
    elif command == "refresh":
        documents_dir = sys.argv[2] if len(sys.argv) > 2 else "extracted-rules"
        cmd_refresh(documents_dir=documents_dir)
    elif command == "info":
        cmd_info()
    elif command == "delete":
        cmd_delete()
    else:
        print(f"❌ Unknown command: {command}")
        print("Run without arguments to see usage")
        sys.exit(1)


if __name__ == "__main__":
    main()
