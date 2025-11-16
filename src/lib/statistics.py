"""Unified statistics formatting utilities for CLI and test reports.

Provides consistent time/cost breakdown formatting across test_query, rag_test, etc.
"""

from typing import List, Optional
from src.lib.constants import RAG_HOP_EVALUATION_MODEL, EMBEDDING_MODEL
from src.lib.tokens import estimate_embedding_cost


def format_statistics_summary(
    total_time: float,
    initial_retrieval_time: float,
    hop_evaluations: Optional[List] = None,
    llm_time: Optional[float] = None,
    query: str = "",
    initial_embedding_cost: float = 0.0,
    hop_embedding_cost: float = 0.0,
    hop_evaluation_cost: float = 0.0,
    llm_cost: float = 0.0,
    llm_prompt_tokens: int = 0,
    llm_completion_tokens: int = 0,
    llm_model: str = "",
) -> str:
    """Format statistics summary with time and cost breakdowns.

    Args:
        total_time: Total execution time in seconds
        initial_retrieval_time: Initial retrieval time in seconds
        hop_evaluations: List of HopEvaluation objects (optional)
        llm_time: LLM generation time in seconds (optional, for full pipeline)
        query: Query string (for embedding cost calculation if not provided)
        initial_embedding_cost: Cost of initial embedding (default: 0, will calculate from query)
        hop_embedding_cost: Total cost of hop embeddings (default: 0)
        hop_evaluation_cost: Total cost of hop LLM evaluations (default: 0)
        llm_cost: Cost of main LLM generation (default: 0)
        llm_prompt_tokens: Prompt tokens for main LLM (default: 0)
        llm_completion_tokens: Completion tokens for main LLM (default: 0)
        llm_model: Model name for main LLM (default: "")

    Returns:
        Formatted statistics string
    """
    lines = []
    lines.append("=" * 60)
    lines.append("SUMMARY" if llm_time is not None else "SUMMARY (RAG-only mode)")
    lines.append("=" * 60)
    lines.append("")

    # TIME BREAKDOWN
    lines.append(f"Total time: {total_time:.2f}s")

    # RAG retrieval time
    rag_time = total_time - (llm_time or 0.0)
    lines.append(f"  RAG retrieval: {rag_time:.2f}s")
    lines.append(f"    Initial retrieval: {initial_retrieval_time:.2f}s")

    # Hop breakdown if multi-hop was used
    if hop_evaluations:
        for i, hop_eval in enumerate(hop_evaluations, 1):
            hop_time = hop_eval.retrieval_time_s + hop_eval.evaluation_time_s
            lines.append(
                f"    Hop {i}: {hop_time:.2f}s "
                f"(retrieval: {hop_eval.retrieval_time_s:.2f}s, "
                f"evaluation: {hop_eval.evaluation_time_s:.2f}s)"
            )

    # LLM generation time (if full pipeline)
    if llm_time is not None:
        lines.append(f"  LLM generation: {llm_time:.2f}s")

    lines.append("")

    # COST BREAKDOWN
    # Calculate initial embedding cost if not provided
    if initial_embedding_cost == 0.0 and query:
        initial_embedding_cost = estimate_embedding_cost(query, EMBEDDING_MODEL)

    # Group embedding costs
    total_embedding_cost = initial_embedding_cost + hop_embedding_cost

    # Total RAG cost
    total_rag_cost = total_embedding_cost + hop_evaluation_cost

    # Total cost
    total_cost = total_rag_cost + llm_cost

    lines.append(f"Total cost: ${total_cost:.6f}")
    lines.append(f"  RAG costs: ${total_rag_cost:.6f}")
    lines.append(f"    Embeddings: ${total_embedding_cost:.6f}")
    lines.append(f"      Initial query: ${initial_embedding_cost:.6f}")

    if hop_evaluations and hop_embedding_cost > 0:
        lines.append(f"      Hop queries: ${hop_embedding_cost:.6f}")
        for i, hop_eval in enumerate(hop_evaluations, 1):
            if hop_eval.missing_query:
                hop_emb_cost = estimate_embedding_cost(hop_eval.missing_query, EMBEDDING_MODEL)
                lines.append(f"        Hop {i}: ${hop_emb_cost:.6f}")

    if hop_evaluations and hop_evaluation_cost > 0:
        lines.append(f"    Hop evaluations: ${hop_evaluation_cost:.6f}")
        for i, hop_eval in enumerate(hop_evaluations, 1):
            lines.append(f"      Hop {i} LLM ({RAG_HOP_EVALUATION_MODEL}): ${hop_eval.cost_usd:.6f}")

    # LLM generation cost (if full pipeline)
    if llm_cost > 0:
        lines.append(f"  LLM generation: ${llm_cost:.6f}")
        if llm_model:
            lines.append(f"    Model: {llm_model}")
        if llm_prompt_tokens > 0:
            lines.append(f"    Prompt tokens: {llm_prompt_tokens:,}")
            lines.append(f"    Completion tokens: {llm_completion_tokens:,}")

    lines.append("=" * 60)
    lines.append("")

    return "\n".join(lines)
