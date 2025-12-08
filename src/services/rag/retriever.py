"""RAG retrieval service implementing the RAG pipeline contract.

Implements retrieve() method from specs/001-we-are-building/contracts/rag-pipeline.md
"""

import asyncio
import threading
from typing import Any
from uuid import UUID, uuid4

from src.lib.constants import (
    BM25_B,
    BM25_K1,
    BM25_WEIGHT,
    MAXIMUM_FINAL_CHUNK_COUNT,
    RAG_ENABLE_DETERMINISTIC_HOP,
    RAG_ENABLE_QUERY_EXPANSION,
    RAG_ENABLE_QUERY_NORMALIZATION,
    RAG_HOP_EVALUATION_TIMEOUT,
    RAG_MAX_HOPS,
    RAG_SYNONYM_DICT_PATH,
    RRF_K,
)
from src.lib.logging import get_logger
from src.models.rag_context import DocumentChunk, RAGContext
from src.models.rag_request import RetrieveRequest
from src.services.rag.deterministic_hop_retriever import (
    DeterministicHopResult,
    DeterministicHopRetriever,
)
from src.services.rag.embeddings import EmbeddingService
from src.services.rag.hybrid_retriever import HybridRetriever
from src.services.rag.keyword_extractor import KeywordExtractor
from src.services.rag.multi_hop_retriever import MultiHopRetriever
from src.services.rag.query_expander import QueryExpander
from src.services.rag.vector_db import VectorDBService

logger = get_logger(__name__)


class InvalidQueryError(Exception):
    """Query validation error."""

    pass


class VectorDBUnavailableError(Exception):
    """Vector DB connection error."""

    pass


class RAGRetriever:
    """Service for retrieving relevant documents using RAG."""

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        vector_db_service: VectorDBService | None = None,
        keyword_extractor: KeywordExtractor | None = None,
        query_expander: QueryExpander | None = None,
        enable_hybrid: bool = True,
        enable_multi_hop: bool = (RAG_MAX_HOPS > 0),
        rrf_k: int = RRF_K,
        bm25_k1: float = BM25_K1,
        bm25_b: float = BM25_B,
        bm25_weight: float = BM25_WEIGHT,
        db_path: str | None = None,
    ):
        """Initialize RAG retriever.

        Args:
            embedding_service: Embedding service (creates if None)
            vector_db_service: Vector DB service (creates if None)
            keyword_extractor: Keyword extractor for query normalization (creates if None)
            query_expander: Query expander for synonym expansion (creates if None)
            enable_hybrid: Enable hybrid search with BM25 (default: True)
            enable_multi_hop: Enable multi-hop retrieval (default: False)
            rrf_k: RRF constant for hybrid fusion (default: 60)
            bm25_k1: BM25 term frequency saturation parameter (default: 1.5)
            bm25_b: BM25 document length normalization parameter (default: 0.75)
            bm25_weight: Weight for BM25 in fusion (default: 0.5, vector gets 1-bm25_weight)
            db_path: Optional database path (only used if vector_db_service is None)
        """
        self.embedding_service = embedding_service or EmbeddingService()
        self.vector_db = vector_db_service or VectorDBService(db_path=db_path)
        self.keyword_extractor = keyword_extractor or KeywordExtractor()
        self.query_expander = query_expander or QueryExpander(RAG_SYNONYM_DICT_PATH)
        self.enable_hybrid = enable_hybrid
        self.enable_multi_hop = enable_multi_hop

        # Initialize hybrid retriever if enabled
        self.hybrid_retriever: HybridRetriever | None = None
        if enable_hybrid:
            self.hybrid_retriever = HybridRetriever(
                k=rrf_k, bm25_k1=bm25_k1, bm25_b=bm25_b, bm25_weight=bm25_weight
            )
            # Index all chunks from vector DB
            self._build_hybrid_index()

        # Initialize multi-hop retriever if enabled
        self.multi_hop_retriever = None
        if enable_multi_hop:
            self.multi_hop_retriever = MultiHopRetriever(base_retriever=self)
            logger.info("multi_hop_enabled", max_hops=RAG_MAX_HOPS)

        # Initialize deterministic hop retriever if enabled
        self.deterministic_hop_retriever: DeterministicHopRetriever | None = None
        if RAG_ENABLE_DETERMINISTIC_HOP:
            self.deterministic_hop_retriever = DeterministicHopRetriever(
                keyword_extractor=self.keyword_extractor,
            )
            logger.info(
                "deterministic_hop_enabled",
                keyword_headers_count=self.keyword_extractor.get_keyword_headers_count(),
            )

        logger.info(
            "rag_retriever_initialized",
            hybrid_enabled=enable_hybrid,
            multi_hop_enabled=enable_multi_hop,
            deterministic_hop_enabled=RAG_ENABLE_DETERMINISTIC_HOP,
            rrf_k=rrf_k,
            bm25_k1=bm25_k1,
            bm25_b=bm25_b,
            bm25_weight=bm25_weight,
            keywords_loaded=self.keyword_extractor.get_keyword_count(),
            synonyms_loaded=self.query_expander.get_stats()["total_synonyms"],
        )

    def retrieve(
        self, request: RetrieveRequest, query_id: UUID, verbose: bool = False
    ) -> tuple[RAGContext, list[Any], dict[UUID, int | str], DeterministicHopResult | None]:
        """Retrieve relevant rule documents for a user query.

        Implements the RAG pipeline contract from contracts/rag-pipeline.md.

        Args:
            request: Retrieval request parameters
            query_id: Query UUID for tracking
            verbose: If True, capture filled prompts in HopEvaluation objects

        Returns:
            Tuple of:
            - RAGContext with retrieved chunks
            - List of HopEvaluation objects (empty if single-hop)
            - Dict mapping chunk_id to hop number (0=initial, "D"=deterministic, 1+=multi-hop)
            - DeterministicHopResult (None if not triggered)

        Raises:
            InvalidQueryError: If query is invalid
            VectorDBUnavailableError: If vector DB is unavailable
        """
        # Validate query
        self._validate_query(request.query)

        # Perform initial retrieval (Hop 0)
        try:
            initial_chunks = self._perform_initial_retrieval(request)
        except Exception as e:
            logger.error("retrieval_failed", query_id=str(query_id), error=str(e))
            raise VectorDBUnavailableError(f"Vector DB query failed: {e}") from e

        # Initialize chunk_hop_map with Hop 0
        chunk_hop_map: dict[UUID, int | str] = {c.chunk_id: 0 for c in initial_chunks}
        deterministic_result: DeterministicHopResult | None = None

        # Perform deterministic hop (Hop D) if enabled
        if self.deterministic_hop_retriever:
            initial_chunks, deterministic_result, chunk_hop_map = (
                self._perform_deterministic_hop(
                    query=request.query,
                    existing_chunks=initial_chunks,
                    query_id=query_id,
                    chunk_hop_map=chunk_hop_map,
                )
            )

        # If multi-hop enabled, continue with additional retrieval hops (Hop 1+)
        if request.use_multi_hop and self.multi_hop_retriever:
            return self._perform_multi_hop_retrieval(
                request, query_id, initial_chunks, verbose, chunk_hop_map, deterministic_result
            )

        # Single-hop: create context and return
        context = self._create_rag_context(query_id, initial_chunks, request.min_relevance)

        logger.info(
            "retrieval_completed",
            query_id=str(query_id),
            chunks_found=len(initial_chunks),
            deterministic_hop_triggered=deterministic_result.triggered
            if deterministic_result
            else False,
            avg_relevance=context.avg_relevance,
            meets_threshold=context.meets_threshold,
        )

        # Return tuple: context, hop_evaluations, chunk_hop_map, deterministic_result
        return context, [], chunk_hop_map, deterministic_result

    def _perform_initial_retrieval(self, request: RetrieveRequest) -> list[DocumentChunk]:
        """Perform initial retrieval: normalize, embed, search, and apply hybrid if enabled.

        Args:
            request: Retrieval request parameters

        Returns:
            List of retrieved DocumentChunk objects
        """
        # Normalize and expand query
        normalized_query, expanded_query = self._normalize_and_expand_query(request.query)

        # Generate query embedding using normalized query (NOT expanded)
        # Vector search handles semantic synonyms naturally
        query_embedding = self.embedding_service.embed_text(normalized_query)

        logger.debug(
            "query_embedding_generated",
            query_length=len(request.query),
            context_key=request.context_key,
        )

        # Query vector database
        results = self.vector_db.query(
            query_embeddings=[query_embedding], n_results=request.max_chunks
        )

        # Convert results to DocumentChunk objects
        chunks = self._results_to_chunks(results, request.min_relevance)

        # Apply hybrid search if enabled
        # Use EXPANDED query for BM25 to catch user-friendly synonyms
        if request.use_hybrid and self.hybrid_retriever and chunks:
            chunks = self.hybrid_retriever.retrieve_hybrid(
                query=expanded_query, vector_chunks=chunks, top_k=request.max_chunks
            )
            logger.debug("hybrid_search_applied", final_chunks=len(chunks))

        return chunks

    def _normalize_and_expand_query(self, query: str) -> tuple[str, str]:
        """Normalize and expand query for retrieval.

        Args:
            query: Original user query

        Returns:
            Tuple of (normalized_query, expanded_query)
        """
        # Normalize query for better keyword matching (if enabled)
        if RAG_ENABLE_QUERY_NORMALIZATION:
            normalized_query = self.keyword_extractor.normalize_query(query)
        else:
            normalized_query = query

        # Expand query with synonyms for BM25 (if enabled)
        # This happens AFTER normalization, and is used only for BM25 keyword search
        if RAG_ENABLE_QUERY_EXPANSION:
            expanded_query = self.query_expander.expand_query(normalized_query)
        else:
            expanded_query = normalized_query

        return normalized_query, expanded_query

    def _perform_deterministic_hop(
        self,
        query: str,
        existing_chunks: list[DocumentChunk],
        query_id: UUID,
        chunk_hop_map: dict[UUID, int | str],
    ) -> tuple[list[DocumentChunk], DeterministicHopResult | None, dict[UUID, int | str]]:
        """Perform deterministic hop retrieval for unmatched keywords.

        Args:
            query: User query
            existing_chunks: Chunks from initial retrieval (Hop 0)
            query_id: Query UUID
            chunk_hop_map: Current chunk-hop mapping

        Returns:
            Tuple of (merged chunks, deterministic hop result, updated chunk_hop_map)
        """
        if not self.deterministic_hop_retriever:
            return existing_chunks, None, chunk_hop_map

        result = self.deterministic_hop_retriever.retrieve_deterministic(
            query=query,
            existing_chunks=existing_chunks,
            vector_db_service=self.vector_db,
            embedding_service=self.embedding_service,
            query_id=query_id,
        )

        if not result.triggered or not result.chunks:
            return existing_chunks, result, chunk_hop_map

        # Mark deterministic hop chunks with "D" marker
        for chunk in result.chunks:
            chunk_hop_map[chunk.chunk_id] = "D"

        # Merge chunks: existing + deterministic hop
        merged = list(existing_chunks) + result.chunks

        logger.info(
            "deterministic_hop_merged",
            initial_chunks=len(existing_chunks),
            deterministic_chunks=len(result.chunks),
            total_chunks=len(merged),
            unmatched_keywords=result.unmatched_keywords,
        )

        return merged, result, chunk_hop_map

    def _create_rag_context(
        self, query_id: UUID, chunks: list[DocumentChunk], min_relevance: float
    ) -> RAGContext:
        """Create RAGContext from retrieved chunks with relevance calculations.

        Args:
            query_id: Query UUID
            chunks: Retrieved document chunks
            min_relevance: Minimum relevance threshold

        Returns:
            RAGContext with relevance metrics
        """
        # Calculate average relevance
        if chunks:
            relevance_scores = [chunk.relevance_score for chunk in chunks]
            avg_relevance = sum(relevance_scores) / len(relevance_scores)
            meets_threshold = avg_relevance >= min_relevance
        else:
            relevance_scores = []
            avg_relevance = 0.0
            meets_threshold = False

        # Create RAGContext
        return RAGContext(
            context_id=uuid4(),
            query_id=query_id,
            document_chunks=chunks if meets_threshold else [],
            relevance_scores=relevance_scores if meets_threshold else [],
            total_chunks=len(chunks) if meets_threshold else 0,
            avg_relevance=avg_relevance,
            meets_threshold=meets_threshold,
        )

    def _perform_multi_hop_retrieval(
        self,
        request: RetrieveRequest,
        query_id: UUID,
        initial_chunks: list[DocumentChunk],
        verbose: bool = False,
        initial_chunk_hop_map: dict[UUID, int | str] | None = None,
        deterministic_result: DeterministicHopResult | None = None,
    ) -> tuple[RAGContext, list[Any], dict[UUID, int | str], DeterministicHopResult | None]:
        """Perform multi-hop retrieval starting from initial chunks.

        Args:
            request: Retrieval request parameters
            query_id: Query UUID
            initial_chunks: Initial retrieved chunks (from Hop 0 + Hop D)
            verbose: If True, capture filled prompts in HopEvaluation objects
            initial_chunk_hop_map: Pre-existing chunk-hop mapping (from Hop 0 and Hop D)
            deterministic_result: Result from deterministic hop (to pass through)

        Returns:
            Tuple of (RAGContext, hop_evaluations, chunk_hop_map, deterministic_result)
        """
        # Normalize query for hop evaluation (same as initial retrieval)
        # This ensures the hop evaluation LLM sees properly capitalized keywords
        # matching the Available Rules Reference (e.g., "accurate 1" → "Accurate 1")
        normalized_query, _ = self._normalize_and_expand_query(request.query)

        # Multi-hop retrieval is async, so we need to run it in a way that works
        # both from sync contexts (CLI) and async contexts (Discord bot)
        # Always use thread-based approach to avoid event loop conflicts
        # This works whether called from sync or async context
        result_container = []
        exception_container = []

        def run_in_thread() -> None:
            try:
                # Create a new event loop in this thread
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    result = new_loop.run_until_complete(
                        self.multi_hop_retriever.retrieve_multi_hop(
                            query=normalized_query,
                            context_key=request.context_key,
                            query_id=query_id,
                            initial_chunks=initial_chunks,
                            verbose=verbose,
                        )
                    )
                    result_container.append(result)
                finally:
                    new_loop.close()
            except Exception as e:
                exception_container.append(e)

        # Run in separate thread
        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()
        thread.join(timeout=RAG_HOP_EVALUATION_TIMEOUT)

        # Check for errors
        if exception_container:
            raise exception_container[0]

        # Check if thread finished
        if thread.is_alive():
            raise TimeoutError(f"Multi-hop retrieval timed out after {RAG_HOP_EVALUATION_TIMEOUT} seconds")

        # Return result
        if result_container:
            context, hop_evaluations, multi_hop_chunk_map = result_container[0]

            # Merge chunk_hop_maps: initial (including "D") + multi-hop
            # Multi-hop only adds new chunks with numbered hops (1, 2, ...)
            merged_chunk_hop_map: dict[UUID, int | str] = {}
            if initial_chunk_hop_map:
                merged_chunk_hop_map.update(initial_chunk_hop_map)
            # Add multi-hop chunks (won't overwrite existing 0 or "D" markers)
            for chunk_id, hop_num in multi_hop_chunk_map.items():
                if chunk_id not in merged_chunk_hop_map:
                    merged_chunk_hop_map[chunk_id] = hop_num

            # Apply final reranking and limiting to multi-hop accumulated chunks
            reranked_context, updated_chunk_hop_map = self.rerank_and_limit_final_chunks(
                _query=request.query,
                chunks=context.document_chunks,
                query_id=query_id,
                chunk_hop_map=merged_chunk_hop_map,
            )

            return reranked_context, hop_evaluations, updated_chunk_hop_map, deterministic_result

        raise RuntimeError("Multi-hop retrieval completed but produced no result")

    def _validate_query(self, query: str) -> None:
        """Validate query string.

        Args:
            query: Query string

        Raises:
            InvalidQueryError: If query is invalid
        """
        if not query or not query.strip():
            raise InvalidQueryError("Query cannot be empty")

        if len(query) > 2000:
            raise InvalidQueryError("Query exceeds 2000 character limit")

    def _results_to_chunks(self, results: dict, min_relevance: float) -> list[DocumentChunk]:
        """Convert vector DB results to DocumentChunk objects.

        Args:
            results: Vector DB query results
            min_relevance: Minimum relevance threshold

        Returns:
            List of DocumentChunk objects sorted by relevance DESC
        """
        chunks: list[DocumentChunk] = []

        # Chroma returns results as lists in the first index
        if not results["ids"] or not results["ids"][0]:
            return chunks

        ids = results["ids"][0]
        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]

        for i, chunk_id_str in enumerate(ids):
            # Convert L2 squared distance to cosine similarity
            # Chroma returns squared L2 distance for normalized embeddings
            # cosine_similarity = 1 - (L2_squared / 2)
            l2_squared = distances[i]
            relevance_score = max(0.0, 1.0 - (l2_squared / 2.0))

            # Skip if below threshold
            if relevance_score < min_relevance:
                continue

            metadata = metadatas[i]

            chunk = DocumentChunk(
                chunk_id=UUID(chunk_id_str),
                document_id=UUID(metadata.get("document_id", str(uuid4()))),
                text=documents[i],
                header=metadata.get("header", ""),
                header_level=metadata.get("header_level", 0),
                metadata=metadata,
                relevance_score=relevance_score,
                position_in_doc=metadata.get("position", 0),
            )

            chunks.append(chunk)

        # Sort by relevance score DESC (contract requirement)
        chunks.sort(key=lambda c: c.relevance_score, reverse=True)

        return chunks

    def rerank_and_limit_final_chunks(
        self, _query: str, chunks: list[DocumentChunk], query_id: UUID, chunk_hop_map: dict[UUID, int | str]
    ) -> tuple[RAGContext, dict[UUID, int | str]]:
        """Sort accumulated chunks by relevance score and limit to maximum count.

        This method is used by multi-hop retrieval to finalize all accumulated chunks
        after all hops are complete, sorting by their original relevance scores and
        limiting to MAXIMUM_FINAL_CHUNK_COUNT.

        Args:
            query: Original user query (unused, kept for interface compatibility)
            chunks: Accumulated chunks to limit
            query_id: Query UUID for creating RAGContext
            chunk_hop_map: Mapping of chunk_id to hop number

        Returns:
            Tuple of (limited RAGContext, updated chunk_hop_map)
        """
        if not chunks:
            empty_context = RAGContext.from_retrieval(query_id=query_id, chunks=[])
            return empty_context, {}

        logger.info(
            "applying_final_reranking",
            chunks_before=len(chunks),
            max_chunks=MAXIMUM_FINAL_CHUNK_COUNT,
        )

        # Sort by relevance score descending and take top MAXIMUM_FINAL_CHUNK_COUNT
        # Each chunk retains its original relevance score from its retrieval context
        reranked_chunks = sorted(chunks, key=lambda c: c.relevance_score, reverse=True)[
            :MAXIMUM_FINAL_CHUNK_COUNT
        ]

        # Update chunk_hop_map to include only remaining chunks
        remaining_chunk_ids = {c.chunk_id for c in reranked_chunks}
        updated_chunk_hop_map = {
            chunk_id: chunk_hop_map[chunk_id]
            for chunk_id in remaining_chunk_ids
            if chunk_id in chunk_hop_map
        }

        # Create new RAGContext with limited chunks
        reranked_context = RAGContext.from_retrieval(query_id=query_id, chunks=reranked_chunks)

        logger.info(
            "final_reranking_complete",
            chunks_after=len(reranked_chunks),
        )

        return reranked_context, updated_chunk_hop_map

    def _build_hybrid_index(self) -> None:
        """Build BM25 index from all chunks in vector database."""
        if not self.hybrid_retriever:
            return

        try:
            # Get all chunks from vector DB
            all_results = self.vector_db.collection.get(include=["documents", "metadatas"])

            if not all_results["ids"]:
                logger.warning("hybrid_index_empty", message="No documents in vector DB")
                return

            # Convert to DocumentChunk objects
            chunks: list[DocumentChunk] = []
            for i, chunk_id_str in enumerate(all_results["ids"]):
                metadata = all_results["metadatas"][i]
                chunk = DocumentChunk(
                    chunk_id=UUID(chunk_id_str),
                    document_id=UUID(metadata.get("document_id", str(uuid4()))),
                    text=all_results["documents"][i],
                    header=metadata.get("header", ""),
                    header_level=metadata.get("header_level", 0),
                    metadata=metadata,
                    relevance_score=1.0,  # Placeholder for indexing
                    position_in_doc=metadata.get("position", 0),
                )
                chunks.append(chunk)

            # Build BM25 index
            self.hybrid_retriever.index_chunks(chunks)

            logger.info(
                "hybrid_index_built",
                chunk_count=len(chunks),
                stats=self.hybrid_retriever.get_stats(),
            )

        except Exception as e:
            logger.error("hybrid_index_build_failed", error=str(e))
            # Non-fatal: continue without hybrid search
            self.hybrid_retriever = None
