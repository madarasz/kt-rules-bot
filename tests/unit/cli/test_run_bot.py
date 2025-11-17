"""Unit tests for run_bot.py CLI command."""

import asyncio
import signal
from unittest.mock import Mock, AsyncMock, MagicMock, patch

import pytest

from src.cli.run_bot import BotRunner, run_bot


class TestBotRunner:
    """Tests for BotRunner class."""

    @pytest.fixture
    def mock_config(self):
        """Mock configuration."""
        config = Mock()
        config.discord_bot_token = "test_token"
        config.default_llm_provider = "claude-4.5-sonnet"
        return config

    def test_initializes_with_config(self, mock_config):
        """Test that BotRunner initializes with config."""
        runner = BotRunner(config=mock_config)

        assert runner.config == mock_config
        assert runner.bot is None
        assert isinstance(runner.shutdown_event, asyncio.Event)

    def test_setup_signal_handlers(self, mock_config):
        """Test signal handler setup."""
        runner = BotRunner(config=mock_config)

        with patch('signal.signal') as mock_signal:
            runner._setup_signal_handlers()

            # Should register handlers for SIGINT and SIGTERM
            assert mock_signal.call_count == 2
            calls = mock_signal.call_args_list
            assert calls[0][0][0] == signal.SIGINT
            assert calls[1][0][0] == signal.SIGTERM

    @pytest.mark.asyncio
    async def test_initialize_services_success(self, mock_config):
        """Test successful service initialization."""
        runner = BotRunner(config=mock_config)

        with patch('src.cli.run_bot.RAGRetriever') as mock_rag:
            with patch('src.cli.run_bot.LLMProviderFactory') as mock_factory:
                with patch('src.cli.run_bot.ResponseValidator') as mock_validator:
                    with patch('src.cli.run_bot.RateLimiter') as mock_limiter:
                        with patch('src.cli.run_bot.ConversationContextManager') as mock_context:
                            with patch('src.cli.run_bot.AnalyticsDatabase') as mock_analytics:
                                with patch('src.cli.run_bot.FeedbackLogger') as mock_feedback:
                                    with patch('src.cli.run_bot.KillTeamBotOrchestrator') as mock_orch:
                                        # Setup mocks
                                        mock_rag.return_value = Mock()
                                        mock_factory.return_value = Mock()
                                        mock_validator.return_value = Mock()
                                        mock_limiter.return_value = Mock()
                                        mock_context.return_value = Mock()
                                        mock_analytics.from_config.return_value = Mock(enabled=False)
                                        mock_feedback.return_value = Mock()
                                        mock_orch.return_value = Mock()

                                        orchestrator = await runner._initialize_services()

                                        assert orchestrator is not None
                                        assert mock_orch.called

    @pytest.mark.asyncio
    async def test_initialize_services_failure(self, mock_config):
        """Test handling of service initialization failure."""
        runner = BotRunner(config=mock_config)

        with patch('src.cli.run_bot.RAGRetriever', side_effect=Exception("Init failed")):
            with pytest.raises(Exception):
                await runner._initialize_services()

    @pytest.mark.asyncio
    async def test_initialize_services_with_analytics(self, mock_config):
        """Test service initialization with analytics enabled."""
        runner = BotRunner(config=mock_config)

        with patch('src.cli.run_bot.RAGRetriever') as mock_rag:
            with patch('src.cli.run_bot.LLMProviderFactory') as mock_factory:
                with patch('src.cli.run_bot.ResponseValidator') as mock_validator:
                    with patch('src.cli.run_bot.RateLimiter') as mock_limiter:
                        with patch('src.cli.run_bot.ConversationContextManager') as mock_context:
                            with patch('src.cli.run_bot.AnalyticsDatabase') as mock_analytics:
                                with patch('src.cli.run_bot.FeedbackLogger') as mock_feedback:
                                    with patch('src.cli.run_bot.KillTeamBotOrchestrator') as mock_orch:
                                        # Setup mocks
                                        mock_rag.return_value = Mock()
                                        mock_factory.return_value = Mock()
                                        mock_validator.return_value = Mock()
                                        mock_limiter.return_value = Mock()
                                        mock_context.return_value = Mock()

                                        # Analytics enabled
                                        mock_analytics_instance = Mock(enabled=True, retention_days=30)
                                        mock_analytics.from_config.return_value = mock_analytics_instance

                                        mock_feedback.return_value = Mock()
                                        mock_orch.return_value = Mock()

                                        orchestrator = await runner._initialize_services()

                                        assert orchestrator is not None

    @pytest.mark.asyncio
    async def test_run_bot_with_shutdown(self, mock_config):
        """Test bot run with graceful shutdown."""
        runner = BotRunner(config=mock_config)

        # Create mock bot
        mock_bot = MagicMock()
        mock_bot.start = AsyncMock()
        mock_bot.close = AsyncMock()
        mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)
        mock_bot.__aexit__ = AsyncMock()
        runner.bot = mock_bot

        # Trigger shutdown immediately
        async def trigger_shutdown():
            await asyncio.sleep(0.01)
            runner.shutdown_event.set()

        asyncio.create_task(trigger_shutdown())

        await runner._run_bot_with_shutdown(token="test_token")

        # Bot should be started and closed
        mock_bot.start.assert_called_once_with("test_token")
        mock_bot.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_missing_token(self, mock_config):
        """Test that run exits if token is missing."""
        mock_config.discord_bot_token = None
        runner = BotRunner(config=mock_config)

        with pytest.raises(SystemExit) as exc_info:
            await runner.run()

        assert exc_info.value.code == 1

    @pytest.mark.asyncio
    async def test_run_initialization_error(self, mock_config):
        """Test handling of initialization errors during run."""
        runner = BotRunner(config=mock_config)

        with patch.object(runner, '_initialize_services', side_effect=Exception("Init failed")):
            with pytest.raises(SystemExit):
                await runner.run()

    @pytest.mark.asyncio
    async def test_run_creates_discord_bot(self, mock_config):
        """Test that Discord bot is created with orchestrator."""
        runner = BotRunner(config=mock_config)

        with patch.object(runner, '_initialize_services') as mock_init:
            mock_orchestrator = Mock()
            mock_orchestrator.feedback_logger = Mock()
            mock_init.return_value = mock_orchestrator

            with patch('src.cli.run_bot.KillTeamBot') as mock_bot_class:
                mock_bot = MagicMock()
                mock_bot.start = AsyncMock()
                mock_bot.close = AsyncMock()
                mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)
                mock_bot.__aexit__ = AsyncMock()
                mock_bot_class.return_value = mock_bot

                # Trigger shutdown immediately
                async def trigger_shutdown():
                    await asyncio.sleep(0.01)
                    runner.shutdown_event.set()

                asyncio.create_task(trigger_shutdown())

                try:
                    await runner.run()
                except:
                    pass

                # Bot should be created with orchestrator
                mock_bot_class.assert_called_once_with(orchestrator=mock_orchestrator)


class TestRunBotCLI:
    """Tests for run_bot CLI function."""

    @patch('src.cli.run_bot.get_config')
    @patch('src.cli.run_bot.asyncio.run')
    def test_successful_bot_run(self, mock_asyncio_run, mock_config):
        """Test successful bot run."""
        mock_config.return_value = Mock()

        run_bot(mode="production")

        # Should call asyncio.run
        assert mock_asyncio_run.called

    @patch('src.cli.run_bot.get_config')
    @patch('src.cli.run_bot.asyncio.run')
    def test_handles_keyboard_interrupt(self, mock_asyncio_run, mock_config):
        """Test handling of keyboard interrupt."""
        mock_config.return_value = Mock()
        mock_asyncio_run.side_effect = KeyboardInterrupt()

        # Should not raise
        run_bot(mode="production")

    @patch('src.cli.run_bot.get_config')
    @patch('src.cli.run_bot.asyncio.run')
    def test_handles_unexpected_exception(self, mock_asyncio_run, mock_config):
        """Test handling of unexpected exceptions."""
        mock_config.return_value = Mock()
        mock_asyncio_run.side_effect = Exception("Unexpected error")

        with pytest.raises(SystemExit):
            run_bot(mode="production")

    @patch('src.cli.run_bot.get_config')
    @patch('src.cli.run_bot.asyncio.run')
    def test_accepts_dev_mode(self, mock_asyncio_run, mock_config):
        """Test that dev mode is accepted."""
        mock_config.return_value = Mock()

        run_bot(mode="dev")

        # Should not raise
        assert mock_asyncio_run.called

    @patch('src.cli.run_bot.get_config')
    @patch('src.cli.run_bot.asyncio.run')
    def test_accepts_production_mode(self, mock_asyncio_run, mock_config):
        """Test that production mode is accepted."""
        mock_config.return_value = Mock()

        run_bot(mode="production")

        # Should not raise
        assert mock_asyncio_run.called

    @patch('src.cli.run_bot.get_config')
    @patch('src.cli.run_bot.BotRunner')
    @patch('src.cli.run_bot.asyncio.run')
    def test_creates_bot_runner(self, mock_asyncio_run, mock_runner_class, mock_config):
        """Test that BotRunner is created with config."""
        mock_config_instance = Mock()
        mock_config.return_value = mock_config_instance

        mock_runner = Mock()
        mock_runner.run = AsyncMock()
        mock_runner_class.return_value = mock_runner

        run_bot(mode="production")

        # BotRunner should be created with config
        mock_runner_class.assert_called_once_with(mock_config_instance)
