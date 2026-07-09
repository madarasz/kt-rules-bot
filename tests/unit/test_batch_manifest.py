"""Tests for the batch run manifest (batch_state.json)."""

import re
from pathlib import Path

from tests.quality.batch.manifest import BatchManifest


def test_save_load_roundtrip(tmp_path: Path):
    m = BatchManifest(
        phase="generation_submitted",
        created_at="t",
        models=["claude-4.6-sonnet"],
        judge_model="grok-4-1-fast-reasoning",
        runs=1,
        test_ids=["t1"],
        report_dir=str(tmp_path),
        generation={"anthropic": {"batch_id": "b1", "status": "in_progress"}},
        judge={},
        requests=[
            {
                "custom_id": "gen__t1__claude-4.6-sonnet__run1",
                "test_id": "t1",
                "model": "claude-4.6-sonnet",
                "run_num": 1,
                "kind": "gen",
                "backend": "anthropic",
                "batchable": True,
            }
        ],
        live_done=[],
    )
    m.save()
    assert (tmp_path / "batch_state.json").exists()
    loaded = BatchManifest.load(tmp_path)
    assert loaded.phase == "generation_submitted"
    assert loaded.generation["anthropic"]["batch_id"] == "b1"
    assert loaded.requests[0]["run_num"] == 1


CUSTOM_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def test_make_custom_id_is_anthropic_safe():
    # Dotted model name (the live-smoke failure) must sanitize to a valid id.
    cid = BatchManifest.make_custom_id("gen", "teleport-counteract", "claude-4.6-sonnet", 1)
    assert CUSTOM_ID_PATTERN.match(cid), cid
    assert "." not in cid


def test_make_custom_id_caps_length_and_stays_unique():
    long_test = "a" * 80
    a = BatchManifest.make_custom_id("gen", long_test, "gemini-3.1-pro-preview", 10)
    b = BatchManifest.make_custom_id("gen", long_test, "gemini-3.1-pro-preview", 11)
    assert CUSTOM_ID_PATTERN.match(a) and len(a) <= 64
    assert a != b  # different run -> different id even after truncation


def test_make_custom_id_deterministic():
    # Judge round rebuilds the id from metadata; must match the submitted one.
    args = ("judge", "t1", "claude-4.6-sonnet", 3)
    assert BatchManifest.make_custom_id(*args) == BatchManifest.make_custom_id(*args)
