"""Batch-item error classification and extraction.

The Batch APIs report per-item failures with wildly different shapes (Anthropic
`result_type`, OpenAI/Mistral JSONL `error` objects, Grok/Gemini missing
responses). This module normalizes them to two questions the collect loop needs
to answer:

- `extract_item_error(item)` — is this normalized fetch item a failure, and if so
  what human-readable text describes it? (`None` == looks successful.)
- `classify_batch_error(text)` — is that failure worth re-requesting?

Classification is deliberately a lowercased substring match (consistent with the
adapters' own error handling) rather than SDK-native exception typing, because
batch results arrive as plain serialized dicts, not raised exceptions.
"""

# Permanent markers are checked FIRST so that a substring like "request" inside an
# "invalid_request_error" can't be mis-matched by a transient rule. A permanent
# error will not be fixed by re-requesting the same input.
_PERMANENT_MARKERS = (
    "authentication",
    "invalid_api_key",
    "invalid api key",
    "unauthorized",
    "401",
    "permission",
    "forbidden",
    "403",
    "invalid_request",
    "invalid request",
    "malformed",
    "schema",
    "unprocessable",
    "content_filter",
    "content filter",
    "content_policy",
    "content policy",
    "blocked",
    "safety",
    "recitation",
    "refusal",
    "not_found",
    "not found",
    "404",
    "canceled",
    "cancelled",
)

# Transient markers: the request itself is fine, the failure is a temporary
# provider-side condition (or a fixable account condition like credits) that a
# later re-request can succeed through.
_TRANSIENT_MARKERS = (
    "rate limit",
    "rate_limit",
    "ratelimit",
    "429",
    "too many requests",
    "overloaded",
    "529",
    "503",
    "500",
    "502",
    "service unavailable",
    "unavailable",
    "server_error",
    "server error",
    "api_error",
    "internal",
    "timeout",
    "timed out",
    "expired",
    "connection",
    "insufficient credits",
    "insufficient_credits",
    "insufficient_quota",
    "insufficient quota",
    "quota",
    "billing",
    "payment",
)

CLASS_TRANSIENT = "transient"
CLASS_PERMANENT = "permanent"


def classify_batch_error(text: str | None) -> tuple[str, str]:
    """Classify a batch-item error string as transient or permanent.

    Returns (error_class, reason) where error_class is CLASS_TRANSIENT or
    CLASS_PERMANENT and reason is the marker that matched (or "unclassified").
    Permanent markers are matched before transient ones. An unrecognized error
    defaults to transient so the bounded retry cap gives it a chance rather than
    dropping a possibly-recoverable item.
    """
    haystack = (text or "").lower()
    for marker in _PERMANENT_MARKERS:
        if marker in haystack:
            return CLASS_PERMANENT, marker
    for marker in _TRANSIENT_MARKERS:
        if marker in haystack:
            return CLASS_TRANSIENT, marker
    return CLASS_TRANSIENT, "unclassified"


def extract_item_error(item: dict) -> str | None:
    """Return a human-readable error string for a failed batch item, else None.

    Reads the backend-surfaced `error` field first (backends attach it for failed
    items), then falls back to the success signals of each normalized item shape:
    OpenAI/Mistral (`status_code`/`body`), Anthropic (`result_type`), and
    Grok/Gemini (`response`).
    """
    if not isinstance(item, dict):
        return None

    err = item.get("error")
    if err:
        return err if isinstance(err, str) else str(err)

    # OpenAI-compatible / Mistral: a non-200 status or a missing body is a failure.
    if "status_code" in item or "body" in item:
        status_code = item.get("status_code")
        if status_code not in (200, None):
            return f"status {status_code}"
        if item.get("body") is None and status_code is not None:
            return f"status {status_code} (no response body)"

    # Anthropic: result_type is succeeded/errored/canceled/expired.
    result_type = item.get("result_type")
    if result_type is not None and result_type != "succeeded":
        return f"result_type={result_type}"

    # Grok / Gemini: a None response is a failed item.
    if "response" in item and item.get("response") is None:
        return "no response"

    return None
