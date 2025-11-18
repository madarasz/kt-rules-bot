"""CLI command to test RAG + LLM locally without Discord.

Usage:
    python -m src.cli.test_query "What actions can I take during movement?"
"""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from uuid import uuid4

import src.lib.constants as constants
from src.lib.config import get_config
from src.lib.constants import (
    ALL_LLM_PROVIDERS,
    EMBEDDING_MODEL,
    LLM_GENERATION_TIMEOUT,
    RAG_MAX_CHUNKS,
    RAG_MAX_HOPS,
)
from src.lib.logging import get_logger
from src.lib.statistics import format_statistics_summary
from src.lib.tokens import estimate_cost, estimate_embedding_cost
from src.models.rag_request import RetrieveRequest
from src.services.llm.base import GenerationConfig, GenerationRequest
from src.services.llm.factory import LLMProviderFactory
from src.services.llm.retry import retry_on_content_filter
from src.services.llm.validator import ResponseValidator
from src.services.rag.embeddings import EmbeddingService
from src.services.rag.retriever import RAGRetriever
from src.services.rag.vector_db import VectorDBService

logger = get_logger(__name__)


class TestQueryServices:
    """Container for initialized services."""

    def __init__(self, rag_retriever, llm_provider=None, validator=None):
        """Initialize services container.

        Args:
            rag_retriever: RAG retrieval service
            llm_provider: Optional LLM provider (not needed for RAG-only)
            validator: Optional response validator (not needed for RAG-only)
        """
        self.rag_retriever = rag_retriever
        self.llm_provider = llm_provider
        self.validator = validator


class CostBreakdown:
    """Container for cost breakdown calculations."""

    def __init__(
        self,
        initial_embedding_cost: float,
        hop_embedding_cost: float,
        hop_evaluation_cost: float,
        llm_cost: float = 0.0,
    ):
        """Initialize cost breakdown.

        Args:
            initial_embedding_cost: Cost of initial query embedding
            hop_embedding_cost: Cost of hop query embeddings
            hop_evaluation_cost: Cost of hop LLM evaluations
            llm_cost: Cost of main LLM generation (optional)
        """
        self.initial_embedding_cost = initial_embedding_cost
        self.hop_embedding_cost = hop_embedding_cost
        self.hop_evaluation_cost = hop_evaluation_cost
        self.llm_cost = llm_cost

    @property
    def total_rag_cost(self) -> float:
        """Calculate total RAG cost (embedding + hop evaluations)."""
        return self.initial_embedding_cost + self.hop_embedding_cost + self.hop_evaluation_cost


def _initialize_services(model: str | None, rag_only: bool) -> TestQueryServices:
    """Initialize required services for test query.

    Args:
        model: LLM model to use (None for RAG-only)
        rag_only: Whether to run in RAG-only mode

    Returns:
        TestQueryServices container

    Raises:
        SystemExit: If service initialization fails
    """
    try:
        vector_db = VectorDBService(collection_name="kill_team_rules")
        embedding_service = EmbeddingService()
        rag_retriever = RAGRetriever(
            vector_db_service=vector_db,
            embedding_service=embedding_service,
            enable_multi_hop=(RAG_MAX_HOPS > 0),
        )

        # Only initialize LLM services if not rag_only
        llm_provider = None
        validator = None
        if not rag_only:
            llm_factory = LLMProviderFactory()
            llm_provider = llm_factory.create(model)
            validator = ResponseValidator(
                llm_confidence_threshold=0.7,
                rag_score_threshold=0.45,
            )

        return TestQueryServices(rag_retriever, llm_provider, validator)

    except Exception as e:
        logger.error(f"Failed to initialize services: {e}", exc_info=True)
        print(f"❌ Error initializing services: {e}")
        sys.exit(1)


def _perform_rag_retrieval(
    services: TestQueryServices, query: str, max_chunks: int, max_hops: int
) -> tuple:
    """Perform RAG retrieval and calculate costs.

    Args:
        services: Test query services
        query: User query
        max_chunks: Maximum chunks to retrieve
        max_hops: Maximum hops for multi-hop retrieval

    Returns:
        Tuple of (rag_context, hop_evaluations, chunk_hop_map, rag_time, cost_breakdown)
    """
    start_time = datetime.now(UTC)
    query_id = uuid4()

    rag_context, hop_evaluations, chunk_hop_map = services.rag_retriever.retrieve(
        RetrieveRequest(
            query=query,
            context_key="cli:test",
            max_chunks=max_chunks,
            use_multi_hop=(max_hops > 0),
        ),
        query_id=query_id,
    )

    rag_time = (datetime.now(UTC) - start_time).total_seconds()

    # Calculate costs
    cost_breakdown = _calculate_rag_costs(query, hop_evaluations)

    return rag_context, hop_evaluations, chunk_hop_map, rag_time, cost_breakdown


def _calculate_rag_costs(query: str, hop_evaluations: list | None) -> CostBreakdown:
    """Calculate RAG-related costs.

    Args:
        query: User query
        hop_evaluations: Optional list of hop evaluations

    Returns:
        CostBreakdown instance
    """
    # 1. Initial retrieval embedding
    initial_embedding_cost = estimate_embedding_cost(query, EMBEDDING_MODEL)

    # 2. Hop query embeddings
    hop_embedding_cost = 0.0
    if hop_evaluations:
        for hop_eval in hop_evaluations:
            if hop_eval.missing_query:
                hop_embedding_cost += estimate_embedding_cost(hop_eval.missing_query, EMBEDDING_MODEL)

    # 3. Hop evaluation LLM costs
    hop_evaluation_cost = sum(hop_eval.cost_usd for hop_eval in hop_evaluations or [])

    return CostBreakdown(initial_embedding_cost, hop_embedding_cost, hop_evaluation_cost)


async def _perform_llm_generation(services: TestQueryServices, query: str, rag_context) -> tuple:
    """Perform LLM generation with retry logic.

    Args:
        services: Test query services
        query: User query
        rag_context: RAG context with chunks

    Returns:
        Tuple of (llm_response, llm_time, llm_cost)
    """
    llm_start = datetime.now(UTC)

    llm_response = await retry_on_content_filter(
        services.llm_provider.generate,
        GenerationRequest(
            prompt=query,
            context=[chunk.text for chunk in rag_context.document_chunks],
            config=GenerationConfig(timeout_seconds=LLM_GENERATION_TIMEOUT),
        ),
        timeout_seconds=LLM_GENERATION_TIMEOUT,
    )

    llm_time = (datetime.now(UTC) - llm_start).total_seconds()

    # Calculate LLM cost
    llm_cost = estimate_cost(
        llm_response.prompt_tokens, llm_response.completion_tokens, llm_response.model_version
    )

    return llm_response, llm_time, llm_cost


def _print_rag_results(
    rag_context, hop_evaluations, chunk_hop_map, rag_time, max_hops: int
) -> None:
    """Print RAG retrieval results.

    Args:
        rag_context: RAG context with chunks
        hop_evaluations: List of hop evaluations
        chunk_hop_map: Chunk ID to hop number mapping
        rag_time: Time taken for RAG retrieval
        max_hops: Maximum hops configured
    """
    print(f"Retrieved {rag_context.total_chunks} chunks in {rag_time:.2f}s")
    print(f"Average relevance: {rag_context.avg_relevance:.2f}")
    print(f"Meets threshold: {rag_context.meets_threshold}")
    if hop_evaluations:
        print(f"Hops used: {len(hop_evaluations)}")
    print()

    # Display hop information if multi-hop was used
    if hop_evaluations:
        _print_multi_hop_info(hop_evaluations, chunk_hop_map, rag_context)

    # Display all chunks
    if rag_context.document_chunks:
        _print_chunks(rag_context.document_chunks, chunk_hop_map, hop_evaluations)


def _print_multi_hop_info(hop_evaluations, chunk_hop_map, rag_context) -> None:
    """Print multi-hop retrieval information.

    Args:
        hop_evaluations: List of hop evaluations
        chunk_hop_map: Chunk ID to hop number mapping
        rag_context: RAG context with chunks
    """
    print(f"\n{'=' * 60}")
    print(f"MULTI-HOP INFORMATION ({len(hop_evaluations)} hops)")
    print(f"{'=' * 60}")

    for i, hop_eval in enumerate(hop_evaluations, 1):
        print(f"\n--- Hop {i} ---")
        print(f"Can Answer: {'✅ Yes' if hop_eval.can_answer else '❌ No'}")
        print(f"Reasoning: {hop_eval.reasoning}")
        if hop_eval.missing_query:
            print(f'Missing Query: "{hop_eval.missing_query}"')

    print(f"\n{'=' * 60}")
    print("CHUNKS BY HOP")
    print(f"{'=' * 60}")

    chunks_by_hop = {}
    for chunk in rag_context.document_chunks:
        hop_num = chunk_hop_map.get(chunk.chunk_id, 0)
        if hop_num not in chunks_by_hop:
            chunks_by_hop[hop_num] = []
        chunks_by_hop[hop_num].append(chunk)

    for hop_num in sorted(chunks_by_hop.keys()):
        hop_label = "Initial (Hop 0)" if hop_num == 0 else f"Hop {hop_num}"
        chunks = chunks_by_hop[hop_num]
        print(f"\n{hop_label}: {len(chunks)} chunks")
        for chunk in chunks:
            print(f"  - {chunk.header} (score: {chunk.relevance_score:.3f})")
    print()


def _print_chunks(chunks, chunk_hop_map, hop_evaluations) -> None:
    """Print all chunks with details.

    Args:
        chunks: List of document chunks
        chunk_hop_map: Chunk ID to hop number mapping
        hop_evaluations: Optional list of hop evaluations
    """
    print("All Chunks:")
    for i, chunk in enumerate(chunks, 1):
        hop_num = chunk_hop_map.get(chunk.chunk_id, 0) if hop_evaluations else 0
        hop_label = f" [Hop {hop_num}]" if hop_evaluations else ""
        print(f"\n{i}. {chunk.header}{hop_label} (relevance: {chunk.relevance_score:.2f})")
        print(f"   Text: {chunk.text[:200]}...")


def _print_llm_results(llm_response, llm_time) -> None:
    """Print LLM generation results.

    Args:
        llm_response: LLM response
        llm_time: Time taken for LLM generation
    """
    print(f"Generated response in {llm_time:.2f}s")
    print(f"Confidence: {llm_response.confidence_score:.2f}")
    print(f"Tokens: {llm_response.token_count}")
    print(f"Provider: {llm_response.provider}")
    print()

    print("Answer:")
    print("-" * 60)
    try:
        parsed_json = json.loads(llm_response.answer_text)
        print(json.dumps(parsed_json, indent=2))
    except (json.JSONDecodeError, TypeError):
        # Not JSON or can't parse, print as-is
        print(llm_response.answer_text)


def _print_validation_results(validation_result) -> None:
    """Print validation results.

    Args:
        validation_result: Validation result
    """
    print(f"Valid: {validation_result.is_valid}")
    print(f"LLM Confidence: {validation_result.llm_confidence:.2f}")
    print(f"RAG Score: {validation_result.rag_score:.2f}")
    print(f"Reason: {validation_result.reason}")


def test_query(
    query: str,
    model: str = None,  # type: ignore[assignment]
    max_chunks: int = RAG_MAX_CHUNKS,
    rag_only: bool = False,
    max_hops: int = None,  # type: ignore[assignment]
) -> None:
    """Test RAG + LLM pipeline locally.

    Args:
        query: User question to test
        model: LLM model to use (claude-4.5-sonnet, gemini-2.5-pro, gpt-4o, etc.)
        max_chunks: Maximum chunks to retrieve
        rag_only: If True, stop after RAG retrieval (no LLM call)
        max_hops: Override RAG_MAX_HOPS constant (None = use constant)
    """
    # Override RAG_MAX_HOPS if specified
    current_max_hops = max_hops if max_hops is not None else RAG_MAX_HOPS
    if max_hops is not None:
        constants.RAG_MAX_HOPS = max_hops
        print(f"Overriding RAG_MAX_HOPS to {max_hops}")

    config = get_config()

    # Print header
    print(f"\nQuery: {query}")
    if not rag_only:
        print(f"Model: {model or config.default_llm_provider}")
    else:
        print("Mode: RAG-only (no LLM generation)")
    print(f"{'=' * 60}\n")
    print(
        f"Multi-hop: {'enabled' if current_max_hops > 0 else 'disabled'} "
        f"(max_hops={current_max_hops})"
    )

    # Initialize services
    services = _initialize_services(model, rag_only)

    # Step 1: RAG Retrieval
    print("Step 1: RAG Retrieval")
    print("-" * 60)

    start_time = datetime.now(UTC)

    try:
        rag_context, hop_evaluations, chunk_hop_map, rag_time, cost_breakdown = (
            _perform_rag_retrieval(services, query, max_chunks, current_max_hops)
        )

        # Calculate initial retrieval time (total minus hop times)
        hop_total_time = (
            sum(hop.retrieval_time_s + hop.evaluation_time_s for hop in hop_evaluations)
            if hop_evaluations
            else 0.0
        )
        initial_retrieval_time = rag_time - hop_total_time

        _print_rag_results(rag_context, hop_evaluations, chunk_hop_map, rag_time, current_max_hops)

    except Exception as e:
        logger.error(f"RAG retrieval failed: {e}", exc_info=True)
        print(f"❌ RAG retrieval failed: {e}")
        sys.exit(1)

    # If rag_only mode, stop here with cost breakdown
    if rag_only:
        summary = format_statistics_summary(
            total_time=rag_time,
            initial_retrieval_time=initial_retrieval_time,
            hop_evaluations=hop_evaluations,
            llm_time=None,
            query=query,
            initial_embedding_cost=cost_breakdown.initial_embedding_cost,
            hop_embedding_cost=cost_breakdown.hop_embedding_cost,
            hop_evaluation_cost=cost_breakdown.hop_evaluation_cost,
        )
        print(f"\n{summary}")
        return

    # Step 2: LLM Generation
    print(f"\n{'=' * 60}")
    print("Step 2: LLM Generation")
    print("-" * 60)

    try:
        llm_response, llm_time, llm_cost = asyncio.run(
            _perform_llm_generation(services, query, rag_context)
        )
        _print_llm_results(llm_response, llm_time)

    except Exception as e:
        logger.error(f"LLM generation failed: {e}", exc_info=True)
        print(f"❌ LLM generation failed: {e}")
        sys.exit(1)

    # Step 3: Validation
    print(f"\n{'=' * 60}")
    print("Step 3: Validation")
    print("-" * 60)

    try:
        validation_result = services.validator.validate(llm_response, rag_context)
        _print_validation_results(validation_result)

    except Exception as e:
        logger.error(f"Validation failed: {e}", exc_info=True)
        print(f"❌ Validation failed: {e}")
        sys.exit(1)

    # Summary
    total_time = (datetime.now(UTC) - start_time).total_seconds()
    summary = format_statistics_summary(
        total_time=total_time,
        initial_retrieval_time=initial_retrieval_time,
        hop_evaluations=hop_evaluations,
        llm_time=llm_time,
        query=query,
        initial_embedding_cost=cost_breakdown.initial_embedding_cost,
        hop_embedding_cost=cost_breakdown.hop_embedding_cost,
        hop_evaluation_cost=cost_breakdown.hop_evaluation_cost,
        llm_cost=llm_cost,
        llm_prompt_tokens=llm_response.prompt_tokens,
        llm_completion_tokens=llm_response.completion_tokens,
        llm_model=llm_response.model_version,
    )
    print(f"\n{summary}")


def main():
    """Main entry point for test_query CLI."""
    parser = argparse.ArgumentParser(description="Test RAG + LLM pipeline locally without Discord")
    parser.add_argument("query", help="Question to ask")
    parser.add_argument(
        "--model", "-m", choices=ALL_LLM_PROVIDERS, help="LLM model to use (default: from config)"
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=RAG_MAX_CHUNKS,
        help=f"Maximum chunks to retrieve (default: {RAG_MAX_CHUNKS})",
    )
    parser.add_argument(
        "--rag-only", action="store_true", help="Stop after RAG retrieval, do not call LLM"
    )
    parser.add_argument(
        "--max-hops",
        type=int,
        default=None,
        help=f"Override RAG_MAX_HOPS constant (default: {RAG_MAX_HOPS})",
    )

    args = parser.parse_args()

    try:
        test_query(
            args.query,
            model=args.model,
            max_chunks=args.max_chunks,
            rag_only=args.rag_only,
            max_hops=args.max_hops,
        )
    except Exception as e:
        logger.error(f"Test query failed: {e}", exc_info=True)
        print(f"❌ Test query failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
