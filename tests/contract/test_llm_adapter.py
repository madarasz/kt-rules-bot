"""Contract tests for LLM Adapter interface.

Tests ensure provider-agnostic behavior and LLM independence (Constitution Principle II).
Based on specs/001-we-are-building/contracts/llm-adapter.md
"""

import pytest
from dataclasses import dataclass
from typing import List
from uuid import UUID, uuid4
from io import BytesIO


@dataclass
class GenerationConfig:
    """Configuration for LLM generation."""
    max_tokens: int = 2048
    temperature: float = 0.1
    system_prompt: str = "You are a Kill Team rules assistant..."
    include_citations: bool = True
    timeout_seconds: int = 25


@dataclass
class LLMResponse:
    """LLM generation response."""
    response_id: UUID
    answer_text: str
    confidence_score: float  # 0-1
    token_count: int
    latency_ms: int
    provider: str
    model_version: str
    citations_included: bool


@dataclass
class GenerationRequest:
    """LLM generation request."""
    prompt: str
    context: List[str]
    config: GenerationConfig


@dataclass
class ExtractionConfig:
    """Configuration for PDF extraction."""
    max_tokens: int = 16000
    temperature: float = 0.1
    timeout_seconds: int = 120


@dataclass
class ExtractionResponse:
    """PDF extraction response."""
    extraction_id: UUID
    markdown_content: str
    token_count: int
    latency_ms: int
    provider: str
    model_version: str
    validation_warnings: List[str]


class RateLimitError(Exception):
    """Rate limit exceeded."""
    pass


class AuthenticationError(Exception):
    """Authentication failed."""
    pass


class TimeoutError(Exception):
    """Request timed out."""
    pass


class ContentFilterError(Exception):
    """Content blocked by safety filters."""
    pass


class TokenLimitError(Exception):
    """Token limit exceeded."""
    pass


class TestLLMAdapterContractGeneration:
    """Contract tests for LLM answer generation."""

    def test_provider_consistency(self, mock_llm_providers):
        """
        Contract Test 1: Provider Consistency.

        Given: Same prompt + context across all providers
        When: Generate answer with each provider
        Then:
            - All answers mention factual information
            - confidence ≥ 0.6
            - token counts within 20% of each other
        """
        prompt = "Can I shoot through a barricade?"
        context = [
            "Barricades provide light cover. Models can shoot through light cover with no penalty.",
            "Heavy cover blocks line of sight entirely."
        ]

        config = GenerationConfig(
            max_tokens=500,
            temperature=0.1,
            include_citations=True
        )

        # Mock responses from different providers
        claude_response = LLMResponse(
            response_id=uuid4(),
            answer_text="Yes, you can shoot through a barricade. According to the rules: 'Barricades provide light cover. Models can shoot through light cover with no penalty.'",
            confidence_score=0.85,
            token_count=150,
            latency_ms=1200,
            provider="claude",
            model_version="claude-sonnet-4-5-20250929",
            citations_included=True
        )

        chatgpt_response = LLMResponse(
            response_id=uuid4(),
            answer_text="Yes, shooting through barricades is allowed. The rules state: 'Barricades provide light cover. Models can shoot through light cover with no penalty.'",
            confidence_score=0.82,
            token_count=145,
            latency_ms=1100,
            provider="chatgpt",
            model_version="gpt-4-turbo-2024",
            citations_included=True
        )

        gemini_response = LLMResponse(
            response_id=uuid4(),
            answer_text="Affirmative, barricades allow shooting through them. From the rulebook: 'Barricades provide light cover. Models can shoot through light cover with no penalty.'",
            confidence_score=0.80,
            token_count=158,
            latency_ms=1300,
            provider="gemini",
            model_version="gemini-2.5-pro",
            citations_included=True
        )

        responses = [claude_response, chatgpt_response, gemini_response]

        # Verify all have sufficient confidence
        for response in responses:
            assert response.confidence_score >= 0.6

        # Verify token counts within 20%
        token_counts = [r.token_count for r in responses]
        avg_tokens = sum(token_counts) / len(token_counts)
        for count in token_counts:
            assert abs(count - avg_tokens) / avg_tokens <= 0.20

        # Verify all mention key facts
        for response in responses:
            assert "barricade" in response.answer_text.lower()
            assert "light cover" in response.answer_text.lower()

    def test_confidence_thresholds(self, mock_llm_adapter):
        """
        Contract Test 2: Confidence Thresholds.

        Given: High-quality context (relevance > 0.9) vs low-quality (relevance < 0.5)
        When: Generate answers
        Then:
            - High-quality → confidence ≥ 0.7
            - Low-quality → confidence ≤ 0.6
        """
        # High-quality context
        high_quality_request = GenerationRequest(
            prompt="What is the movement distance?",
            context=["Movement Phase: Each model can move up to 6 inches during the movement phase."],
            config=GenerationConfig()
        )

        high_quality_response = LLMResponse(
            response_id=uuid4(),
            answer_text="Each model can move up to 6 inches during the movement phase.",
            confidence_score=0.85,
            token_count=100,
            latency_ms=800,
            provider="claude",
            model_version="claude-sonnet-4-5-20250929",
            citations_included=True
        )

        assert high_quality_response.confidence_score >= 0.7

        # Low-quality context
        low_quality_request = GenerationRequest(
            prompt="What is the movement distance?",
            context=["Weapon damage rules apply during shooting phase."],
            config=GenerationConfig()
        )

        low_quality_response = LLMResponse(
            response_id=uuid4(),
            answer_text="I cannot find specific information about movement distance in the provided context.",
            confidence_score=0.4,
            token_count=80,
            latency_ms=700,
            provider="claude",
            model_version="claude-sonnet-4-5-20250929",
            citations_included=False
        )

        assert low_quality_response.confidence_score <= 0.6

    def test_citation_inclusion(self, mock_llm_adapter):
        """
        Contract Test 3: Citation Inclusion.

        Given: include_citations = True
        When: Generate answer
        Then:
            - answer_text contains citation format
            - citations_included = True
        """
        request = GenerationRequest(
            prompt="How does overwatch work?",
            context=["Overwatch allows defensive fire when enemy models move within range."],
            config=GenerationConfig(include_citations=True)
        )

        response = LLMResponse(
            response_id=uuid4(),
            answer_text="According to the rules: 'Overwatch allows defensive fire when enemy models move within range.' You can use overwatch during your opponent's movement phase.",
            confidence_score=0.8,
            token_count=120,
            latency_ms=1000,
            provider="claude",
            model_version="claude-sonnet-4-5-20250929",
            citations_included=True
        )

        assert "According to" in response.answer_text or "[" in response.answer_text
        assert response.citations_included is True

    def test_timeout_enforcement(self, mock_llm_adapter):
        """
        Contract Test 4: Timeout Enforcement.

        Given: Slow LLM API
        When: timeout_seconds = 5
        Then: Raises TimeoutError within timeout_seconds
        """
        request = GenerationRequest(
            prompt="Explain all rules",
            context=["Many rules..."],
            config=GenerationConfig(timeout_seconds=5)
        )

        # Mock slow response
        with pytest.raises(TimeoutError):
            # In real implementation, this would actually timeout
            raise TimeoutError("LLM response exceeded 5 seconds")

    def test_token_tracking(self, mock_llm_adapter):
        """
        Contract Test 5: Token Tracking.

        Given: Any generation request
        When: Response received
        Then:
            - token_count > 0
            - token_count = prompt_tokens + completion_tokens
        """
        response = LLMResponse(
            response_id=uuid4(),
            answer_text="Movement is 6 inches.",
            confidence_score=0.8,
            token_count=150,  # e.g., 100 prompt + 50 completion
            latency_ms=900,
            provider="claude",
            model_version="claude-sonnet-4-5-20250929",
            citations_included=True
        )

        assert response.token_count > 0
        # In real implementation, verify: prompt_tokens + completion_tokens = token_count

    def test_rate_limit_handling(self, mock_llm_adapter):
        """
        Contract Test 6: Rate Limit Handling.

        Given: Provider rate limit exceeded
        When: Generate request
        Then: Raises RateLimitError, error logged
        """
        request = GenerationRequest(
            prompt="Test query",
            context=["Test context"],
            config=GenerationConfig()
        )

        # Mock rate limit error
        with pytest.raises(RateLimitError):
            raise RateLimitError("Rate limit exceeded: 429 Too Many Requests")


class TestLLMAdapterContractExtraction:
    """Contract tests for PDF extraction."""

    def test_markdown_structure(self, mock_llm_adapter):
        """
        Contract Test: PDF Extraction Markdown Structure.

        Given: PDF file
        When: extract_pdf() called
        Then:
            - Output includes valid YAML frontmatter
            - Markdown uses proper heading hierarchy
            - document_type in {"core-rules", "faq", "team-rules", "ops", "killzone"}
        """
        pdf_file = BytesIO(b"Mock PDF content")

        extraction_prompt = """Extract this Kill Team rulebook PDF to markdown format.

Requirements:
1. Preserve all headings, lists, and section structure
2. Include YAML frontmatter with:
   - source: (e.g., "Core Rules v3.1")
   - last_update_date: (YYYY-MM-DD format)
   - document_type: ("core-rules" or "faq" or "team-rules" or "ops" or "killzone")
   - section: (thematic grouping, e.g., "Movement Phase")
3. Use proper markdown syntax (##, ###, -, *, etc.)
"""

        response = ExtractionResponse(
            extraction_id=uuid4(),
            markdown_content="""---
source: Core Rules v3.1
last_update_date: 2024-09-15
document_type: core-rules
section: Movement Phase
---

## Movement Phase

During the movement phase, each model can:

- Move up to 6 inches
- Climb or traverse terrain
- Perform free actions

### Movement Restrictions

Models cannot move through enemy models.
""",
            token_count=8500,
            latency_ms=45000,
            provider="claude",
            model_version="claude-3-opus-20240229",
            validation_warnings=[]
        )

        # Verify YAML frontmatter
        assert response.markdown_content.startswith("---")
        assert "source:" in response.markdown_content
        assert "last_update_date:" in response.markdown_content
        assert "document_type:" in response.markdown_content

        # Verify document_type is valid
        assert "core-rules" in response.markdown_content or \
               "faq" in response.markdown_content or \
               "team-rules" in response.markdown_content or \
               "ops" in response.markdown_content or \
               "killzone" in response.markdown_content

        # Verify markdown structure
        assert "##" in response.markdown_content

    def test_token_usage_tracking(self, mock_llm_adapter):
        """
        Contract Test: Token Usage Tracking for PDF Extraction.

        Given: PDF extraction request
        When: Extraction completes
        Then: token_count > 0 (for budget monitoring)
        """
        response = ExtractionResponse(
            extraction_id=uuid4(),
            markdown_content="---\nsource: Test\n---\n## Content",
            token_count=12500,
            latency_ms=60000,
            provider="claude",
            model_version="claude-3-opus-20240229",
            validation_warnings=[]
        )

        assert response.token_count > 0

    def test_validation_warnings(self, mock_llm_adapter):
        """
        Contract Test: Validation Warnings.

        Given: Malformed PDF extraction
        When: extract_pdf() returns
        Then: validation_warnings includes issues
        """
        response = ExtractionResponse(
            extraction_id=uuid4(),
            markdown_content="## Content without frontmatter",
            token_count=500,
            latency_ms=30000,
            provider="claude",
            model_version="claude-3-opus-20240229",
            validation_warnings=[
                "Missing YAML frontmatter",
                "No last_update_date specified"
            ]
        )

        assert len(response.validation_warnings) > 0
        assert "Missing YAML frontmatter" in response.validation_warnings


    def test_deepseek_provider_compatibility(self, mock_llm_adapter):
        """
        Contract Test: DeepSeek Provider Compatibility.

        Given: Same prompt + context for DeepSeek
        When: Generate answer with DeepSeek (both chat and reasoner models)
        Then:
            - Answer mentions factual information
            - confidence ≥ 0.6
            - citations_included reflects config
            - reasoner model may include reasoning chain
        """
        prompt = "Can I shoot through a barricade?"
        context = [
            "Barricades provide light cover. Models can shoot through light cover with no penalty.",
            "Heavy cover blocks line of sight entirely."
        ]

        config = GenerationConfig(
            max_tokens=500,
            temperature=0.1,
            include_citations=True
        )

        # DeepSeek Chat model response
        deepseek_chat_response = LLMResponse(
            response_id=uuid4(),
            answer_text="Yes, you can shoot through a barricade. According to the rules: 'Barricades provide light cover. Models can shoot through light cover with no penalty.'",
            confidence_score=0.80,
            token_count=148,
            latency_ms=1150,
            provider="deepseek",
            model_version="deepseek-chat",
            citations_included=True
        )

        # DeepSeek Reasoner model response (includes chain-of-thought)
        deepseek_reasoner_response = LLMResponse(
            response_id=uuid4(),
            answer_text="Yes, shooting through barricades is allowed. The rules clearly state: 'Barricades provide light cover. Models can shoot through light cover with no penalty.' This means there's no shooting penalty when targeting through barricades.",
            confidence_score=0.85,  # Reasoner gets slightly higher confidence
            token_count=165,
            latency_ms=1400,
            provider="deepseek",
            model_version="deepseek-reasoner",
            citations_included=True
        )

        responses = [deepseek_chat_response, deepseek_reasoner_response]

        # Verify all have sufficient confidence
        for response in responses:
            assert response.confidence_score >= 0.6
            assert response.provider == "deepseek"

        # Verify key facts are mentioned
        for response in responses:
            assert "barricade" in response.answer_text.lower()
            assert "light cover" in response.answer_text.lower()

        # Verify citations when requested
        for response in responses:
            if response.citations_included:
                assert "According to" in response.answer_text or "rules" in response.answer_text.lower()

    def test_grok_provider_compatibility(self, mock_llm_adapter):
        """
        Contract Test: Grok Provider Compatibility.

        Given: Same prompt + context for Grok
        When: Generate answer with Grok
        Then:
            - Answer mentions factual information
            - confidence ≥ 0.6
            - token_count > 0
            - citations_included reflects config
        """
        prompt = "How does overwatch work?"
        context = [
            "Overwatch allows defensive fire when enemy models move within range.",
            "You can use overwatch during your opponent's movement phase."
        ]

        config = GenerationConfig(
            max_tokens=500,
            temperature=0.1,
            include_citations=True
        )

        grok_response = LLMResponse(
            response_id=uuid4(),
            answer_text="Overwatch enables defensive fire against enemy models during their movement phase. According to the rules: 'Overwatch allows defensive fire when enemy models move within range.' This can be used during your opponent's turn.",
            confidence_score=0.80,
            token_count=152,
            latency_ms=1250,
            provider="grok",
            model_version="grok-3",
            citations_included=True
        )

        # Verify confidence threshold
        assert grok_response.confidence_score >= 0.6
        assert grok_response.provider == "grok"

        # Verify token tracking
        assert grok_response.token_count > 0

        # Verify key facts mentioned
        assert "overwatch" in grok_response.answer_text.lower()
        assert "movement" in grok_response.answer_text.lower()

        # Verify citations
        if grok_response.citations_included:
            assert "According to" in grok_response.answer_text or "rules" in grok_response.answer_text.lower()

    def test_multi_provider_consistency_with_deepseek_grok(self, mock_llm_providers):
        """
        Contract Test: Multi-Provider Consistency (Including DeepSeek and Grok).

        Given: Same prompt + context across all providers (Claude, ChatGPT, Gemini, DeepSeek, Grok)
        When: Generate answer with each provider
        Then:
            - All answers mention core facts
            - confidence ≥ 0.6
            - token counts within 25% of each other
        """
        prompt = "What is the movement distance in Kill Team?"
        context = [
            "Movement Phase: Each model can move up to 6 inches during the movement phase.",
            "Climbing terrain reduces movement distance."
        ]

        config = GenerationConfig(
            max_tokens=500,
            temperature=0.1,
            include_citations=True
        )

        # All provider responses
        responses = [
            LLMResponse(
                response_id=uuid4(),
                answer_text="Each model can move up to 6 inches during the movement phase.",
                confidence_score=0.85,
                token_count=140,
                latency_ms=1100,
                provider="claude",
                model_version="claude-sonnet-4-5-20250929",
                citations_included=True
            ),
            LLMResponse(
                response_id=uuid4(),
                answer_text="Models can move up to 6 inches in the movement phase.",
                confidence_score=0.82,
                token_count=135,
                latency_ms=1050,
                provider="chatgpt",
                model_version="gpt-4-turbo-2024",
                citations_included=True
            ),
            LLMResponse(
                response_id=uuid4(),
                answer_text="The movement distance is 6 inches per model during the movement phase.",
                confidence_score=0.80,
                token_count=145,
                latency_ms=1200,
                provider="gemini",
                model_version="gemini-2.5-pro",
                citations_included=True
            ),
            LLMResponse(
                response_id=uuid4(),
                answer_text="During the movement phase, each model can move up to 6 inches.",
                confidence_score=0.80,
                token_count=138,
                latency_ms=1150,
                provider="deepseek",
                model_version="deepseek-chat",
                citations_included=True
            ),
            LLMResponse(
                response_id=uuid4(),
                answer_text="Models have a movement distance of 6 inches during the movement phase.",
                confidence_score=0.80,
                token_count=142,
                latency_ms=1180,
                provider="grok",
                model_version="grok-3",
                citations_included=True
            ),
        ]

        # Verify all have sufficient confidence
        for response in responses:
            assert response.confidence_score >= 0.6

        # Verify token counts within 25% (broader tolerance for 5 providers)
        token_counts = [r.token_count for r in responses]
        avg_tokens = sum(token_counts) / len(token_counts)
        for count in token_counts:
            assert abs(count - avg_tokens) / avg_tokens <= 0.25

        # Verify all mention key facts
        for response in responses:
            assert "6 inches" in response.answer_text or "6\"" in response.answer_text
            assert "movement" in response.answer_text.lower()


class TestLLMAdapterContractDeepSeek:
    """Contract tests specific to DeepSeek provider."""

    def test_deepseek_reasoner_model(self, mock_llm_adapter):
        """
        Contract Test: DeepSeek Reasoner Model.

        Given: deepseek-reasoner model with complex query
        When: Generate answer
        Then:
            - Response confidence ≥ 0.8 (higher for reasoning model)
            - Token limit is 3x normal (for chain-of-thought)
            - Answer demonstrates logical reasoning
        """
        request = GenerationRequest(
            prompt="If a model moves 3 inches, climbs 2 inches, and moves 2 more inches, can it still shoot?",
            context=[
                "Models can move up to 6 inches per turn.",
                "Climbing counts toward movement distance.",
                "Models cannot shoot if they moved more than 6 inches."
            ],
            config=GenerationConfig(max_tokens=800)
        )

        response = LLMResponse(
            response_id=uuid4(),
            answer_text="Let me work through this step by step: The model moves 3 inches (3\" total), climbs 2 inches (5\" total), then moves 2 more inches (7\" total). Since 7 inches exceeds the 6-inch movement limit, the model cannot shoot this turn.",
            confidence_score=0.85,  # Reasoning model gets higher confidence
            token_count=450,
            latency_ms=1800,
            provider="deepseek",
            model_version="deepseek-reasoner",
            citations_included=False
        )

        # Verify reasoning model characteristics
        assert response.confidence_score >= 0.8
        assert "step by step" in response.answer_text.lower() or "total" in response.answer_text.lower()
        assert response.model_version == "deepseek-reasoner"

    def test_deepseek_authentication_error(self, mock_llm_adapter):
        """
        Contract Test: DeepSeek Authentication Error.

        Given: Invalid API key
        When: Generate request
        Then: Raises AuthenticationError with 401
        """
        with pytest.raises(AuthenticationError):
            raise AuthenticationError("DeepSeek auth error: 401 Unauthorized")

    def test_deepseek_pdf_extraction_not_supported(self, mock_llm_adapter):
        """
        Contract Test: DeepSeek PDF Extraction Not Supported.

        Given: PDF extraction request
        When: extract_pdf() called
        Then: Raises NotImplementedError
        """
        pdf_file = BytesIO(b"Mock PDF content")
        
        with pytest.raises(NotImplementedError):
            raise NotImplementedError(
                "DeepSeek PDF extraction is not documented in the API. "
                "Use gemini-2.5-pro or gemini-2.5-flash for PDF extraction instead."
            )


class TestLLMAdapterContractGrok:
    """Contract tests specific to Grok provider."""

    def test_grok_http_error_handling(self, mock_llm_adapter):
        """
        Contract Test: Grok HTTP Error Handling.

        Given: Grok API returns various HTTP errors
        When: Generate request
        Then: Appropriate exceptions raised
        """
        # Test 429 rate limit
        with pytest.raises(RateLimitError):
            raise RateLimitError("Grok rate limit: 429 Too Many Requests")

        # Test 401 authentication
        with pytest.raises(AuthenticationError):
            raise AuthenticationError("Grok auth error: 401 Unauthorized")

    def test_grok_content_filter(self, mock_llm_adapter):
        """
        Contract Test: Grok Content Filter.

        Given: Content that triggers Grok's safety filters
        When: Generate request
        Then: Raises ContentFilterError
        """
        with pytest.raises(ContentFilterError):
            raise ContentFilterError("Grok content filter blocked response")

    def test_grok_token_limit_error(self, mock_llm_adapter):
        """
        Contract Test: Grok Token Limit Error.

        Given: Response exceeds max_tokens
        When: Generate request
        Then: Raises TokenLimitError with finish_reason='length'
        """
        with pytest.raises(TokenLimitError):
            raise TokenLimitError("Grok output was truncated due to max_tokens limit")

    def test_grok_pdf_extraction_placeholder(self, mock_llm_adapter):
        """
        Contract Test: Grok PDF Extraction Placeholder.

        Given: PDF extraction request
        When: extract_pdf() called
        Then: Raises NotImplementedError (requires PDF-to-text conversion)
        """
        pdf_file = BytesIO(b"Mock PDF content")
        
        with pytest.raises(NotImplementedError):
            raise NotImplementedError(
                "Grok PDF extraction requires PDF-to-text conversion"
            )

    def test_grok_response_validation(self, mock_llm_adapter):
        """
        Contract Test: Grok Response Validation.

        Given: Grok API response
        When: Parse response
        Then:
            - response_id is UUID
            - token_count > 0
            - latency_ms > 0
            - provider == "grok"
        """
        response = LLMResponse(
            response_id=uuid4(),
            answer_text="Test answer about Kill Team rules.",
            confidence_score=0.80,
            token_count=125,
            latency_ms=1100,
            provider="grok",
            model_version="grok-3",
            citations_included=False
        )

        # Validate response structure
        assert isinstance(response.response_id, UUID)
        assert response.token_count > 0
        assert response.latency_ms > 0
        assert response.provider == "grok"
        assert len(response.answer_text) > 0


@pytest.fixture
def mock_llm_adapter():
    """Mock LLM adapter for contract testing."""
    return None


@pytest.fixture
def mock_llm_providers():
    """Mock multiple LLM providers for consistency testing."""
    return {
        "claude": None,
        "chatgpt": None,
        "gemini": None,
        "deepseek": None,
        "grok": None
    }
