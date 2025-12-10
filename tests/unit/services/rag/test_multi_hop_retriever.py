"""Tests for multi-hop retrieval functionality."""

import json
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from src.models.rag_context import DocumentChunk, RAGContext
from src.services.rag.multi_hop_retriever import HopEvaluation, MultiHopRetriever


@pytest.fixture
def mock_base_retriever():
    """Mock base retriever."""
    retriever = Mock()
    retriever.retrieve = Mock()
    return retriever


@pytest.fixture
def sample_chunks():
    """Sample document chunks."""
    return [
        DocumentChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            text="Content about overwatch",
            header="Overwatch Rules",
            header_level=2,
            metadata={
                "source": "core-rules.md",
                "doc_type": "core-rules",
                "publication_date": "2024-01-01",
            },
            relevance_score=0.9,
            position_in_doc=1,
        ),
        DocumentChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            text="Content about charges",
            header="Charge Rules",
            header_level=2,
            metadata={
                "source": "core-rules.md",
                "doc_type": "core-rules",
                "publication_date": "2024-01-01",
            },
            relevance_score=0.85,
            position_in_doc=2,
        ),
    ]


@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider."""
    provider = Mock()
    provider.generate = AsyncMock()
    return provider


class TestHopEvaluation:
    """Tests for HopEvaluation class."""

    def test_init_basic(self):
        """Test basic initialization."""
        hop_eval = HopEvaluation(
            can_answer=True, reasoning="Sufficient context", missing_query=None, cost_usd=0.001
        )
        assert hop_eval.can_answer is True
        assert hop_eval.reasoning == "Sufficient context"
        assert hop_eval.missing_query is None
        assert hop_eval.cost_usd == 0.001

    def test_init_with_missing_query(self):
        """Test initialization with missing query."""
        hop_eval = HopEvaluation(
            can_answer=False,
            reasoning="Need more context",
            missing_query="What is overwatch?",
            cost_usd=0.002,
        )
        assert hop_eval.can_answer is False
        assert hop_eval.missing_query == "What is overwatch?"

    def test_to_dict(self):
        """Test conversion to dictionary."""
        hop_eval = HopEvaluation(
            can_answer=True,
            reasoning="Complete",
            cost_usd=0.001,
            retrieval_time_s=0.5,
            evaluation_time_s=0.3,
        )
        result = hop_eval.to_dict()
        assert result["can_answer"] is True
        assert result["reasoning"] == "Complete"
        assert result["cost_usd"] == 0.001
        assert result["retrieval_time_s"] == 0.5
        assert result["evaluation_time_s"] == 0.3


class TestMultiHopRetrieverInit:
    """Tests for MultiHopRetriever initialization."""

    @patch("src.services.rag.multi_hop_retriever.LLMProviderFactory.create")
    @patch("builtins.open", create=True)
    @patch("src.services.rag.multi_hop_retriever.yaml.safe_load")
    def test_init_basic(self, mock_yaml_load, mock_open, mock_create):
        """Test basic initialization."""
        mock_create.return_value = Mock()
        mock_yaml_load.return_value = {}
        mock_open.return_value.__enter__.return_value.read.return_value = "prompt template"

        base_retriever = Mock()
        retriever = MultiHopRetriever(base_retriever)

        assert retriever.base_retriever == base_retriever
        assert retriever.evaluation_llm is not None

    @patch("src.services.rag.multi_hop_retriever.LLMProviderFactory.create")
    @patch("builtins.open", create=True)
    @patch("src.services.rag.multi_hop_retriever.yaml.safe_load")
    def test_init_custom_params(self, mock_yaml_load, mock_open, mock_create):
        """Test initialization with custom parameters."""
        mock_create.return_value = Mock()
        mock_yaml_load.return_value = {}
        mock_open.return_value.__enter__.return_value.read.return_value = "prompt template"

        base_retriever = Mock()
        retriever = MultiHopRetriever(
            base_retriever, max_hops=5, chunks_per_hop=10, evaluation_timeout=45
        )

        assert retriever.max_hops == 5
        assert retriever.chunks_per_hop == 10
        assert retriever.evaluation_timeout == 45


class TestFormatChunksForPrompt:
    """Tests for _format_chunks_for_prompt method."""

    @patch("src.services.rag.multi_hop_retriever.LLMProviderFactory.create")
    @patch("builtins.open", create=True)
    @patch("src.services.rag.multi_hop_retriever.yaml.safe_load")
    def test_format_empty_chunks(self, mock_yaml_load, mock_open, mock_create):
        """Test formatting empty chunks list."""
        mock_create.return_value = Mock()
        mock_yaml_load.return_value = {}
        mock_open.return_value.__enter__.return_value.read.return_value = "prompt"

        retriever = MultiHopRetriever(Mock())
        result = retriever._format_chunks_for_prompt([])
        assert result == "(No context retrieved yet)"

    @patch("src.services.rag.multi_hop_retriever.LLMProviderFactory.create")
    @patch("builtins.open", create=True)
    @patch("src.services.rag.multi_hop_retriever.yaml.safe_load")
    def test_format_single_chunk(self, mock_yaml_load, mock_open, mock_create, sample_chunks):
        """Test formatting single chunk."""
        mock_create.return_value = Mock()
        mock_yaml_load.return_value = {}
        mock_open.return_value.__enter__.return_value.read.return_value = "prompt"

        retriever = MultiHopRetriever(Mock())
        result = retriever._format_chunks_for_prompt([sample_chunks[0]])

        # Without summary metadata, format is "{i}. {text}\n"
        assert "1. Content about overwatch" in result

    @patch("src.services.rag.multi_hop_retriever.LLMProviderFactory.create")
    @patch("builtins.open", create=True)
    @patch("src.services.rag.multi_hop_retriever.yaml.safe_load")
    def test_format_multiple_chunks(self, mock_yaml_load, mock_open, mock_create, sample_chunks):
        """Test formatting multiple chunks."""
        mock_create.return_value = Mock()
        mock_yaml_load.return_value = {}
        mock_open.return_value.__enter__.return_value.read.return_value = "prompt"

        retriever = MultiHopRetriever(Mock())
        result = retriever._format_chunks_for_prompt(sample_chunks)

        # Without summary metadata, format is "{i}. {text}\n"
        assert "1. Content about overwatch" in result
        assert "2. Content about charges" in result

    @patch("src.services.rag.multi_hop_retriever.LLMProviderFactory.create")
    @patch("builtins.open", create=True)
    @patch("src.services.rag.multi_hop_retriever.yaml.safe_load")
    def test_format_truncates_long_chunks(self, mock_yaml_load, mock_open, mock_create):
        """Test that very long chunks are truncated."""
        mock_create.return_value = Mock()
        mock_yaml_load.return_value = {}
        mock_open.return_value.__enter__.return_value.read.return_value = "prompt"

        long_chunk = DocumentChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            text="A" * 10000,  # Very long text
            header="Long Section",
            header_level=2,
            metadata={
                "source": "test.md",
                "doc_type": "core-rules",
                "publication_date": "2024-01-01",
            },
            relevance_score=0.9,
            position_in_doc=1,
        )

        retriever = MultiHopRetriever(Mock())
        result = retriever._format_chunks_for_prompt([long_chunk])

        assert "..." in result  # Should be truncated


    @patch("src.services.rag.multi_hop_retriever.LLMProviderFactory.create")
    @patch("builtins.open", create=True)
    @patch("src.services.rag.multi_hop_retriever.yaml.safe_load")
    def test_format_with_summary_metadata(self, mock_yaml_load, mock_open, mock_create):
        """Test chunk formatting when summary metadata is present."""
        mock_create.return_value = Mock()
        mock_yaml_load.return_value = {}
        mock_open.return_value.__enter__.return_value.read.return_value = "prompt"

        # Create chunks with summary metadata
        chunks_with_summary = [
            DocumentChunk(
                chunk_id=uuid4(),
                document_id=uuid4(),
                text="## Overwatch Rules\nDetailed overwatch content here",
                header="Overwatch Rules",
                header_level=2,
                metadata={
                    "source": "core-rules.md",
                    "doc_type": "core-rules",
                    "publication_date": "2024-01-01",
                    "summary": "Rules for using overwatch action",
                },
                relevance_score=0.9,
                position_in_doc=1,
            ),
        ]

        retriever = MultiHopRetriever(Mock())
        result = retriever._format_chunks_for_prompt(chunks_with_summary)

        # With summary metadata, format is "{i}. {header_line}\n{summary}\n"
        assert "1. ## Overwatch Rules" in result
        assert "Rules for using overwatch action" in result
        # Full text content should NOT appear (only header + summary)
        assert "Detailed overwatch content here" not in result

    @patch("src.services.rag.multi_hop_retriever.LLMProviderFactory.create")
    @patch("builtins.open", create=True)
    @patch("src.services.rag.multi_hop_retriever.yaml.safe_load")
    def test_format_without_summary_metadata(self, mock_yaml_load, mock_open, mock_create, sample_chunks):
        """Test chunk formatting when summary metadata is not present."""
        mock_create.return_value = Mock()
        mock_yaml_load.return_value = {}
        mock_open.return_value.__enter__.return_value.read.return_value = "prompt"

        retriever = MultiHopRetriever(Mock())
        result = retriever._format_chunks_for_prompt(sample_chunks)

        # Without summary metadata, format is "{i}. {text}\n"
        # Full text should appear
        assert "1. Content about overwatch" in result
        assert "2. Content about charges" in result


class TestEvaluateContext:
    """Tests for _evaluate_context method."""

    @pytest.mark.asyncio
    @patch("src.services.rag.multi_hop_retriever.LLMProviderFactory.create")
    @patch("builtins.open", create=True)
    @patch("src.services.rag.multi_hop_retriever.yaml.safe_load")
    async def test_evaluate_can_answer(self, mock_yaml_load, mock_open, mock_create, sample_chunks):
        """Test evaluation when context is sufficient."""
        mock_llm = Mock()
        mock_response = Mock()
        mock_response.answer_text = json.dumps(
            {"can_answer": True, "reasoning": "Sufficient context"}
        )
        mock_response.token_count = 100
        mock_response.prompt_tokens = 70
        mock_response.completion_tokens = 30
        mock_llm.generate = AsyncMock(return_value=mock_response)
        mock_create.return_value = mock_llm

        mock_yaml_load.return_value = {"Team1": {}}
        mock_open.return_value.__enter__.return_value.read.return_value = (
            "{user_query} {retrieved_chunks} {rule_structure} {team_structure}"
        )

        retriever = MultiHopRetriever(Mock())
        result = await retriever._evaluate_context("test query", sample_chunks)

        assert result.can_answer is True
        assert result.reasoning == "Sufficient context"
        assert result.missing_query is None

    @pytest.mark.asyncio
    @patch("src.services.rag.multi_hop_retriever.LLMProviderFactory.create")
    @patch("builtins.open", create=True)
    @patch("src.services.rag.multi_hop_retriever.yaml.safe_load")
    async def test_evaluate_needs_more_context(
        self, mock_yaml_load, mock_open, mock_create, sample_chunks
    ):
        """Test evaluation when more context is needed."""
        mock_llm = Mock()
        mock_response = Mock()
        mock_response.answer_text = json.dumps(
            {
                "can_answer": False,
                "reasoning": "Missing information",
                "missing_query": "What are charge restrictions?",
            }
        )
        mock_response.token_count = 100
        mock_response.prompt_tokens = 70
        mock_response.completion_tokens = 30
        mock_llm.generate = AsyncMock(return_value=mock_response)
        mock_create.return_value = mock_llm

        mock_yaml_load.return_value = {}
        mock_open.return_value.__enter__.return_value.read.return_value = (
            "{user_query} {retrieved_chunks} {rule_structure} {team_structure}"
        )

        retriever = MultiHopRetriever(Mock())
        result = await retriever._evaluate_context("test query", sample_chunks)

        assert result.can_answer is False
        assert result.missing_query == "What are charge restrictions?"

    @pytest.mark.asyncio
    @patch("src.services.rag.multi_hop_retriever.LLMProviderFactory.create")
    @patch("builtins.open", create=True)
    @patch("src.services.rag.multi_hop_retriever.yaml.safe_load")
    async def test_evaluate_invalid_json(
        self, mock_yaml_load, mock_open, mock_create, sample_chunks
    ):
        """Test evaluation with invalid JSON response."""
        mock_llm = Mock()
        mock_response = Mock()
        mock_response.answer_text = "invalid json"
        mock_response.token_count = 100
        mock_llm.generate = AsyncMock(return_value=mock_response)
        mock_create.return_value = mock_llm

        mock_yaml_load.return_value = {}
        mock_open.return_value.__enter__.return_value.read.return_value = (
            "{user_query} {retrieved_chunks} {rule_structure} {team_structure}"
        )

        retriever = MultiHopRetriever(Mock())

        with pytest.raises(ValueError, match="Failed to parse"):
            await retriever._evaluate_context("test query", sample_chunks)

    @pytest.mark.asyncio
    @patch("src.services.rag.multi_hop_retriever.LLMProviderFactory.create")
    @patch("builtins.open", create=True)
    @patch("src.services.rag.multi_hop_retriever.yaml.safe_load")
    async def test_evaluate_missing_required_fields(
        self, mock_yaml_load, mock_open, mock_create, sample_chunks
    ):
        """Test evaluation with missing required fields."""
        mock_llm = Mock()
        mock_response = Mock()
        mock_response.answer_text = json.dumps({"can_answer": True})  # Missing reasoning
        mock_response.token_count = 100
        mock_llm.generate = AsyncMock(return_value=mock_response)
        mock_create.return_value = mock_llm

        mock_yaml_load.return_value = {}
        mock_open.return_value.__enter__.return_value.read.return_value = (
            "{user_query} {retrieved_chunks} {rule_structure} {team_structure}"
        )

        retriever = MultiHopRetriever(Mock())

        with pytest.raises(ValueError, match="Missing required fields"):
            await retriever._evaluate_context("test query", sample_chunks)

    @pytest.mark.asyncio
    @patch("src.services.rag.multi_hop_retriever.LLMProviderFactory.create")
    @patch("builtins.open", create=True)
    @patch("src.services.rag.multi_hop_retriever.yaml.safe_load")
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_evaluate_rate_limit_retry(
        self, mock_sleep, mock_yaml_load, mock_open, mock_create, sample_chunks
    ):
        """Test evaluation retries on rate limit error."""
        from src.services.llm.base import RateLimitError

        mock_llm = Mock()
        # First call raises rate limit, second succeeds
        mock_response = Mock()
        mock_response.answer_text = json.dumps(
            {"can_answer": True, "reasoning": "Success after retry"}
        )
        mock_response.token_count = 100
        mock_response.prompt_tokens = 70
        mock_response.completion_tokens = 30

        mock_llm.generate = AsyncMock(side_effect=[RateLimitError("Rate limited"), mock_response])
        mock_create.return_value = mock_llm

        mock_yaml_load.return_value = {}
        mock_open.return_value.__enter__.return_value.read.return_value = (
            "{user_query} {retrieved_chunks} {rule_structure} {team_structure}"
        )

        retriever = MultiHopRetriever(Mock())
        result = await retriever._evaluate_context("test query", sample_chunks)

        assert result.can_answer is True
        assert mock_sleep.called  # Should have slept before retry


class TestRetrieveMultiHop:
    """Tests for retrieve_multi_hop method."""

    @pytest.mark.asyncio
    @patch("src.services.rag.multi_hop_retriever.LLMProviderFactory.create")
    @patch("builtins.open", create=True)
    @patch("src.services.rag.multi_hop_retriever.yaml.safe_load")
    async def test_single_hop_sufficient(
        self, mock_yaml_load, mock_open, mock_create, sample_chunks
    ):
        """Test multi-hop when initial retrieval is sufficient."""
        # Setup mocks
        mock_llm = Mock()
        mock_response = Mock()
        mock_response.answer_text = json.dumps({"can_answer": True, "reasoning": "Sufficient"})
        mock_response.token_count = 100
        mock_response.prompt_tokens = 70
        mock_response.completion_tokens = 30
        mock_llm.generate = AsyncMock(return_value=mock_response)
        mock_create.return_value = mock_llm

        mock_yaml_load.return_value = {}
        mock_open.return_value.__enter__.return_value.read.return_value = (
            "{user_query} {retrieved_chunks} {rule_structure} {team_structure}"
        )

        # Setup base retriever
        base_retriever = Mock()
        initial_context = RAGContext.from_retrieval(uuid4(), sample_chunks)
        base_retriever.retrieve = Mock(return_value=(initial_context, [], {}))

        retriever = MultiHopRetriever(base_retriever, max_hops=2)

        context, hop_evals, chunk_map = await retriever.retrieve_multi_hop(
            "test query", "context_key", uuid4()
        )

        assert len(context.document_chunks) == 2
        assert len(hop_evals) == 1
        assert hop_evals[0].can_answer is True

    @pytest.mark.asyncio
    @patch("src.services.rag.multi_hop_retriever.LLMProviderFactory.create")
    @patch("builtins.open", create=True)
    @patch("src.services.rag.multi_hop_retriever.yaml.safe_load")
    async def test_multi_hop_with_additional_retrieval(
        self, mock_yaml_load, mock_open, mock_create, sample_chunks
    ):
        """Test multi-hop with additional retrieval needed."""
        # Setup LLM mock - first needs more, then sufficient
        mock_llm = Mock()
        response1 = Mock()
        response1.answer_text = json.dumps(
            {
                "can_answer": False,
                "reasoning": "Need more",
                "missing_query": "Additional query",
            }
        )
        response1.token_count = 100
        response1.prompt_tokens = 70
        response1.completion_tokens = 30

        response2 = Mock()
        response2.answer_text = json.dumps({"can_answer": True, "reasoning": "Now sufficient"})
        response2.token_count = 100
        response2.prompt_tokens = 70
        response2.completion_tokens = 30

        responses = [response1, response2]
        mock_llm.generate = AsyncMock(side_effect=responses)
        mock_create.return_value = mock_llm

        mock_yaml_load.return_value = {}
        mock_open.return_value.__enter__.return_value.read.return_value = (
            "{user_query} {retrieved_chunks} {rule_structure} {team_structure}"
        )

        # Setup base retriever
        base_retriever = Mock()
        initial_context = RAGContext.from_retrieval(uuid4(), sample_chunks[:1])
        hop_context = RAGContext.from_retrieval(uuid4(), sample_chunks[1:])

        base_retriever.retrieve = Mock(
            side_effect=[(initial_context, [], {}), (hop_context, [], {})]
        )

        retriever = MultiHopRetriever(base_retriever, max_hops=2)

        context, hop_evals, chunk_map = await retriever.retrieve_multi_hop(
            "test query", "context_key", uuid4()
        )

        assert len(hop_evals) == 2
        assert hop_evals[0].can_answer is False
        assert hop_evals[1].can_answer is True
        assert len(context.document_chunks) == 2

    @pytest.mark.asyncio
    @patch("src.services.rag.multi_hop_retriever.LLMProviderFactory.create")
    @patch("builtins.open", create=True)
    @patch("src.services.rag.multi_hop_retriever.yaml.safe_load")
    async def test_max_hops_reached(self, mock_yaml_load, mock_open, mock_create, sample_chunks):
        """Test behavior when max hops is reached."""
        # Setup LLM mock - always says need more
        mock_llm = Mock()
        mock_response = Mock()
        mock_response.answer_text = json.dumps(
            {"can_answer": False, "reasoning": "Need more", "missing_query": "More info"}
        )
        mock_response.token_count = 100
        mock_response.prompt_tokens = 70
        mock_response.completion_tokens = 30
        mock_llm.generate = AsyncMock(return_value=mock_response)
        mock_create.return_value = mock_llm

        mock_yaml_load.return_value = {}
        mock_open.return_value.__enter__.return_value.read.return_value = (
            "{user_query} {retrieved_chunks} {rule_structure} {team_structure}"
        )

        # Setup base retriever
        base_retriever = Mock()
        context = RAGContext.from_retrieval(uuid4(), sample_chunks[:1])
        base_retriever.retrieve = Mock(return_value=(context, [], {}))

        retriever = MultiHopRetriever(base_retriever, max_hops=1)

        context, hop_evals, chunk_map = await retriever.retrieve_multi_hop(
            "test query", "context_key", uuid4()
        )

        # Should have 1 hop evaluation (at max_hops)
        assert len(hop_evals) == 1
        assert hop_evals[-1].can_answer is False

    @pytest.mark.asyncio
    @patch("src.services.rag.multi_hop_retriever.LLMProviderFactory.create")
    @patch("builtins.open", create=True)
    @patch("src.services.rag.multi_hop_retriever.yaml.safe_load")
    async def test_chunk_deduplication(self, mock_yaml_load, mock_open, mock_create, sample_chunks):
        """Test that duplicate chunks are not added."""
        # Setup LLM mock
        mock_llm = Mock()
        response1 = Mock()
        response1.answer_text = json.dumps(
            {"can_answer": False, "reasoning": "Need more", "missing_query": "Additional"}
        )
        response1.token_count = 100
        response1.prompt_tokens = 70
        response1.completion_tokens = 30

        response2 = Mock()
        response2.answer_text = json.dumps({"can_answer": True, "reasoning": "Done"})
        response2.token_count = 100
        response2.prompt_tokens = 70
        response2.completion_tokens = 30

        responses = [response1, response2]
        mock_llm.generate = AsyncMock(side_effect=responses)
        mock_create.return_value = mock_llm

        mock_yaml_load.return_value = {}
        mock_open.return_value.__enter__.return_value.read.return_value = (
            "{user_query} {retrieved_chunks} {rule_structure} {team_structure}"
        )

        # Setup base retriever - return same chunks both times
        base_retriever = Mock()
        context = RAGContext.from_retrieval(uuid4(), sample_chunks)
        base_retriever.retrieve = Mock(return_value=(context, [], {}))

        retriever = MultiHopRetriever(base_retriever, max_hops=2)

        final_context, hop_evals, chunk_map = await retriever.retrieve_multi_hop(
            "test query", "context_key", uuid4()
        )

        # Should not have duplicates
        chunk_ids = [c.chunk_id for c in final_context.document_chunks]
        assert len(chunk_ids) == len(set(chunk_ids))
