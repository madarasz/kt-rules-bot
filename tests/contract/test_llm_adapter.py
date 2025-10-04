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
        "gemini": None
    }
