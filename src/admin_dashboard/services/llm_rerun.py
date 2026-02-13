"""Service for re-running queries with different LLM models.

Supports two modes:
- Fresh RAG retrieval: re-runs the full retrieval pipeline with the current vector DB
- Reuse RAG context: reconstructs context from stored DB chunks for LLM-only comparison
"""

import asyncio
import time
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from src.lib.constants import LLM_GENERATION_TIMEOUT, QUALITY_TEST_PROVIDERS, RAG_MAX_CHUNKS
from src.lib.logging import get_logger
from src.lib.tokens import estimate_cost
from src.models.rag_context import DocumentChunk, RAGContext
from src.models.structured_response import StructuredLLMResponse
from src.services.llm.base import GenerationConfig, GenerationRequest, LLMResponse
from src.services.llm.factory import LLMProviderFactory
from src.services.llm.retry import retry_on_content_filter

logger = get_logger(__name__)


@dataclass
class RerunResult:
    """Result of re-running a query with a different LLM model."""

    model: str
    answer_text: str = ""
    structured_response: StructuredLLMResponse | None = None
    latency_ms: int = 0
    token_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    rag_info: dict = field(default_factory=dict)
    error: str | None = None


def get_available_models() -> list[str]:
    """Get list of available models for re-running queries.

    Returns:
        List of model name strings from QUALITY_TEST_PROVIDERS.
    """
    return list(QUALITY_TEST_PROVIDERS)


def _build_rag_context_from_db_chunks(chunks: list[dict], query_id: UUID) -> RAGContext:
    """Reconstruct RAGContext from stored DB chunks.

    Args:
        chunks: List of chunk dictionaries from the analytics database.
        query_id: Query UUID.

    Returns:
        RAGContext reconstructed from stored chunk data.
    """
    doc_chunks = []
    for chunk in chunks:
        doc_chunk = DocumentChunk(
            chunk_id=uuid4(),  # Generate new ID (original not stored in analytics DB)
            document_id=uuid4(),  # Not stored in analytics DB
            text=chunk.get("chunk_text", ""),
            header=chunk.get("chunk_header", ""),
            header_level=2,  # Default; not stored in analytics DB
            metadata={
                "source": chunk.get("document_name", "unknown"),
                "doc_type": chunk.get("document_type", "core-rules"),
                "publication_date": "unknown",
            },
            relevance_score=chunk.get("final_score", 0.0),
            position_in_doc=chunk.get("rank", 0),
        )
        doc_chunks.append(doc_chunk)

    # Sort by relevance DESC (should already be, but ensure)
    doc_chunks.sort(key=lambda c: c.relevance_score, reverse=True)

    return RAGContext.from_retrieval(query_id=query_id, chunks=doc_chunks)


def _initialize_orchestrator():
    """Initialize the QueryOrchestrator with RAG services.

    Returns:
        QueryOrchestrator instance.

    Raises:
        Exception: If service initialization fails.
    """
    from src.services.orchestrator import QueryOrchestrator
    from src.services.rag.embeddings import EmbeddingService
    from src.services.rag.retriever import RAGRetriever
    from src.services.rag.vector_db import VectorDBService

    vector_db = VectorDBService(collection_name="kill_team_rules")
    embedding_service = EmbeddingService()
    rag_retriever = RAGRetriever(
        vector_db_service=vector_db,
        embedding_service=embedding_service,
        enable_multi_hop=True,
    )
    llm_factory = LLMProviderFactory()
    orchestrator = QueryOrchestrator(
        rag_retriever=rag_retriever,
        llm_factory=llm_factory,
        enable_quote_validation=True,
    )
    return orchestrator


async def _rerun_query_async(
    query_text: str,
    chunks_from_db: list[dict],
    model_name: str,
    reuse_rag_context: bool,
) -> RerunResult:
    """Async implementation of query re-run.

    Args:
        query_text: The original query text.
        chunks_from_db: Stored chunks from the analytics database.
        model_name: LLM model name to use.
        reuse_rag_context: If True, reconstruct context from DB chunks.
                          If False, perform fresh RAG retrieval.

    Returns:
        RerunResult with response data or error.
    """
    result = RerunResult(model=model_name)
    query_id = uuid4()

    try:
        # Initialize orchestrator (needed for both paths)
        orchestrator = _initialize_orchestrator()

        # Step 1: Get RAG context
        if reuse_rag_context:
            rag_context = _build_rag_context_from_db_chunks(chunks_from_db, query_id)
            result.rag_info = {
                "source": "Reused from DB",
                "chunk_count": rag_context.total_chunks,
                "avg_relevance": rag_context.avg_relevance,
            }
        else:
            # Fresh RAG retrieval
            rag_context, _hop_evals, _chunk_hop_map, _embedding_cost, retrieval_time_ms = (
                await orchestrator.retrieve_rag(
                    query=query_text,
                    query_id=query_id,
                    max_chunks=RAG_MAX_CHUNKS,
                    context_key="admin:rerun",
                    use_multi_hop=True,
                )
            )
            result.rag_info = {
                "source": "Fresh retrieval",
                "chunk_count": rag_context.total_chunks,
                "avg_relevance": rag_context.avg_relevance,
                "retrieval_time_ms": retrieval_time_ms,
            }

        # Step 2: Create LLM provider
        llm_provider = LLMProviderFactory.create(model_name)
        if llm_provider is None:
            result.error = f"❌ Cannot create provider for {model_name}. Check API key configuration."
            return result

        # Step 3: Generate response with retry logic
        start_time = time.time()

        async def generate():
            return await orchestrator.generate_with_context(
                query=query_text,
                query_id=query_id,
                model=model_name,
                rag_context=rag_context,
                llm_provider=llm_provider,
                generation_timeout=LLM_GENERATION_TIMEOUT,
            )

        llm_response, _chunk_ids = await retry_on_content_filter(
            generate,
            timeout_seconds=LLM_GENERATION_TIMEOUT,
        )

        elapsed_ms = int((time.time() - start_time) * 1000)

        # Populate result
        result.answer_text = llm_response.answer_text
        result.latency_ms = elapsed_ms
        result.token_count = llm_response.token_count
        result.prompt_tokens = llm_response.prompt_tokens
        result.completion_tokens = llm_response.completion_tokens
        result.cost_usd = estimate_cost(
            llm_response.prompt_tokens, llm_response.completion_tokens, model_name
        )

        # Try to parse as structured response
        try:
            result.structured_response = StructuredLLMResponse.from_json(llm_response.answer_text)
        except ValueError:
            pass  # Will display raw text instead

    except Exception as e:
        logger.error(f"Re-run query failed: {e}", exc_info=True)
        result.error = f"❌ {type(e).__name__}: {e}"

    return result


def rerun_query(
    query_text: str,
    chunks_from_db: list[dict],
    model_name: str,
    reuse_rag_context: bool,
) -> RerunResult:
    """Re-run a query with a different LLM model.

    Synchronous wrapper around the async implementation.

    Args:
        query_text: The original query text.
        chunks_from_db: Stored chunks from the analytics database.
        model_name: LLM model name to use.
        reuse_rag_context: If True, reconstruct context from DB chunks.
                          If False, perform fresh RAG retrieval.

    Returns:
        RerunResult with response data or error.
    """
    # Run async code in a new event loop (Streamlit runs synchronously)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If there's already a running loop (unlikely in Streamlit), use nest_asyncio pattern
            import nest_asyncio

            nest_asyncio.apply()
            return loop.run_until_complete(
                _rerun_query_async(query_text, chunks_from_db, model_name, reuse_rag_context)
            )
    except RuntimeError:
        pass

    return asyncio.run(
        _rerun_query_async(query_text, chunks_from_db, model_name, reuse_rag_context)
    )
