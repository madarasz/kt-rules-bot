"""Post-generation quote validator for grounding enforcement.

Validates that quoted rules actually appear in RAG context to prevent hallucination.
Based on docs/future-development/GROUNDING.md Strategy 4.
"""

from dataclasses import dataclass
from difflib import SequenceMatcher

from src.lib.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationResult:
    """Result of quote validation."""

    is_valid: bool
    invalid_quotes: list[dict]  # [{"quote_text": str, "chunk_id": str, "reason": str}]
    validation_score: float  # 0-1, fraction of quotes that are valid
    total_quotes: int
    valid_quotes: int


class QuoteValidator:
    """Validates quotes against RAG context."""

    def __init__(self, similarity_threshold: float = 0.85):
        """Initialize validator.

        Args:
            similarity_threshold: Minimum similarity for fuzzy matching (0-1)
        """
        self.similarity_threshold = similarity_threshold

    def validate(
        self, quotes: list[dict], context_chunks: list[str], chunk_ids: list[str] | None = None
    ) -> ValidationResult:
        """Validate quotes against context chunks.

        Args:
            quotes: List of {"quote_title": str, "quote_text": str, "chunk_id": str} dicts
            context_chunks: Retrieved RAG chunks (text content)
            chunk_ids: Optional list of chunk IDs corresponding to context_chunks

        Returns:
            ValidationResult with validity status
        """
        invalid_quotes = []

        for quote in quotes:
            quote_text = quote.get("quote_text", "").strip()
            quote_chunk_id = quote.get("chunk_id", "")

            if not quote_text:
                # Empty quote - skip validation
                continue

            # Check if quote appears in any chunk (exact or fuzzy match)
            found, matched_chunk_id = self._find_quote_in_chunks(
                quote_text, context_chunks, chunk_ids
            )

            if not found:
                invalid_quotes.append(
                    {
                        "quote_text": quote_text,
                        "quote_title": quote.get("quote_title", ""),
                        "claimed_chunk_id": quote_chunk_id,
                        "reason": "Quote not found in any RAG context chunk",
                    }
                )
                logger.warning(
                    "Quote validation failed",
                    extra={
                        "quote_title": quote.get("quote_title", ""),
                        "quote_preview": quote_text[:100],
                        "claimed_chunk_id": quote_chunk_id,
                    },
                )
            elif quote_chunk_id and matched_chunk_id and quote_chunk_id != matched_chunk_id:
                # Quote found, but chunk_id mismatch
                logger.warning(
                    "Quote chunk_id mismatch",
                    extra={
                        "quote_title": quote.get("quote_title", ""),
                        "claimed_chunk_id": quote_chunk_id,
                        "matched_chunk_id": matched_chunk_id,
                    },
                )

        total_quotes = len(quotes)
        valid_quotes = total_quotes - len(invalid_quotes)
        validation_score = valid_quotes / total_quotes if total_quotes > 0 else 1.0

        logger.info(
            "Quote validation complete",
            extra={
                "total_quotes": total_quotes,
                "valid_quotes": valid_quotes,
                "invalid_quotes": len(invalid_quotes),
                "validation_score": validation_score,
            },
        )

        return ValidationResult(
            is_valid=(len(invalid_quotes) == 0),
            invalid_quotes=invalid_quotes,
            validation_score=validation_score,
            total_quotes=total_quotes,
            valid_quotes=valid_quotes,
        )

    def _find_quote_in_chunks(
        self, quote: str, chunks: list[str], chunk_ids: list[str] | None = None
    ) -> tuple[bool, str | None]:
        """Check if quote appears in any chunk (exact or fuzzy).

        Args:
            quote: Quote text to find
            chunks: Context chunks to search
            chunk_ids: Optional list of chunk IDs (UUIDs)

        Returns:
            Tuple of (found: bool, matched_chunk_id: str | None)
        """
        for i, chunk in enumerate(chunks):
            if self._is_quote_in_chunk(quote, chunk):
                matched_chunk_id = chunk_ids[i][-8:] if chunk_ids and i < len(chunk_ids) else None
                return True, matched_chunk_id

        return False, None

    def _is_quote_in_chunk(self, quote: str, chunk: str) -> bool:
        """Check if quote appears in chunk (exact or fuzzy).

        Args:
            quote: Quote text to find
            chunk: Context chunk to search

        Returns:
            True if quote found in chunk
        """
        # Normalize: lowercase, strip extra whitespace
        quote_norm = " ".join(quote.lower().split())
        chunk_norm = " ".join(chunk.lower().split())

        # Exact match (fast path)
        if quote_norm in chunk_norm:
            return True

        # Fuzzy match (allows for minor LLM formatting differences)
        # Use sliding window to find best match
        quote_len = len(quote_norm)
        if quote_len == 0:
            return False

        best_similarity = 0.0

        # Sliding window with step size for performance
        step_size = max(1, quote_len // 4)
        for i in range(0, max(1, len(chunk_norm) - quote_len + 1), step_size):
            window = chunk_norm[i : i + quote_len]
            similarity = SequenceMatcher(None, quote_norm, window).ratio()
            best_similarity = max(best_similarity, similarity)

            if best_similarity >= self.similarity_threshold:
                return True

        return False
