"""Metadata generation and extraction for quality test outputs.

This module centralizes all metadata-related logic for quality tests,
enabling test replay without re-running expensive RAG and LLM operations.
"""

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional

from src.lib.logging import get_logger
from src.services.llm.base import LLMResponse
from tests.quality.reporting.report_models import IndividualTestResult
from tests.quality.test_case_models import GroundTruthContext

if TYPE_CHECKING:
    from tests.quality.ragas_evaluator import RagasMetrics

logger = get_logger(__name__)


@dataclass
class OutputMetadata:
    """
    Complete metadata for a quality test output file.

    Includes all data needed to replay test without re-running RAG or LLM.
    This metadata is embedded in output_*.md files for future replay.
    """

    # Test identification
    test_metadata: dict  # test_id, model, actual_model_id, run_num, timestamp

    # Costs (all non-judge components)
    costs: dict  # llm_generation_usd, multi_hop_usd, embedding_usd, total_non_judge_usd

    # Performance
    latency: dict  # llm_generation_seconds
    tokens: dict  # prompt, completion, total

    # Deterministic metrics (can be reused without re-evaluation)
    deterministic_metrics: dict
    # {
    #   "quote_precision": 0.85,
    #   "quote_recall": 0.92,
    #   "quote_faithfulness": 0.88,
    #   "quote_recall_feedback": "**Missing contexts:**\n- ⭐ Distance...",
    #   "quote_faithfulness_details": {"a1b2c3d4": 0.95, "e5f6g7h8": 0.82},
    #   "llm_quotes_structured": [
    #       {"chunk_id": "a1b2c3d4", "quote_title": "...", "quote_text": "..."},
    #       ...
    #   ]
    # }

    def to_json(self) -> str:
        """Serialize to JSON for embedding in markdown."""
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "OutputMetadata":
        """Deserialize from JSON."""
        data = json.loads(json_str)
        return cls(**data)


class MetadataGenerator:
    """
    Generates metadata for quality test outputs.

    Extracts all information needed for replay without re-running expensive operations.
    """

    @staticmethod
    def generate_metadata(
        test_id: str,
        model: str,
        run_num: int,
        llm_response: LLMResponse,
        result: IndividualTestResult,
        metrics: "RagasMetrics",
    ) -> OutputMetadata:
        """
        Generate complete metadata from test result.

        Args:
            test_id: Test case identifier
            model: Friendly model name (e.g., "claude-4.5-sonnet")
            run_num: Run number (for multi-run tests)
            llm_response: Raw LLM response object
            result: Test result with costs and timing
            metrics: Evaluation metrics including deterministic scores

        Returns:
            OutputMetadata ready for serialization
        """
        return OutputMetadata(
            test_metadata={
                "test_id": test_id,
                "model": model,
                "actual_model_id": llm_response.model_version,
                "run_num": run_num,
                "timestamp": datetime.now(UTC).isoformat(),
            },
            costs={
                "llm_generation_usd": result.cost_usd,
                "multi_hop_usd": result.multi_hop_cost_usd,
                "embedding_usd": result.embedding_cost_usd,
                "total_non_judge_usd": result.cost_usd
                + result.multi_hop_cost_usd
                + result.embedding_cost_usd,
            },
            latency={"llm_generation_seconds": result.generation_time_seconds},
            tokens={
                "prompt": llm_response.prompt_tokens,
                "completion": llm_response.completion_tokens,
                "total": llm_response.prompt_tokens + llm_response.completion_tokens,
            },
            deterministic_metrics={
                # Core scores
                "quote_precision": metrics.quote_precision,
                "quote_recall": metrics.quote_recall,
                "quote_faithfulness": metrics.quote_faithfulness,
                # Textual feedback
                "quote_recall_feedback": metrics.quote_recall_feedback,
                # Detailed breakdowns
                "quote_faithfulness_details": metrics.quote_faithfulness_details,
                "llm_quotes_structured": metrics.llm_quotes_structured,
            },
        )

    @staticmethod
    def extract_deterministic_metrics_from_metadata(metadata: OutputMetadata) -> dict:
        """
        Extract deterministic metrics that can be reused during replay.

        Returns dict suitable for initializing RagasMetrics partial object.

        Args:
            metadata: Parsed metadata from output file

        Returns:
            Dict with deterministic metric fields for RagasMetrics
        """
        dm = metadata.deterministic_metrics

        return {
            "quote_precision": dm["quote_precision"],
            "quote_recall": dm["quote_recall"],
            "quote_faithfulness": dm["quote_faithfulness"],
            "quote_recall_feedback": dm["quote_recall_feedback"],
            "quote_faithfulness_details": dm["quote_faithfulness_details"],
            "llm_quotes_structured": dm["llm_quotes_structured"],
            # Judge metrics will be filled in during replay
            "explanation_faithfulness": None,
            "answer_correctness": None,
            "feedback": "",
        }

    @staticmethod
    def generate_quote_recall_feedback(
        score: float | None,
        retrieved_contexts: list[str],
        normalized_ground_truth_contexts: list[str],
        original_ground_truth_contexts: list[str],
        ground_truth_context_objects: list[GroundTruthContext] | None = None,
    ) -> str | None:
        """
        Generate feedback for quote recall showing missing ground truth contexts.

        Extracted from RagasEvaluator._generate_quote_recall_feedback()
        for reuse in both test runner and replay modes.

        Quote Recall measures how much of the expected information was cited.
        Lists which ground truth contexts were not found in the quotes, showing keys and priorities.

        Args:
            score: The quote recall score (0-1, priority-weighted)
            retrieved_contexts: Normalized contexts that were retrieved/cited
            normalized_ground_truth_contexts: Normalized expected contexts
            original_ground_truth_contexts: Original (non-normalized) expected contexts for display
            ground_truth_context_objects: GroundTruthContext objects with keys and priorities (optional)

        Returns:
            Feedback listing missing ground truths with keys and priorities, or None if perfect score
        """
        if score is None or score >= 1.0:
            return None  # Perfect score or unable to calculate

        # Find which ground truths are missing
        missing_ground_truths = []

        if ground_truth_context_objects:
            # New format: use keys and priorities
            for gt_obj, norm_gt in zip(
                ground_truth_context_objects, normalized_ground_truth_contexts, strict=False
            ):
                # Check if this ground truth appears in any retrieved context
                found = any(
                    norm_gt in retrieved or retrieved in norm_gt for retrieved in retrieved_contexts
                )
                if not found:
                    # Priority icons
                    priority_icon = {
                        "critical": "⭐",
                        "important": "⚠️",
                        "supporting": "ℹ️",
                    }.get(gt_obj.priority, "•")

                    missing_ground_truths.append(
                        (gt_obj.key, gt_obj.text, gt_obj.priority, priority_icon, gt_obj.weight)
                    )
        else:
            # Legacy format: use indices
            for i, (norm_gt, orig_gt) in enumerate(
                zip(normalized_ground_truth_contexts, original_ground_truth_contexts, strict=False),
                1,
            ):
                # Check if this ground truth appears in any retrieved context
                found = any(
                    norm_gt in retrieved or retrieved in norm_gt for retrieved in retrieved_contexts
                )
                if not found:
                    missing_ground_truths.append((f"context_{i}", orig_gt, "unknown", "•", 1.0))

        if not missing_ground_truths:
            return None  # All ground truths found

        # Generate feedback
        feedback_lines = []
        feedback_lines.append("**Missing ground truth contexts:**")
        for key, text, priority, icon, weight in missing_ground_truths:
            # Truncate long contexts
            text_display = text[:120] + "..." if len(text) > 120 else text
            weight_str = f"{weight:.0f}" if weight is not None else "N/A"
            feedback_lines.append(
                f"  - {icon} **{key}** ({priority}, weight={weight_str}): {text_display}"
            )

        return "  \n".join(feedback_lines)


class MetadataFormatter:
    """
    Formats metadata for embedding in markdown files.
    """

    @staticmethod
    def format_metadata_block(metadata: OutputMetadata) -> str:
        """
        Format metadata as HTML comment block for markdown.

        Returns:
            String ready to append to output_*.md file
        """
        json_str = metadata.to_json()

        return f"""
---

<!-- METADATA:START -->
```json
{json_str}
```
<!-- METADATA:END -->
"""

    @staticmethod
    def extract_metadata_from_markdown(content: str) -> Optional[OutputMetadata]:
        """
        Extract metadata from markdown file.

        Args:
            content: Full markdown file content

        Returns:
            OutputMetadata if found, None otherwise
        """
        pattern = r"<!-- METADATA:START -->\s*```json\s*(\{.*?\})\s*```\s*<!-- METADATA:END -->"
        match = re.search(pattern, content, re.DOTALL)

        if not match:
            return None

        json_str = match.group(1)
        return OutputMetadata.from_json(json_str)
