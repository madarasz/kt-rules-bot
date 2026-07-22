"""Tests for batch backends and model->backend routing (no network)."""

from src.services.llm.qwen import QwenAdapter
from tests.quality.batch import backends
from tests.quality.batch.backends import batch_group_key, make_backend, resolve_backend
from tests.quality.batch.errors import classify_batch_error


def test_resolve_backend_routing():
    assert resolve_backend("claude-4.6-sonnet").name == "anthropic"
    assert resolve_backend("gpt-4.1").name == "openai"
    assert resolve_backend("kimi-k2.5").name == "moonshot"
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


def test_resolve_backend_excludes_unbatchable_qwen_models():
    # DashScope's Batch API only accepts the stable qwen aliases; every model in
    # the registry is a versioned/qwen3.x name it rejects with model_not_found
    # (which fails the *whole* batch), so they all route live.
    for model in ("qwen3.6-flash", "qwen3.7-max", "qwen3-turbo", "qwen3-coder-plus"):
        assert resolve_backend(model) is None
    # The alibaba backend stays wired for the aliases DashScope does batch.
    assert QwenAdapter.batch_supports_model("qwen-flash")
    assert make_backend("alibaba").name == "alibaba"


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


def test_openai_poll_captures_whole_batch_rejection(monkeypatch):
    # A whole-batch rejection (e.g. an unsupported model) reports its reason on
    # `errors`, never in an error file — poll must keep it for the collect loop.
    b = backends.OpenAICompatBatchBackend(
        api_key="x", base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        name="alibaba",
    )

    class _Err:
        code = "model_not_found"
        message = "The provided model 'qwen3.6-flash' is not supported by the Batch API."

    class _Errors:
        data = [_Err()]

    class _FakeBatch:
        status = "failed"
        errors = _Errors()

    class _Batches:
        @staticmethod
        def retrieve(_id):
            return _FakeBatch()

    class _Client:
        batches = _Batches()

    monkeypatch.setattr(b, "_client", _Client())
    assert b.poll("bid") == "failed"
    assert "model_not_found" in b.last_error
    # classify_batch_error must call this permanent so collect skips the resubmit.
    assert classify_batch_error(b.last_error)[0] == "permanent"


def _poll_without_error_detail(monkeypatch, status: str) -> str:
    """poll() a batch that reports `status` and carries no errors payload."""
    b = backends.OpenAICompatBatchBackend(
        api_key="x", base_url="https://api.openai.com/v1", name="openai"
    )

    class _FakeBatch:
        errors = None

    _FakeBatch.status = status

    class _Batches:
        @staticmethod
        def retrieve(_id):
            return _FakeBatch()

    class _Client:
        batches = _Batches()

    monkeypatch.setattr(b, "_client", _Client())
    assert b.poll("bid") == "failed"
    return b.last_error


def test_poll_without_error_detail_is_still_readable(monkeypatch):
    # No errors payload: last_error must say something usable rather than the bare
    # status word, which would land in report.md as the message "failed".
    detail = _poll_without_error_detail(monkeypatch, "failed")
    assert detail == "batch failed, no error detail reported"
    # Still unclassified -> transient, so a detail-less failure earns its one resubmit.
    assert classify_batch_error(detail)[0] == "transient"


def test_poll_cancelled_without_detail_classifies_permanent(monkeypatch):
    # The status word has to survive into last_error for cancelled batches, or the
    # collect loop would resubmit a batch the host already gave up on.
    detail = _poll_without_error_detail(monkeypatch, "cancelled")
    assert classify_batch_error(detail)[0] == "permanent"


def test_poll_error_detail_excludes_batch_id(monkeypatch):
    # last_error is fed to classify_batch_error by substring match, so an id like
    # "batch_404abc" must not be able to fake a permanent marker.
    b = backends.OpenAICompatBatchBackend(
        api_key="x", base_url="https://api.openai.com/v1", name="openai"
    )

    class _FakeBatch:
        status = "failed"
        errors = None

    class _Batches:
        @staticmethod
        def retrieve(_id):
            return _FakeBatch()

    class _Client:
        batches = _Batches()

    monkeypatch.setattr(b, "_client", _Client())
    b.poll("batch_404abc")
    assert "404" not in b.last_error
    assert classify_batch_error(b.last_error)[0] == "transient"
