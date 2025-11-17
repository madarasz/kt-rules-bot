"""Unified statistics formatting utilities for CLI and test reports.

Provides consistent time/cost breakdown formatting across test_query, rag_test, etc.
"""

from src.lib.constants import EMBEDDING_MODEL, RAG_HOP_EVALUATION_MODEL
from src.lib.tokens import estimate_embedding_cost


class TimeFormatter:
    """Formats time breakdown sections."""

    @staticmethod
    def format(total_time: float, initial_time: float, hop_evals: list | None, llm_time: float | None) -> list[str]:
        """Format time breakdown section."""
        rag_time = total_time - (llm_time or 0.0)
        lines = [
            f"Total time: {total_time:.2f}s",
            f"  RAG retrieval: {rag_time:.2f}s",
            f"    Initial retrieval: {initial_time:.2f}s",
        ]

        # Hop breakdown
        if hop_evals:
            for i, hop in enumerate(hop_evals, 1):
                hop_time = hop.retrieval_time_s + hop.evaluation_time_s
                lines.append(
                    f"    Hop {i}: {hop_time:.2f}s "
                    f"(retrieval: {hop.retrieval_time_s:.2f}s, evaluation: {hop.evaluation_time_s:.2f}s)"
                )

        # LLM time
        if llm_time is not None:
            lines.append(f"  LLM generation: {llm_time:.2f}s")

        return lines


class CostFormatter:
    """Formats cost breakdown sections."""

    @staticmethod
    def format(
        query: str,
        init_emb: float,
        hop_emb: float,
        hop_eval: float,
        llm_cost: float,
        llm_model: str,
        prompt_tokens: int,
        completion_tokens: int,
        hop_evals: list | None,
    ) -> list[str]:
        """Format cost breakdown section."""
        # Calculate initial embedding cost if needed
        if init_emb == 0.0 and query:
            init_emb = estimate_embedding_cost(query, EMBEDDING_MODEL)

        total_emb = init_emb + hop_emb
        total_rag = total_emb + hop_eval
        total = total_rag + llm_cost

        lines = [
            f"Total cost: ${total:.6f}",
            f"  RAG costs: ${total_rag:.6f}",
            f"    Embeddings: ${total_emb:.6f}",
            f"      Initial query: ${init_emb:.6f}",
        ]

        # Hop query embeddings
        if hop_evals and hop_emb > 0:
            lines.append(f"      Hop queries: ${hop_emb:.6f}")
            for i, hop in enumerate(hop_evals, 1):
                if hop.missing_query:
                    cost = estimate_embedding_cost(hop.missing_query, EMBEDDING_MODEL)
                    lines.append(f"        Hop {i}: ${cost:.6f}")

        # Hop evaluation costs
        if hop_evals and hop_eval > 0:
            lines.append(f"    Hop evaluations: ${hop_eval:.6f}")
            for i, hop in enumerate(hop_evals, 1):
                lines.append(f"      Hop {i} LLM ({RAG_HOP_EVALUATION_MODEL}): ${hop.cost_usd:.6f}")

        # LLM generation cost
        if llm_cost > 0:
            lines.append(f"  LLM generation: ${llm_cost:.6f}")
            if llm_model:
                lines.append(f"    Model: {llm_model}")
            if prompt_tokens > 0:
                lines.append(f"    Prompt tokens: {prompt_tokens:,}")
                lines.append(f"    Completion tokens: {completion_tokens:,}")

        return lines


def format_statistics_summary(
    total_time: float,
    initial_retrieval_time: float,
    hop_evaluations: list | None = None,
    llm_time: float | None = None,
    query: str = "",
    initial_embedding_cost: float = 0.0,
    hop_embedding_cost: float = 0.0,
    hop_evaluation_cost: float = 0.0,
    llm_cost: float = 0.0,
    llm_prompt_tokens: int = 0,
    llm_completion_tokens: int = 0,
    llm_model: str = "",
) -> str:
    """Format statistics summary with time and cost breakdowns."""
    lines = [
        "=" * 60,
        "SUMMARY" if llm_time is not None else "SUMMARY (RAG-only mode)",
        "=" * 60,
        "",
    ]

    # Time breakdown
    lines.extend(TimeFormatter.format(total_time, initial_retrieval_time, hop_evaluations, llm_time))
    lines.append("")

    # Cost breakdown
    lines.extend(CostFormatter.format(
        query, initial_embedding_cost, hop_embedding_cost, hop_evaluation_cost,
        llm_cost, llm_model, llm_prompt_tokens, llm_completion_tokens, hop_evaluations
    ))

    lines.extend(["=" * 60, ""])
    return "\n".join(lines)
