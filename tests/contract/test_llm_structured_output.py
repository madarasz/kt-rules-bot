"""Contract tests for LLM structured JSON output.

Verifies all providers return valid JSON conforming to STRUCTURED_OUTPUT_SCHEMA.
Requires API keys - run with: pytest tests/contract/test_llm_structured_output.py
"""

import json
import pytest

from src.services.llm.factory import LLMProviderFactory
from src.services.llm.base import GenerationRequest, GenerationConfig, STRUCTURED_OUTPUT_SCHEMA
from src.models.structured_response import StructuredLLMResponse


# All providers that must support structured output
PROVIDERS_TO_TEST = [
    "claude-4.5-sonnet",
    "gpt-4.1",
    "gemini-2.5-flash",
    "grok-3",
    "deepseek-chat"
]

TEST_PROMPT = "Can a model perform two Shoot actions in the same activation?"
TEST_CONTEXT = [
    "Core Rules: Actions\nA model cannot perform the same action more than once in the same activation."
]

SMALLTALK_PROMPT = "Hello! How are you?"
SMALLTALK_CONTEXT = []


@pytest.mark.parametrize("provider", PROVIDERS_TO_TEST)
@pytest.mark.asyncio
@pytest.mark.contract
@pytest.mark.llm_api
async def test_provider_structured_output_compliance(provider):
    """Test provider returns valid structured JSON with all required fields.

    Combined test that validates:
    1. Valid JSON format
    2. All required schema fields present with correct types
    3. Quotes have correct structure
    4. Can be parsed into StructuredLLMResponse model

    Contract: All providers must return valid JSON conforming to STRUCTURED_OUTPUT_SCHEMA.
    """
    llm = LLMProviderFactory.create(provider)

    request = GenerationRequest(
        prompt=TEST_PROMPT,
        context=TEST_CONTEXT,
        config=GenerationConfig()
    )

    response = await llm.generate(request)

    # 1. Verify response is valid JSON
    try:
        data = json.loads(response.answer_text)
    except json.JSONDecodeError as e:
        pytest.fail(f"{provider} returned invalid JSON: {e}\nResponse: {response.answer_text[:200]}")

    assert isinstance(data, dict), f"{provider} must return JSON object (got {type(data)})"
    print(f"✓ {provider} returned valid JSON")

    # 2. Verify all required fields present with correct types
    required_fields = STRUCTURED_OUTPUT_SCHEMA["required"]
    missing_fields = [f for f in required_fields if f not in data]
    assert not missing_fields, f"{provider} missing required fields: {missing_fields}"

    assert isinstance(data["smalltalk"], bool), f"{provider} smalltalk must be boolean"
    assert isinstance(data["short_answer"], str), f"{provider} short_answer must be string"
    assert isinstance(data["persona_short_answer"], str), f"{provider} persona_short_answer must be string"
    assert isinstance(data["quotes"], list), f"{provider} quotes must be array"
    assert isinstance(data["explanation"], str), f"{provider} explanation must be string"
    assert isinstance(data["persona_afterword"], str), f"{provider} persona_afterword must be string"

    print(f"✓ {provider} has all required fields with correct types")

    # 3. Verify quotes structure
    quotes = data["quotes"]
    assert len(quotes) > 0, f"{provider} must return at least one quote for rules questions"

    for i, quote in enumerate(quotes):
        assert "quote_title" in quote, f"{provider} quote[{i}] missing quote_title"
        assert "quote_text" in quote, f"{provider} quote[{i}] missing quote_text"
        assert isinstance(quote["quote_title"], str), f"{provider} quote[{i}] title must be string"
        assert isinstance(quote["quote_text"], str), f"{provider} quote[{i}] text must be string"
        assert len(quote["quote_title"]) > 0, f"{provider} quote[{i}] title cannot be empty"
        assert len(quote["quote_text"]) > 0, f"{provider} quote[{i}] text cannot be empty"

    print(f"✓ {provider} returned {len(quotes)} valid quotes")

    # 4. Verify can parse into StructuredLLMResponse model
    try:
        structured_response = StructuredLLMResponse.from_json(response.answer_text)
        structured_response.validate()
    except Exception as e:
        pytest.fail(f"{provider} failed to parse into StructuredLLMResponse: {e}")

    assert structured_response.smalltalk == False, f"{provider} should mark rules questions as not smalltalk"
    assert len(structured_response.short_answer) > 0, f"{provider} short_answer cannot be empty"
    assert len(structured_response.quotes) > 0, f"{provider} must provide quotes for rules questions"

    print(f"✓ {provider} response successfully parsed to StructuredLLMResponse")


@pytest.mark.parametrize("provider", ["gpt-4.1"])
@pytest.mark.asyncio
@pytest.mark.contract
@pytest.mark.llm_api
async def test_provider_smalltalk_flag(provider):
    """Test provider correctly sets smalltalk flag.

    Contract: smalltalk should be true for casual conversation, false for rules.
    """
    llm = LLMProviderFactory.create(provider)

    # Test with smalltalk
    request = GenerationRequest(
        prompt=SMALLTALK_PROMPT,
        context=SMALLTALK_CONTEXT,
        config=GenerationConfig()
    )

    response = await llm.generate(request)
    data = json.loads(response.answer_text)

    assert data["smalltalk"] == True, f"{provider} should mark casual conversation as smalltalk"
    # Smalltalk can have empty quotes
    assert isinstance(data["quotes"], list), f"{provider} quotes must be array even for smalltalk"

    print(f"✓ {provider} correctly identified smalltalk")


@pytest.mark.parametrize("provider", ["gpt-4.1"])
@pytest.mark.asyncio
@pytest.mark.contract
@pytest.mark.llm_api
async def test_provider_markdown_conversion(provider):
    """Test provider response converts to markdown correctly.

    Contract: StructuredLLMResponse.to_markdown() should work for all providers.
    """
    llm = LLMProviderFactory.create(provider)

    request = GenerationRequest(
        prompt=TEST_PROMPT,
        context=TEST_CONTEXT,
        config=GenerationConfig()
    )

    response = await llm.generate(request)
    structured_response = StructuredLLMResponse.from_json(response.answer_text)

    # Convert to markdown
    markdown = structured_response.to_markdown()

    # Verify markdown contains expected elements
    assert structured_response.short_answer in markdown, f"{provider} markdown missing short_answer"
    assert structured_response.persona_short_answer in markdown, f"{provider} markdown missing persona"
    assert "## Explanation" in markdown, f"{provider} markdown missing explanation header"
    assert structured_response.explanation in markdown, f"{provider} markdown missing explanation"

    print(f"✓ {provider} successfully converted to markdown")


class TestProviderSpecificEdgeCases:
    """Provider-specific edge case tests."""

    @pytest.mark.asyncio
    @pytest.mark.contract
    @pytest.mark.llm_api
    async def test_gpt_4_1_strict_mode(self):
        """Test GPT-4.1 uses strict mode for schema enforcement."""
        llm = LLMProviderFactory.create("gpt-4.1")

        request = GenerationRequest(
            prompt=TEST_PROMPT,
            context=TEST_CONTEXT,
            config=GenerationConfig()
        )

        response = await llm.generate(request)
        data = json.loads(response.answer_text)

        # Strict mode should guarantee exact schema compliance
        assert set(data.keys()) == set(STRUCTURED_OUTPUT_SCHEMA["required"]), \
            "GPT-4.1 strict mode should only include required fields"

        print("✓ GPT-4.1 strict mode validated")

    @pytest.mark.asyncio
    @pytest.mark.contract
    @pytest.mark.llm_api
    async def test_deepseek_chat_vs_reasoner(self):
        """Test both DeepSeek models support structured output."""
        for model in ["deepseek-chat"]:  # deepseek-reasoner can be added when available
            llm = LLMProviderFactory.create(model)

            request = GenerationRequest(
                prompt=TEST_PROMPT,
                context=TEST_CONTEXT,
                config=GenerationConfig()
            )

            response = await llm.generate(request)

            # Should return valid JSON
            try:
                data = json.loads(response.answer_text)
                assert "short_answer" in data
                print(f"✓ {model} returned structured output")
            except json.JSONDecodeError:
                pytest.fail(f"{model} did not return valid JSON")


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
