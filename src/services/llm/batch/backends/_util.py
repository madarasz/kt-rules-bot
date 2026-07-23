"""Shared helpers for batch backend implementations."""


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
