"""Fuzzy quote validator for quality testing.

Provides deterministic, fast quote validation using string matching instead of LLM-based evaluation.
Replaces the "Quote Faithfulness" metric from LLM judge with fuzzy string matching.
"""

from dataclasses import dataclass

from src.lib.logging import get_logger
from src.models.rag_context import DocumentChunk
from src.services.llm.quote_validator import QuoteValidator

logger = get_logger(__name__)


@dataclass
class FuzzyQuoteEvaluationResult:
    """Result from fuzzy quote evaluation."""

    quote_faithfulness: float  # 0.0-1.0 (aggregate score - fraction of valid quotes)
    quote_scores: list[dict]  # Per-quote details with similarity scores
    # Each dict: {"quote_text": str, "quote_title": str, "similarity": float,
    #             "matched_chunk_text": str, "chunk_id": str, "is_valid": bool}
    total_quotes: int
    valid_quotes: int
    invalid_quotes: int


class FuzzyQuoteEvaluator:
    """Fuzzy quote validator using string matching for quality testing.

    Uses QuoteValidator with strict threshold (0.98) to detect quote inaccuracies.
    Much faster and cheaper than LLM-based evaluation, and fully deterministic.
    """

    def __init__(self):
        """Initialize fuzzy quote evaluator with QuoteValidator."""
        # QuoteValidator uses QUOTE_SIMILARITY_THRESHOLD from constants (0.98)
        self.validator = QuoteValidator()

    def evaluate(
        self,
        llm_quotes_structured: list[dict],
        rag_context_chunks: list[DocumentChunk],
    ) -> FuzzyQuoteEvaluationResult:
        """Evaluate quote faithfulness using fuzzy string matching.

        Args:
            llm_quotes_structured: List of dicts with chunk_id, quote_title, quote_text
            rag_context_chunks: Full list of DocumentChunk objects from RAG

        Returns:
            FuzzyQuoteEvaluationResult with aggregate score and per-quote details
        """
        # Extract context chunks as strings
        context_texts = [chunk.text for chunk in rag_context_chunks]
        chunk_ids = [str(chunk.chunk_id) for chunk in rag_context_chunks]

        # Prepare quotes for validation
        quotes_for_validation = []
        for quote in llm_quotes_structured:
            quotes_for_validation.append(
                {
                    "quote_title": quote.get("quote_title", ""),
                    "quote_text": quote.get("quote_text", ""),
                    "chunk_id": quote.get("chunk_id", ""),
                }
            )

        # Run validation
        validation_result = self.validator.validate(
            quotes=quotes_for_validation,
            context_chunks=context_texts,
            chunk_ids=chunk_ids,
        )

        logger.info(
            "Fuzzy quote evaluation complete",
            extra={
                "total_quotes": validation_result.total_quotes,
                "valid_quotes": validation_result.valid_quotes,
                "validation_score": validation_result.validation_score,
                "threshold": self.validator.similarity_threshold,
            },
        )

        return FuzzyQuoteEvaluationResult(
            quote_faithfulness=validation_result.validation_score,
            quote_scores=validation_result.quote_scores,
            total_quotes=validation_result.total_quotes,
            valid_quotes=validation_result.valid_quotes,
            invalid_quotes=len(validation_result.invalid_quotes),
        )
