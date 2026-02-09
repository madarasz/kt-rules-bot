"""Unit tests for ChunkSummarizer.

Tests summary generation logic with mocked LLM provider.
"""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from src.services.llm.base import LLMResponse
from src.services.llm.schemas import ChunkSummaries, ChunkSummary
from src.services.rag.chunker import MarkdownChunk
from src.services.rag.summarizer import ChunkSummarizer


@pytest.fixture
def sample_chunks():
    """Sample markdown chunks for testing."""
    return [
        MarkdownChunk(
            chunk_id=uuid4(),
            text="Operatives can move up to their Movement characteristic in inches.",
            header="Movement Phase",
            header_level=2,
            position=0,
            token_count=15,
            summary="",  # Empty initially
        ),
        MarkdownChunk(
            chunk_id=uuid4(),
            text="Operatives can shoot at enemy models within line of sight.",
            header="Shooting Phase",
            header_level=2,
            position=1,
            token_count=12,
            summary="",  # Empty initially
        ),
    ]


class TestChunkSummaryModels:
    """Tests for Pydantic models."""

    def test_chunk_summary_creation(self):
        """Test ChunkSummary model creation."""
        summary = ChunkSummary(
            chunk_number=1,
            summary="Operatives move up to Movement characteristic distance."
        )
        assert summary.chunk_number == 1
        assert "Movement characteristic" in summary.summary

    def test_chunk_summaries_batch(self):
        """Test ChunkSummaries batch model."""
        summaries = ChunkSummaries(
            summaries=[
                ChunkSummary(chunk_number=1, summary="First summary"),
                ChunkSummary(chunk_number=2, summary="Second summary"),
            ]
        )
        assert len(summaries.summaries) == 2
        assert summaries.summaries[0].chunk_number == 1
        assert summaries.summaries[1].chunk_number == 2


class TestFormatChunksForLLM:
    """Tests for _format_chunks_for_llm method."""

    @patch("src.services.rag.summarizer.LLMProviderFactory")
    @patch("src.services.rag.summarizer.SUMMARY_ENABLED", True)
    @patch("src.services.rag.summarizer.load_summary_prompt")
    def test_format_empty_chunks(self, mock_prompt, mock_factory):
        """Test formatting empty chunks list."""
        mock_prompt.return_value = "Test prompt"
        mock_factory.create.return_value = Mock()

        summarizer = ChunkSummarizer()
        result = summarizer._format_chunks_for_llm([])
        assert result == ""

    @patch("src.services.rag.summarizer.LLMProviderFactory")
    @patch("src.services.rag.summarizer.SUMMARY_ENABLED", True)
    @patch("src.services.rag.summarizer.load_summary_prompt")
    def test_format_single_chunk(self, mock_prompt, mock_factory, sample_chunks):
        """Test formatting single chunk."""
        mock_prompt.return_value = "Test prompt"
        mock_factory.create.return_value = Mock()

        summarizer = ChunkSummarizer()
        result = summarizer._format_chunks_for_llm([sample_chunks[0]])

        assert "Chunk 1:" in result
        assert "Header: Movement Phase" in result
        assert "Text: Operatives can move" in result

    @patch("src.services.rag.summarizer.LLMProviderFactory")
    @patch("src.services.rag.summarizer.SUMMARY_ENABLED", True)
    @patch("src.services.rag.summarizer.load_summary_prompt")
    def test_format_multiple_chunks(self, mock_prompt, mock_factory, sample_chunks):
        """Test formatting multiple chunks with proper numbering."""
        mock_prompt.return_value = "Test prompt"
        mock_factory.create.return_value = Mock()

        summarizer = ChunkSummarizer()
        result = summarizer._format_chunks_for_llm(sample_chunks)

        # Should have numbered chunks
        assert "Chunk 1:" in result
        assert "Chunk 2:" in result
        assert "Movement Phase" in result
        assert "Shooting Phase" in result


class TestGenerateSummaries:
    """Tests for generate_summaries method."""

    @pytest.mark.asyncio
    @patch("src.services.rag.summarizer.LLMProviderFactory")
    @patch("src.services.rag.summarizer.SUMMARY_ENABLED", True)
    @patch("src.services.rag.summarizer.load_summary_prompt")
    async def test_generate_summaries_success(self, mock_prompt, mock_factory, sample_chunks):
        """Test successful summary generation."""
        mock_prompt.return_value = "Test prompt"

        # Create mock LLM provider
        mock_provider = AsyncMock()
        mock_response = LLMResponse(
            response_id=uuid4(),
            answer_text="{}",  # Not used when structured_output is set
            confidence_score=0.9,
            token_count=150,
            latency_ms=500,
            provider="test",
            model_version="test-model",
            citations_included=False,
            prompt_tokens=100,
            completion_tokens=50,
            structured_output={
                "summaries": [
                    {"chunk_number": 1, "summary": "Movement rules summary"},
                    {"chunk_number": 2, "summary": "Shooting rules summary"},
                ]
            },
        )
        mock_provider.generate.return_value = mock_response
        mock_factory.create.return_value = mock_provider

        summarizer = ChunkSummarizer()

        # Generate summaries
        result_chunks, prompt_tokens, completion_tokens, model = await summarizer.generate_summaries(
            sample_chunks
        )

        # Verify summaries assigned
        assert result_chunks[0].summary == "Movement rules summary"
        assert result_chunks[1].summary == "Shooting rules summary"

        # Verify token counts returned
        assert prompt_tokens == 100
        assert completion_tokens == 50

        # Verify LLM provider called
        assert mock_provider.generate.called

    @pytest.mark.asyncio
    @patch("src.services.rag.summarizer.LLMProviderFactory")
    @patch("src.services.rag.summarizer.SUMMARY_ENABLED", True)
    @patch("src.services.rag.summarizer.load_summary_prompt")
    async def test_generate_summaries_api_failure(self, mock_prompt, mock_factory, sample_chunks):
        """Test graceful handling when LLM API fails."""
        mock_prompt.return_value = "Test prompt"

        # Mock LLM provider to raise exception
        mock_provider = AsyncMock()
        mock_provider.generate.side_effect = Exception("API Error")
        mock_factory.create.return_value = mock_provider

        summarizer = ChunkSummarizer()

        # Generate summaries (should not raise)
        result_chunks, prompt_tokens, completion_tokens, model = await summarizer.generate_summaries(
            sample_chunks
        )

        # Should return empty summaries
        assert result_chunks[0].summary == ""
        assert result_chunks[1].summary == ""
        assert prompt_tokens == 0
        assert completion_tokens == 0
        assert model == ""

    @pytest.mark.asyncio
    @patch("src.services.rag.summarizer.SUMMARY_ENABLED", False)
    async def test_generate_summaries_disabled(self, sample_chunks):
        """Test behavior when SUMMARY_ENABLED is False."""
        summarizer = ChunkSummarizer()

        result_chunks, prompt_tokens, completion_tokens, model = await summarizer.generate_summaries(
            sample_chunks
        )

        # Should return unchanged chunks with no API calls
        assert result_chunks[0].summary == ""
        assert result_chunks[1].summary == ""
        assert prompt_tokens == 0
        assert completion_tokens == 0
        assert model == ""

    @pytest.mark.asyncio
    @patch("src.services.rag.summarizer.LLMProviderFactory")
    @patch("src.services.rag.summarizer.SUMMARY_ENABLED", True)
    @patch("src.services.rag.summarizer.load_summary_prompt")
    async def test_generate_summaries_empty_chunks(self, mock_prompt, mock_factory):
        """Test handling of empty chunks list."""
        mock_prompt.return_value = "Test prompt"
        mock_factory.create.return_value = Mock()

        summarizer = ChunkSummarizer()

        result_chunks, prompt_tokens, completion_tokens, model = await summarizer.generate_summaries([])

        # Should return empty list with no API calls
        assert result_chunks == []
        assert prompt_tokens == 0
        assert completion_tokens == 0

    @pytest.mark.asyncio
    @patch("src.services.rag.summarizer.LLMProviderFactory")
    @patch("src.services.rag.summarizer.SUMMARY_ENABLED", True)
    @patch("src.services.rag.summarizer.load_summary_prompt")
    async def test_generate_summaries_missing_chunk_number(
        self, mock_prompt, mock_factory, sample_chunks
    ):
        """Test handling when LLM skips a chunk number."""
        mock_prompt.return_value = "Test prompt"

        # Mock LLM provider - only returns summary for chunk 1
        mock_provider = AsyncMock()
        mock_response = LLMResponse(
            response_id=uuid4(),
            answer_text="{}",
            confidence_score=0.9,
            token_count=125,
            latency_ms=400,
            provider="test",
            model_version="test-model",
            citations_included=False,
            prompt_tokens=100,
            completion_tokens=25,
            structured_output={
                "summaries": [
                    {"chunk_number": 1, "summary": "Only first summary"},
                    # Missing chunk 2
                ]
            },
        )
        mock_provider.generate.return_value = mock_response
        mock_factory.create.return_value = mock_provider

        summarizer = ChunkSummarizer()

        result_chunks, _, _, _ = await summarizer.generate_summaries(sample_chunks)

        # First chunk should have summary
        assert result_chunks[0].summary == "Only first summary"
        # Second chunk should have empty summary (fallback)
        assert result_chunks[1].summary == ""


class TestLoadSummaryPrompt:
    """Tests for load_summary_prompt function."""

    @patch("src.services.rag.summarizer.Path")
    def test_load_summary_prompt_success(self, mock_path):
        """Test successful prompt loading."""
        from src.services.rag.summarizer import load_summary_prompt

        # Mock Path to return a file that exists
        mock_prompt_file = Mock()
        mock_prompt_file.exists.return_value = True
        mock_prompt_file.read_text.return_value = "Test prompt content"

        mock_path.return_value.parent.parent.parent.parent.__truediv__.return_value = (
            mock_prompt_file
        )

        result = load_summary_prompt()
        assert result == "Test prompt content"

    @patch("src.services.rag.summarizer.Path")
    def test_load_summary_prompt_file_not_found(self, mock_path):
        """Test error handling when prompt file not found."""
        from src.services.rag.summarizer import load_summary_prompt

        # Mock Path to return a file that doesn't exist
        mock_prompt_file = Mock()
        mock_prompt_file.exists.return_value = False

        mock_path.return_value.parent.parent.parent.parent.__truediv__.return_value = (
            mock_prompt_file
        )

        with pytest.raises(FileNotFoundError, match="Summary prompt file not found"):
            load_summary_prompt()
