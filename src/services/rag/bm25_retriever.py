"""BM25 keyword-based retrieval service.

Implements BM25 (Best Matching 25) ranking algorithm for keyword matching.
Complements vector semantic search with exact term matching.
"""

from typing import List, Dict, Tuple
from uuid import UUID
from dataclasses import dataclass
from rank_bm25 import BM25Okapi

from src.models.rag_context import DocumentChunk
from src.lib.logging import get_logger

logger = get_logger(__name__)


@dataclass
class BM25Result:
    """BM25 search result with score."""

    chunk: DocumentChunk
    score: float  # BM25 relevance score


class BM25Retriever:
    """BM25-based keyword retrieval for exact term matching."""

    def __init__(self):
        """Initialize BM25 retriever."""
        self.bm25: BM25Okapi | None = None
        self.chunks: List[DocumentChunk] = []
        self.tokenized_corpus: List[List[str]] = []

        logger.info("bm25_retriever_initialized")

    def index_chunks(self, chunks: List[DocumentChunk]) -> None:
        """Index document chunks for BM25 search.

        Args:
            chunks: List of DocumentChunk objects to index
        """
        if not chunks:
            logger.warning("bm25_index_empty", message="No chunks to index")
            return

        self.chunks = chunks

        # Tokenize corpus (lowercase, split on whitespace/punctuation)
        self.tokenized_corpus = [
            self._tokenize(chunk.text + " " + chunk.header)
            for chunk in chunks
        ]

        # Build BM25 index
        self.bm25 = BM25Okapi(self.tokenized_corpus)

        logger.info(
            "bm25_index_built",
            chunk_count=len(chunks),
            avg_tokens=sum(len(t) for t in self.tokenized_corpus) / len(chunks)
        )

    def search(self, query: str, top_k: int = 15) -> List[BM25Result]:
        """Search for relevant chunks using BM25.

        Args:
            query: Search query
            top_k: Number of top results to return

        Returns:
            List of BM25Result objects sorted by score DESC
        """
        if not self.bm25 or not self.chunks:
            logger.warning("bm25_not_indexed", message="BM25 index not built")
            return []

        # Tokenize query
        tokenized_query = self._tokenize(query)

        # Get BM25 scores
        scores = self.bm25.get_scores(tokenized_query)

        # Get top-k results
        top_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True
        )[:top_k]

        results = [
            BM25Result(
                chunk=self.chunks[idx],
                score=float(scores[idx])
            )
            for idx in top_indices
            if scores[idx] > 0  # Filter zero scores
        ]

        logger.debug(
            "bm25_search_completed",
            query_tokens=len(tokenized_query),
            results_count=len(results),
            top_score=results[0].score if results else 0.0
        )

        return results

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text for BM25 indexing.

        Simple tokenization: lowercase, split on whitespace and basic punctuation.

        Args:
            text: Text to tokenize

        Returns:
            List of tokens
        """
        import re

        # Lowercase
        text = text.lower()

        # Split on whitespace and punctuation (keep alphanumeric and hyphen)
        tokens = re.findall(r'\b[\w-]+\b', text)

        return tokens

    def get_stats(self) -> Dict:
        """Get BM25 index statistics.

        Returns:
            Statistics dictionary
        """
        if not self.bm25:
            return {"indexed": False}

        return {
            "indexed": True,
            "chunk_count": len(self.chunks),
            "avg_doc_length": sum(len(t) for t in self.tokenized_corpus) / len(self.tokenized_corpus) if self.tokenized_corpus else 0,
            "vocabulary_size": len(set(token for doc in self.tokenized_corpus for token in doc))
        }
