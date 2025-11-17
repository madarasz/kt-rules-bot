"""Unit tests for BotResponse model - business logic only."""

from datetime import UTC, date, datetime
from uuid import uuid4

from src.models.bot_response import BotResponse, Citation


class TestBotResponse:
    """Test BotResponse model - business logic only."""

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
            timestamp=datetime.now(UTC),
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
            timestamp=datetime.now(UTC),
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
            timestamp=datetime.now(UTC),
        )

        assert response.should_send() is False

    def test_split_for_discord_long_message(self):
        """Test splitting a long message into multiple chunks."""
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
            timestamp=datetime.now(UTC),
        )

        chunks = response.split_for_discord()

        assert len(chunks) > 1
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
        assert response.confidence_score == 0.85
        assert response.rag_score == 0.75
        assert response.validation_passed is True  # Both scores above thresholds
