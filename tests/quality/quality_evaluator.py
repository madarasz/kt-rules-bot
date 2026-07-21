"""Quality evaluator for RAG responses (RAGAS-style metrics, our own implementation).

Evaluates RAG responses using five metrics:
- Quote Precision: Validates quote.text from LLM response against ground_truth_contexts
- Quote Recall: Checks if ground_truth_contexts are represented in quote.text
- Quote Faithfulness: Validates quote.text is grounded in retrieved RAG contexts (no hallucination in citations)
- Explanation Faithfulness: Validates short_answer+explanation is grounded in quote.text (no hallucination beyond quotes)
- Answer Correctness: Validates short_answer+explanation against ground_truth_answers

Quote precision/recall/faithfulness are deterministic (substring and fuzzy matching);
explanation faithfulness and answer correctness come from a single CustomJudge LLM call.
"""

import math
from dataclasses import dataclass

from src.lib.constants import QUALITY_METRIC_WEIGHTS, QUALITY_TEST_JUDGE_MODEL
from src.lib.logging import get_logger
from src.lib.pricing import calculate_llm_cost
from src.lib.retrieval_metrics import evaluate_retrieval
from src.lib.text_utils import normalize_text_for_matching
from src.models.structured_response import StructuredLLMResponse
from tests.quality.custom_judge import CustomJudge
from tests.quality.fuzzy_quote_evaluator import FuzzyQuoteEvaluator
from tests.quality.metadata_generator import MetadataGenerator
from tests.quality.test_case_models import GroundTruthAnswer, GroundTruthContext

logger = get_logger(__name__)


@dataclass
class QualityMetrics:
    """Container for quality evaluation metrics with detailed feedback."""

    quote_precision: float | None = None
    quote_recall: float | None = None
    quote_faithfulness: float | None = None
    explanation_faithfulness: float | None = None
    answer_correctness: float | None = None
    error: str | None = None
    feedback: str = ""
    quote_recall_feedback: str | None = None

    # Cost tracking (based on actual judge model token usage)
    total_cost_usd: float = 0.0
    cache_savings_usd: float = 0.0  # Prompt-cache net savings on the judge call

    # Detailed per-quote/answer breakdowns from custom judge
    quote_faithfulness_details: dict[str, float] | None = None  # chunk_id -> score
    answer_correctness_details: dict[str, float] | None = None  # answer_key -> score
    llm_quotes_structured: list[dict] | None = None  # List of {chunk_id, quote_title, quote_text}


class QualityEvaluator:
    """Evaluates RAG responses using deterministic quote metrics plus a custom LLM judge."""

    def __init__(self, llm_model: str | None = None):
        """Initialize the evaluator.

        Args:
            llm_model: Optional judge model name (uses QUALITY_TEST_JUDGE_MODEL if not specified)
        """
        self.llm_model = llm_model or QUALITY_TEST_JUDGE_MODEL

    async def evaluate(
        self,
        query: str,
        llm_response: StructuredLLMResponse | None,
        context_chunks: list,  # list[DocumentChunk] or list[str] for backward compatibility
        ground_truth_answers: list[GroundTruthAnswer],
        ground_truth_contexts: list[GroundTruthContext],
    ) -> QualityMetrics:
        """Evaluate a single RAG response.

        Args:
            query: The user's question
            llm_response: The structured LLM response object (can be None if LLM call failed)
            context_chunks: The RAG context chunks (DocumentChunk objects or strings for backward compat)
            ground_truth_answers: List of ground truth answer objects with keys and priorities
            ground_truth_contexts: List of ground truth context objects with keys and priorities

        Returns:
            QualityMetrics with scores (0-1 scale)
        """
        try:
            # Check if LLM response is None (e.g., due to timeout, rate limit, or other errors)
            if llm_response is None:
                logger.warning("LLM response is None, cannot evaluate")
                return QualityMetrics(error="LLM response is None (generation failed)")

            # Handle DocumentChunk objects vs strings (backward compatibility)
            from src.models.rag_context import DocumentChunk

            if context_chunks and isinstance(context_chunks[0], DocumentChunk):
                context_chunk_objects = context_chunks
            else:
                # Legacy: strings only (no DocumentChunk objects available)
                context_chunk_objects = None

            # Extract and normalize components from structured response
            # Concatenate quote_title and quote_text for matching against ground truth
            quotes_text = [
                self._normalize_text(f"{q.quote_title} {q.quote_text}")
                for q in llm_response.quotes
            ]

            logger.debug(f"Extracted {len(quotes_text)} quotes from structured response")

            ground_truth_context_texts = [ctx.text for ctx in ground_truth_contexts]
            normalized_ground_truth_contexts = [
                self._normalize_text(gt_text) for gt_text in ground_truth_context_texts
            ]

            # Quote Precision and Quote Recall: compare quotes.text (what was cited) against
            # ground_truth_contexts (what should be cited) by substring match with priority weights.
            retrieval_metrics = evaluate_retrieval(
                retrieved_contexts=quotes_text,
                ground_truth_contexts=ground_truth_contexts,  # Pass GroundTruthContext objects
            )

            llm_quotes_structured = [
                {
                    "chunk_id": q.chunk_id,
                    "quote_title": q.quote_title,
                    "quote_text": q.quote_text,
                }
                for q in llm_response.quotes
            ]

            # Both LLM-scored metrics and quote faithfulness need DocumentChunk objects
            # for chunk_id filtering. Without them nothing here can be scored, so skip
            # the judge entirely rather than paying for a call we cannot use.
            explanation_faithfulness_score = None
            answer_correctness_score = None
            custom_judge_feedback = None
            answer_correctness_details = None
            quote_faithfulness_score = None
            quote_faithfulness_details = None
            evaluation_error_message = None
            judge_prompt_tokens = 0
            judge_completion_tokens = 0
            judge_cache_read_tokens = 0
            judge_cache_creation_tokens = 0

            if context_chunk_objects is None:
                logger.warning(
                    "No DocumentChunk objects available (empty retrieval or legacy string "
                    "chunks). Skipping custom judge and quote faithfulness."
                )
                evaluation_error_message = (
                    "No DocumentChunk objects available - judge and quote faithfulness skipped"
                )
            else:
                # Explanation Faithfulness + Answer Correctness: single unified judge call
                logger.debug(f"Running custom LLM judge (model={self.llm_model})")

                custom_judge = CustomJudge(model=self.llm_model)
                judge_result = await custom_judge.evaluate(
                    query=query,
                    llm_response_text=llm_response.to_json(),  # Full structured response as JSON
                    llm_quotes_structured=llm_quotes_structured,
                    ground_truth_answers=ground_truth_answers,  # Pass objects, not strings
                    ground_truth_contexts=ground_truth_context_texts,
                )

                if judge_result.error:
                    logger.error(f"Custom judge evaluation failed: {judge_result.error}")
                    # Surface as metrics.error so the run is reported as an evaluation
                    # failure instead of being silently rescored over the remaining
                    # metric weights (which would report a perfect run as 100%).
                    evaluation_error_message = f"Judge error: {judge_result.error}"
                    custom_judge_feedback = f"Custom judge error: {judge_result.error}"
                else:
                    explanation_faithfulness_score = judge_result.explanation_faithfulness
                    answer_correctness_score = judge_result.answer_correctness
                    custom_judge_feedback = judge_result.feedback
                    answer_correctness_details = judge_result.answer_correctness_details
                    # Capture actual token counts from LLM call
                    judge_prompt_tokens = judge_result.prompt_tokens
                    judge_completion_tokens = judge_result.completion_tokens
                    judge_cache_read_tokens = judge_result.cache_read_tokens
                    judge_cache_creation_tokens = judge_result.cache_creation_tokens
                    logger.info(
                        f"Custom judge completed: ef={explanation_faithfulness_score:.2f}, "
                        f"ac={answer_correctness_score:.2f}"
                    )

                # Quote Faithfulness: fuzzy string matching (deterministic, fast, cheap)
                fuzzy_result = FuzzyQuoteEvaluator().evaluate(
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

            metrics = QualityMetrics(
                quote_precision=retrieval_metrics.context_precision,
                quote_recall=retrieval_metrics.context_recall,
                quote_faithfulness=quote_faithfulness_score,
                explanation_faithfulness=explanation_faithfulness_score,
                answer_correctness=answer_correctness_score,
                quote_faithfulness_details=quote_faithfulness_details,
                answer_correctness_details=answer_correctness_details,
                llm_quotes_structured=llm_quotes_structured,
                feedback=custom_judge_feedback or "",
                error=evaluation_error_message,
            )

            metrics.quote_recall_feedback = self._generate_quote_recall_feedback(
                metrics.quote_recall,
                quotes_text,
                normalized_ground_truth_contexts,
                ground_truth_context_texts,
                ground_truth_contexts,  # Pass objects for keys/priorities
            )

            # Cost of the single judge call. Use ACTUAL token counts, including prompt-cache
            # tokens so cost reflects (and savings are tracked for) cache hits.
            judge_breakdown = calculate_llm_cost(
                prompt_tokens=judge_prompt_tokens,
                completion_tokens=judge_completion_tokens,
                model=self.llm_model,
                cache_read_tokens=judge_cache_read_tokens,
                cache_creation_tokens=judge_cache_creation_tokens,
            )
            metrics.total_cost_usd = judge_breakdown.total_cost
            metrics.cache_savings_usd = judge_breakdown.cache_savings

            logger.debug(
                "custom_judge_cost_actual",
                input_tokens=judge_prompt_tokens,
                output_tokens=judge_completion_tokens,
                cache_read_tokens=judge_cache_read_tokens,
                cache_creation_tokens=judge_cache_creation_tokens,
                cost_usd=metrics.total_cost_usd,
                cache_savings_usd=metrics.cache_savings_usd,
                judge_model=self.llm_model,
            )

            return metrics

        except Exception as e:
            logger.error(f"Quality evaluation failed: {e}", exc_info=True)
            return QualityMetrics(error=str(e))

    def compute_deterministic_metrics(
        self,
        llm_response: StructuredLLMResponse,
        context_texts: list[str],
        chunk_ids: list[str],
        ground_truth_contexts: list[GroundTruthContext],
    ) -> QualityMetrics:
        """Compute the judge-free metrics (quote precision/recall/faithfulness)
        from a structured response and its retrieval context.

        Mirrors the deterministic half of evaluate() so the batch generation-write
        path can persist the same quote metrics the live path produces, instead of
        writing an empty QualityMetrics(). Judge fields (explanation_faithfulness,
        answer_correctness) are left None and filled in later during scoring.

        Args:
            llm_response: Parsed structured response with cited quotes
            context_texts: Retrieved RAG chunk texts (for faithfulness)
            chunk_ids: Chunk ids aligned with context_texts
            ground_truth_contexts: Expected contexts (for precision/recall)
        """
        from src.models.rag_context import DocumentChunk

        quotes_text = [
            self._normalize_text(f"{q.quote_title} {q.quote_text}")
            for q in llm_response.quotes
        ]
        llm_quotes_structured = [
            {"chunk_id": q.chunk_id, "quote_title": q.quote_title, "quote_text": q.quote_text}
            for q in llm_response.quotes
        ]

        retrieval_metrics = evaluate_retrieval(
            retrieved_contexts=quotes_text,
            ground_truth_contexts=ground_truth_contexts,
        )

        # ponytail: FuzzyQuoteEvaluator only reads .text/.chunk_id off each chunk,
        # so the other DocumentChunk fields are unused placeholders here.
        chunks = [
            DocumentChunk(
                chunk_id=cid, document_id="", text=text, header="",
                header_level=2, metadata={}, relevance_score=0.0, position_in_doc=0,
            )
            for cid, text in zip(chunk_ids, context_texts, strict=False)
        ]
        fuzzy_result = FuzzyQuoteEvaluator().evaluate(
            llm_quotes_structured=llm_quotes_structured,
            rag_context_chunks=chunks,
        )

        metrics = QualityMetrics(
            quote_precision=retrieval_metrics.context_precision,
            quote_recall=retrieval_metrics.context_recall,
            quote_faithfulness=fuzzy_result.quote_faithfulness,
            quote_faithfulness_details={
                s["chunk_id"]: s["similarity"] for s in fuzzy_result.quote_scores
            },
            llm_quotes_structured=llm_quotes_structured,
        )
        metrics.quote_recall_feedback = self._generate_quote_recall_feedback(
            metrics.quote_recall,
            quotes_text,
            [self._normalize_text(c.text) for c in ground_truth_contexts],
            [c.text for c in ground_truth_contexts],
            ground_truth_contexts,
        )
        return metrics

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison.
        Removes asterisks, lowercases, and strips whitespace.

        Args:
            text: Text to normalize

        Returns:
            Normalized text
        """
        return normalize_text_for_matching(text)

    def calculate_aggregate_score(self, metrics: QualityMetrics) -> float:
        """Calculate weighted aggregate score from quality metrics.

        Uses QUALITY_METRIC_WEIGHTS to prioritize more important metrics:
        - answer_correctness: 50%
        - quote_recall: 20%
        - explanation_faithfulness: 15%
        - quote_faithfulness: 10%
        - quote_precision: 5%

        Args:
            metrics: QualityMetrics instance

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
                weight = QUALITY_METRIC_WEIGHTS.get(metric_name, 0.0)
                weighted_sum += value * weight
                total_weight += weight

        if total_weight == 0:
            return 0.0

        # Normalize by total weight and scale to 0-100
        return (weighted_sum / total_weight) * 100

    def _generate_quote_recall_feedback(
        self,
        score: float | None,
        retrieved_contexts: list[str],
        normalized_ground_truth_contexts: list[str],
        original_ground_truth_contexts: list[str],
        ground_truth_context_objects: list[GroundTruthContext] | None = None,
    ) -> str:
        """Generate feedback for quote recall with missing ground truths (keys and priorities).

        Delegates to shared MetadataGenerator.generate_quote_recall_feedback() for reusability.

        Args:
            score: The quote recall score (0-1, priority-weighted)
            retrieved_contexts: Normalized contexts that were retrieved/cited
            normalized_ground_truth_contexts: Normalized expected contexts
            original_ground_truth_contexts: Original (non-normalized) expected contexts for display
            ground_truth_context_objects: GroundTruthContext objects with keys and priorities (optional)

        Returns:
            Feedback listing missing ground truths with keys and priorities, or None if perfect score
        """
        return MetadataGenerator.generate_quote_recall_feedback(
            score=score,
            retrieved_contexts=retrieved_contexts,
            normalized_ground_truth_contexts=normalized_ground_truth_contexts,
            original_ground_truth_contexts=original_ground_truth_contexts,
            ground_truth_context_objects=ground_truth_context_objects,
        )
