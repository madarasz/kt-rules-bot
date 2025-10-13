"""Data models for quality test case definitions."""

from dataclasses import dataclass
from typing import Literal, List

RequirementType = Literal["contains", "llm"]

@dataclass
class TestRequirement:
    """Single requirement for a quality test."""
    type: RequirementType
    description: str
    points: int
    check: str = ""

@dataclass
class TestCase:
    """Quality test case descriptor."""
    test_id: str
    query: str
    requirements: List[TestRequirement]

    @property
    def max_score(self) -> int:
        """Calculate maximum possible score for this test."""
        return sum(req.points for req in self.requirements)
