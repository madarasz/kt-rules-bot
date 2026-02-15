"""Text processing utilities for RAG evaluation.

Provides centralized functions for ground truth matching and text normalization
to ensure consistency across evaluators and test runners.
"""

from src.lib.constants import QUOTE_MERGE_SEPARATOR


def normalize_text_for_matching(text: str) -> str:
    """Normalize text for ground truth matching.

    Applies consistent normalization used across all RAG evaluation code:
    - Normalize whitespace (replace newlines/tabs/multiple spaces with single space)
    - Strip leading/trailing whitespace
    - Convert to lowercase
    - Remove markdown asterisks (bold/italic markers)
    - Remove ellipsis characters (… and ...)

    Args:
        text: Text to normalize

    Returns:
        Normalized text string
    """
    # Normalize whitespace: replace newlines, tabs, multiple spaces with single space
    normalized = " ".join(text.split())
    return normalized.lower().replace("*", "").replace(QUOTE_MERGE_SEPARATOR, "").replace("…", "").replace("...", "")


def ground_truth_matches_text(ground_truth: str, text: str) -> bool:
    """Check if ground truth substring matches retrieved text.

    Uses consistent normalization for substring matching:
    - Both strings are normalized (whitespace, lowercase, remove asterisks)
    - Ground truth must be contained in text (substring match)

    Args:
        ground_truth: Ground truth context to find (can be substring)
        text: Retrieved text to search in

    Returns:
        True if ground truth is found in text after normalization
    """
    gt_normalized = normalize_text_for_matching(ground_truth)
    text_normalized = normalize_text_for_matching(text)
    return gt_normalized in text_normalized


def find_ground_truth_in_texts(
    ground_truth: str, texts: list[str]
) -> tuple[bool, int | None]:
    """Find ground truth in a list of texts and return its rank.

    Searches through texts (in order) and returns the 1-indexed rank
    where the ground truth is first found.

    Args:
        ground_truth: Ground truth context to find
        texts: List of texts to search through (ordered by relevance)

    Returns:
        Tuple of (found, rank) where:
        - found: True if ground truth was found
        - rank: 1-indexed position where found, or None if not found
    """
    for i, text in enumerate(texts, start=1):
        if ground_truth_matches_text(ground_truth, text):
            return True, i
    return False, None
