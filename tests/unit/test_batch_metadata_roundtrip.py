"""Round-trip: batch flag + savings survive metadata serialize/parse."""

from uuid import uuid4

from src.services.llm.base import LLMResponse
from tests.quality.metadata_generator import MetadataFormatter, MetadataGenerator
from tests.quality.ragas_evaluator import RagasMetrics
from tests.quality.reporting.report_models import IndividualTestResult


def _llm_response():
    return LLMResponse(
        response_id=uuid4(),
        answer_text='{"smalltalk": false, "short_answer": "Yes.", "persona_short_answer": "",'
        ' "quotes": [], "explanation": "x", "persona_afterword": ""}',
        confidence_score=0.8,
        token_count=120,
        latency_ms=0,
        provider="claude",
        model_version="claude-sonnet-4-5-20250929",
        citations_included=True,
        prompt_tokens=100,
        completion_tokens=20,
    )


def _result():
    return IndividualTestResult(
        test_id="t1", query="q", model="claude-4.6-sonnet", score=0, max_score=0,
        passed=False, tokens=120, cost_usd=0.01, output_char_count=0,
        generation_time_seconds=1.0, output_filename="", batch_savings_usd=0.03,
        cache_savings_usd=0.05,
    )


def test_batch_metadata_roundtrips():
    meta = MetadataGenerator.generate_metadata(
        test_id="t1", model="claude-4.6-sonnet", run_num=1,
        llm_response=_llm_response(), result=_result(), metrics=RagasMetrics(),
        batch=True,
    )
    assert meta.batch is True
    assert meta.batch_savings_usd == 0.03
    assert meta.cache_savings_usd == 0.05

    block = MetadataFormatter.format_metadata_block(meta)
    parsed = MetadataFormatter.extract_metadata_from_markdown(f"# Query\n\nq\n\n---\n{block}")
    assert parsed.batch is True
    assert parsed.batch_savings_usd == 0.03
    assert parsed.cache_savings_usd == 0.05  # stacks with batch, both re-surfaced


def test_old_metadata_without_batch_defaults_false():
    # generate_metadata without batch kwarg (legacy call) -> defaults
    meta = MetadataGenerator.generate_metadata(
        test_id="t1", model="claude-4.6-sonnet", run_num=1,
        llm_response=_llm_response(), result=_result(), metrics=RagasMetrics(),
    )
    assert meta.batch is False
    assert meta.batch_savings_usd == 0.03  # still reads result.batch_savings_usd
