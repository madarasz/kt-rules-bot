"""Input validation and sanitization.

Discord message sanitization, prompt injection detection, markdown validation.
Based on specs/001-we-are-building/tasks.md T028
Constitution Principle III: Security by Design
"""

import re

# Prompt injection patterns
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+previous\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+all\s+prior", re.IGNORECASE),
    re.compile(r"forget\s+everything", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\s*script", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(r"on\w+\s*=", re.IGNORECASE),  # Event handlers
]


# Markdown injection patterns
MARKDOWN_INJECTION_PATTERNS = [
    re.compile(r"!\[.*\]\(javascript:", re.IGNORECASE),
    re.compile(r"\[.*\]\(data:", re.IGNORECASE),
    re.compile(r"```.*?<script", re.IGNORECASE | re.DOTALL),
]


def sanitize_discord_message(message: str) -> tuple[str, bool]:
    """Sanitize Discord message and detect prompt injection.

    Args:
        message: Raw Discord message text

    Returns:
        Tuple of (sanitized_text, injection_detected)
    """
    # Trim whitespace
    sanitized = message.strip()

    # Detect prompt injection
    injection_detected = False
    for pattern in INJECTION_PATTERNS:
        if pattern.search(sanitized):
            injection_detected = True
            # Remove the injection pattern
            sanitized = pattern.sub("[BLOCKED]", sanitized)

    # Remove excessive newlines
    sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)

    # Limit length (Discord max is 2000, but we're more conservative)
    if len(sanitized) > 2000:
        sanitized = sanitized[:2000]

    return sanitized, injection_detected


def validate_markdown_content(content: str) -> tuple[bool, str]:
    """Validate markdown content for security issues.

    Args:
        content: Markdown content

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check for markdown injection patterns
    for pattern in MARKDOWN_INJECTION_PATTERNS:
        if pattern.search(content):
            return False, f"Markdown contains injection pattern: {pattern.pattern}"

    # Check for executable code blocks
    if "```python" in content or "```bash" in content or "```sh" in content:
        return False, "Markdown contains executable code blocks"

    # Check for inline scripts
    if "<script" in content.lower():
        return False, "Markdown contains script tags"

    return True, ""


def extract_mentions(message: str) -> list[str]:
    """Extract Discord mentions from message.

    Args:
        message: Discord message text

    Returns:
        List of user IDs mentioned
    """
    # Discord mention format: <@USER_ID> or <@!USER_ID>
    pattern = re.compile(r"<@!?(\d+)>")
    matches = pattern.findall(message)
    return matches


def sanitize_for_llm(text: str) -> str:
    """Sanitize text before sending to LLM.

    Args:
        text: Text to sanitize

    Returns:
        Sanitized text
    """
    # Remove any control characters
    sanitized = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", text)

    # Remove excessive whitespace
    sanitized = re.sub(r"\s+", " ", sanitized)

    # Trim to reasonable length (16000 chars for context window)
    if len(sanitized) > 16000:
        sanitized = sanitized[:16000]

    return sanitized.strip()


def validate_citation_quote(quote: str) -> bool:
    """Validate citation quote length.

    Args:
        quote: Citation quote text

    Returns:
        True if valid
    """
    # Must be non-empty and <= 200 chars
    return 0 < len(quote) <= 200


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe filesystem operations.

    Args:
        filename: Filename to sanitize

    Returns:
        Sanitized filename
    """
    # Remove path traversal attempts
    filename = filename.replace("..", "")
    filename = filename.replace("/", "")
    filename = filename.replace("\\", "")

    # Only allow alphanumeric, dash, underscore, and dot
    filename = re.sub(r"[^a-zA-Z0-9._-]", "", filename)

    # Ensure .md extension
    if not filename.endswith(".md"):
        filename += ".md"

    return filename


def detect_pii(text: str) -> tuple[bool, list[str]]:
    """Detect PII in text.

    Args:
        text: Text to check

    Returns:
        Tuple of (pii_found, pii_types_detected)
    """
    pii_types = []

    # Email detection
    if re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", text):
        pii_types.append("email")

    # Phone number detection
    if re.search(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", text):
        pii_types.append("phone")

    # Credit card detection
    if re.search(r"\b\d{16}\b", text):
        pii_types.append("credit_card")

    # SSN detection
    if re.search(r"\b\d{3}-\d{2}-\d{4}\b", text):
        pii_types.append("ssn")

    return len(pii_types) > 0, pii_types
