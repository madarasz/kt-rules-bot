"""Tests for batch request/result hooks on LLM adapters."""

import json
from types import SimpleNamespace

from src.services.llm.base import GenerationConfig, GenerationRequest
from src.services.llm.chatgpt import ChatGPTAdapter
from src.services.llm.claude import ClaudeAdapter
from src.services.llm.deepseek import DeepSeekAdapter


def test_non_batch_adapter_defaults_false():
    # DeepSeek has no native batch API and stays on the live-async fallback.
    assert DeepSeekAdapter.supports_batch is False


def test_batchable_adapters_opt_in():
    assert ClaudeAdapter.supports_batch is True
    assert ChatGPTAdapter.supports_batch is True


def test_chatgpt_batch_excludes_chat_latest():
    # OpenAI's Batch API rejects the *-chat-latest aliases (model_not_found);
    # everything else batches.
    assert ChatGPTAdapter.batch_supports_model("gpt-5.3-chat-latest") is False
    assert ChatGPTAdapter.batch_supports_model("gpt-5.4-mini") is True
    assert ChatGPTAdapter.batch_supports_model("gpt-5") is True
    # Base default is permissive.
    assert ClaudeAdapter.batch_supports_model("claude-4.6-sonnet") is True


# ---- Claude ----------------------------------------------------------------

def _fake_claude_msg():
    return SimpleNamespace(
        model="claude-sonnet-4-5-20250929",
        content=[
            SimpleNamespace(
                type="tool_use",
                input={
                    "smalltalk": False,
                    "short_answer": "Yes.",
                    "persona_short_answer": "",
                    "quotes": [],
                    "explanation": "x",
                    "persona_afterword": "",
                },
            )
        ],
        usage=SimpleNamespace(
            input_tokens=100,
            output_tokens=20,
            cache_read_input_tokens=80,
            cache_creation_input_tokens=0,
        ),
    )


def test_claude_build_batch_request_has_tool_and_custom_id():
    a = ClaudeAdapter(api_key="x", model="claude-sonnet-4-5-20250929")
    req = GenerationRequest(prompt="q", context=[], config=GenerationConfig(), chunk_ids=None)
    line = a.build_batch_request(req, custom_id="gen__t__m__run1")
    assert line["custom_id"] == "gen__t__m__run1"
    p = line["params"]
    assert p["model"] == "claude-sonnet-4-5-20250929"
    assert p["tool_choice"]["name"] == p["tools"][0]["name"]
    assert p["messages"][0]["role"] == "user"


def test_claude_parse_batch_result_roundtrips():
    raw = {
        "custom_id": "gen__t__m__run1",
        "result_type": "succeeded",
        "message": _fake_claude_msg(),
    }
    resp = ClaudeAdapter.parse_batch_result(raw)
    assert json.loads(resp.answer_text)["short_answer"] == "Yes."
    assert resp.prompt_tokens == 100 and resp.completion_tokens == 20
    assert resp.cache_read_tokens == 80
    assert resp.provider == "claude"
    assert resp.model_version == "claude-sonnet-4-5-20250929"


# ---- OpenAI ----------------------------------------------------------------

def test_openai_build_batch_request_json_schema():
    a = ChatGPTAdapter(api_key="x", model="gpt-4.1")
    req = GenerationRequest(prompt="q", context=[], config=GenerationConfig(), chunk_ids=None)
    line = a.build_batch_request(req, custom_id="gen__t__gpt-4.1__run1")
    assert line["url"] == "/v1/chat/completions"
    b = line["body"]
    assert b["model"] == "gpt-4.1"
    assert b["response_format"]["type"] == "json_schema"
    assert "max_tokens" in b  # non-reasoning model


def test_openai_parse_batch_result_roundtrips():
    body = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"smalltalk": false, "short_answer": "Yes.", '
                        '"persona_short_answer": "", "quotes": [], '
                        '"explanation": "x", "persona_afterword": ""}'
                    )
                }
            }
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120,
            "prompt_tokens_details": {"cached_tokens": 80},
        },
        "model": "gpt-4.1-2025",
    }
    raw = {"custom_id": "gen__t__gpt-4.1__run1", "status_code": 200, "body": body}
    resp = ChatGPTAdapter.parse_batch_result(raw)
    assert resp.prompt_tokens == 100 and resp.cache_read_tokens == 80
    assert resp.model_version == "gpt-4.1-2025"
    assert resp.structured_output["short_answer"] == "Yes."
