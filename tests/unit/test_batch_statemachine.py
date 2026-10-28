"""State-machine wiring for batch-collect (no network, no DB, no LLM)."""

from datetime import UTC, datetime

import pytest

from src.services.llm.batch import backends as backends_mod
from tests.quality.batch.manifest import BatchManifest
from tests.quality.test_runner import QualityTestRunner


class _FakeBackend:
    def __init__(self, name, poll_status, items=None):
        self.name = name
        self._poll_status = poll_status
        self._items = items or {}

    def poll(self, _batch_id):
        return self._poll_status

    def fetch(self, _batch_id):
        return self._items


def _runner():
    # Skip heavy __init__ (vector DB, embeddings); set only what collect needs.
    r = object.__new__(QualityTestRunner)
    r.judge_model = "grok-4-1-fast-reasoning"  # not batchable -> live judge path
    return r


def _manifest(tmp_path):
    m = BatchManifest(
        phase="generation_submitted",
        created_at=datetime.now(UTC).isoformat(),
        models=["claude-4.6-sonnet"],
        judge_model="grok-4-1-fast-reasoning",
        runs=1,
        test_ids=["t1"],
        report_dir=str(tmp_path),
        generation={"anthropic": {"batch_id": "b1", "status": "in_progress"}},
        judge={},
        requests=[{
            "custom_id": "gen__t1__claude-4.6-sonnet__run1",
            "test_id": "t1", "model": "claude-4.6-sonnet", "run_num": 1,
            "kind": "gen", "backend": "anthropic", "batchable": True,
            "embedding_cost": 0.0, "multi_hop_cost": 0.0,
        }],
        live_done=[],
    )
    m.save()
    return m


def test_collect_generation_ended_runs_live_judge_and_finishes(tmp_path, monkeypatch):
    _manifest(tmp_path)
    runner = _runner()

    fake = _FakeBackend("anthropic", "ended", items={"gen__t1__claude-4.6-sonnet__run1": {"ok": 1}})
    monkeypatch.setattr(backends_mod, "make_backend", lambda _name: fake)
    monkeypatch.setattr(backends_mod, "resolve_backend", lambda _model: None)  # judge live

    writes = []

    def _fake_write(_rd, meta, _item, _ctx):
        writes.append(meta["custom_id"])
        return ("succeeded", None)

    monkeypatch.setattr(runner, "_write_batch_generation_output", _fake_write)
    monkeypatch.setattr("tests.quality.output_parser.parse_output_directory", lambda _d: ["PO"])
    monkeypatch.setattr(runner, "_load_test_cases_for_outputs", lambda _parsed: {})

    async def _judge(_parsed, _tcm):
        return ["RESULT"]
    monkeypatch.setattr(runner, "_judge_parsed_outputs", _judge)

    finalized = []
    monkeypatch.setattr(runner, "_finalize_report",
                        lambda results, _rd, _m: finalized.append(results))

    import asyncio
    phase = asyncio.run(runner.collect_batch_run(tmp_path))

    assert phase == "done"
    assert writes == ["gen__t1__claude-4.6-sonnet__run1"]
    assert finalized == [["RESULT"]]
    assert BatchManifest.load(tmp_path).phase == "done"


def test_collect_generation_not_ready_is_noop(tmp_path, monkeypatch):
    _manifest(tmp_path)
    runner = _runner()

    fake = _FakeBackend("anthropic", "in_progress")
    monkeypatch.setattr(backends_mod, "make_backend", lambda _name: fake)

    called = []
    monkeypatch.setattr(runner, "_finalize_report", lambda *_a: called.append(1))

    import asyncio
    phase = asyncio.run(runner.collect_batch_run(tmp_path))

    assert phase == "generation_submitted"
    assert called == []  # no report written
    assert BatchManifest.load(tmp_path).phase == "generation_submitted"


def test_collect_generation_poll_error_keeps_other_backends_progress(tmp_path, monkeypatch):
    # xAI answers 403 once the team is out of credits. That backend must stay
    # in progress without aborting the pass, so the anthropic results fetched
    # in the same pass are saved.
    m = _manifest(tmp_path)
    m.generation["x"] = {"batch_id": "bx", "status": "in_progress"}
    m.requests.append({
        "custom_id": "gen__t1__grok-4.3__run1",
        "test_id": "t1", "model": "grok-4.3", "run_num": 1,
        "kind": "gen", "backend": "x", "batchable": True,
        "embedding_cost": 0.0, "multi_hop_cost": 0.0,
    })
    m.save()
    runner = _runner()

    class _ForbiddenBackend(_FakeBackend):
        def poll(self, _batch_id):
            raise RuntimeError("403 Forbidden: used all available credits")

    fakes = {
        "anthropic": _FakeBackend(
            "anthropic", "ended", items={"gen__t1__claude-4.6-sonnet__run1": {"ok": 1}}
        ),
        "x": _ForbiddenBackend("x", None),
    }
    monkeypatch.setattr(backends_mod, "make_backend", lambda name: fakes[name])
    monkeypatch.setattr(
        runner, "_write_batch_generation_output", lambda *_a: ("succeeded", None)
    )

    import asyncio
    phase = asyncio.run(runner.collect_batch_run(tmp_path))

    assert phase == "generation_submitted"
    saved = BatchManifest.load(tmp_path)
    assert saved.generation["anthropic"]["collected"] is True
    assert not saved.generation["x"].get("collected")
    row = next(r for r in saved.requests if r["backend"] == "anthropic")
    assert row["status"] == "succeeded"


def test_collect_done_is_idempotent(tmp_path):
    m = _manifest(tmp_path)
    m.phase = "done"
    m.save()
    import asyncio
    assert asyncio.run(_runner().collect_batch_run(tmp_path)) == "done"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
