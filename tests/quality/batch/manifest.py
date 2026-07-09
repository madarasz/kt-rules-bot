"""Batch run manifest — the single source of truth for a batch quality-test run.

Persisted as `batch_state.json` in the results dir. `batch-collect` reads the
`phase` field, advances it at most one step per invocation, and saves.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

MANIFEST_FILENAME = "batch_state.json"


@dataclass
class BatchManifest:
    """State of a two-phase batch run.

    phase: "generation_submitted" -> "judge_submitted" -> "scoring" -> "done".
    generation / judge: backend name -> {"batch_id": str, "status": str}.
    requests: one row per test x model x run x kind (gen|judge), carrying the
        custom_id used to map results back and whether it went to a batch.
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

    @staticmethod
    def make_custom_id(kind: str, test_id: str, model: str, run_num: int) -> str:
        """Encode a custom_id for round-trip mapping (kind__test__model__runN)."""
        return f"{kind}__{test_id}__{model}__run{run_num}"

    @staticmethod
    def parse_custom_id(custom_id: str) -> tuple[str, str, str, int]:
        """Decode a custom_id back into (kind, test_id, model, run_num)."""
        kind, test_id, model, run_token = custom_id.split("__")
        return kind, test_id, model, int(run_token.removeprefix("run"))

    def save(self) -> None:
        path = Path(self.report_dir) / MANIFEST_FILENAME
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, report_dir: Path | str) -> "BatchManifest":
        path = Path(report_dir) / MANIFEST_FILENAME
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**data)
