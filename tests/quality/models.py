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
