"""Data models for quality test reporting."""

from dataclasses import dataclass, field
from typing import List, Optional, Dict
import numpy as np

@dataclass
class RequirementResult:
    """Represents the result of a single requirement check."""
    title: str
    type: str
    achieved_score: int
    max_score: int
    description: str
    outcome: str

    @property
    def passed(self) -> bool:
        return self.achieved_score == self.max_score

    @property
    def emoji(self) -> str:
        if self.passed:
            return "✅"
        score_pct = self.achieved_score / self.max_score if self.max_score > 0 else 0
        if score_pct < 0.5:
            return "❌"
        return "⚠️"

@dataclass
class IndividualTestResult:
    """Represents the result of a single test run for a specific model and test case."""
    test_id: str
    query: str
    model: str
    score: int
    max_score: int
    passed: bool
    tokens: int
    cost_usd: float
    output_char_count: int
    generation_time_seconds: float
    requirements: List[RequirementResult]
    output_filename: str
    error: Optional[str] = None

    @property
    def score_percentage(self) -> float:
        return (self.score / self.max_score) * 100 if self.max_score > 0 else 0

    @property
    def status_emoji(self) -> str:
        if self.error:
            return "💀"
        if self.passed:
            return "✅"
        if self.score_percentage < 50:
            return "❌"
        return "⚠️"

@dataclass
class TestCaseReport:
    """Aggregates results for a single test case across multiple models and/or runs."""
    test_id: str
    results: List[IndividualTestResult] = field(default_factory=list)
    chart_path: Optional[str] = None

@dataclass
class ModelSummary:
    """Aggregates results for a single model across multiple test cases and/or runs."""
    model_name: str
    results: List[IndividualTestResult] = field(default_factory=list)

    @property
    def avg_score_pct(self) -> float:
        if not self.results:
            return 0.0
        return np.mean([r.score_percentage for r in self.results])

    @property
    def std_dev_score_pct(self) -> float:
        if len(self.results) < 2:
            return 0.0
        return np.std([r.score_percentage for r in self.results])

    @property
    def avg_time(self) -> float:
        if not self.results:
            return 0.0
        return np.mean([r.generation_time_seconds for r in self.results])

    @property
    def std_dev_time(self) -> float:
        if len(self.results) < 2:
            return 0.0
        return np.std([r.generation_time_seconds for r in self.results])

    @property
    def avg_cost(self) -> float:
        if not self.results:
            return 0.0
        return np.mean([r.cost_usd for r in self.results])

    @property
    def std_dev_cost(self) -> float:
        if len(self.results) < 2:
            return 0.0
        return np.std([r.cost_usd for r in self.results])

@dataclass
class QualityReport:
    """The main container for a full quality test report, covering all runs, tests, and models."""
    results: List[IndividualTestResult]
    total_time_seconds: float
    total_cost_usd: float
    runs: int
    models: List[str]
    test_cases: List[str]
    report_dir: str
    prompt_path: Optional[str] = None
    chart_path: Optional[str] = None
    
    # Populated by the aggregator
    per_test_case_reports: Dict[str, TestCaseReport] = field(default_factory=dict)
    per_model_summaries: Dict[str, ModelSummary] = field(default_factory=dict)

    @property
    def total_queries(self) -> int:
        return len(self.results)

    @property
    def is_multi_run(self) -> bool:
        return self.runs > 1

    @property
    def is_multi_model(self) -> bool:
        return len(self.models) > 1

    @property
    def is_multi_test_case(self) -> bool:
        return len(self.test_cases) > 1
