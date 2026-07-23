"""Unit tests for the persisted ingestion state (incremental ingestion)."""

import json

import pytest

from src.services.rag.ingestion_state import IngestionState, current_fingerprint, file_hash

MD = "---\nsource: X\nlast_update_date: 2025-01-01\ndocument_type: core-rules\n---\n\n## A\nbody\n"


@pytest.fixture
def source_tree(tmp_path):
    """A small source directory with a nested subdirectory."""
    (tmp_path / "team").mkdir()
    (tmp_path / "core.md").write_text(MD, encoding="utf-8")
    (tmp_path / "team" / "kommandos.md").write_text(MD, encoding="utf-8")
    return tmp_path


def _files(source_tree):
    return sorted(source_tree.rglob("*.md"))


def test_missing_state_file_is_stale(tmp_path):
    """No state file means nothing can be trusted — caller must rebuild."""
    state = IngestionState.load(tmp_path / "nope.json")
    assert state.is_stale()
    assert state.files == {}


def test_corrupt_state_file_degrades_to_rebuild(tmp_path):
    """A truncated/invalid JSON state must not crash ingestion."""
    path = tmp_path / "state.json"
    path.write_text("{ this is not json", encoding="utf-8")

    state = IngestionState.load(path)

    assert state.files == {}
    assert state.is_stale()


def test_save_load_roundtrip(tmp_path):
    state = IngestionState(path=tmp_path / "state.json")
    state.reset_for_rebuild()
    state.record("team/a.md", "hash-a", "doc-id-a", chunks=3)
    state.save()

    reloaded = IngestionState.load(tmp_path / "state.json")

    assert reloaded.files["team/a.md"]["hash"] == "hash-a"
    assert reloaded.files["team/a.md"]["chunks"] == 3
    assert reloaded.document_id_for("team/a.md") == "doc-id-a"
    assert not reloaded.is_stale()


def test_save_is_atomic_and_leaves_no_temp_file(tmp_path):
    state = IngestionState(path=tmp_path / "state.json")
    state.reset_for_rebuild()
    state.save()

    assert (tmp_path / "state.json").exists()
    assert list(tmp_path.glob("*.tmp")) == []
    assert json.loads((tmp_path / "state.json").read_text())["version"] == 1


def test_classify_detects_new_changed_unchanged_removed(source_tree, tmp_path):
    state = IngestionState(path=tmp_path / "state.json")
    state.reset_for_rebuild()

    # First pass: everything is new
    changes = state.classify(_files(source_tree), source_tree)
    assert len(changes.new) == 2
    assert changes.changed == [] and changes.unchanged == [] and changes.removed == []

    # Record both, plus a file that no longer exists on disk
    for md_file in _files(source_tree):
        rel = md_file.relative_to(source_tree).as_posix()
        state.record(rel, file_hash(md_file.read_text()), f"id-{rel}", chunks=1)
    state.record("gone.md", "old-hash", "id-gone", chunks=5)

    # Second pass: nothing changed, and the vanished file is reported
    changes = state.classify(_files(source_tree), source_tree)
    assert len(changes.unchanged) == 2
    assert changes.new == [] and changes.changed == []
    assert changes.removed == ["gone.md"]

    # Edit one file: only that one is "changed"
    (source_tree / "core.md").write_text(MD + "\n## B\nmore\n", encoding="utf-8")
    changes = state.classify(_files(source_tree), source_tree)
    assert [p.name for p in changes.changed] == ["core.md"]
    assert [p.name for p in changes.unchanged] == ["kommandos.md"]
    assert [p.name for p in changes.to_ingest] == ["core.md"]


def test_classify_ignores_mtime_only_touch(source_tree, tmp_path):
    """Rewriting identical bytes must not trigger reprocessing (hash, not mtime)."""
    state = IngestionState(path=tmp_path / "state.json")
    state.reset_for_rebuild()
    for md_file in _files(source_tree):
        rel = md_file.relative_to(source_tree).as_posix()
        state.record(rel, file_hash(md_file.read_text()), f"id-{rel}", chunks=1)

    (source_tree / "core.md").write_text(MD, encoding="utf-8")  # same content

    changes = state.classify(_files(source_tree), source_tree)
    assert changes.changed == []
    assert len(changes.unchanged) == 2


def test_classify_uses_relative_path_so_basenames_can_repeat(tmp_path):
    """Two files with the same basename in different subdirs are distinct entries."""
    (tmp_path / "team").mkdir()
    (tmp_path / "killzone").mkdir()
    (tmp_path / "team" / "same.md").write_text(MD, encoding="utf-8")
    (tmp_path / "killzone" / "same.md").write_text(MD + "\n## Extra\n", encoding="utf-8")

    state = IngestionState(path=tmp_path / "state.json")
    state.reset_for_rebuild()
    changes = state.classify(sorted(tmp_path.rglob("*.md")), tmp_path)

    assert len(changes.new) == 2
    assert {p.parent.name for p in changes.new} == {"team", "killzone"}


def test_fingerprint_change_makes_state_stale(tmp_path, monkeypatch):
    state = IngestionState(path=tmp_path / "state.json")
    state.reset_for_rebuild()
    assert not state.is_stale()

    monkeypatch.setattr("src.services.rag.ingestion_state.MARKDOWN_CHUNK_HEADER_LEVEL", 4)

    assert state.is_stale()


def test_fingerprint_tracks_summary_settings(monkeypatch):
    """Summary model changes invalidate stored state — summaries live in the store."""
    before = current_fingerprint()
    monkeypatch.setattr("src.services.rag.ingestion_state.SUMMARY_LLM_MODEL", "some-other-model")
    assert current_fingerprint() != before


def test_forget_removes_entry(tmp_path):
    state = IngestionState(path=tmp_path / "state.json")
    state.record("a.md", "h", "id", chunks=1)
    state.forget("a.md")
    assert state.files == {}
    state.forget("a.md")  # idempotent


def test_reset_for_rebuild_clears_files_and_batch(tmp_path):
    state = IngestionState(path=tmp_path / "state.json")
    state.record("a.md", "h", "id", chunks=1)
    state.batch = {"batch_id": "b1"}

    state.reset_for_rebuild()

    assert state.files == {}
    assert state.batch is None
    assert state.fingerprint == current_fingerprint()
