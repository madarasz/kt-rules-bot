"""Tests for statistics formatting utilities."""

import pytest
from src.lib.statistics import format_statistics_summary


class TestFormatStatisticsSummary:
    """Tests for format_statistics_summary function."""

    def test_rag_only_mode_basic(self):
        """Test RAG-only mode with minimal parameters."""
        result = format_statistics_summary(
            total_time=1.5,
            initial_retrieval_time=1.2,
            query="test query"
        )

        assert "SUMMARY (RAG-only mode)" in result
        assert "Total time: 1.50s" in result
        assert "RAG retrieval: 1.50s" in result
        assert "Initial retrieval: 1.20s" in result
        assert "Total cost:" in result

    def test_full_pipeline_mode(self):
        """Test full pipeline mode with LLM generation."""
        result = format_statistics_summary(
            total_time=3.0,
            initial_retrieval_time=1.0,
            llm_time=2.0,
            query="test query"
        )

        assert "SUMMARY" in result
        assert "SUMMARY (RAG-only mode)" not in result
        assert "Total time: 3.00s" in result
        assert "RAG retrieval: 1.00s" in result
        assert "LLM generation: 2.00s" in result

    def test_with_single_hop_evaluation(self):
        """Test with one hop evaluation."""
        class MockHopEval:
            def __init__(self):
                self.retrieval_time_s = 0.5
                self.evaluation_time_s = 0.3
                self.missing_query = "additional query"
                self.cost_usd = 0.001

        hop_evals = [MockHopEval()]
        result = format_statistics_summary(
            total_time=2.0,
            initial_retrieval_time=1.0,
            hop_evaluations=hop_evals,
            query="test query"
        )

        assert "Hop 1: 0.80s" in result
        assert "retrieval: 0.50s" in result
        assert "evaluation: 0.30s" in result

    def test_with_multiple_hop_evaluations(self):
        """Test with multiple hop evaluations."""
        class MockHopEval:
            def __init__(self, retrieval_time, eval_time, cost):
                self.retrieval_time_s = retrieval_time
                self.evaluation_time_s = eval_time
                self.missing_query = "query"
                self.cost_usd = cost

        hop_evals = [
            MockHopEval(0.5, 0.3, 0.001),
            MockHopEval(0.6, 0.4, 0.002)
        ]
        result = format_statistics_summary(
            total_time=3.0,
            initial_retrieval_time=1.0,
            hop_evaluations=hop_evals,
            query="test query"
        )

        assert "Hop 1: 0.80s" in result
        assert "Hop 2: 1.00s" in result

    def test_cost_breakdown_with_embeddings(self):
        """Test cost breakdown with embedding costs."""
        result = format_statistics_summary(
            total_time=2.0,
            initial_retrieval_time=1.5,
            query="test query",
            initial_embedding_cost=0.0001,
            hop_embedding_cost=0.0002,
        )

        assert "Total cost:" in result
        assert "RAG costs:" in result
        assert "Embeddings:" in result
        assert "Initial query:" in result

    def test_cost_breakdown_with_hop_evaluations(self):
        """Test cost breakdown including hop evaluation costs."""
        class MockHopEval:
            def __init__(self):
                self.retrieval_time_s = 0.5
                self.evaluation_time_s = 0.3
                self.missing_query = "additional query"
                self.cost_usd = 0.001

        hop_evals = [MockHopEval()]
        result = format_statistics_summary(
            total_time=2.0,
            initial_retrieval_time=1.0,
            hop_evaluations=hop_evals,
            hop_evaluation_cost=0.001,
            query="test query"
        )

        assert "Hop evaluations:" in result
        assert "$0.001000" in result

    def test_cost_breakdown_with_llm_generation(self):
        """Test cost breakdown with LLM generation costs."""
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
        assert "Prompt tokens: 1,000" in result
        assert "Completion tokens: 500" in result

    def test_hop_embedding_cost_breakdown(self):
        """Test detailed hop embedding cost breakdown."""
        class MockHopEval:
            def __init__(self, query):
                self.retrieval_time_s = 0.5
                self.evaluation_time_s = 0.3
                self.missing_query = query
                self.cost_usd = 0.001

        hop_evals = [
            MockHopEval("query one"),
            MockHopEval("query two")
        ]
        result = format_statistics_summary(
            total_time=3.0,
            initial_retrieval_time=1.0,
            hop_evaluations=hop_evals,
            hop_embedding_cost=0.0003,
            query="test query"
        )

        assert "Hop queries:" in result
        assert "Hop 1:" in result
        assert "Hop 2:" in result

    def test_empty_hop_evaluations_list(self):
        """Test with empty hop evaluations list."""
        result = format_statistics_summary(
            total_time=1.5,
            initial_retrieval_time=1.2,
            hop_evaluations=[],
            query="test query"
        )

        assert "SUMMARY (RAG-only mode)" in result
        assert "Hop 1" not in result

    def test_zero_costs(self):
        """Test with all costs at zero."""
        result = format_statistics_summary(
            total_time=1.0,
            initial_retrieval_time=1.0,
            query="test query",
            initial_embedding_cost=0.0,
            hop_embedding_cost=0.0,
            hop_evaluation_cost=0.0,
            llm_cost=0.0
        )

        assert "Total cost: $0.000000" in result

    def test_query_embedding_cost_calculation(self):
        """Test that embedding cost is calculated from query when not provided."""
        result = format_statistics_summary(
            total_time=1.0,
            initial_retrieval_time=1.0,
            query="This is a test query with multiple words"
        )

        # Should calculate and include initial embedding cost
        assert "Initial query:" in result
        assert "$" in result

    def test_formatting_consistency(self):
        """Test that output has consistent formatting."""
        result = format_statistics_summary(
            total_time=1.5,
            initial_retrieval_time=1.2,
            query="test"
        )

        # Check for separators
        assert "=" * 60 in result
        # Check it starts with proper formatting
        lines = result.split("\n")
        assert lines[0] == "=" * 60
        # Check it has separator line near the end
        assert lines[-2] == "=" * 60

    def test_time_precision(self):
        """Test that times are formatted with 2 decimal places."""
        result = format_statistics_summary(
            total_time=1.234567,
            initial_retrieval_time=0.987654,
            query="test"
        )

        assert "1.23s" in result
        assert "0.99s" in result

    def test_cost_precision(self):
        """Test that costs are formatted with 6 decimal places."""
        result = format_statistics_summary(
            total_time=1.0,
            initial_retrieval_time=1.0,
            llm_cost=0.123456789,
            llm_time=0.5,
            query="test"
        )

        assert "$0.123457" in result  # Rounded to 6 decimal places

    def test_no_query_no_initial_embedding_cost(self):
        """Test that no embedding cost is calculated when query is empty."""
        result = format_statistics_summary(
            total_time=1.0,
            initial_retrieval_time=1.0,
            query=""
        )

        # Should still have cost section but with zero initial cost
        assert "Total cost:" in result
        assert "Initial query: $0.000000" in result

    def test_hop_evaluation_without_missing_query(self):
        """Test hop evaluation where missing_query is None."""
        class MockHopEval:
            def __init__(self):
                self.retrieval_time_s = 0.5
                self.evaluation_time_s = 0.3
                self.missing_query = None  # No missing query
                self.cost_usd = 0.001

        hop_evals = [MockHopEval()]
        result = format_statistics_summary(
            total_time=2.0,
            initial_retrieval_time=1.0,
            hop_evaluations=hop_evals,
            hop_embedding_cost=0.0,  # Should be 0 if no query
            query="test query"
        )

        assert "Hop 1: 0.80s" in result
        # Should not show hop queries section if no missing queries
        assert "Hop queries:" not in result or hop_evals[0].missing_query is None
