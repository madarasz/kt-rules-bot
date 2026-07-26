"""Grok batch: adapter hooks (xAI Responses shape) + httpx REST backend.

NOTE: xAI batch uses the Responses API (`input`, per-item success) and an
unquantified "reduced" discount. These tests fix the transport/poll logic and
the request/parse scaffold; live fidelity is smoke-confirmable only."""

import httpx
import pytest

from src.services.llm.base import GenerationConfig, GenerationRequest
from src.services.llm.batch.backends import GrokBatchBackend
from src.services.llm.batch.backends._util import raise_for_status_with_body
from src.services.llm.grok import GrokAdapter


def _req():
    return GenerationRequest(
        prompt="q",
        context=["c"],
        chunk_ids=["cid1"],
        config=GenerationConfig(system_prompt="s", max_tokens=300, temperature=0.0),
    )


def test_grok_build_batch_request_shape():
    a = GrokAdapter(api_key="k", model="grok-4-1-fast-reasoning")
    line = a.build_batch_request(_req(), "judge__t__grok__run0")
    assert line["custom_id"] == "judge__t__grok__run0"
    assert line["batch_request_id"] == "judge__t__grok__run0"
    assert line["batch_request"]["responses"]["model"] == "grok-4-1-fast-reasoning"


def test_grok_parse_batch_result_output_text():
    content = '{"smalltalk": false, "short_answer": "Y", "persona_short_answer": "x", "quotes": [], "explanation": "e", "persona_afterword": "a"}'
    raw = {
        "custom_id": "c",
        "response": {
            "output_text": content,
            "model": "grok-4.3",
            "usage": {"input_tokens": 6, "output_tokens": 3},
        },
    }
    resp = GrokAdapter.parse_batch_result(raw)
    assert resp.provider == "grok"
    assert resp.prompt_tokens == 6
    assert resp.completion_tokens == 3


def test_grok_parse_batch_result_output_blocks():
    content = '{"smalltalk": false, "short_answer": "Y", "persona_short_answer": "x", "quotes": [], "explanation": "e", "persona_afterword": "a"}'
    raw = {
        "custom_id": "c",
        "response": {
            "output": [{"content": [{"type": "output_text", "text": content}]}],
            "model": "grok-4.3",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        },
    }
    resp = GrokAdapter.parse_batch_result(raw)
    assert resp.provider == "grok"


def test_grok_batch_excludes_unsupported_models():
    assert not GrokAdapter.batch_supports_model("grok-4.5")
    assert GrokAdapter.batch_supports_model("grok-4.3")


def test_raise_for_status_with_body_keeps_the_provider_message():
    # The bare httpx message is status + URL only; the reason ("not supported for
    # batch processing") lives in the body and must reach the traceback.
    request = httpx.Request("POST", "https://api.x.ai/v1/batches/b1/requests")
    response = httpx.Response(
        400,
        request=request,
        json={
            "code": "Client specified an invalid argument",
            "error": "Model grok-4.5 is not supported for batch processing.",
        },
    )
    with pytest.raises(httpx.HTTPStatusError) as exc:
        raise_for_status_with_body(response)
    assert "not supported for batch processing" in str(exc.value)
    assert exc.value.response is response


def test_raise_for_status_with_body_passes_success_through():
    request = httpx.Request("GET", "https://api.x.ai/v1/batches/b1")
    raise_for_status_with_body(httpx.Response(200, request=request, json={}))


def test_grok_backend_poll_pending_zero_is_ended():
    b = GrokBatchBackend(api_key="k")

    class _Resp:
        def __init__(self, pending):
            self._p = pending
            self.status_code = 200

        def json(self):
            return {"state": {"num_pending": self._p, "num_error": 0}}

        def raise_for_status(self):
            pass

    class _HTTP:
        def __init__(self, pending):
            self._p = pending

        def get(self, *_a, **_k):
            return _Resp(self._p)

    b._http = _HTTP(0)
    assert b.poll("x") == "ended"
    b._http = _HTTP(5)
    assert b.poll("x") == "in_progress"
