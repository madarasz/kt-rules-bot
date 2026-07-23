"""Persisted ingestion state: what was ingested, from which content, under which config.

Without this, every `ingest` run re-summarizes and re-embeds all files: the
previous in-memory hash map started empty on each process, so the "unchanged,
skipping" branch in the CLI could never fire.

The file also carries a *fingerprint* of the settings that determine chunk
boundaries and embeddings. When any of those change, per-file hashes are
meaningless (the same bytes would now produce different chunks), so the caller
does a full rebuild instead of an incremental pass.

Layout (data/ingestion_state.json):

    {
      "version": 1,
      "source_dir": "/abs/path/to/extracted-rules",   # tree the file keys are relative to
      "fingerprint": {...},
      "files": {"<relative path>": {"hash", "document_id", "chunks", "ingested_at"}},
      "batch": null | {...}          # in-flight batch summarization, see summarizer_batch
    }
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from src.lib.constants import (
    EMBEDDING_MODEL,
    INGEST_STATE_PATH,
    MARKDOWN_CHUNK_HEADER_LEVEL,
    SUMMARY_ENABLED,
    SUMMARY_LLM_MODEL,
)
from src.lib.logging import get_logger
from src.models.rule_document import RuleDocument

logger = get_logger(__name__)

STATE_VERSION = 1


def current_fingerprint() -> dict[str, object]:
    """Settings that invalidate every stored file hash when changed.

    Chunk level and embedding model change what is stored per file; summary model
    and prompt change the metadata attached to it. A mismatch means the vector
    store no longer corresponds to these settings and must be rebuilt.
    """
    summary_prompt_sha = ""
    if SUMMARY_ENABLED:
        try:
            from src.services.rag.summarizer import load_summary_prompt

            summary_prompt_sha = hashlib.sha256(
                load_summary_prompt().encode("utf-8")
            ).hexdigest()
        except OSError:
            # Any read failure (missing, unreadable, bad permissions) is the
            # summarizer's problem to report, not ours; an empty sha just means
            # "unknown", which mismatches once the prompt becomes readable again.
            # Catching OSError rather than FileNotFoundError keeps a permissions
            # blip from aborting the whole ingest with an opaque traceback.
            logger.warning("summary_prompt_unreadable_for_fingerprint")

    return {
        "state_version": STATE_VERSION,
        "chunk_level": MARKDOWN_CHUNK_HEADER_LEVEL,
        "embedding_model": EMBEDDING_MODEL,
        "summary_enabled": SUMMARY_ENABLED,
        "summary_model": SUMMARY_LLM_MODEL if SUMMARY_ENABLED else "",
        "summary_prompt_sha256": summary_prompt_sha,
    }


def file_hash(content: str) -> str:
    """SHA-256 of a markdown file's content.

    Delegates rather than reimplements: `classify()` compares this against
    `document.hash`, which `state.record()` stores from `RuleDocument.compute_hash`.
    Two independent implementations that must stay byte-identical would, on the
    smallest divergence, either re-ingest every file every run or (worse) classify
    changed files as unchanged, with nothing to signal it.
    """
    return RuleDocument.compute_hash(content)


@dataclass
class FileChanges:
    """Classification of the source tree against stored state."""

    new: list[Path] = field(default_factory=list)
    changed: list[Path] = field(default_factory=list)
    unchanged: list[Path] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)  # relative paths, gone from disk

    @property
    def to_ingest(self) -> list[Path]:
        return self.new + self.changed


@dataclass
class IngestionState:
    """Read/write wrapper around data/ingestion_state.json."""

    path: Path
    source_dir: str = ""  # absolute source tree the `files` keys are relative to
    fingerprint: dict[str, object] = field(default_factory=dict)
    files: dict[str, dict] = field(default_factory=dict)
    batch: dict | None = None

    @classmethod
    def load(cls, path: str | Path = INGEST_STATE_PATH) -> "IngestionState":
        """Load state, or return an empty one if the file is absent or corrupt.

        Corrupt *content* is not fatal: an empty state means "rebuild
        everything", which is always safe. An OSError on a file that
        `exists()` just confirmed is a different matter — a permissions or I/O
        problem, not a config change — and is re-raised rather than silently
        authorizing a destructive full rebuild.
        """
        p = Path(path)
        if not p.exists():
            return cls(path=p)
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            logger.warning("ingestion_state_corrupt", path=str(p), error=str(e))
            return cls(path=p)

        return cls(
            path=p,
            source_dir=data.get("source_dir", ""),
            fingerprint=data.get("fingerprint", {}),
            files=data.get("files", {}),
            batch=data.get("batch"),
        )

    def save(self) -> None:
        """Write state atomically, so a crash mid-write cannot corrupt it."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": STATE_VERSION,
            "source_dir": self.source_dir,
            "fingerprint": self.fingerprint,
            "files": self.files,
            "batch": self.batch,
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def is_stale(self) -> bool:
        """True when stored per-file hashes cannot be trusted (config changed / no state)."""
        return self.fingerprint != current_fingerprint()

    @staticmethod
    def normalize_source_dir(source_dir: Path) -> str:
        """Canonical form of a source tree, for comparing runs against each other."""
        return str(Path(source_dir).resolve())

    def matches_source_dir(self, source_dir: Path) -> bool:
        """True when this state describes the given tree (or predates the field).

        The `files` keys are relative to whichever directory was ingested. Comparing
        them against a *different* tree makes every absent key look like a deleted
        file, so `classify()` must only ever run against the tree that produced them.
        """
        if not self.source_dir:
            return True  # written before source_dir was tracked; assume the same tree
        return self.source_dir == self.normalize_source_dir(source_dir)

    def classify(self, md_files: list[Path], source_dir: Path) -> FileChanges:
        """Split the source tree into new / changed / unchanged, plus removed entries.

        Reads each file to hash it — cheap next to embedding and summarizing, and
        it means an mtime-only touch does not trigger reprocessing.

        Only valid for the tree this state was built from: `removed` is derived by
        subtraction, so running it against a subdirectory would report every file
        outside that subdirectory as deleted. Callers must check
        `matches_source_dir()` first.
        """
        changes = FileChanges()
        seen: set[str] = set()

        for md_file in md_files:
            rel = md_file.relative_to(source_dir).as_posix()
            seen.add(rel)
            entry = self.files.get(rel)
            if entry is None:
                changes.new.append(md_file)
                continue
            try:
                content = md_file.read_text(encoding="utf-8")
            except OSError as e:
                logger.warning("ingestion_state_read_failed", file=rel, error=str(e))
                changes.changed.append(md_file)
                continue
            if entry.get("hash") == file_hash(content):
                changes.unchanged.append(md_file)
            else:
                changes.changed.append(md_file)

        changes.removed = sorted(set(self.files) - seen)
        return changes

    def record(self, relative_path: str, content_hash: str, document_id: str, chunks: int) -> None:
        """Mark one file as successfully ingested."""
        self.files[relative_path] = {
            "hash": content_hash,
            "document_id": document_id,
            "chunks": chunks,
            "ingested_at": datetime.now(UTC).isoformat(),
        }

    def forget(self, relative_path: str) -> None:
        """Drop a file's entry (it was deleted from the source tree)."""
        self.files.pop(relative_path, None)

    def document_id_for(self, relative_path: str) -> str | None:
        """The document id previously stored for a path, if any."""
        entry = self.files.get(relative_path)
        return entry.get("document_id") if entry else None

    def reset_for_rebuild(self, source_dir: Path) -> None:
        """Clear per-file state and stamp the current fingerprint (full rebuild).

        The caller must `save()` this *before* resetting the vector store: until it
        is on disk, a crash leaves a state file claiming every file is ingested
        while the collection is being emptied.
        """
        self.files = {}
        self.batch = None
        self.source_dir = self.normalize_source_dir(source_dir)
        self.fingerprint = current_fingerprint()
