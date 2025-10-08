"""Unit tests for LLM adapters.

Tests LLM provider implementations with mocked API calls.
Based on specs/001-we-are-building/tasks.md T047
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from src.services.llm.base import (
    GenerationRequest,
    GenerationConfig,
    LLMResponse,
    RateLimitError,
    AuthenticationError,
    TimeoutError,
)
from src.services.llm.claude import ClaudeAdapter
from src.services.llm.chatgpt import ChatGPTAdapter
from src.services.llm.gemini import GeminiAdapter
from src.services.llm.factory import LLMProviderFactory, get_provider
from src.services.llm.validator import ResponseValidator, ValidationResult
from src.services.llm.rate_limiter import RateLimiter, RateLimitConfig
from src.models.rag_context import RAGContext, DocumentChunk


class TestClaudeAdapter:
    """Test Claude LLM adapter."""

    @pytest.fixture
    def mock_anthropic(self):
        """Mock Anthropic client."""
        with patch("src.services.llm.claude.AsyncAnthropic") as mock:
            yield mock

    @pytest.fixture
    def claude_adapter(self, mock_anthropic):
        """Create Claude adapter with mocked client."""
        adapter = ClaudeAdapter(api_key="test-key", model="claude-sonnet-4-5-20250929")
        return adapter

    async def test_generate_success(self, claude_adapter):
        """Test successful generation."""
        # Mock API response
        mock_response = Mock()
        mock_response.content = [Mock(text="According to Core Rules: Movement is 6 inches")]
        mock_response.usage = Mock(input_tokens=100, output_tokens=50)

        claude_adapter.client.messages.create = AsyncMock(return_value=mock_response)

        # Create request
        request = GenerationRequest(
            prompt="How far can I move?",
            context=["Movement Phase: Operatives can move 6 inches"],
            config=GenerationConfig(),
        )

        # Generate response
        response = await claude_adapter.generate(request)

        # Assertions
        assert isinstance(response, LLMResponse)
        assert response.provider == "claude"
        assert response.confidence_score == 0.8  # Claude default
        assert response.token_count == 150
        assert response.citations_included is True
        assert "According to" in response.answer_text

    async def test_generate_rate_limit(self, claude_adapter):
        """Test rate limit error handling."""
        # Mock rate limit error
        claude_adapter.client.messages.create = AsyncMock(
            side_effect=Exception("rate_limit exceeded")
        )

        request = GenerationRequest(
            prompt="Test", context=["Context"], config=GenerationConfig()
        )

        # Should raise RateLimitError
        with pytest.raises(RateLimitError):
            await claude_adapter.generate(request)

    async def test_generate_auth_error(self, claude_adapter):
        """Test authentication error handling."""
        claude_adapter.client.messages.create = AsyncMock(
            side_effect=Exception("authentication failed 401")
        )

        request = GenerationRequest(
            prompt="Test", context=["Context"], config=GenerationConfig()
        )

        with pytest.raises(AuthenticationError):
            await claude_adapter.generate(request)


class TestChatGPTAdapter:
    """Test ChatGPT LLM adapter."""

    @pytest.fixture
    def mock_openai(self):
        """Mock OpenAI client."""
        with patch("src.services.llm.chatgpt.AsyncOpenAI") as mock:
            yield mock

    @pytest.fixture
    def chatgpt_adapter(self, mock_openai):
        """Create ChatGPT adapter with mocked client."""
        adapter = ChatGPTAdapter(api_key="test-key", model="gpt-4-turbo")
        return adapter

    async def test_generate_success(self, chatgpt_adapter):
        """Test successful generation with logprobs."""
        # Mock API response with logprobs
        mock_choice = Mock()
        mock_choice.message.content = "According to Core Rules: Movement is 6 inches"
        mock_choice.logprobs.content = [
            Mock(logprob=-0.1),  # exp(-0.1) ≈ 0.9
            Mock(logprob=-0.2),  # exp(-0.2) ≈ 0.82
        ]

        mock_response = Mock()
        mock_response.choices = [mock_choice]
        mock_response.usage = Mock(total_tokens=150)

        chatgpt_adapter.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        request = GenerationRequest(
            prompt="How far can I move?",
            context=["Movement: 6 inches"],
            config=GenerationConfig(),
        )

        response = await chatgpt_adapter.generate(request)

        assert isinstance(response, LLMResponse)
        assert response.provider == "chatgpt"
        assert 0.8 <= response.confidence_score <= 0.9  # Based on logprobs
        assert response.token_count == 150
        assert response.citations_included is True

    async def test_calculate_confidence(self, chatgpt_adapter):
        """Test confidence calculation from logprobs."""
        # Mock logprobs
        mock_logprobs = Mock()
        mock_logprobs.content = [
            Mock(logprob=-0.1),  # ~0.9
            Mock(logprob=-0.5),  # ~0.6
        ]

        confidence = chatgpt_adapter._calculate_confidence(mock_logprobs)

        assert 0.7 <= confidence <= 0.8  # Average should be around 0.75


class TestGeminiAdapter:
    """Test Gemini LLM adapter."""

    @pytest.fixture
    def mock_genai(self):
        """Mock Google GenAI."""
        with patch("src.services.llm.gemini.genai") as mock:
            yield mock

    @pytest.fixture
    def gemini_adapter(self, mock_genai):
        """Create Gemini adapter with mocked client."""
        mock_model = Mock()
        mock_genai.GenerativeModel.return_value = mock_model
        adapter = GeminiAdapter(api_key="test-key", model="gemini-2.5-pro")
        return adapter

    async def test_generate_success(self, gemini_adapter):
        """Test successful generation."""
        # Mock API response with candidates
        mock_candidate = Mock()
        mock_candidate.finish_reason = 1  # STOP
        mock_candidate.content = Mock()
        mock_candidate.content.parts = [Mock()]  # Has valid parts

        mock_response = Mock()
        mock_response.text = "According to Core Rules: Movement is 6 inches"
        mock_response.candidates = [mock_candidate]
        mock_response.safety_ratings = [
            Mock(probability="LOW"),  # 0.8 confidence
            Mock(probability="NEGLIGIBLE"),  # 0.9 confidence
        ]
        mock_response.usage_metadata = Mock(total_token_count=150)

        gemini_adapter.client.generate_content = Mock(return_value=mock_response)

        request = GenerationRequest(
            prompt="How far can I move?",
            context=["Movement: 6 inches"],
            config=GenerationConfig(timeout_seconds=25),
        )

        response = await gemini_adapter.generate(request)

        assert isinstance(response, LLMResponse)
        assert response.provider == "gemini"
        assert 0.8 <= response.confidence_score <= 0.9  # Based on safety ratings
        assert response.token_count == 150

    def test_safety_to_confidence(self, gemini_adapter):
        """Test safety rating to confidence mapping."""
        # Test different safety levels
        ratings = [
            Mock(probability="NEGLIGIBLE"),  # 0.9
            Mock(probability="LOW"),  # 0.8
            Mock(probability="MEDIUM"),  # 0.7
        ]

        confidence = gemini_adapter._safety_to_confidence(ratings)

        assert 0.7 <= confidence <= 0.85  # Average around 0.8


class TestLLMProviderFactory:
    """Test LLM provider factory."""

    def test_get_available_providers(self):
        """Test getting list of available models."""
        providers = LLMProviderFactory.get_available_providers()

        assert "claude-sonnet" in providers
        assert "claude-opus" in providers
        assert "gemini-2.5-pro" in providers
        assert "gpt-4o" in providers
        assert len(providers) == 12  # Total number of models

    @patch("src.services.llm.factory.get_config")
    def test_create_claude_provider(self, mock_config):
        """Test creating Claude Sonnet provider."""
        config_obj = Mock()
        config_obj.anthropic_api_key = "test-key"
        config_obj.default_llm_provider = "claude-sonnet"
        mock_config.return_value = config_obj

        with patch("src.services.llm.claude.AsyncAnthropic"):
            provider = LLMProviderFactory.create("claude-sonnet")

            assert isinstance(provider, ClaudeAdapter)
            assert provider.model == "claude-sonnet-4-5-20250929"

    @patch("src.services.llm.factory.get_config")
    def test_create_invalid_provider(self, mock_config):
        """Test creating invalid model raises error."""
        mock_config.return_value = {}

        with pytest.raises(ValueError, match="Invalid model"):
            LLMProviderFactory.create("invalid")


class TestResponseValidator:
    """Test response validation service."""

    @pytest.fixture
    def validator(self):
        """Create validator with default thresholds."""
        return ResponseValidator(
            llm_confidence_threshold=0.7,
            rag_score_threshold=0.6,
        )

    @pytest.fixture
    def llm_response_high(self):
        """Create high-confidence LLM response."""
        return LLMResponse(
            response_id=uuid4(),
            answer_text="Test answer",
            confidence_score=0.85,
            token_count=100,
            latency_ms=500,
            provider="claude",
            model_version="claude-sonnet-4-5-20250929",
            citations_included=True,
        )

    @pytest.fixture
    def llm_response_low(self):
        """Create low-confidence LLM response."""
        return LLMResponse(
            response_id=uuid4(),
            answer_text="Test answer",
            confidence_score=0.5,
            token_count=100,
            latency_ms=500,
            provider="claude",
            model_version="claude-sonnet-4-5-20250929",
            citations_included=False,
        )

    @pytest.fixture
    def rag_context_high(self):
        """Create high-relevance RAG context."""
        return RAGContext(
            context_id=uuid4(),
            query_id=uuid4(),
            document_chunks=[
                DocumentChunk(
                    chunk_id=uuid4(),
                    document_id=uuid4(),
                    text="Test chunk",
                    header="Test",
                    header_level=2,
                    metadata={},
                    relevance_score=0.9,
                    position_in_doc=1,
                )
            ],
            relevance_scores=[0.9],
            total_chunks=1,
            avg_relevance=0.9,
            meets_threshold=True,
        )

    @pytest.fixture
    def rag_context_low(self):
        """Create low-relevance RAG context."""
        return RAGContext(
            context_id=uuid4(),
            query_id=uuid4(),
            document_chunks=[
                DocumentChunk(
                    chunk_id=uuid4(),
                    document_id=uuid4(),
                    text="Test chunk",
                    header="Test",
                    header_level=2,
                    metadata={},
                    relevance_score=0.4,
                    position_in_doc=1,
                )
            ],
            relevance_scores=[0.4],
            total_chunks=1,
            avg_relevance=0.4,
            meets_threshold=False,
        )

    def test_validate_both_pass(
        self, validator, llm_response_high, rag_context_high
    ):
        """Test validation when both thresholds pass."""
        result = validator.validate(llm_response_high, rag_context_high)

        assert result.is_valid is True
        assert result.llm_confidence == 0.85
        assert result.rag_score == 0.9
        assert "passed validation" in result.reason

    def test_validate_llm_fails(self, validator, llm_response_low, rag_context_high):
        """Test validation when LLM confidence fails."""
        result = validator.validate(llm_response_low, rag_context_high)

        assert result.is_valid is False
        assert "LLM confidence" in result.reason

    def test_validate_rag_fails(self, validator, llm_response_high, rag_context_low):
        """Test validation when RAG score fails."""
        result = validator.validate(llm_response_high, rag_context_low)

        assert result.is_valid is False
        assert "RAG score" in result.reason

    def test_validate_both_fail(self, validator, llm_response_low, rag_context_low):
        """Test validation when both fail."""
        result = validator.validate(llm_response_low, rag_context_low)

        assert result.is_valid is False
        assert "LLM confidence" in result.reason
        assert "RAG score" in result.reason

    def test_should_send_response(
        self, validator, llm_response_high, rag_context_high
    ):
        """Test should_send_response convenience method."""
        should_send, reason = validator.should_send_response(
            llm_response_high, rag_context_high
        )

        assert should_send is True
        assert "passed validation" in reason

    def test_get_fallback_message(self, validator):
        """Test fallback message generation."""
        message = validator.get_fallback_message()

        assert "cannot provide a confident answer" in message
        assert "rephrasing" in message


class TestRateLimiter:
    """Test rate limiter."""

    @pytest.fixture
    def rate_limiter(self):
        """Create rate limiter with test config."""
        config = RateLimitConfig(
            max_requests=10,
            window_seconds=60,
            burst_size=15,
        )
        return RateLimiter(config)

    def test_check_rate_limit_allowed(self, rate_limiter):
        """Test rate limit check allows requests."""
        is_allowed, retry_after = rate_limiter.check_rate_limit("claude", "user123")

        assert is_allowed is True
        assert retry_after == 0.0

    def test_check_rate_limit_exceed(self, rate_limiter):
        """Test rate limit exceeded after max requests."""
        # Consume all tokens
        for _ in range(10):
            is_allowed, _ = rate_limiter.check_rate_limit("claude", "user123")
            assert is_allowed is True

        # 11th request should be denied
        is_allowed, retry_after = rate_limiter.check_rate_limit("claude", "user123")

        assert is_allowed is False
        assert retry_after > 0

    def test_rate_limit_per_user(self, rate_limiter):
        """Test rate limits are per-user."""
        # User 1 consumes all tokens
        for _ in range(10):
            rate_limiter.check_rate_limit("claude", "user1")

        # User 2 should still have tokens
        is_allowed, _ = rate_limiter.check_rate_limit("claude", "user2")
        assert is_allowed is True

    def test_rate_limit_per_provider(self, rate_limiter):
        """Test rate limits are per-provider."""
        # Consume all tokens for claude
        for _ in range(10):
            rate_limiter.check_rate_limit("claude", "user1")

        # ChatGPT should have separate limit
        is_allowed, _ = rate_limiter.check_rate_limit("chatgpt", "user1")
        assert is_allowed is True

    def test_reset(self, rate_limiter):
        """Test reset functionality."""
        # Consume all tokens
        for _ in range(10):
            rate_limiter.check_rate_limit("claude", "user1")

        # Reset
        rate_limiter.reset("claude", "user1")

        # Should be allowed again
        is_allowed, _ = rate_limiter.check_rate_limit("claude", "user1")
        assert is_allowed is True

    def test_get_stats(self, rate_limiter):
        """Test getting rate limit stats."""
        # Make a few requests
        rate_limiter.check_rate_limit("claude", "user1")
        rate_limiter.check_rate_limit("claude", "user1")

        stats = rate_limiter.get_stats("claude", "user1")

        assert "tokens_remaining" in stats
        assert "last_update" in stats
        assert stats["tokens_remaining"] < 10  # Some tokens consumed

    def test_cleanup_old_buckets(self, rate_limiter):
        """Test cleanup of old buckets."""
        rate_limiter.check_rate_limit("claude", "user1")

        # Should have 1 bucket
        assert len(rate_limiter._buckets) == 1

        # Cleanup with 0 max_age should remove it
        removed = rate_limiter.cleanup_old_buckets(max_age_seconds=0)

        assert removed == 1
        assert len(rate_limiter._buckets) == 0
