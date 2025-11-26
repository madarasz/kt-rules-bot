"""Adapter module for Ragas RAG evaluation framework.

This module provides wrapper functions to integrate Ragas metrics into our testing pipeline.
It converts our data formats to Ragas format and provides helper functions for metric calculation.
"""

import os
from dataclasses import dataclass
from typing import Any

from datasets import Dataset
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from ragas import evaluate
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import AnswerRelevancy, Faithfulness

from src.lib.text_utils import ground_truth_matches_text

# Load environment variables from config/.env
load_dotenv("config/.env")


@dataclass
class RagasRetrievalMetrics:
    """Ragas metrics for retrieval evaluation."""

    context_precision: float | None = None
    context_recall: float | None = None


@dataclass
class RagasGenerationMetrics:
    """Ragas metrics for generation evaluation."""

    faithfulness: float | None = None
    answer_relevancy: float | None = None


def evaluate_retrieval(
    retrieved_contexts: list[str], ground_truth_contexts: list[dict[str, str]]
) -> RagasRetrievalMetrics:
    """Evaluate retrieval quality using Ragas metrics.

    Note: This implementation uses substring matching for ground_truth_contexts
    instead of Ragas's full-text matching. We check if each ground truth context
    substring appears in any of the retrieved contexts.

    Args:
        retrieved_contexts: List of retrieved document chunks (full text)
        ground_truth_contexts: List of {key: value} dicts where value is the text for matching

    Returns:
        RagasRetrievalMetrics with context_precision and context_recall
    """

    # Extract values from ground_truth_contexts dicts for matching
    ground_truth_values = [next(iter(gt_dict.values())) for gt_dict in ground_truth_contexts]

    # Calculate custom substring-based context recall
    # Recall = (number of ground truth substrings found) / (total ground truth substrings)
    found_count = 0
    for ground_truth_substring in ground_truth_values:
        # Check if this ground truth substring appears in any retrieved context
        for retrieved_context in retrieved_contexts:
            if ground_truth_matches_text(ground_truth_substring, retrieved_context):
                found_count += 1
                break  # Found this ground truth, move to next one

    context_recall_value = (
        found_count / len(ground_truth_values) if ground_truth_values else 0.0
    )

    # Calculate custom substring-based context precision
    # Precision = (number of retrieved contexts containing ground truth) / (total retrieved contexts)
    relevant_retrieved_count = 0
    for retrieved_context in retrieved_contexts:
        # Check if this retrieved context contains any ground truth substring
        for ground_truth_substring in ground_truth_values:
            if ground_truth_matches_text(ground_truth_substring, retrieved_context):
                relevant_retrieved_count += 1
                break  # This retrieved context is relevant, move to next one

    context_precision_value = (
        relevant_retrieved_count / len(retrieved_contexts) if retrieved_contexts else 0.0
    )

    return RagasRetrievalMetrics(
        context_precision=context_precision_value, context_recall=context_recall_value
    )


def evaluate_generation(
    query: str,
    response: str,
    retrieved_contexts: list[str],
    ground_truth_answer: str | None = None,
    judge_model: str | None = None,
) -> RagasGenerationMetrics:
    """Evaluate generation quality using Ragas metrics.

    Args:
        query: The user query
        response: The generated response from the LLM
        retrieved_contexts: List of retrieved document chunks used for generation
        ground_truth_answer: Optional reference answer for comparison
        judge_model: Optional LLM model for Ragas evaluation (defaults to gpt-4o)

    Returns:
        RagasGenerationMetrics with faithfulness and answer_relevancy

    Raises:
        ValueError: If Ragas evaluation fails
    """

    # Prepare dataset for Ragas
    data = {"question": [query], "answer": [response], "contexts": [retrieved_contexts]}

    if ground_truth_answer:
        data["ground_truth"] = [ground_truth_answer]

    dataset = Dataset.from_dict(data)

    # Configure LLM for Ragas
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required for RAGAS evaluation")

    # Use Langchain wrapper with ChatOpenAI (new RAGAS API)
    chat_llm = ChatOpenAI(model=judge_model or "gpt-4o", api_key=openai_api_key)
    llm = LangchainLLMWrapper(chat_llm)

    # Create metric instances with configured LLM
    faithfulness_metric = Faithfulness(llm=llm)
    answer_relevancy_metric = AnswerRelevancy(llm=llm)

    metrics = [faithfulness_metric, answer_relevancy_metric]

    try:
        # Run Ragas evaluation
        result = evaluate(dataset, metrics=metrics)

        return RagasGenerationMetrics(
            faithfulness=result.get("faithfulness"), answer_relevancy=result.get("answer_relevancy")
        )
    except Exception as e:
        raise ValueError(f"Ragas evaluation failed: {str(e)}") from e


def format_ragas_metrics_for_display(
    retrieval_metrics: RagasRetrievalMetrics | None = None,
    generation_metrics: RagasGenerationMetrics | None = None,
) -> dict[str, Any]:
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


def get_ragas_metric_descriptions() -> dict[str, str]:
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
