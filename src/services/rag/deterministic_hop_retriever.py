"""Deterministic hop retrieval using keyword-to-header matching.

Adds a rules-based retrieval step between initial retrieval and LLM-guided multi-hop.
Identifies keywords in the query that aren't covered by initial retrieval,
finds matching chunk headers, and retrieves those chunks directly.
"""

import re
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from src.lib.constants import RAG_DETERMINISTIC_HOP_CHUNK_LIMIT
from src.lib.logging import get_logger
from src.models.rag_context import DocumentChunk
from src.services.rag.keyword_extractor import KeywordExtractor

logger = get_logger(__name__)


@dataclass
class DeterministicHopResult:
    """Result of deterministic hop retrieval."""

    chunks: list[DocumentChunk]
    query_keywords: list[str]  # All keywords extracted from query
    matched_keywords: list[str]  # Keywords already covered by existing chunks
    unmatched_keywords: list[str]  # Keywords requiring additional retrieval
    target_headers: list[str]  # Headers targeted for retrieval
    retrieval_query: str  # Query used for retrieval (headers concatenated)
    triggered: bool  # Whether deterministic hop was performed


class DeterministicHopRetriever:
    """Retriever for deterministic keyword-to-header matching.

    Flow:
    1. Tokenize query using BM25-style tokenization
    2. Filter to known keywords from keyword library
    3. Check which keywords are already covered by existing chunks
    4. For unmatched keywords, find matching chunk headers
    5. Retrieve chunks by header name (concatenated query)
    6. Deduplicate and return
    """

    def __init__(
        self,
        keyword_extractor: KeywordExtractor,
        chunk_limit: int = RAG_DETERMINISTIC_HOP_CHUNK_LIMIT,
    ):
        """Initialize deterministic hop retriever.

        Args:
            keyword_extractor: KeywordExtractor with loaded keyword-headers mapping
            chunk_limit: Maximum chunks to retrieve via deterministic hop
        """
        self.keyword_extractor = keyword_extractor
        self.chunk_limit = chunk_limit

        logger.info(
            "deterministic_hop_retriever_initialized",
            chunk_limit=chunk_limit,
            keyword_headers_loaded=len(keyword_extractor.keyword_headers),
        )

    def _tokenize_query(self, query: str) -> list[str]:
        """Tokenize query using BM25-style tokenization.

        Simple tokenization: lowercase, split on whitespace and basic punctuation.

        Args:
            query: User query

        Returns:
            List of lowercase tokens
        """
        # Lowercase
        text = query.lower()

        # Split on whitespace and punctuation (keep alphanumeric and hyphen)
        tokens = re.findall(r"\b[\w-]+\b", text)

        return tokens

    def _keyword_matches_text(self, keyword: str, text: str) -> bool:
        """Check if keyword appears as whole word in text (case-insensitive).

        Uses word boundary matching: "Accurate" matches " Accurate " but not "Inaccurate"

        Args:
            keyword: Keyword to search for
            text: Text to search in

        Returns:
            True if keyword found as whole word
        """
        pattern = r"\b" + re.escape(keyword) + r"\b"
        return bool(re.search(pattern, text, re.IGNORECASE))

    def _extract_query_keywords(self, query: str) -> list[str]:
        """Extract known keywords from query.

        Args:
            query: User query

        Returns:
            List of known keywords found in query (original casing from library)
        """
        tokens = self._tokenize_query(query)
        known_keywords = self.keyword_extractor.get_keywords()
        known_lower = {kw.lower(): kw for kw in known_keywords}

        # Match tokens to known keywords (case-insensitive)
        matched = []
        for token in tokens:
            if token in known_lower:
                matched.append(known_lower[token])

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique = []
        for kw in matched:
            if kw.lower() not in seen:
                seen.add(kw.lower())
                unique.append(kw)

        return unique

    def _check_keyword_coverage(
        self,
        keywords: list[str],
        chunks: list[DocumentChunk],
    ) -> tuple[list[str], list[str]]:
        """Check which keywords are already covered by chunks.

        A keyword is "covered" if it appears (word boundary match) in any
        chunk's header or text.

        Args:
            keywords: Keywords to check
            chunks: Existing chunks

        Returns:
            Tuple of (matched_keywords, unmatched_keywords)
        """
        matched = []
        unmatched = []

        for keyword in keywords:
            found = False
            for chunk in chunks:
                # Check header
                if self._keyword_matches_text(keyword, chunk.header):
                    found = True
                    break
                # Check text
                if self._keyword_matches_text(keyword, chunk.text):
                    found = True
                    break

            if found:
                matched.append(keyword)
            else:
                unmatched.append(keyword)

        return matched, unmatched

    def retrieve_deterministic(
        self,
        query: str,
        existing_chunks: list[DocumentChunk],
        vector_db_service,  # VectorDBService - type hint omitted to avoid circular import
        embedding_service,  # EmbeddingService - type hint omitted to avoid circular import
        query_id: UUID,
    ) -> DeterministicHopResult:
        """Perform deterministic hop retrieval.

        Args:
            query: User query
            existing_chunks: Chunks from initial retrieval (Hop 0)
            vector_db_service: Vector DB service for retrieval
            embedding_service: Embedding service for query embedding
            query_id: Query UUID for tracking

        Returns:
            DeterministicHopResult with retrieved chunks and metadata
        """
        # Step 1: Extract keywords from query
        query_keywords = self._extract_query_keywords(query)

        if not query_keywords:
            logger.debug("deterministic_hop_no_keywords", query=query)
            return DeterministicHopResult(
                chunks=[],
                query_keywords=[],
                matched_keywords=[],
                unmatched_keywords=[],
                target_headers=[],
                retrieval_query="",
                triggered=False,
            )

        # Step 2: Check which keywords are already covered
        matched_keywords, unmatched_keywords = self._check_keyword_coverage(
            query_keywords, existing_chunks
        )

        if not unmatched_keywords:
            logger.debug(
                "deterministic_hop_all_covered",
                query=query,
                keywords=query_keywords,
            )
            return DeterministicHopResult(
                chunks=[],
                query_keywords=query_keywords,
                matched_keywords=matched_keywords,
                unmatched_keywords=[],
                target_headers=[],
                retrieval_query="",
                triggered=False,
            )

        # Step 3: Find target headers for unmatched keywords
        target_headers = self.keyword_extractor.get_headers_for_keywords(unmatched_keywords)

        if not target_headers:
            logger.debug(
                "deterministic_hop_no_headers",
                unmatched_keywords=unmatched_keywords,
            )
            return DeterministicHopResult(
                chunks=[],
                query_keywords=query_keywords,
                matched_keywords=matched_keywords,
                unmatched_keywords=unmatched_keywords,
                target_headers=[],
                retrieval_query="",
                triggered=False,
            )

        # Step 4: Create retrieval query from header names
        # Limit headers to prevent overly long query
        limited_headers = target_headers[: min(10, len(target_headers))]
        retrieval_query = ", ".join(limited_headers)

        # Step 5: Retrieve chunks by header query
        query_embedding = embedding_service.embed_text(retrieval_query)
        results = vector_db_service.query(
            query_embeddings=[query_embedding],
            n_results=self.chunk_limit * 2,  # Get more, filter later
        )

        # Convert to chunks with header-match boosting
        new_chunks = self._results_to_chunks(results, target_headers)

        # Step 6: Deduplicate against existing chunks
        existing_ids = {c.chunk_id for c in existing_chunks}
        unique_chunks = [c for c in new_chunks if c.chunk_id not in existing_ids]

        # Limit to chunk_limit
        final_chunks = unique_chunks[: self.chunk_limit]

        logger.info(
            "deterministic_hop_completed",
            query_keywords=query_keywords,
            unmatched_keywords=unmatched_keywords,
            target_headers_count=len(target_headers),
            retrieval_query=retrieval_query[:100],  # Truncate for logging
            chunks_retrieved=len(final_chunks),
        )

        return DeterministicHopResult(
            chunks=final_chunks,
            query_keywords=query_keywords,
            matched_keywords=matched_keywords,
            unmatched_keywords=unmatched_keywords,
            target_headers=target_headers,
            retrieval_query=retrieval_query,
            triggered=True,
        )

    def _results_to_chunks(
        self,
        results: dict,
        target_headers: list[str],
    ) -> list[DocumentChunk]:
        """Convert vector DB results to chunks, prioritizing header matches.

        Args:
            results: Vector DB query results
            target_headers: Headers we're looking for

        Returns:
            List of DocumentChunk objects sorted by relevance
        """
        chunks: list[DocumentChunk] = []

        if not results["ids"] or not results["ids"][0]:
            return chunks

        ids = results["ids"][0]
        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]

        for i, chunk_id_str in enumerate(ids):
            metadata = metadatas[i]
            header = metadata.get("header", "")

            # Check if chunk header matches any target (for boosting)
            header_matches = any(
                self._keyword_matches_text(target.split(" - ")[-1], header)
                for target in target_headers
            )

            # Calculate relevance score from L2 distance
            l2_squared = distances[i]
            relevance_score = max(0.0, 1.0 - (l2_squared / 2.0))

            # Boost score for header matches
            if header_matches:
                relevance_score = min(1.0, relevance_score + 0.15)

            chunk = DocumentChunk(
                chunk_id=UUID(chunk_id_str),
                document_id=UUID(metadata.get("document_id", str(uuid4()))),
                text=documents[i],
                header=header,
                header_level=metadata.get("header_level", 0),
                metadata=metadata,
                relevance_score=relevance_score,
                position_in_doc=metadata.get("position", 0),
            )

            chunks.append(chunk)

        # Sort by relevance (header matches + vector similarity)
        chunks.sort(key=lambda c: c.relevance_score, reverse=True)

        return chunks
