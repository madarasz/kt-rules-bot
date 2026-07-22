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
        # Whole-batch rejection reason from the last failed poll (e.g. an invalid
        # model), so the failure is not reported as a bare "batch failed".
        self.last_error: str | None = None

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
        batch = self.client.batches.retrieve(batch_id)
        status = batch.status
        if status == "completed":
            return "ended"
        if status == "expired":
            return "expired"
        if status in ("failed", "cancelled", "canceled"):
            # A whole-batch rejection carries its reason on `errors`, never in an
            # error file — read it here or it is lost for the rest of the run.
            self.last_error = self._batch_error_text(batch)
            logger.error(
                f"{self.name} batch {batch_id} {status}: {self.last_error or 'no detail'}"
            )
            return "failed"
        return "in_progress"

    @staticmethod
    def _batch_error_text(batch) -> str | None:
        errors = getattr(batch, "errors", None)
        data = getattr(errors, "data", None) if errors is not None else None
        if not data:
            return None
        parts = []
        for err in data:
            code = getattr(err, "code", None) or "error"
            message = getattr(err, "message", None) or ""
            parts.append(f"{code}: {message}".strip(": "))
        return "; ".join(parts)

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
