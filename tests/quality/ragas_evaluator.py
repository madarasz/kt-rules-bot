"""Ragas-based evaluator for RAG quality metrics.

Evaluates RAG responses using Ragas metrics:
- Quote Precision: Validates quote.text from LLM response against ground_truth_contexts
- Quote Recall: Checks if ground_truth_contexts are represented in quote.text
- Quote Faithfulness: Validates quote.text is grounded in retrieved RAG contexts (no hallucination in citations)
- Explanation Faithfulness: Validates short_answer+explanation is grounded in quote.text (no hallucination beyond quotes)
- Answer Correctness: Validates short_answer+explanation against ground_truth_answers
"""

import asyncio
import math
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from datasets import Dataset
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from ragas import evaluate
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import AnswerCorrectness, Faithfulness

from src.lib.constants import QUALITY_TEST_JUDGE_MODEL, QUALITY_TEST_JUDGING, RAGAS_METRIC_WEIGHTS
from src.lib.logging import get_logger
from src.lib.ragas_adapter import evaluate_retrieval
from src.lib.text_utils import normalize_text_for_matching
from src.lib.tokens import estimate_cost
from src.models.structured_response import StructuredLLMResponse
from tests.quality.custom_judge import CustomJudge
from tests.quality.fuzzy_quote_evaluator import FuzzyQuoteEvaluator
from tests.quality.test_case_models import GroundTruthAnswer, GroundTruthContext

# Load environment variables from config/.env
load_dotenv("config/.env")

logger = get_logger(__name__)


def _get_ragas_llm(judge_model: str):
    """Get a configured RAGAS LLM instance.

    Args:
        judge_model: Model name to use for RAGAS evaluation

    Returns:
        Configured RAGAS LLM instance
    """
    # Get OpenAI API key from environment
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required for RAGAS evaluation")

    # Use Langchain wrapper with ChatOpenAI (new RAGAS API)
    chat_llm = ChatOpenAI(model=judge_model, api_key=openai_api_key)
    llm = LangchainLLMWrapper(chat_llm)

    return llm


def _run_ragas_evaluate_sync(dataset, metrics):
    """Run Ragas evaluate synchronously in a separate thread.

    This function is designed to be called from a thread pool executor
    to avoid event loop conflicts when running Ragas evaluations in parallel.
    Ragas uses async HTTP clients internally, which can cause event loop
    lifecycle issues when called from an existing async context.

    Args:
        dataset: Ragas Dataset object
        metrics: List of Ragas metrics to evaluate

    Returns:
        EvaluationResult from Ragas
    """
    import asyncio
    import warnings

    # Suppress ResourceWarnings related to unclosed resources
    # Ragas creates async HTTP clients that may not close cleanly in threads
    warnings.filterwarnings("ignore", category=ResourceWarning)

    # Get or create a new event loop for this thread
    # This ensures proper cleanup of async resources
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        result = evaluate(dataset, metrics=metrics)
        return result
    finally:
        # Don't close the loop here - let Python handle cleanup
        # Closing it explicitly can cause "Event loop is closed" errors
        # when async clients try to cleanup in __del__
        pass


@dataclass
class RagasMetrics:
    """Container for Ragas evaluation metrics with detailed feedback."""

    quote_precision: float | None = None
    quote_recall: float | None = None
    quote_faithfulness: float | None = None
    explanation_faithfulness: float | None = None
    answer_correctness: float | None = None
    error: str | None = None
    feedback: str = ""
    quote_precision_feedback: str | None = None
    quote_recall_feedback: str | None = None
    quote_faithfulness_feedback: str | None = None
    explanation_faithfulness_feedback: str | None = None
    answer_correctness_feedback: str | None = None

    # Cost tracking (estimated based on judge model usage)
    total_cost_usd: float = 0.0

    # Detailed per-quote/answer breakdowns from custom judge
    quote_faithfulness_details: dict[str, float] | None = None  # chunk_id -> score
    answer_correctness_details: dict[str, float] | None = None  # answer_key -> score
    llm_quotes_structured: list[dict] | None = None  # List of {chunk_id, quote_title, quote_text}


class RagasEvaluator:
    """Evaluates RAG responses using Ragas metrics."""

    def __init__(self, llm_model: str | None = None):
        """Initialize Ragas evaluator.

        Args:
            llm_model: Optional LLM model name for Ragas evaluation (uses default if not specified)
        """
        self.llm_model = llm_model or QUALITY_TEST_JUDGE_MODEL
        self._ragas_llm = None

    def _get_configured_llm(self):
        """Get or create a configured RAGAS LLM instance.

        Returns:
            Configured RAGAS LLM instance
        """
        if self._ragas_llm is None:
            self._ragas_llm = _get_ragas_llm(self.llm_model)
        return self._ragas_llm

    async def evaluate(
        self,
        query: str,
        llm_response: StructuredLLMResponse | None,
        context_chunks: list,  # list[DocumentChunk] or list[str] for backward compatibility
        ground_truth_answers: list[GroundTruthAnswer],
        ground_truth_contexts: list[GroundTruthContext],
    ) -> RagasMetrics:
        """Evaluate a single RAG response using Ragas metrics or custom judge.

        Args:
            query: The user's question
            llm_response: The structured LLM response object (can be None if LLM call failed)
            context_chunks: The RAG context chunks (DocumentChunk objects or strings for backward compat)
            ground_truth_answers: List of ground truth answer objects with keys and priorities
            ground_truth_contexts: List of ground truth context objects with keys and priorities

        Returns:
            RagasMetrics with scores (0-1 scale)
        """
        try:
            # Check if LLM response is None (e.g., due to timeout, rate limit, or other errors)
            if llm_response is None:
                logger.warning("LLM response is None, cannot evaluate with Ragas")
                return RagasMetrics(error="LLM response is None (generation failed)")

            # Handle DocumentChunk objects vs strings (backward compatibility)
            from src.models.rag_context import DocumentChunk

            if context_chunks and isinstance(context_chunks[0], DocumentChunk):
                context_chunk_objects = context_chunks
                context_chunk_texts = [chunk.text for chunk in context_chunks]
            else:
                # Legacy: strings only (no DocumentChunk objects available)
                context_chunk_objects = None
                context_chunk_texts = context_chunks

            # Extract and normalize components from structured response
            # Concatenate quote_title and quote_text for matching against ground truth
            quotes_text = [
                self._normalize_text(f"{q.quote_title} {q.quote_text}")
                for q in llm_response.quotes
            ]
            short_answer = self._normalize_text(llm_response.short_answer)
            explanation = self._normalize_text(llm_response.explanation)
            answer_text = f"{short_answer} {explanation}".strip()

            logger.debug(f"Extracted {len(quotes_text)} quotes from structured response")

            # Extract text from GroundTruthAnswer/Context objects
            ground_truth_answer_texts = [ans.text for ans in ground_truth_answers]
            ground_truth_context_texts = [ctx.text for ctx in ground_truth_contexts]

            # Normalize ground truth values for comparison
            normalized_ground_truth_contexts = [
                self._normalize_text(gt_text) for gt_text in ground_truth_context_texts
            ]
            normalized_ground_truth_answers = [
                self._normalize_text(gt_text) for gt_text in ground_truth_answer_texts
            ]

            # For Quote Precision and Quote Recall:
            # Use evaluate_retrieval from ragas_adapter (substring matching approach with priority weights)
            # Compare quotes.text (what was cited) against ground_truth_contexts (what should be cited)
            # Pass GroundTruthContext objects directly (they have text and weight properties)
            retrieval_metrics = evaluate_retrieval(
                retrieved_contexts=quotes_text,
                ground_truth_contexts=ground_truth_contexts,  # Pass GroundTruthContext objects
            )

            # For Explanation Faithfulness:
            # Compare answer_text (short_answer + explanation) with quotes (what was cited)
            # This ensures the explanation doesn't hallucinate beyond the quotes

            # For Answer Correctness:
            # Compare answer_text (short_answer + explanation) with ground_truth_answers

            # Note: Quote Faithfulness is now evaluated using fuzzy string matching (not Ragas)

            # Combine quotes for feedback generation
            quotes_combined = " ".join(quotes_text) if quotes_text else ""

            # Prepare dataset for Ragas - Explanation Faithfulness and Answer Correctness
            # Uses full answer (short_answer + explanation) validated against quotes
            # For Answer Correctness: ground_truth should be ground_truth_answers (expected answers)
            data_explanation = {
                "question": [query],
                "answer": [answer_text],  # short_answer + explanation (normalized)
                "contexts": [quotes_text],  # Validate against quotes (normalized)
                "ground_truth": [
                    " ".join(normalized_ground_truth_answers)
                ],  # Expected answer content (normalized)
            }

            # Initialize LLM-based metrics as None (may be calculated below)
            quote_faithfulness_score = None
            explanation_faithfulness_score = None
            answer_correctness_score = None
            custom_judge_feedback = None

            # Conditionally run LLM-based metrics based on QUALITY_TEST_JUDGING
            use_custom_judge = QUALITY_TEST_JUDGING == "CUSTOM"

            # Check if we can use custom judge (requires DocumentChunk objects)
            if use_custom_judge and context_chunk_objects is None:
                logger.warning(
                    "context_chunks are strings, not DocumentChunk objects. "
                    "Custom judge requires DocumentChunk objects for chunk_id filtering. "
                    "Falling back to Ragas mode."
                )
                use_custom_judge = False

            if use_custom_judge:
                logger.debug(f"Running custom LLM judge (QUALITY_TEST_JUDGING=CUSTOM, model={QUALITY_TEST_JUDGE_MODEL})")

                # Extract structured quotes with chunk_ids
                llm_quotes_structured = [
                    {
                        "chunk_id": q.chunk_id,
                        "quote_title": q.quote_title,
                        "quote_text": q.quote_text,
                    }
                    for q in llm_response.quotes
                ]

                # Call unified custom judge (single LLM call for explanation faithfulness + answer correctness + feedback)
                # Note: Quote faithfulness is evaluated separately using fuzzy string matching
                custom_judge = CustomJudge(model=QUALITY_TEST_JUDGE_MODEL)
                judge_result = await custom_judge.evaluate(
                    query=query,
                    llm_response_text=llm_response.to_json(),  # Full structured response as JSON
                    llm_quotes_structured=llm_quotes_structured,
                    ground_truth_answers=ground_truth_answers,  # Pass objects, not strings
                    ground_truth_contexts=ground_truth_context_texts,
                )

                # Extract metrics from custom judge result
                if judge_result.error:
                    logger.error(f"Custom judge evaluation failed: {judge_result.error}")
                    explanation_faithfulness_score = None
                    answer_correctness_score = None
                    custom_judge_feedback = f"Custom judge error: {judge_result.error}"
                    answer_correctness_details = None
                    # No tokens consumed on error
                    judge_prompt_tokens = 0
                    judge_completion_tokens = 0
                else:
                    explanation_faithfulness_score = judge_result.explanation_faithfulness
                    answer_correctness_score = judge_result.answer_correctness
                    custom_judge_feedback = judge_result.feedback
                    answer_correctness_details = judge_result.answer_correctness_details
                    # Capture actual token counts from LLM call
                    judge_prompt_tokens = judge_result.prompt_tokens
                    judge_completion_tokens = judge_result.completion_tokens

                # Evaluate quote faithfulness using fuzzy string matching (deterministic, fast, cheap)
                fuzzy_evaluator = FuzzyQuoteEvaluator()
                fuzzy_result = fuzzy_evaluator.evaluate(
                    llm_quotes_structured=llm_quotes_structured,
                    rag_context_chunks=context_chunk_objects,
                )
                quote_faithfulness_score = fuzzy_result.quote_faithfulness
                quote_faithfulness_details = {
                    score_dict["chunk_id"]: score_dict["similarity"]
                    for score_dict in fuzzy_result.quote_scores
                }

                logger.info(
                    f"Custom judge completed: ef={explanation_faithfulness_score:.2f}, "
                    f"ac={answer_correctness_score:.2f}"
                )
                logger.info(
                    f"Fuzzy quote validation completed: qf={quote_faithfulness_score:.2f} "
                    f"({fuzzy_result.valid_quotes}/{fuzzy_result.total_quotes} quotes valid)"
                )

            elif not use_custom_judge and QUALITY_TEST_JUDGING == "RAGAS":
                logger.debug("Running LLM-based Ragas metrics (QUALITY_TEST_JUDGING=RAGAS)")

                dataset_explanation = Dataset.from_dict(data_explanation)

                # Configure RAGAS metrics with LLM
                ragas_llm = self._get_configured_llm()

                # Create metric instances with configured LLM
                # Note: Quote faithfulness is now evaluated using fuzzy string matching (not Ragas)
                faithfulness_metric_explanation = Faithfulness(llm=ragas_llm)
                answer_correctness_metric = AnswerCorrectness(llm=ragas_llm)

                # Run Ragas evaluation in separate thread to avoid event loop conflicts
                # Ragas uses async HTTP clients internally which can cause "Event loop is closed" errors
                # when running in parallel with asyncio.to_thread(). Using ThreadPoolExecutor with
                # loop.run_in_executor() properly isolates the evaluation.
                loop = asyncio.get_event_loop()
                executor = ThreadPoolExecutor(max_workers=1)

                # Run Ragas evaluation - Explanation metrics only
                result_explanation = await loop.run_in_executor(
                    executor,
                    _run_ragas_evaluate_sync,
                    dataset_explanation,
                    [
                        faithfulness_metric_explanation,
                        answer_correctness_metric,
                    ],  # Explanation faithfulness and answer correctness
                )

                # Clean up executor
                executor.shutdown(wait=True)

                # Extract scores from EvaluationResult objects
                result_explanation_df = result_explanation.to_pandas()

                # Helper function to safely extract metric and check for NaN
                def safe_extract_metric(df, metric_name: str, metric_label: str):
                    """Extract metric from dataframe, checking for NaN values."""
                    if metric_name not in df:
                        return None
                    value = df[metric_name].iloc[0]
                    # Check if value is NaN
                    if isinstance(value, float) and math.isnan(value):
                        logger.error(
                            f"Ragas metric {metric_label} returned NaN - evaluation failed for this metric"
                        )
                        return None
                    return value

                explanation_faithfulness_score = safe_extract_metric(
                    result_explanation_df, "faithfulness", "explanation_faithfulness"
                )
                answer_correctness_score = safe_extract_metric(
                    result_explanation_df, "answer_correctness", "answer_correctness"
                )

                # Evaluate quote faithfulness using fuzzy string matching (deterministic, fast, cheap)
                fuzzy_evaluator = FuzzyQuoteEvaluator()
                fuzzy_result = fuzzy_evaluator.evaluate(
                    llm_quotes_structured=llm_quotes_structured,
                    rag_context_chunks=context_chunk_objects,
                )
                quote_faithfulness_score = fuzzy_result.quote_faithfulness
                quote_faithfulness_details = {
                    score_dict["chunk_id"]: score_dict["similarity"]
                    for score_dict in fuzzy_result.quote_scores
                }

                logger.info(
                    f"Fuzzy quote validation completed: qf={quote_faithfulness_score:.2f} "
                    f"({fuzzy_result.valid_quotes}/{fuzzy_result.total_quotes} quotes valid)"
                )
            else:
                logger.debug(f"Skipping LLM-based Ragas metrics (QUALITY_TEST_JUDGING={QUALITY_TEST_JUDGING})")

            metrics = RagasMetrics(
                quote_precision=retrieval_metrics.context_precision,
                quote_recall=retrieval_metrics.context_recall,
                quote_faithfulness=quote_faithfulness_score,
                explanation_faithfulness=explanation_faithfulness_score,
                answer_correctness=answer_correctness_score,
                quote_faithfulness_details=quote_faithfulness_details if use_custom_judge else None,
                answer_correctness_details=answer_correctness_details if use_custom_judge else None,
                llm_quotes_structured=llm_quotes_structured if use_custom_judge else None,
            )

            # Generate detailed feedback based on judging mode
            if QUALITY_TEST_JUDGING == "CUSTOM":
                # For custom judge: use single unified feedback
                metrics.feedback = custom_judge_feedback or ""

                # Still generate local feedback for quote precision/recall
                metrics.quote_precision_feedback = self._generate_quote_precision_feedback(
                    metrics.quote_precision, quotes_text, normalized_ground_truth_contexts
                )
                metrics.quote_recall_feedback = self._generate_quote_recall_feedback(
                    metrics.quote_recall,
                    quotes_text,
                    normalized_ground_truth_contexts,
                    ground_truth_context_texts,
                    ground_truth_contexts,  # Pass objects for keys/priorities
                )
            else:
                # For RAGAS or OFF modes: use individual feedback fields (legacy)
                metrics.quote_precision_feedback = self._generate_quote_precision_feedback(
                    metrics.quote_precision, quotes_text, normalized_ground_truth_contexts
                )
                metrics.quote_recall_feedback = self._generate_quote_recall_feedback(
                    metrics.quote_recall,
                    quotes_text,
                    normalized_ground_truth_contexts,
                    ground_truth_context_texts,
                    ground_truth_contexts,  # Pass objects for keys/priorities
                )
                metrics.quote_faithfulness_feedback = self._generate_quote_faithfulness_feedback(
                    metrics.quote_faithfulness, quotes_combined, context_chunk_texts
                )
                metrics.explanation_faithfulness_feedback = (
                    self._generate_explanation_faithfulness_feedback(
                        metrics.explanation_faithfulness, answer_text, quotes_text
                    )
                )
                metrics.answer_correctness_feedback = self._generate_answer_correctness_feedback(
                    metrics.answer_correctness, answer_text, ground_truth_answer_texts
                )

            # Calculate cost based on judge model usage (only if LLM-based metrics were run)
            if use_custom_judge:
                # Custom judge makes 1 unified LLM call
                # Use ACTUAL token counts from LLM response
                metrics.total_cost_usd = estimate_cost(
                    prompt_tokens=judge_prompt_tokens,
                    completion_tokens=judge_completion_tokens,
                    model=QUALITY_TEST_JUDGE_MODEL,
                )

                logger.debug(
                    "custom_judge_cost_actual",
                    input_tokens=judge_prompt_tokens,
                    output_tokens=judge_completion_tokens,
                    cost_usd=metrics.total_cost_usd,
                    judge_model=QUALITY_TEST_JUDGE_MODEL,
                )

            elif not use_custom_judge and QUALITY_TEST_JUDGING == "RAGAS":
                # Ragas makes 2 separate evaluations with 3 total metrics (1+2)
                # Quote Precision/Recall are calculated locally without LLM judge
                # Estimate token usage: query + context + answer + ground truths for each metric
                estimated_input_tokens_per_metric = (
                    len(query.split()) * 1.3  # query
                    + sum(len(chunk.split()) * 1.3 for chunk in context_chunk_texts)
                    / 3  # context (averaged)
                    + len(answer_text.split()) * 1.3  # answer
                    + sum(len(gt.split()) * 1.3 for gt in ground_truth_answer_texts)
                    / 3  # ground truths (averaged)
                )
                estimated_output_tokens_per_metric = 50  # Judge model outputs are typically short

                total_input_tokens = int(
                    estimated_input_tokens_per_metric * 3
                )  # 3 metrics using LLM judge
                total_output_tokens = int(estimated_output_tokens_per_metric * 3)

                metrics.total_cost_usd = estimate_cost(
                    prompt_tokens=total_input_tokens,
                    completion_tokens=total_output_tokens,
                    model=QUALITY_TEST_JUDGE_MODEL,
                )

                logger.debug(
                    "ragas_cost_estimated",
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    cost_usd=metrics.total_cost_usd,
                    judge_model=QUALITY_TEST_JUDGE_MODEL,
                )
            else:
                # No LLM-based evaluation costs when judging is OFF
                metrics.total_cost_usd = 0.0
                logger.debug("No Ragas LLM costs (QUALITY_TEST_JUDGING=OFF)")

            return metrics

        except Exception as e:
            logger.error(f"Ragas evaluation failed: {e}", exc_info=True)
            return RagasMetrics(error=str(e))

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison.
        Removes asterisks, lowercases, and strips whitespace.

        Args:
            text: Text to normalize

        Returns:
            Normalized text
        """
        return normalize_text_for_matching(text)

    def calculate_aggregate_score(self, metrics: RagasMetrics) -> float:
        """Calculate weighted aggregate score from Ragas metrics.

        Uses RAGAS_METRIC_WEIGHTS to prioritize more important metrics:
        - answer_correctness: 30%
        - quote_recall: 30%
        - explanation_faithfulness: 20%
        - quote_faithfulness: 15%
        - quote_precision: 5%

        Args:
            metrics: RagasMetrics instance

        Returns:
            Aggregate score (0-100 scale)
        """
        if metrics.error:
            return 0.0

        weighted_sum = 0.0
        total_weight = 0.0

        # Map metric names to values
        metric_values = {
            "answer_correctness": metrics.answer_correctness,
            "quote_recall": metrics.quote_recall,
            "explanation_faithfulness": metrics.explanation_faithfulness,
            "quote_faithfulness": metrics.quote_faithfulness,
            "quote_precision": metrics.quote_precision,
        }

        # Calculate weighted sum of available metrics
        for metric_name, value in metric_values.items():
            # Check if value is valid (not None and not NaN)
            if value is not None and not (isinstance(value, float) and math.isnan(value)):
                weight = RAGAS_METRIC_WEIGHTS.get(metric_name, 0.0)
                weighted_sum += value * weight
                total_weight += weight

        if total_weight == 0:
            return 0.0

        # Normalize by total weight and scale to 0-100
        return (weighted_sum / total_weight) * 100

    def _generate_quote_precision_feedback(
        self,
        _score: float | None,
        _retrieved_contexts: list[str],
        _ground_truth_contexts: list[str],
    ) -> str:
        """Generate minimal feedback for quote precision.

        Quote Precision measures how many of the cited quotes are actually relevant.
        Score alone is sufficient - no detailed explanation needed.

        Args:
            _score: The quote precision score (0-1) - currently unused
            _retrieved_contexts: Contexts that were retrieved/cited - currently unused
            ground_truth_contexts: Expected relevant contexts

        Returns:
            None (score is sufficient)
        """
        # User doesn't need explanation for this metric
        return None

    def _generate_quote_recall_feedback(
        self,
        score: float | None,
        retrieved_contexts: list[str],
        normalized_ground_truth_contexts: list[str],
        original_ground_truth_contexts: list[str],
        ground_truth_context_objects: list[GroundTruthContext] | None = None,
    ) -> str:
        """Generate feedback for quote recall with missing ground truths (now with keys and priorities).

        Quote Recall measures how much of the expected information was cited.
        Lists which ground truth contexts were not found in the quotes, showing keys and priorities.

        Args:
            score: The quote recall score (0-1, priority-weighted)
            retrieved_contexts: Normalized contexts that were retrieved/cited
            normalized_ground_truth_contexts: Normalized expected contexts
            original_ground_truth_contexts: Original (non-normalized) expected contexts for display
            ground_truth_context_objects: GroundTruthContext objects with keys and priorities (optional)

        Returns:
            Feedback listing missing ground truths with keys and priorities, or None if perfect score
        """
        if score is None or score >= 1.0:
            return None  # Perfect score or unable to calculate

        # Find which ground truths are missing
        missing_ground_truths = []

        if ground_truth_context_objects:
            # New format: use keys and priorities
            for gt_obj, norm_gt in zip(ground_truth_context_objects, normalized_ground_truth_contexts, strict=False):
                # Check if this ground truth appears in any retrieved context
                found = any(
                    norm_gt in retrieved or retrieved in norm_gt for retrieved in retrieved_contexts
                )
                if not found:
                    # Priority icons
                    priority_icon = {
                        "critical": "⭐",
                        "important": "⚠️",
                        "supporting": "ℹ️"
                    }.get(gt_obj.priority, "•")

                    missing_ground_truths.append((gt_obj.key, gt_obj.text, gt_obj.priority, priority_icon, gt_obj.weight))
        else:
            # Legacy format: use indices
            for i, (norm_gt, orig_gt) in enumerate(
                zip(normalized_ground_truth_contexts, original_ground_truth_contexts, strict=False), 1
            ):
                # Check if this ground truth appears in any retrieved context
                found = any(
                    norm_gt in retrieved or retrieved in norm_gt for retrieved in retrieved_contexts
                )
                if not found:
                    missing_ground_truths.append((f"context_{i}", orig_gt, "unknown", "•", 1.0))

        if not missing_ground_truths:
            return None  # All ground truths found

        # Generate feedback
        feedback_lines = []
        feedback_lines.append("**Missing ground truth contexts:**")
        for key, text, priority, icon, weight in missing_ground_truths:
            # Truncate long contexts
            text_display = text[:120] + "..." if len(text) > 120 else text
            feedback_lines.append(f"  - {icon} **{key}** ({priority}, weight={weight:.0f}): {text_display}")

        return "  \n".join(feedback_lines)

    def _generate_quote_faithfulness_feedback(
        self, score: float | None, quotes_combined: str, context_chunks: list[str]
    ) -> str:
        """Generate actionable feedback for quote faithfulness with statement analysis.

        Quote Faithfulness measures whether the quotes are grounded in the retrieved context.
        When score is low, attempt to identify potentially unsupported quotes.

        Args:
            score: The quote faithfulness score (0-1)
            quotes_combined: The combined quotes from the LLM
            context_chunks: The context chunks provided to the LLM

        Returns:
            Detailed feedback string with unsupported statement detection
        """
        if score is None:
            return "Quote faithfulness could not be calculated."

        score_pct = score * 100
        feedback_lines = []

        # Basic score interpretation
        if score >= 0.9:
            quality = "✅ Excellent"
            feedback_lines.append(
                f"{quality} ({score_pct:.1f}%): Quotes are highly faithful to retrieved context."
            )
        elif score >= 0.7:
            quality = "✓ Good"
            feedback_lines.append(
                f"{quality} ({score_pct:.1f}%): Most quotes supported by context."
            )
        elif score >= 0.5:
            quality = "⚠️ Fair"
            feedback_lines.append(
                f"{quality} ({score_pct:.1f}%): Some quotes not found in context."
            )
        else:
            quality = "❌ Poor"
            feedback_lines.append(
                f"{quality} ({score_pct:.1f}%): Significant hallucination in citations."
            )

        # For low scores, try to identify problematic quotes
        if score < 0.8:
            feedback_lines.append("\n**Potential Issues:**")

            # Combine all context into searchable text
            combined_context = " ".join(context_chunks).lower()

            # Split quotes into sentences
            import re

            sentences = re.split(r"[.!?]+", quotes_combined)
            unsupported = []

            # Simple heuristic: check if key phrases appear in context
            for sentence in sentences:
                sentence = sentence.strip()
                if len(sentence) < 20:  # Skip very short fragments
                    continue

                # Extract key phrases (words longer than 4 chars)
                words = [w.lower() for w in re.findall(r"\b\w{5,}\b", sentence)]

                if not words:
                    continue

                # Check if at least some key words appear in context
                matches = sum(1 for word in words if word in combined_context)
                coverage = matches / len(words) if words else 0

                # Flag sentences with low context coverage
                if coverage < 0.3 and len(sentence) > 30:
                    # Truncate long sentences for display
                    display = sentence[:120] + "..." if len(sentence) > 120 else sentence
                    unsupported.append(display)

            if unsupported:
                feedback_lines.append("Quotes with low context support:")
                for i, stmt in enumerate(unsupported[:5], 1):  # Show max 5
                    feedback_lines.append(f"  {i}. {stmt}")
                if len(unsupported) > 5:
                    feedback_lines.append(f"  ... and {len(unsupported) - 5} more")

        return "\n".join(feedback_lines) if feedback_lines else None

    def _generate_explanation_faithfulness_feedback(
        self, score: float | None, explanation: str, quotes: list[str]
    ) -> str:
        """Generate actionable feedback for explanation faithfulness with statement analysis.

        Explanation Faithfulness measures whether the LLM's explanation is grounded in the quotes.
        When score is low, attempt to identify potentially unsupported statements.

        Args:
            score: The explanation faithfulness score (0-1)
            explanation: The LLM's explanation/answer
            quotes: The quotes provided as context (not raw retrieved chunks)

        Returns:
            Detailed feedback string with unsupported statement detection
        """
        if score is None:
            return "Explanation faithfulness could not be calculated."

        score_pct = score * 100
        feedback_lines = []

        # Basic score interpretation
        if score >= 0.9:
            quality = "✅ Excellent"
            feedback_lines.append(
                f"{quality} ({score_pct:.1f}%): Explanation is highly faithful to quotes."
            )
        elif score >= 0.7:
            quality = "✓ Good"
            feedback_lines.append(
                f"{quality} ({score_pct:.1f}%): Most statements supported by quotes."
            )
        elif score >= 0.5:
            quality = "⚠️ Fair"
            feedback_lines.append(
                f"{quality} ({score_pct:.1f}%): Some unsupported statements detected."
            )
        else:
            quality = "❌ Poor"
            feedback_lines.append(
                f"{quality} ({score_pct:.1f}%): Significant hallucination detected."
            )

        # For low scores, try to identify problematic statements
        if score < 0.8:
            feedback_lines.append("\n**Potential Issues:**")

            # Combine all quotes into searchable text
            combined_quotes = " ".join(quotes).lower() if quotes else ""

            # Split explanation into sentences
            import re

            sentences = re.split(r"[.!?]+", explanation)
            unsupported = []

            # Simple heuristic: check if key phrases appear in quotes
            for sentence in sentences:
                sentence = sentence.strip()
                if len(sentence) < 20:  # Skip very short fragments
                    continue

                # Extract key phrases (words longer than 4 chars)
                words = [w.lower() for w in re.findall(r"\b\w{5,}\b", sentence)]

                if not words:
                    continue

                # Check if at least some key words appear in quotes
                matches = sum(1 for word in words if word in combined_quotes)
                coverage = matches / len(words) if words else 0

                # Flag sentences with low quote coverage
                if coverage < 0.3 and len(sentence) > 30:
                    # Truncate long sentences for display
                    display = sentence[:120] + "..." if len(sentence) > 120 else sentence
                    unsupported.append(display)

            if unsupported:
                feedback_lines.append("Statements with low quote support:")
                for i, stmt in enumerate(unsupported[:5], 1):  # Show max 5
                    feedback_lines.append(f"  {i}. {stmt}")
                if len(unsupported) > 5:
                    feedback_lines.append(f"  ... and {len(unsupported) - 5} more")

        return "\n".join(feedback_lines) if feedback_lines else None

    def _generate_answer_correctness_feedback(
        self, score: float | None, explanation: str, ground_truth_answers: list[str]
    ) -> str:
        """Generate actionable feedback for answer correctness with coverage analysis.

        Answer Correctness measures semantic similarity to ground truth answers.
        When score is low, identify which ground truths are missing from the answer.

        Args:
            score: The answer correctness score (0-1)
            explanation: The LLM's explanation/answer
            ground_truth_answers: Expected correct answers

        Returns:
            Detailed feedback string with missing ground truth analysis
        """
        if score is None:
            return "Answer correctness could not be calculated."

        score_pct = score * 100
        feedback_lines = []

        # Basic score interpretation
        if score >= 0.9:
            quality = "✅ Excellent"
            feedback_lines.append(
                f"{quality} ({score_pct:.1f}%): Answer closely matches ground truth."
            )
        elif score >= 0.7:
            quality = "✓ Good"
            feedback_lines.append(
                f"{quality} ({score_pct:.1f}%): Answer mostly correct with minor gaps."
            )
        elif score >= 0.5:
            quality = "⚠️ Fair"
            feedback_lines.append(
                f"{quality} ({score_pct:.1f}%): Answer partially correct, missing key points."
            )
        else:
            quality = "❌ Poor"
            feedback_lines.append(
                f"{quality} ({score_pct:.1f}%): Answer significantly deviates from expected."
            )

        # For low scores, check which ground truths are covered
        if score < 0.8 and ground_truth_answers:
            feedback_lines.append("\n**Ground Truth Answser Coverage Analysis:**")

            explanation_lower = explanation.lower()
            missing_truths = []
            covered_truths = []

            for i, gt in enumerate(ground_truth_answers, 1):
                gt_lower = gt.lower()

                # Extract key terms from ground truth (words 4+ chars)
                import re

                key_terms = [
                    w
                    for w in re.findall(r"\b\w{4,}\b", gt_lower)
                    if w
                    not in {
                        "this",
                        "that",
                        "with",
                        "from",
                        "have",
                        "will",
                        "while",
                        "when",
                        "where",
                    }
                ]

                if not key_terms:
                    continue

                # Check how many key terms appear in the answer
                matches = sum(1 for term in key_terms if term in explanation_lower)
                coverage = matches / len(key_terms) if key_terms else 0

                # Truncate for display
                gt_display = gt[:150] + "..." if len(gt) > 150 else gt

                if coverage >= 0.5:  # At least half the key terms present
                    covered_truths.append((i, gt_display, coverage))
                else:
                    missing_truths.append((i, gt_display, coverage))

            # Show covered ground truths
            if covered_truths:
                feedback_lines.append("\n✓ **Covered ground truth answers:**")
                for idx, gt, cov in covered_truths[:3]:
                    feedback_lines.append(f"  {idx}. {gt} ({cov * 100:.0f}% terms found)")

            # Show missing ground truths
            if missing_truths:
                feedback_lines.append("\n❌ **Missing or weakly covered ground truth answers:**")
                for idx, gt, cov in missing_truths:
                    feedback_lines.append(f"  {idx}. {gt} ({cov * 100:.0f}% terms found)")

            if not missing_truths and not covered_truths:
                feedback_lines.append("- Unable to perform detailed coverage analysis")
                feedback_lines.append(
                    f"- Review answer against {len(ground_truth_answers)} ground truth answer statement(s)"
                )

        return "\n".join(feedback_lines) if feedback_lines else None
