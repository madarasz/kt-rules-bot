"""Unit tests for custom judge Claude prompt-caching behavior."""

from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from src.services.llm.base import GenerationRequest, LLMResponse
from tests.quality.test_case_models import GroundTruthAnswer


def _make_judge_response(cache_read_tokens=0, cache_creation_tokens=0):
    return LLMResponse(
        response_id=uuid4(),
        answer_text="{}",
        confidence_score=0.9,
        token_count=150,
        latency_ms=300,
        provider="test",
        model_version="test-model",
        citations_included=False,
        prompt_tokens=120,
        completion_tokens=30,
        cache_read_tokens=cache_read_tokens,
        cache_creation_tokens=cache_creation_tokens,
        structured_output={
            "explanation_faithfulness": 0.9,
            "feedback": "Good answer.",
            "answer_correctness_details": [{"answer_key": "Final Answer", "score": 1.0}],
        },
    )


@pytest.mark.asyncio
@patch("tests.quality.custom_judge.LLMProviderFactory")
async def test_claude_judge_gets_list_prompt(mock_factory):
    """When judge uses ClaudeAdapter, evaluate() sends list[dict] blocks."""
    from src.services.llm.claude import ClaudeAdapter
    from tests.quality.custom_judge import CustomJudge

    # Template with a cache break marker in the static rubric section
    fake_template = (
        "Static rubric instructions here.<!--CACHE_BREAK-->\n"
        "Query: {query}\n"
        "Answers: {ground_truth_answers}\n"
        "Contexts: {ground_truth_contexts}\n"
        "Response: {llm_response_text}\n"
        "Quotes: {llm_quotes}\n"
    )

    claude_provider = ClaudeAdapter(api_key="test-key", model="claude-sonnet-4-5-20250929")
    captured = []

    async def capture(req):
        captured.append(req)
        return _make_judge_response()

    claude_provider.generate = capture
    mock_factory.create.return_value = claude_provider

    judge = CustomJudge(model="claude-sonnet-4-5-20250929")
    judge._provider = claude_provider

    with patch.object(judge, "_load_prompt_template", return_value=fake_template):
        await judge.evaluate(
            query="test query",
            llm_response_text='{"short_answer": "Yes"}',
            llm_quotes_structured=[],
            ground_truth_answers=[
                GroundTruthAnswer(key="Final Answer", text="Yes", priority="critical")
            ],
            ground_truth_contexts=["Rule text here"],
        )

    assert captured, "generate() was never called"
    req: GenerationRequest = captured[0]
    assert isinstance(req.prompt, list), "Claude judge should use list[dict] blocks"
    assert all(isinstance(b, dict) and b.get("type") == "text" for b in req.prompt)
    assert "cache_control" not in req.prompt[-1]
    assert req.prompt[0].get("cache_control") == {"type": "ephemeral"}


@pytest.mark.asyncio
@patch("tests.quality.custom_judge.LLMProviderFactory")
async def test_non_claude_judge_gets_str_prompt(mock_factory):
    """When judge uses a non-Claude provider, evaluate() sends plain str (no marker)."""
    from tests.quality.custom_judge import CustomJudge

    fake_template = (
        "Static rubric instructions here.<!--CACHE_BREAK-->\n"
        "Query: {query}\n"
        "Answers: {ground_truth_answers}\n"
        "Contexts: {ground_truth_contexts}\n"
        "Response: {llm_response_text}\n"
        "Quotes: {llm_quotes}\n"
    )

    captured = []

    async def capture(req):
        captured.append(req)
        return _make_judge_response()

    mock_provider = Mock()
    mock_provider.generate = capture
    mock_factory.create.return_value = mock_provider

    judge = CustomJudge(model="gpt-4o")
    judge._provider = mock_provider

    with patch.object(judge, "_load_prompt_template", return_value=fake_template):
        await judge.evaluate(
            query="test query",
            llm_response_text='{"short_answer": "Yes"}',
            llm_quotes_structured=[],
            ground_truth_answers=[
                GroundTruthAnswer(key="Final Answer", text="Yes", priority="critical")
            ],
            ground_truth_contexts=["Rule text here"],
        )

    assert captured, "generate() was never called"
    req: GenerationRequest = captured[0]
    assert isinstance(req.prompt, str), "Non-Claude judge should use plain str"
    assert "<!--CACHE_BREAK-->" not in req.prompt


@pytest.mark.asyncio
@patch("tests.quality.custom_judge.LLMProviderFactory")
async def test_judge_result_propagates_cache_tokens(mock_factory):
    """evaluate() must surface prompt-cache token counts so cost/savings can use them."""
    from tests.quality.custom_judge import CustomJudge

    fake_template = (
        "Static rubric instructions here.<!--CACHE_BREAK-->\n"
        "Query: {query}\n"
        "Answers: {ground_truth_answers}\n"
        "Contexts: {ground_truth_contexts}\n"
        "Response: {llm_response_text}\n"
        "Quotes: {llm_quotes}\n"
    )

    async def capture(_req):
        return _make_judge_response(cache_read_tokens=900, cache_creation_tokens=100)

    mock_provider = Mock()
    mock_provider.generate = capture
    mock_factory.create.return_value = mock_provider

    judge = CustomJudge(model="gpt-4o")
    judge._provider = mock_provider

    with patch.object(judge, "_load_prompt_template", return_value=fake_template):
        result = await judge.evaluate(
            query="test query",
            llm_response_text='{"short_answer": "Yes"}',
            llm_quotes_structured=[],
            ground_truth_answers=[
                GroundTruthAnswer(key="Final Answer", text="Yes", priority="critical")
            ],
            ground_truth_contexts=["Rule text here"],
        )

    assert result.error is None
    assert result.cache_read_tokens == 900
    assert result.cache_creation_tokens == 100
