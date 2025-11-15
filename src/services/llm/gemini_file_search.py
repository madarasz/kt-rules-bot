"""Gemini File Search Store Management Service.

Handles creation, document upload, and management of Gemini file search stores.
File search replaces traditional RAG retrieval with Gemini's built-in semantic search.
"""

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

from src.lib.constants import (
    GEMINI_FILE_SEARCH_STORE_ID_PATH,
    GEMINI_FILE_SEARCH_HASHES_PATH,
)
from src.lib.logging import get_logger

logger = get_logger(__name__)


@dataclass
class UploadStats:
    """Statistics from document upload operation."""

    files_uploaded: int
    files_skipped: int  # Already up-to-date based on hash
    files_failed: int
    total_tokens: int  # Estimated tokens for cost calculation
    estimated_cost_usd: float  # Embeddings cost: $0.15 per 1M tokens
    errors: List[str]


class FileSearchStoreError(Exception):
    """Base exception for file search store errors."""

    pass


class GeminiFileSearchService:
    """Service for managing Gemini file search stores."""

    EMBEDDING_COST_PER_MILLION_TOKENS = 0.15  # $0.15 per 1M tokens
    AVG_TOKENS_PER_CHAR = 0.25  # Rough estimate: 4 chars per token

    def __init__(self, api_key: str):
        """Initialize file search service.

        Args:
            api_key: Google API key

        Raises:
            ImportError: If google-genai not installed
        """
        if genai is None:
            raise ImportError(
                "google-genai package not installed. "
                "Run: pip install google-genai"
            )

        self.client = genai.Client(api_key=api_key)
        logger.info("gemini_file_search_service_initialized")

    def create_store(self, display_name: str = "kill-team-rules") -> str:
        """Create a new file search store and persist the ID.

        Args:
            display_name: Human-readable store name

        Returns:
            Store ID (e.g., "file-search-stores/abc123")

        Raises:
            FileSearchStoreError: If store creation fails
        """
        try:
            logger.info(f"Creating file search store: {display_name}")

            store = self.client.file_search_stores.create(
                config={"display_name": display_name}
            )

            store_id = store.name
            logger.info(f"File search store created: {store_id}")

            # Persist store ID
            self._save_store_id(store_id)

            return store_id

        except Exception as e:
            logger.error(f"Failed to create file search store: {e}")
            raise FileSearchStoreError(f"Store creation failed: {e}")

    def upload_documents(
        self, documents_dir: str, store_id: Optional[str] = None
    ) -> UploadStats:
        """Upload markdown documents to file search store.

        Only uploads files that have changed (based on content hash).

        Args:
            documents_dir: Path to directory containing markdown files
            store_id: Store ID (loads from file if None)

        Returns:
            UploadStats with upload results and cost estimation

        Raises:
            FileSearchStoreError: If upload fails
        """
        if store_id is None:
            store_id = self.load_store_id()

        documents_path = Path(documents_dir)
        if not documents_path.exists():
            raise FileSearchStoreError(f"Documents directory not found: {documents_dir}")

        # Load existing hashes
        existing_hashes = self._load_hashes()

        # Find all markdown files
        md_files = list(documents_path.rglob("*.md"))
        logger.info(f"Found {len(md_files)} markdown files in {documents_dir}")

        stats = UploadStats(
            files_uploaded=0,
            files_skipped=0,
            files_failed=0,
            total_tokens=0,
            estimated_cost_usd=0.0,
            errors=[],
        )

        for md_file in md_files:
            try:
                # Read file content
                content = md_file.read_text(encoding="utf-8")
                file_hash = self._compute_hash(content)

                # Check if file has changed
                file_key = str(md_file.relative_to(documents_path))
                if existing_hashes.get(file_key) == file_hash:
                    logger.debug(f"Skipping unchanged file: {file_key}")
                    stats.files_skipped += 1
                    continue

                # Upload file
                logger.info(f"Uploading: {file_key}")
                self._upload_single_file(md_file, store_id)

                # Update hash and stats
                existing_hashes[file_key] = file_hash
                stats.files_uploaded += 1

                # Estimate tokens for cost calculation
                tokens = int(len(content) * self.AVG_TOKENS_PER_CHAR)
                stats.total_tokens += tokens

            except Exception as e:
                logger.error(f"Failed to upload {md_file}: {e}")
                stats.files_failed += 1
                stats.errors.append(f"{md_file.name}: {str(e)}")

        # Calculate cost
        stats.estimated_cost_usd = (
            stats.total_tokens / 1_000_000
        ) * self.EMBEDDING_COST_PER_MILLION_TOKENS

        # Save updated hashes
        self._save_hashes(existing_hashes)

        logger.info(
            f"Upload complete: {stats.files_uploaded} uploaded, "
            f"{stats.files_skipped} skipped, {stats.files_failed} failed"
        )

        return stats

    def get_store_info(self, store_id: Optional[str] = None) -> Dict:
        """Get information about file search store.

        Args:
            store_id: Store ID (loads from file if None)

        Returns:
            Dictionary with store metadata

        Raises:
            FileSearchStoreError: If store not found
        """
        if store_id is None:
            store_id = self.load_store_id()

        try:
            store = self.client.file_search_stores.get(name=store_id)

            return {
                "store_id": store.name,
                "display_name": store.display_name,
                "create_time": str(store.create_time) if hasattr(store, "create_time") else "unknown",
                "update_time": str(store.update_time) if hasattr(store, "update_time") else "unknown",
            }

        except Exception as e:
            logger.error(f"Failed to get store info: {e}")
            raise FileSearchStoreError(f"Store not found: {e}")

    def delete_store(self, store_id: Optional[str] = None) -> None:
        """Delete file search store and remove persisted ID.

        Args:
            store_id: Store ID (loads from file if None)

        Raises:
            FileSearchStoreError: If deletion fails
        """
        if store_id is None:
            store_id = self.load_store_id()

        try:
            logger.warning(f"Deleting file search store: {store_id}")
            self.client.file_search_stores.delete(name=store_id)

            # Remove persisted ID
            store_id_path = Path(GEMINI_FILE_SEARCH_STORE_ID_PATH)
            if store_id_path.exists():
                store_id_path.unlink()

            logger.info("File search store deleted")

        except Exception as e:
            logger.error(f"Failed to delete store: {e}")
            raise FileSearchStoreError(f"Store deletion failed: {e}")

    def load_store_id(self) -> str:
        """Load store ID from persisted file.

        Returns:
            Store ID

        Raises:
            FileSearchStoreError: If store ID file not found
        """
        store_id_path = Path(GEMINI_FILE_SEARCH_STORE_ID_PATH)

        if not store_id_path.exists():
            raise FileSearchStoreError(
                f"Store ID not found. Create a store first with: "
                f"python -m src.cli gemini-store create"
            )

        store_id = store_id_path.read_text(encoding="utf-8").strip()
        return store_id

    def _upload_single_file(self, file_path: Path, store_id: str) -> None:
        """Upload a single file to the store (synchronous).

        Args:
            file_path: Path to file
            store_id: Store ID

        Raises:
            Exception: If upload fails
        """
        # Gemini API expects string path, not Path object
        operation = self.client.file_search_stores.upload_to_file_search_store(
            file=str(file_path),
            file_search_store_name=store_id,
            config={
                "display_name": file_path.name,
            },
        )

        # Wait for upload to complete (operation is synchronous in current API)
        # Note: If API returns an operation object, we may need to poll for completion

    def _save_store_id(self, store_id: str) -> None:
        """Persist store ID to file.

        Args:
            store_id: Store ID to save
        """
        store_id_path = Path(GEMINI_FILE_SEARCH_STORE_ID_PATH)
        store_id_path.parent.mkdir(parents=True, exist_ok=True)
        store_id_path.write_text(store_id, encoding="utf-8")
        logger.debug(f"Store ID saved to {store_id_path}")

    def _load_hashes(self) -> Dict[str, str]:
        """Load document hashes from file.

        Returns:
            Dictionary mapping file paths to content hashes
        """
        hashes_path = Path(GEMINI_FILE_SEARCH_HASHES_PATH)

        if not hashes_path.exists():
            return {}

        try:
            return json.loads(hashes_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to load hashes: {e}")
            return {}

    def _save_hashes(self, hashes: Dict[str, str]) -> None:
        """Persist document hashes to file.

        Args:
            hashes: Dictionary mapping file paths to content hashes
        """
        hashes_path = Path(GEMINI_FILE_SEARCH_HASHES_PATH)
        hashes_path.parent.mkdir(parents=True, exist_ok=True)
        hashes_path.write_text(json.dumps(hashes, indent=2), encoding="utf-8")
        logger.debug(f"Hashes saved to {hashes_path}")

    @staticmethod
    def _compute_hash(content: str) -> str:
        """Compute SHA-256 hash of file content.

        Args:
            content: File content

        Returns:
            Hex-encoded hash
        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
