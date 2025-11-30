"""Unit tests for QueryOrchestrator - business logic and orchestration only.

Tests focus on:
- Method delegation to RAG and LLM services
- Parameter passing and orchestration logic
- Quote validation toggle behavior
- Usage pattern support (RAG-only, separate steps, all-in-one)
- Error handling and edge cases

Excludes:
- RAG service internals (tested separately)
- LLM provider internals (tested separately)
- Boilerplate code (constructors, getters/setters)
"""

import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from src.models.rag_context import RAGContext
from src.models.rag_request import RetrieveRequest
from src.services.llm.base import GenerationRequest, LLMProvider
from src.services.orchestrator import QueryOrchestrator


class TestInitialization:
    """Test QueryOrchestrator initialization."""

    def test_init_with_required_deps(self, mock_rag_retriever, mock_llm_factory):
        """Test orchestrator initializes with required dependencies."""
        orchestrator = QueryOrchestrator(
            rag_retriever=mock_rag_retriever,
            llm_factory=mock_llm_factory,
        )

        assert orchestrator.rag == mock_rag_retriever
        assert orchestrator.llm_factory == mock_llm_factory
        assert orchestrator.enable_quote_validation is True  # Default
        assert orchestrator.quote_validator is not None

    def test_init_with_custom_params(self, mock_rag_retriever, mock_llm_factory):
        """Test orchestrator with custom quote validation settings."""
        orchestrator = QueryOrchestrator(
            rag_retriever=mock_rag_retriever,
            llm_factory=mock_llm_factory,
            enable_quote_validation=False,
            quote_similarity_threshold=0.95,
        )

        assert orchestrator.enable_quote_validation is False
        assert orchestrator.quote_validator.similarity_threshold == 0.95


class TestRetrieveRag:
    """Test retrieve_rag() method - RAG retrieval orchestration."""

    @pytest.mark.asyncio
    async def test_retrieve_rag_basic(self, mock_rag_retriever, mock_llm_factory, sample_chunks):
        """Test basic RAG retrieval without multi-hop."""
        orchestrator = QueryOrchestrator(
            rag_retriever=mock_rag_retriever,
            llm_factory=mock_llm_factory,
        )

        query_id = uuid4()
        rag_context, hop_evals, chunk_map, cost = await orchestrator.retrieve_rag(
            query="Test query",
            query_id=query_id,
            max_chunks=5,
            use_multi_hop=False,
        )

        # Verify RAG service was called
        mock_rag_retriever.retrieve.assert_called_once()
        call_args = mock_rag_retriever.retrieve.call_args

        # Check request parameters
        request = call_args[0][0]
        assert isinstance(request, RetrieveRequest)
        assert request.query == "Test query"
        assert request.max_chunks == 5
        assert request.use_multi_hop is False

        # Check query_id passed through
        assert call_args[1]["query_id"] == query_id

        # Verify return values
        assert rag_context.total_chunks == len(sample_chunks)
        assert hop_evals == []  # No multi-hop
        assert chunk_map == {}
        assert cost > 0  # Embedding cost estimated

    @pytest.mark.asyncio
    async def test_retrieve_rag_with_multi_hop(
        self, mock_rag_retriever_multihop, mock_llm_factory
    ):
        """Test RAG retrieval with multi-hop enabled."""
        orchestrator = QueryOrchestrator(
            rag_retriever=mock_rag_retriever_multihop,
            llm_factory=mock_llm_factory,
        )

        rag_context, hop_evals, chunk_map, cost = await orchestrator.retrieve_rag(
            query="Complex query",
            query_id=uuid4(),
            use_multi_hop=True,
        )

        # Verify multi-hop results
        assert len(hop_evals) == 1
        assert hop_evals[0].reasoning == "Need more context about conceal order"
        assert len(chunk_map) > 0  # Has chunk-hop mapping

    @pytest.mark.asyncio
    @patch("src.services.orchestrator.estimate_embedding_cost")
    async def test_retrieve_rag_cost_estimation(
        self, mock_cost, mock_rag_retriever, mock_llm_factory
    ):
        """Test embedding cost is estimated correctly."""
        mock_cost.return_value = 0.00012

        orchestrator = QueryOrchestrator(
            rag_retriever=mock_rag_retriever,
            llm_factory=mock_llm_factory,
        )

        _, _, _, cost = await orchestrator.retrieve_rag(
            query="Test query",
            query_id=uuid4(),
        )

        assert cost == 0.00012
        mock_cost.assert_called_once_with("Test query")

    @pytest.mark.asyncio
    async def test_retrieve_rag_context_key(self, mock_rag_retriever, mock_llm_factory):
        """Test context_key parameter is passed to RAG service."""
        orchestrator = QueryOrchestrator(
            rag_retriever=mock_rag_retriever,
            llm_factory=mock_llm_factory,
        )

        await orchestrator.retrieve_rag(
            query="Test",
            query_id=uuid4(),
            context_key="guild:user:123",
        )

        # Verify context_key passed to RAG service
        call_args = mock_rag_retriever.retrieve.call_args
        request = call_args[0][0]
        assert request.context_key == "guild:user:123"

    @pytest.mark.asyncio
    async def test_retrieve_rag_timing_logged(self, mock_rag_retriever, mock_llm_factory):
        """Test retrieval time is logged (via orchestrator execution)."""
        orchestrator = QueryOrchestrator(
            rag_retriever=mock_rag_retriever,
            llm_factory=mock_llm_factory,
        )

        # Should not raise and should complete successfully
        rag_context, _, _, cost = await orchestrator.retrieve_rag(
            query="Test query",
            query_id=uuid4(),
        )

        # Verify retrieval completed (timing is logged internally)
        assert rag_context.total_chunks > 0
        assert cost > 0

    @pytest.mark.asyncio
    async def test_retrieve_rag_long_query(self, mock_rag_retriever, mock_llm_factory):
        """Test retrieval with very long query (edge case for embedding)."""
        long_query = "What are the rules for " * 500  # Very long query

        orchestrator = QueryOrchestrator(
            rag_retriever=mock_rag_retriever,
            llm_factory=mock_llm_factory,
        )

        # Should not raise error
        rag_context, _, _, cost = await orchestrator.retrieve_rag(
            query=long_query,
            query_id=uuid4(),
        )

        assert rag_context.total_chunks > 0
        assert cost > 0


class TestGenerateWithContext:
    """Test generate_with_context() method - LLM generation orchestration."""

    @pytest.mark.asyncio
    async def test_generate_with_context_basic(
        self, mock_llm_provider, sample_rag_context, mock_llm_factory
    ):
        """Test basic LLM generation with pre-retrieved context."""
        orchestrator = QueryOrchestrator(
            rag_retriever=Mock(),
            llm_factory=mock_llm_factory,
        )

        query_id = uuid4()
        llm_response, chunk_ids = await orchestrator.generate_with_context(
            query="Test query",
            query_id=query_id,
            model="test-model",
            rag_context=sample_rag_context,
        )

        # Verify factory was called
        mock_llm_factory.create.assert_called_once_with(model_name="test-model")

        # Verify LLM provider was called
        mock_llm_provider.generate.assert_called_once()

        # Check generation request
        call_args = mock_llm_provider.generate.call_args
        request = call_args[0][0]
        assert isinstance(request, GenerationRequest)
        assert request.prompt == "Test query"
        assert len(request.context) == sample_rag_context.total_chunks

        # Verify return values
        assert llm_response.answer_text  # Has response
        assert len(chunk_ids) == sample_rag_context.total_chunks

    @pytest.mark.asyncio
    async def test_generate_with_provided_llm(
        self, mock_llm_provider, sample_rag_context, mock_llm_factory
    ):
        """Test generation with injected LLM provider (skips factory)."""
        orchestrator = QueryOrchestrator(
            rag_retriever=Mock(),
            llm_factory=mock_llm_factory,
        )

        llm_response, _ = await orchestrator.generate_with_context(
            query="Test",
            query_id=uuid4(),
            model="unused",
            rag_context=sample_rag_context,
            llm_provider=mock_llm_provider,  # Injected
        )

        # Factory should NOT be called
        mock_llm_factory.create.assert_not_called()

        # Custom provider should be called
        mock_llm_provider.generate.assert_called_once()

        assert llm_response.answer_text

    @pytest.mark.asyncio
    async def test_generate_with_quote_validation(
        self, mock_llm_provider, sample_rag_context, mock_llm_factory
    ):
        """Test quote validation is performed when enabled."""
        orchestrator = QueryOrchestrator(
            rag_retriever=Mock(),
            llm_factory=mock_llm_factory,
            enable_quote_validation=True,
        )

        # Mock validator
        with patch.object(orchestrator, "_validate_quotes") as mock_validate:
            await orchestrator.generate_with_context(
                query="Test",
                query_id=uuid4(),
                model="test",
                rag_context=sample_rag_context,
                llm_provider=mock_llm_provider,
            )

            mock_validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_without_quote_validation(
        self, mock_llm_provider, sample_rag_context, mock_llm_factory
    ):
        """Test quote validation is skipped when disabled."""
        orchestrator = QueryOrchestrator(
            rag_retriever=Mock(),
            llm_factory=mock_llm_factory,
            enable_quote_validation=False,  # Disabled
        )

        with patch.object(orchestrator, "_validate_quotes") as mock_validate:
            await orchestrator.generate_with_context(
                query="Test",
                query_id=uuid4(),
                model="test",
                rag_context=sample_rag_context,
                llm_provider=mock_llm_provider,
            )

            mock_validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_with_custom_timeout(
        self, mock_llm_provider, sample_rag_context, mock_llm_factory
    ):
        """Test custom timeout is passed to LLM generation."""
        orchestrator = QueryOrchestrator(
            rag_retriever=Mock(),
            llm_factory=mock_llm_factory,
        )

        await orchestrator.generate_with_context(
            query="Test",
            query_id=uuid4(),
            model="test",
            rag_context=sample_rag_context,
            llm_provider=mock_llm_provider,
            generation_timeout=60,  # Custom timeout
        )

        # Check GenerationConfig timeout
        call_args = mock_llm_provider.generate.call_args
        request = call_args[0][0]
        assert request.config.timeout_seconds == 60

    @pytest.mark.asyncio
    async def test_generate_with_empty_context(self, mock_llm_provider, mock_llm_factory):
        """Test generation handles empty RAG context."""
        empty_context = RAGContext.empty(query_id=uuid4())

        orchestrator = QueryOrchestrator(
            rag_retriever=Mock(),
            llm_factory=mock_llm_factory,
        )

        llm_response, chunk_ids = await orchestrator.generate_with_context(
            query="Test",
            query_id=uuid4(),
            model="test",
            rag_context=empty_context,
            llm_provider=mock_llm_provider,
        )

        assert chunk_ids == []
        assert llm_response.answer_text  # Still generates (with no context)


class TestProcessQuery:
    """Test process_query() method - full pipeline orchestration."""

    @pytest.mark.asyncio
    async def test_process_query_full_pipeline(
        self, mock_rag_retriever, mock_llm_provider, mock_llm_factory, _sample_chunks
    ):
        """Test process_query combines retrieve_rag + generate_with_context."""
        orchestrator = QueryOrchestrator(
            rag_retriever=mock_rag_retriever,
            llm_factory=mock_llm_factory,
        )

        llm_response, rag_context, hop_evals, chunk_map, cost = await orchestrator.process_query(
            query="Test query",
            query_id=uuid4(),
            model="test-model",
        )

        # Verify both steps executed
        assert rag_context.total_chunks > 0  # RAG retrieved
        assert llm_response.answer_text  # LLM generated

        mock_rag_retriever.retrieve.assert_called_once()
        mock_llm_provider.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_query_parameters(self, mock_rag_retriever, mock_llm_factory):
        """Test all parameters are passed to sub-methods."""
        orchestrator = QueryOrchestrator(
            rag_retriever=mock_rag_retriever,
            llm_factory=mock_llm_factory,
        )

        query_id = uuid4()

        with patch.object(orchestrator, "retrieve_rag") as mock_retrieve, patch.object(
            orchestrator, "generate_with_context"
        ) as mock_generate:

            # Mock returns
            rag_context = RAGContext.empty(query_id)
            llm_response = Mock()
            mock_retrieve.return_value = (rag_context, [], {}, 0.001)
            mock_generate.return_value = (llm_response, ["chunk1"])

            await orchestrator.process_query(
                query="Test",
                query_id=query_id,
                model="test-model",
                max_chunks=10,
                context_key="custom_key",
                use_multi_hop=False,
                generation_timeout=120,
            )

            # Verify retrieve_rag called with correct params
            mock_retrieve.assert_called_once_with(
                query="Test",
                query_id=query_id,
                max_chunks=10,
                context_key="custom_key",
                use_multi_hop=False,
            )

            # Verify generate_with_context called with correct params
            mock_generate.assert_called_once_with(
                query="Test",
                query_id=query_id,
                model="test-model",
                rag_context=rag_context,
                llm_provider=None,
                generation_timeout=120,
            )


class TestValidateQuotes:
    """Test _validate_quotes() method - quote validation logic."""

    def test_validate_quotes_valid(self, sample_rag_context, mock_llm_factory):
        """Test quote validation with valid quotes."""
        orchestrator = QueryOrchestrator(
            rag_retriever=Mock(),
            llm_factory=mock_llm_factory,
            enable_quote_validation=True,
        )

        # Mock LLM response with valid JSON
        llm_response = Mock()
        llm_response.answer_text = json.dumps(
            {
                "smalltalk": False,
                "quotes": [
                    {
                        "quote_title": "Silent",
                        "quote_text": "Silent allows shooting with the weapon while the operative has a Conceal order.",
                    }
                ],
                "short_answer": "Yes.",
                "persona_short_answer": "Obviously.",
                "explanation": "The Silent weapon rule allows it.",
                "persona_afterword": "Simple.",
            }
        )

        result = orchestrator._validate_quotes(
            llm_response,
            sample_rag_context,
            [str(sample_rag_context.document_chunks[0].chunk_id)],
            "correlation_123",
        )

        assert result is not None
        assert result.valid_quotes >= 0  # Has validation result

    def test_validate_quotes_smalltalk_skips_validation(self, sample_rag_context, mock_llm_factory):
        """Test quote validation is skipped for smalltalk."""
        orchestrator = QueryOrchestrator(
            rag_retriever=Mock(),
            llm_factory=mock_llm_factory,
        )

        # Create structured data with smalltalk=True
        llm_response = Mock()
        llm_response.answer_text = json.dumps(
            {
                "smalltalk": True,
                "short_answer": "Hi!",
                "persona_short_answer": "Greetings.",
                "quotes": [],
                "explanation": "",
                "persona_afterword": "",
            }
        )

        result = orchestrator._validate_quotes(
            llm_response, sample_rag_context, [], "corr_id"
        )

        assert result is None  # Skipped

    def test_validate_quotes_no_quotes(self, sample_rag_context, mock_llm_factory):
        """Test validation returns None when no quotes present."""
        orchestrator = QueryOrchestrator(
            rag_retriever=Mock(),
            llm_factory=mock_llm_factory,
        )

        llm_response = Mock()
        llm_response.answer_text = json.dumps(
            {
                "smalltalk": False,
                "quotes": [],  # Empty
                "short_answer": "Yes.",
                "persona_short_answer": "Obviously.",
                "explanation": "Test explanation",
                "persona_afterword": "Simple.",
            }
        )

        result = orchestrator._validate_quotes(
            llm_response, sample_rag_context, [], "corr_id"
        )

        assert result is None

    def test_validate_quotes_invalid_logged(self, sample_rag_context, mock_llm_factory):
        """Test invalid quotes are handled correctly."""
        orchestrator = QueryOrchestrator(
            rag_retriever=Mock(),
            llm_factory=mock_llm_factory,
        )

        # Mock validator to return invalid quote
        with patch.object(orchestrator.quote_validator, "validate") as mock_validate:
            mock_validate.return_value = Mock(
                is_valid=False,
                valid_quotes=0,
                invalid_quotes=[{"quote_title": "Bad", "reason": "Not found in context"}],
                validation_score=0.0,
            )

            llm_response = Mock()
            llm_response.answer_text = json.dumps(
                {
                    "smalltalk": False,
                    "quotes": [{"quote_title": "Bad", "quote_text": "Invalid quote"}],
                    "short_answer": "Yes.",
                    "persona_short_answer": "Yes.",
                    "explanation": "Test",
                    "persona_afterword": "Test",
                }
            )

            result = orchestrator._validate_quotes(
                llm_response, sample_rag_context, ["chunk1"], "corr_id"
            )

            # Should return result with invalid quote info (logging happens internally)
            assert result is not None
            assert result.is_valid is False
            assert result.valid_quotes == 0

    def test_validate_quotes_invalid_json(self, sample_rag_context, mock_llm_factory):
        """Test graceful handling of invalid JSON in LLM response."""
        orchestrator = QueryOrchestrator(
            rag_retriever=Mock(),
            llm_factory=mock_llm_factory,
        )

        llm_response = Mock()
        llm_response.answer_text = "Not valid JSON"

        # Should not raise, returns None gracefully
        result = orchestrator._validate_quotes(
            llm_response, sample_rag_context, [], "corr_id"
        )

        assert result is None  # Graceful degradation (warning logged internally)

    def test_validate_quotes_exception_handling(self, sample_rag_context, mock_llm_factory):
        """Test exception handling in quote validation."""
        orchestrator = QueryOrchestrator(
            rag_retriever=Mock(),
            llm_factory=mock_llm_factory,
        )

        # Mock validator to raise exception
        with patch.object(orchestrator.quote_validator, "validate") as mock_validate:
            mock_validate.side_effect = Exception("Validation error")

            llm_response = Mock()
            llm_response.answer_text = json.dumps(
                {
                    "smalltalk": False,
                    "quotes": [{"quote_title": "Test", "quote_text": "Test"}],
                    "short_answer": "Yes.",
                    "persona_short_answer": "Yes.",
                    "explanation": "Test",
                    "persona_afterword": "Test",
                }
            )

            # Should not raise, returns None gracefully
            result = orchestrator._validate_quotes(
                llm_response, sample_rag_context, ["chunk1"], "corr_id"
            )

            assert result is None  # Graceful error handling (warning logged internally)


class TestIntegrationPatterns:
    """Test orchestrator usage patterns matching entry points."""

    @pytest.mark.asyncio
    async def test_discord_bot_pattern(
        self, mock_rag_retriever, mock_llm_provider, mock_llm_factory
    ):
        """Test orchestrator usage pattern matching Discord bot."""
        orchestrator = QueryOrchestrator(
            rag_retriever=mock_rag_retriever,
            llm_factory=mock_llm_factory,
            enable_quote_validation=True,
        )

        query_id = uuid4()

        # Step 1: RAG retrieval
        rag_context, hop_evals, chunk_map, cost = await orchestrator.retrieve_rag(
            query="Test",
            query_id=query_id,
            context_key="987654321:123456789",  # guild:user
            use_multi_hop=True,
        )

        # Step 2: LLM generation with custom provider (guild-specific)
        llm_response, chunk_ids = await orchestrator.generate_with_context(
            query="Test",
            query_id=query_id,
            model="guild-model",
            rag_context=rag_context,
            llm_provider=mock_llm_provider,  # Custom provider
        )

        assert llm_response.answer_text
        assert len(chunk_ids) > 0

    @pytest.mark.asyncio
    async def test_quality_test_pattern(
        self, mock_rag_retriever, mock_llm_response, mock_llm_factory
    ):
        """Test orchestrator usage pattern matching quality tests."""
        orchestrator = QueryOrchestrator(
            rag_retriever=mock_rag_retriever,
            llm_factory=mock_llm_factory,
        )

        # Retrieve once
        query_id = uuid4()
        rag_context, hop_evals, chunk_map, cost = await orchestrator.retrieve_rag(
            query="Test query",
            query_id=query_id,
        )

        # Generate multiple times with same context (different models)
        results = []
        for model_name in ["model1", "model2", "model3"]:
            # Create separate provider for each model
            provider = AsyncMock(spec=LLMProvider)
            provider.model = model_name
            provider.generate = AsyncMock(return_value=mock_llm_response)

            llm_response, _ = await orchestrator.generate_with_context(
                query="Test query",
                query_id=query_id,
                model=model_name,
                rag_context=rag_context,  # Reuse same context
                llm_provider=provider,
            )
            results.append(llm_response)

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_rag_only_mode(self, mock_rag_retriever, mock_llm_factory):
        """Test RAG-only mode (no LLM generation)."""
        orchestrator = QueryOrchestrator(
            rag_retriever=mock_rag_retriever,
            llm_factory=mock_llm_factory,  # Won't be used
        )

        # Only retrieve RAG
        rag_context, hop_evals, chunk_map, cost = await orchestrator.retrieve_rag(
            query="Test",
            query_id=uuid4(),
        )

        # Do NOT call generate_with_context
        assert rag_context.total_chunks > 0
        assert cost > 0

        # Verify LLM factory was never called
        mock_llm_factory.create.assert_not_called()


class TestEdgeCases:
    """Test edge cases and robustness."""

    @pytest.mark.asyncio
    async def test_concurrent_retrieve_rag(self, mock_rag_retriever, mock_llm_factory):
        """Test orchestrator handles concurrent calls correctly."""
        orchestrator = QueryOrchestrator(
            rag_retriever=mock_rag_retriever,
            llm_factory=mock_llm_factory,
        )

        # Run 10 concurrent retrievals
        tasks = [
            orchestrator.retrieve_rag(
                query=f"Query {i}",
                query_id=uuid4(),
            )
            for i in range(10)
        ]

        results = await asyncio.gather(*tasks)

        assert len(results) == 10
        # Each should have unique context_id
        context_ids = {r[0].context_id for r in results}
        assert len(context_ids) == 10

    @pytest.mark.asyncio
    async def test_concurrent_generate(
        self, mock_llm_provider, sample_rag_context, mock_llm_factory
    ):
        """Test concurrent LLM generation calls."""
        orchestrator = QueryOrchestrator(
            rag_retriever=Mock(),
            llm_factory=mock_llm_factory,
        )

        # Run 5 concurrent generations
        tasks = [
            orchestrator.generate_with_context(
                query=f"Query {i}",
                query_id=uuid4(),
                model="test",
                rag_context=sample_rag_context,
                llm_provider=mock_llm_provider,
            )
            for i in range(5)
        ]

        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        # Each should have response
        for llm_response, _chunk_ids in results:
            assert llm_response.answer_text
