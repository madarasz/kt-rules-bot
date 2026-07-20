"""Unit tests for the reasoning-effort model-name postfix feature.

Covers the central validator (src/lib/model_name.py), the factory injection,
per-adapter application (offline, via build_batch_request), and the batch
registry-lookup postfix stripping.
"""

import argparse

import pytest

from src.lib.model_name import (
    LLM_REASONING_EFFORT_LEVELS,
    REASONING_EFFORT_SUPPORT,
    is_effort_supported,
    model_base_name,
    split_reasoning_effort,
    supported_effort_levels,
    validate_model_arg,
)
from src.services.llm.base import GenerationConfig, GenerationRequest
from src.services.llm.chatgpt import ChatGPTAdapter
from src.services.llm.claude import ClaudeAdapter
from src.services.llm.gemini import GeminiAdapter
from src.services.llm.grok import GrokAdapter


# --------------------------------------------------------------------------- #
# split_reasoning_effort / model_base_name
# --------------------------------------------------------------------------- #
def test_split_with_postfix():
    assert split_reasoning_effort("grok-4.3#high") == ("grok-4.3", "high")


def test_split_no_postfix():
    assert split_reasoning_effort("grok-4.3") == ("grok-4.3", None)


def test_split_normalizes_case_and_whitespace():
    assert split_reasoning_effort("gpt-5.5# High ") == ("gpt-5.5", "high")


def test_split_bad_token_raises():
    with pytest.raises(ValueError, match="Invalid reasoning-effort level"):
        split_reasoning_effort("grok-4.3#turbo")


def test_model_base_name_is_lenient():
    # No validation — just strips the postfix.
    assert model_base_name("grok-4.3#anything") == "grok-4.3"
    assert model_base_name("grok-4.3") == "grok-4.3"


# --------------------------------------------------------------------------- #
# is_effort_supported / supported_effort_levels
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "model_id,effort,expected",
    [
        ("grok-4.3", "high", True),
        ("grok-4.3", "xhigh", False),  # Grok tops out at high
        ("grok-4-0709", "high", False),  # Grok non-effort model
        ("gpt-5.5", "minimal", True),
        ("gpt-4o", "high", False),  # non-reasoning OpenAI model
        ("claude-opus-4-8", "xhigh", True),
        ("claude-opus-4-5-20251101", "xhigh", False),  # 4.5 has no xhigh
        ("claude-opus-4-1-20250805", "high", False),  # Opus 4.1 unsupported
        ("gemini-3-pro-preview", "high", True),
        ("gemini-3-pro-preview", "medium", False),  # 3-pro is LOW/HIGH only
        ("deepseek-v4-pro", "high", False),  # provider not wired
        ("grok-4.3", None, True),  # None effort is always "supported"
    ],
)
def test_is_effort_supported(model_id, effort, expected):
    assert is_effort_supported(model_id, effort) is expected


def test_supported_effort_levels_unwired_is_none():
    assert supported_effort_levels("deepseek-v4-pro") is None
    assert "high" in supported_effort_levels("grok-4.3")


def test_effort_matrix_only_uses_canonical_levels():
    for levels in [supported_effort_levels("grok-4.3"), supported_effort_levels("claude-opus-4-8")]:
        assert levels is not None
        assert levels <= set(LLM_REASONING_EFFORT_LEVELS)


# --------------------------------------------------------------------------- #
# validate_model_arg (CLI type=)
# --------------------------------------------------------------------------- #
def test_validate_model_arg_accepts_supported():
    assert validate_model_arg("grok-4.3#high") == "grok-4.3#high"
    assert validate_model_arg("claude-4.8-opus#low") == "claude-4.8-opus#low"
    assert validate_model_arg("grok-4.3") == "grok-4.3"


@pytest.mark.parametrize(
    "arg",
    [
        "grok-4.3#xhigh",  # valid vocab, unsupported by model
        "gpt-4o#high",  # non-reasoning model
        "deepseek-v4-pro#high",  # provider not wired
        "grok-4.3#turbo",  # invalid vocab
        "nonsense#high",  # unknown model
    ],
)
def test_validate_model_arg_rejects(arg):
    with pytest.raises(argparse.ArgumentTypeError):
        validate_model_arg(arg)


# --------------------------------------------------------------------------- #
# Factory injection
# --------------------------------------------------------------------------- #
def test_factory_injects_effort(monkeypatch):
    from src.services.llm import factory as fac

    class _Cfg:
        default_llm_provider = "grok-4.3"
        anthropic_api_key = openai_api_key = google_api_key = "dummy"
        x_api_key = dial_api_key = deepseek_api_key = "dummy"
        mistral_api_key = moonshot_api_key = alibaba_api_key = "dummy"

    class _MSC:
        def get_server_config(self, _gid):
            return None

    monkeypatch.setattr(fac, "get_config", lambda: _Cfg())
    monkeypatch.setattr(fac, "get_multi_server_config", lambda: _MSC())

    provider = fac.LLMProviderFactory.create("grok-4.3#high")
    assert provider is not None
    assert provider.model == "grok-4.3"
    assert provider.reasoning_effort == "high"

    # No postfix -> default (unchanged behaviour).
    assert fac.LLMProviderFactory.create("grok-4.3").reasoning_effort is None

    # Runtime path is lenient: an unsupported level does NOT raise; the adapter
    # will warn+ignore it at request time.
    lenient = fac.LLMProviderFactory.create("gpt-4o#high")
    assert lenient is not None
    assert lenient.reasoning_effort == "high"  # stored, but adapter ignores it


# --------------------------------------------------------------------------- #
# Per-adapter application (offline via build_batch_request)
# --------------------------------------------------------------------------- #
@pytest.fixture
def request_():
    return GenerationRequest(
        prompt="q", context=["c"], config=GenerationConfig(), chunk_ids=["id1"]
    )


def _with_effort(adapter, effort):
    adapter.reasoning_effort = effort
    return adapter


def test_chatgpt_effort_applied(request_):
    a = _with_effort(ChatGPTAdapter("k", "gpt-5.5"), "high")
    assert a.build_batch_request(request_, "c")["body"]["reasoning_effort"] == "high"


def test_chatgpt_effort_ignored_for_non_reasoning(request_):
    a = _with_effort(ChatGPTAdapter("k", "gpt-4o"), "high")
    assert "reasoning_effort" not in a.build_batch_request(request_, "c")["body"]


def test_claude_effort_applied(request_):
    a = _with_effort(ClaudeAdapter("k", "claude-opus-4-8"), "xhigh")
    assert a.build_batch_request(request_, "c")["params"]["output_config"] == {"effort": "xhigh"}


def test_claude_effort_ignored_when_unsupported(request_):
    a = _with_effort(ClaudeAdapter("k", "claude-opus-4-1-20250805"), "high")
    assert "output_config" not in a.build_batch_request(request_, "c")["params"]


def test_grok_effort_applied(request_):
    # Batch uses the same field name as the live chat/completions path, because
    # parse_batch_result reads xAI batch results as chat.completions-shaped.
    a = _with_effort(GrokAdapter("k", "grok-4.3"), "high")
    body = a.build_batch_request(request_, "c")["batch_request"]["responses"]
    assert body["reasoning_effort"] == "high"


def test_grok_effort_ignored_for_non_effort_model(request_):
    a = _with_effort(GrokAdapter("k", "grok-4-0709"), "high")
    body = a.build_batch_request(request_, "c")["batch_request"]["responses"]
    assert "reasoning_effort" not in body


def test_gemini3_uses_thinking_level(request_):
    a = _with_effort(GeminiAdapter("k", "gemini-3-pro-preview"), "high")
    cfg = a.build_batch_request(request_, "c")["request"]["config"]
    assert cfg["thinking_config"] == {"thinking_level": "HIGH"}


def test_gemini25_uses_thinking_budget(request_):
    a = _with_effort(GeminiAdapter("k", "gemini-2.5-pro"), "low")
    cfg = a.build_batch_request(request_, "c")["request"]["config"]
    assert cfg["thinking_config"] == {"thinking_budget": 2048}


def test_no_effort_leaves_request_unchanged(request_):
    a = GrokAdapter("k", "grok-4.3")  # reasoning_effort defaults to None
    body = a.build_batch_request(request_, "c")["batch_request"]["responses"]
    assert "reasoning" not in body


# --------------------------------------------------------------------------- #
# Batch registry lookup strips the postfix
# --------------------------------------------------------------------------- #
def test_resolve_backend_strips_postfix():
    from tests.quality.batch.backends import resolve_backend

    assert type(resolve_backend("gpt-5.5#high")) is type(resolve_backend("gpt-5.5"))
    assert resolve_backend("gpt-5.5#high") is not None


# --------------------------------------------------------------------------- #
# Capability-table drift guards
#
# REASONING_EFFORT_SUPPORT is keyed by resolved model_id, while the adapters key
# their own reasoning-model lists separately. When the two disagree, effort is
# applied to a model the adapter thinks is non-reasoning -> the request carries
# conflicting params and/or an un-inflated token budget. These guards fail on
# that drift instead of letting it reach the API.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "adapter_class",
    [ChatGPTAdapter, GeminiAdapter],
    ids=["chatgpt", "gemini"],
)
def test_effort_models_are_classified_as_reasoning_models(adapter_class):
    from src.services.llm.factory import LLMProviderFactory

    mismatched = []
    for friendly, (cls, model_id, _key) in LLMProviderFactory._model_registry.items():
        if cls is not adapter_class or model_id not in REASONING_EFFORT_SUPPORT:
            continue
        if not adapter_class("k", model_id).uses_completion_tokens:
            mismatched.append(f"{friendly} -> {model_id}")

    assert not mismatched, (
        f"{adapter_class.__name__}: models in REASONING_EFFORT_SUPPORT but missing from the "
        f"adapter's reasoning-model list (effort applied without a reasoning token budget): "
        f"{mismatched}"
    )


def test_effort_matrix_keys_all_resolve_to_a_registry_model():
    """A matrix key that matches no model_id silently disables effort for it."""
    from src.services.llm.factory import LLMProviderFactory

    known_ids = {mid for _cls, mid, _key in LLMProviderFactory._model_registry.values()}
    assert not (set(REASONING_EFFORT_SUPPORT) - known_ids)


# --------------------------------------------------------------------------- #
# Factory round-trip: friendly name + effort -> built request
#
# The per-adapter tests above construct adapters directly with a hand-picked
# model_id, so they never exercise friendly-name -> model_id resolution, which
# is where the capability tables can disagree.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "spec,expect",
    [
        ("gpt-5.5#high", lambda r: r["body"]["reasoning_effort"] == "high"),
        ("gpt-5.4-mini#high", lambda r: r["body"]["reasoning_effort"] == "high"),
        ("claude-4.8-opus#xhigh", lambda r: r["params"]["output_config"] == {"effort": "xhigh"}),
        ("grok-4.3#high", lambda r: r["batch_request"]["responses"]["reasoning_effort"] == "high"),
        (
            "gemini-2.5-pro#low",
            lambda r: r["request"]["config"]["thinking_config"] == {"thinking_budget": 2048},
        ),
    ],
)
def test_factory_roundtrip_applies_effort(monkeypatch, request_, spec, expect):
    from src.services.llm import factory as fac

    class _Cfg:
        default_llm_provider = "grok-4.3"
        anthropic_api_key = openai_api_key = google_api_key = "dummy"
        x_api_key = dial_api_key = deepseek_api_key = "dummy"
        mistral_api_key = moonshot_api_key = alibaba_api_key = "dummy"

    class _MSC:
        def get_server_config(self, _gid):
            return None

    monkeypatch.setattr(fac, "get_config", lambda: _Cfg())
    monkeypatch.setattr(fac, "get_multi_server_config", lambda: _MSC())

    provider = fac.LLMProviderFactory.create(spec)
    assert expect(provider.build_batch_request(request_, "c"))


def test_factory_roundtrip_reasoning_model_omits_temperature(monkeypatch):
    """gpt-5.4-mini resolves to a dated model_id; effort must not be paired with
    temperature/max_tokens, which OpenAI rejects for reasoning models."""
    from src.services.llm import factory as fac

    class _Cfg:
        default_llm_provider = "gpt-5.4-mini"
        anthropic_api_key = openai_api_key = google_api_key = "dummy"
        x_api_key = dial_api_key = deepseek_api_key = "dummy"
        mistral_api_key = moonshot_api_key = alibaba_api_key = "dummy"

    class _MSC:
        def get_server_config(self, _gid):
            return None

    monkeypatch.setattr(fac, "get_config", lambda: _Cfg())
    monkeypatch.setattr(fac, "get_multi_server_config", lambda: _MSC())

    provider = fac.LLMProviderFactory.create("gpt-5.4-mini#high")
    body = provider.build_batch_request(
        GenerationRequest(prompt="q", context=["c"], config=GenerationConfig(), chunk_ids=["i"]),
        "c",
    )["body"]
    assert body["reasoning_effort"] == "high"
    assert "temperature" not in body
    assert "max_tokens" not in body


# --------------------------------------------------------------------------- #
# Postfix must not leak into pricing lookups or filenames
# --------------------------------------------------------------------------- #
def test_cost_lookup_ignores_effort_postfix():
    from src.lib.tokens import calculate_llm_cost

    plain = calculate_llm_cost(100_000, 20_000, "grok-4.3")
    posted = calculate_llm_cost(100_000, 20_000, "grok-4.3#high")
    assert posted.total_cost == plain.total_cost


def test_model_slug_is_link_safe():
    from src.lib.model_name import model_slug

    assert model_slug("grok-4.3#high") == "grok-4.3-high"
    assert model_slug("grok-4.3") == "grok-4.3"
    assert "#" not in model_slug("claude-4.8-opus#xhigh")
