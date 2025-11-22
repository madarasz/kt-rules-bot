"""Utility functions for team filtering.

This module provides shared helper functions used across different matching strategies.
"""

from typing import Any

from .config import COMMON_ROLE_WORDS, STOP_WORDS


def filter_stop_words(text: str) -> list[str]:
    """Remove stop words from text and return list of meaningful words.

    Args:
        text: Text string to filter (should be lowercased)

    Returns:
        List of words with stop words removed
    """
    return [word for word in text.split() if word not in STOP_WORDS]


def words_adjacent_in_text(words: list[str], text: str) -> bool:
    """Check if words appear adjacent to each other in text.

    Args:
        words: List of words to check for adjacency
        text: Text string (lowercased)

    Returns:
        True if all words appear consecutively in text
    """
    if len(words) == 0:
        return False
    if len(words) == 1:
        return words[0] in text

    # Build the phrase to search for
    phrase = " ".join(words)
    return phrase in text


def has_common_role_word(words: list[str]) -> bool:
    """Check if word list contains any common role words.

    Args:
        words: List of words to check (should be lowercased)

    Returns:
        True if any word is a common role word
    """
    return any(word in COMMON_ROLE_WORDS for word in words)


def extract_all_items(items: list[Any]) -> list[str]:
    """Extract all text items from a potentially nested list structure.

    Handles YAML structures where items can be:
    - Simple strings: "OPERATIVE NAME"
    - Nested dictionaries: {"OPERATIVE NAME": ["ability1", "ability2"]}

    Args:
        items: List that may contain strings or dicts with nested children

    Returns:
        Flat list of all string items (titles) from the structure
    """
    result = []
    for item in items:
        if isinstance(item, str):
            # Simple string item
            result.append(item)
        elif isinstance(item, dict):
            # Dictionary item with nested children (e.g., {"OPERATIVE": ["ability1", "ability2"]})
            for title, children in item.items():
                # Add the parent title
                result.append(title)
                # Recursively extract children
                if isinstance(children, list):
                    result.extend(extract_all_items(children))
    return result
