"""OpenAI-compatible /v1/batches backend (OpenAI, Kimi, Qwen)."""

import json
from pathlib import Path

from src.lib.logging import get_logger

from ._util import error_text

logger = get_logger(__name__)


class OpenAICompatBatchBackend:
    """OpenAI /v1/batches (JSONL file upload). Parameterized base_url/api_key so
    the same flow can target OpenAI-compatible hosts; base plan wires OpenAI."""

    def __init__(self, api_key: str, base_url: str, name: str):
        self.api_key = api_key
        self.base_url = base_url
        self.name = name
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    def submit(self, lines: list[dict]) -> str:
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as f:
            for line in lines:
                f.write(json.dumps(line) + "\n")
            jsonl_path = Path(f.name)
        try:
            with open(jsonl_path, "rb") as fh:
                uploaded = self.client.files.create(file=fh, purpose="batch")
            batch = self.client.batches.create(
                input_file_id=uploaded.id,
                endpoint="/v1/chat/completions",
                completion_window="24h",
            )
            logger.info(f"Submitted {self.name} batch {batch.id} ({len(lines)} requests)")
            return batch.id
        finally:
            jsonl_path.unlink(missing_ok=True)

    def poll(self, batch_id: str) -> str:
        status = self.client.batches.retrieve(batch_id).status
        if status == "completed":
            return "ended"
        if status == "expired":
            return "expired"
        if status in ("failed", "cancelled", "canceled"):
            return "failed"
        return "in_progress"

    def fetch(self, batch_id: str) -> dict[str, dict]:
        batch = self.client.batches.retrieve(batch_id)
        out: dict[str, dict] = {}
        # Successful items live in the output file (may be absent if all failed).
        output_file_id = getattr(batch, "output_file_id", None)
        if output_file_id:
            content = self.client.files.content(output_file_id).text
            for raw_line in content.splitlines():
                if not raw_line.strip():
                    continue
                line = json.loads(raw_line)
                response = line.get("response") or {}
                out[line["custom_id"]] = {
                    "custom_id": line["custom_id"],
                    "status_code": response.get("status_code"),
                    "body": response.get("body"),
                }
        # Failed items live in the error file — previously never read, so they
        # vanished from the run. Surface them with an "error" string so the
        # collect loop can classify + re-request them.
        error_file_id = getattr(batch, "error_file_id", None)
        if error_file_id:
            err_content = self.client.files.content(error_file_id).text
            for raw_line in err_content.splitlines():
                if not raw_line.strip():
                    continue
                line = json.loads(raw_line)
                response = line.get("response") or {}
                err_text = (
                    error_text(line.get("error"))
                    or error_text(response.get("body"))
                    or f"status {response.get('status_code')}"
                )
                out[line["custom_id"]] = {
                    "custom_id": line["custom_id"],
                    "status_code": response.get("status_code"),
                    "body": None,
                    "error": err_text,
                }
        return out
