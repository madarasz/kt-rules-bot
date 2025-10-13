"""Hybrid retrieval combining BM25 and vector search with RRF fusion.

Implements Reciprocal Rank Fusion (RRF) to merge keyword and semantic search results.
Based on best practices from 2025 RAG research.
"""

from typing import List, Dict
from uuid import UUID
from collections import defaultdict
from dataclasses import replace

from src.models.rag_context import DocumentChunk
from src.services.rag.bm25_retriever import BM25Retriever, BM25Result
from src.lib.constants import RRF_K, BM25_K1, BM25_B
from src.lib.logging import get_logger

logger = get_logger(__name__)


class HybridRetriever:
    """Hybrid retriever combining BM25 keyword search and vector semantic search."""

    def __init__(self, k: int = RRF_K, bm25_k1: float = BM25_K1, bm25_b: float = BM25_B):
        """Initialize hybrid retriever.

        Args:
            k: RRF constant (default: 60 from research papers)
            bm25_k1: BM25 term frequency saturation parameter (default: 1.5)
            bm25_b: BM25 document length normalization parameter (default: 0.75)
        """
        self.k = k
        self.bm25_retriever = BM25Retriever(k1=bm25_k1, b=bm25_b)

        logger.info("hybrid_retriever_initialized", rrf_k=k, bm25_k1=bm25_k1, bm25_b=bm25_b)

    def index_chunks(self, chunks: List[DocumentChunk]) -> None:
        """Index chunks for BM25 search.

        Args:
            chunks: List of DocumentChunk objects
        """
        self.bm25_retriever.index_chunks(chunks)

    def fuse_results(
        self,
        vector_chunks: List[DocumentChunk],
        bm25_results: List[BM25Result],
        top_k: int = 15
    ) -> List[DocumentChunk]:
        """Fuse vector and BM25 results using Reciprocal Rank Fusion.

        RRF formula: score(doc) = Σ (1 / (k + rank_i))
        where k is a constant (typically 60) and rank_i is the rank in each list.

        Args:
            vector_chunks: Results from vector semantic search (ordered by relevance)
            bm25_results: Results from BM25 keyword search
            top_k: Number of results to return

        Returns:
            Fused and ranked list of DocumentChunk objects
        """
        # Calculate RRF scores for each document
        rrf_scores: Dict[str, float] = defaultdict(float)
        chunk_map: Dict[str, DocumentChunk] = {}
        bm25_score_map: Dict[str, float] = {}  # Store BM25 scores

        # Process vector search results (ranked by relevance_score DESC)
        for rank, chunk in enumerate(vector_chunks, start=1):
            chunk_id = str(chunk.chunk_id)
            rrf_scores[chunk_id] += 1.0 / (self.k + rank)
            chunk_map[chunk_id] = chunk

        # Process BM25 results (ranked by BM25 score DESC)
        for rank, result in enumerate(bm25_results, start=1):
            chunk_id = str(result.chunk.chunk_id)
            rrf_scores[chunk_id] += 1.0 / (self.k + rank)
            bm25_score_map[chunk_id] = result.score  # Store BM25 score
            if chunk_id not in chunk_map:
                chunk_map[chunk_id] = result.chunk

        # Sort by RRF score DESC
        sorted_ids = sorted(
            rrf_scores.keys(),
            key=lambda cid: rrf_scores[cid],
            reverse=True
        )[:top_k]

        # Normalize RRF scores to 0-1 range and assign as relevance scores
        if sorted_ids:
            max_rrf = rrf_scores[sorted_ids[0]]
            min_rrf = rrf_scores[sorted_ids[-1]]
            rrf_range = max_rrf - min_rrf if max_rrf > min_rrf else 1.0

            # Create new chunks with normalized RRF fusion scores
            fused_chunks = []
            for cid in sorted_ids:
                chunk = chunk_map[cid]

                # Store original vector similarity score
                original_vector_score = chunk.relevance_score

                # Get raw RRF score
                raw_rrf_score = rrf_scores[cid]

                # Get BM25 score if available
                bm25_score = bm25_score_map.get(cid, None)

                # Normalize RRF score to 0.45-1.0 range (matching min threshold)
                normalized_score = 0.45 + (raw_rrf_score - min_rrf) / rrf_range * 0.55

                # Store scoring details in metadata for debugging/analysis
                updated_metadata = chunk.metadata.copy()
                # Only store vector_similarity if it's not the 1.0 placeholder
                if original_vector_score < 1.0:
                    updated_metadata['vector_similarity'] = original_vector_score
                if bm25_score is not None:
                    updated_metadata['bm25_score'] = bm25_score
                updated_metadata['rrf_score'] = raw_rrf_score
                updated_metadata['rrf_normalized'] = normalized_score

                # Always update relevance_score to show the RRF fusion score
                # This ensures the displayed score matches the ranking order
                chunk = replace(
                    chunk,
                    relevance_score=normalized_score,
                    metadata=updated_metadata
                )

                fused_chunks.append(chunk)
        else:
            fused_chunks = []

        logger.debug(
            "rrf_fusion_completed",
            vector_count=len(vector_chunks),
            bm25_count=len(bm25_results),
            fused_count=len(fused_chunks),
            top_score=rrf_scores[sorted_ids[0]] if sorted_ids else 0.0
        )

        return fused_chunks

    def retrieve_hybrid(
        self,
        query: str,
        vector_chunks: List[DocumentChunk],
        top_k: int = 15
    ) -> List[DocumentChunk]:
        """Perform hybrid retrieval combining vector and BM25 search.

        Args:
            query: User query
            vector_chunks: Pre-retrieved chunks from vector search
            top_k: Number of final results

        Returns:
            Fused list of chunks
        """
        # Get BM25 results
        bm25_results = self.bm25_retriever.search(query, top_k=top_k * 2)

        # Fuse results using RRF
        fused_chunks = self.fuse_results(
            vector_chunks=vector_chunks,
            bm25_results=bm25_results,
            top_k=top_k
        )

        logger.info(
            "hybrid_retrieval_completed",
            query_length=len(query),
            vector_results=len(vector_chunks),
            bm25_results=len(bm25_results),
            fused_results=len(fused_chunks)
        )

        return fused_chunks

    def get_stats(self) -> Dict:
        """Get hybrid retriever statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "rrf_k": self.k,
            "bm25_stats": self.bm25_retriever.get_stats()
        }
