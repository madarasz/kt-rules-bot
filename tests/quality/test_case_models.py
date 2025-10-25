"""Data models for quality test case definitions."""

from dataclasses import dataclass
from typing import List, Optional

@dataclass
class TestCase:
    """Quality test case descriptor with ground truth for Ragas evaluation."""
    test_id: str
    query: str
    ground_truth_answers: List[str]
    ground_truth_contexts: List[str]
    
    # Legacy support - optional for backward compatibility during migration
    requirements: Optional[List] = None

    @property
    def max_score(self) -> int:
        """Legacy compatibility - returns fixed score for Ragas metrics."""
        return 100  # Ragas metrics are percentages (0-1 scaled to 0-100)
