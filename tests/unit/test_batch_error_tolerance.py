"""Per-item batch error tolerance: generation retry/recovery, permanent synthesis,
and multi-backend re-fetch idempotency (no network, no LLM)."""

import asyncio
import json
from datetime import UTC, datetime

import pytest

from src.services.llm.factory import LLMProviderFactory
from tests.quality.batch import backends as backends_mod
from tests.quality.batch.manifest import BatchManifest
from tests.quality.reporting.report_models import IndividualTestResult
from tests.quality.test_runner import QualityTestRunner

MODEL = "modelx"
JUDGE = "grok-4-1-fast-reasoning"  # resolve_backend monkeypatched to None -> live judge


class _TC:
    query = "q?"
    max_score = 100
    ground_truth_contexts = []


class _Prov:
    def build_batch_request(self, _req, cid):
        return {"custom_id": cid, "body": {}}


class _FakeGenBackend:
    """Backend whose fetch() returns a scripted item set per call."""

    def __init__(self, name, fetch_by_call):
        self.name = name
        self._fetch_by_call = fetch_by_call
        self.fetch_calls = 0
        self.poll_calls = 0
        self.submitted = []

    def poll(self, _b):
        self.poll_calls += 1
        return "ended"

    def fetch(self, _b):
        items = self._fetch_by_call[self.fetch_calls]
        self.fetch_calls += 1
        return items

    def submit(self, lines):
        self.submitted.append([ln["custom_id"] for ln in lines])
        return f"resub{len(self.submitted)}"


def _gen_row(run, status="pending", attempts=0):
    return {
        "custom_id": BatchManifest.make_custom_id("gen", "t1", MODEL, run),
        "test_id": "t1",
        "model": MODEL,
        "run_num": run,
        "kind": "gen",
        "backend": "anthropic",
        "batchable": True,
        "embedding_cost": 0.0,
        "multi_hop_cost": 0.0,
        "status": status,
        "attempts": attempts,
    }


def _write_by_item(_rd, _meta, item, _ctx):
    """Stand-in for _write_batch_generation_output: fail iff item carries an error."""
    if item.get("error"):
        return ("error", item["error"])
    return ("succeeded", None)


def _prepare_runner(monkeypatch, fake, captured):
    monkeypatch.setattr(backends_mod, "make_backend", lambda _n: fake)
    monkeypatch.setattr(backends_mod, "resolve_backend", lambda _m: None)  # live judge
    monkeypatch.setattr(LLMProviderFactory, "create", lambda _m: _Prov())
    monkeypatch.setattr(
        "tests.quality.output_parser.parse_output_directory", lambda _d: []
    )
    runner = object.__new__(QualityTestRunner)
    monkeypatch.setattr(runner, "load_test_cases", lambda _tid: [_TC()])
    monkeypatch.setattr(runner, "_load_test_cases_for_outputs", lambda _p: {})
    monkeypatch.setattr(runner, "_write_batch_generation_output", _write_by_item)

    async def _judge(_parsed, _tcm):
        # Live-judge stand-in: return results for the runs that produced output
        # (run1 success, run2 recovered). run3 permanently failed -> no output.
        return captured["judge_results"]

    monkeypatch.setattr(runner, "_judge_parsed_outputs", _judge)

    def _finalize(results, _rd, manifest):
        captured["results"] = results
        captured["manifest"] = manifest

    monkeypatch.setattr(runner, "_finalize_report", _finalize)
    return runner


def test_generation_retry_recovers_and_synthesizes_permanent(tmp_path, monkeypatch):
    r1 = BatchManifest.make_custom_id("gen", "t1", MODEL, 1)
    r2 = BatchManifest.make_custom_id("gen", "t1", MODEL, 2)
    r3 = BatchManifest.make_custom_id("gen", "t1", MODEL, 3)

    BatchManifest(
        phase="generation_submitted",
        created_at=datetime.now(UTC).isoformat(),
        models=[MODEL],
        judge_model=JUDGE,
        runs=3,
        test_ids=["t1"],
        report_dir=str(tmp_path),
        generation={"anthropic": {"batch_id": "b1", "status": "in_progress", "attempts": 0, "collected": False}},
        judge={},
        requests=[_gen_row(1), _gen_row(2), _gen_row(3)],
        live_done=[],
        contexts={
            "t1__run1": {"context": ["c"], "chunk_ids": ["x"]},
            "t1__run2": {"context": ["c"], "chunk_ids": ["x"]},
            "t1__run3": {"context": ["c"], "chunk_ids": ["x"]},
        },
    ).save()

    fake = _FakeGenBackend(
        "anthropic",
        fetch_by_call=[
            {  # pass 1: r1 ok, r2 transient, r3 permanent
                r1: {},
                r2: {"error": "429 rate limit"},
                r3: {"error": "invalid_request: bad schema"},
            },
            {r2: {}},  # pass 2: resubmitted r2 succeeds
        ],
    )

    captured = {
        "judge_results": [
            IndividualTestResult(
                test_id="t1", query="q?", model=MODEL, run_num=run, score=90,
                max_score=100, passed=True, tokens=0, cost_usd=0.0,
                output_char_count=0, generation_time_seconds=0.0, output_filename="f",
            )
            for run in (1, 2)
        ]
    }
    runner = _prepare_runner(monkeypatch, fake, captured)

    # Pass 1: r2 re-requested, phase stays.
    phase1 = asyncio.run(runner.collect_batch_run(tmp_path))
    assert phase1 == "generation_submitted"
    m = BatchManifest.load(tmp_path)
    rows = m.rows_by_custom_id("gen")
    assert rows[r1]["status"] == "succeeded"
    assert rows[r2]["status"] == "pending" and rows[r2]["attempts"] == 1  # in flight again
    assert rows[r3]["status"] == "failed_permanent"
    assert rows[r3]["error_class"] == "permanent"
    assert fake.submitted == [[r2]]  # only the transient item was re-requested

    # Pass 2: r2 succeeds -> recovered; run finalizes.
    phase2 = asyncio.run(runner.collect_batch_run(tmp_path))
    assert phase2 == "done"
    m2 = BatchManifest.load(tmp_path)
    assert BatchManifest.is_recovered(m2.rows_by_custom_id("gen")[r2])

    # Enrichment: r2 tagged recovered; r3 synthesized as a score-0 error result.
    enriched = runner._enrich_and_synthesize_results(
        captured["results"], captured["manifest"]
    )
    by_run = {res.run_num: res for res in enriched}
    assert by_run[2].recovered_from_error is True
    assert by_run[2].recovery_attempts == 1
    assert by_run[1].recovered_from_error is False
    assert 3 in by_run  # synthesized
    assert by_run[3].score == 0 and by_run[3].error and by_run[3].error_class == "permanent"


def test_multi_backend_idempotency(tmp_path, monkeypatch):
    """A backend that finishes clean is not re-polled/re-fetched while another
    backend keeps retrying its failed item."""
    ra = BatchManifest.make_custom_id("gen", "t1", MODEL, 1)  # backend A (anthropic)
    rb = BatchManifest.make_custom_id("gen", "t2", MODEL, 1)  # backend B (openai)

    row_a = _gen_row(1)
    row_a["custom_id"] = ra
    row_a["test_id"] = "t1"
    row_a["backend"] = "anthropic"
    row_b = _gen_row(1)
    row_b["custom_id"] = rb
    row_b["test_id"] = "t2"
    row_b["backend"] = "openai"

    BatchManifest(
        phase="generation_submitted",
        created_at=datetime.now(UTC).isoformat(),
        models=[MODEL],
        judge_model=JUDGE,
        runs=1,
        test_ids=["t1", "t2"],
        report_dir=str(tmp_path),
        generation={
            "anthropic": {"batch_id": "a1", "status": "in_progress", "attempts": 0, "collected": False},
            "openai": {"batch_id": "b1", "status": "in_progress", "attempts": 0, "collected": False},
        },
        judge={},
        requests=[row_a, row_b],
        live_done=[],
        contexts={
            "t1__run1": {"context": ["c"], "chunk_ids": ["x"]},
            "t2__run1": {"context": ["c"], "chunk_ids": ["x"]},
        },
    ).save()

    fake_a = _FakeGenBackend("anthropic", fetch_by_call=[{ra: {}}])  # clean, one fetch
    fake_b = _FakeGenBackend(
        "openai", fetch_by_call=[{rb: {"error": "503 unavailable"}}, {rb: {}}]
    )
    fakes = {"anthropic": fake_a, "openai": fake_b}
    monkeypatch.setattr(backends_mod, "make_backend", lambda n: fakes[n])
    monkeypatch.setattr(backends_mod, "resolve_backend", lambda _m: None)
    monkeypatch.setattr(LLMProviderFactory, "create", lambda _m: _Prov())
    monkeypatch.setattr("tests.quality.output_parser.parse_output_directory", lambda _d: [])

    runner = object.__new__(QualityTestRunner)
    monkeypatch.setattr(runner, "load_test_cases", lambda _tid: [_TC()])
    monkeypatch.setattr(runner, "_load_test_cases_for_outputs", lambda _p: {})
    monkeypatch.setattr(runner, "_write_batch_generation_output", _write_by_item)

    async def _judge(_p, _t):
        return []

    monkeypatch.setattr(runner, "_judge_parsed_outputs", _judge)
    monkeypatch.setattr(runner, "_finalize_report", lambda *_a: None)

    # Pass 1: A clean+collected; B transient re-requested.
    assert asyncio.run(runner.collect_batch_run(tmp_path)) == "generation_submitted"
    assert fake_a.fetch_calls == 1 and fake_a.poll_calls == 1
    assert BatchManifest.load(tmp_path).generation["anthropic"]["collected"] is True

    # Pass 2: A is skipped entirely (no extra poll/fetch); B recovers -> done.
    assert asyncio.run(runner.collect_batch_run(tmp_path)) == "done"
    assert fake_a.fetch_calls == 1 and fake_a.poll_calls == 1  # untouched
    assert fake_b.fetch_calls == 2


class _FakeJudgeBackend:
    def __init__(self, name, fetch_by_call):
        self.name = name
        self._fetch_by_call = fetch_by_call
        self.fetch_calls = 0

    def poll(self, _b):
        return "ended"

    def fetch(self, _b):
        items = self._fetch_by_call[self.fetch_calls]
        self.fetch_calls += 1
        return items


class _PO:
    def __init__(self, run):
        self.metadata = type(
            "M", (), {"test_metadata": {"test_id": "t1", "model": MODEL, "run_num": run}}
        )()


class _DummyJudge:
    def __init__(self, *a, **k):
        pass


def _judge_row(run, status="pending", attempts=0):
    return {
        "custom_id": BatchManifest.make_custom_id("judge", "t1", MODEL, run),
        "test_id": "t1",
        "model": MODEL,
        "run_num": run,
        "kind": "judge",
        "backend": "openai",
        "batchable": True,
        "status": status,
        "attempts": attempts,
    }


def test_judge_item_retry_recovers(tmp_path, monkeypatch):
    """A transient judge-item failure is re-requested and recovers on the next pass."""
    j1 = BatchManifest.make_custom_id("judge", "t1", MODEL, 1)
    j2 = BatchManifest.make_custom_id("judge", "t1", MODEL, 2)

    BatchManifest(
        phase="judge_submitted",
        created_at=datetime.now(UTC).isoformat(),
        models=[MODEL],
        judge_model="gpt-4.1-mini",
        runs=2,
        test_ids=["t1"],
        report_dir=str(tmp_path),
        generation={"anthropic": {"batch_id": "b1", "status": "ended", "collected": True}},
        judge={"openai": {"batch_id": "jb1", "status": "in_progress", "attempts": 0, "collected": False}},
        requests=[_judge_row(1), _judge_row(2)],
        live_done=[],
    ).save()

    fake = _FakeJudgeBackend("openai", fetch_by_call=[{j1: {}, j2: {"error": "429 rate limit"}}, {j2: {}}])
    monkeypatch.setattr(backends_mod, "make_backend", lambda _n: fake)
    monkeypatch.setattr("tests.quality.custom_judge.CustomJudge", _DummyJudge)
    monkeypatch.setattr("tests.quality.output_parser.parse_output_directory",
                        lambda _d: [_PO(1), _PO(2)])

    resubmits = []

    def _fake_resubmit(_m, _name, custom_ids):
        resubmits.append(set(custom_ids))
        return f"jresub{len(resubmits)}"

    def _fake_score_item(_m, _bn, row, item, _tc, _j, _ja):
        if item.get("error"):
            from tests.quality.batch.errors import classify_batch_error

            cls, _r = classify_batch_error(item["error"])
            row["error"] = item["error"]
            row["error_class"] = cls
            row["status"] = (
                "failed_retryable"
                if cls == "transient" and row.get("attempts", 0) < 2
                else "failed_permanent"
            )
        else:
            row["status"] = "succeeded"
            row.pop("error", None)

    finalized = []
    runner = object.__new__(QualityTestRunner)
    monkeypatch.setattr(runner, "_load_test_cases_for_outputs", lambda _p: {"t1": _TC()})
    monkeypatch.setattr(runner, "_resubmit_judge", _fake_resubmit)
    monkeypatch.setattr(runner, "_score_judge_item", _fake_score_item)
    monkeypatch.setattr(runner, "_score_from_judge_batch", lambda _m: ["RESULT"])
    monkeypatch.setattr(runner, "_finalize_report", lambda results, _rd, _m: finalized.append(results))

    # Pass 1: j2 transient -> re-requested, phase stays judge_submitted.
    assert asyncio.run(runner.collect_batch_run(tmp_path)) == "judge_submitted"
    assert resubmits == [{j2}]
    m = BatchManifest.load(tmp_path)
    jrows = m.rows_by_custom_id("judge")
    assert jrows[j1]["status"] == "succeeded"
    assert jrows[j2]["status"] == "pending" and jrows[j2]["attempts"] == 1

    # Pass 2: j2 succeeds -> recovered, run finalizes.
    assert asyncio.run(runner.collect_batch_run(tmp_path)) == "done"
    m2 = BatchManifest.load(tmp_path)
    assert BatchManifest.is_recovered(m2.rows_by_custom_id("judge")[j2])
    assert finalized == [["RESULT"]]


class _JudgeableTC(_TC):
    ground_truth_answers = []


class _BuildingJudge:
    def build_judge_request(self, **_kw):
        return object()


class _POWithResponse(_PO):
    """Parsed output carrying a generation response body the judge builder must parse."""

    def __init__(self, run, answer_text):
        super().__init__(run)
        self.query = "q?"
        self.llm_response = type("R", (), {"answer_text": answer_text})()


def test_unbuildable_judge_item_is_recorded_not_dropped(monkeypatch):
    """An item that fails to build gets a failed_permanent row instead of vanishing.

    Without a row, _score_from_judge_batch later reports the bogus "judge item
    missing" and the run is logged as an unrecoverable *API* error with 0 attempts.
    """
    good = json.dumps({
        "smalltalk": False,
        "short_answer": "Yes.",
        "persona_short_answer": "Yes.",
        "quotes": [{"quote_title": "REPOSITION (1AP)", "quote_text": "...", "chunk_id": "a1"}],
        "explanation": "...",
        "persona_afterword": "...",
    })
    parsed = [_POWithResponse(1, good), _POWithResponse(2, "this is not json")]

    monkeypatch.setattr(
        "tests.quality.metadata_generator.MetadataGenerator"
        ".extract_deterministic_metrics_from_metadata",
        staticmethod(lambda _m: {"llm_quotes_structured": []}),
    )

    runner = object.__new__(QualityTestRunner)
    lines, rows = runner._build_judge_lines(
        parsed, {"t1": _JudgeableTC()}, _Prov(), _BuildingJudge()
    )

    assert len(lines) == 1, "only the parseable item yields a request line"

    by_cid = {r["custom_id"]: r for r in rows}
    assert len(by_cid) == 2, "every parsed output gets a row, buildable or not"

    ok = by_cid[BatchManifest.make_custom_id("judge", "t1", MODEL, 1)]
    assert ok["status"] == "pending"

    bad = by_cid[BatchManifest.make_custom_id("judge", "t1", MODEL, 2)]
    assert bad["status"] == "failed_permanent"
    assert bad["error_class"] == "permanent"
    assert "Invalid JSON from LLM" in bad["error"]
    # Permanent => excluded from re-request, so it never burns retry budget.
    assert bad["attempts"] == 0


def _resubmit_manifest(tmp_path) -> BatchManifest:
    return BatchManifest(
        phase="judge_submitted",
        created_at=datetime.now(UTC).isoformat(),
        models=[MODEL],
        judge_model="gpt-4.1-mini",
        runs=1,
        test_ids=["t1"],
        report_dir=str(tmp_path),
        generation={"anthropic": {"batch_id": "b1", "status": "ended", "collected": True}},
        judge={"openai": {"batch_id": "jb1", "status": "ended", "attempts": 0}},
        requests=[_judge_row(1, status="failed_retryable", attempts=1)],
        live_done=[],
        contexts={},
    )


class _ExplodingBackend:
    name = "openai"

    @staticmethod
    def submit(_lines):
        raise AssertionError("submit() must not be called when there is nothing to send")


def test_resubmit_judge_returns_none_when_nothing_rebuilds(tmp_path, monkeypatch):
    """Every item failing to rebuild must yield None, not an empty batch submission.

    submit([]) uploads a zero-byte JSONL that the host rejects, and the raise would
    escape _collect_judge before manifest.save(), discarding that pass's scores.
    """
    manifest = _resubmit_manifest(tmp_path)
    cid = manifest.requests[0]["custom_id"]

    monkeypatch.setattr(backends_mod, "make_backend", lambda _n: _ExplodingBackend())
    monkeypatch.setattr(LLMProviderFactory, "create", lambda _m: _Prov())
    monkeypatch.setattr(
        "tests.quality.output_parser.parse_output_directory",
        lambda _d: [_POWithResponse(1, "this is not json")],
    )
    monkeypatch.setattr(
        "tests.quality.metadata_generator.MetadataGenerator"
        ".extract_deterministic_metrics_from_metadata",
        staticmethod(lambda _m: {"llm_quotes_structured": []}),
    )
    runner = object.__new__(QualityTestRunner)
    monkeypatch.setattr(runner, "_load_test_cases_for_outputs", lambda _p: {"t1": _JudgeableTC()})

    assert runner._resubmit_judge(manifest, "openai", {cid}) is None

    row = manifest.rows_by_custom_id("judge")[cid]
    assert row["status"] == "failed_permanent"
    assert "Invalid JSON from LLM" in row["error"]
    # One row, not a duplicate appended alongside the original.
    assert len([r for r in manifest.requests if r["custom_id"] == cid]) == 1


def test_resubmit_judge_returns_none_when_provider_unavailable(tmp_path, monkeypatch):
    """A missing judge API key retires the items with a readable reason, not None."""
    manifest = _resubmit_manifest(tmp_path)
    cid = manifest.requests[0]["custom_id"]

    monkeypatch.setattr(backends_mod, "make_backend", lambda _n: _ExplodingBackend())
    monkeypatch.setattr(LLMProviderFactory, "create", lambda _m: None)
    runner = object.__new__(QualityTestRunner)

    assert runner._resubmit_judge(manifest, "openai", {cid}) is None

    row = manifest.rows_by_custom_id("judge")[cid]
    assert row["status"] == "failed_permanent"
    assert "missing API key" in row["error"]
    assert row["error_class"] == "permanent"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
