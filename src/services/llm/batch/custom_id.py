"""Provider-safe custom_id sanitization.

Providers constrain the custom_id that maps a batch result back to its request.
Anthropic is the strictest: ^[a-zA-Z0-9_-]{1,64}$ (no dots, <=64 chars) — so model
names like "claude-4.6-sonnet" and long test ids or file paths must be sanitized
and capped. Callers build a descriptive raw string and pass it through here; the
rule lives in exactly one place.
"""

import hashlib
import re

CUSTOM_ID_MAX = 64
_DISALLOWED = re.compile(r"[^a-zA-Z0-9_-]")


def safe_custom_id(raw: str) -> str:
    """Return a deterministic, provider-safe custom_id for an arbitrary raw string.

    Disallowed characters become '-'. Over-long ids are truncated with a hash
    suffix derived from the *full* raw string, so uniqueness survives truncation.
    """
    safe = _DISALLOWED.sub("-", raw)
    if len(safe) <= CUSTOM_ID_MAX:
        return safe
    digest = hashlib.sha1(raw.encode()).hexdigest()[:10]
    return f"{safe[: CUSTOM_ID_MAX - 11]}-{digest}"
