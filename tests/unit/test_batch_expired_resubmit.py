"""Whole-batch `expired` poll status is reported distinctly (for resubmission)."""

from src.services.llm.batch.backends import OpenAICompatBatchBackend


class _FakeBatches:
    def __init__(self, status):
        self._status = status

    def retrieve(self, _id):
        class R:
            status = self._status

        return R()


class _FakeClient:
    def __init__(self, status):
        self.batches = _FakeBatches(status)


def test_poll_reports_expired_distinctly():
    b = OpenAICompatBatchBackend(api_key="k", base_url="http://x", name="openai")
    b._client = _FakeClient("expired")
    assert b.poll("batch_1") == "expired"
    b._client = _FakeClient("completed")
    assert b.poll("batch_1") == "ended"
    b._client = _FakeClient("in_progress")
    assert b.poll("batch_1") == "in_progress"
    b._client = _FakeClient("failed")
    assert b.poll("batch_1") == "failed"


def test_collect_generation_expired_resubmits(tmp_path, monkeypatch):
    """An expired generation batch is resubmitted; phase stays generation_submitted."""
    import asyncio
    from datetime import UTC, datetime

    from src.services.llm.batch import backends as backends_mod
    from src.services.llm.factory import LLMProviderFactory
    from tests.quality.batch.manifest import BatchManifest
    from tests.quality.test_runner import QualityTestRunner

    BatchManifest(
        phase="generation_submitted",
        created_at=datetime.now(UTC).isoformat(),
        models=["kimi-k2.5"],
        judge_model="grok-4-1-fast-reasoning",
        runs=1,
        test_ids=["t1"],
        report_dir=str(tmp_path),
        generation={"moonshot": {"batch_id": "b1", "status": "in_progress"}},
        judge={},
        requests=[{
            "custom_id": "gen__t1__kimi__run1",
            "test_id": "t1", "model": "kimi-k2.5", "run_num": 1,
            "kind": "gen", "backend": "moonshot", "batchable": True,
            "embedding_cost": 0.0, "multi_hop_cost": 0.0,
        }],
        live_done=[],
        contexts={"t1__run1": {"context": ["ctx text"], "chunk_ids": ["cid1"]}},
    ).save()

    submitted = []

    class _Fake:
        name = "moonshot"

        def poll(self, _b):
            return "expired"

        def submit(self, lines):
            submitted.append(lines)
            return "b2"

    monkeypatch.setattr(backends_mod, "make_backend", lambda _n: _Fake())

    class _TC:
        query = "q?"

    class _Prov:
        def build_batch_request(self, _req, cid):
            return {"custom_id": cid, "body": {}}

    runner = object.__new__(QualityTestRunner)
    monkeypatch.setattr(runner, "load_test_cases", lambda _tid: [_TC()])
    monkeypatch.setattr(LLMProviderFactory, "create", lambda _m: _Prov())

    phase = asyncio.run(runner.collect_batch_run(tmp_path))

    assert phase == "generation_submitted"
    assert submitted and submitted[0][0]["custom_id"] == "gen__t1__kimi__run1"
    assert BatchManifest.load(tmp_path).generation["moonshot"]["batch_id"] == "b2"
