"""Unit tests for LLM adapters.

Tests LLM provider implementations with mocked API calls.
Based on specs/001-we-are-building/tasks.md T047
"""

import json
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import anthropic
import pytest

from src.models.rag_context import DocumentChunk, RAGContext
from src.services.llm.base import (
    AuthenticationError,
    GenerationConfig,
    GenerationRequest,
    LLMResponse,
    RateLimitError,
)
from src.services.llm.chatgpt import ChatGPTAdapter
from src.services.llm.claude import ClaudeAdapter
from src.services.llm.factory import LLMProviderFactory
from src.services.llm.gemini import GeminiAdapter
from src.services.llm.grok import GrokAdapter
from src.services.llm.rate_limiter import RateLimitConfig, RateLimiter
from src.services.llm.validator import ResponseValidator


class TestClaudeAdapter:
    """Test Claude LLM adapter."""

    @pytest.fixture
    def mock_anthropic(self):
        """Mock Anthropic client."""
        with patch("src.services.llm.claude.AsyncAnthropic") as mock:
            yield mock

    @pytest.fixture
    def claude_adapter(self):
        """Create Claude adapter with mocked client."""
        adapter = ClaudeAdapter(api_key="test-key", model="claude-sonnet-4-5-20250929")
        return adapter

    async def test_generate_rate_limit(self, claude_adapter):
        """Test rate limit error handling."""
        # Mock rate limit error (new Pydantic approach uses beta.messages.parse)
        # Create mock response for Anthropic exception
        mock_response = Mock()
        mock_response.status_code = 429
        mock_body = {"error": {"message": "rate_limit exceeded", "type": "rate_limit_error"}}

        claude_adapter.client.beta.messages.parse = AsyncMock(
            side_effect=anthropic.RateLimitError(
                "rate_limit exceeded", response=mock_response, body=mock_body
            )
        )

        request = GenerationRequest(
            prompt="Test", context=["Context"], config=GenerationConfig(), chunk_ids=["test-chunk-1"]
        )

        # Should raise RateLimitError
        with pytest.raises(RateLimitError):
            await claude_adapter.generate(request)

    async def test_generate_auth_error(self, claude_adapter):
        """Test authentication error handling."""
        # Mock authentication error (new Pydantic approach uses beta.messages.parse)
        # Create mock response for Anthropic exception
        mock_response = Mock()
        mock_response.status_code = 401
        mock_body = {"error": {"message": "authentication failed 401", "type": "authentication_error"}}

        claude_adapter.client.beta.messages.parse = AsyncMock(
            side_effect=anthropic.AuthenticationError(
                "authentication failed 401", response=mock_response, body=mock_body
            )
        )

        request = GenerationRequest(
            prompt="Test", context=["Context"], config=GenerationConfig(), chunk_ids=["test-chunk-1"]
        )

        with pytest.raises(AuthenticationError):
            await claude_adapter.generate(request)

    async def test_generate_with_list_prompt_passes_blocks_as_content(self, claude_adapter):
        """list[dict] prompt is forwarded directly as message content for cache-control blocks."""
        blocks = [
            {"type": "text", "text": "static instructions", "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": "dynamic query"},
        ]

        mock_parsed = Mock()
        mock_parsed.model_dump_json.return_value = '{"smalltalk":false,"short_answer":"Yes","persona_short_answer":"Obviously","quotes":[],"explanation":"test","persona_afterword":"Done"}'
        mock_parsed.model_dump.return_value = {
            "smalltalk": False,
            "short_answer": "Yes",
            "persona_short_answer": "Obviously",
            "quotes": [],
            "explanation": "test",
            "persona_afterword": "Done",
        }

        mock_usage = Mock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 20
        mock_usage.cache_read_input_tokens = 80
        mock_usage.cache_creation_input_tokens = 0

        mock_response = Mock()
        mock_response.parsed_output = mock_parsed
        mock_response.usage = mock_usage

        claude_adapter.client.beta.messages.parse = AsyncMock(return_value=mock_response)

        request = GenerationRequest(
            prompt=blocks,
            context=[],
            chunk_ids=[],
            config=GenerationConfig(system_prompt=""),
        )

        await claude_adapter.generate(request)

        call_kwargs = claude_adapter.client.beta.messages.parse.call_args.kwargs
        assert call_kwargs["messages"][0]["content"] == blocks

    async def test_generate_with_str_prompt_builds_content_via_template(self, claude_adapter):
        """str prompt still goes through _build_prompt (existing behavior preserved)."""
        mock_parsed = Mock()
        mock_parsed.model_dump_json.return_value = '{"smalltalk":false,"short_answer":"Yes","persona_short_answer":"Obviously","quotes":[],"explanation":"test","persona_afterword":"Done"}'
        mock_parsed.model_dump.return_value = {
            "smalltalk": False,
            "short_answer": "Yes",
            "persona_short_answer": "Obviously",
            "quotes": [],
            "explanation": "test",
            "persona_afterword": "Done",
        }

        mock_usage = Mock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 20
        mock_usage.cache_read_input_tokens = 0
        mock_usage.cache_creation_input_tokens = 0

        mock_response = Mock()
        mock_response.parsed_output = mock_parsed
        mock_response.usage = mock_usage

        claude_adapter.client.beta.messages.parse = AsyncMock(return_value=mock_response)

        request = GenerationRequest(
            prompt="Can I shoot twice?",
            context=[],
            chunk_ids=[],
            config=GenerationConfig(system_prompt=""),
        )

        await claude_adapter.generate(request)

        call_kwargs = claude_adapter.client.beta.messages.parse.call_args.kwargs
        content = call_kwargs["messages"][0]["content"]
        # str prompt → _build_prompt → wrapped string, not the raw query
        assert isinstance(content, str)
        assert "Can I shoot twice?" in content

    async def test_haiku_55_hop_evaluation_omits_temperature(self):
        """Haiku 5.5 as RAG hop judge: forced tool use, no temperature (400 on the API).

        The response leads with a thinking block, so the tool_use block is found by type.
        """
        adapter = ClaudeAdapter(api_key="test-key", model="claude-haiku-5-5")
        hop_input = {"can_answer": True, "reasoning": "Enough context.", "missing_query": None}

        mock_usage = Mock(input_tokens=500, output_tokens=40,
                          cache_read_input_tokens=0, cache_creation_input_tokens=0)
        mock_response = Mock(
            content=[Mock(type="thinking"), Mock(type="tool_use", input=hop_input)],
            usage=mock_usage,
        )
        adapter.client.messages.create = AsyncMock(return_value=mock_response)

        request = GenerationRequest(
            prompt="Is the context sufficient?",
            context=[],
            chunk_ids=[],
            config=GenerationConfig(
                system_prompt="", max_tokens=300, temperature=0.3,
                structured_output_schema="hop_evaluation",
            ),
        )

        response = await adapter.generate(request)

        call_kwargs = adapter.client.messages.create.call_args.kwargs
        assert "temperature" not in call_kwargs
        assert call_kwargs["tool_choice"]["type"] == "tool"
        assert response.structured_output == hop_input

    async def test_sonnet_55_judge_uses_output_config_format(self):
        """Sonnet 5.5: JSON via output_config.format in extra_body, parsed from the text block.

        Numeric bounds (unsupported by structured outputs) are stripped from the schema.
        """
        adapter = ClaudeAdapter(api_key="test-key", model="claude-sonnet-5-5")
        judge = {"explanation_faithfulness": 0.9, "feedback": "ok", "answer_correctness_details": []}

        mock_usage = Mock(input_tokens=500, output_tokens=40,
                          cache_read_input_tokens=0, cache_creation_input_tokens=0)
        mock_response = Mock(
            content=[Mock(type="thinking"), Mock(type="text", text=json.dumps(judge))],
            usage=mock_usage,
            stop_reason="end_turn",
        )
        adapter.client.messages.create = AsyncMock(return_value=mock_response)

        request = GenerationRequest(
            prompt="Judge this.",
            context=[],
            chunk_ids=[],
            config=GenerationConfig(system_prompt="", structured_output_schema="custom_judge"),
        )

        response = await adapter.generate(request)

        call_kwargs = adapter.client.messages.create.call_args.kwargs
        assert "tool_choice" not in call_kwargs and "temperature" not in call_kwargs
        assert call_kwargs["extra_body"]["thinking"] == {"type": "between_tools"}
        schema = call_kwargs["extra_body"]["output_config"]["format"]["schema"]
        assert "minimum" not in schema["properties"]["explanation_faithfulness"]
        assert response.structured_output == judge


class TestChatGPTAdapter:
    """Test ChatGPT LLM adapter."""

    @pytest.fixture
    def mock_openai(self):
        """Mock OpenAI client."""
        with patch("src.services.llm.chatgpt.AsyncOpenAI") as mock:
            yield mock

    @pytest.fixture
    def chatgpt_adapter(self):
        """Create ChatGPT adapter with mocked client."""
        adapter = ChatGPTAdapter(api_key="test-key", model="gpt-4-turbo")
        return adapter

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


class TestGrokAdapter:
    """Test Grok LLM adapter."""

    @pytest.fixture
    def mock_httpx(self):
        """Mock httpx client."""
        with patch("src.services.llm.grok.httpx") as mock:
            yield mock

    @pytest.fixture
    def grok_adapter(self, mock_httpx):
        """Create Grok adapter with mocked client."""
        with patch("src.services.llm.grok.httpx", mock_httpx):
            adapter = GrokAdapter(api_key="test-key", model="grok-3")
            return adapter

    async def test_generate_rate_limit(self, grok_adapter, mock_httpx):
        """Test rate limit error handling."""
        # Mock 429 response
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"

        # Mock the AsyncClient context manager properly
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_client)
        mock_context_manager.__aexit__ = AsyncMock(return_value=None)

        mock_httpx.AsyncClient.return_value = mock_context_manager

        request = GenerationRequest(
            prompt="Test query", context=[], config=GenerationConfig(), chunk_ids=[]
        )

        with pytest.raises(RateLimitError, match="Grok rate limit"):
            await grok_adapter.generate(request)

    async def test_multi_agent_uses_responses_api(self, mock_httpx):
        """Multi-agent model: /responses with text.format and reasoning.effort, no max tokens."""
        adapter = GrokAdapter(api_key="test-key", model="grok-4.20-multi-agent-0309")
        adapter.reasoning_effort = "high"
        hop = {"can_answer": True, "reasoning": "Enough.", "missing_query": None}

        mock_response = Mock(status_code=200)
        mock_response.json.return_value = {
            "model": "grok-4.20-multi-agent-0309",
            "status": "completed",
            "output": [
                {"type": "reasoning", "content": []},
                {"type": "message", "content": [{"type": "output_text", "text": json.dumps(hop)}]},
            ],
            "usage": {"input_tokens": 2708, "output_tokens": 991,
                      "input_tokens_details": {"cached_tokens": 2560}},
        }
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_client)
        mock_context_manager.__aexit__ = AsyncMock(return_value=None)
        mock_httpx.AsyncClient.return_value = mock_context_manager

        request = GenerationRequest(
            prompt="Enough context?", context=[], chunk_ids=[],
            config=GenerationConfig(system_prompt="", structured_output_schema="hop_evaluation"),
        )
        response = await adapter.generate(request)

        url = mock_client.post.call_args.args[0]
        payload = mock_client.post.call_args.kwargs["json"]
        assert url.endswith("/responses")
        assert payload["reasoning"] == {"effort": "high"}
        assert payload["text"]["format"]["type"] == "json_schema"
        assert "max_output_tokens" not in payload and "max_tokens" not in payload
        assert response.structured_output == hop
        assert response.completion_tokens == 991
        assert response.cache_read_tokens == 2560

    async def test_generate_auth_error(self, grok_adapter, mock_httpx):
        """Test authentication error handling."""
        # Mock 401 response
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        # Mock the AsyncClient context manager properly
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_client)
        mock_context_manager.__aexit__ = AsyncMock(return_value=None)

        mock_httpx.AsyncClient.return_value = mock_context_manager

        request = GenerationRequest(
            prompt="Test query", context=[], config=GenerationConfig(), chunk_ids=[]
        )

        with pytest.raises(AuthenticationError, match="Grok auth error"):
            await grok_adapter.generate(request)


class TestLLMProviderFactory:
    """Test LLM provider factory."""

    def test_get_available_providers(self):
        """Test getting list of available models."""
        providers = LLMProviderFactory.get_available_providers()

        assert "claude-4.6-sonnet" in providers
        assert "claude-4.8-opus" in providers
        assert "gemini-2.5-pro" in providers
        assert "gpt-4.1" in providers
        assert "grok-4.3" in providers
        assert "deepseek-v4-flash" in providers

    @patch("src.services.llm.factory.get_config")
    def test_create_claude_provider(self, mock_config):
        """Test creating Claude Sonnet provider."""
        config_obj = Mock()
        config_obj.anthropic_api_key = "test-key"
        config_obj.default_llm_provider = "claude-sonnet"
        mock_config.return_value = config_obj

        with patch("src.services.llm.claude.AsyncAnthropic"):
            provider = LLMProviderFactory.create("claude-4.5-sonnet")

            assert isinstance(provider, ClaudeAdapter)
            assert provider.model == "claude-sonnet-4-5-20250929"

    @patch("src.services.llm.factory.get_config")
    def test_create_grok_provider(self, mock_config):
        """Test creating Grok provider."""
        config_obj = Mock()
        config_obj.x_api_key = "test-key"
        config_obj.default_llm_provider = "grok-3"
        mock_config.return_value = config_obj

        with patch("src.services.llm.grok.httpx"):
            provider = LLMProviderFactory.create("grok-3")

            assert isinstance(provider, GrokAdapter)
            assert provider.model == "grok-3"

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
        return ResponseValidator(llm_confidence_threshold=0.7, rag_score_threshold=0.6)

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

    def test_validate_both_pass(self, validator, llm_response_high, rag_context_high):
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

    def test_should_send_response(self, validator, llm_response_high, rag_context_high):
        """Test should_send_response convenience method."""
        should_send, reason = validator.should_send_response(llm_response_high, rag_context_high)

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
        config = RateLimitConfig(max_requests=10, window_seconds=60, burst_size=15)
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
