"""Unit tests for quality_test.py CLI command."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

import pytest

from src.cli.quality_test import quality_test, _print_configuration


class TestQualityTest:
    """Tests for quality_test function."""

    @patch('src.cli.quality_test.QualityTestRunner')
    @patch('src.lib.config.get_config')
    @patch('src.cli.quality_test.asyncio.run')
    @patch('src.cli.quality_test.aggregate_results')
    @patch('src.cli.quality_test.ReportGenerator')
    @patch('builtins.input', return_value='y')
    def test_successful_quality_test_run(
        self,
        mock_input,
        mock_report_gen_class,
        mock_aggregate,
        mock_asyncio_run,
        mock_config,
        mock_runner_class
    ):
        """Test successful quality test execution."""
        # Mock config
        mock_config.return_value.default_llm_provider = "claude-4.5-sonnet"

        # Mock runner
        mock_runner = Mock()
        mock_test_case = Mock()
        mock_test_case.test_id = "test-1"
        mock_runner.load_test_cases.return_value = [mock_test_case]
        mock_runner_class.return_value = mock_runner

        # Mock test results
        mock_result = Mock()
        mock_result.total_cost_usd = 0.05
        mock_asyncio_run.return_value = [mock_result]

        # Mock report generator
        mock_report_gen = Mock()
        mock_report_gen.get_console_output.return_value = "Test results"
        mock_report_gen_class.return_value = mock_report_gen

        # Should not raise
        quality_test(test_id=None, skip_confirm=False)

    @patch('src.cli.quality_test.QualityTestRunner')
    def test_handles_test_case_loading_failure(self, mock_runner_class):
        """Test handling of test case loading failure."""
        mock_runner = Mock()
        mock_runner.load_test_cases.side_effect = Exception("Load failed")
        mock_runner_class.return_value = mock_runner

        with pytest.raises(SystemExit):
            quality_test()

    @patch('src.cli.quality_test.QualityTestRunner')
    def test_exits_when_no_test_cases_found(self, mock_runner_class):
        """Test that CLI exits when no test cases found."""
        mock_runner = Mock()
        mock_runner.load_test_cases.return_value = []
        mock_runner_class.return_value = mock_runner

        with pytest.raises(SystemExit):
            quality_test()

    @patch('src.cli.quality_test.QualityTestRunner')
    @patch('builtins.input', return_value='n')
    def test_handles_user_cancellation(self, mock_input, mock_runner_class):
        """Test handling of user cancelling confirmation."""
        mock_runner = Mock()
        mock_test_case = Mock()
        mock_test_case.test_id = "test-1"
        mock_runner.load_test_cases.return_value = [mock_test_case]
        mock_runner_class.return_value = mock_runner

        with pytest.raises(SystemExit) as exc_info:
            quality_test(skip_confirm=False)

        assert exc_info.value.code == 0

    @patch('src.cli.quality_test.QualityTestRunner')
    @patch('src.lib.config.get_config')
    @patch('builtins.input', return_value='y')
    def test_skips_confirmation_with_flag(
        self,
        mock_input,
        mock_config,
        mock_runner_class
    ):
        """Test that confirmation is skipped with --yes flag."""
        mock_config.return_value.default_llm_provider = "claude-4.5-sonnet"

        mock_runner = Mock()
        mock_test_case = Mock()
        mock_test_case.test_id = "test-1"
        mock_runner.load_test_cases.return_value = [mock_test_case]
        mock_runner_class.return_value = mock_runner

        with patch('src.cli.quality_test.asyncio.run'):
            with patch('src.cli.quality_test.aggregate_results'):
                with patch('src.cli.quality_test.ReportGenerator'):
                    quality_test(skip_confirm=True)

        # input() should not be called
        assert not mock_input.called

    @patch('src.cli.quality_test.QualityTestRunner')
    @patch('builtins.input', return_value='y')
    def test_uses_specific_model_when_provided(
        self,
        mock_input,
        mock_runner_class
    ):
        """Test that specific model is used when provided."""
        mock_runner = Mock()
        mock_test_case = Mock()
        mock_test_case.test_id = "test-1"
        mock_runner.load_test_cases.return_value = [mock_test_case]
        mock_runner_class.return_value = mock_runner

        with patch('src.cli.quality_test.asyncio.run'):
            with patch('src.cli.quality_test.aggregate_results'):
                with patch('src.cli.quality_test.ReportGenerator'):
                    quality_test(model="gpt-4.1", skip_confirm=True)

    @patch('src.cli.quality_test.QualityTestRunner')
    @patch('builtins.input', return_value='y')
    def test_tests_all_models_when_flag_set(
        self,
        mock_input,
        mock_runner_class
    ):
        """Test that all models are tested when --all-models flag set."""
        mock_runner = Mock()
        mock_test_case = Mock()
        mock_test_case.test_id = "test-1"
        mock_runner.load_test_cases.return_value = [mock_test_case]
        mock_runner_class.return_value = mock_runner

        with patch('src.cli.quality_test.asyncio.run'):
            with patch('src.cli.quality_test.aggregate_results'):
                with patch('src.cli.quality_test.ReportGenerator'):
                    quality_test(all_models=True, skip_confirm=True)

    @patch('src.cli.quality_test.QualityTestRunner')
    @patch('builtins.input', return_value='y')
    def test_overrides_rag_max_hops(
        self,
        mock_input,
        mock_runner_class
    ):
        """Test that RAG_MAX_HOPS is overridden when specified."""
        import src.lib.constants as constants
        original_hops = constants.RAG_MAX_HOPS

        mock_runner = Mock()
        mock_test_case = Mock()
        mock_test_case.test_id = "test-1"
        mock_runner.load_test_cases.return_value = [mock_test_case]
        mock_runner_class.return_value = mock_runner

        with patch('src.cli.quality_test.asyncio.run'):
            with patch('src.cli.quality_test.aggregate_results'):
                with patch('src.cli.quality_test.ReportGenerator'):
                    quality_test(max_hops=2, skip_confirm=True)

        # Should be restored after test
        assert constants.RAG_MAX_HOPS == original_hops

    @patch('src.cli.quality_test.QualityTestRunner')
    @patch('src.lib.config.get_config')
    @patch('builtins.input', return_value='y')
    @patch('src.cli.quality_test.asyncio.run')
    def test_handles_test_execution_failure(
        self,
        mock_asyncio_run,
        mock_input,
        mock_config,
        mock_runner_class
    ):
        """Test handling of test execution failure."""
        mock_config.return_value.default_llm_provider = "claude-4.5-sonnet"

        mock_runner = Mock()
        mock_test_case = Mock()
        mock_test_case.test_id = "test-1"
        mock_runner.load_test_cases.return_value = [mock_test_case]
        mock_runner_class.return_value = mock_runner

        mock_asyncio_run.side_effect = Exception("Test failed")

        with pytest.raises(SystemExit):
            quality_test(skip_confirm=True)

    @patch('src.cli.quality_test.QualityTestRunner')
    @patch('src.lib.config.get_config')
    @patch('builtins.input', return_value='y')
    @patch('src.cli.quality_test.asyncio.run')
    @patch('src.cli.quality_test.aggregate_results')
    @patch('src.cli.quality_test.ReportGenerator')
    def test_creates_report_directory(
        self,
        mock_report_gen_class,
        mock_aggregate,
        mock_asyncio_run,
        mock_input,
        mock_config,
        mock_runner_class
    ):
        """Test that report directory is created with timestamp."""
        mock_config.return_value.default_llm_provider = "claude-4.5-sonnet"

        mock_runner = Mock()
        mock_test_case = Mock()
        mock_test_case.test_id = "test-1"
        mock_runner.load_test_cases.return_value = [mock_test_case]
        mock_runner_class.return_value = mock_runner

        mock_result = Mock()
        mock_result.total_cost_usd = 0.05
        mock_asyncio_run.return_value = [mock_result]

        mock_report_gen = Mock()
        mock_report_gen.get_console_output.return_value = "Results"
        mock_report_gen_class.return_value = mock_report_gen

        with patch('src.cli.quality_test.Path') as mock_path:
            quality_test(skip_confirm=True)

            # Report directory should be created
            assert mock_path.called

    @patch('src.cli.quality_test.QualityTestRunner')
    @patch('src.lib.config.get_config')
    @patch('builtins.input', return_value='y')
    @patch('src.cli.quality_test.asyncio.run')
    @patch('src.cli.quality_test.aggregate_results')
    @patch('src.cli.quality_test.ReportGenerator')
    def test_no_eval_mode(
        self,
        mock_report_gen_class,
        mock_aggregate,
        mock_asyncio_run,
        mock_input,
        mock_config,
        mock_runner_class
    ):
        """Test no-eval mode (output generation only)."""
        mock_config.return_value.default_llm_provider = "claude-4.5-sonnet"

        mock_runner = Mock()
        mock_test_case = Mock()
        mock_test_case.test_id = "test-1"
        mock_runner.load_test_cases.return_value = [mock_test_case]
        mock_runner_class.return_value = mock_runner

        mock_result = Mock()
        mock_result.total_cost_usd = 0.05
        mock_asyncio_run.return_value = [mock_result]

        mock_report_gen = Mock()
        mock_report_gen.get_console_output.return_value = "Results"
        mock_report_gen_class.return_value = mock_report_gen

        quality_test(no_eval=True, skip_confirm=True)

        # Should pass no_eval to runner
        call_kwargs = mock_asyncio_run.call_args[0][0]  # Get the coroutine that would be run


class TestPrintConfiguration:
    """Tests for _print_configuration helper function."""

    def test_prints_configuration(self, capsys):
        """Test that configuration is printed correctly."""
        mock_test_cases = [
            Mock(test_id="test-1"),
            Mock(test_id="test-2"),
        ]
        models = ["claude-4.5-sonnet", "gpt-4.1"]

        _print_configuration(mock_test_cases, models, runs=3, judge_model="claude-4.5-sonnet")

        captured = capsys.readouterr()
        assert "test-1" in captured.out
        assert "test-2" in captured.out
        assert "claude-4.5-sonnet" in captured.out
        assert "3" in captured.out

    def test_prints_no_eval_mode(self, capsys):
        """Test that no-eval mode is indicated."""
        mock_test_cases = [Mock(test_id="test-1")]
        models = ["claude-4.5-sonnet"]

        _print_configuration(
            mock_test_cases, models, runs=1, judge_model="claude-4.5-sonnet", no_eval=True
        )

        captured = capsys.readouterr()
        assert "DISABLED" in captured.out
