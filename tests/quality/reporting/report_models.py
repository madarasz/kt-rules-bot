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
    output_filename: str
    error: Optional[str] = None
    
    # Detailed cost breakdown
    multi_hop_cost_usd: float = 0.0
    ragas_cost_usd: float = 0.0
    embedding_cost_usd: float = 0.0
    json_formatted: bool = False  # True if response was valid JSON
    structured_quotes_count: int = 0  # Number of quotes in structured response
    
    # Ragas metrics (0-1 scale, or None if evaluation failed)
    quote_precision: Optional[float] = None
    quote_recall: Optional[float] = None
    quote_faithfulness: Optional[float] = None
    explanation_faithfulness: Optional[float] = None
    answer_correctness: Optional[float] = None
    ragas_error: Optional[str] = None
    
    # Ragas detailed feedback
    quote_precision_feedback: Optional[str] = None
    quote_recall_feedback: Optional[str] = None
    quote_faithfulness_feedback: Optional[str] = None
    explanation_faithfulness_feedback: Optional[str] = None
    answer_correctness_feedback: Optional[str] = None
    
    # Legacy support - optional for backward compatibility
    requirements: Optional[List[RequirementResult]] = None

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
    
    @property
    def ragas_metrics_available(self) -> bool:
        """Check if Ragas metrics are available."""
        return (
            self.quote_precision is not None 
            or self.quote_recall is not None
            or self.quote_faithfulness is not None
            or self.explanation_faithfulness is not None
            or self.answer_correctness is not None
        )
    
    @property
    def total_cost_usd(self) -> float:
        """Calculate total cost including all components."""
        return self.cost_usd + self.multi_hop_cost_usd + self.ragas_cost_usd + self.embedding_cost_usd

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
        return np.mean([r.total_cost_usd for r in self.results])

    @property
    def std_dev_cost(self) -> float:
        if len(self.results) < 2:
            return 0.0
        return np.std([r.total_cost_usd for r in self.results])

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
