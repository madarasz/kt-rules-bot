"""Unit tests for health_check.py CLI command."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch

import pytest

from src.cli.health_check import HealthChecker, health_check
from src.services.discord.health import HealthStatus


class TestHealthChecker:
    """Tests for HealthChecker class."""

    @pytest.fixture
    def mock_config(self):
        """Mock configuration."""
        config = Mock()
        config.get = Mock(return_value="test_value")
        return config

    def test_initializes_with_config(self, mock_config):
        """Test that HealthChecker initializes with config."""
        checker = HealthChecker(config=mock_config)

        assert checker.config == mock_config

    @pytest.mark.asyncio
    async def test_initializes_services(self, mock_config):
        """Test service initialization."""
        checker = HealthChecker(config=mock_config)

        with patch('src.cli.health_check.RAGRetriever') as mock_rag:
            with patch('src.cli.health_check.LLMProviderFactory') as mock_factory:
                mock_rag.return_value = Mock()
                mock_llm = Mock()
                mock_factory.return_value.create.return_value = mock_llm

                rag_retriever, llm_provider = await checker._initialize_services()

                assert rag_retriever is not None
                assert llm_provider is not None
                mock_rag.assert_called_once()
                mock_factory.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_service_initialization_failure(self, mock_config):
        """Test handling of service initialization failure."""
        checker = HealthChecker(config=mock_config)

        with patch('src.cli.health_check.RAGRetriever', side_effect=Exception("Init failed")):
            with pytest.raises(Exception):
                await checker._initialize_services()

    def test_prints_healthy_status(self, mock_config, capsys):
        """Test printing healthy status."""
        checker = HealthChecker(config=mock_config)

        status = HealthStatus(
            is_healthy=True,
            discord_connected=True,
            vector_db_available=True,
            llm_provider_available=True,
            recent_error_rate=0.0,
            avg_latency_ms=50,
            timestamp=datetime.now(timezone.utc)
        )

        checker._print_status(status, verbose=False)

        captured = capsys.readouterr()
        assert "HEALTHY" in captured.out
        assert "Connected" in captured.out

    def test_prints_unhealthy_status(self, mock_config, capsys):
        """Test printing unhealthy status."""
        checker = HealthChecker(config=mock_config)

        status = HealthStatus(
            is_healthy=False,
            discord_connected=False,
            vector_db_available=True,
            llm_provider_available=False,
            recent_error_rate=0.5,
            avg_latency_ms=1000,
            timestamp=datetime.now(timezone.utc)
        )

        checker._print_status(status, verbose=False)

        captured = capsys.readouterr()
        assert "UNHEALTHY" in captured.out
        assert "Disconnected" in captured.out

    def test_prints_verbose_status(self, mock_config, capsys):
        """Test printing verbose status information."""
        checker = HealthChecker(config=mock_config)

        status = HealthStatus(
            is_healthy=True,
            discord_connected=True,
            vector_db_available=True,
            llm_provider_available=True,
            recent_error_rate=0.05,
            avg_latency_ms=75,
            timestamp=datetime.now(timezone.utc)
        )

        checker._print_status(status, verbose=True)

        captured = capsys.readouterr()
        assert "Error Rate" in captured.out
        assert "Avg Latency" in captured.out
        assert "Check Time" in captured.out

    @pytest.mark.asyncio
    async def test_run_health_check_success(self, mock_config):
        """Test successful health check run."""
        checker = HealthChecker(config=mock_config)

        with patch.object(checker, '_initialize_services') as mock_init:
            mock_rag = Mock()
            mock_llm = Mock()
            mock_init.return_value = (mock_rag, mock_llm)

            with patch('src.cli.health_check.check_health') as mock_check:
                mock_check.return_value = HealthStatus(
                    is_healthy=True,
                    discord_connected=False,
                    vector_db_available=True,
                    llm_provider_available=True,
                    recent_error_rate=0.0,
                    avg_latency_ms=50,
                    timestamp=datetime.now(timezone.utc)
                )

                is_healthy = await checker.run(verbose=False, wait_for_discord=False)

                assert is_healthy is True

    @pytest.mark.asyncio
    async def test_run_health_check_failure(self, mock_config):
        """Test health check run with unhealthy status."""
        checker = HealthChecker(config=mock_config)

        with patch.object(checker, '_initialize_services') as mock_init:
            mock_rag = Mock()
            mock_llm = Mock()
            mock_init.return_value = (mock_rag, mock_llm)

            with patch('src.cli.health_check.check_health') as mock_check:
                mock_check.return_value = HealthStatus(
                    is_healthy=False,
                    discord_connected=False,
                    vector_db_available=False,
                    llm_provider_available=True,
                    recent_error_rate=0.8,
                    avg_latency_ms=2000,
                    timestamp=datetime.now(timezone.utc)
                )

                is_healthy = await checker.run(verbose=False, wait_for_discord=False)

                assert is_healthy is False

    @pytest.mark.asyncio
    async def test_run_handles_exceptions(self, mock_config):
        """Test that run handles exceptions gracefully."""
        checker = HealthChecker(config=mock_config)

        with patch.object(checker, '_initialize_services', side_effect=Exception("Failed")):
            is_healthy = await checker.run(verbose=False, wait_for_discord=False)

            assert is_healthy is False

    @pytest.mark.asyncio
    async def test_creates_mock_bot_for_health_check(self, mock_config):
        """Test that mock bot is created when Discord not running."""
        checker = HealthChecker(config=mock_config)

        with patch.object(checker, '_initialize_services') as mock_init:
            mock_rag = Mock()
            mock_llm = Mock()
            mock_init.return_value = (mock_rag, mock_llm)

            with patch('src.cli.health_check.check_health') as mock_check:
                mock_check.return_value = HealthStatus(
                    is_healthy=True,
                    discord_connected=False,
                    vector_db_available=True,
                    llm_provider_available=True,
                    recent_error_rate=0.0,
                    avg_latency_ms=50,
                    timestamp=datetime.now(timezone.utc)
                )

                await checker.run(verbose=False, wait_for_discord=False)

                # check_health should be called with a mock bot
                assert mock_check.called


class TestHealthCheckCLI:
    """Tests for health_check CLI function."""

    @patch('src.cli.health_check.get_config')
    @patch('src.cli.health_check.asyncio.run')
    def test_successful_health_check(self, mock_asyncio_run, mock_config):
        """Test successful health check execution."""
        mock_config.return_value = Mock()
        mock_asyncio_run.return_value = True

        with pytest.raises(SystemExit) as exc_info:
            health_check(verbose=False, wait_for_discord=False)

        # Should exit with code 0 (healthy)
        assert exc_info.value.code == 0

    @patch('src.cli.health_check.get_config')
    @patch('src.cli.health_check.asyncio.run')
    def test_failed_health_check(self, mock_asyncio_run, mock_config):
        """Test failed health check execution."""
        mock_config.return_value = Mock()
        mock_asyncio_run.return_value = False

        with pytest.raises(SystemExit) as exc_info:
            health_check(verbose=False, wait_for_discord=False)

        # Should exit with code 1 (unhealthy)
        assert exc_info.value.code == 1

    @patch('src.cli.health_check.get_config')
    @patch('src.cli.health_check.asyncio.run')
    def test_handles_keyboard_interrupt(self, mock_asyncio_run, mock_config):
        """Test handling of keyboard interrupt."""
        mock_config.return_value = Mock()
        mock_asyncio_run.side_effect = KeyboardInterrupt()

        with pytest.raises(SystemExit) as exc_info:
            health_check(verbose=False, wait_for_discord=False)

        assert exc_info.value.code == 1

    @patch('src.cli.health_check.get_config')
    @patch('src.cli.health_check.asyncio.run')
    def test_handles_unexpected_exception(self, mock_asyncio_run, mock_config):
        """Test handling of unexpected exceptions."""
        mock_config.return_value = Mock()
        mock_asyncio_run.side_effect = Exception("Unexpected error")

        with pytest.raises(SystemExit) as exc_info:
            health_check(verbose=False, wait_for_discord=False)

        assert exc_info.value.code == 1

    @patch('src.cli.health_check.get_config')
    @patch('src.cli.health_check.asyncio.run')
    def test_passes_verbose_flag(self, mock_asyncio_run, mock_config):
        """Test that verbose flag is passed to checker."""
        mock_config.return_value = Mock()
        mock_asyncio_run.return_value = True

        with patch('src.cli.health_check.HealthChecker') as mock_checker_class:
            mock_checker = Mock()
            mock_checker.run = AsyncMock(return_value=True)
            mock_checker_class.return_value = mock_checker

            try:
                health_check(verbose=True, wait_for_discord=False)
            except SystemExit:
                pass

    @patch('src.cli.health_check.get_config')
    @patch('src.cli.health_check.asyncio.run')
    def test_passes_wait_for_discord_flag(self, mock_asyncio_run, mock_config):
        """Test that wait_for_discord flag is passed to checker."""
        mock_config.return_value = Mock()
        mock_asyncio_run.return_value = True

        with patch('src.cli.health_check.HealthChecker') as mock_checker_class:
            mock_checker = Mock()
            mock_checker.run = AsyncMock(return_value=True)
            mock_checker_class.return_value = mock_checker

            try:
                health_check(verbose=False, wait_for_discord=True)
            except SystemExit:
                pass
