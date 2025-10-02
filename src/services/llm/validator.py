"""Response validation service for LLM outputs.

Implements combined LLM confidence + RAG retrieval score validation (FR-013).
Based on specs/001-we-are-building/contracts/llm-adapter.md
"""

from dataclasses import dataclass
from typing import Tuple

from src.services.llm.base import LLMResponse
from src.models.rag_context import RAGContext
from src.lib.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationResult:
    """Result of response validation."""

    is_valid: bool
    llm_confidence: float
    rag_score: float
    reason: str  # Explanation of validation result


class ResponseValidator:
    """Validates LLM responses using combined confidence thresholds.

    Implements FR-013: Combined validation requiring both LLM confidence
    AND RAG retrieval score to meet minimum thresholds.
    """

    def __init__(
        self,
        llm_confidence_threshold: float = 0.7,
        rag_score_threshold: float = 0.6,
    ):
        """Initialize response validator.

        Args:
            llm_confidence_threshold: Minimum LLM confidence score (0-1)
            rag_score_threshold: Minimum RAG relevance score (0-1)
        """
        self.llm_threshold = llm_confidence_threshold
        self.rag_threshold = rag_score_threshold

        logger.info(
            f"Initialized ResponseValidator with thresholds: "
            f"LLM={llm_confidence_threshold}, RAG={rag_score_threshold}"
        )

    def validate(
        self,
        llm_response: LLMResponse,
        rag_context: RAGContext,
    ) -> ValidationResult:
        """Validate LLM response against combined thresholds.

        Args:
            llm_response: Response from LLM provider
            rag_context: RAG retrieval context with relevance scores

        Returns:
            ValidationResult with pass/fail and reason
        """
        llm_confidence = llm_response.confidence_score
        rag_score = rag_context.avg_relevance

        # Check LLM confidence threshold
        llm_valid = llm_confidence >= self.llm_threshold

        # Check RAG score threshold
        rag_valid = rag_score >= self.rag_threshold

        # Combined validation: BOTH must pass
        is_valid = llm_valid and rag_valid

        # Generate reason message
        if is_valid:
            reason = (
                f"Response passed validation: "
                f"LLM confidence {llm_confidence:.2f} >= {self.llm_threshold}, "
                f"RAG score {rag_score:.2f} >= {self.rag_threshold}"
            )
            logger.info(reason)
        else:
            failures = []
            if not llm_valid:
                failures.append(
                    f"LLM confidence {llm_confidence:.2f} < {self.llm_threshold}"
                )
            if not rag_valid:
                failures.append(f"RAG score {rag_score:.2f} < {self.rag_threshold}")

            reason = f"Response failed validation: {', '.join(failures)}"
            logger.warning(reason)

        return ValidationResult(
            is_valid=is_valid,
            llm_confidence=llm_confidence,
            rag_score=rag_score,
            reason=reason,
        )

    def should_send_response(
        self,
        llm_response: LLMResponse,
        rag_context: RAGContext,
    ) -> Tuple[bool, str]:
        """Check if response should be sent to user.

        Convenience method that returns boolean and reason string.

        Args:
            llm_response: Response from LLM provider
            rag_context: RAG retrieval context

        Returns:
            Tuple of (should_send: bool, reason: str)
        """
        result = self.validate(llm_response, rag_context)
        return result.is_valid, result.reason

    def get_fallback_message(self) -> str:
        """Get fallback message when validation fails.

        Returns:
            User-friendly message to send instead of low-confidence response
        """
        return (
            "I apologize, but I cannot provide a confident answer to your question "
            "based on the available rules. This might be because:\n\n"
            "• The question is outside the scope of Kill Team 3rd edition rules\n"
            "• The relevant rules section wasn't found in my knowledge base\n"
            "• The question needs more specifics\n\n"
            "Please try rephrasing your question or asking about a specific rule section."
        )


def create_validator(
    llm_confidence_threshold: float = None,
    rag_score_threshold: float = None,
) -> ResponseValidator:
    """Create response validator with optional custom thresholds.

    Args:
        llm_confidence_threshold: Custom LLM threshold (default: 0.7)
        rag_score_threshold: Custom RAG threshold (default: 0.6)

    Returns:
        ResponseValidator instance
    """
    kwargs = {}
    if llm_confidence_threshold is not None:
        kwargs["llm_confidence_threshold"] = llm_confidence_threshold
    if rag_score_threshold is not None:
        kwargs["rag_score_threshold"] = rag_score_threshold

    return ResponseValidator(**kwargs)
