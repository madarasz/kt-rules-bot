"""Data models for quality test case definitions."""

from dataclasses import dataclass

from src.lib.constants import (
    GROUND_TRUTH_PRIORITY_WEIGHTS,
    DEFAULT_GROUND_TRUTH_PRIORITY,
)


@dataclass
class GroundTruthAnswer:
    """Ground truth answer with key and priority weight.

    Attributes:
        key: Unique identifier for this answer (used in reports)
        text: The answer text
        priority: Priority level (critical, important, supporting) - affects weighting
    """
    key: str
    text: str
    priority: str = DEFAULT_GROUND_TRUTH_PRIORITY

    @property
    def weight(self) -> float:
        """Get numeric weight based on priority level."""
        return GROUND_TRUTH_PRIORITY_WEIGHTS.get(
            self.priority,
            GROUND_TRUTH_PRIORITY_WEIGHTS[DEFAULT_GROUND_TRUTH_PRIORITY]
        )


@dataclass
class GroundTruthContext:
    """Ground truth context (rule) with key and priority weight.

    Attributes:
        key: Unique identifier for this context (used in reports)
        text: The rule text (should match rules verbatim)
        priority: Priority level (critical, important, supporting) - affects quote recall weighting
    """
    key: str
    text: str
    priority: str = DEFAULT_GROUND_TRUTH_PRIORITY

    @property
    def weight(self) -> float:
        """Get numeric weight based on priority level."""
        return GROUND_TRUTH_PRIORITY_WEIGHTS.get(
            self.priority,
            GROUND_TRUTH_PRIORITY_WEIGHTS[DEFAULT_GROUND_TRUTH_PRIORITY]
        )


@dataclass
class TestCase:
    """Quality test case descriptor with weighted ground truth for evaluation.

    Attributes:
        test_id: Unique test identifier
        query: User question to test
        ground_truth_answers: List of expected answer statements with keys and priorities
        ground_truth_contexts: List of rules that should be cited with keys and priorities
        requirements: Legacy field (deprecated, can be removed)
    """
    test_id: str
    query: str
    ground_truth_answers: list[GroundTruthAnswer]
    ground_truth_contexts: list[GroundTruthContext]

    # Legacy support - can be removed if no longer needed
    requirements: list | None = None

    @property
    def max_score(self) -> int:
        """Legacy compatibility - returns fixed score for Ragas metrics."""
        return 100  # Ragas metrics are percentages (0-1 scaled to 0-100)
