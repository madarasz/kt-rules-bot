"""RAG retrieval service implementing the RAG pipeline contract.

Implements retrieve() method from specs/001-we-are-building/contracts/rag-pipeline.md
"""

from typing import List
from uuid import UUID, uuid4
from dataclasses import dataclass

from src.models.rag_context import RAGContext, DocumentChunk
from src.services.rag.embeddings import EmbeddingService
from src.services.rag.vector_db import VectorDBService
from src.services.rag.hybrid_retriever import HybridRetriever
from src.services.rag.keyword_extractor import KeywordExtractor
from src.services.rag.query_expander import QueryExpander
from src.lib.constants import (
    RAG_MAX_CHUNKS,
    RAG_MIN_RELEVANCE,
    RRF_K,
    BM25_K1,
    BM25_B,
    RAG_ENABLE_QUERY_NORMALIZATION,
    RAG_ENABLE_QUERY_EXPANSION,
    RAG_SYNONYM_DICT_PATH,
)
from src.lib.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RetrieveRequest:
    """RAG retrieval request parameters."""

    query: str  # User question (sanitized)
    context_key: str  # "{channel_id}:{user_id}" for conversation tracking
    max_chunks: int = RAG_MAX_CHUNKS  # Maximum document chunks to retrieve
    min_relevance: float = RAG_MIN_RELEVANCE  # Minimum cosine similarity threshold
    use_hybrid: bool = True  # Enable hybrid search (BM25 + vector)


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
        rrf_k: int = RRF_K,
        bm25_k1: float = BM25_K1,
        bm25_b: float = BM25_B,
    ):
        """Initialize RAG retriever.

        Args:
            embedding_service: Embedding service (creates if None)
            vector_db_service: Vector DB service (creates if None)
            keyword_extractor: Keyword extractor for query normalization (creates if None)
            query_expander: Query expander for synonym expansion (creates if None)
            enable_hybrid: Enable hybrid search with BM25 (default: True)
            rrf_k: RRF constant for hybrid fusion (default: 60)
            bm25_k1: BM25 term frequency saturation parameter (default: 1.5)
            bm25_b: BM25 document length normalization parameter (default: 0.75)
        """
        self.embedding_service = embedding_service or EmbeddingService()
        self.vector_db = vector_db_service or VectorDBService()
        self.keyword_extractor = keyword_extractor or KeywordExtractor()
        self.query_expander = query_expander or QueryExpander(RAG_SYNONYM_DICT_PATH)
        self.enable_hybrid = enable_hybrid

        # Initialize hybrid retriever if enabled
        self.hybrid_retriever: HybridRetriever | None = None
        if enable_hybrid:
            self.hybrid_retriever = HybridRetriever(k=rrf_k, bm25_k1=bm25_k1, bm25_b=bm25_b)
            # Index all chunks from vector DB
            self._build_hybrid_index()

        logger.info(
            "rag_retriever_initialized",
            hybrid_enabled=enable_hybrid,
            rrf_k=rrf_k,
            bm25_k1=bm25_k1,
            bm25_b=bm25_b,
            keywords_loaded=self.keyword_extractor.get_keyword_count(),
            synonyms_loaded=self.query_expander.get_stats()["total_synonyms"]
        )

    def retrieve(self, request: RetrieveRequest, query_id: UUID) -> RAGContext:
        """Retrieve relevant rule documents for a user query.

        Implements the RAG pipeline contract from contracts/rag-pipeline.md.

        Args:
            request: Retrieval request parameters
            query_id: Query UUID for tracking

        Returns:
            RAGContext with retrieved chunks

        Raises:
            InvalidQueryError: If query is invalid
            VectorDBUnavailableError: If vector DB is unavailable
        """
        # Validate query
        self._validate_query(request.query)

        try:
            # Normalize query for better keyword matching (if enabled)
            if RAG_ENABLE_QUERY_NORMALIZATION:
                normalized_query = self.keyword_extractor.normalize_query(request.query)
            else:
                normalized_query = request.query

            # Expand query with synonyms for BM25 (if enabled)
            # This happens AFTER normalization, and is used only for BM25 keyword search
            if RAG_ENABLE_QUERY_EXPANSION:
                expanded_query = self.query_expander.expand_query(normalized_query)
            else:
                expanded_query = normalized_query

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
                query_embeddings=[query_embedding],
                n_results=request.max_chunks,
            )

            # Convert results to DocumentChunk objects
            chunks = self._results_to_chunks(results, request.min_relevance)

            # Apply hybrid search if enabled
            # Use EXPANDED query for BM25 to catch user-friendly synonyms
            if request.use_hybrid and self.hybrid_retriever and chunks:
                chunks = self.hybrid_retriever.retrieve_hybrid(
                    query=expanded_query,
                    vector_chunks=chunks,
                    top_k=request.max_chunks
                )
                logger.debug("hybrid_search_applied", final_chunks=len(chunks))

            # Calculate average relevance
            if chunks:
                relevance_scores = [chunk.relevance_score for chunk in chunks]
                avg_relevance = sum(relevance_scores) / len(relevance_scores)
                meets_threshold = avg_relevance >= request.min_relevance
            else:
                relevance_scores = []
                avg_relevance = 0.0
                meets_threshold = False

            # Create RAGContext
            context = RAGContext(
                context_id=uuid4(),
                query_id=query_id,
                document_chunks=chunks if meets_threshold else [],
                relevance_scores=relevance_scores if meets_threshold else [],
                total_chunks=len(chunks) if meets_threshold else 0,
                avg_relevance=avg_relevance,
                meets_threshold=meets_threshold,
            )

            logger.info(
                "retrieval_completed",
                query_id=str(query_id),
                chunks_found=len(chunks),
                avg_relevance=avg_relevance,
                meets_threshold=meets_threshold,
            )

            return context

        except Exception as e:
            logger.error(
                "retrieval_failed",
                query_id=str(query_id),
                error=str(e),
            )
            raise VectorDBUnavailableError(f"Vector DB query failed: {e}") from e

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

    def _results_to_chunks(
        self, results: dict, min_relevance: float
    ) -> List[DocumentChunk]:
        """Convert vector DB results to DocumentChunk objects.

        Args:
            results: Vector DB query results
            min_relevance: Minimum relevance threshold

        Returns:
            List of DocumentChunk objects sorted by relevance DESC
        """
        chunks: List[DocumentChunk] = []

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

    def _build_hybrid_index(self) -> None:
        """Build BM25 index from all chunks in vector database."""
        if not self.hybrid_retriever:
            return

        try:
            # Get all chunks from vector DB
            all_results = self.vector_db.collection.get(
                include=["documents", "metadatas"]
            )

            if not all_results["ids"]:
                logger.warning("hybrid_index_empty", message="No documents in vector DB")
                return

            # Convert to DocumentChunk objects
            chunks: List[DocumentChunk] = []
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
                stats=self.hybrid_retriever.get_stats()
            )

        except Exception as e:
            logger.error("hybrid_index_build_failed", error=str(e))
            # Non-fatal: continue without hybrid search
            self.hybrid_retriever = None
