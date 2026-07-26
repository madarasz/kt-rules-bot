"""Shared helpers for batch backend implementations."""


def raise_for_status_with_body(response) -> None:
    """httpx raise_for_status(), but with the response body in the message.

    The bare httpx error reports only the status and URL, which hides the one
    thing that says what went wrong (e.g. xAI answers an unsupported batch model
    with `Model grok-4.5 is not supported for batch processing.`). Batch
    submissions are slow and expensive to reproduce, so the body has to survive
    into the traceback.
    """
    if response.status_code < 400:
        return
    try:
        body = response.text[:1000]
    except Exception:  # pragma: no cover - defensive
        body = "<unreadable body>"
    try:
        response.raise_for_status()
    except Exception as exc:
        raise type(exc)(  # type: ignore[misc]
            f"{exc}\nResponse body: {body}",
            request=exc.request,  # type: ignore[attr-defined]
            response=exc.response,  # type: ignore[attr-defined]
        ) from None


def error_text(obj) -> str | None:
    """Best-effort human-readable string for a provider error object.

    Handles plain strings, dicts ({code/type, message}, optionally nested under
    "error"), and pydantic-ish objects (via model_dump). Returns None for a
    falsy/empty object so callers can fall back to a status-based message.
    """
    if not obj:
        return None
    if isinstance(obj, str):
        return obj
    if hasattr(obj, "model_dump"):
        try:
            obj = obj.model_dump()
        except Exception:  # pragma: no cover - defensive
            return str(obj)
    if isinstance(obj, dict):
        if isinstance(obj.get("error"), dict):
            obj = obj["error"]
        msg = obj.get("message")
        code = obj.get("code") or obj.get("type")
        if msg and code:
            return f"{code}: {msg}"
        return msg or code or str(obj)
    return str(obj)
