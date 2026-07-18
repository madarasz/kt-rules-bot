"""Per-backend batch discount table (tokens.py)."""

from src.lib.tokens import BATCH_DISCOUNT, batch_discount_for, calculate_llm_cost


def test_known_backends_have_discounts():
    for name in ("anthropic", "openai", "mistral", "alibaba", "moonshot", "x", "google"):
        assert 0.0 < BATCH_DISCOUNT[name] <= 1.0


def test_unknown_backend_falls_back_to_default():
    assert batch_discount_for("nope") == 0.5
    assert batch_discount_for(None) == 0.5


def test_batch_backend_selects_discount():
    # gpt-4.1: prompt 0.002, completion 0.008 per 1k. 1000 prompt + 1000 completion.
    live = calculate_llm_cost(1000, 1000, "gpt-4.1")
    batched = calculate_llm_cost(1000, 1000, "gpt-4.1", batch=True, batch_backend="openai")
    assert batched.total_cost == live.total_cost * 0.5
    assert batched.batch_savings == live.total_cost * 0.5


def test_batch_without_backend_uses_default_discount():
    live = calculate_llm_cost(1000, 1000, "gpt-4.1")
    batched = calculate_llm_cost(1000, 1000, "gpt-4.1", batch=True)
    assert batched.total_cost == live.total_cost * 0.5
