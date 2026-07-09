"""Tests for the batch run manifest (batch_state.json)."""

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


def test_parse_custom_id():
    assert BatchManifest.parse_custom_id("judge__t1__gpt-4.1__run3") == (
        "judge",
        "t1",
        "gpt-4.1",
        3,
    )


def test_make_custom_id_roundtrips():
    cid = BatchManifest.make_custom_id("gen", "t1", "claude-4.6-sonnet", 2)
    assert BatchManifest.parse_custom_id(cid) == ("gen", "t1", "claude-4.6-sonnet", 2)
