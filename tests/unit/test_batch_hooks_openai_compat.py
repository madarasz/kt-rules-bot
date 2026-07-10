"""Kimi + Qwen batch hooks (OpenAI-compat json_object + schema-in-prompt)."""

import json

from src.services.llm.base import GenerationConfig, GenerationRequest
from src.services.llm.kimi import KimiAdapter
from src.services.llm.qwen import QwenAdapter


def _req():
    return GenerationRequest(
        prompt="Can the Eliminator shoot twice?",
        context=["[chunk] Suspensor System lets it shoot twice."],
        chunk_ids=["chunkid01"],
        config=GenerationConfig(
            system_prompt="You are a rules helper.", max_tokens=500, temperature=0.0
        ),
    )


def test_kimi_build_batch_request_is_json_object_with_schema_in_prompt():
    a = KimiAdapter(api_key="k", model="kimi-k2.5")
    line = a.build_batch_request(_req(), "gen__t__kimi-k2.5__run0")
    assert line["custom_id"] == "gen__t__kimi-k2.5__run0"
    assert line["url"] == "/v1/chat/completions"
    body = line["body"]
    assert body["response_format"] == {"type": "json_object"}
    # schema is appended to the system message, not sent as response_format json_schema
    assert "schema" in body["messages"][0]["content"].lower()
    assert body["model"] == "kimi-k2.5"
    # thinking model: temperature forced to 1.0, max_tokens tripled (matches generate())
    assert body["temperature"] == 1.0
    assert body["max_tokens"] == 1500


def test_kimi_non_thinking_model_keeps_temperature_and_tokens():
    a = KimiAdapter(api_key="k", model="moonshot-v1-8k")
    body = a.build_batch_request(_req(), "gen__t__moonshot-v1-8k__run0")["body"]
    assert body["temperature"] == 0.0
    assert body["max_tokens"] == 500


def test_kimi_parse_batch_result_roundtrips_content():
    answer = json.dumps(
        {
            "smalltalk": False,
            "short_answer": "Yes.",
            "persona_short_answer": "Obviously.",
            "quotes": [],
            "explanation": "Suspensor System.",
            "persona_afterword": "Elementary.",
        }
    )
    raw = {
        "custom_id": "c",
        "status_code": 200,
        "body": {
            "model": "kimi-k2.5",
            "choices": [{"message": {"content": answer}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    }
    resp = KimiAdapter.parse_batch_result(raw)
    assert resp.provider == "moonshot"
    assert resp.prompt_tokens == 10
    assert json.loads(resp.answer_text)["short_answer"] == "Yes."


def test_kimi_parse_batch_result_errored_item_raises():
    raw = {"custom_id": "c", "status_code": 400, "body": None}
    try:
        KimiAdapter.parse_batch_result(raw)
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass


def test_qwen_build_batch_request_provider_and_schema():
    a = QwenAdapter(api_key="k", model="qwen3-turbo")
    line = a.build_batch_request(_req(), "gen__t__qwen3-turbo__run0")
    assert line["body"]["response_format"] == {"type": "json_object"}
    assert line["body"]["max_tokens"] == 500  # no thinking-token multiplier
    resp = QwenAdapter.parse_batch_result(
        {
            "custom_id": "c",
            "status_code": 200,
            "body": {
                "model": "qwen3-turbo",
                "choices": [
                    {
                        "message": {
                            "content": '{"smalltalk": false, "short_answer": "Y", "persona_short_answer": "x", "quotes": [], "explanation": "e", "persona_afterword": "a"}'
                        }
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            },
        }
    )
    assert resp.provider == "alibaba"
    assert resp.completion_tokens == 2
