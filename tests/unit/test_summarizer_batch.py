"""Unit tests for batch summarization during ingestion.

No network: a fake backend stands in for the provider Batch API, and the LLM
adapter's build/parse hooks are stubbed. What is exercised here is the state
machine around them — submit, wait, apply, retry, fall back.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.models.rule_document import RuleDocument
from src.services.llm.base import LLMResponse
from src.services.llm.batch.custom_id import safe_custom_id
from src.services.rag.ingestion_state import IngestionState
from src.services.rag.summarizer_batch import BatchCosts, BatchSummarizer

MD = (
    "---\nsource: X\nlast_update_date: 2025-01-01\ndocument_type: core-rules\n---\n\n"
    "## Alpha\nalpha body\n\n## Beta\nbeta body\n"
)
META = {"source": "X", "last_update_date": "2025-01-01", "document_type": "core-rules"}


def _doc(relative_path="team/a.md", content=MD):
    return RuleDocument.from_markdown_file(
        filename=relative_path.rsplit("/", 1)[-1],
        content=content,
        metadata=META,
        relative_path=relative_path,
    )


def _summary_payload(count=2):
    return {
        "summaries": [
            {"chunk_number": i, "summary": f"summary {i}"} for i in range(1, count + 1)
        ]
    }


class FakeBackend:
    """Records submissions and replays canned fetch results."""

    name = "x"

    def __init__(self, results_per_batch, poll_status="ended"):
        # results_per_batch: list of {custom_id: item} dicts, one per submit()
        self._results = list(results_per_batch)
        self._poll_status = poll_status
        self.submitted: list[list[dict]] = []
        self.labels: list[str] = []
        self.poll_calls = 0

    def submit(self, lines, label="quality-test"):
        self.submitted.append(lines)
        self.labels.append(label)
        return f"batch-{len(self.submitted)}"

    def poll(self, batch_id):  # noqa: ARG002 - terminal on first call, no waiting in tests
        self.poll_calls += 1
        return self._poll_status

    def fetch(self, batch_id):
        index = int(batch_id.rsplit("-", 1)[1]) - 1
        return self._results[index] if index < len(self._results) else {}


def _summarize_live_stub(chunks):
    """Stand in for a *successful* live call: it must leave summaries behind.

    A stub that returned without touching the chunks would look identical to a
    failed live call, which the caller now detects and reports for retry.
    """
    for chunk in chunks:
        chunk.summary = "live summary"
    return BatchCosts()


def _stub_live(summarizer, succeed=True):
    """Replace the live-summarization fallback with a free stub."""
    side_effect = _summarize_live_stub if succeed else (lambda chunks: BatchCosts())  # noqa: ARG005
    summarizer._summarize_live = MagicMock(side_effect=side_effect)
    return summarizer._summarize_live


def _response(payload=None, prompt_tokens=100, completion_tokens=20):
    return LLMResponse(
        response_id=None,
        answer_text=json.dumps(payload or _summary_payload()),
        confidence_score=0.8,
        token_count=prompt_tokens + completion_tokens,
        latency_ms=0,
        provider="grok",
        model_version="grok-4.3",
        citations_included=False,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        structured_output=payload or _summary_payload(),
    )


@pytest.fixture
def summarizer_factory(tmp_path):
    """Build a BatchSummarizer with a fake backend and stubbed provider."""

    def _make(results_per_batch, parse_side_effect=None, poll_status="ended"):
        backend = FakeBackend(results_per_batch, poll_status=poll_status)
        provider = MagicMock()
        provider.build_batch_request.side_effect = lambda req, cid: {"custom_id": cid}  # noqa: ARG005
        provider.parse_batch_result.side_effect = parse_side_effect or (
            lambda raw: _response()  # noqa: ARG005 - canned response per item
        )

        with (
            patch("src.services.llm.batch.backends.resolve_backend", return_value=backend),
            patch("src.services.llm.factory.LLMProviderFactory.create", return_value=provider),
            patch("src.services.rag.summarizer_batch.ChunkSummarizer") as summarizer_cls,
        ):
            summarizer_cls.return_value.build_request.return_value = MagicMock()
            # BatchSummarizer reuses the ChunkSummarizer's own client rather than
            # building a second one for the same model, so the stub has to live here.
            summarizer_cls.return_value.provider = provider
            # Use the real apply_summaries so summaries actually land on chunks
            from src.services.rag.summarizer import ChunkSummarizer as RealSummarizer

            summarizer_cls.return_value.apply_summaries = RealSummarizer.apply_summaries

            state = IngestionState(path=tmp_path / "state.json")
            batch_summarizer = BatchSummarizer(state=state)

        return batch_summarizer, backend, provider, state

    return _make


def test_successful_batch_applies_summaries(summarizer_factory):
    doc = _doc()
    cid = safe_custom_id("sum__team/a.md")
    summarizer, backend, _provider, state = summarizer_factory(
        [{cid: {"custom_id": cid, "response": {}}}]
    )

    prepared, costs = summarizer.run([doc])

    assert list(prepared) == ["team/a.md"]
    assert [c.summary for c in prepared["team/a.md"]] == ["summary 1", "summary 2"]
    assert costs.cost_usd > 0
    assert costs.batch_savings_usd > 0  # xAI batch discount applied


def test_batch_state_survives_until_the_caller_has_ingested(summarizer_factory):
    """run() must not clear the resume record — the summaries are not durable yet.

    They only become durable once the caller has embedded and upserted them.
    Clearing here meant a failure during embedding discarded an already-paid batch,
    with --batch-collect then reporting no in-flight run at all.
    """
    doc = _doc()
    cid = safe_custom_id("sum__team/a.md")
    summarizer, _backend, _provider, state = summarizer_factory(
        [{cid: {"custom_id": cid, "response": {}}}]
    )

    summarizer.run([doc])

    assert state.batch is not None
    assert state.batch["batch_ids"] == ["batch-1"]


def test_one_batch_line_per_file_with_ingestion_label(summarizer_factory):
    """All files go out in a single batch, one line each, under an ingestion label."""
    docs = [_doc("team/a.md"), _doc("team/b.md"), _doc("core.md")]
    summarizer, backend, _p, _s = summarizer_factory([{}])
    _stub_live(summarizer)

    summarizer.run(docs)

    assert len(backend.submitted[0]) == 3
    assert backend.labels[0] == "kt-rules-ingestion"
    assert {line["custom_id"] for line in backend.submitted[0]} == {
        safe_custom_id("sum__team/a.md"),
        safe_custom_id("sum__team/b.md"),
        safe_custom_id("sum__core.md"),
    }


def test_state_is_saved_before_waiting(summarizer_factory, tmp_path):
    """Interrupting the wait must leave a resumable batch id on disk.

    True of the retry batches too, not just the first: each is separately billable,
    so one that is submitted and then interrupted before being recorded is paid for
    and unreachable, and --batch-collect would resubmit yet again.
    """
    doc = _doc()
    seen_before_each_wait = []

    summarizer, backend, _p, _state = summarizer_factory([{}])
    _stub_live(summarizer)
    original_poll = backend.poll

    def capture_then_poll(batch_id):
        on_disk = json.loads((tmp_path / "state.json").read_text())["batch"]
        seen_before_each_wait.append(on_disk)
        return original_poll(batch_id)

    backend.poll = capture_then_poll
    summarizer.run([doc])

    first = seen_before_each_wait[0]
    assert first["batch_ids"] == ["batch-1"]
    assert first["backend"] == "x"
    assert first["model"] == summarizer.model
    assert first["requests"][0]["relative_path"] == "team/a.md"
    assert first["requests"][0]["file_hash"] == doc.hash

    # Every batch this run submitted was on disk before its own wait began
    for index, on_disk in enumerate(seen_before_each_wait, start=1):
        assert on_disk["batch_ids"] == [f"batch-{n}" for n in range(1, index + 1)]


def test_transient_failure_is_retried_in_a_fresh_batch(summarizer_factory):
    doc = _doc()
    cid = safe_custom_id("sum__team/a.md")
    summarizer, backend, _p, _s = summarizer_factory(
        [
            {cid: {"custom_id": cid, "response": None, "error": "rate limit exceeded"}},
            {cid: {"custom_id": cid, "response": {}}},  # retry succeeds
        ]
    )

    prepared, _costs = summarizer.run([doc])

    assert len(backend.submitted) == 2
    assert backend.labels[1] == "kt-rules-ingestion-retry"
    assert [c.summary for c in prepared["team/a.md"]] == ["summary 1", "summary 2"]


def test_permanent_failure_falls_back_to_live_summarization(summarizer_factory):
    doc = _doc()
    cid = safe_custom_id("sum__team/a.md")
    summarizer, backend, _p, _s = summarizer_factory(
        [{cid: {"custom_id": cid, "response": None, "error": "invalid_request: bad schema"}}]
    )
    _stub_live(summarizer)

    prepared, _costs = summarizer.run([doc])

    # No retry for a permanent error, and the file still gets summarized
    assert len(backend.submitted) == 1
    summarizer._summarize_live.assert_called_once()
    assert "team/a.md" in prepared


def test_missing_result_item_is_treated_as_transient(summarizer_factory):
    doc = _doc()
    summarizer, backend, _p, _s = summarizer_factory([{}, {}])
    _stub_live(summarizer)

    summarizer.run([doc])

    assert len(backend.submitted) > 1  # it was re-requested


def test_file_changed_after_submission_is_not_applied(summarizer_factory):
    """Summaries must never be attached to chunks of a different file version."""
    doc = _doc()
    cid = safe_custom_id("sum__team/a.md")
    summarizer, _backend, _p, state = summarizer_factory(
        [{cid: {"custom_id": cid, "response": {}}}]
    )
    _stub_live(summarizer)

    # Pretend the batch was built from different bytes than the document we hold
    state.batch = {
        "backend": "x",
        "batch_id": "batch-1",
        "requests": [
            {
                "custom_id": cid,
                "relative_path": "team/a.md",
                "file_hash": "a-different-hash",
                "status": "pending",
                "attempts": 0,
            }
        ],
    }

    summarizer.resume([doc])

    # Permanent (not retried), and resolved by a live call instead
    summarizer._summarize_live.assert_called_once()


@pytest.mark.parametrize("terminal_status", ["expired", "failed"])
def test_dead_batch_states_stop_the_wait(summarizer_factory, terminal_status):
    """'expired'/'failed' are terminal — polling one to the 24h cap is dead time.

    The OpenAI-compatible, Mistral and Gemini backends all report "expired"; only
    Grok (today's default summary model) never does.
    """
    doc = _doc()
    cid = safe_custom_id("sum__team/a.md")
    summarizer, backend, _p, _s = summarizer_factory(
        [{cid: {"custom_id": cid, "response": {}}}], poll_status=terminal_status
    )
    _stub_live(summarizer)

    prepared, _costs = summarizer.run([doc])

    # One poll per submitted batch, not a spin until the wait cap
    assert backend.poll_calls == len(backend.submitted)
    # Whatever did complete is still salvaged
    assert "team/a.md" in prepared


def test_incomplete_summaries_are_not_accepted_as_success(summarizer_factory):
    """A short (truncated) response parses fine but leaves later chunks blank.

    Treating "parsed without raising" as success recorded a half-summarized file as
    cleanly ingested, and incremental runs never revisit it.
    """
    doc = _doc()
    cid = safe_custom_id("sum__team/a.md")
    summarizer, backend, _p, _s = summarizer_factory(
        # Two chunks in the document, one summary in the response
        [{cid: {"custom_id": cid, "response": {}}}] * 3,
        parse_side_effect=lambda raw: _response(_summary_payload(count=1)),  # noqa: ARG005
    )
    live = _stub_live(summarizer)

    prepared, _costs = summarizer.run([doc])

    assert len(backend.submitted) > 1  # re-requested rather than accepted
    live.assert_called_once()  # then resolved live
    assert all(c.summary for c in prepared["team/a.md"])


def test_failed_live_fallback_leaves_chunks_unsummarized_for_the_ingestor(summarizer_factory):
    """When the live fallback fails too, the blanks must reach the ingestor.

    They are handed over so the text is still indexed; RAGIngestor.ingest() detects
    the blank summaries and reports the path, which keeps the CLI from recording it.
    """
    doc = _doc()
    cid = safe_custom_id("sum__team/a.md")
    summarizer, _backend, _p, _s = summarizer_factory(
        [{cid: {"custom_id": cid, "response": None, "error": "invalid_request: bad schema"}}]
    )
    _stub_live(summarizer, succeed=False)

    prepared, _costs = summarizer.run([doc])

    assert "team/a.md" in prepared
    assert [c.summary for c in prepared["team/a.md"]] == ["", ""]


def test_resume_refuses_a_batch_submitted_with_a_different_model(summarizer_factory):
    """Summaries came from the model recorded at submit time.

    Resuming under a different one polled another provider's batch id against the
    wrong API, and would have mixed two models' summaries in one collection.
    """
    doc = _doc()
    cid = safe_custom_id("sum__team/a.md")
    summarizer, backend, _p, state = summarizer_factory(
        [{cid: {"custom_id": cid, "response": {}}}]
    )
    state.batch = {
        "backend": "x",
        "batch_ids": ["batch-1"],
        "model": "some-other-model",
        "requests": [{"custom_id": cid, "relative_path": "team/a.md", "file_hash": doc.hash}],
    }

    prepared, costs = summarizer.resume([doc])

    assert prepared == {}
    assert costs.cost_usd == 0.0
    assert backend.poll_calls == 0  # never polled the wrong provider


def test_resume_reads_the_legacy_single_batch_id(summarizer_factory):
    """State written before batch_ids existed must still resume, not strand a batch."""
    doc = _doc()
    cid = safe_custom_id("sum__team/a.md")
    summarizer, _backend, _p, state = summarizer_factory(
        [{cid: {"custom_id": cid, "response": {}}}]
    )
    state.batch = {
        "backend": "x",
        "batch_id": "batch-1",
        "requests": [{"custom_id": cid, "relative_path": "team/a.md", "file_hash": doc.hash}],
    }

    prepared, _costs = summarizer.resume([doc])

    assert [c.summary for c in prepared["team/a.md"]] == ["summary 1", "summary 2"]


def test_summaries_disabled_degrades_instead_of_crashing(tmp_path):
    """With SUMMARY_ENABLED=False, ChunkSummarizer returns a half-built instance.

    Constructing and calling it anyway raised AttributeError on summary_prompt and
    aborted the whole ingest — after the collection had already been reset.
    """
    with patch("src.services.rag.summarizer_batch.SUMMARY_ENABLED", False):
        summarizer = BatchSummarizer(state=IngestionState(path=tmp_path / "s.json"))
        prepared, costs = summarizer.run([_doc()])

    assert prepared == {}
    assert costs.cost_usd == 0.0


def test_no_batch_backend_falls_back_to_live_path(tmp_path):
    """A summary model without a Batch API must degrade, not fail."""
    with (
        patch("src.services.llm.batch.backends.resolve_backend", return_value=None),
        patch("src.services.llm.factory.LLMProviderFactory.create", return_value=MagicMock()),
        patch("src.services.rag.summarizer_batch.ChunkSummarizer"),
    ):
        summarizer = BatchSummarizer(state=IngestionState(path=tmp_path / "s.json"))
        prepared, costs = summarizer.run([_doc()])

    # No prepared chunks means the ingestor summarizes normally
    assert prepared == {}
    assert costs.cost_usd == 0.0
