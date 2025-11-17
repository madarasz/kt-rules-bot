"""Query expansion service for RAG synonym mapping.

Expands user queries with official Kill Team terminology to improve BM25 retrieval.
Handles cases where users use informal terms (e.g., "heal") instead of official
game terminology (e.g., "regain wounds").
"""

import json
import re
from pathlib import Path

from src.lib.logging import get_logger

logger = get_logger(__name__)


class QueryExpander:
    """Expands queries with official terminology synonyms for better keyword matching."""

    def __init__(self, synonym_dict_path: str):
        """Initialize query expander.

        Args:
            synonym_dict_path: Path to synonym dictionary JSON file
        """
        self.synonym_dict_path = Path(synonym_dict_path)
        self.official_to_synonyms: dict[str, list[str]] = {}
        self.synonym_to_official: dict[str, str] = {}

        # Load synonyms if file exists
        if self.synonym_dict_path.exists():
            self._load_synonyms()
        else:
            logger.warning(
                "synonym_dict_not_found",
                path=str(self.synonym_dict_path),
                message="Query expansion will be disabled",
            )

    def _load_synonyms(self) -> None:
        """Load synonym dictionary from JSON file.

        Expected format:
        {
            "official term": ["synonym1", "synonym2", ...],
            ...
        }
        """
        try:
            with open(self.synonym_dict_path) as f:
                self.official_to_synonyms = json.load(f)

            # Build reverse mapping: synonym -> official term
            self.synonym_to_official = {}
            for official_term, synonyms in self.official_to_synonyms.items():
                for synonym in synonyms:
                    # Store lowercase for case-insensitive matching
                    self.synonym_to_official[synonym.lower()] = official_term

            logger.info(
                "synonyms_loaded",
                path=str(self.synonym_dict_path),
                official_terms=len(self.official_to_synonyms),
                total_synonyms=len(self.synonym_to_official),
            )

        except Exception as e:
            logger.error("synonym_load_failed", error=str(e), path=str(self.synonym_dict_path))
            self.official_to_synonyms = {}
            self.synonym_to_official = {}

    def expand_query(self, query: str) -> str:
        """Expand query with official terminology synonyms.

        Strategy:
        1. Detect user synonyms in query (case-insensitive)
        2. Append official terms to end of query
        3. Preserve original query for semantic search compatibility

        Example:
            "Can I heal my operative?" -> "Can I heal my operative? regain wounds"

        Args:
            query: Original user query

        Returns:
            Expanded query with official terms appended
        """
        if not self.synonym_to_official:
            return query

        query_lower = query.lower()
        matched_official_terms: set[str] = set()

        # Check for multi-word phrase matches first (longer matches = more specific)
        for synonym, official_term in sorted(
            self.synonym_to_official.items(), key=lambda x: len(x[0]), reverse=True
        ):
            # Use word boundaries for multi-word phrases
            if len(synonym.split()) > 1:
                # Multi-word phrase: match as substring with word boundaries
                pattern = r"\b" + re.escape(synonym) + r"\b"
                if re.search(pattern, query_lower):
                    matched_official_terms.add(official_term)
            else:
                # Single word: match as whole word
                pattern = r"\b" + re.escape(synonym) + r"\b"
                if re.search(pattern, query_lower):
                    matched_official_terms.add(official_term)

        # If we found synonyms, append official terms
        if matched_official_terms:
            expansion = " " + " ".join(sorted(matched_official_terms))
            expanded_query = query + expansion

            logger.debug(
                "query_expanded",
                original=query,
                expanded=expanded_query,
                added_terms=sorted(matched_official_terms),
            )

            return expanded_query

        return query

    def get_stats(self) -> dict[str, int]:
        """Get synonym dictionary statistics.

        Returns:
            Statistics dictionary with counts
        """
        return {
            "official_terms": len(self.official_to_synonyms),
            "total_synonyms": len(self.synonym_to_official),
            "loaded": len(self.synonym_to_official) > 0,
        }

    def get_official_terms(self) -> list[str]:
        """Get all official terms in dictionary.

        Returns:
            List of official terminology strings
        """
        return list(self.official_to_synonyms.keys())

    def get_synonyms_for_term(self, official_term: str) -> list[str]:
        """Get all synonyms for a given official term.

        Args:
            official_term: Official game terminology

        Returns:
            List of user-friendly synonyms
        """
        return self.official_to_synonyms.get(official_term, [])
