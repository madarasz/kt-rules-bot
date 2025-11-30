"""Shared query orchestrator for RAG + LLM pipeline.

This orchestrator provides the core "user question → RAG → LLM answer" flow
used by all entry points (Discord bot, CLI query, quality tests, RAG tests).

Design principles:
- Delegates to RAG service (preserves all RAG features)
- Supports 3 usage patterns: all-in-one, separate steps, RAG-only
- Optional components via dependency injection (analytics, rate limiting)
- Entry points provide their own retry strategies
"""

import time
from uuid import UUID

from src.lib.constants import LLM_GENERATION_TIMEOUT, RAG_MAX_CHUNKS
from src.lib.logging import get_logger
from src.lib.tokens import estimate_embedding_cost
from src.models.rag_context import RAGContext
from src.models.rag_request import RetrieveRequest
from src.services.llm.base import GenerationConfig, GenerationRequest
from src.services.llm.factory import LLMProviderFactory
from src.services.llm.quote_validator import QuoteValidator
from src.services.rag.retriever import RAGRetriever

logger = get_logger(__name__)


class QueryOrchestrator:
    """Shared orchestration for "question → RAG → LLM answer" flow.

    Used by all entry points to ensure consistent behavior.

    Supports three usage patterns:
    1. Full flow: process_query() - retrieve + generate (Discord, CLI)
    2. Separate steps: retrieve_rag() then generate_with_context() (Quality tests)
    3. RAG-only: retrieve_rag() only (RAG tests)
    """

    def __init__(
        self,
        rag_retriever: RAGRetriever,
        llm_factory: LLMProviderFactory,
        enable_quote_validation: bool = True,
        quote_similarity_threshold: float = 0.85,
    ):
        """Initialize orchestrator with core services.

        Args:
            rag_retriever: RAG retrieval service (singleton)
            llm_factory: LLM provider factory
            enable_quote_validation: Whether to validate quotes against RAG chunks
            quote_similarity_threshold: Minimum similarity for valid quotes (0-1)
        """
        self.rag = rag_retriever
        self.llm_factory = llm_factory
        self.enable_quote_validation = enable_quote_validation
        self.quote_validator = QuoteValidator(similarity_threshold=quote_similarity_threshold)

    async def retrieve_rag(
        self,
        query: str,
        query_id: UUID,
        max_chunks: int = RAG_MAX_CHUNKS,
        context_key: str = "default",
        use_multi_hop: bool = True,
    ) -> tuple[RAGContext, list, dict, float]:
        """Step 1: RAG retrieval only.

        Delegates to RAGRetriever which handles ALL RAG features:
        - Query normalization (RAG_ENABLE_QUERY_NORMALIZATION)
        - Query expansion (RAG_ENABLE_QUERY_EXPANSION)
        - Hybrid search (vector + BM25 with RRF fusion)
        - Multi-hop retrieval with team filtering (if use_multi_hop=True)
        - Final chunk limiting (MAXIMUM_FINAL_CHUNK_COUNT)

        Args:
            query: User question (sanitized)
            query_id: Unique identifier for this query
            max_chunks: Maximum chunks to retrieve
            context_key: Context key for conversation tracking
            use_multi_hop: Enable multi-hop retrieval

        Returns:
            Tuple of:
            - RAG context with document chunks
            - Multi-hop evaluations (list, empty if not used)
            - Chunk-hop map (dict, empty if not used)
            - Embedding cost estimate (float)

        Use case: Quality tests retrieve once, then generate_with_context() N times
        """
        start_time = time.time()

        # Delegate to RAG service (all features enabled via config)
        rag_context, hop_evaluations, chunk_hop_map = self.rag.retrieve(
            RetrieveRequest(
                query=query,
                context_key=context_key,
                max_chunks=max_chunks,
                use_multi_hop=use_multi_hop,
            ),
            query_id=query_id,
        )

        # Calculate embedding cost
        embedding_cost = estimate_embedding_cost(query)

        retrieval_time_ms = int((time.time() - start_time) * 1000)

        logger.debug(
            "RAG retrieval complete",
            extra={
                "correlation_id": str(query_id),
                "chunks_retrieved": rag_context.total_chunks,
                "avg_relevance": rag_context.avg_relevance,
                "hops_used": len(hop_evaluations or []),
                "retrieval_time_ms": retrieval_time_ms,
            },
        )

        return rag_context, hop_evaluations, chunk_hop_map, embedding_cost

    async def generate_with_context(
        self,
        query: str,
        query_id: UUID,
        model: str,
        rag_context: RAGContext,
        llm_provider=None,
        generation_timeout: int = LLM_GENERATION_TIMEOUT,
    ) -> tuple[object, list[str]]:
        """Step 2: LLM generation with pre-retrieved RAG context.

        Flow:
        1. LLM generation (entry point provides retry wrapper)
        2. Quote validation (if enabled)
        3. Returns raw LLM response

        Note: Entry points are responsible for:
        - Retry logic (each has their own strategy)
        - Rate limiting (each has their own limits)
        - Cost calculation
        - Analytics storage
        - Response formatting

        Args:
            query: User question
            query_id: Unique identifier for this query
            model: LLM model to use
            rag_context: Pre-retrieved RAG context
            llm_provider: LLM provider instance (if None, creates from factory)
            generation_timeout: Timeout in seconds

        Returns:
            Tuple of:
            - LLM response object
            - Chunk IDs list

        Use case: Quality tests call this N times with same rag_context
        """
        correlation_id = str(query_id)
        chunk_ids = [str(chunk.chunk_id) for chunk in rag_context.document_chunks]

        # Create LLM provider if not provided
        if llm_provider is None:
            llm_provider = self.llm_factory.create(model_name=model)

        start_time = time.time()

        # Generate response
        # Note: Retry logic is applied by the entry point before calling this method
        llm_response = await llm_provider.generate(
            GenerationRequest(
                prompt=query,
                context=[chunk.text for chunk in rag_context.document_chunks],
                config=GenerationConfig(timeout_seconds=generation_timeout),
                chunk_ids=chunk_ids,
            )
        )

        generation_time_ms = int((time.time() - start_time) * 1000)

        logger.debug(
            "LLM generation complete",
            extra={
                "correlation_id": correlation_id,
                "model": model,
                "confidence": llm_response.confidence_score,
                "token_count": llm_response.token_count,
                "generation_time_ms": generation_time_ms,
            },
        )

        # Validate quotes if enabled
        if self.enable_quote_validation:
            self._validate_quotes(llm_response, rag_context, chunk_ids, correlation_id)

        return llm_response, chunk_ids

    async def process_query(
        self,
        query: str,
        query_id: UUID,
        model: str,
        max_chunks: int = RAG_MAX_CHUNKS,
        context_key: str = "default",
        use_multi_hop: bool = True,
        llm_provider=None,
        generation_timeout: int = LLM_GENERATION_TIMEOUT,
    ) -> tuple[object, RAGContext, list, dict, float]:
        """Full flow: retrieve + generate (convenience method).

        Flow:
        1. Input validation
        2. RAG retrieval (calls retrieve_rag)
        3. LLM generation (calls generate_with_context)

        Args:
            query: User question
            query_id: Unique identifier for this query
            model: LLM model to use
            max_chunks: Maximum chunks to retrieve
            context_key: Context key for conversation tracking
            use_multi_hop: Enable multi-hop retrieval
            llm_provider: LLM provider instance (if None, creates from factory)
            generation_timeout: Timeout in seconds

        Returns:
            Tuple of:
            - LLM response object
            - RAG context
            - Multi-hop evaluations
            - Chunk-hop map
            - Embedding cost

        Use case: Discord bot, CLI query (one-shot queries)
        """
        # Step 1: RAG retrieval
        rag_context, hop_evaluations, chunk_hop_map, embedding_cost = await self.retrieve_rag(
            query=query,
            query_id=query_id,
            max_chunks=max_chunks,
            context_key=context_key,
            use_multi_hop=use_multi_hop,
        )

        # Step 2: LLM generation
        llm_response, chunk_ids = await self.generate_with_context(
            query=query,
            query_id=query_id,
            model=model,
            rag_context=rag_context,
            llm_provider=llm_provider,
            generation_timeout=generation_timeout,
        )

        return llm_response, rag_context, hop_evaluations, chunk_hop_map, embedding_cost

    def _validate_quotes(
        self,
        llm_response,
        rag_context: RAGContext,
        chunk_ids: list[str],
        correlation_id: str,
    ) -> object | None:
        """Validate quotes against RAG context.

        Args:
            llm_response: LLM response object
            rag_context: RAG context with document chunks
            chunk_ids: List of chunk IDs
            correlation_id: Correlation ID for logging

        Returns:
            QuoteValidationResult or None
        """
        # Parse structured response to get quotes
        try:
            from src.models.structured_response import StructuredLLMResponse

            structured_data = StructuredLLMResponse.from_json(llm_response.answer_text)

            # Skip validation if smalltalk or no quotes
            if structured_data.smalltalk or not structured_data.quotes:
                return None

            # Validate quotes
            quote_validation_result = self.quote_validator.validate(
                quotes=[
                    {
                        "quote_title": q.quote_title,
                        "quote_text": q.quote_text,
                        "chunk_id": getattr(q, "chunk_id", ""),
                    }
                    for q in structured_data.quotes
                ],
                context_chunks=[chunk.text for chunk in rag_context.document_chunks],
                chunk_ids=chunk_ids,
            )

            logger.info(
                "Quote validation complete",
                extra={
                    "correlation_id": correlation_id,
                    "validation_score": quote_validation_result.validation_score,
                    "valid_quotes": quote_validation_result.valid_quotes,
                    "invalid_quotes": len(quote_validation_result.invalid_quotes),
                },
            )

            # Log invalid quotes
            if not quote_validation_result.is_valid:
                for invalid_quote in quote_validation_result.invalid_quotes:
                    logger.warning(
                        "Invalid quote detected",
                        extra={
                            "correlation_id": correlation_id,
                            "quote_title": invalid_quote.get("quote_title", ""),
                            "reason": invalid_quote.get("reason", ""),
                        },
                    )

            return quote_validation_result

        except Exception as e:
            logger.warning(
                f"Quote validation failed: {e}",
                extra={"correlation_id": correlation_id},
            )
            return None
