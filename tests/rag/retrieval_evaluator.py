"""RAG retrieval test evaluator.

Computes RAGAS-style context precision/recall alongside the custom IR metrics,
using substring matching against `ground_truth_contexts`.
"""

from src.lib.constants import QUALITY_TEST_JUDGE_MODEL
from src.lib.retrieval_metrics import RetrievalMetrics, evaluate_retrieval
from src.models.rag_context import DocumentChunk
from tests.rag.test_case_models import RAGTestCase, RAGTestResult


class RetrievalEvaluator:
    """Evaluates RAG retrieval with substring matching against ground truth contexts."""

    def __init__(self, judge_model: str | None = None):
        """Initialize the retrieval evaluator.

        Args:
            judge_model: Optional LLM model name (default: QUALITY_TEST_JUDGE_MODEL)
                        Note: Not used for substring matching, but available for future extensions
        """
        self.judge_model = judge_model or QUALITY_TEST_JUDGE_MODEL

    def evaluate(
        self, test_case: RAGTestCase, retrieved_chunks: list[DocumentChunk]
    ) -> RetrievalMetrics | None:
        """Evaluate retrieval quality.

        Args:
            test_case: Test case definition with ground_truth_contexts
            retrieved_chunks: Chunks retrieved by RAG system (ordered by relevance)

        Returns:
            RetrievalMetrics
        """

        # Get ground truth contexts
        ground_truth_contexts = test_case.ground_truth_contexts

        # Extract full text from retrieved chunks
        retrieved_texts = [chunk.text for chunk in retrieved_chunks]

        return evaluate_retrieval(
            retrieved_contexts=retrieved_texts, ground_truth_contexts=ground_truth_contexts
        )


def add_retrieval_metrics_to_result(
    base_result: RAGTestResult, retrieval_metrics: RetrievalMetrics | None
) -> RAGTestResult:
    """Add retrieval metrics to an existing RAGTestResult.

    This is a helper function to augment RAGTestResult with context precision/recall
    without modifying the existing evaluation flow.

    Args:
        base_result: The base RAGTestResult from custom evaluation
        retrieval_metrics: Optional retrieval metrics to add

    Returns:
        New RAGTestResult with retrieval metrics added
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
        # Error tracking
        "error_type": base_result.error_type,
        "error_message": base_result.error_message,
        "hop_errors": base_result.hop_errors,
        # Multi-hop fields
        "hops_used": base_result.hops_used,
        "hop_evaluations": base_result.hop_evaluations,
        "chunk_hop_numbers": base_result.chunk_hop_numbers,
        "filtered_teams_count": base_result.filtered_teams_count,
        # Ground truth rank analysis
        "max_ground_truth_rank": base_result.max_ground_truth_rank,
    }

    # Add retrieval metrics if available
    if retrieval_metrics:
        result_dict["context_precision"] = retrieval_metrics.context_precision
        result_dict["context_recall"] = retrieval_metrics.context_recall
    else:
        result_dict["context_precision"] = None
        result_dict["context_recall"] = None

    # Return new RAGTestResult with all fields
    return RAGTestResult(**result_dict)
