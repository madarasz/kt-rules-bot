"""Keyword extraction service for RAG query normalization.

Automatically extracts game-specific keywords from rule documents during ingestion
to enable case-insensitive query matching.
"""

import json
import re
from pathlib import Path

from src.lib.constants import RAG_KEYWORD_CACHE_PATH, RAG_KEYWORD_HEADERS_PATH
from src.lib.logging import get_logger
from src.services.rag.chunker import MarkdownChunk

logger = get_logger(__name__)


class KeywordExtractor:
    """Extracts and manages game-specific keywords for query normalization."""

    def __init__(
        self,
        cache_path: str = RAG_KEYWORD_CACHE_PATH,
        headers_cache_path: str = RAG_KEYWORD_HEADERS_PATH,
    ):
        """Initialize keyword extractor.

        Args:
            cache_path: Path to keyword cache file
            headers_cache_path: Path to keyword-headers mapping cache file
        """
        self.cache_path = Path(cache_path)
        self.headers_cache_path = Path(headers_cache_path)
        self.keywords: set[str] = set()
        self.keyword_headers: dict[str, set[str]] = {}  # keyword (lowercase) -> set of headers

        # Load existing keywords if cache exists
        if self.cache_path.exists():
            self._load_keywords()
        else:
            logger.info("keyword_cache_not_found", path=str(self.cache_path))

        # Load existing keyword-headers mapping if cache exists
        if self.headers_cache_path.exists():
            self._load_keyword_headers()
        else:
            logger.info("keyword_headers_cache_not_found", path=str(self.headers_cache_path))

    def extract_from_chunks(self, chunks: list[MarkdownChunk]) -> set[str]:
        """Extract keywords from document chunks.

        Extracts capitalized terms from markdown headers (## Keyword pattern).

        Args:
            chunks: List of MarkdownChunk objects

        Returns:
            Set of extracted keywords
        """
        new_keywords: set[str] = set()

        for chunk in chunks:
            # Extract from header text directly
            if chunk.header:
                extracted = self._extract_keywords_from_header(chunk.header)
                new_keywords.update(extracted)

            # Also check the chunk text for ## headers (in case header wasn't parsed)
            for line in chunk.text.split("\n"):
                if line.startswith("## "):
                    header_text = line[3:].strip()  # Remove "## "
                    extracted = self._extract_keywords_from_header(header_text)
                    new_keywords.update(extracted)

        logger.debug("keywords_extracted_from_chunks", count=len(new_keywords))
        return new_keywords

    def _extract_keywords_from_header(self, header: str) -> set[str]:
        """Extract keywords from a single header string.

        Patterns:
        - "Accurate x" -> ["Accurate"]
        - "Balanced" -> ["Balanced"]
        - "Lethal 5+" -> ["Lethal"]
        - "VESPID STINGWINGS - FLY" -> ["VESPID", "STINGWINGS"] (FLY filtered out)

        Args:
            header: Header text (without ## prefix)

        Returns:
            Set of extracted keywords (minimum 4 characters)
        """
        keywords: set[str] = set()

        # Remove common patterns that are not keywords
        # Pattern 1: "Keyword x" or "Keyword N+" (e.g., "Accurate x", "Lethal 5+")
        match = re.match(r"^([A-Z][a-z]+)(?:\s+[x\d+]+)?$", header)
        if match:
            word = match.group(1)
            if len(word) >= 4:
                keywords.add(word)
            return keywords

        # Pattern 2: "UPPERCASE - SEPARATED - TERMS"
        if " - " in header:
            parts = header.split(" - ")
            for part in parts:
                # Add multi-word uppercase terms
                words = part.strip().split()
                for word in words:
                    if word and word[0].isupper() and len(word) >= 4:
                        keywords.add(word)
            return keywords

        # Pattern 3: Single capitalized word
        words = header.split()
        for word in words:
            # Only add words that start with uppercase and are at least 4 chars
            # This filters out articles, prepositions, short words, etc.
            if len(word) >= 4 and word[0].isupper() and word.isalpha():
                keywords.add(word)

        return keywords

    def add_keywords(self, new_keywords: set[str]) -> int:
        """Add new keywords to the library.

        Args:
            new_keywords: Set of keywords to add

        Returns:
            Number of newly added keywords (excluding duplicates)
        """
        initial_count = len(self.keywords)
        self.keywords.update(new_keywords)
        added_count = len(self.keywords) - initial_count

        if added_count > 0:
            logger.info("keywords_added", count=added_count, total=len(self.keywords))

        return added_count

    def save_keywords(self) -> None:
        """Save keywords to cache file."""
        # Ensure parent directory exists
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

        # Save as JSON (sorted for readability)
        with open(self.cache_path, "w") as f:
            json.dump(sorted(self.keywords), f, indent=2)

        logger.info("keywords_saved", path=str(self.cache_path), count=len(self.keywords))

    def _load_keywords(self) -> None:
        """Load keywords from cache file."""
        try:
            with open(self.cache_path) as f:
                keyword_list = json.load(f)
                self.keywords = set(keyword_list)

            logger.info("keywords_loaded", path=str(self.cache_path), count=len(self.keywords))

        except Exception as e:
            logger.error("keyword_load_failed", error=str(e), path=str(self.cache_path))
            self.keywords = set()

    def get_keyword_count(self) -> int:
        """Get total number of keywords in library.

        Returns:
            Keyword count
        """
        return len(self.keywords)

    def get_keywords(self) -> set[str]:
        """Get all keywords.

        Returns:
            Set of all keywords
        """
        return self.keywords.copy()

    def normalize_query(self, query: str) -> str:
        """Normalize query by capitalizing known keywords.

        Case-insensitive matching against keyword library.

        Args:
            query: User query string

        Returns:
            Normalized query with capitalized keywords
        """
        if not self.keywords:
            return query

        # Create lowercase lookup map
        keyword_map = {kw.lower(): kw for kw in self.keywords}

        # Split query into words (preserve punctuation structure)
        words = query.split()
        normalized_words = []

        for word in words:
            # Extract the actual word (strip punctuation)
            clean_word = word.strip(".,!?;:()[]{}\"'-")
            word_lower = clean_word.lower()

            # Check if word matches a keyword
            if word_lower in keyword_map:
                # Replace with capitalized version, preserving surrounding punctuation
                original_keyword = keyword_map[word_lower]
                normalized_word = word.replace(clean_word, original_keyword)
                normalized_words.append(normalized_word)
            else:
                normalized_words.append(word)

        normalized_query = " ".join(normalized_words)

        # Log if normalization changed the query
        if normalized_query != query:
            logger.debug("query_normalized", original=query, normalized=normalized_query)

        return normalized_query

    # =========================================================================
    # Keyword-Headers Mapping Methods (for Deterministic Hop)
    # =========================================================================

    def _load_keyword_headers(self) -> None:
        """Load keyword-headers mapping from cache file."""
        try:
            with open(self.headers_cache_path) as f:
                data = json.load(f)
                # Convert lists back to sets
                self.keyword_headers = {k: set(v) for k, v in data.items()}

            logger.info(
                "keyword_headers_loaded",
                path=str(self.headers_cache_path),
                keyword_count=len(self.keyword_headers),
            )

        except Exception as e:
            logger.error(
                "keyword_headers_load_failed",
                error=str(e),
                path=str(self.headers_cache_path),
            )
            self.keyword_headers = {}

    def _keyword_matches_header(self, keyword: str, header: str) -> bool:
        """Check if keyword appears as whole word in header (case-insensitive).

        Uses word boundary matching: "Accurate" matches " Accurate " but not "Inaccurate"

        Args:
            keyword: Keyword to search for
            header: Header text to search in

        Returns:
            True if keyword found as whole word
        """
        pattern = r"\b" + re.escape(keyword) + r"\b"
        return bool(re.search(pattern, header, re.IGNORECASE))

    def extract_keyword_headers_from_chunks(
        self, chunks: list[MarkdownChunk]
    ) -> dict[str, set[str]]:
        """Extract mapping of keywords to headers they appear in.

        Uses word boundary matching: "Accurate" matches " Accurate " but not "Inaccurate"

        Args:
            chunks: List of MarkdownChunk objects

        Returns:
            Dict mapping keyword (lowercase) to set of header names
        """
        keyword_headers: dict[str, set[str]] = {}

        for chunk in chunks:
            if not chunk.header:
                continue

            header_text = chunk.header

            # For each known keyword, check if it appears in header with word boundary
            for keyword in self.keywords:
                if self._keyword_matches_header(keyword, header_text):
                    key = keyword.lower()
                    if key not in keyword_headers:
                        keyword_headers[key] = set()
                    keyword_headers[key].add(header_text)

        logger.debug(
            "keyword_headers_extracted_from_chunks",
            unique_keywords=len(keyword_headers),
            total_mappings=sum(len(v) for v in keyword_headers.values()),
        )

        return keyword_headers

    def add_keyword_headers(self, new_mappings: dict[str, set[str]]) -> int:
        """Add new keyword-header mappings to the library.

        Args:
            new_mappings: Dict mapping keyword (lowercase) to set of headers

        Returns:
            Number of new keyword-header pairs added
        """
        added_count = 0

        for keyword, headers in new_mappings.items():
            key = keyword.lower()
            if key not in self.keyword_headers:
                self.keyword_headers[key] = set()

            initial_count = len(self.keyword_headers[key])
            self.keyword_headers[key].update(headers)
            added_count += len(self.keyword_headers[key]) - initial_count

        if added_count > 0:
            logger.info(
                "keyword_headers_added",
                new_mappings=added_count,
                total_keywords=len(self.keyword_headers),
            )

        return added_count

    def save_keyword_headers(self) -> None:
        """Save keyword-headers mapping to cache file."""
        # Ensure parent directory exists
        self.headers_cache_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert sets to sorted lists for JSON serialization
        serializable = {k: sorted(v) for k, v in self.keyword_headers.items()}

        with open(self.headers_cache_path, "w") as f:
            json.dump(serializable, f, indent=2)

        logger.info(
            "keyword_headers_saved",
            path=str(self.headers_cache_path),
            keyword_count=len(self.keyword_headers),
            total_mappings=sum(len(v) for v in self.keyword_headers.values()),
        )

    def get_headers_for_keywords(self, keywords: list[str]) -> list[str]:
        """Get all unique headers containing any of the specified keywords.

        Args:
            keywords: List of keywords to lookup (case-insensitive)

        Returns:
            Deduplicated list of header names
        """
        all_headers: set[str] = set()

        for keyword in keywords:
            headers = self.keyword_headers.get(keyword.lower(), set())
            all_headers.update(headers)

        return list(all_headers)

    def get_keyword_headers_count(self) -> int:
        """Get total number of keyword-header mappings.

        Returns:
            Total count of keyword-header pairs
        """
        return sum(len(v) for v in self.keyword_headers.values())

    def filter_overmatched_keywords(self, max_match: int) -> int:
        """Remove keywords that match too many headers (too generic).

        Args:
            max_match: Maximum number of headers a keyword can match

        Returns:
            Number of keywords removed
        """
        keywords_to_remove = []

        for keyword, headers in self.keyword_headers.items():
            if len(headers) > max_match:
                keywords_to_remove.append(keyword)

        # Remove overmatched keywords
        for keyword in keywords_to_remove:
            del self.keyword_headers[keyword]

        if keywords_to_remove:
            logger.info(
                "overmatched_keywords_filtered",
                removed_count=len(keywords_to_remove),
                max_match=max_match,
                remaining_keywords=len(self.keyword_headers),
            )

        return len(keywords_to_remove)
