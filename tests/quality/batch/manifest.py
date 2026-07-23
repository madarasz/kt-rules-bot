"""Batch run manifest — the single source of truth for a batch quality-test run.

Persisted as `batch_state.json` in the results dir. `batch-collect` reads the
`phase` field, advances it at most one step per invocation, and saves.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from src.services.llm.batch.custom_id import safe_custom_id

MANIFEST_FILENAME = "batch_state.json"


@dataclass
class BatchManifest:
    """State of a two-phase batch run.

    phase: "generation_submitted" -> "judge_submitted" -> "scoring" -> "done".
    generation / judge: backend name -> {"batch_id": str, "status": str,
        "attempts": int (backend-level resubmits), "collected": bool (all its rows
        terminal — skip re-poll/re-fetch)}.
    requests: one row per test x model x run x kind (gen|judge), carrying the
        custom_id used to map results back and whether it went to a batch. Error
        tolerance adds per-row fields, all optional (a missing "status" == pending):
            status: "pending" | "succeeded" | "failed_retryable" | "failed_permanent"
            attempts: int  # per-item re-requests so far
            error: str | None  # last error text
            error_class: str | None  # "transient" | "permanent"
        A row is considered "recovered" when status == "succeeded" and attempts > 0.
    live_done: custom_ids that were run live (non-batch models) at submit time.
    """

    phase: str
    created_at: str
    models: list[str]
    judge_model: str
    runs: int
    test_ids: list[str]
    report_dir: str
    generation: dict[str, dict] = field(default_factory=dict)
    judge: dict[str, dict] = field(default_factory=dict)
    requests: list[dict] = field(default_factory=list)
    live_done: list[str] = field(default_factory=list)
    # Retrieval context keyed by f"{test_id}__run{run_num}" (shared across the
    # run's models) so batch-collect can recompute deterministic quote metrics.
    contexts: dict[str, dict] = field(default_factory=dict)

    @staticmethod
    def make_custom_id(kind: str, test_id: str, model: str, run_num: int) -> str:
        """Deterministic, provider-safe custom_id for (kind, test_id, model, run_num).

        Nothing round-trips the model back out of the id at runtime (gen maps via
        the manifest, judge recomputes deterministically), so the id only needs to
        be safe, deterministic, and unique per (kind, test, model, run). The
        sanitization rule itself lives in src/services/llm/batch/custom_id.py.
        """
        return safe_custom_id(f"{kind}__{test_id}__{model}__run{run_num}")

    def rows_by_custom_id(self, kind: str | None = None) -> dict[str, dict]:
        """Index request rows by custom_id, optionally filtered to one kind."""
        return {
            r["custom_id"]: r
            for r in self.requests
            if kind is None or r.get("kind") == kind
        }

    def retryable_custom_ids(self, kind: str, backend: str) -> set[str]:
        """custom_ids of a kind/backend still marked failed_retryable."""
        return {
            r["custom_id"]
            for r in self.requests
            if r.get("kind") == kind
            and r.get("backend") == backend
            and r.get("status") == "failed_retryable"
        }

    @staticmethod
    def is_recovered(row: dict) -> bool:
        """A row recovered if it eventually succeeded after >=1 re-request."""
        return row.get("status") == "succeeded" and row.get("attempts", 0) > 0

    def save(self) -> None:
        path = Path(self.report_dir) / MANIFEST_FILENAME
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, report_dir: Path | str) -> "BatchManifest":
        path = Path(report_dir) / MANIFEST_FILENAME
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**data)
