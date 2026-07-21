"""Retrieval evaluation metrics (RAGAS-style, our own implementation).

Context precision and priority-weighted context recall, computed by substring
matching rather than by an LLM judge. Deterministic, free, and fast.
"""

from dataclasses import dataclass

from src.lib.text_utils import ground_truth_matches_text


@dataclass
class RetrievalMetrics:
    """Precision/recall of retrieved contexts against ground truth."""

    context_precision: float | None = None
    context_recall: float | None = None


def evaluate_retrieval(retrieved_contexts: list[str], ground_truth_contexts) -> RetrievalMetrics:
    """Evaluate retrieval quality with priority-weighted recall.

    Each ground truth context is a substring that should appear in at least one
    retrieved context. Recall uses priority weights (critical=10, important=5,
    supporting=3) to emphasize finding the most important rules.

    Args:
        retrieved_contexts: List of retrieved document chunks (full text)
        ground_truth_contexts: List of GroundTruthContext objects with text and priority weights

    Returns:
        RetrievalMetrics with context_precision and context_recall
    """
    # Import here to avoid circular dependency
    from tests.quality.test_case_models import GroundTruthContext

    # Handle both old dict format (RAG tests) and new GroundTruthContext format (quality tests)
    if ground_truth_contexts and isinstance(ground_truth_contexts[0], dict):
        # Old format: [{"key": "text"}] - convert to GroundTruthContext for uniform handling
        gt_contexts = [
            GroundTruthContext(
                key=f"ctx_{i}",
                text=next(iter(gt_dict.values())),
                priority="critical",  # Default to critical for backward compatibility
            )
            for i, gt_dict in enumerate(ground_truth_contexts)
        ]
    else:
        # New format: already GroundTruthContext objects
        gt_contexts = ground_truth_contexts

    if not gt_contexts:
        return RetrievalMetrics(context_precision=0.0, context_recall=0.0)

    # Calculate priority-weighted context recall
    # Recall = (sum of weights for found ground truths) / (total weight of all ground truths)
    total_weight = sum(gt.weight for gt in gt_contexts)
    found_weight = 0.0

    for gt_context in gt_contexts:
        # Check if this ground truth substring appears in any retrieved context
        for retrieved_context in retrieved_contexts:
            if ground_truth_matches_text(gt_context.text, retrieved_context):
                found_weight += gt_context.weight
                break  # Found this ground truth, move to next one

    context_recall_value = found_weight / total_weight if total_weight > 0 else 0.0

    # Calculate substring-based context precision (no priority weighting)
    # Precision = (number of retrieved contexts containing ground truth) / (total retrieved contexts)
    relevant_retrieved_count = 0
    for retrieved_context in retrieved_contexts:
        # Check if this retrieved context contains any ground truth substring
        for gt_context in gt_contexts:
            if ground_truth_matches_text(gt_context.text, retrieved_context):
                relevant_retrieved_count += 1
                break  # This retrieved context is relevant, move to next one

    context_precision_value = (
        relevant_retrieved_count / len(retrieved_contexts) if retrieved_contexts else 0.0
    )

    return RetrievalMetrics(
        context_precision=context_precision_value, context_recall=context_recall_value
    )
