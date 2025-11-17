"""Smoke tests: verify all critical components load and respond.

These tests run on every commit to catch basic configuration/import issues.
"""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from src.models.bot_response import BotResponse, Citation
from src.services.llm.validator import ValidationResult


@pytest.mark.smoke
@pytest.mark.fast
def test_llm_factory_available():
    """Test LLM factory can list available providers."""
    from src.services.llm.factory import LLMProviderFactory

    providers = LLMProviderFactory.get_available_providers()

    assert len(providers) > 0
    assert "claude-4.5-sonnet" in providers
    assert "gpt-4.1" in providers


@pytest.mark.smoke
@pytest.mark.fast
def test_rag_retriever_imports():
    """Test RAG retriever can be imported and initialized."""
    from src.services.rag.multi_hop_retriever import MultiHopRetriever

    # Should be able to import without errors
    assert MultiHopRetriever is not None


@pytest.mark.smoke
@pytest.mark.fast
def test_discord_formatter_basic():
    """Test Discord formatter can format a basic response."""
    from src.services.discord.formatter import format_response

    # Create mock response
    citation = Citation(
        document_name="test.md",
        section="Test",
        quote="Test quote",
        document_type="core-rules",
        last_update_date=date.today(),
    )

    response = BotResponse(
        response_id=uuid4(),
        query_id=uuid4(),
        answer_text="Test answer",
        citations=[citation],
        confidence_score=0.9,
        rag_score=0.8,
        validation_passed=True,
        llm_model="gpt-4.1",
        token_count=100,
        latency_ms=1000,
        timestamp=datetime.now(UTC),
    )

    validation_result = ValidationResult(
        is_valid=True, llm_confidence=0.9, rag_score=0.8, reason="Valid"
    )

    # Should format without errors
    embeds = format_response(response, validation_result)

    assert len(embeds) > 0
    assert embeds[0].description == "Test answer"


@pytest.mark.smoke
@pytest.mark.fast
def test_models_can_be_created():
    """Test critical models can be instantiated."""
    from src.models.rag_context import RAGContext
    from src.models.user_query import UserQuery

    # UserQuery
    query = UserQuery.from_discord_message(
        discord_user_id="123456", channel_id="789", message_text="test", sanitized_text="test"
    )
    assert query.query_id is not None

    # RAGContext
    context = RAGContext(
        context_id=uuid4(),
        query_id=uuid4(),
        document_chunks=[],
        relevance_scores=[],
        total_chunks=0,
        avg_relevance=0.0,
        meets_threshold=False,
    )
    assert context.context_id is not None


@pytest.mark.smoke
@pytest.mark.fast
def test_chunker_can_be_imported():
    """Test markdown chunker can be imported."""
    from src.services.rag.chunker import MarkdownChunker

    # Should be able to import without errors
    assert MarkdownChunker is not None


@pytest.mark.smoke
@pytest.mark.fast
def test_validator_basic_validation():
    """Test validator can validate LLM responses."""
    from src.models.rag_context import RAGContext
    from src.services.llm.base import LLMResponse
    from src.services.llm.validator import ResponseValidator

    validator = ResponseValidator()

    llm_response = LLMResponse(
        response_id=uuid4(),
        answer_text="Test",
        confidence_score=0.9,
        token_count=10,
        latency_ms=100,
        citations_included=True,
        provider="test",
        model_version="test-1",
    )

    rag_context = RAGContext(
        context_id=uuid4(),
        query_id=uuid4(),
        document_chunks=[],
        relevance_scores=[],
        total_chunks=0,
        avg_relevance=0.9,
        meets_threshold=True,
    )

    result = validator.validate(llm_response, rag_context)

    assert result.is_valid is True
