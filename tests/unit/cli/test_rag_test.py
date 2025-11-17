"""Unit tests for rag_test.py CLI command."""

from unittest.mock import Mock, patch

import pytest

from src.cli.rag_test import rag_test


class TestRagTest:
    """Tests for rag_test function."""

    @patch('src.cli.rag_test.RAGTestRunner')
    @patch('src.cli.rag_test.RAGReportGenerator')
    def test_successful_rag_test_run(self, mock_report_gen_class, mock_runner_class):
        """Test successful RAG test execution."""
        # Mock runner
        mock_runner = Mock()
        mock_result = Mock()
        mock_result.test_id = "test-1"
        mock_result.missing_chunks = []
        mock_runner.run_tests.return_value = ([mock_result], 1.5)

        mock_summary = Mock()
        mock_summary.total_tests = 1
        mock_summary.mean_ragas_context_precision = 0.85
        mock_summary.mean_ragas_context_recall = 0.90
        mock_summary.std_dev_ragas_context_precision = 0.05
        mock_summary.std_dev_ragas_context_recall = 0.03
        mock_summary.mean_map = 0.80
        mock_summary.total_time_seconds = 1.5
        mock_summary.avg_retrieval_time_seconds = 0.5
        mock_summary.total_cost_usd = 0.001
        mock_runner.calculate_summary.return_value = mock_summary
        mock_runner_class.return_value = mock_runner

        # Mock report generator
        mock_report_gen = Mock()
        mock_report_gen_class.return_value = mock_report_gen

        # Should not raise
        rag_test(test_id=None, runs=1)

    @patch('src.cli.rag_test.RAGTestRunner')
    @patch('src.cli.rag_test.RAGReportGenerator')
    def test_runs_specific_test(self, mock_report_gen_class, mock_runner_class):
        """Test running a specific test by ID."""
        mock_runner = Mock()
        mock_result = Mock()
        mock_result.test_id = "specific-test"
        mock_result.missing_chunks = []
        mock_runner.run_tests.return_value = ([mock_result], 1.0)

        mock_summary = Mock()
        mock_summary.total_tests = 1
        mock_summary.mean_ragas_context_precision = 0.85
        mock_summary.mean_ragas_context_recall = 0.90
        mock_summary.std_dev_ragas_context_precision = 0.05
        mock_summary.std_dev_ragas_context_recall = 0.03
        mock_summary.mean_map = 0.80
        mock_summary.total_time_seconds = 1.0
        mock_summary.avg_retrieval_time_seconds = 0.5
        mock_summary.total_cost_usd = 0.001
        mock_runner.calculate_summary.return_value = mock_summary
        mock_runner_class.return_value = mock_runner

        mock_report_gen = Mock()
        mock_report_gen_class.return_value = mock_report_gen

        rag_test(test_id="specific-test", runs=1)

        # Check that test_id was passed to runner
        mock_runner.run_tests.assert_called_once()
        call_kwargs = mock_runner.run_tests.call_args[1]
        assert call_kwargs['test_id'] == "specific-test"

    @patch('src.cli.rag_test.RAGTestRunner')
    @patch('src.cli.rag_test.RAGReportGenerator')
    def test_runs_multiple_iterations(self, mock_report_gen_class, mock_runner_class):
        """Test running tests multiple times."""
        mock_runner = Mock()
        mock_result = Mock()
        mock_result.test_id = "test-1"
        mock_result.missing_chunks = []
        mock_runner.run_tests.return_value = ([mock_result], 1.0)

        mock_summary = Mock()
        mock_summary.total_tests = 1
        mock_summary.mean_ragas_context_precision = 0.85
        mock_summary.mean_ragas_context_recall = 0.90
        mock_summary.std_dev_ragas_context_precision = 0.05
        mock_summary.std_dev_ragas_context_recall = 0.03
        mock_summary.mean_map = 0.80
        mock_summary.total_time_seconds = 1.0
        mock_summary.avg_retrieval_time_seconds = 0.5
        mock_summary.total_cost_usd = 0.001
        mock_runner.calculate_summary.return_value = mock_summary
        mock_runner_class.return_value = mock_runner

        mock_report_gen = Mock()
        mock_report_gen_class.return_value = mock_report_gen

        rag_test(runs=5)

        call_kwargs = mock_runner.run_tests.call_args[1]
        assert call_kwargs['runs'] == 5

    @patch('src.cli.rag_test.RAGTestRunner')
    @patch('src.cli.rag_test.RAGReportGenerator')
    def test_uses_custom_max_chunks(self, mock_report_gen_class, mock_runner_class):
        """Test using custom max_chunks parameter."""
        mock_runner = Mock()
        mock_result = Mock()
        mock_result.test_id = "test-1"
        mock_result.missing_chunks = []
        mock_runner.run_tests.return_value = ([mock_result], 1.0)

        mock_summary = Mock()
        mock_summary.total_tests = 1
        mock_summary.mean_ragas_context_precision = 0.85
        mock_summary.mean_ragas_context_recall = 0.90
        mock_summary.std_dev_ragas_context_precision = 0.05
        mock_summary.std_dev_ragas_context_recall = 0.03
        mock_summary.mean_map = 0.80
        mock_summary.total_time_seconds = 1.0
        mock_summary.avg_retrieval_time_seconds = 0.5
        mock_summary.total_cost_usd = 0.001
        mock_runner.calculate_summary.return_value = mock_summary
        mock_runner_class.return_value = mock_runner

        mock_report_gen = Mock()
        mock_report_gen_class.return_value = mock_report_gen

        rag_test(max_chunks=20, runs=1)

        call_kwargs = mock_runner.run_tests.call_args[1]
        assert call_kwargs['max_chunks'] == 20

    @patch('src.cli.rag_test.RAGTestRunner')
    @patch('src.cli.rag_test.RAGReportGenerator')
    def test_uses_custom_min_relevance(self, mock_report_gen_class, mock_runner_class):
        """Test using custom min_relevance parameter."""
        mock_runner = Mock()
        mock_result = Mock()
        mock_result.test_id = "test-1"
        mock_result.missing_chunks = []
        mock_runner.run_tests.return_value = ([mock_result], 1.0)

        mock_summary = Mock()
        mock_summary.total_tests = 1
        mock_summary.mean_ragas_context_precision = 0.85
        mock_summary.mean_ragas_context_recall = 0.90
        mock_summary.std_dev_ragas_context_precision = 0.05
        mock_summary.std_dev_ragas_context_recall = 0.03
        mock_summary.mean_map = 0.80
        mock_summary.total_time_seconds = 1.0
        mock_summary.avg_retrieval_time_seconds = 0.5
        mock_summary.total_cost_usd = 0.001
        mock_runner.calculate_summary.return_value = mock_summary
        mock_runner_class.return_value = mock_runner

        mock_report_gen = Mock()
        mock_report_gen_class.return_value = mock_report_gen

        rag_test(min_relevance=0.6, runs=1)

        call_kwargs = mock_runner.run_tests.call_args[1]
        assert call_kwargs['min_relevance'] == 0.6

    @patch('src.cli.rag_test.RAGTestRunner')
    @patch('src.cli.rag_test.RAGReportGenerator')
    def test_handles_no_results(self, mock_report_gen_class, mock_runner_class):
        """Test handling when no results are generated."""
        mock_runner = Mock()
        mock_runner.run_tests.return_value = ([], 0.0)
        mock_runner_class.return_value = mock_runner

        mock_report_gen = Mock()
        mock_report_gen_class.return_value = mock_report_gen

        # Should not raise, just return early
        rag_test(runs=1)

    @patch('src.cli.rag_test.RAGTestRunner')
    def test_handles_file_not_found_error(self, mock_runner_class):
        """Test handling of FileNotFoundError."""
        mock_runner = Mock()
        mock_runner.run_tests.side_effect = FileNotFoundError("Test cases not found")
        mock_runner_class.return_value = mock_runner

        with pytest.raises(SystemExit):
            rag_test()

    @patch('src.cli.rag_test.RAGTestRunner')
    def test_handles_value_error(self, mock_runner_class):
        """Test handling of ValueError."""
        mock_runner = Mock()
        mock_runner.run_tests.side_effect = ValueError("Invalid test config")
        mock_runner_class.return_value = mock_runner

        with pytest.raises(SystemExit):
            rag_test()

    @patch('src.cli.rag_test.RAGTestRunner')
    def test_handles_generic_exception(self, mock_runner_class):
        """Test handling of generic exceptions."""
        mock_runner = Mock()
        mock_runner.run_tests.side_effect = Exception("Unexpected error")
        mock_runner_class.return_value = mock_runner

        with pytest.raises(SystemExit):
            rag_test()

    @patch('src.cli.rag_test.RAGTestRunner')
    @patch('src.cli.rag_test.RAGReportGenerator')
    def test_displays_missing_chunks(self, mock_report_gen_class, mock_runner_class):
        """Test that missing chunks are displayed."""
        mock_runner = Mock()
        mock_result = Mock()
        mock_result.test_id = "test-1"
        mock_result.missing_chunks = ["chunk-1", "chunk-2"]
        mock_runner.run_tests.return_value = ([mock_result], 1.0)

        mock_summary = Mock()
        mock_summary.total_tests = 1
        mock_summary.mean_ragas_context_precision = 0.85
        mock_summary.mean_ragas_context_recall = 0.90
        mock_summary.std_dev_ragas_context_precision = 0.05
        mock_summary.std_dev_ragas_context_recall = 0.03
        mock_summary.mean_map = 0.80
        mock_summary.total_time_seconds = 1.0
        mock_summary.avg_retrieval_time_seconds = 0.5
        mock_summary.total_cost_usd = 0.001
        mock_runner.calculate_summary.return_value = mock_summary
        mock_runner_class.return_value = mock_runner

        mock_report_gen = Mock()
        mock_report_gen_class.return_value = mock_report_gen

        # Should not raise and should print missing chunks
        rag_test(runs=1)

    @patch('src.cli.rag_test.RAGTestRunner')
    @patch('src.cli.rag_test.RAGReportGenerator')
    @patch('src.cli.rag_test.Path')
    def test_generates_report_file(self, mock_path, mock_report_gen_class, mock_runner_class):
        """Test that report file is generated."""
        mock_runner = Mock()
        mock_result = Mock()
        mock_result.test_id = "test-1"
        mock_result.missing_chunks = []
        mock_runner.run_tests.return_value = ([mock_result], 1.0)

        mock_summary = Mock()
        mock_summary.total_tests = 1
        mock_summary.mean_ragas_context_precision = 0.85
        mock_summary.mean_ragas_context_recall = 0.90
        mock_summary.std_dev_ragas_context_precision = 0.05
        mock_summary.std_dev_ragas_context_recall = 0.03
        mock_summary.mean_map = 0.80
        mock_summary.total_time_seconds = 1.0
        mock_summary.avg_retrieval_time_seconds = 0.5
        mock_summary.total_cost_usd = 0.001
        mock_runner.calculate_summary.return_value = mock_summary
        mock_runner_class.return_value = mock_runner

        mock_report_gen = Mock()
        mock_report_gen_class.return_value = mock_report_gen

        rag_test(runs=1)

        # Report should be generated
        mock_report_gen.generate_report.assert_called_once()
        mock_report_gen.save_retrieved_chunks.assert_called_once()
