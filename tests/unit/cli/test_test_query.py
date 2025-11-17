"""Unit tests for test_query.py CLI command."""

from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch
from uuid import uuid4

import pytest

from src.cli.test_query import test_query


class TestTestQuery:
    """Tests for test_query function."""

    @patch('src.cli.test_query.get_config')
    @patch('src.cli.test_query.VectorDBService')
    @patch('src.cli.test_query.EmbeddingService')
    @patch('src.cli.test_query.RAGRetriever')
    @patch('src.cli.test_query.LLMProviderFactory')
    @patch('src.cli.test_query.ResponseValidator')
    @patch('src.cli.test_query.asyncio.run')
    def test_successful_query_execution(
        self,
        mock_asyncio_run,
        mock_validator_class,
        mock_llm_factory_class,
        mock_retriever_class,
        mock_embedding_class,
        mock_vectordb_class,
        mock_config
    ):
        """Test successful query execution."""
        # Mock config
        mock_config.return_value.default_llm_provider = "claude-4.5-sonnet"

        # Mock services
        mock_vectordb_class.return_value = Mock()
        mock_embedding_class.return_value = Mock()

        # Mock RAG retriever
        mock_retriever = Mock()
        mock_chunk = Mock()
        mock_chunk.chunk_id = "chunk-1"
        mock_chunk.header = "Test Header"
        mock_chunk.text = "Test content"
        mock_chunk.relevance_score = 0.85
        mock_chunk.metadata = {"source": "test"}

        mock_rag_context = Mock()
        mock_rag_context.total_chunks = 1
        mock_rag_context.avg_relevance = 0.85
        mock_rag_context.meets_threshold = True
        mock_rag_context.document_chunks = [mock_chunk]

        mock_retriever.retrieve.return_value = (mock_rag_context, [], {})
        mock_retriever_class.return_value = mock_retriever

        # Mock LLM provider
        mock_llm_provider = Mock()
        mock_llm_response = Mock()
        mock_llm_response.answer_text = "Test answer"
        mock_llm_response.confidence_score = 0.9
        mock_llm_response.token_count = 100
        mock_llm_response.provider = "claude"
        mock_llm_response.model_version = "claude-4.5-sonnet"
        mock_llm_response.prompt_tokens = 80
        mock_llm_response.completion_tokens = 20

        mock_asyncio_run.return_value = mock_llm_response

        mock_llm_factory = Mock()
        mock_llm_factory.create.return_value = mock_llm_provider
        mock_llm_factory_class.return_value = mock_llm_factory

        # Mock validator
        mock_validator = Mock()
        mock_validation_result = Mock()
        mock_validation_result.is_valid = True
        mock_validation_result.llm_confidence = 0.9
        mock_validation_result.rag_score = 0.85
        mock_validation_result.reason = "Valid response"
        mock_validator.validate.return_value = mock_validation_result
        mock_validator_class.return_value = mock_validator

        # Should not raise
        test_query(query="Test question", model="claude-4.5-sonnet")

    @patch('src.cli.test_query.get_config')
    @patch('src.cli.test_query.VectorDBService')
    @patch('src.cli.test_query.EmbeddingService')
    @patch('src.cli.test_query.RAGRetriever')
    def test_rag_only_mode(
        self,
        mock_retriever_class,
        mock_embedding_class,
        mock_vectordb_class,
        mock_config
    ):
        """Test RAG-only mode (no LLM generation)."""
        mock_config.return_value.default_llm_provider = "claude-4.5-sonnet"

        mock_vectordb_class.return_value = Mock()
        mock_embedding_class.return_value = Mock()

        # Mock RAG retriever
        mock_retriever = Mock()
        mock_chunk = Mock()
        mock_chunk.chunk_id = "chunk-1"
        mock_chunk.header = "Test Header"
        mock_chunk.text = "Test content"
        mock_chunk.relevance_score = 0.85
        mock_chunk.metadata = {"source": "test"}

        mock_rag_context = Mock()
        mock_rag_context.total_chunks = 1
        mock_rag_context.avg_relevance = 0.85
        mock_rag_context.meets_threshold = True
        mock_rag_context.document_chunks = [mock_chunk]

        mock_retriever.retrieve.return_value = (mock_rag_context, [], {})
        mock_retriever_class.return_value = mock_retriever

        # Should not raise, should return after RAG step
        test_query(query="Test question", rag_only=True)

    @patch('src.cli.test_query.get_config')
    @patch('src.cli.test_query.VectorDBService')
    def test_handles_service_initialization_failure(
        self,
        mock_vectordb_class,
        mock_config
    ):
        """Test handling of service initialization failure."""
        mock_config.return_value.default_llm_provider = "claude-4.5-sonnet"
        mock_vectordb_class.side_effect = Exception("Init failed")

        with pytest.raises(SystemExit):
            test_query(query="Test question")

    @patch('src.cli.test_query.get_config')
    @patch('src.cli.test_query.VectorDBService')
    @patch('src.cli.test_query.EmbeddingService')
    @patch('src.cli.test_query.RAGRetriever')
    def test_handles_rag_retrieval_failure(
        self,
        mock_retriever_class,
        mock_embedding_class,
        mock_vectordb_class,
        mock_config
    ):
        """Test handling of RAG retrieval failure."""
        mock_config.return_value.default_llm_provider = "claude-4.5-sonnet"

        mock_vectordb_class.return_value = Mock()
        mock_embedding_class.return_value = Mock()

        mock_retriever = Mock()
        mock_retriever.retrieve.side_effect = Exception("Retrieval failed")
        mock_retriever_class.return_value = mock_retriever

        with pytest.raises(SystemExit):
            test_query(query="Test question")

    @patch('src.cli.test_query.get_config')
    @patch('src.cli.test_query.VectorDBService')
    @patch('src.cli.test_query.EmbeddingService')
    @patch('src.cli.test_query.RAGRetriever')
    @patch('src.cli.test_query.LLMProviderFactory')
    @patch('src.cli.test_query.ResponseValidator')
    @patch('src.cli.test_query.asyncio.run')
    def test_handles_llm_generation_failure(
        self,
        mock_asyncio_run,
        mock_validator_class,
        mock_llm_factory_class,
        mock_retriever_class,
        mock_embedding_class,
        mock_vectordb_class,
        mock_config
    ):
        """Test handling of LLM generation failure."""
        mock_config.return_value.default_llm_provider = "claude-4.5-sonnet"

        mock_vectordb_class.return_value = Mock()
        mock_embedding_class.return_value = Mock()

        # Mock RAG retriever
        mock_retriever = Mock()
        mock_rag_context = Mock()
        mock_rag_context.total_chunks = 1
        mock_rag_context.avg_relevance = 0.85
        mock_rag_context.meets_threshold = True
        mock_rag_context.document_chunks = []
        mock_retriever.retrieve.return_value = (mock_rag_context, [], {})
        mock_retriever_class.return_value = mock_retriever

        # Mock LLM failure
        mock_asyncio_run.side_effect = Exception("LLM failed")

        mock_llm_factory = Mock()
        mock_llm_factory.create.return_value = Mock()
        mock_llm_factory_class.return_value = mock_llm_factory

        mock_validator_class.return_value = Mock()

        with pytest.raises(SystemExit):
            test_query(query="Test question")

    @patch('src.cli.test_query.get_config')
    @patch('src.cli.test_query.VectorDBService')
    @patch('src.cli.test_query.EmbeddingService')
    @patch('src.cli.test_query.RAGRetriever')
    @patch('src.cli.test_query.LLMProviderFactory')
    @patch('src.cli.test_query.ResponseValidator')
    @patch('src.cli.test_query.asyncio.run')
    def test_handles_validation_failure(
        self,
        mock_asyncio_run,
        mock_validator_class,
        mock_llm_factory_class,
        mock_retriever_class,
        mock_embedding_class,
        mock_vectordb_class,
        mock_config
    ):
        """Test handling of validation failure."""
        mock_config.return_value.default_llm_provider = "claude-4.5-sonnet"

        mock_vectordb_class.return_value = Mock()
        mock_embedding_class.return_value = Mock()

        # Mock RAG retriever
        mock_retriever = Mock()
        mock_rag_context = Mock()
        mock_rag_context.total_chunks = 1
        mock_rag_context.avg_relevance = 0.85
        mock_rag_context.meets_threshold = True
        mock_rag_context.document_chunks = []
        mock_retriever.retrieve.return_value = (mock_rag_context, [], {})
        mock_retriever_class.return_value = mock_retriever

        # Mock LLM
        mock_llm_response = Mock()
        mock_llm_response.answer_text = "Test"
        mock_llm_response.confidence_score = 0.9
        mock_llm_response.token_count = 100
        mock_llm_response.provider = "claude"
        mock_llm_response.model_version = "claude-4.5-sonnet"
        mock_llm_response.prompt_tokens = 80
        mock_llm_response.completion_tokens = 20
        mock_asyncio_run.return_value = mock_llm_response

        mock_llm_factory = Mock()
        mock_llm_factory.create.return_value = Mock()
        mock_llm_factory_class.return_value = mock_llm_factory

        # Mock validator failure
        mock_validator = Mock()
        mock_validator.validate.side_effect = Exception("Validation failed")
        mock_validator_class.return_value = mock_validator

        with pytest.raises(SystemExit):
            test_query(query="Test question")

    @patch('src.cli.test_query.get_config')
    @patch('src.cli.test_query.VectorDBService')
    @patch('src.cli.test_query.EmbeddingService')
    @patch('src.cli.test_query.RAGRetriever')
    def test_overrides_max_hops(
        self,
        mock_retriever_class,
        mock_embedding_class,
        mock_vectordb_class,
        mock_config
    ):
        """Test that max_hops parameter overrides constant."""
        import src.lib.constants as constants
        original_hops = constants.RAG_MAX_HOPS

        mock_config.return_value.default_llm_provider = "claude-4.5-sonnet"

        mock_vectordb_class.return_value = Mock()
        mock_embedding_class.return_value = Mock()

        # Mock RAG retriever
        mock_retriever = Mock()
        mock_rag_context = Mock()
        mock_rag_context.total_chunks = 0
        mock_rag_context.avg_relevance = 0.0
        mock_rag_context.meets_threshold = False
        mock_rag_context.document_chunks = []
        mock_retriever.retrieve.return_value = (mock_rag_context, [], {})
        mock_retriever_class.return_value = mock_retriever

        # Test with max_hops override in RAG-only mode
        test_query(query="Test question", rag_only=True, max_hops=2)

        # Constant should be restored
        assert constants.RAG_MAX_HOPS == original_hops

    @patch('src.cli.test_query.get_config')
    @patch('src.cli.test_query.VectorDBService')
    @patch('src.cli.test_query.EmbeddingService')
    @patch('src.cli.test_query.RAGRetriever')
    def test_uses_custom_max_chunks(
        self,
        mock_retriever_class,
        mock_embedding_class,
        mock_vectordb_class,
        mock_config
    ):
        """Test using custom max_chunks parameter."""
        mock_config.return_value.default_llm_provider = "claude-4.5-sonnet"

        mock_vectordb_class.return_value = Mock()
        mock_embedding_class.return_value = Mock()

        mock_retriever = Mock()
        mock_rag_context = Mock()
        mock_rag_context.total_chunks = 0
        mock_rag_context.avg_relevance = 0.0
        mock_rag_context.meets_threshold = False
        mock_rag_context.document_chunks = []
        mock_retriever.retrieve.return_value = (mock_rag_context, [], {})
        mock_retriever_class.return_value = mock_retriever

        test_query(query="Test question", rag_only=True, max_chunks=20)

        # Should pass max_chunks to retrieve
        call_args = mock_retriever.retrieve.call_args[0][0]
        assert call_args.max_chunks == 20

    @patch('src.cli.test_query.get_config')
    @patch('src.cli.test_query.VectorDBService')
    @patch('src.cli.test_query.EmbeddingService')
    @patch('src.cli.test_query.RAGRetriever')
    @patch('src.cli.test_query.LLMProviderFactory')
    @patch('src.cli.test_query.ResponseValidator')
    @patch('src.cli.test_query.asyncio.run')
    def test_displays_multi_hop_information(
        self,
        mock_asyncio_run,
        mock_validator_class,
        mock_llm_factory_class,
        mock_retriever_class,
        mock_embedding_class,
        mock_vectordb_class,
        mock_config
    ):
        """Test that multi-hop information is displayed when hops are used."""
        mock_config.return_value.default_llm_provider = "claude-4.5-sonnet"

        mock_vectordb_class.return_value = Mock()
        mock_embedding_class.return_value = Mock()

        # Mock RAG retriever with hop evaluations
        mock_retriever = Mock()
        mock_chunk = Mock()
        mock_chunk.chunk_id = "chunk-1"
        mock_chunk.header = "Test Header"
        mock_chunk.text = "Test content"
        mock_chunk.relevance_score = 0.85
        mock_chunk.metadata = {"source": "test"}

        mock_rag_context = Mock()
        mock_rag_context.total_chunks = 1
        mock_rag_context.avg_relevance = 0.85
        mock_rag_context.meets_threshold = True
        mock_rag_context.document_chunks = [mock_chunk]

        mock_hop_eval = Mock()
        mock_hop_eval.can_answer = False
        mock_hop_eval.reasoning = "Need more info"
        mock_hop_eval.missing_query = "Additional query"
        mock_hop_eval.retrieval_time_s = 0.5
        mock_hop_eval.evaluation_time_s = 0.3
        mock_hop_eval.cost_usd = 0.001

        mock_retriever.retrieve.return_value = (
            mock_rag_context,
            [mock_hop_eval],
            {"chunk-1": 1}  # chunk_hop_map
        )
        mock_retriever_class.return_value = mock_retriever

        # Mock LLM
        mock_llm_response = Mock()
        mock_llm_response.answer_text = "Test answer"
        mock_llm_response.confidence_score = 0.9
        mock_llm_response.token_count = 100
        mock_llm_response.provider = "claude"
        mock_llm_response.model_version = "claude-4.5-sonnet"
        mock_llm_response.prompt_tokens = 80
        mock_llm_response.completion_tokens = 20
        mock_asyncio_run.return_value = mock_llm_response

        mock_llm_factory = Mock()
        mock_llm_factory.create.return_value = Mock()
        mock_llm_factory_class.return_value = mock_llm_factory

        mock_validator = Mock()
        mock_validation_result = Mock()
        mock_validation_result.is_valid = True
        mock_validation_result.llm_confidence = 0.9
        mock_validation_result.rag_score = 0.85
        mock_validation_result.reason = "Valid"
        mock_validator.validate.return_value = mock_validation_result
        mock_validator_class.return_value = mock_validator

        # Should display hop information
        test_query(query="Test question", model="claude-4.5-sonnet")
