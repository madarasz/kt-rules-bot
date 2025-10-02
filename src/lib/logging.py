"""Structured logging with correlation IDs and PII redaction.

Based on specs/001-we-are-building/tasks.md T027
Constitution Principle V: Observable and Debuggable
"""

import structlog
import logging
import sys
import re
from typing import Any, Dict
from uuid import uuid4


# PII patterns to redact
PII_PATTERNS = [
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[EMAIL]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    (re.compile(r"\b\d{16}\b"), "[CARD]"),
    (re.compile(r"discord_user_id:\s*\d+"), "discord_user_id: [REDACTED]"),
    (re.compile(r"user_id:\s*\d+"), "user_id: [REDACTED]"),
]


def redact_pii(message: str) -> str:
    """Redact PII from log message.

    Args:
        message: Log message

    Returns:
        Message with PII redacted
    """
    for pattern, replacement in PII_PATTERNS:
        message = pattern.sub(replacement, message)
    return message


def add_correlation_id(
    logger: Any, method_name: str, event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """Add correlation ID to log events.

    Args:
        logger: Logger instance
        method_name: Method name
        event_dict: Event dictionary

    Returns:
        Updated event dictionary
    """
    if "correlation_id" not in event_dict:
        event_dict["correlation_id"] = str(uuid4())
    return event_dict


def redact_pii_processor(
    logger: Any, method_name: str, event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """Redact PII from log events.

    Args:
        logger: Logger instance
        method_name: Method name
        event_dict: Event dictionary

    Returns:
        Updated event dictionary
    """
    # Redact PII from event message
    if "event" in event_dict:
        event_dict["event"] = redact_pii(event_dict["event"])

    # Redact PII from other string fields
    for key, value in event_dict.items():
        if isinstance(value, str):
            event_dict[key] = redact_pii(value)

    return event_dict


def setup_logging(log_level: str = "INFO") -> None:
    """Setup structured logging with correlation IDs and PII redaction.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            add_correlation_id,
            redact_pii_processor,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.getLevelName(log_level),
    )


def get_logger(name: str) -> Any:
    """Get a structured logger instance.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Structured logger
    """
    return structlog.get_logger(name)


def set_correlation_id(correlation_id: str) -> None:
    """Set correlation ID for current context.

    Args:
        correlation_id: Correlation ID
    """
    structlog.contextvars.bind_contextvars(correlation_id=correlation_id)


def clear_correlation_id() -> None:
    """Clear correlation ID from current context."""
    structlog.contextvars.clear_contextvars()
