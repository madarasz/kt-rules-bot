"""Mistral batch backend (httpx REST, no mistralai SDK dep)."""

import json

from src.lib.logging import get_logger

from ._util import error_text

logger = get_logger(__name__)


class MistralBatchBackend:
    """Mistral batch via httpx REST against api.mistral.ai (no mistralai SDK dep).

    Flow: upload JSONL (POST /files, purpose=batch) -> create job
    (POST /batch/jobs) -> poll (GET /batch/jobs/{id}) SUCCESS -> download
    output_file (GET /files/{id}/content)."""

    name = "mistral"
    BASE_URL = "https://api.mistral.ai/v1"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._http = None

    @property
    def http(self):
        if self._http is None:
            import httpx

            self._http = httpx.Client(
                base_url=self.BASE_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=60.0,
            )
        return self._http

    def submit(self, lines: list[dict], label: str = "quality-test") -> str:  # noqa: ARG002 - no name field in this API
        import io

        model = lines[0]["body"]["model"]
        buf = io.BytesIO(("\n".join(json.dumps(x) for x in lines)).encode("utf-8"))
        up = self.http.post(
            "/files",
            files={"file": ("batch.jsonl", buf, "application/jsonl")},
            data={"purpose": "batch"},
        )
        up.raise_for_status()
        file_id = up.json()["id"]
        job = self.http.post(
            "/batch/jobs",
            json={"input_files": [file_id], "endpoint": "/v1/chat/completions", "model": model},
        )
        job.raise_for_status()
        job_id = job.json()["id"]
        logger.info(f"Submitted Mistral batch {job_id} ({len(lines)} requests)")
        return job_id

    def poll(self, batch_id: str) -> str:
        r = self.http.get(f"/batch/jobs/{batch_id}")
        r.raise_for_status()
        status = r.json()["status"]
        if status == "SUCCESS":
            return "ended"
        if status == "TIMEOUT_EXCEEDED":
            return "expired"
        if status in ("FAILED", "CANCELLED", "CANCELLATION_REQUESTED"):
            return "failed"
        return "in_progress"

    def fetch(self, batch_id: str) -> dict[str, dict]:
        r = self.http.get(f"/batch/jobs/{batch_id}")
        r.raise_for_status()
        job = r.json()
        out: dict[str, dict] = {}
        output_file = job.get("output_file")
        if output_file:
            content = self.http.get(f"/files/{output_file}/content").text
            for raw_line in content.splitlines():
                if not raw_line.strip():
                    continue
                line = json.loads(raw_line)
                # ponytail: output line shape (response.body) is smoke-confirmable — adjust
                # this mapping after the first live Mistral batch if it nests differently.
                response = line.get("response") or {}
                out[line["custom_id"]] = {
                    "custom_id": line["custom_id"],
                    "status_code": response.get("status_code", 200),
                    "body": response.get("body"),
                }
        # Failed items land in the job's error file — surface them so the collect
        # loop can classify + re-request them.
        error_file = job.get("error_file")
        if error_file:
            err_content = self.http.get(f"/files/{error_file}/content").text
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
