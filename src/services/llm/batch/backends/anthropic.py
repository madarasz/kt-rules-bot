"""Anthropic Messages Batches backend."""

from src.lib.logging import get_logger

from ._util import error_text

logger = get_logger(__name__)


class AnthropicBatchBackend:
    """Anthropic Messages Batches."""

    name = "anthropic"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from anthropic import Anthropic

            self._client = Anthropic(
                api_key=self.api_key,
                default_headers={
                    "anthropic-beta": "structured-outputs-2025-11-13"
                },
            )
        return self._client

    def submit(self, lines: list[dict], label: str = "quality-test") -> str:  # noqa: ARG002 - no name field in this API
        # lines are {custom_id, params}; the SDK accepts plain dicts as requests.
        batch = self.client.messages.batches.create(requests=lines)
        logger.info(f"Submitted Anthropic batch {batch.id} ({len(lines)} requests)")
        return batch.id

    def poll(self, batch_id: str) -> str:
        status = self.client.messages.batches.retrieve(batch_id).processing_status
        return "ended" if status == "ended" else "in_progress"

    def fetch(self, batch_id: str) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for item in self.client.messages.batches.results(batch_id):
            result = item.result
            entry: dict = {
                "custom_id": item.custom_id,
                "result_type": result.type,
                "message": getattr(result, "message", None),
            }
            # errored/canceled/expired items carry no message; surface the error
            # detail (present on "errored", absent on canceled/expired) so the
            # collect loop can classify transient vs permanent.
            if result.type != "succeeded":
                entry["error"] = (
                    error_text(getattr(result, "error", None))
                    or f"result_type={result.type}"
                )
            out[item.custom_id] = entry
        return out
