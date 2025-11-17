"""Unit tests for rag_test_sweep.py CLI command."""

from unittest.mock import Mock, patch

import pytest

from src.cli.rag_test_sweep import rag_test_sweep
from src.cli.testing.parameter_parser import ParameterParser


class TestParseParameterValues:
    """Tests for ParameterParser.parse_parameter_values function."""

    def test_parses_integer_parameters(self):
        """Test parsing integer parameters."""
        result = ParameterParser.parse_parameter_values("max_chunks", "10,20,30")

        assert result == [10, 20, 30]

    def test_parses_float_parameters(self):
        """Test parsing float parameters."""
        result = ParameterParser.parse_parameter_values("min_relevance", "0.4,0.5,0.6")

        assert result == [0.4, 0.5, 0.6]

    def test_parses_string_parameters(self):
        """Test parsing string parameters."""
        result = ParameterParser.parse_parameter_values(
            "embedding_model",
            "text-embedding-3-small,text-embedding-3-large"
        )

        assert result == ["text-embedding-3-small", "text-embedding-3-large"]

    def test_handles_whitespace_in_values(self):
        """Test that whitespace is stripped from values."""
        result = ParameterParser.parse_parameter_values("max_chunks", " 10 , 20 , 30 ")

        assert result == [10, 20, 30]

    def test_raises_error_for_unknown_parameter(self):
        """Test that error is raised for unknown parameter."""
        with pytest.raises(ValueError, match="Unknown parameter"):
            ParameterParser.parse_parameter_values("unknown_param", "1,2,3")

    def test_parses_rrf_k_as_integer(self):
        """Test that rrf_k is parsed as integer."""
        result = ParameterParser.parse_parameter_values("rrf_k", "40,60,80")

        assert result == [40, 60, 80]

    def test_parses_chunk_header_level_as_integer(self):
        """Test that chunk_header_level is parsed as integer."""
        result = ParameterParser.parse_parameter_values("chunk_header_level", "2,3,4")

        assert result == [2, 3, 4]

    def test_parses_bm25_parameters_as_float(self):
        """Test that BM25 parameters are parsed as float."""
        result = ParameterParser.parse_parameter_values("bm25_k1", "1.2,1.5,1.8")
        assert result == [1.2, 1.5, 1.8]

        result = ParameterParser.parse_parameter_values("bm25_b", "0.5,0.75,1.0")
        assert result == [0.5, 0.75, 1.0]

        result = ParameterParser.parse_parameter_values("bm25_weight", "0.3,0.5,0.7")
        assert result == [0.3, 0.5, 0.7]


class TestParseGridParams:
    """Tests for ParameterParser.parse_grid_params function."""

    def test_parses_multiple_parameters(self):
        """Test parsing multiple grid parameters."""
        result = ParameterParser.parse_grid_params(
            max_chunks="10,20",
            min_relevance="0.4,0.5",
            rrf_k=None,
            bm25_k1=None,
            bm25_b=None,
            bm25_weight=None,
            embedding_model=None,
            chunk_header_level=None
        )

        assert result == {
            "max_chunks": [10, 20],
            "min_relevance": [0.4, 0.5]
        }

    def test_returns_empty_dict_when_no_parameters(self):
        """Test that empty dict is returned when no parameters provided."""
        result = ParameterParser.parse_grid_params(
            max_chunks=None,
            min_relevance=None,
            rrf_k=None,
            bm25_k1=None,
            bm25_b=None,
            bm25_weight=None,
            embedding_model=None,
            chunk_header_level=None
        )

        assert result == {}

    def test_handles_all_parameter_types(self):
        """Test parsing all parameter types."""
        result = ParameterParser.parse_grid_params(
            max_chunks="10,20",
            min_relevance="0.4,0.5",
            rrf_k="40,60",
            bm25_k1="1.2,1.5",
            bm25_b="0.5,0.75",
            bm25_weight="0.3,0.5",
            embedding_model="text-embedding-3-small,text-embedding-3-large",
            chunk_header_level="2,3"
        )

        assert len(result) == 8
        assert result["max_chunks"] == [10, 20]
        assert result["min_relevance"] == [0.4, 0.5]
        assert result["rrf_k"] == [40, 60]
        assert result["embedding_model"] == ["text-embedding-3-small", "text-embedding-3-large"]


class TestRagTestSweep:
    """Tests for rag_test_sweep function."""

    def test_requires_param_and_values_or_grid(self):
        """Test that either param/values or grid must be specified."""
        with pytest.raises(SystemExit):
            rag_test_sweep(param=None, values=None, grid=False)

    def test_rejects_both_grid_and_param_modes(self):
        """Test that grid and param modes cannot be used together."""
        with pytest.raises(SystemExit):
            rag_test_sweep(param="max_chunks", values="10,20", grid=True)

    @patch('src.cli.rag_test_sweep.RAGSweepRunner')
    @patch('src.cli.rag_test_sweep.ComparisonGenerator')
    def test_parameter_sweep_mode(self, mock_comparison_class, mock_runner_class):
        """Test parameter sweep mode."""
        mock_runner = Mock()
        mock_result = Mock()
        mock_result.summary.mean_ragas_context_precision = 0.85
        mock_result.config.get_description.return_value = "Config"
        mock_runner.sweep_parameter.return_value = [mock_result]
        mock_runner.save_sweep_results.return_value = Mock()
        mock_runner_class.return_value = mock_runner

        mock_comparison = Mock()
        mock_comparison_class.return_value = mock_comparison

        rag_test_sweep(param="rrf_k", values="40,60,80", runs=1)

        mock_runner.sweep_parameter.assert_called_once()

    @patch('src.cli.rag_test_sweep.RAGSweepRunner')
    @patch('src.cli.rag_test_sweep.ComparisonGenerator')
    def test_grid_search_mode(self, mock_comparison_class, mock_runner_class):
        """Test grid search mode."""
        mock_runner = Mock()
        mock_result = Mock()
        mock_result.summary.mean_ragas_context_precision = 0.85
        mock_result.config.get_description.return_value = "Config"
        mock_runner.grid_search.return_value = [mock_result]
        mock_runner.save_sweep_results.return_value = Mock()
        mock_runner_class.return_value = mock_runner

        mock_comparison = Mock()
        mock_comparison_class.return_value = mock_comparison

        rag_test_sweep(
            grid=True,
            max_chunks="10,20",
            min_relevance="0.4,0.5",
            runs=1
        )

        mock_runner.grid_search.assert_called_once()

    @patch('src.cli.rag_test_sweep.RAGSweepRunner')
    @patch('src.cli.rag_test_sweep.ComparisonGenerator')
    def test_handles_invalid_parameter_values(self, mock_comparison_class, mock_runner_class):
        """Test handling of invalid parameter values."""
        with pytest.raises(SystemExit):
            rag_test_sweep(param="max_chunks", values="invalid,values")

    @patch('src.cli.rag_test_sweep.RAGSweepRunner')
    @patch('src.cli.rag_test_sweep.ComparisonGenerator')
    def test_requires_at_least_one_grid_parameter(
        self,
        mock_comparison_class,
        mock_runner_class
    ):
        """Test that grid mode requires at least one parameter."""
        with pytest.raises(SystemExit):
            rag_test_sweep(grid=True, runs=1)

    @patch('src.cli.rag_test_sweep.RAGSweepRunner')
    @patch('src.cli.rag_test_sweep.ComparisonGenerator')
    def test_passes_test_id_to_runner(self, mock_comparison_class, mock_runner_class):
        """Test that test_id is passed to runner."""
        mock_runner = Mock()
        mock_result = Mock()
        mock_result.summary.mean_ragas_context_precision = 0.85
        mock_result.config.get_description.return_value = "Config"
        mock_runner.sweep_parameter.return_value = [mock_result]
        mock_runner.save_sweep_results.return_value = Mock()
        mock_runner_class.return_value = mock_runner

        mock_comparison = Mock()
        mock_comparison_class.return_value = mock_comparison

        rag_test_sweep(
            param="rrf_k",
            values="40,60",
            test_id="specific-test",
            runs=1
        )

        call_kwargs = mock_runner.sweep_parameter.call_args[1]
        assert call_kwargs['test_id'] == "specific-test"

    @patch('src.cli.rag_test_sweep.RAGSweepRunner')
    @patch('src.cli.rag_test_sweep.ComparisonGenerator')
    def test_passes_runs_to_runner(self, mock_comparison_class, mock_runner_class):
        """Test that runs parameter is passed to runner."""
        mock_runner = Mock()
        mock_result = Mock()
        mock_result.summary.mean_ragas_context_precision = 0.85
        mock_result.config.get_description.return_value = "Config"
        mock_runner.sweep_parameter.return_value = [mock_result]
        mock_runner.save_sweep_results.return_value = Mock()
        mock_runner_class.return_value = mock_runner

        mock_comparison = Mock()
        mock_comparison_class.return_value = mock_comparison

        rag_test_sweep(param="rrf_k", values="40,60", runs=5)

        call_kwargs = mock_runner.sweep_parameter.call_args[1]
        assert call_kwargs['runs'] == 5

    @patch('src.cli.rag_test_sweep.RAGSweepRunner')
    def test_handles_file_not_found_error(self, mock_runner_class):
        """Test handling of FileNotFoundError."""
        mock_runner = Mock()
        mock_runner.sweep_parameter.side_effect = FileNotFoundError("Test cases not found")
        mock_runner_class.return_value = mock_runner

        with pytest.raises(SystemExit):
            rag_test_sweep(param="rrf_k", values="40,60")

    @patch('src.cli.rag_test_sweep.RAGSweepRunner')
    def test_handles_value_error(self, mock_runner_class):
        """Test handling of ValueError."""
        mock_runner = Mock()
        mock_runner.sweep_parameter.side_effect = ValueError("Invalid config")
        mock_runner_class.return_value = mock_runner

        with pytest.raises(SystemExit):
            rag_test_sweep(param="rrf_k", values="40,60")

    @patch('src.cli.rag_test_sweep.RAGSweepRunner')
    def test_handles_generic_exception(self, mock_runner_class):
        """Test handling of generic exceptions."""
        mock_runner = Mock()
        mock_runner.sweep_parameter.side_effect = Exception("Unexpected error")
        mock_runner_class.return_value = mock_runner

        with pytest.raises(SystemExit):
            rag_test_sweep(param="rrf_k", values="40,60")

    @patch('src.cli.rag_test_sweep.RAGSweepRunner')
    @patch('src.cli.rag_test_sweep.ComparisonGenerator')
    def test_generates_comparison_report(self, mock_comparison_class, mock_runner_class):
        """Test that comparison report is generated."""
        mock_runner = Mock()
        mock_result = Mock()
        mock_result.summary.mean_ragas_context_precision = 0.85
        mock_result.summary.mean_ragas_context_recall = 0.90
        mock_result.config.get_description.return_value = "Config"
        mock_runner.sweep_parameter.return_value = [mock_result]
        mock_runner.save_sweep_results.return_value = Mock()
        mock_runner_class.return_value = mock_runner

        mock_comparison = Mock()
        mock_comparison_class.return_value = mock_comparison

        rag_test_sweep(param="rrf_k", values="40,60", runs=1)

        # Comparison report should be generated
        mock_comparison.generate_parameter_sweep_report.assert_called_once()

    @patch('src.cli.rag_test_sweep.RAGSweepRunner')
    @patch('src.cli.rag_test_sweep.ComparisonGenerator')
    def test_finds_best_configuration(self, mock_comparison_class, mock_runner_class):
        """Test that best configuration is identified."""
        mock_runner = Mock()

        # Multiple results with different scores
        mock_result1 = Mock()
        mock_result1.summary.mean_ragas_context_precision = 0.80
        mock_result1.summary.mean_ragas_context_recall = 0.85
        mock_result1.config.get_description.return_value = "Config 1"

        mock_result2 = Mock()
        mock_result2.summary.mean_ragas_context_precision = 0.90  # Best
        mock_result2.summary.mean_ragas_context_recall = 0.95
        mock_result2.config.get_description.return_value = "Config 2"

        mock_runner.sweep_parameter.return_value = [mock_result1, mock_result2]
        mock_runner.save_sweep_results.return_value = Mock()
        mock_runner_class.return_value = mock_runner

        mock_comparison = Mock()
        mock_comparison_class.return_value = mock_comparison

        # Should identify result2 as best
        rag_test_sweep(param="rrf_k", values="40,60", runs=1)
