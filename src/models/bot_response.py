"""BotResponse model for Discord bot answers.

Represents an answer to a user query with rule citations.
Based on specs/001-we-are-building/data-model.md
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from src.models.structured_response import StructuredLLMResponse


# LLM Model names (actual model identifiers like "gpt-4.1", "claude-sonnet-4-5-20250929", etc.)
LLMModel = str


@dataclass
class Citation:
    """Source rule reference."""

    document_name: str  # "rules-1-phases.md"
    section: str  # "Movement Phase"
    quote: str  # Relevant excerpt (max 200 chars)
    document_type: str  # "core-rules", "faq", "team-rules", "ops", "killzone"
    last_update_date: date

    def validate(self) -> None:
        """Validate Citation fields.

        Raises:
            ValueError: If validation fails
        """
        # Quote length limit
        if len(self.quote) > 200:
            raise ValueError("quote exceeds 200 character limit")

        # Document type validation
        valid_types = {"core-rules", "faq", "team-rules", "ops", "killzone"}
        if self.document_type not in valid_types:
            raise ValueError(
                f"document_type must be one of: {', '.join(valid_types)}"
            )


@dataclass
class BotResponse:
    """An answer to a user query with rule citations."""

    response_id: UUID
    query_id: UUID  # FK to UserQuery
    answer_text: str  # JSON string if structured, markdown if not
    citations: list[Citation]
    confidence_score: float  # LLM confidence (0-1)
    rag_score: float  # RAG avg relevance (0-1)
    validation_passed: bool  # FR-013 combined validation
    llm_model: LLMModel
    token_count: int
    latency_ms: int
    timestamp: datetime
    structured_data: Optional["StructuredLLMResponse"] = None  # Parsed JSON response

    def validate(self) -> None:
        """Validate BotResponse fields.

        Raises:
            ValueError: If validation fails
        """
        # Answer text length (Discord limit is 2000 chars per message)
        if len(self.answer_text) > 4000:
            raise ValueError("answer_text exceeds 4000 character limit")

        # Confidence score range
        if not 0 <= self.confidence_score <= 1:
            raise ValueError("confidence_score must be between 0 and 1")

        # RAG score range
        if not 0 <= self.rag_score <= 1:
            raise ValueError("rag_score must be between 0 and 1")

        # At least one citation required
        if not self.citations:
            raise ValueError("citations list cannot be empty")

        # Validate each citation
        for citation in self.citations:
            citation.validate()

        # LLM model validation (basic check for non-empty string)
        if not self.llm_model or not self.llm_model.strip():
            raise ValueError("llm_model cannot be empty")

    def should_send(self, confidence_threshold: float = 0.7) -> bool:
        """Check if response meets validation criteria (FR-013).

        Args:
            confidence_threshold: Minimum LLM confidence required

        Returns:
            True if response passes combined validation
        """
        # Combined validation: LLM confidence AND RAG score
        llm_valid = self.confidence_score >= confidence_threshold
        rag_valid = self.rag_score >= 0.6

        return llm_valid and rag_valid

    def split_for_discord(self) -> list[str]:
        """Split answer into Discord-compatible message chunks.

        Discord has a 2000 character limit per message.

        Returns:
            List of message chunks
        """
        if len(self.answer_text) <= 2000:
            return [self.answer_text]

        # Split at sentence boundaries
        sentences = self.answer_text.split(". ")
        chunks = []
        current_chunk = ""

        for sentence in sentences:
            # Add period back except for last sentence
            sentence_with_period = (
                sentence + "." if not sentence.endswith(".") else sentence
            )

            if len(current_chunk) + len(sentence_with_period) <= 1900:
                current_chunk += sentence_with_period + " "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence_with_period + " "

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    @classmethod
    def create(
        cls,
        query_id: UUID,
        answer_text: str,
        citations: list[Citation],
        confidence_score: float,
        rag_score: float,
        llm_model: LLMModel,
        token_count: int,
        latency_ms: int,
        confidence_threshold: float = 0.7,
        structured_data: Optional["StructuredLLMResponse"] = None,
    ) -> "BotResponse":
        """Create BotResponse with validation.

        Args:
            query_id: Reference to UserQuery
            answer_text: Generated answer (JSON string if structured, markdown if not)
            citations: Source rule references
            confidence_score: LLM confidence (0-1)
            rag_score: RAG avg relevance (0-1)
            llm_model: LLM model used for generation (e.g., "gpt-4.1", "claude-sonnet-4-5-20250929")
            token_count: Total tokens used
            latency_ms: Response time in milliseconds
            confidence_threshold: Minimum LLM confidence for validation
            structured_data: Parsed structured response (optional)

        Returns:
            BotResponse instance
        """
        # Compute combined validation
        validation_passed = (
            confidence_score >= confidence_threshold and rag_score >= 0.6
        )

        return cls(
            response_id=uuid4(),
            query_id=query_id,
            answer_text=answer_text,
            citations=citations,
            confidence_score=confidence_score,
            rag_score=rag_score,
            validation_passed=validation_passed,
            llm_model=llm_model,
            token_count=token_count,
            latency_ms=latency_ms,
            timestamp=datetime.now(UTC),
            structured_data=structured_data,
        )
