"""Chart 3-way score breakdown (green/gold/grey) and the report.md error log."""

import pytest

from tests.quality.reporting.chart_generator import ChartGenerator
from tests.quality.reporting.report_generator import ReportGenerator
from tests.quality.reporting.report_models import IndividualTestResult, QualityReport


def _result(run, score, *, error=None, ragas_eval_error=False, recovered=False,
            attempts=0, error_class=None, max_score=100):
    return IndividualTestResult(
        test_id="t1",
        query="q?",
        model="m",
        run_num=run,
        score=score,
        max_score=max_score,
        passed=score >= 80,
        tokens=0,
        cost_usd=0.0,
        output_char_count=0,
        generation_time_seconds=0.0,
        output_filename="f",
        error=error,
        ragas_evaluation_error=ragas_eval_error,
        recovered_from_error=recovered,
        recovery_attempts=attempts,
        error_class=error_class,
    )


def _report(results):
    return QualityReport(
        results=results,
        total_time_seconds=0.0,
        total_cost_usd=0.0,
        runs=len(results),
        models=["m"],
        test_cases=["t1"],
        report_dir="/tmp/x",
        judge_model="j",
    )


def test_score_breakdown_three_way():
    # run1 clean 90; run2 recovered 80 (no residual error); run3 permanent error 0.
    results = [
        _result(1, 90),
        _result(2, 80, recovered=True, attempts=1),
        _result(3, 0, error="invalid_request", error_class="permanent"),
    ]
    earned, recovered, error = ChartGenerator(_report(results))._calculate_score_breakdown(["m"])

    total_max = 300
    assert earned[0] == pytest.approx(90 / total_max * 100)  # non-recovered scores
    assert recovered[0] == pytest.approx(80 / total_max * 100)  # gold
    assert error[0] == pytest.approx(100 / total_max * 100)  # lost on run3

    # green + gold equals the old "total earned" (sum of all scores); grey unchanged.
    assert earned[0] + recovered[0] == pytest.approx((90 + 80) / total_max * 100)
    # full stack height never exceeds 100%.
    assert earned[0] + recovered[0] + error[0] <= 100 + 1e-9


def test_score_breakdown_double_fault():
    # Generation recovered but judge permanently errored: earned portion -> gold,
    # lost portion -> grey, total height preserved.
    results = [_result(1, 40, recovered=True, attempts=1, ragas_eval_error=True)]
    earned, recovered, error = ChartGenerator(_report(results))._calculate_score_breakdown(["m"])
    assert earned[0] == pytest.approx(0.0)
    assert recovered[0] == pytest.approx(40.0)
    assert error[0] == pytest.approx(60.0)
    assert earned[0] + recovered[0] + error[0] == pytest.approx(100.0)


def test_score_breakdown_no_errors_all_green():
    results = [_result(1, 90), _result(2, 100)]
    earned, recovered, error = ChartGenerator(_report(results))._calculate_score_breakdown(["m"])
    assert recovered[0] == 0.0
    assert error[0] == 0.0
    assert earned[0] == pytest.approx((90 + 100) / 200 * 100)


def test_error_recovery_log_renders_with_counts():
    results = [
        _result(1, 90),  # clean — not in log
        _result(2, 80, recovered=True, attempts=1, error_class="transient"),
        _result(3, 0, error="401 authentication failed", error_class="permanent"),
    ]
    log = ReportGenerator(_report(results))._get_error_recovery_log()

    assert "## Error & Recovery Log" in log
    assert "1 recovered by re-request, 1 unrecoverable" in log
    # recovered run shows a ✅ and its attempt count; permanent shows the message
    assert "recovered after re-request" in log
    assert "401 authentication failed" in log
    assert "permanent" in log and "transient" in log
    # the clean run is not listed
    assert log.count("| t1 |") == 2


def test_error_recovery_log_empty_when_clean():
    results = [_result(1, 90), _result(2, 100)]
    assert ReportGenerator(_report(results))._get_error_recovery_log() == ""


def test_error_log_message_escapes_pipes():
    results = [_result(1, 0, error="bad | pipe\nnewline", error_class="permanent")]
    log = ReportGenerator(_report(results))._get_error_recovery_log()
    assert "bad \\| pipe newline" in log


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
