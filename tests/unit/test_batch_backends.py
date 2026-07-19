"""Tests for batch backends and model->backend routing (no network)."""

from tests.quality.batch import backends
from tests.quality.batch.backends import batch_group_key, make_backend, resolve_backend


def test_resolve_backend_routing():
    assert resolve_backend("claude-4.6-sonnet").name == "anthropic"
    assert resolve_backend("gpt-4.1").name == "openai"
    assert resolve_backend("kimi-k2.5").name == "moonshot"
    assert resolve_backend("qwen3-turbo").name == "alibaba"
    assert resolve_backend("mistral-medium-3-5").name == "mistral"
    assert resolve_backend("gemini-2.5-flash").name == "google"
    assert resolve_backend("grok-4-1-fast-reasoning").name == "x"
    assert resolve_backend("deepseek-v4-flash") is None  # DeepSeek stays live-only


def test_resolve_backend_excludes_openai_chat_latest():
    # OpenAI's Batch API rejects *-chat-latest (model_not_found) -> live fallback.
    assert resolve_backend("gpt-5.3-chat-latest") is None
    assert resolve_backend("gpt-5.2-chat-latest") is None
    assert resolve_backend("gpt-5.1-chat-latest") is None
    # Non-chat-latest OpenAI models still batch.
    assert resolve_backend("gpt-5.4-mini").name == "openai"


def test_batch_group_key_partitions_openai_by_model():
    # OpenAI-compat backends require one model per batch -> group key carries the
    # model; each distinct model becomes its own submission group.
    oa = backends.OpenAICompatBatchBackend(
        api_key="k", base_url="https://api.openai.com/v1", name="openai"
    )
    k1 = batch_group_key(oa, "gpt-5.6-luna")
    k2 = batch_group_key(oa, "gpt-5.4-mini")
    assert k1 == "openai::gpt-5.6-luna"
    assert k2 == "openai::gpt-5.4-mini"
    assert k1 != k2


def test_batch_group_key_mixed_model_backends_group_by_name():
    # Anthropic (and the other non-OpenAI backends) accept mixed-model batches, so
    # the group key is just the backend name regardless of model.
    an = backends.AnthropicBatchBackend(api_key="k")
    assert batch_group_key(an, "claude-4.6-sonnet") == "anthropic"
    assert batch_group_key(an, "claude-4.6-haiku") == "anthropic"


def test_make_backend_round_trips_group_key():
    # make_backend must accept a name::model group key and reconstruct the backend.
    b = make_backend("openai::gpt-5.6-luna")
    assert isinstance(b, backends.OpenAICompatBatchBackend)
    assert b.name == "openai"


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
