"""Data models for quality test reporting."""

from dataclasses import dataclass, field

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
    error: str | None = None

    # Detailed cost breakdown
    multi_hop_cost_usd: float = 0.0
    ragas_cost_usd: float = 0.0
    embedding_cost_usd: float = 0.0
    json_formatted: bool = False  # True if response was valid JSON
    structured_quotes_count: int = 0  # Number of quotes in structured response

    # Ragas metrics (0-1 scale, or None if evaluation failed)
    quote_precision: float | None = None
    quote_recall: float | None = None
    quote_faithfulness: float | None = None
    explanation_faithfulness: float | None = None
    answer_correctness: float | None = None
    ragas_error: str | None = None

    # Ragas detailed feedback
    quote_precision_feedback: str | None = None
    quote_recall_feedback: str | None = None
    quote_faithfulness_feedback: str | None = None
    explanation_faithfulness_feedback: str | None = None
    answer_correctness_feedback: str | None = None
    feedback: str | None = None

    # Ragas evaluation error tracking (for grey bar visualization)
    ragas_evaluation_error: bool = False

    # Detailed per-quote/answer breakdowns from custom judge
    quote_faithfulness_details: dict[str, float] | None = None  # chunk_id -> score
    answer_correctness_details: dict[str, float] | None = None  # answer_key -> score
    llm_quotes_structured: list[dict] | None = None  # List of {chunk_id, quote_title, quote_text}

    # Legacy support - optional for backward compatibility
    requirements: list[RequirementResult] | None = None

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
        return (
            self.cost_usd + self.multi_hop_cost_usd + self.ragas_cost_usd + self.embedding_cost_usd
        )


@dataclass
class TestCaseReport:
    """Aggregates results for a single test case across multiple models and/or runs."""

    test_id: str
    results: list[IndividualTestResult] = field(default_factory=list)
    chart_path: str | None = None


@dataclass
class ModelSummary:
    """Aggregates results for a single model across multiple test cases and/or runs."""

    model_name: str
    results: list[IndividualTestResult] = field(default_factory=list)

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
        """Average production cost per test (excludes evaluation infrastructure costs like judge, embeddings)."""
        if not self.results:
            return 0.0
        return np.mean([r.cost_usd for r in self.results])

    @property
    def std_dev_cost(self) -> float:
        """Standard deviation of production cost (excludes evaluation infrastructure costs)."""
        if len(self.results) < 2:
            return 0.0
        return np.std([r.cost_usd for r in self.results])

    @property
    def avg_multi_hop(self) -> float:
        """Average multi-hop evaluation cost per test."""
        if not self.results:
            return 0.0
        return np.mean([r.multi_hop_cost_usd for r in self.results])

    @property
    def avg_judge(self) -> float:
        """Average judge evaluation cost per test."""
        if not self.results:
            return 0.0
        return np.mean([r.ragas_cost_usd for r in self.results])

    @property
    def avg_embedding(self) -> float:
        """Average embedding cost per test."""
        if not self.results:
            return 0.0
        return np.mean([r.embedding_cost_usd for r in self.results])

    @property
    def avg_infrastructure(self) -> float:
        """Average total infrastructure cost per test (multi-hop + judge + embeddings)."""
        return self.avg_multi_hop + self.avg_judge + self.avg_embedding

    @property
    def avg_total_cost(self) -> float:
        """Average total cost per test including production and infrastructure costs."""
        if not self.results:
            return 0.0
        return np.mean([r.total_cost_usd for r in self.results])

    @property
    def avg_quote_recall(self) -> float | None:
        """Average quote recall across all results (skips None values)."""
        values = [r.quote_recall for r in self.results if r.quote_recall is not None]
        return float(np.mean(values)) if values else None

    @property
    def std_dev_quote_recall(self) -> float:
        """Standard deviation of quote recall (returns 0.0 if < 2 values)."""
        values = [r.quote_recall for r in self.results if r.quote_recall is not None]
        return float(np.std(values)) if len(values) >= 2 else 0.0

    @property
    def avg_quote_precision(self) -> float | None:
        """Average quote precision across all results (skips None values)."""
        values = [r.quote_precision for r in self.results if r.quote_precision is not None]
        return float(np.mean(values)) if values else None

    @property
    def std_dev_quote_precision(self) -> float:
        """Standard deviation of quote precision (returns 0.0 if < 2 values)."""
        values = [r.quote_precision for r in self.results if r.quote_precision is not None]
        return float(np.std(values)) if len(values) >= 2 else 0.0

    @property
    def avg_quote_faithfulness(self) -> float | None:
        """Average quote faithfulness across all results (skips None values)."""
        values = [r.quote_faithfulness for r in self.results if r.quote_faithfulness is not None]
        return float(np.mean(values)) if values else None

    @property
    def std_dev_quote_faithfulness(self) -> float:
        """Standard deviation of quote faithfulness (returns 0.0 if < 2 values)."""
        values = [r.quote_faithfulness for r in self.results if r.quote_faithfulness is not None]
        return float(np.std(values)) if len(values) >= 2 else 0.0

    @property
    def avg_explanation_faithfulness(self) -> float | None:
        """Average explanation faithfulness across all results (skips None values)."""
        values = [r.explanation_faithfulness for r in self.results if r.explanation_faithfulness is not None]
        return float(np.mean(values)) if values else None

    @property
    def std_dev_explanation_faithfulness(self) -> float:
        """Standard deviation of explanation faithfulness (returns 0.0 if < 2 values)."""
        values = [r.explanation_faithfulness for r in self.results if r.explanation_faithfulness is not None]
        return float(np.std(values)) if len(values) >= 2 else 0.0

    @property
    def avg_answer_correctness(self) -> float | None:
        """Average answer correctness across all results (skips None values)."""
        values = [r.answer_correctness for r in self.results if r.answer_correctness is not None]
        return float(np.mean(values)) if values else None

    @property
    def std_dev_answer_correctness(self) -> float:
        """Standard deviation of answer correctness (returns 0.0 if < 2 values)."""
        values = [r.answer_correctness for r in self.results if r.answer_correctness is not None]
        return float(np.std(values)) if len(values) >= 2 else 0.0


@dataclass
class QualityReport:
    """The main container for a full quality test report, covering all runs, tests, and models."""

    results: list[IndividualTestResult]
    total_time_seconds: float
    total_cost_usd: float
    runs: int
    models: list[str]
    test_cases: list[str]
    report_dir: str
    judge_model: str
    prompt_path: str | None = None
    chart_path: str | None = None
    ragas_chart_path: str | None = None

    # Populated by the aggregator
    per_test_case_reports: dict[str, TestCaseReport] = field(default_factory=dict)
    per_model_summaries: dict[str, ModelSummary] = field(default_factory=dict)

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
