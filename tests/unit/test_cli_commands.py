"""Unit tests for CLI commands."""

import asyncio
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest

from src.cli.gdpr_delete import delete_user_data
from src.cli.health_check import HealthChecker
from src.cli.run_bot import BotRunner
from src.models.rule_document import RuleDocument
from src.models.rag_context import DocumentChunk, RAGContext
from src.services.discord.health import HealthStatus
from src.services.llm.base import LLMResponse


# --- Fixtures ---


@pytest.fixture
def mock_config():
    """Mock configuration."""
    config = Mock()
    config.get = Mock(
        side_effect=lambda key, default=None: {
            "discord.token": "test_token_123",
            "vectordb.collection_name": "test_collection",
            "vectordb.persist_directory": "./test_data/vectordb",
            "llm.provider": "claude",
            "environment": "test",
        }.get(key, default)
    )
    config.vector_db_path = "./test_data/vectordb"
    return config


@pytest.fixture
def mock_logger():
    """Mock logger."""
    with patch("src.lib.logging.get_logger") as mock:
        yield mock.return_value


@pytest.fixture
def sample_rule_document():
    """Sample rule document for testing."""
    return RuleDocument(
        document_id=uuid4(),
        filename="test-rule.md",
        content="# Test Rule\n\nThis is a test rule.",
        metadata={
            "source": "Test",
            "last_update_date": "2024-01-01",
            "document_type": "core-rules",
        },
        version="Test Source v1.0",
        last_update_date=date(2024, 1, 1),
        document_type="core-rules",
        last_updated=datetime.now(timezone.utc),
        hash=RuleDocument.compute_hash("# Test Rule\n\nThis is a test rule."),
    )


# --- Test: ingest_rules ---


def test_ingest_rules_validates_source_dir():
    """Test that ingest_rules validates source directory exists."""
    from src.cli.ingest_rules import ingest_rules

    # Should raise FileNotFoundError for non-existent directory
    with pytest.raises(FileNotFoundError):
        ingest_rules(source_dir="/nonexistent/path", force=False)


# --- Test: health_check ---


@pytest.mark.asyncio
async def test_health_checker_initializes_services(mock_config):
    """Test that HealthChecker initializes required services."""
    checker = HealthChecker(config=mock_config)

    with patch("src.cli.health_check.RAGRetriever") as mock_rag:
        with patch("src.cli.health_check.LLMProviderFactory") as mock_factory:
            mock_factory.return_value.create.return_value = Mock()
            mock_rag.return_value = Mock()

            try:
                await checker._initialize_services()
                # Should not raise
            except Exception as e:
                pytest.fail(f"Service initialization failed: {e}")


@pytest.mark.asyncio
async def test_health_checker_returns_status(mock_config):
    """Test that HealthChecker returns health status."""
    checker = HealthChecker(config=mock_config)

    # Mock services
    with patch("src.cli.health_check.RAGRetriever"):
        with patch("src.cli.health_check.LLMProviderFactory"):
            with patch("src.cli.health_check.check_health") as mock_check:
                mock_check.return_value = HealthStatus(
                    is_healthy=True,
                    discord_connected=False,
                    vector_db_available=True,
                    llm_provider_available=True,
                    recent_error_rate=0.0,
                    avg_latency_ms=0,
                    timestamp=datetime.now(timezone.utc),
                )

                is_healthy = await checker.run(verbose=False, wait_for_discord=False)

                assert is_healthy is True
                assert mock_check.called


# --- Test: run_bot ---


@pytest.mark.asyncio
async def test_bot_runner_initializes_orchestrator(mock_config):
    """Test that BotRunner initializes orchestrator with all services."""
    runner = BotRunner(config=mock_config)

    with patch("src.cli.run_bot.RAGRetriever") as mock_rag:
        with patch("src.cli.run_bot.LLMProviderFactory") as mock_factory:
            with patch("src.cli.run_bot.ResponseValidator") as mock_validator:
                with patch("src.cli.run_bot.RateLimiter") as mock_limiter:
                    with patch("src.cli.run_bot.ConversationContextManager") as mock_context:
                        with patch(
                            "src.cli.run_bot.KillTeamBotOrchestrator"
                        ) as mock_orch:
                            mock_rag.return_value = Mock()
                            mock_factory.return_value = Mock()
                            mock_validator.return_value = Mock()
                            mock_limiter.return_value = Mock()
                            mock_context.return_value = Mock()
                            mock_orch.return_value = Mock()

                            orchestrator = await runner._initialize_services()

                            # Verify all services initialized
                            assert mock_rag.called
                            assert mock_factory.called
                            assert mock_validator.called
                            assert mock_limiter.called
                            assert mock_context.called
                            assert mock_orch.called


@pytest.mark.asyncio
async def test_bot_runner_handles_missing_token(mock_config):
    """Test that BotRunner exits if Discord token is missing."""
    # Override config to return None for token
    mock_config.discord_bot_token = None

    runner = BotRunner(config=mock_config)

    with pytest.raises(SystemExit) as exc_info:
        await runner.run()

    assert exc_info.value.code == 1


# --- Test: gdpr_delete ---


@patch("src.cli.gdpr_delete.get_logger")
@patch("builtins.input")
def test_gdpr_delete_requires_confirmation(mock_input, mock_logger):
    """Test that gdpr_delete requires confirmation."""
    mock_input.return_value = "no"

    # Should exit without deleting
    delete_user_data(user_id="123456789", confirm=False)

    # Verify confirmation was requested
    assert mock_input.called


@patch("src.cli.gdpr_delete.get_logger")
@patch("builtins.input")
def test_gdpr_delete_with_confirm_flag(mock_input, mock_logger):
    """Test that gdpr_delete skips confirmation with --confirm flag."""
    # Should not prompt for confirmation
    delete_user_data(user_id="123456789", confirm=True)

    # Verify confirmation was NOT requested
    assert not mock_input.called


# --- Test: __main__ ---


@patch("src.cli.__main__.run_bot")
def test_main_routes_run_command(mock_run_bot):
    """Test that main routes 'run' command correctly."""
    with patch("sys.argv", ["cli", "run", "--mode", "dev"]):
        from src.cli.__main__ import main

        try:
            main()
        except SystemExit:
            pass

        # Verify run_bot was called
        mock_run_bot.assert_called_once_with(mode="dev")


@patch("src.cli.__main__.ingest_rules")
def test_main_routes_ingest_command(mock_ingest):
    """Test that main routes 'ingest' command correctly."""
    with patch("sys.argv", ["cli", "ingest", "./rules", "--force"]):
        from src.cli.__main__ import main

        try:
            main()
        except SystemExit:
            pass

        # Verify ingest_rules was called
        mock_ingest.assert_called_once_with(source_dir="./rules", force=True)


@patch("src.cli.__main__.test_query")
def test_main_routes_query_command(mock_query):
    """Test that main routes 'query' command correctly."""
    with patch("sys.argv", ["cli", "query", "test query", "--provider", "claude-sonnet"]):
        from src.cli.__main__ import main

        try:
            main()
        except SystemExit:
            pass

        # Verify test_query was called
        mock_query.assert_called_once_with(query="test query", provider="claude-sonnet", max_chunks=5)


@patch("src.cli.__main__.health_check")
def test_main_routes_health_command(mock_health):
    """Test that main routes 'health' command correctly."""
    with patch("sys.argv", ["cli", "health", "-v"]):
        from src.cli.__main__ import main

        try:
            main()
        except SystemExit:
            pass

        # Verify health_check was called
        mock_health.assert_called_once_with(verbose=True, wait_for_discord=False)


@patch("src.cli.__main__.delete_user_data")
def test_main_routes_gdpr_delete_command(mock_delete):
    """Test that main routes 'gdpr-delete' command correctly."""
    with patch("sys.argv", ["cli", "gdpr-delete", "123456", "--confirm"]):
        from src.cli.__main__ import main

        try:
            main()
        except SystemExit:
            pass

        # Verify delete_user_data was called
        mock_delete.assert_called_once_with(user_id="123456", confirm=True)
