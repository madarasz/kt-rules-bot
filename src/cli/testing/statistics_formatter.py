"""Statistics formatting utilities for test results.

Provides a wrapper around src.lib.statistics for CLI commands.
This exists to maintain separation between lib (core utilities) and
cli (command-specific formatting).
"""

from typing import List, Optional

from src.lib.statistics import format_statistics_summary as _lib_format_summary
from src.lib.logging import get_logger

logger = get_logger(__name__)


class StatisticsFormatter:
    """Formats statistics for CLI test output.

    Provides a clean interface for formatting test statistics
    while delegating to the underlying lib.statistics module.
    """

    @staticmethod
    def format_query_summary(
        total_time: float,
        initial_retrieval_time: float,
        hop_evaluations: List,
        llm_time: Optional[float],
        query: str,
        initial_embedding_cost: float,
        hop_embedding_cost: float,
        hop_evaluation_cost: float,
        llm_cost: Optional[float] = None,
        llm_prompt_tokens: Optional[int] = None,
        llm_completion_tokens: Optional[int] = None,
        llm_model: Optional[str] = None,
    ) -> str:
        """Format query execution summary.

        Args:
            total_time: Total execution time in seconds
            initial_retrieval_time: Initial RAG retrieval time in seconds
            hop_evaluations: List of hop evaluation results
            llm_time: LLM generation time in seconds (None for RAG-only)
            query: Query text
            initial_embedding_cost: Cost of initial embedding
            hop_embedding_cost: Cost of hop embeddings
            hop_evaluation_cost: Cost of hop evaluations
            llm_cost: Optional LLM cost
            llm_prompt_tokens: Optional LLM prompt tokens
            llm_completion_tokens: Optional LLM completion tokens
            llm_model: Optional LLM model identifier

        Returns:
            Formatted summary string
        """
        # Delegate to lib.statistics
        return _lib_format_summary(
            total_time=total_time,
            initial_retrieval_time=initial_retrieval_time,
            hop_evaluations=hop_evaluations,
            llm_time=llm_time,
            query=query,
            initial_embedding_cost=initial_embedding_cost,
            hop_embedding_cost=hop_embedding_cost,
            hop_evaluation_cost=hop_evaluation_cost,
            llm_cost=llm_cost,
            llm_prompt_tokens=llm_prompt_tokens,
            llm_completion_tokens=llm_completion_tokens,
            llm_model=llm_model,
        )

    @staticmethod
    def format_time_breakdown(
        total_time: float,
        rag_time: float,
        llm_time: Optional[float] = None,
    ) -> str:
        """Format time breakdown.

        Args:
            total_time: Total execution time in seconds
            rag_time: RAG retrieval time in seconds
            llm_time: Optional LLM generation time in seconds

        Returns:
            Formatted time breakdown string
        """
        lines = []
        lines.append("Time Breakdown:")
        lines.append(f"  RAG retrieval: {rag_time:.2f}s")

        if llm_time is not None:
            lines.append(f"  LLM generation: {llm_time:.2f}s")

        lines.append(f"  Total: {total_time:.2f}s")

        return "\n".join(lines)

    @staticmethod
    def format_hop_summary(hop_evaluations: List) -> str:
        """Format multi-hop retrieval summary.

        Args:
            hop_evaluations: List of hop evaluation results

        Returns:
            Formatted hop summary string
        """
        if not hop_evaluations:
            return "Multi-hop: Not used"

        lines = []
        lines.append(f"Multi-hop Summary ({len(hop_evaluations)} hops):")

        for i, hop_eval in enumerate(hop_evaluations, 1):
            can_answer = "✅ Yes" if hop_eval.can_answer else "❌ No"
            lines.append(f"  Hop {i}:")
            lines.append(f"    Can answer: {can_answer}")
            lines.append(f"    Reasoning: {hop_eval.reasoning}")
            if hop_eval.missing_query:
                lines.append(f"    Missing query: \"{hop_eval.missing_query}\"")
            lines.append(f"    Retrieval time: {hop_eval.retrieval_time_s:.2f}s")
            lines.append(f"    Evaluation time: {hop_eval.evaluation_time_s:.2f}s")

        return "\n".join(lines)

    @staticmethod
    def format_chunk_summary(
        chunks: List,
        chunk_hop_map: dict = None,
    ) -> str:
        """Format chunk retrieval summary.

        Args:
            chunks: List of retrieved chunks
            chunk_hop_map: Optional mapping of chunk_id to hop number

        Returns:
            Formatted chunk summary string
        """
        if not chunks:
            return "No chunks retrieved"

        lines = []
        lines.append(f"Retrieved Chunks ({len(chunks)}):")

        for i, chunk in enumerate(chunks, 1):
            hop_num = chunk_hop_map.get(chunk.chunk_id, 0) if chunk_hop_map else 0
            hop_label = f" [Hop {hop_num}]" if chunk_hop_map else ""

            lines.append(f"  {i}. {chunk.header}{hop_label}")
            lines.append(f"     Relevance: {chunk.relevance_score:.3f}")
            lines.append(f"     Text: {chunk.text[:100]}...")

        return "\n".join(lines)
