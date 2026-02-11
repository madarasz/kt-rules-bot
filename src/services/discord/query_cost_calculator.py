"""Cost calculation service for query processing."""

from src.lib.constants import EMBEDDING_MODEL
from src.lib.tokens import estimate_cost, estimate_embedding_cost
from src.services.llm.base import LLMResponse


class QueryCostCalculator:
    """Calculates costs for query processing (embeddings + LLM calls)."""

    @staticmethod
    def calculate_total_cost(
        query: str,
        llm_response: LLMResponse,
        hop_evaluations: list | None = None,
    ) -> dict[str, float]:
        """Calculate total cost breakdown for a query.

        Args:
            query: User's query text
            llm_response: LLM response with token counts
            hop_evaluations: Optional list of hop evaluations

        Returns:
            Dict with cost breakdown: {
                'initial_embedding_cost': float,
                'hop_embedding_cost': float,
                'hop_evaluation_cost': float,
                'main_llm_cost': float,
                'total_cost': float
            }
        """
        # 1. Initial retrieval embedding
        initial_embedding_cost = estimate_embedding_cost(query, EMBEDDING_MODEL)

        # 2. Hop query embeddings (if multi-hop was used)
        hop_embedding_cost = 0.0
        if hop_evaluations:
            for hop_eval in hop_evaluations:
                if hop_eval.missing_query:
                    hop_embedding_cost += estimate_embedding_cost(
                        hop_eval.missing_query, EMBEDDING_MODEL
                    )

        # 3. Hop evaluation LLM costs (already tracked)
        hop_evaluation_cost = sum(hop_eval.cost_usd for hop_eval in hop_evaluations or [])

        # 4. Main LLM generation cost
        main_llm_cost = estimate_cost(
            llm_response.prompt_tokens,
            llm_response.completion_tokens,
            llm_response.model_version,
        )

        # Total cost
        total_cost = (
            initial_embedding_cost + hop_embedding_cost + hop_evaluation_cost + main_llm_cost
        )

        return {
            "initial_embedding_cost": initial_embedding_cost,
            "hop_embedding_cost": hop_embedding_cost,
            "hop_evaluation_cost": hop_evaluation_cost,
            "main_llm_cost": main_llm_cost,
            "total_cost": total_cost,
        }

    @staticmethod
    def calculate_latency_breakdown(
        retrieval_latency_ms: int,
        hop_evaluations: list | None,
        main_llm_latency_ms: int,
        total_latency_ms: int | None = None,
    ) -> dict[str, int]:
        """Calculate latency breakdown for a query.

        Args:
            retrieval_latency_ms: Total RAG time (includes initial + hop retrieval + hop evaluation)
            hop_evaluations: Optional list of hop evaluations
            main_llm_latency_ms: Main LLM generation latency
            total_latency_ms: Actual measured total latency (optional, calculated if not provided)

        Returns:
            Dict with latency breakdown: {
                'retrieval_latency_ms': int (pure retrieval without hop LLM calls),
                'hop_evaluation_latency_ms': int (hop LLM evaluation time),
                'main_llm_latency_ms': int (main LLM generation time),
                'total_latency_ms': int (actual measured total latency),
            }
        """
        # Calculate hop evaluation latency (sum of evaluation time for all hops)
        hop_eval_latency_ms = int(
            sum(hop_eval.evaluation_time_s for hop_eval in hop_evaluations or []) * 1000
        )

        # Subtract hop evaluation time from total to get pure retrieval time
        # This prevents double-counting since the input retrieval_latency_ms includes hop evaluation
        pure_retrieval_latency_ms = retrieval_latency_ms - hop_eval_latency_ms

        # Use actual measured total if provided, otherwise calculate from components
        actual_total_ms = total_latency_ms if total_latency_ms is not None else (
            pure_retrieval_latency_ms + hop_eval_latency_ms + main_llm_latency_ms
        )

        return {
            "retrieval_latency_ms": pure_retrieval_latency_ms,
            "hop_evaluation_latency_ms": hop_eval_latency_ms,
            "main_llm_latency_ms": main_llm_latency_ms,
            "total_latency_ms": actual_total_ms,
        }
