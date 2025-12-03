"""Post-generation quote validator for grounding enforcement.

Validates that quoted rules actually appear in RAG context to prevent hallucination.
Based on docs/future-development/GROUNDING.md Strategy 4.
"""

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from src.lib.constants import QUOTE_SIMILARITY_THRESHOLD
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
    quote_scores: list[dict] = field(default_factory=list)  # Per-quote details with similarity scores
    # Each dict: {"quote_text": str, "quote_title": str, "similarity": float,
    #             "matched_chunk_text": str, "chunk_id": str, "is_valid": bool}


class QuoteValidator:
    """Validates quotes against RAG context."""

    def __init__(self, similarity_threshold: float | None = None):
        """Initialize validator.

        Args:
            similarity_threshold: Minimum similarity for fuzzy matching (0-1).
                                 If None, uses QUOTE_SIMILARITY_THRESHOLD from constants.
        """
        self.similarity_threshold = similarity_threshold or QUOTE_SIMILARITY_THRESHOLD

    def validate(
        self, quotes: list[dict], context_chunks: list[str], chunk_ids: list[str] | None = None
    ) -> ValidationResult:
        """Validate quotes against context chunks.

        Args:
            quotes: List of {"quote_title": str, "quote_text": str, "chunk_id": str} dicts
            context_chunks: Retrieved RAG chunks (text content)
            chunk_ids: Optional list of chunk IDs corresponding to context_chunks

        Returns:
            ValidationResult with validity status and per-quote details
        """
        invalid_quotes = []
        quote_scores = []

        for quote in quotes:
            quote_text = quote.get("quote_text", "").strip()
            quote_title = quote.get("quote_title", "")
            quote_chunk_id = quote.get("chunk_id", "")

            if not quote_text:
                # Empty quote - skip validation
                continue

            # Check if quote appears in any chunk (exact or fuzzy match)
            found, matched_chunk_id, similarity, matched_text = self._find_quote_in_chunks(
                quote_text, context_chunks, chunk_ids
            )

            # Store per-quote details
            quote_scores.append(
                {
                    "quote_text": quote_text,
                    "quote_title": quote_title,
                    "similarity": similarity,
                    "matched_chunk_text": matched_text,
                    "chunk_id": matched_chunk_id or "",
                    "is_valid": found,
                }
            )

            if not found:
                invalid_quotes.append(
                    {
                        "quote_text": quote_text,
                        "quote_title": quote_title,
                        "claimed_chunk_id": quote_chunk_id,
                        "reason": "Quote not found in any RAG context chunk",
                        "similarity": similarity,
                    }
                )
                logger.warning(
                    "Quote validation failed",
                    extra={
                        "quote_title": quote_title,
                        "quote_preview": quote_text[:100],
                        "claimed_chunk_id": quote_chunk_id,
                        "similarity": similarity,
                    },
                )
            elif quote_chunk_id and matched_chunk_id and quote_chunk_id != matched_chunk_id:
                # Quote found, but chunk_id mismatch
                logger.warning(
                    "Quote chunk_id mismatch",
                    extra={
                        "quote_title": quote_title,
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
            quote_scores=quote_scores,
        )

    def _find_quote_in_chunks(
        self, quote: str, chunks: list[str], chunk_ids: list[str] | None = None
    ) -> tuple[bool, str | None, float, str]:
        """Check if quote appears in any chunk (exact or fuzzy).

        Args:
            quote: Quote text to find
            chunks: Context chunks to search
            chunk_ids: Optional list of chunk IDs (UUIDs)

        Returns:
            Tuple of (found, matched_chunk_id, best_similarity, matched_text):
            - found: True if quote found with similarity >= threshold
            - matched_chunk_id: Last 8 chars of chunk UUID (or None)
            - best_similarity: Float 0-1, best similarity across all chunks
            - matched_text: Best matching text from the best chunk
        """
        best_similarity_overall = 0.0
        best_matched_text = ""
        best_chunk_id = None
        found = False

        for i, chunk in enumerate(chunks):
            is_valid, similarity, matched_text = self._is_quote_in_chunk(quote, chunk)
            if similarity > best_similarity_overall:
                best_similarity_overall = similarity
                best_matched_text = matched_text
                best_chunk_id = chunk_ids[i][-8:] if chunk_ids and i < len(chunk_ids) else None
                if is_valid:
                    found = True

        return found, best_chunk_id, best_similarity_overall, best_matched_text

    def _is_quote_in_chunk(self, quote: str, chunk: str) -> tuple[bool, float, str]:
        """Check if quote appears in chunk (exact or fuzzy).

        Args:
            quote: Quote text to find
            chunk: Context chunk to search

        Returns:
            Tuple of (is_valid, best_similarity, matched_text):
            - is_valid: True if similarity >= threshold
            - best_similarity: Float 0-1, best matching score
            - matched_text: Best matching window from chunk (original text before normalization)
        """
        # Normalize: strip markdown, lowercase, strip extra whitespace
        quote_norm = self._normalize_text(quote)
        chunk_norm = self._normalize_text(chunk)

        # Exact match (fast path)
        if quote_norm in chunk_norm:
            # Find the matching portion in original chunk by searching for a substring
            # that normalizes to quote_norm
            matched_text = self._find_original_text_match(quote_norm, chunk)
            return True, 1.0, matched_text

        # Fuzzy match (allows for minor LLM formatting differences)
        # Use sliding window to find best match
        quote_len = len(quote_norm)
        if quote_len == 0:
            return False, 0.0, ""

        best_similarity = 0.0
        best_matched_text = ""

        # Sliding window in ORIGINAL chunk to find best match
        # We need to try different window sizes since normalization changes length
        # Use a range around the quote length
        min_window_len = max(1, quote_len)
        max_window_len = quote_len * 3  # Allow for markdown/whitespace expansion
        step_size = max(1, len(chunk) // 20)  # Coarser step for performance

        for start_pos in range(0, len(chunk), step_size):
            # Try windows of varying lengths around the expected size
            for window_len in [min_window_len, quote_len * 2, max_window_len]:
                end_pos = min(start_pos + window_len, len(chunk))
                if end_pos <= start_pos:
                    continue

                window_original = chunk[start_pos:end_pos]
                window_norm = self._normalize_text(window_original)

                # rapidfuzz returns 0-100, normalize to 0-1
                similarity = fuzz.ratio(quote_norm, window_norm) / 100.0
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_matched_text = window_original

        # If no good match found, fall back to chunk preview
        if not best_matched_text:
            best_matched_text = chunk[:500]

        is_valid = best_similarity >= self.similarity_threshold

        return is_valid, best_similarity, best_matched_text

    def _find_original_text_match(self, quote_norm: str, chunk: str) -> str:
        """Find the original text in chunk that normalizes to quote_norm.

        Args:
            quote_norm: Normalized quote text to find
            chunk: Original chunk text to search

        Returns:
            Original text from chunk that normalizes to quote_norm, or chunk preview if not found
        """
        quote_norm_len = len(quote_norm)
        if quote_norm_len == 0:
            return chunk[:500]

        # Try windows of varying lengths (normalization can significantly reduce length)
        # Start with small windows and expand
        min_window_len = quote_norm_len
        max_window_len = quote_norm_len * 3  # Account for markdown, whitespace, etc.

        for start_pos in range(len(chunk)):
            # Try different window lengths for this start position
            for window_len in range(min_window_len, min(max_window_len, len(chunk) - start_pos + 1)):
                candidate = chunk[start_pos : start_pos + window_len]
                candidate_norm = self._normalize_text(candidate)

                # Check for exact match
                if candidate_norm == quote_norm:
                    # Add some context after the match for better readability
                    context_end = min(start_pos + window_len + 100, len(chunk))
                    return chunk[start_pos:context_end]

                # Early termination: if normalized candidate is much longer than quote_norm,
                # no need to try even longer windows
                if len(candidate_norm) > quote_norm_len * 1.5:
                    break

        # Fallback: return chunk preview if no exact match found
        # (This shouldn't happen if quote_norm is actually in chunk_norm, but safety net)
        return chunk[:500]

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize text by stripping markdown and whitespace.

        Args:
            text: Text to normalize

        Returns:
            Normalized text (lowercase, no markdown, normalized whitespace)
        """
        # Strip markdown formatting (bold, italic, etc.)
        # Remove **bold** and __bold__
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"__([^_]+)__", r"\1", text)

        # Remove *italic* and _italic_
        text = re.sub(r"\*([^*]+)\*", r"\1", text)
        text = re.sub(r"_([^_]+)_", r"\1", text)

        # Remove inline code `code`
        text = re.sub(r"`([^`]+)`", r"\1", text)

        # Remove ellipsis characters (both Unicode and three-dot variants)
        text = text.replace("…", "")  # Unicode ellipsis U+2026
        text = text.replace("...", "")  # Three-dot ellipsis

        # Lowercase and normalize whitespace
        return " ".join(text.lower().split())
