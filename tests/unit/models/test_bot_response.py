"""Unit tests for BotResponse model."""

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest

from src.models.bot_response import BotResponse, Citation


class TestCitation:
    """Test Citation model."""

    def test_validate_success(self):
        """Test successful citation validation."""
        citation = Citation(
            document_name="rules-1-phases.md",
            section="Movement Phase",
            quote="You can move up to your Movement characteristic.",
            document_type="core-rules",
            last_update_date=date.today(),
        )
        # Should not raise
        citation.validate()

    def test_citation_creation(self):
        """Test creating a citation."""
        citation = Citation(
            document_name="faq.md",
            section="Charge Phase",
            quote="A charge requires line of sight.",
            document_type="faq",
            last_update_date=date(2024, 10, 1),
        )

        assert citation.document_name == "faq.md"
        assert citation.section == "Charge Phase"
        assert citation.document_type == "faq"


class TestBotResponse:
    """Test BotResponse model."""

    def test_validate_success(self):
        """Test successful bot response validation."""
        citation = Citation(
            document_name="rules.md",
            section="Combat",
            quote="Attack sequence follows these steps.",
            document_type="core-rules",
            last_update_date=date.today(),
        )

        response = BotResponse(
            response_id=uuid4(),
            query_id=uuid4(),
            answer_text="Yes, you can overwatch.",
            citations=[citation],
            confidence_score=0.9,
            rag_score=0.8,
            validation_passed=True,
            llm_model="gpt-4.1",
            token_count=150,
            latency_ms=1200,
            timestamp=datetime.now(timezone.utc),
        )
        # Should not raise
        response.validate()

    def test_should_send_high_scores(self):
        """Test should_send with high confidence and RAG scores."""
        citation = Citation(
            document_name="rules.md",
            section="Combat",
            quote="Test quote",
            document_type="core-rules",
            last_update_date=date.today(),
        )

        response = BotResponse(
            response_id=uuid4(),
            query_id=uuid4(),
            answer_text="Answer",
            citations=[citation],
            confidence_score=0.9,
            rag_score=0.8,
            validation_passed=True,
            llm_model="gpt-4.1",
            token_count=100,
            latency_ms=1000,
            timestamp=datetime.now(timezone.utc),
        )

        assert response.should_send() is True

    def test_should_send_low_confidence(self):
        """Test should_send with low LLM confidence."""
        citation = Citation(
            document_name="rules.md",
            section="Combat",
            quote="Test quote",
            document_type="core-rules",
            last_update_date=date.today(),
        )

        response = BotResponse(
            response_id=uuid4(),
            query_id=uuid4(),
            answer_text="Answer",
            citations=[citation],
            confidence_score=0.5,  # Below threshold
            rag_score=0.8,
            validation_passed=False,
            llm_model="gpt-4.1",
            token_count=100,
            latency_ms=1000,
            timestamp=datetime.now(timezone.utc),
        )

        assert response.should_send() is False

    def test_should_send_low_rag(self):
        """Test should_send with low RAG score."""
        citation = Citation(
            document_name="rules.md",
            section="Combat",
            quote="Test quote",
            document_type="core-rules",
            last_update_date=date.today(),
        )

        response = BotResponse(
            response_id=uuid4(),
            query_id=uuid4(),
            answer_text="Answer",
            citations=[citation],
            confidence_score=0.9,
            rag_score=0.4,  # Below threshold
            validation_passed=False,
            llm_model="gpt-4.1",
            token_count=100,
            latency_ms=1000,
            timestamp=datetime.now(timezone.utc),
        )

        assert response.should_send() is False

    def test_should_send_custom_threshold(self):
        """Test should_send with custom confidence threshold."""
        citation = Citation(
            document_name="rules.md",
            section="Combat",
            quote="Test quote",
            document_type="core-rules",
            last_update_date=date.today(),
        )

        response = BotResponse(
            response_id=uuid4(),
            query_id=uuid4(),
            answer_text="Answer",
            citations=[citation],
            confidence_score=0.75,
            rag_score=0.8,
            validation_passed=True,
            llm_model="gpt-4.1",
            token_count=100,
            latency_ms=1000,
            timestamp=datetime.now(timezone.utc),
        )

        assert response.should_send(confidence_threshold=0.8) is False
        assert response.should_send(confidence_threshold=0.7) is True

    def test_split_for_discord_short_message(self):
        """Test splitting a short message that fits in one chunk."""
        citation = Citation(
            document_name="rules.md",
            section="Combat",
            quote="Test quote",
            document_type="core-rules",
            last_update_date=date.today(),
        )

        response = BotResponse(
            response_id=uuid4(),
            query_id=uuid4(),
            answer_text="This is a short answer.",
            citations=[citation],
            confidence_score=0.9,
            rag_score=0.8,
            validation_passed=True,
            llm_model="gpt-4.1",
            token_count=100,
            latency_ms=1000,
            timestamp=datetime.now(timezone.utc),
        )

        chunks = response.split_for_discord()

        assert len(chunks) == 1
        assert chunks[0] == "This is a short answer."

    def test_split_for_discord_long_message(self):
        """Test splitting a long message into multiple chunks."""
        # Create a long message with sentences
        long_text = ". ".join([f"Sentence {i}" for i in range(200)])

        citation = Citation(
            document_name="rules.md",
            section="Combat",
            quote="Test quote",
            document_type="core-rules",
            last_update_date=date.today(),
        )

        response = BotResponse(
            response_id=uuid4(),
            query_id=uuid4(),
            answer_text=long_text,
            citations=[citation],
            confidence_score=0.9,
            rag_score=0.8,
            validation_passed=True,
            llm_model="gpt-4.1",
            token_count=100,
            latency_ms=1000,
            timestamp=datetime.now(timezone.utc),
        )

        chunks = response.split_for_discord()

        # Should be split into multiple chunks
        assert len(chunks) > 1

        # Each chunk should be under 2000 characters
        for chunk in chunks:
            assert len(chunk) <= 2000

    def test_create(self):
        """Test creating BotResponse with factory method."""
        query_id = uuid4()
        citation = Citation(
            document_name="rules.md",
            section="Combat",
            quote="Test quote",
            document_type="core-rules",
            last_update_date=date.today(),
        )

        response = BotResponse.create(
            query_id=query_id,
            answer_text="Test answer",
            citations=[citation],
            confidence_score=0.85,
            rag_score=0.75,
            llm_model="claude-sonnet-4-5-20250929",
            token_count=200,
            latency_ms=1500,
        )

        assert response.query_id == query_id
        assert response.answer_text == "Test answer"
        assert len(response.citations) == 1
        assert response.confidence_score == 0.85
        assert response.rag_score == 0.75
        assert response.llm_model == "claude-sonnet-4-5-20250929"
        assert response.token_count == 200
        assert response.latency_ms == 1500
        assert response.validation_passed is True  # Both scores above thresholds
        assert isinstance(response.timestamp, datetime)

    def test_create_validation_failed(self):
        """Test creating BotResponse with validation_passed=False."""
        citation = Citation(
            document_name="rules.md",
            section="Combat",
            quote="Test quote",
            document_type="core-rules",
            last_update_date=date.today(),
        )

        response = BotResponse.create(
            query_id=uuid4(),
            answer_text="Test answer",
            citations=[citation],
            confidence_score=0.5,  # Below threshold
            rag_score=0.75,
            llm_model="gpt-4.1",
            token_count=200,
            latency_ms=1500,
        )

        assert response.validation_passed is False

    def test_create_with_structured_data(self):
        """Test creating BotResponse with structured data."""
        from src.models.structured_response import StructuredLLMResponse, StructuredQuote

        citation = Citation(
            document_name="rules.md",
            section="Combat",
            quote="Test quote",
            document_type="core-rules",
            last_update_date=date.today(),
        )

        structured = StructuredLLMResponse(
            smalltalk=False,
            short_answer="Yes.",
            persona_short_answer="That's correct!",
            quotes=[StructuredQuote("Core Rules", "Some text")],
            explanation="Here's why...",
            persona_afterword="Hope that helps!",
        )

        response = BotResponse.create(
            query_id=uuid4(),
            answer_text='{"smalltalk": false}',
            citations=[citation],
            confidence_score=0.9,
            rag_score=0.8,
            llm_model="gpt-4.1",
            token_count=200,
            latency_ms=1500,
            structured_data=structured,
        )

        assert response.structured_data == structured
