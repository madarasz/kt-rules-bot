"""Tests for statistics formatting utilities - behavior-critical tests only."""

from src.lib.statistics import format_statistics_summary


class TestFormatStatisticsSummary:
    """Tests for format_statistics_summary function - critical cost calculation logic only."""

    def test_cost_breakdown_with_embeddings(self):
        """Test cost calculation includes embedding costs."""
        result = format_statistics_summary(
            total_time=2.0,
            initial_retrieval_time=1.5,
            query="test query",
            initial_embedding_cost=0.0001,
            hop_embedding_cost=0.0002,
        )

        assert "Total cost:" in result
        assert "Embeddings:" in result

    def test_cost_breakdown_with_llm_generation(self):
        """Test cost calculation includes LLM generation costs."""
        result = format_statistics_summary(
            total_time=3.0,
            initial_retrieval_time=1.0,
            llm_time=2.0,
            llm_cost=0.005,
            llm_prompt_tokens=1000,
            llm_completion_tokens=500,
            llm_model="gpt-4.1",
            query="test query"
        )

        assert "LLM generation: $0.005000" in result
        assert "Model: gpt-4.1" in result
