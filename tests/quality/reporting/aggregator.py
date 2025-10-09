"""Aggregates quality test results for reporting."""

from collections import defaultdict
from typing import Dict, List
import numpy as np

from tests.quality.reporting.report_models import (
    QualityReport,
    TestCaseReport,
    ModelSummary,
    IndividualTestResult,
)


def aggregate_results(report: QualityReport) -> None:
    """
    Populates the report object with aggregated data.
    This function modifies the report object in-place.
    """
    per_test_case: Dict[str, List[IndividualTestResult]] = defaultdict(list)
    per_model: Dict[str, List[IndividualTestResult]] = defaultdict(list)

    for result in report.results:
        per_test_case[result.test_id].append(result)
        per_model[result.model].append(result)

    report.per_test_case_reports = {
        test_id: TestCaseReport(test_id=test_id, results=results)
        for test_id, results in per_test_case.items()
    }

    report.per_model_summaries = {
        model_name: ModelSummary(model_name=model_name, results=results)
        for model_name, results in per_model.items()
    }
