"""Security logging for Discord events."""

from src.lib.logging import get_logger

security_logger = get_logger("security")


def log_injection_attempt(user_id: str, message: str) -> None:
    """Log potential injection attempt.

    Args:
        user_id: Hashed user ID
        message: Message content that triggered detection
    """
    security_logger.warning(
        "Injection attempt detected",
        extra={
            "event_type": "injection_attempt",
            "user_id": user_id[:16],  # Partial hash for privacy
            "message_length": len(message),
            "patterns_detected": _detect_patterns(message),
        },
    )


def log_rate_limit_violation(user_id: str, provider: str) -> None:
    """Log rate limit hit.

    Args:
        user_id: Hashed user ID
        provider: LLM provider name
    """
    security_logger.info(
        "Rate limit reached",
        extra={
            "event_type": "rate_limit",
            "user_id": user_id[:16],
            "provider": provider,
        },
    )


def log_permission_violation(user_id: str, action: str) -> None:
    """Log permission violation attempt.

    Args:
        user_id: Hashed user ID
        action: Action that was attempted
    """
    security_logger.warning(
        "Permission violation",
        extra={
            "event_type": "permission_violation",
            "user_id": user_id[:16],
            "action": action,
        },
    )


def log_unusual_query_pattern(user_id: str, pattern_type: str, details: str) -> None:
    """Log unusual query patterns.

    Args:
        user_id: Hashed user ID
        pattern_type: Type of unusual pattern detected
        details: Additional details
    """
    security_logger.info(
        "Unusual query pattern detected",
        extra={
            "event_type": "unusual_pattern",
            "user_id": user_id[:16],
            "pattern_type": pattern_type,
            "details": details,
        },
    )


def _detect_patterns(message: str) -> list[str]:
    """Detect injection patterns in message.

    Args:
        message: Message content

    Returns:
        List of detected pattern types
    """
    patterns = []

    # Check for common prompt injection patterns
    injection_keywords = [
        "ignore previous",
        "ignore all",
        "system:",
        "<script>",
        "DROP TABLE",
        "SELECT * FROM",
    ]

    for keyword in injection_keywords:
        if keyword.lower() in message.lower():
            patterns.append(keyword)

    return patterns
