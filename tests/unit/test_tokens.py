import pytest

from src.lib.tokens import LLMCostBreakdown, calculate_llm_cost, estimate_cost


class TestCalculateLlmCost:
    def test_no_caching_returns_simple_cost(self):
        result = calculate_llm_cost(1000, 200, "gpt-4.1")
        assert isinstance(result, LLMCostBreakdown)
        assert result.cache_savings == 0.0
        assert result.cache_read_tokens == 0
        assert result.total_cost == pytest.approx(
            (1000 / 1000) * 0.002 + (200 / 1000) * 0.008
        )

    def test_openai_cache_savings(self):
        result = calculate_llm_cost(
            prompt_tokens=1000,
            completion_tokens=200,
            model="gpt-4.1",
            cache_read_tokens=500,
        )
        assert result.prompt_cost == pytest.approx(0.001)
        assert result.cache_read_cost == pytest.approx(0.0005)
        assert result.total_cost == pytest.approx(0.001 + 0.0005 + 0.0016)
        assert result.cache_savings == pytest.approx(0.0005)

    def test_mistral_cache_savings(self):
        result = calculate_llm_cost(1000, 200, "mistral-large-2512", cache_read_tokens=500)
        # 500 cached tokens billed @ 0.00005 vs 0.0005 full prompt rate
        assert result.cache_savings == pytest.approx((500 / 1000) * (0.0005 - 0.00005))
        assert result.has_cache_activity

    def test_anthropic_cache_savings_reads(self):
        result = calculate_llm_cost(
            prompt_tokens=500,
            completion_tokens=100,
            model="claude-4.5-sonnet",
            cache_read_tokens=400,
        )
        assert result.prompt_cost == pytest.approx(0.0015)
        assert result.cache_read_cost == pytest.approx(0.00012)
        assert result.cache_creation_cost == 0.0
        assert result.total_cost == pytest.approx(0.0015 + 0.00012 + 0.0006)
        assert result.cache_savings == pytest.approx(0.00108)

    def test_anthropic_cache_creation_reduces_savings(self):
        result = calculate_llm_cost(
            prompt_tokens=500,
            completion_tokens=100,
            model="claude-4.5-sonnet",
            cache_read_tokens=0,
            cache_creation_tokens=400,
        )
        assert result.cache_creation_cost == pytest.approx(0.0015)
        assert result.cache_savings == pytest.approx(-0.0003)

    def test_unknown_model_uses_fallback(self):
        result = calculate_llm_cost(1000, 200, "new-unknown-model")
        assert result.total_cost > 0
        assert result.cache_savings == 0.0

    def test_estimate_cost_backward_compat(self):
        result = estimate_cost(1000, 200, "gpt-4.1")
        assert isinstance(result, float)
        assert result == pytest.approx(calculate_llm_cost(1000, 200, "gpt-4.1").total_cost)

    def test_has_cache_activity_flag(self):
        no_cache = calculate_llm_cost(1000, 200, "gpt-4.1")
        with_cache = calculate_llm_cost(1000, 200, "gpt-4.1", cache_read_tokens=300)
        assert not no_cache.has_cache_activity
        assert with_cache.has_cache_activity
