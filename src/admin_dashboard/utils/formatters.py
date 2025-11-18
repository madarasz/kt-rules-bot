"""Formatting utilities for the admin dashboard."""

from datetime import datetime

import pandas as pd


def format_timestamp(timestamp: str, format_str: str = "%Y-%m-%d %H:%M") -> str:
    """Format timestamp string for display.

    Args:
        timestamp: ISO format timestamp string
        format_str: Format string for output

    Returns:
        Formatted timestamp string
    """
    return pd.to_datetime(timestamp).strftime(format_str)


def truncate_text(text: str, max_length: int = 80, suffix: str = "...") -> str:
    """Truncate text to maximum length with suffix.

    Args:
        text: Text to truncate
        max_length: Maximum length before truncation
        suffix: Suffix to add if truncated

    Returns:
        Truncated text with suffix if needed
    """
    if len(text) <= max_length:
        return text
    return text[:max_length] + suffix


def format_feedback(upvotes: int, downvotes: int) -> str:
    """Format upvote/downvote counts for display.

    Args:
        upvotes: Number of upvotes
        downvotes: Number of downvotes

    Returns:
        Formatted feedback string
    """
    return f"{upvotes}👍 / {downvotes}👎"


def format_confidence_score(score: float | None) -> str:
    """Format confidence score for display.

    Args:
        score: Confidence score value or None

    Returns:
        Formatted score or "N/A"
    """
    if score is None:
        return "N/A"
    return f"{score:.2f}"


def format_helpful_rate(upvotes: int, downvotes: int) -> tuple[float, str]:
    """Calculate and format helpful rate.

    Args:
        upvotes: Number of upvotes
        downvotes: Number of downvotes

    Returns:
        Tuple of (rate as float, formatted string)
    """
    total_votes = upvotes + downvotes
    rate = upvotes / total_votes if total_votes > 0 else 0
    return rate, f"⬆️ {upvotes} / ⬇️ {downvotes} ({rate:.0%} helpful)"


def generate_test_id(query_text: str, word_count: int = 3) -> str:
    """Generate test ID from first N words of query.

    Args:
        query_text: Query text to generate ID from
        word_count: Number of words to use

    Returns:
        Test ID string
    """
    words = query_text.lower().split()[:word_count]
    return "-".join(word.strip(".,!?;:") for word in words)
