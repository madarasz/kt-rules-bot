"""Unit tests for the `ingest` CLI orchestration.

These cover the parts that live in src/cli/ingest_rules.py rather than in the
services: when the collection is reset relative to when the state file is
written, which failures abort a run, and what --batch-collect refuses to resume.
Every one of them is a data-loss or double-billing path, and none of them are
reachable from the service-level tests.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.cli.ingest_rules import ingest_rules
from src.services.rag.ingestion_state import IngestionState, current_fingerprint, file_hash
from src.services.rag.ingestor import IngestionResult

MD = (
    "---\nsource: X\nlast_update_date: 2025-01-01\ndocument_type: core-rules\n---\n\n"
    "## Alpha\nalpha body\n\n## Beta\nbeta body\n"
)
STATE_PATH = Path("data/ingestion_state.json")


@pytest.fixture
def source_tree(tmp_path, monkeypatch):
    """A source directory, with cwd moved so data/ingestion_state.json is local."""
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "rules"
    (src / "team").mkdir(parents=True)
    (src / "core.md").write_text(MD, encoding="utf-8")
    (src / "team" / "kommandos.md").write_text(MD, encoding="utf-8")
    return src


def _ok_result(chunks=2):
    return IngestionResult(
        job_id=None,
        documents_processed=1,
        documents_failed=0,
        embedding_count=chunks,
        errors=[],
        warnings=[],
        duration_seconds=0.0,
    )


@pytest.fixture
def services():
    """Patch out every external service the CLI builds; yield the mocks."""
    vector_db = MagicMock()
    ingestor = MagicMock()
    ingestor.ingest.return_value = _ok_result()
    ingestor.delete_document.return_value = 3

    with (
        patch("src.cli.ingest_rules.get_config"),
        patch("src.cli.ingest_rules.VectorDBService", return_value=vector_db),
        patch("src.cli.ingest_rules.EmbeddingService"),
        patch("src.cli.ingest_rules.RAGIngestor", return_value=ingestor),
    ):
        yield vector_db, ingestor


def _write_state(source_tree, files=None):
    """A state file that looks like a clean previous ingest of `source_tree`."""
    state = IngestionState(path=STATE_PATH)
    state.reset_for_rebuild(source_tree)
    for rel in files or ["core.md", "team/kommandos.md"]:
        state.record(rel, file_hash((source_tree / rel).read_text()), f"id-{rel}", chunks=2)
    state.save()
    return state


def test_force_persists_the_cleared_state_before_resetting_the_collection(
    source_tree, services
):
    """A crash mid-rebuild must not leave a state file claiming everything is done.

    --force does not change the fingerprint, so if the reset lands but the cleared
    state does not, the next incremental run sees a matching fingerprint and every
    file unchanged — and reports "nothing to ingest" against an empty collection.
    """
    vector_db, ingestor = services
    _write_state(source_tree)
    on_disk_at_reset = {}

    def capture(*_args, **_kwargs):
        on_disk_at_reset.update(json.loads(STATE_PATH.read_text()))

    vector_db.reset.side_effect = capture
    # Abort immediately after the reset, before any document can be recorded
    ingestor.ingest.side_effect = RuntimeError("embedding API down")

    ingest_rules(str(source_tree), force=True)

    vector_db.reset.assert_called_once()
    assert on_disk_at_reset["files"] == {}, "state must be cleared before the reset"

    # And the next plain run therefore re-ingests rather than skipping
    reloaded = IngestionState.load(STATE_PATH)
    assert reloaded.files == {}
    changes = reloaded.classify(sorted(source_tree.rglob("*.md")), source_tree)
    assert len(changes.new) == 2


def test_one_document_failing_does_not_abort_the_run(source_tree, services):
    """RAGIngestor raises VectorDBWriteError per document; the rest must still run."""
    _vector_db, ingestor = services
    ingestor.ingest.side_effect = [RuntimeError("chroma write failed"), _ok_result()]

    ingest_rules(str(source_tree), force=True)

    assert ingestor.ingest.call_count == 2
    # The surviving document was still recorded
    assert len(IngestionState.load(STATE_PATH).files) == 1


def test_ingesting_a_subdirectory_is_refused(source_tree, services):
    """`classify` derives "removed" by subtraction, so another tree looks all-deleted.

    Without this guard, `ingest rules/team/` deletes every chunk of every file
    outside team/ from the vector store, silently and with no confirmation.
    """
    _vector_db, ingestor = services
    _write_state(source_tree)

    with pytest.raises(SystemExit):
        ingest_rules(str(source_tree / "team"))

    ingestor.delete_document.assert_not_called()
    assert len(IngestionState.load(STATE_PATH).files) == 2


def test_deleted_source_file_still_has_its_chunks_removed(source_tree, services):
    """The guard above must not break the legitimate deletion path."""
    _vector_db, ingestor = services
    _write_state(source_tree)
    (source_tree / "core.md").unlink()

    ingest_rules(str(source_tree))

    ingestor.delete_document.assert_called_once_with("id-core.md")
    assert "core.md" not in IngestionState.load(STATE_PATH).files


def test_batch_collect_refuses_after_a_config_change(source_tree, services):
    """Re-chunking under new settings binds each summary to unrelated text.

    The only integrity check in the batch path compares file *content*, which is
    unchanged — so nothing else catches this.
    """
    _vector_db, ingestor = services
    state = _write_state(source_tree)
    state.batch = {
        "backend": "x",
        "batch_ids": ["batch-1"],
        "model": "grok-4.3",
        "requests": [{"custom_id": "c", "relative_path": "core.md", "file_hash": "h"}],
    }
    state.fingerprint = {**current_fingerprint(), "chunk_level": 99}
    state.save()

    with pytest.raises(SystemExit):
        ingest_rules(str(source_tree), batch_collect=True)

    ingestor.ingest.assert_not_called()
    # The batch is preserved, so it can still be collected once the config is restored
    assert IngestionState.load(STATE_PATH).batch is not None


def test_batch_collect_from_the_wrong_directory_keeps_the_batch(source_tree, services):
    """The submission is already paid for; a wrong cwd must not discard it."""
    _vector_db, _ingestor = services
    state = _write_state(source_tree)
    state.batch = {
        "backend": "x",
        "batch_ids": ["batch-1"],
        "model": "grok-4.3",
        "requests": [{"custom_id": "c", "relative_path": "core.md", "file_hash": "h"}],
    }
    state.save()

    elsewhere = source_tree.parent / "other"
    elsewhere.mkdir()

    with pytest.raises(SystemExit):
        ingest_rules(str(elsewhere), batch_collect=True)

    assert IngestionState.load(STATE_PATH).batch is not None


def test_unchanged_files_are_skipped(source_tree, services):
    """The point of the whole state file."""
    _vector_db, ingestor = services
    _write_state(source_tree)

    ingest_rules(str(source_tree))

    ingestor.ingest.assert_not_called()


def test_keyword_library_is_flushed_once_not_per_document(source_tree, services):
    _vector_db, ingestor = services

    ingest_rules(str(source_tree), force=True)

    assert ingestor.ingest.call_count == 2
    assert all(
        call.kwargs["flush_keywords"] is False for call in ingestor.ingest.call_args_list
    )
    ingestor.keyword_extractor.save_keywords.assert_called_once()
