"""xAI Grok batch backend (httpx REST, no xai_sdk dep)."""

from src.lib.logging import get_logger

from ._util import error_text

logger = get_logger(__name__)


class GrokBatchBackend:
    """xAI Grok batch via httpx REST (Responses-API batch; no xai_sdk dep).

    Flow: POST /batches (name) -> POST /batches/{id}/requests (batch_requests)
    -> poll GET /batches/{id} (num_pending==0) -> GET /batches/{id}/results
    (paginated succeeded/failed)."""

    name = "x"
    BASE_URL = "https://api.x.ai/v1"

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

    def submit(self, lines: list[dict], label: str = "quality-test") -> str:
        # `label` is the human-readable batch name in the xAI console; callers other
        # than the quality-test runner (e.g. RAG ingestion) pass their own so the
        # submissions are distinguishable there.
        created = self.http.post("/batches", json={"name": label})
        created.raise_for_status()
        batch_id = created.json()["batch_id"]
        payload = {
            "batch_requests": [
                {"batch_request_id": x["batch_request_id"], "batch_request": x["batch_request"]}
                for x in lines
            ]
        }
        added = self.http.post(f"/batches/{batch_id}/requests", json=payload)
        added.raise_for_status()
        logger.info(f"Submitted Grok batch {batch_id} ({len(lines)} requests)")
        return batch_id

    def poll(self, batch_id: str) -> str:
        r = self.http.get(f"/batches/{batch_id}")
        r.raise_for_status()
        state = r.json().get("state", {})
        if state.get("num_pending", 1) == 0:
            return "ended"
        return "in_progress"

    def fetch(self, batch_id: str) -> dict[str, dict]:
        out: dict[str, dict] = {}
        token = None
        while True:
            params = {"limit": 100}
            if token:
                params["pagination_token"] = token
            r = self.http.get(f"/batches/{batch_id}/results", params=params)
            r.raise_for_status()
            data = r.json()
            # xAI returns every item (success or error) under "results"; each has
            # a "batch_request_id" and a "batch_result" that wraps the served
            # completion under a typed key (chat_get_completion for the
            # chat.completions endpoint, get_response for the responses endpoint).
            for item in data.get("results", []):
                cid = item["batch_request_id"]
                result = item.get("batch_result") or {}
                response = result.get("response") or {}
                completion = (
                    response.get("chat_get_completion")
                    or response.get("get_response")
                    or (response if response else None)
                )
                if completion is None:
                    # Error items carry an error under batch_result/response/item
                    # rather than a completion — surface it for classification.
                    err_text = (
                        error_text(result.get("error"))
                        or error_text(response.get("error"))
                        or error_text(item.get("error"))
                        or "no response"
                    )
                    out[cid] = {"custom_id": cid, "response": None, "error": err_text}
                else:
                    out[cid] = {"custom_id": cid, "response": completion}
            token = data.get("pagination_token")
            if not token:
                break
        return out
