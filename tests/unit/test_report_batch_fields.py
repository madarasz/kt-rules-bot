"""Tests for batch-savings fields on report models."""

from tests.quality.reporting.report_models import IndividualTestResult, ModelSummary


def _result(**kw):
    base = dict(
        test_id="t",
        query="q",
        model="m",
        score=80,
        max_score=100,
        passed=True,
        tokens=10,
        cost_usd=0.01,
        output_char_count=1,
        generation_time_seconds=1.0,
        output_filename="f",
    )
    base.update(kw)
    return IndividualTestResult(**base)


def test_batch_savings_defaults_and_aggregate():
    r = _result(batch_savings_usd=0.02)
    assert r.batch_savings_usd == 0.02 and r.judge_batch_savings_usd == 0.0
    assert ModelSummary("m", [r]).avg_batch_savings == 0.02


def test_avg_batch_savings_empty():
    assert ModelSummary("m", []).avg_batch_savings == 0.0
