"""Mistral batch: adapter hooks (OpenAI-compat json_schema) + httpx REST backend."""

import json

from src.services.llm.base import GenerationConfig, GenerationRequest
from src.services.llm.batch.backends import MistralBatchBackend
from src.services.llm.mistral import MistralAdapter


def _req():
    return GenerationRequest(
        prompt="q",
        context=["c"],
        chunk_ids=["cid1"],
        config=GenerationConfig(system_prompt="s", max_tokens=400, temperature=0.0),
    )


def test_mistral_build_batch_request_json_schema_body():
    a = MistralAdapter(api_key="k", model="mistral-medium-3-5")
    line = a.build_batch_request(_req(), "gen__t__mistral-medium-3-5__run0")
    assert line["custom_id"] == "gen__t__mistral-medium-3-5__run0"
    body = line["body"]
    assert body["model"] == "mistral-medium-3-5"
    assert body["response_format"]["type"] == "json_schema"


def test_mistral_parse_batch_result():
    content = json.dumps(
        {
            "smalltalk": False,
            "short_answer": "Y",
            "persona_short_answer": "x",
            "quotes": [],
            "explanation": "e",
            "persona_afterword": "a",
        }
    )
    raw = {
        "custom_id": "c",
        "status_code": 200,
        "body": {
            "model": "mistral-medium-3-5",
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
        },
    }
    resp = MistralAdapter.parse_batch_result(raw)
    assert resp.provider == "mistral"
    assert resp.prompt_tokens == 4


def test_mistral_parse_batch_result_errored_raises():
    try:
        MistralAdapter.parse_batch_result({"custom_id": "c", "status_code": 500, "body": None})
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass


class _Resp:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


class _HTTP:
    def __init__(self, status):
        self._status = status

    def get(self, *_a, **_k):
        return _Resp({"status": self._status})


def test_mistral_backend_poll_status_mapping():
    b = MistralBatchBackend(api_key="k")
    b._http = _HTTP("SUCCESS")
    assert b.poll("j") == "ended"
    b._http = _HTTP("TIMEOUT_EXCEEDED")
    assert b.poll("j") == "expired"
    b._http = _HTTP("FAILED")
    assert b.poll("j") == "failed"
    b._http = _HTTP("RUNNING")
    assert b.poll("j") == "in_progress"
