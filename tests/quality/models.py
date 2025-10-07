"""Data models for response quality testing.

Defines test descriptors, requirements, and results.
"""

from dataclasses import dataclass, field
from typing import Literal, List
from uuid import UUID


RequirementType = Literal["contains", "llm"]


@dataclass
class TestRequirement:
    """Single requirement for a quality test."""

    type: RequirementType  # "contains" or "llm"
    description: str  # Text to check for (contains) or statement to verify (llm)
    points: int  # Points awarded if requirement passes
    check: str = ""  # Optional check title/name


@dataclass
class TestCase:
    """Quality test case descriptor."""

    test_id: str  # Unique identifier (e.g., "track-enemy-tacop")
    query: str  # Query to send to the RAG system
    requirements: List[TestRequirement]  # List of requirements to check

    @property
    def max_score(self) -> int:
        """Calculate maximum possible score for this test."""
        return sum(req.points for req in self.requirements)


@dataclass
class RequirementResult:
    """Result of evaluating a single requirement."""

    requirement: TestRequirement
    passed: bool
    points_earned: int
    details: str = ""  # Optional details about the evaluation
    judge_malfunction: bool = False  # True if judge model failed to evaluate


@dataclass
class TestResult:
    """Result of running a single test case with a specific model."""

    test_id: str
    query: str
    model: str
    response: str
    system_prompt: str  # System prompt used for generation

    # Scoring
    requirements: List[RequirementResult]
    score: int
    max_score: int

    # Performance metrics
    generation_time_seconds: float
    token_count: int
    cost_usd: float
    response_chars: int = 0  # Number of characters in response

    @property
    def passed(self) -> bool:
        """Whether the test passed (score > 0)."""
        return self.score > 0

    @property
    def pass_rate(self) -> float:
        """Percentage of points earned."""
        if self.max_score == 0:
            return 0.0
        return (self.score / self.max_score) * 100

    @property
    def points_lost_to_llm_error(self) -> int:
        """Points lost due to LLM judge malfunction."""
        return sum(
            r.requirement.points
            for r in self.requirements
            if r.judge_malfunction and r.points_earned == 0
        )

    @property
    def points_failed(self) -> int:
        """Points lost due to actual test failure (not LLM error)."""
        return sum(
            r.requirement.points - r.points_earned
            for r in self.requirements
            if not r.judge_malfunction
        )


@dataclass
class QualityTestSuite:
    """Results from running a full quality test suite."""

    timestamp: str  # ISO format timestamp
    test_results: List[TestResult]

    # Overall metrics
    total_tests: int
    total_queries: int
    total_time_seconds: float
    total_cost_usd: float
    total_response_chars: int = 0  # Total characters across all responses

    judge_model: str = "gemini-2.5-flash"

    @property
    def average_score(self) -> float:
        """Average score across all tests."""
        if not self.test_results:
            return 0.0
        return sum(r.score for r in self.test_results) / len(self.test_results)

    @property
    def average_time(self) -> float:
        """Average generation time per query."""
        if not self.test_results:
            return 0.0
        return self.total_time_seconds / self.total_queries

    @property
    def total_llm_error_points(self) -> int:
        """Total points lost to LLM judge malfunctions across all tests."""
        return sum(r.points_lost_to_llm_error for r in self.test_results)

    @property
    def total_possible_points(self) -> int:
        """Total possible points across all tests."""
        return sum(r.max_score for r in self.test_results)

    @property
    def total_earned_points(self) -> int:
        """Total points earned across all tests."""
        return sum(r.score for r in self.test_results)


@dataclass
class MultiRunTestSuite:
    """Results from running quality tests N times."""

    run_suites: List[QualityTestSuite]  # All individual test runs
    run_count: int  # Number of runs (N)

    # Metadata
    first_run_timestamp: str  # ISO format timestamp of first run
    last_run_timestamp: str  # ISO format timestamp of last run

    @property
    def test_ids(self) -> List[str]:
        """Get unique test IDs across all runs."""
        if not self.run_suites or not self.run_suites[0].test_results:
            return []
        # Assume all runs have same test structure
        return list(set(r.test_id for r in self.run_suites[0].test_results))

    @property
    def models(self) -> List[str]:
        """Get unique models tested across all runs."""
        if not self.run_suites or not self.run_suites[0].test_results:
            return []
        # Assume all runs have same test structure
        return sorted(set(r.model for r in self.run_suites[0].test_results))
