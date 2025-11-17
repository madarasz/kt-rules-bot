"""Cost calculation utilities for testing.

Extracted from test_query.py to reduce code duplication.
"""

from typing import List, Optional

from src.lib.tokens import estimate_cost, estimate_embedding_cost
from src.lib.logging import get_logger

logger = get_logger(__name__)


class CostCalculator:
    """Calculates costs for RAG and LLM operations.

    Provides centralized cost calculation for testing commands.
    """

    @staticmethod
    def calculate_rag_costs(
        query: str,
        hop_evaluations: List,
        embedding_model: str,
    ) -> dict:
        """Calculate all RAG-related costs.

        Args:
            query: Initial query text
            hop_evaluations: List of hop evaluation results
            embedding_model: Embedding model identifier

        Returns:
            Dictionary with cost breakdown:
            {
                "initial_embedding_cost": float,
                "hop_embedding_cost": float,
                "hop_evaluation_cost": float,
                "total_rag_cost": float,
            }
        """
        # 1. Initial retrieval embedding
        initial_embedding_cost = estimate_embedding_cost(query, embedding_model)

        # 2. Hop query embeddings (if multi-hop was used)
        hop_embedding_cost = 0.0
        if hop_evaluations:
            for hop_eval in hop_evaluations:
                if hop_eval.missing_query:
                    hop_embedding_cost += estimate_embedding_cost(
                        hop_eval.missing_query,
                        embedding_model
                    )

        # 3. Hop evaluation LLM costs (already tracked in hop_eval.cost_usd)
        hop_evaluation_cost = sum(
            hop_eval.cost_usd for hop_eval in hop_evaluations
        ) if hop_evaluations else 0.0

        # Total RAG cost (embedding + hop evaluations)
        total_rag_cost = initial_embedding_cost + hop_embedding_cost + hop_evaluation_cost

        return {
            "initial_embedding_cost": initial_embedding_cost,
            "hop_embedding_cost": hop_embedding_cost,
            "hop_evaluation_cost": hop_evaluation_cost,
            "total_rag_cost": total_rag_cost,
        }

    @staticmethod
    def calculate_llm_cost(
        prompt_tokens: int,
        completion_tokens: int,
        model: str,
    ) -> float:
        """Calculate LLM generation cost.

        Args:
            prompt_tokens: Input tokens
            completion_tokens: Output tokens
            model: Model identifier

        Returns:
            Estimated cost in USD
        """
        return estimate_cost(prompt_tokens, completion_tokens, model)

    @staticmethod
    def calculate_total_cost(
        rag_costs: dict,
        llm_cost: Optional[float] = None,
    ) -> float:
        """Calculate total cost across RAG and LLM.

        Args:
            rag_costs: RAG cost breakdown from calculate_rag_costs()
            llm_cost: Optional LLM cost (if None, RAG-only mode)

        Returns:
            Total cost in USD
        """
        total = rag_costs["total_rag_cost"]

        if llm_cost is not None:
            total += llm_cost

        return total

    @staticmethod
    def format_cost_breakdown(
        rag_costs: dict,
        llm_cost: Optional[float] = None,
        llm_prompt_tokens: Optional[int] = None,
        llm_completion_tokens: Optional[int] = None,
    ) -> str:
        """Format cost breakdown as human-readable string.

        Args:
            rag_costs: RAG cost breakdown
            llm_cost: Optional LLM cost
            llm_prompt_tokens: Optional LLM input tokens
            llm_completion_tokens: Optional LLM output tokens

        Returns:
            Formatted cost breakdown string
        """
        lines = []
        lines.append("Cost Breakdown:")
        lines.append(f"  RAG Costs:")
        lines.append(f"    Initial embedding: ${rag_costs['initial_embedding_cost']:.4f}")
        lines.append(f"    Hop embeddings: ${rag_costs['hop_embedding_cost']:.4f}")
        lines.append(f"    Hop evaluations: ${rag_costs['hop_evaluation_cost']:.4f}")
        lines.append(f"    Total RAG: ${rag_costs['total_rag_cost']:.4f}")

        if llm_cost is not None:
            lines.append(f"  LLM Costs:")
            if llm_prompt_tokens and llm_completion_tokens:
                lines.append(f"    Prompt tokens: {llm_prompt_tokens:,}")
                lines.append(f"    Completion tokens: {llm_completion_tokens:,}")
            lines.append(f"    Total LLM: ${llm_cost:.4f}")

        total = CostCalculator.calculate_total_cost(rag_costs, llm_cost)
        lines.append(f"  Total: ${total:.4f}")

        return "\n".join(lines)
