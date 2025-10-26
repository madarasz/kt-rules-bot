"""Adapter module for Ragas RAG evaluation framework.

This module provides wrapper functions to integrate Ragas metrics into our testing pipeline.
It converts our data formats to Ragas format and provides helper functions for metric calculation.
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from ragas import evaluate
from ragas.metrics import (
    context_precision,
    context_recall,
    faithfulness,
    answer_relevancy,
)
from datasets import Dataset

@dataclass
class RagasRetrievalMetrics:
    """Ragas metrics for retrieval evaluation."""

    context_precision: Optional[float] = None
    context_recall: Optional[float] = None


@dataclass
class RagasGenerationMetrics:
    """Ragas metrics for generation evaluation."""

    faithfulness: Optional[float] = None
    answer_relevancy: Optional[float] = None

def evaluate_retrieval(
    retrieved_contexts: List[str],
    ground_truth_contexts: List[str]
) -> RagasRetrievalMetrics:
    """Evaluate retrieval quality using Ragas metrics.

    Note: This implementation uses substring matching for ground_truth_contexts
    instead of Ragas's full-text matching. We check if each ground truth context
    substring appears in any of the retrieved contexts.

    Args:
        query: The user query
        retrieved_contexts: List of retrieved document chunks (full text)
        ground_truth_contexts: List of expected context substrings
        judge_model: Optional LLM model for Ragas evaluation (unused in substring mode)

    Returns:
        RagasRetrievalMetrics with context_precision and context_recall
    """

    # Calculate custom substring-based context recall
    # Recall = (number of ground truth substrings found) / (total ground truth substrings)
    # Note: Strip asterisks (*) from both ground truth and retrieved contexts for matching
    found_count = 0
    for ground_truth_substring in ground_truth_contexts:
        # Normalize ground truth: lowercase and remove asterisks
        gt_normalized = ground_truth_substring.strip().lower().replace("*", "")

        # Check if this ground truth substring appears in any retrieved context
        for retrieved_context in retrieved_contexts:
            # Normalize retrieved context: lowercase and remove asterisks
            retrieved_normalized = retrieved_context.strip().lower().replace("*", "")

            if gt_normalized in retrieved_normalized:
                found_count += 1
                break  # Found this ground truth, move to next one

    context_recall_value = found_count / len(ground_truth_contexts) if ground_truth_contexts else 0.0

    # Calculate custom substring-based context precision
    # Precision = (number of retrieved contexts containing ground truth) / (total retrieved contexts)
    relevant_retrieved_count = 0
    for retrieved_context in retrieved_contexts:
        # Normalize retrieved context: lowercase and remove asterisks
        retrieved_normalized = retrieved_context.strip().lower().replace("*", "")

        # Check if this retrieved context contains any ground truth substring
        for ground_truth_substring in ground_truth_contexts:
            # Normalize ground truth: lowercase and remove asterisks
            gt_normalized = ground_truth_substring.strip().lower().replace("*", "")

            if gt_normalized in retrieved_normalized:
                relevant_retrieved_count += 1
                break  # This retrieved context is relevant, move to next one

    context_precision_value = (
        relevant_retrieved_count / len(retrieved_contexts)
        if retrieved_contexts else 0.0
    )

    return RagasRetrievalMetrics(
        context_precision=context_precision_value,
        context_recall=context_recall_value,
    )


def evaluate_generation(
    query: str,
    response: str,
    retrieved_contexts: List[str],
    ground_truth_answer: Optional[str] = None,
    judge_model: Optional[str] = None,
) -> RagasGenerationMetrics:
    """Evaluate generation quality using Ragas metrics.

    Args:
        query: The user query
        response: The generated response from the LLM
        retrieved_contexts: List of retrieved document chunks used for generation
        ground_truth_answer: Optional reference answer for comparison
        judge_model: Optional LLM model for Ragas evaluation (e.g., "gpt-4o")

    Returns:
        RagasGenerationMetrics with faithfulness and answer_relevancy

    Raises:
        ValueError: If Ragas evaluation fails
    """

    # Prepare dataset for Ragas
    data = {
        "question": [query],
        "answer": [response],
        "contexts": [retrieved_contexts],
    }

    if ground_truth_answer:
        data["ground_truth"] = [ground_truth_answer]

    dataset = Dataset.from_dict(data)

    # Select metrics based on available data
    metrics = [faithfulness, answer_relevancy]

    # Configure LLM for Ragas (if judge_model provided)
    # Note: Ragas uses OpenAI by default if no LLM is configured
    # Future enhancement: Configure custom LLM based on judge_model parameter

    try:
        # Run Ragas evaluation
        result = evaluate(dataset, metrics=metrics)

        return RagasGenerationMetrics(
            faithfulness=result.get("faithfulness"),
            answer_relevancy=result.get("answer_relevancy"),
        )
    except Exception as e:
        raise ValueError(f"Ragas evaluation failed: {str(e)}") from e


def format_ragas_metrics_for_display(
    retrieval_metrics: Optional[RagasRetrievalMetrics] = None,
    generation_metrics: Optional[RagasGenerationMetrics] = None,
) -> Dict[str, Any]:
    """Format Ragas metrics for display in reports.

    Args:
        retrieval_metrics: Optional retrieval metrics
        generation_metrics: Optional generation metrics

    Returns:
        Dictionary with formatted metric names and values
    """
    formatted = {}

    if retrieval_metrics:
        if retrieval_metrics.context_precision is not None:
            formatted["Context Precision"] = f"{retrieval_metrics.context_precision:.3f}"
        if retrieval_metrics.context_recall is not None:
            formatted["Context Recall"] = f"{retrieval_metrics.context_recall:.3f}"

    if generation_metrics:
        if generation_metrics.faithfulness is not None:
            formatted["Faithfulness"] = f"{generation_metrics.faithfulness:.3f}"
        if generation_metrics.answer_relevancy is not None:
            formatted["Answer Relevancy"] = f"{generation_metrics.answer_relevancy:.3f}"

    return formatted


def get_ragas_metric_descriptions() -> Dict[str, str]:
    """Get descriptions of Ragas metrics for documentation.

    Returns:
        Dictionary mapping metric names to their descriptions
    """
    return {
        "Context Precision": (
            "Measures the proportion of retrieved contexts that contain ground truth information. "
            "Higher is better (range: 0.0-1.0)."
        ),
        "Context Recall": (
            "Measures the proportion of ground truth information found in retrieved contexts. "
            "Higher is better (range: 0.0-1.0)."
        ),
        "Faithfulness": (
            "Measures how factually accurate the generated answer is compared to the retrieved contexts. "
            "Higher is better (range: 0.0-1.0)."
        ),
        "Answer Relevancy": (
            "Measures how relevant the generated answer is to the user query. "
            "Higher is better (range: 0.0-1.0)."
        ),
    }
