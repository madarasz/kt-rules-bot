"""Keyword extraction service for RAG query normalization.

Automatically extracts game-specific keywords from rule documents during ingestion
to enable case-insensitive query matching.
"""

import json
import re
from pathlib import Path

from src.lib.constants import RAG_KEYWORD_CACHE_PATH
from src.lib.logging import get_logger
from src.services.rag.chunker import MarkdownChunk

logger = get_logger(__name__)


class KeywordExtractor:
    """Extracts and manages game-specific keywords for query normalization."""

    def __init__(self, cache_path: str = RAG_KEYWORD_CACHE_PATH):
        """Initialize keyword extractor.

        Args:
            cache_path: Path to keyword cache file
        """
        self.cache_path = Path(cache_path)
        self.keywords: set[str] = set()

        # Load existing keywords if cache exists
        if self.cache_path.exists():
            self._load_keywords()
        else:
            logger.info("keyword_cache_not_found", path=str(self.cache_path))

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
        match = re.match(r'^([A-Z][a-z]+)(?:\s+[x\d+]+)?$', header)
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
        with open(self.cache_path, 'w') as f:
            json.dump(sorted(list(self.keywords)), f, indent=2)

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
            clean_word = word.strip('.,!?;:()[]{}"\'-')
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
            logger.debug(
                "query_normalized",
                original=query,
                normalized=normalized_query
            )

        return normalized_query
