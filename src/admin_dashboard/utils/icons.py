"""Icon utilities for the admin dashboard."""


def bool_to_icon(value: bool) -> str:
    """Convert boolean value to icon.

    Args:
        value: Boolean value to convert

    Returns:
        Check mark for True, X mark for False
    """
    return "✅" if value else "❌"


def get_quote_validation_icon(
    quote_validation_score: float | None,
    _quote_valid_count: int | None = None,
    _quote_total_count: int | None = None,
) -> str:
    """Get icon for quote validation score.

    Args:
        quote_validation_score: Validation score (0-1) or None
        _quote_valid_count: Number of valid quotes (unused, for future use)
        _quote_total_count: Total number of quotes (unused, for future use)

    Returns:
        Icon string representing the validation status
    """
    if quote_validation_score is None:
        return "-"

    if quote_validation_score >= 0.95:
        return "✅"
    elif quote_validation_score >= 0.7:
        return "⚠️"
    else:
        return "❌"


def get_chunk_relevance_icon(relevance: int | None) -> str:
    """Get icon for chunk relevance status.

    Args:
        relevance: 1 for relevant, 0 for not relevant, None for not reviewed

    Returns:
        Icon representing relevance status
    """
    if relevance == 1:
        return "✅"
    elif relevance == 0:
        return "❌"
    else:
        return "⍰"
