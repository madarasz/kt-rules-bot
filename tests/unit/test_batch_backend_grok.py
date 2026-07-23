"""Grok batch: adapter hooks (xAI Responses shape) + httpx REST backend.

NOTE: xAI batch uses the Responses API (`input`, per-item success) and an
unquantified "reduced" discount. These tests fix the transport/poll logic and
the request/parse scaffold; live fidelity is smoke-confirmable only."""

from src.services.llm.base import GenerationConfig, GenerationRequest
from src.services.llm.batch.backends import GrokBatchBackend
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
