"""Gemini batch: adapter hooks (sentence-numbered request + GeminiAnswer parse)
and the google-genai backend poll mapping."""

import json

from src.services.llm.base import GenerationConfig, GenerationRequest
from src.services.llm.batch.backends import GeminiBatchBackend
from src.services.llm.gemini import GeminiAdapter


def test_gemini_build_batch_request_has_schema_and_sentence_map():
    a = GeminiAdapter(api_key="k", model="gemini-2.5-flash")
    req = GenerationRequest(
        prompt="Can it move and shoot?",
        context=["The operative can move. It can also shoot."],
        chunk_ids=["chunkidxabc12345"],
        config=GenerationConfig(system_prompt="s", max_tokens=400, temperature=0.0),
    )
    line = a.build_batch_request(req, "gen__t__gemini-2.5-flash__run0")
    assert line["custom_id"] == "gen__t__gemini-2.5-flash__run0"
    assert line["model"] == "gemini-2.5-flash"
    cfg = line["request"]["config"]
    assert cfg["response_mime_type"] == "application/json"
    assert "response_schema" in cfg
    # sentence map carried out-of-band for collect-time quote reconstruction
    assert line["_gemini_sentences"]


def test_gemini_parse_batch_result_returns_geminianswer_json():
    content = json.dumps(
        {
            "smalltalk": False,
            "short_answer": "Yes.",
            "persona_short_answer": "x",
            "quotes": [{"quote_title": "Move", "sentence_numbers": [1], "quote_text": ""}],
            "explanation": "e",
            "persona_afterword": "a",
        }
    )
    raw = {
        "custom_id": "c",
        "response": {
            "candidates": [{"content": {"parts": [{"text": content}]}, "finish_reason": "STOP"}],
            "usage_metadata": {
                "prompt_token_count": 8,
                "candidates_token_count": 4,
                "total_token_count": 12,
            },
            "model_version": "gemini-2.5-flash",
        },
    }
    resp = GeminiAdapter.parse_batch_result(raw)
    assert resp.provider == "gemini"
    assert resp.prompt_tokens == 8
    assert json.loads(resp.answer_text)["quotes"][0]["sentence_numbers"] == [1]


def test_gemini_backend_poll_mapping():
    b = GeminiBatchBackend(api_key="k")

    class _Job:
        def __init__(self, state):
            self.state = type("S", (), {"name": state})()

    class _Batches:
        def __init__(self, state):
            self._state = state

        def get(self, name=None):  # noqa: ARG002 - matches google-genai batches.get(name=...)
            return _Job(self._state)

    class _Client:
        def __init__(self, state):
            self.batches = _Batches(state)

    b._client = _Client("JOB_STATE_SUCCEEDED")
    assert b.poll("n") == "ended"
    b._client = _Client("JOB_STATE_EXPIRED")
    assert b.poll("n") == "expired"
    b._client = _Client("JOB_STATE_FAILED")
    assert b.poll("n") == "failed"
    b._client = _Client("JOB_STATE_RUNNING")
    assert b.poll("n") == "in_progress"


def test_collect_reconstructs_gemini_quote_text(tmp_path, monkeypatch):
    """Collect fills empty GeminiAnswer quote_text from the persisted sentence map."""
    from pathlib import Path

    from tests.quality.quality_evaluator import QualityMetrics
    from tests.quality.test_runner import QualityTestRunner

    content = json.dumps(
        {
            "smalltalk": False,
            "short_answer": "Yes.",
            "persona_short_answer": "Obviously.",
            "quotes": [
                {"quote_title": "Move", "sentence_numbers": [1], "quote_text": "", "chunk_id": "abc12345"}
            ],
            "explanation": "It can move.",
            "persona_afterword": "Elementary.",
        }
    )
    item = {
        "custom_id": "gen__t1__gemini-2.5-flash__run1",
        "response": {
            "candidates": [{"content": {"parts": [{"text": content}]}, "finish_reason": "STOP"}],
            "usage_metadata": {"prompt_token_count": 8, "candidates_token_count": 4, "total_token_count": 12},
            "model_version": "gemini-2.5-flash",
        },
    }
    meta = {
        "custom_id": "gen__t1__gemini-2.5-flash__run1",
        "test_id": "t1", "model": "gemini-2.5-flash", "run_num": 1,
        "kind": "gen", "backend": "google",
        "gemini_sentences": {"abc12345": ["The operative can move.", "It can also shoot."]},
    }
    contexts = {"t1__run1": {"context": ["The operative can move. It can also shoot."],
                            "chunk_ids": ["chunkidxabc12345"]}}

    runner = object.__new__(QualityTestRunner)

    class _TC:
        query = "q?"
        ground_truth_contexts = []

    monkeypatch.setattr(runner, "load_test_cases", lambda _tid: [_TC()])

    class _Evaluator:
        def compute_deterministic_metrics(self, **_k):
            return QualityMetrics()

    runner.evaluator = _Evaluator()

    saved = {}

    def _capture(_fn, _q, _md, **kwargs):
        saved.update(kwargs)

    monkeypatch.setattr(runner, "_save_output", _capture)

    runner._write_batch_generation_output(Path(tmp_path), meta, item, contexts)

    resp = saved["llm_response"]
    filled = json.loads(resp.answer_text)["quotes"][0]["quote_text"]
    assert filled == "The operative can move."
