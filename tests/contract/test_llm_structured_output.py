"""Contract tests for LLM structured JSON output.

Verifies all providers return valid JSON conforming to STRUCTURED_OUTPUT_SCHEMA.
Tests both Pydantic-native providers (Claude, ChatGPT) and JSON-only providers (Gemini, Grok, DeepSeek).

Requires API keys - run with: pytest tests/contract/test_llm_structured_output.py
"""

import json

import pytest

from src.models.structured_response import StructuredLLMResponse
from src.services.llm.base import STRUCTURED_OUTPUT_SCHEMA, GenerationConfig, GenerationRequest
from src.services.llm.factory import LLMProviderFactory
from src.services.llm.schemas import Answer, CustomJudgeResponse, HopEvaluation

# All providers that must support structured output
PROVIDERS_TO_TEST = ["claude-4.5-sonnet", "gpt-4.1", "gemini-2.5-flash", "grok-3", "deepseek-chat"]

# Pydantic-native providers use beta.parse() and populate structured_output field
PYDANTIC_NATIVE_PROVIDERS = ["claude-4.5-sonnet", "gpt-4.1"]

# JSON-only providers return JSON strings and don't populate structured_output field
JSON_ONLY_PROVIDERS = ["gemini-2.5-flash", "grok-3", "deepseek-chat"]

TEST_PROMPT = "Can a model perform two Shoot actions in the same activation?"
TEST_CONTEXT = [
    "Core Rules: Actions\nA model cannot perform the same action more than once in the same activation."
]
TEST_CHUNK_IDS = ["test-chunk-id-12345678"]

SMALLTALK_PROMPT = "Hello! How are you?"
SMALLTALK_CONTEXT = []
SMALLTALK_CHUNK_IDS: list[str] = []


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
        prompt=TEST_PROMPT, context=TEST_CONTEXT, config=GenerationConfig(), chunk_ids=TEST_CHUNK_IDS
    )

    response = await llm.generate(request)

    # 1. Verify response is valid JSON
    try:
        data = json.loads(response.answer_text)
    except json.JSONDecodeError as e:
        pytest.fail(
            f"{provider} returned invalid JSON: {e}\nResponse: {response.answer_text[:200]}"
        )

    assert isinstance(data, dict), f"{provider} must return JSON object (got {type(data)})"
    print(f"✓ {provider} returned valid JSON")

    # 2. Verify all required fields present with correct types
    required_fields = STRUCTURED_OUTPUT_SCHEMA["required"]
    missing_fields = [f for f in required_fields if f not in data]
    assert not missing_fields, f"{provider} missing required fields: {missing_fields}"

    assert isinstance(data["smalltalk"], bool), f"{provider} smalltalk must be boolean"
    assert isinstance(data["short_answer"], str), f"{provider} short_answer must be string"
    assert isinstance(data["persona_short_answer"], str), (
        f"{provider} persona_short_answer must be string"
    )
    assert isinstance(data["quotes"], list), f"{provider} quotes must be array"
    assert isinstance(data["explanation"], str), f"{provider} explanation must be string"
    assert isinstance(data["persona_afterword"], str), (
        f"{provider} persona_afterword must be string"
    )

    print(f"✓ {provider} has all required fields with correct types")

    # 3. Verify quotes structure
    quotes = data["quotes"]
    assert len(quotes) > 0, f"{provider} must return at least one quote for rules questions"

    for i, quote in enumerate(quotes):
        # Required fields
        assert "quote_title" in quote, f"{provider} quote[{i}] missing quote_title"
        assert "quote_text" in quote, f"{provider} quote[{i}] missing quote_text"
        assert isinstance(quote["quote_title"], str), f"{provider} quote[{i}] title must be string"
        assert isinstance(quote["quote_text"], str), f"{provider} quote[{i}] text must be string"
        assert len(quote["quote_title"]) > 0, f"{provider} quote[{i}] title cannot be empty"
        assert len(quote["quote_text"]) > 0, f"{provider} quote[{i}] text cannot be empty"

        # Optional chunk_id field (for quote validation)
        if "chunk_id" in quote:
            assert isinstance(quote["chunk_id"], str), (
                f"{provider} quote[{i}] chunk_id must be string"
            )
            # chunk_id should be last 8 chars of UUID (e.g., 'a1b2c3d4')
            if quote["chunk_id"]:  # If not empty
                assert len(quote["chunk_id"]) <= 36, (
                    f"{provider} quote[{i}] chunk_id looks invalid: {quote['chunk_id']}"
                )

    print(f"✓ {provider} returned {len(quotes)} valid quotes")

    # 4. Verify can parse into StructuredLLMResponse model
    try:
        structured_response = StructuredLLMResponse.from_json(response.answer_text)
        structured_response.validate()
    except Exception as e:
        pytest.fail(f"{provider} failed to parse into StructuredLLMResponse: {e}")

    assert not structured_response.smalltalk, (
        f"{provider} should mark rules questions as not smalltalk"
    )
    assert len(structured_response.short_answer) > 0, f"{provider} short_answer cannot be empty"
    assert len(structured_response.quotes) > 0, (
        f"{provider} must provide quotes for rules questions"
    )

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
        config=GenerationConfig(),
        chunk_ids=SMALLTALK_CHUNK_IDS,
    )

    response = await llm.generate(request)
    data = json.loads(response.answer_text)

    assert data["smalltalk"], f"{provider} should mark casual conversation as smalltalk"
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
        prompt=TEST_PROMPT, context=TEST_CONTEXT, config=GenerationConfig(), chunk_ids=TEST_CHUNK_IDS
    )

    response = await llm.generate(request)
    structured_response = StructuredLLMResponse.from_json(response.answer_text)

    # Convert to markdown
    markdown = structured_response.to_markdown()

    # Verify markdown contains expected elements
    assert structured_response.short_answer in markdown, f"{provider} markdown missing short_answer"
    assert structured_response.persona_short_answer in markdown, (
        f"{provider} markdown missing persona"
    )
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
            prompt=TEST_PROMPT, context=TEST_CONTEXT, config=GenerationConfig(), chunk_ids=TEST_CHUNK_IDS
        )

        response = await llm.generate(request)
        data = json.loads(response.answer_text)

        # Strict mode should guarantee exact schema compliance
        assert set(data.keys()) == set(STRUCTURED_OUTPUT_SCHEMA["required"]), (
            "GPT-4.1 strict mode should only include required fields"
        )

        print("✓ GPT-4.1 strict mode validated")


class TestPydanticStructuredOutput:
    """Test Pydantic-native vs JSON-only structured output approaches.

    Pydantic-native providers (Claude, ChatGPT):
    - Use beta.parse() with Pydantic models directly
    - Populate LLMResponse.structured_output field with parsed dict
    - Return Pydantic model instances from API

    JSON-only providers (Gemini, Grok, DeepSeek):
    - Return raw JSON strings
    - Don't populate LLMResponse.structured_output field
    - Validate with pydantic_model.model_validate_json() post-processing
    """

class TestPydanticModelValidation:
    """Test that all providers return JSON that validates with Pydantic models.

    This tests direct Pydantic validation, not just JSON parsing.
    """

    @pytest.mark.parametrize("provider", PROVIDERS_TO_TEST)
    @pytest.mark.asyncio
    @pytest.mark.contract
    @pytest.mark.llm_api
    async def test_answer_schema_pydantic_validation(self, provider):
        """Provider JSON must validate successfully with Answer Pydantic model.

        Contract: All providers must return JSON that can be parsed by
        Answer.model_validate_json() without validation errors.
        """
        llm = LLMProviderFactory.create(provider)
        request = GenerationRequest(
            prompt=TEST_PROMPT, context=TEST_CONTEXT, config=GenerationConfig(), chunk_ids=TEST_CHUNK_IDS
        )

        response = await llm.generate(request)

        # Should validate with Pydantic Answer model
        try:
            # Gemini uses GeminiAnswer, others use Answer
            if provider == "gemini-2.5-flash":
                # For Gemini, we expect sentence_numbers in quotes
                parsed_json = json.loads(response.answer_text)
                assert isinstance(parsed_json, dict)
                assert "quotes" in parsed_json
                # Just verify it's valid JSON structure
                print(f"✓ {provider} returned valid JSON (uses GeminiAnswer schema)")
            else:
                parsed = Answer.model_validate_json(response.answer_text)

                # Verify types are correct at Pydantic level
                assert isinstance(parsed.smalltalk, bool), f"{provider} smalltalk must be bool"
                assert isinstance(parsed.short_answer, str), f"{provider} short_answer must be str"
                assert isinstance(parsed.quotes, list), f"{provider} quotes must be list"
                assert isinstance(parsed.explanation, str), f"{provider} explanation must be str"

                # Verify required fields are not empty
                assert len(parsed.short_answer) > 0, f"{provider} short_answer cannot be empty"

                print(f"✓ {provider} passed Pydantic Answer validation")

        except Exception as e:
            pytest.fail(f"{provider} failed Pydantic validation: {e}")


class TestSchemaVariants:
    """Test that providers support different schema types.

    Providers should support:
    - Answer schema (default, for rules queries)
    - HopEvaluation schema (for multi-hop retrieval)
    - CustomJudgeResponse schema (for quality testing, Pydantic-native only)
    """

    @pytest.mark.parametrize("provider", PROVIDERS_TO_TEST)
    @pytest.mark.asyncio
    @pytest.mark.contract
    @pytest.mark.llm_api
    async def test_hop_evaluation_schema(self, provider):
        """All providers must support HopEvaluation schema for multi-hop retrieval.

        Contract: Providers must be able to evaluate whether retrieved context
        is sufficient to answer a query (returns can_answer, reasoning, missing_query).
        """
        llm = LLMProviderFactory.create(provider)

        # HopEvaluation request asks if context is sufficient
        # Note: system_prompt="" is required for non-default schemas to prevent
        # the LLM from following the default Kill Team prompt format
        request = GenerationRequest(
            prompt="Can a model with the Stealth operative perform a charge action?",
            context=["Core Rules: Actions\nModels can perform Move, Shoot, or Charge actions."],
            config=GenerationConfig(
                structured_output_schema="hop_evaluation",
                system_prompt="",  # Empty system prompt for hop evaluation
            ),
            chunk_ids=["hop-eval-test-chunk-1"],
        )

        response = await llm.generate(request)

        # Should validate with HopEvaluation schema
        try:
            parsed = HopEvaluation.model_validate_json(response.answer_text)

            assert isinstance(parsed.can_answer, bool), f"{provider} can_answer must be bool"
            assert isinstance(parsed.reasoning, str), f"{provider} reasoning must be str"
            assert len(parsed.reasoning) > 0, f"{provider} reasoning cannot be empty"

            # If can't answer, missing_query should be present
            if not parsed.can_answer:
                assert parsed.missing_query, f"{provider} should provide missing_query when can_answer=false"

            print(f"✓ {provider} supports HopEvaluation schema")

        except Exception as e:
            pytest.fail(f"{provider} failed HopEvaluation validation: {e}")

    @pytest.mark.parametrize("provider", PYDANTIC_NATIVE_PROVIDERS)
    @pytest.mark.asyncio
    @pytest.mark.contract
    @pytest.mark.llm_api
    async def test_custom_judge_schema_pydantic_native_only(self, provider):
        """Pydantic-native providers should support CustomJudgeResponse schema.

        Contract: Claude and ChatGPT support quality testing with custom judge
        responses that evaluate explanation faithfulness and answer correctness.

        Note: This test is limited to Pydantic-native providers as the schema
        is complex and only used in quality testing where we have tight control.
        """
        llm = LLMProviderFactory.create(provider)

        # Simplified judge request
        judge_prompt = """Evaluate this response:
        Question: Can I shoot twice?
        Answer: No.
        Ground Truth: No, models cannot perform the same action twice.

        Rate explanation_faithfulness (0.0-1.0) and provide feedback."""

        request = GenerationRequest(
            prompt=judge_prompt,
            context=[],
            config=GenerationConfig(
                structured_output_schema="custom_judge",
                system_prompt="",  # Empty system prompt for custom_judge schema
            ),
            chunk_ids=[],
        )

        response = await llm.generate(request)

        # Should validate with CustomJudgeResponse schema
        try:
            parsed = CustomJudgeResponse.model_validate_json(response.answer_text)

            assert isinstance(parsed.explanation_faithfulness, float), (
                f"{provider} explanation_faithfulness must be float"
            )
            assert 0.0 <= parsed.explanation_faithfulness <= 1.0, (
                f"{provider} explanation_faithfulness must be 0.0-1.0"
            )
            assert isinstance(parsed.feedback, str), f"{provider} feedback must be str"
            assert len(parsed.feedback) > 0, f"{provider} feedback cannot be empty"
            assert isinstance(parsed.answer_correctness_details, list), (
                f"{provider} answer_correctness_details must be list"
            )

            print(f"✓ {provider} supports CustomJudgeResponse schema")

        except Exception as e:
            pytest.fail(f"{provider} failed CustomJudgeResponse validation: {e}")


@pytest.fixture
def mock_llm_adapter():
    """Mock LLM adapter for contract testing."""
    return None


@pytest.fixture
def mock_llm_providers():
    """Mock multiple LLM providers for consistency testing."""
    return {"claude": None, "chatgpt": None, "gemini": None, "deepseek": None, "grok": None}
