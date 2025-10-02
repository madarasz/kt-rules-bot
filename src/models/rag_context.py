"""RAGContext model for retrieval results.

Represents retrieved rule sections relevant to a user query.
Based on specs/001-we-are-building/data-model.md
"""

from dataclasses import dataclass
from typing import Dict, Any, List
from uuid import UUID, uuid4


@dataclass
class DocumentChunk:
    """A text segment from a rule document."""

    chunk_id: UUID
    document_id: UUID  # FK to RuleDocument
    text: str  # Complete section from ## or ### header (no overlap)
    header: str  # Section header (e.g., "Movement Phase")
    header_level: int  # 2 for ##, 3 for ###
    metadata: Dict[str, Any]  # source, doc_type, last_update_date, section
    relevance_score: float  # 0-1 cosine similarity
    position_in_doc: int  # Section number for citation

    def validate(self) -> None:
        """Validate DocumentChunk fields.

        Raises:
            ValueError: If validation fails
        """
        # Relevance score range
        if not 0 <= self.relevance_score <= 1:
            raise ValueError("relevance_score must be between 0 and 1")

        # Header level validation
        if self.header_level not in {2, 3}:
            raise ValueError("header_level must be 2 (##) or 3 (###)")

        # Required metadata fields
        required_fields = ["source", "doc_type", "publication_date"]
        for field in required_fields:
            if field not in self.metadata:
                raise ValueError(f"metadata missing required field: {field}")

        # Document type validation
        valid_types = {"core-rules", "faq", "team-rules", "ops"}
        if self.metadata.get("doc_type") not in valid_types:
            raise ValueError(
                f"metadata.doc_type must be one of: {', '.join(valid_types)}"
            )


@dataclass
class RAGContext:
    """Retrieved rule sections relevant to a user query."""

    context_id: UUID
    query_id: UUID  # FK to UserQuery
    document_chunks: List[DocumentChunk]
    relevance_scores: List[float]
    total_chunks: int
    avg_relevance: float
    meets_threshold: bool  # True if avg_relevance >= 0.6

    def validate(self) -> None:
        """Validate RAGContext fields.

        Raises:
            ValueError: If validation fails
        """
        # All relevance scores in valid range
        for score in self.relevance_scores:
            if not 0 <= score <= 1:
                raise ValueError("relevance_scores must be between 0 and 1")

        # Chunks ordered by relevance DESC
        if len(self.document_chunks) > 1:
            for i in range(len(self.document_chunks) - 1):
                if (
                    self.document_chunks[i].relevance_score
                    < self.document_chunks[i + 1].relevance_score
                ):
                    raise ValueError(
                        "document_chunks must be ordered by relevance_score DESC"
                    )

        # Relevance scores match chunks
        if len(self.relevance_scores) != len(self.document_chunks):
            raise ValueError(
                "relevance_scores length must match document_chunks length"
            )

        for i, chunk in enumerate(self.document_chunks):
            if chunk.relevance_score != self.relevance_scores[i]:
                raise ValueError(
                    "relevance_scores must match document_chunks order"
                )

        # Total chunks matches length
        if self.total_chunks != len(self.document_chunks):
            raise ValueError("total_chunks must match document_chunks length")

        # Threshold validation
        expected_meets_threshold = self.avg_relevance >= 0.6
        if self.meets_threshold != expected_meets_threshold:
            raise ValueError(
                f"meets_threshold should be {expected_meets_threshold} "
                f"for avg_relevance={self.avg_relevance}"
            )

    @classmethod
    def from_retrieval(
        cls,
        query_id: UUID,
        chunks: List[DocumentChunk],
        min_relevance: float = 0.6,
    ) -> "RAGContext":
        """Create RAGContext from retrieval results.

        Args:
            query_id: Reference to UserQuery
            chunks: Retrieved document chunks (already sorted by relevance DESC)
            min_relevance: Minimum average relevance threshold

        Returns:
            RAGContext instance
        """
        relevance_scores = [chunk.relevance_score for chunk in chunks]
        avg_relevance = sum(relevance_scores) / len(relevance_scores) if chunks else 0.0

        return cls(
            context_id=uuid4(),
            query_id=query_id,
            document_chunks=chunks,
            relevance_scores=relevance_scores,
            total_chunks=len(chunks),
            avg_relevance=avg_relevance,
            meets_threshold=avg_relevance >= min_relevance,
        )

    @classmethod
    def empty(cls, query_id: UUID) -> "RAGContext":
        """Create empty RAGContext when no relevant chunks found.

        Args:
            query_id: Reference to UserQuery

        Returns:
            Empty RAGContext with meets_threshold=False
        """
        return cls(
            context_id=uuid4(),
            query_id=query_id,
            document_chunks=[],
            relevance_scores=[],
            total_chunks=0,
            avg_relevance=0.0,
            meets_threshold=False,
        )
