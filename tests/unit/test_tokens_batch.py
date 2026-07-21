"""Tests for the 50% batch-discount path in calculate_llm_cost."""

from src.lib.pricing import calculate_llm_cost


def test_batch_halves_prompt_and_completion_cost_after_cache():
    live = calculate_llm_cost(1000, 500, "gpt-4.1")
    batched = calculate_llm_cost(1000, 500, "gpt-4.1", batch=True)
    assert abs(batched.total_cost - live.total_cost * 0.5) < 1e-9
    # batch_savings = what the same tokens cost live (after cache) minus batched cost
    assert abs(batched.batch_savings - (live.total_cost - batched.total_cost)) < 1e-9
    assert live.batch_savings == 0.0


def test_batch_stacks_on_anthropic_cache():
    # cache read tokens are separate for anthropic; batch discount applies on top
    batched = calculate_llm_cost(
        1000, 500, "claude-4.6-sonnet", cache_read_tokens=800, batch=True
    )
    live = calculate_llm_cost(1000, 500, "claude-4.6-sonnet", cache_read_tokens=800)
    assert abs(batched.total_cost - live.total_cost * 0.5) < 1e-9
    # cache savings is computed on live (pre-discount) numbers and must not change
    assert abs(batched.cache_savings - live.cache_savings) < 1e-9
