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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import answer_correctness, faithfulness

from src.lib.constants import QUALITY_TEST_JUDGE_MODEL
from src.lib.logging import get_logger
from src.lib.ragas_adapter import evaluate_retrieval
from src.lib.text_utils import normalize_text_for_matching
from src.lib.tokens import estimate_cost
from src.models.structured_response import StructuredLLMResponse

logger = get_logger(__name__)


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

    # Detailed feedback for each metric
    quote_precision_feedback: str | None = None
    quote_recall_feedback: str | None = None
    quote_faithfulness_feedback: str | None = None
    explanation_faithfulness_feedback: str | None = None
    answer_correctness_feedback: str | None = None

    # Cost tracking (estimated based on judge model usage)
    total_cost_usd: float = 0.0


class RagasEvaluator:
    """Evaluates RAG responses using Ragas metrics."""

    def __init__(self, llm_model: str | None = None):
        """Initialize Ragas evaluator.

        Args:
            llm_model: Optional LLM model name for Ragas evaluation (uses default if not specified)
        """
        self.llm_model = llm_model

    async def evaluate(
        self,
        query: str,
        llm_response: StructuredLLMResponse | None,
        context_chunks: list[str],
        ground_truth_answers: list[str],
        ground_truth_contexts: list[str],
    ) -> RagasMetrics:
        """Evaluate a single RAG response using Ragas metrics.

        Args:
            query: The user's question
            llm_response: The structured LLM response object (can be None if LLM call failed)
            context_chunks: The RAG context chunks provided to the LLM
            ground_truth_answers: List of acceptable ground truth answers
            ground_truth_contexts: List of expected context snippets

        Returns:
            RagasMetrics with scores (0-1 scale)
        """
        try:
            # Check if LLM response is None (e.g., due to timeout, rate limit, or other errors)
            if llm_response is None:
                logger.warning("LLM response is None, cannot evaluate with Ragas")
                return RagasMetrics(error="LLM response is None (generation failed)")

            # Extract and normalize components from structured response
            quotes_text = [self._normalize_text(q.quote_text) for q in llm_response.quotes]
            short_answer = self._normalize_text(llm_response.short_answer)
            explanation = self._normalize_text(llm_response.explanation)
            answer_text = f"{short_answer} {explanation}".strip()

            logger.debug(f"Extracted {len(quotes_text)} quotes from structured response")

            # Normalize ground truth values for comparison
            normalized_ground_truth_contexts = [
                self._normalize_text(gt) for gt in ground_truth_contexts
            ]
            normalized_ground_truth_answers = [
                self._normalize_text(gt) for gt in ground_truth_answers
            ]

            # For Quote Precision and Quote Recall:
            # Use evaluate_retrieval from ragas_adapter (substring matching approach)
            # Compare quotes.text (what was cited) against ground_truth_contexts (what should be cited)
            retrieval_metrics = evaluate_retrieval(
                retrieved_contexts=quotes_text,
                ground_truth_contexts=normalized_ground_truth_contexts,
            )

            # For Quote Faithfulness:
            # Compare quotes.text (what was cited) with context_chunks (what RAG retrieved)
            # This ensures citations are grounded in retrieved context
            quotes_combined = " ".join(quotes_text) if quotes_text else ""

            # For Explanation Faithfulness:
            # Compare answer_text (short_answer + explanation) with quotes (what was cited)
            # This ensures the explanation doesn't hallucinate beyond the quotes

            # For Answer Correctness:
            # Compare answer_text (short_answer + explanation) with ground_truth_answers

            # Prepare datasets for Ragas
            # Dataset 1: Quote Faithfulness
            # contexts = context_chunks (what RAG retrieved), answer = quotes_combined (what was cited)
            data_quote_faithfulness = {
                "question": [query],
                "answer": [quotes_combined],  # What was cited (normalized)
                "contexts": [
                    context_chunks
                ],  # What RAG retrieved (not normalized - keep original for RAG faithfulness check)
                "ground_truth": [
                    " ".join(normalized_ground_truth_contexts)
                ],  # Not used for faithfulness
            }

            # Dataset 2: For Explanation Faithfulness and Answer Correctness
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

            dataset_quote_faithfulness = Dataset.from_dict(data_quote_faithfulness)
            dataset_explanation = Dataset.from_dict(data_explanation)

            # Run Ragas evaluation in separate thread to avoid event loop conflicts
            # Ragas uses async HTTP clients internally which can cause "Event loop is closed" errors
            # when running in parallel with asyncio.to_thread(). Using ThreadPoolExecutor with
            # loop.run_in_executor() properly isolates the evaluation.
            loop = asyncio.get_event_loop()
            executor = ThreadPoolExecutor(max_workers=1)

            # Run Ragas evaluation - Part 1: Quote Faithfulness
            result_quote_faithfulness = await loop.run_in_executor(
                executor,
                _run_ragas_evaluate_sync,
                dataset_quote_faithfulness,
                [faithfulness],  # This measures quote faithfulness
            )

            # Run Ragas evaluation - Part 2: Explanation metrics
            result_explanation = await loop.run_in_executor(
                executor,
                _run_ragas_evaluate_sync,
                dataset_explanation,
                [
                    faithfulness,
                    answer_correctness,
                ],  # Explanation faithfulness and answer correctness
            )

            # Clean up executor
            executor.shutdown(wait=True)

            # Extract scores from EvaluationResult objects
            result_qf_df = result_quote_faithfulness.to_pandas()
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

            metrics = RagasMetrics(
                quote_precision=retrieval_metrics.context_precision,
                quote_recall=retrieval_metrics.context_recall,
                quote_faithfulness=safe_extract_metric(
                    result_qf_df, "faithfulness", "quote_faithfulness"
                ),
                explanation_faithfulness=safe_extract_metric(
                    result_explanation_df, "faithfulness", "explanation_faithfulness"
                ),
                answer_correctness=safe_extract_metric(
                    result_explanation_df, "answer_correctness", "answer_correctness"
                ),
            )

            # Generate detailed feedback for each metric
            metrics.quote_precision_feedback = self._generate_quote_precision_feedback(
                metrics.quote_precision, quotes_text, normalized_ground_truth_contexts
            )
            metrics.quote_recall_feedback = self._generate_quote_recall_feedback(
                metrics.quote_recall,
                quotes_text,
                normalized_ground_truth_contexts,
                ground_truth_contexts,
            )
            metrics.quote_faithfulness_feedback = self._generate_quote_faithfulness_feedback(
                metrics.quote_faithfulness, quotes_combined, context_chunks
            )
            metrics.explanation_faithfulness_feedback = (
                self._generate_explanation_faithfulness_feedback(
                    metrics.explanation_faithfulness, answer_text, quotes_text
                )
            )
            metrics.answer_correctness_feedback = self._generate_answer_correctness_feedback(
                metrics.answer_correctness, answer_text, ground_truth_answers
            )

            # Estimate cost based on judge model usage
            # Ragas makes 2 separate evaluations with 3 total metrics (1+2)
            # Quote Precision/Recall are calculated locally without LLM judge
            # Estimate token usage: query + context + answer + ground truths for each metric
            estimated_input_tokens_per_metric = (
                len(query.split()) * 1.3  # query
                + sum(len(chunk.split()) * 1.3 for chunk in context_chunks)
                / 3  # context (averaged)
                + len(answer_text.split()) * 1.3  # answer
                + sum(len(gt.split()) * 1.3 for gt in ground_truth_answers)
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
        """Calculate an aggregate score from Ragas metrics.

        Args:
            metrics: RagasMetrics instance

        Returns:
            Aggregate score (0-100 scale)
        """
        if metrics.error:
            return 0.0

        scores = []
        if metrics.quote_precision is not None:
            # Check for NaN - should not happen here due to local calculation, but be defensive
            if not (isinstance(metrics.quote_precision, float) and math.isnan(metrics.quote_precision)):
                scores.append(metrics.quote_precision)
        if metrics.quote_recall is not None:
            # Check for NaN - should not happen here due to local calculation, but be defensive
            if not (isinstance(metrics.quote_recall, float) and math.isnan(metrics.quote_recall)):
                scores.append(metrics.quote_recall)
        if metrics.quote_faithfulness is not None:
            # Check for NaN - safe_extract_metric should have filtered these out, but be defensive
            if not (isinstance(metrics.quote_faithfulness, float) and math.isnan(metrics.quote_faithfulness)):
                scores.append(metrics.quote_faithfulness)
        if metrics.explanation_faithfulness is not None:
            # Check for NaN - safe_extract_metric should have filtered these out, but be defensive
            if not (isinstance(metrics.explanation_faithfulness, float) and math.isnan(metrics.explanation_faithfulness)):
                scores.append(metrics.explanation_faithfulness)
        if metrics.answer_correctness is not None:
            # Check for NaN - safe_extract_metric should have filtered these out, but be defensive
            if not (isinstance(metrics.answer_correctness, float) and math.isnan(metrics.answer_correctness)):
                scores.append(metrics.answer_correctness)

        if not scores:
            return 0.0

        # Average of all available metrics, scaled to 0-100
        return (sum(scores) / len(scores)) * 100

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
    ) -> str:
        """Generate feedback for quote recall with missing ground truths.

        Quote Recall measures how much of the expected information was cited.
        Lists which ground truth contexts were not found in the quotes.

        Args:
            score: The quote recall score (0-1)
            retrieved_contexts: Normalized contexts that were retrieved/cited
            normalized_ground_truth_contexts: Normalized expected contexts
            original_ground_truth_contexts: Original (non-normalized) expected contexts for display

        Returns:
            Feedback listing missing ground truths, or None if perfect score
        """
        if score is None or score >= 1.0:
            return None  # Perfect score or unable to calculate

        # Find which ground truths are missing
        missing_ground_truths = []
        for i, (norm_gt, orig_gt) in enumerate(
            zip(normalized_ground_truth_contexts, original_ground_truth_contexts, strict=False), 1
        ):
            # Check if this ground truth appears in any retrieved context
            found = any(
                norm_gt in retrieved or retrieved in norm_gt for retrieved in retrieved_contexts
            )
            if not found:
                missing_ground_truths.append((i, orig_gt))

        if not missing_ground_truths:
            return None  # All ground truths found

        # Generate feedback
        feedback_lines = []
        feedback_lines.append("**Missing ground truth contexts:**")
        for idx, gt in missing_ground_truths:
            # Truncate long contexts
            gt_display = gt[:150] + "..." if len(gt) > 150 else gt
            feedback_lines.append(f"  {idx}. {gt_display}")

        return "\n".join(feedback_lines)

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
            feedback_lines.append("\n**Ground Truth Coverage Analysis:**")

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
                feedback_lines.append("\n✓ **Covered ground truths:**")
                for idx, gt, cov in covered_truths[:3]:
                    feedback_lines.append(f"  {idx}. {gt} ({cov * 100:.0f}% terms found)")

            # Show missing ground truths
            if missing_truths:
                feedback_lines.append("\n❌ **Missing or weakly covered ground truths:**")
                for idx, gt, cov in missing_truths:
                    feedback_lines.append(f"  {idx}. {gt} ({cov * 100:.0f}% terms found)")

            if not missing_truths and not covered_truths:
                feedback_lines.append("- Unable to perform detailed coverage analysis")
                feedback_lines.append(
                    f"- Review answer against {len(ground_truth_answers)} ground truth statement(s)"
                )

        return "\n".join(feedback_lines) if feedback_lines else None
