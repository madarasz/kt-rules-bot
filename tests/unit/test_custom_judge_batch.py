"""Judge request-building + result-parsing are reusable for the batch path."""

from uuid import uuid4

from src.services.llm.base import LLMResponse
from tests.quality.custom_judge import CustomJudge
from tests.quality.test_case_models import GroundTruthAnswer


def _gta():
    return [GroundTruthAnswer(key="Final Answer", text="Yes.", priority="critical")]


def test_build_judge_request_uses_custom_judge_schema():
    # Non-Claude judge model -> plain-string prompt, custom_judge schema.
    judge = CustomJudge(model="gpt-4.1-mini")
    req = judge.build_judge_request(
        query="q",
        llm_response_text='{"short_answer": "Yes."}',
        llm_quotes_structured=[],
        ground_truth_answers=_gta(),
        ground_truth_contexts=["ctx"],
    )
    assert req.config.structured_output_schema == "custom_judge"
    assert isinstance(req.prompt, str)
    assert req.context == []


def test_parse_result_extracts_scores():
    judge = CustomJudge(model="gpt-4.1-mini")
    response = LLMResponse(
        response_id=uuid4(),
        answer_text="{}",
        confidence_score=0.8,
        token_count=120,
        latency_ms=0,
        provider="chatgpt",
        model_version="gpt-4.1",
        citations_included=False,
        prompt_tokens=100,
        completion_tokens=20,
        structured_output={
            "explanation_faithfulness": 0.9,
            "feedback": "good",
            "answer_correctness_details": [{"answer_key": "Final Answer", "score": 1.0}],
        },
    )
    result = judge.parse_result(response, _gta())
    assert result.explanation_faithfulness == 0.9
    assert result.answer_correctness == 1.0
    assert result.answer_correctness_details == {"Final Answer": 1.0}
    assert result.prompt_tokens == 100
