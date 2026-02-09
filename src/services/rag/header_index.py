"""Header-based fuzzy lookup index for hop retrieval.

Provides fast header-matching for multi-hop retrieval when the hop judge
explicitly names rules. Instead of semantic search (which dilutes relevance
for compound queries), this enables direct header lookup.
"""

from rapidfuzz import fuzz

from src.lib.constants import HEADER_FUZZY_THRESHOLD
from src.lib.logging import get_logger
from src.models.rag_context import DocumentChunk

logger = get_logger(__name__)


class HeaderIndex:
    """In-memory index mapping chunk headers to chunks for fuzzy lookup."""

    def __init__(self):
        self._header_to_chunk: dict[str, DocumentChunk] = {}  # normalized_header → chunk
        self._all_headers: list[str] = []  # For fuzzy search iteration
        self._built = False

    def build_from_chunks(self, chunks: list[DocumentChunk]) -> None:
        """Build index from list of chunks.

        Args:
            chunks: List of DocumentChunk objects with headers
        """
        self._header_to_chunk.clear()
        self._all_headers.clear()

        for chunk in chunks:
            header = chunk.header.strip()
            if header:
                normalized = header.lower()
                # If duplicate header, keep first occurrence
                if normalized not in self._header_to_chunk:
                    self._header_to_chunk[normalized] = chunk
                    self._all_headers.append(normalized)

        self._built = True
        logger.info(
            "header_index_built",
            total_headers=len(self._all_headers),
            unique_headers=len(self._header_to_chunk),
        )

    def fuzzy_search(
        self, query: str, threshold: float = HEADER_FUZZY_THRESHOLD
    ) -> tuple[DocumentChunk | None, float]:
        """Find chunk by fuzzy header match.

        Args:
            query: Header text to search for
            threshold: Minimum similarity (0.0-1.0), default from constants

        Returns:
            Tuple of (best matching chunk or None, match score 0.0-1.0)
        """
        if not self._built:
            logger.warning("header_index_not_built")
            return None, 0.0

        query_normalized = query.strip().lower()
        if not query_normalized:
            return None, 0.0

        best_match_header = None
        best_score = 0.0

        for header in self._all_headers:
            score = fuzz.ratio(query_normalized, header) / 100.0
            if score >= threshold and score > best_score:
                best_score = score
                best_match_header = header

        if best_match_header:
            chunk = self._header_to_chunk[best_match_header]
            logger.debug(
                "header_fuzzy_match_found",
                query=query,
                matched_header=best_match_header,
                score=best_score,
            )
            return chunk, best_score

        logger.debug(
            "header_fuzzy_match_not_found",
            query=query,
            threshold=threshold,
        )
        return None, 0.0

    @property
    def header_count(self) -> int:
        """Number of indexed headers."""
        return len(self._all_headers)
