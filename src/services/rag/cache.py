"""Caching layer for RAG queries.

5-minute TTL cache for same query + context_key to reduce LLM API calls.
Based on specs/001-we-are-building/contracts/rag-pipeline.md idempotency requirement.
"""

from typing import Dict, Optional
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from uuid import UUID
import hashlib

from src.models.rag_context import RAGContext
from src.lib.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CacheEntry:
    """Cache entry for RAG query result."""

    query_hash: str
    context_key: str
    result: RAGContext
    timestamp: datetime
    ttl_seconds: int = 300  # 5 minutes

    def is_expired(self) -> bool:
        """Check if cache entry is expired.

        Returns:
            True if expired
        """
        now = datetime.now(timezone.utc)
        expiry = self.timestamp + timedelta(seconds=self.ttl_seconds)
        return now > expiry


class RAGCache:
    """In-memory cache for RAG query results."""

    def __init__(self, ttl_seconds: int = 300, max_entries: int = 1000):
        """Initialize cache.

        Args:
            ttl_seconds: Time-to-live in seconds (default: 300 = 5 minutes)
            max_entries: Maximum number of cache entries (LRU eviction)
        """
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._cache: Dict[str, CacheEntry] = {}

        logger.info(
            "rag_cache_initialized",
            ttl_seconds=ttl_seconds,
            max_entries=max_entries,
        )

    def get(self, query: str, context_key: str) -> Optional[RAGContext]:
        """Get cached RAG result.

        Args:
            query: User query
            context_key: Context key (channel_id:user_id)

        Returns:
            Cached RAGContext or None if not found/expired
        """
        cache_key = self._make_cache_key(query, context_key)

        entry = self._cache.get(cache_key)
        if not entry:
            logger.debug("cache_miss", query_hash=cache_key[:16])
            return None

        # Check if expired
        if entry.is_expired():
            del self._cache[cache_key]
            logger.debug("cache_expired", query_hash=cache_key[:16])
            return None

        logger.debug(
            "cache_hit",
            query_hash=cache_key[:16],
            age_seconds=(datetime.now(timezone.utc) - entry.timestamp).total_seconds(),
        )

        return entry.result

    def set(self, query: str, context_key: str, result: RAGContext) -> None:
        """Cache RAG result.

        Args:
            query: User query
            context_key: Context key (channel_id:user_id)
            result: RAGContext to cache
        """
        cache_key = self._make_cache_key(query, context_key)

        # Evict oldest entry if at max capacity
        if len(self._cache) >= self.max_entries and cache_key not in self._cache:
            self._evict_oldest()

        entry = CacheEntry(
            query_hash=cache_key,
            context_key=context_key,
            result=result,
            timestamp=datetime.now(timezone.utc),
            ttl_seconds=self.ttl_seconds,
        )

        self._cache[cache_key] = entry

        logger.debug(
            "cache_set",
            query_hash=cache_key[:16],
            context_key=context_key,
        )

    def invalidate(self, document_id: UUID | None = None) -> int:
        """Invalidate cache entries.

        If document_id is provided, only invalidate entries referencing that document.
        Otherwise, invalidate all entries.

        Args:
            document_id: Document UUID to invalidate (optional)

        Returns:
            Number of entries invalidated
        """
        if document_id is None:
            # Invalidate all
            count = len(self._cache)
            self._cache.clear()
            logger.info("cache_invalidated_all", count=count)
            return count

        # Invalidate entries referencing this document
        to_remove = []
        doc_id_str = str(document_id)

        for cache_key, entry in self._cache.items():
            # Check if any chunk references this document
            for chunk in entry.result.document_chunks:
                if str(chunk.document_id) == doc_id_str:
                    to_remove.append(cache_key)
                    break

        for cache_key in to_remove:
            del self._cache[cache_key]

        if to_remove:
            logger.info(
                "cache_invalidated_by_document",
                document_id=doc_id_str,
                count=len(to_remove),
            )

        return len(to_remove)

    def cleanup_expired(self) -> int:
        """Remove expired entries from cache.

        Returns:
            Number of entries removed
        """
        to_remove = [
            cache_key
            for cache_key, entry in self._cache.items()
            if entry.is_expired()
        ]

        for cache_key in to_remove:
            del self._cache[cache_key]

        if to_remove:
            logger.debug("cache_cleanup", removed=len(to_remove))

        return len(to_remove)

    def get_stats(self) -> dict:
        """Get cache statistics.

        Returns:
            Statistics dictionary
        """
        expired_count = sum(1 for entry in self._cache.values() if entry.is_expired())

        return {
            "total_entries": len(self._cache),
            "expired_entries": expired_count,
            "active_entries": len(self._cache) - expired_count,
            "max_entries": self.max_entries,
            "ttl_seconds": self.ttl_seconds,
        }

    def _make_cache_key(self, query: str, context_key: str) -> str:
        """Create cache key from query and context.

        Args:
            query: User query
            context_key: Context key

        Returns:
            Cache key (hash)
        """
        # Create deterministic key from query + context
        key_string = f"{query.lower().strip()}:{context_key}"
        return hashlib.sha256(key_string.encode()).hexdigest()

    def _evict_oldest(self) -> None:
        """Evict oldest cache entry (LRU)."""
        if not self._cache:
            return

        # Find oldest entry
        oldest_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k].timestamp,
        )

        del self._cache[oldest_key]
        logger.debug("cache_evicted", query_hash=oldest_key[:16])


# Global cache instance
_rag_cache: Optional[RAGCache] = None


def get_rag_cache() -> RAGCache:
    """Get global RAG cache instance.

    Returns:
        RAGCache instance
    """
    global _rag_cache
    if _rag_cache is None:
        _rag_cache = RAGCache()
    return _rag_cache
