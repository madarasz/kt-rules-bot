"""Gemini batch backend (google-genai inline requests, no file upload)."""

from src.lib.logging import get_logger

from ._util import error_text

logger = get_logger(__name__)


def _genai_to_dict(resp) -> dict:
    """Normalize a google-genai GenerateContentResponse into the dict shape
    GeminiAdapter.parse_batch_result reads (candidates/usage_metadata/model_version)."""
    if resp is None:
        return {"candidates": []}
    if hasattr(resp, "model_dump"):
        try:
            return resp.model_dump()
        except Exception:  # pragma: no cover - defensive
            pass
    return resp  # already a dict


class GeminiBatchBackend:
    """Gemini batch via google-genai inline requests (no file upload)."""

    name = "google"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def submit(self, lines: list[dict]) -> str:
        # lines: [{custom_id, model, request:{contents, config}, _gemini_sentences}]
        # google-genai inline batch validates each src item as an InlinedRequest
        # (fields: model/contents/metadata/config) — NOT the file-JSONL
        # {key, request} shape. The custom_id rides out-of-band in metadata["key"]
        # and is echoed back on each InlinedResponse (see fetch()).
        model = lines[0]["model"]
        src = [
            {
                "contents": x["request"]["contents"],
                "config": x["request"]["config"],
                "metadata": {"key": x["custom_id"]},
            }
            for x in lines
        ]
        job = self.client.batches.create(model=model, src=src)
        logger.info(f"Submitted Gemini batch {job.name} ({len(lines)} requests)")
        return job.name

    def poll(self, batch_id: str) -> str:
        state = self.client.batches.get(name=batch_id).state.name
        if state == "JOB_STATE_SUCCEEDED":
            return "ended"
        if state == "JOB_STATE_EXPIRED":
            return "expired"
        if state in ("JOB_STATE_FAILED", "JOB_STATE_CANCELLED"):
            return "failed"
        return "in_progress"

    def fetch(self, batch_id: str) -> dict[str, dict]:
        job = self.client.batches.get(name=batch_id)
        out: dict[str, dict] = {}
        # InlinedResponse echoes the request metadata (google-genai >= 2.x), so we
        # correlate by metadata["key"]. Fail loud if it's ever absent rather than
        # risk silently mis-correlating a response to the wrong custom_id.
        dest = getattr(job, "dest", None)
        responses = dest.inlined_responses if dest else []
        for idx, item in enumerate(responses):
            meta = getattr(item, "metadata", None) or {}
            key = meta.get("key")
            if key is None:
                raise RuntimeError(
                    f"Gemini batch {batch_id} response #{idx} has no metadata['key']; "
                    f"cannot correlate to a custom_id (google-genai too old?)"
                )
            resp = getattr(item, "response", None)
            err = getattr(item, "error", None)
            entry: dict = {"custom_id": key, "response": _genai_to_dict(resp)}
            if err is not None or resp is None:
                entry["error"] = error_text(err) or "no response"
            out[key] = entry
        return out
