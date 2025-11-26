"""RAG test evaluator using Ragas framework.

This evaluator integrates Ragas metrics alongside custom IR metrics.
It uses substring matching for ground_truth_contexts as specified in the refactor plan.
"""

from src.lib.constants import QUALITY_TEST_JUDGE_MODEL
from src.lib.ragas_adapter import RagasRetrievalMetrics, evaluate_retrieval
from src.models.rag_context import DocumentChunk
from tests.rag.test_case_models import RAGTestCase, RAGTestResult


class RagasRAGEvaluator:
    """Evaluates RAG retrieval using Ragas framework with substring matching.

    This evaluator extends the custom IR metrics with Ragas-style evaluation,
    using substring matching for ground_truth_contexts instead of full-text matching.
    """

    def __init__(self, judge_model: str | None = None):
        """Initialize the Ragas evaluator.

        Args:
            judge_model: Optional LLM model for Ragas evaluation (default: QUALITY_TEST_JUDGE_MODEL)
                        Note: Not used for substring matching, but available for future extensions
        """
        self.judge_model = judge_model or QUALITY_TEST_JUDGE_MODEL

    def evaluate(
        self, test_case: RAGTestCase, retrieved_chunks: list[DocumentChunk]
    ) -> RagasRetrievalMetrics | None:
        """Evaluate retrieval using Ragas metrics.

        Args:
            test_case: Test case definition with ground_truth_contexts
            retrieved_chunks: Chunks retrieved by RAG system (ordered by relevance)

        Returns:
            RagasRetrievalMetrics
        """

        # Get ground truth contexts
        ground_truth_contexts = test_case.ground_truth_contexts

        # Extract full text from retrieved chunks
        retrieved_texts = [chunk.text for chunk in retrieved_chunks]

        # Evaluate using Ragas adapter (substring matching)
        ragas_metrics = evaluate_retrieval(
            retrieved_contexts=retrieved_texts, ground_truth_contexts=ground_truth_contexts
        )

        return ragas_metrics


def add_ragas_metrics_to_result(
    base_result: RAGTestResult, ragas_metrics: RagasRetrievalMetrics | None
) -> RAGTestResult:
    """Add Ragas metrics to an existing RAGTestResult.

    This is a helper function to augment RAGTestResult with Ragas metrics
    without modifying the existing evaluation flow.

    Args:
        base_result: The base RAGTestResult from custom evaluation
        ragas_metrics: Optional Ragas metrics to add

    Returns:
        New RAGTestResult with Ragas metrics added
    """
    # Create a dict of all base result fields
    result_dict = {
        "test_id": base_result.test_id,
        "query": base_result.query,
        "ground_truth_contexts": base_result.ground_truth_contexts,
        "ground_truth_values": base_result.ground_truth_values,
        "retrieved_chunks": base_result.retrieved_chunks,
        "retrieved_chunk_texts": base_result.retrieved_chunk_texts,
        "retrieved_relevance_scores": base_result.retrieved_relevance_scores,
        "retrieved_chunk_metadata": base_result.retrieved_chunk_metadata,
        "map_score": base_result.map_score,
        "recall_at_5": base_result.recall_at_5,
        "recall_at_10": base_result.recall_at_10,
        "recall_at_all": base_result.recall_at_all,
        "precision_at_3": base_result.precision_at_3,
        "precision_at_5": base_result.precision_at_5,
        "mrr": base_result.mrr,
        "found_chunks": base_result.found_chunks,
        "missing_chunks": base_result.missing_chunks,
        "ranks_of_required": base_result.ranks_of_required,
        "retrieval_time_seconds": base_result.retrieval_time_seconds,
        "embedding_cost_usd": base_result.embedding_cost_usd,
        "run_number": base_result.run_number,
        # Multi-hop fields
        "hops_used": base_result.hops_used,
        "hop_evaluations": base_result.hop_evaluations,
        "chunk_hop_numbers": base_result.chunk_hop_numbers,
        "filtered_teams_count": base_result.filtered_teams_count,
        # Ground truth rank analysis
        "max_ground_truth_rank": base_result.max_ground_truth_rank,
    }

    # Add Ragas metrics if available
    if ragas_metrics:
        result_dict["ragas_context_precision"] = ragas_metrics.context_precision
        result_dict["ragas_context_recall"] = ragas_metrics.context_recall
    else:
        result_dict["ragas_context_precision"] = None
        result_dict["ragas_context_recall"] = None

    # Return new RAGTestResult with all fields
    return RAGTestResult(**result_dict)
