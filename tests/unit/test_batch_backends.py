"""Tests for batch backends and model->backend routing (no network)."""

from tests.quality.batch import backends
from tests.quality.batch.backends import resolve_backend


def test_resolve_backend_routing():
    assert resolve_backend("claude-4.6-sonnet").name == "anthropic"
    assert resolve_backend("gpt-4.1").name == "openai"
    assert resolve_backend("kimi-k2.5").name == "moonshot"
    assert resolve_backend("qwen3-turbo").name == "alibaba"
    assert resolve_backend("mistral-medium-3-5").name == "mistral"
    assert resolve_backend("gemini-2.5-flash").name == "google"
    assert resolve_backend("deepseek-v4-flash") is None  # DeepSeek stays live-only


def test_anthropic_poll_maps_status(monkeypatch):
    b = backends.AnthropicBatchBackend(api_key="x")

    class _FakeBatch:
        processing_status = "ended"

    class _Batches:
        @staticmethod
        def retrieve(_id):
            return _FakeBatch()

    class _Messages:
        batches = _Batches()

    class _Client:
        messages = _Messages()

    monkeypatch.setattr(b, "_client", _Client())
    assert b.poll("bid") == "ended"


def test_openai_poll_maps_status(monkeypatch):
    b = backends.OpenAICompatBatchBackend(
        api_key="x", base_url="https://api.openai.com/v1", name="openai"
    )

    class _FakeBatch:
        status = "completed"

    class _Batches:
        @staticmethod
        def retrieve(_id):
            return _FakeBatch()

    class _Client:
        batches = _Batches()

    monkeypatch.setattr(b, "_client", _Client())
    assert b.poll("bid") == "ended"
