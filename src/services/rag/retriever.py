"""RAG retrieval service implementing the RAG pipeline contract.

Implements retrieve() method from specs/001-we-are-building/contracts/rag-pipeline.md
"""

from typing import List
from uuid import UUID, uuid4
from dataclasses import dataclass

from src.models.rag_context import RAGContext, DocumentChunk
from src.services.rag.embeddings import EmbeddingService
from src.services.rag.vector_db import VectorDBService
from src.lib.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RetrieveRequest:
    """RAG retrieval request parameters."""

    query: str  # User question (sanitized)
    context_key: str  # "{channel_id}:{user_id}" for conversation tracking
    max_chunks: int = 5  # Maximum document chunks to retrieve
    min_relevance: float = 0.6  # Minimum cosine similarity threshold


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
    ):
        """Initialize RAG retriever.

        Args:
            embedding_service: Embedding service (creates if None)
            vector_db_service: Vector DB service (creates if None)
        """
        self.embedding_service = embedding_service or EmbeddingService()
        self.vector_db = vector_db_service or VectorDBService()

        logger.info("rag_retriever_initialized")

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
            # Generate query embedding
            query_embedding = self.embedding_service.embed_text(request.query)

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
            # Convert distance to similarity (Chroma uses L2 distance)
            # Lower distance = higher similarity
            # Normalize to 0-1 range (approximate)
            distance = distances[i]
            relevance_score = max(0.0, 1.0 - (distance / 2.0))

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
