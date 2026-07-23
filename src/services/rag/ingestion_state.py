"""Persisted ingestion state: what was ingested, from which content, under which config.

Without this, every `ingest` run re-summarizes and re-embeds all files: the
in-memory `RAGIngestor.document_hashes` starts empty on each process, so the
"unchanged, skipping" branch in the CLI could never fire.

The file also carries a *fingerprint* of the settings that determine chunk
boundaries and embeddings. When any of those change, per-file hashes are
meaningless (the same bytes would now produce different chunks), so the caller
does a full rebuild instead of an incremental pass.

Layout (data/ingestion_state.json):

    {
      "version": 1,
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
        except FileNotFoundError:
            # Prompt file missing is the summarizer's problem to report, not ours;
            # an empty sha just means "unknown", which mismatches once it appears.
            logger.warning("summary_prompt_missing_for_fingerprint")

    return {
        "state_version": STATE_VERSION,
        "chunk_level": MARKDOWN_CHUNK_HEADER_LEVEL,
        "embedding_model": EMBEDDING_MODEL,
        "summary_enabled": SUMMARY_ENABLED,
        "summary_model": SUMMARY_LLM_MODEL if SUMMARY_ENABLED else "",
        "summary_prompt_sha256": summary_prompt_sha,
    }


def file_hash(content: str) -> str:
    """SHA-256 of a markdown file's content (same rule as RuleDocument.compute_hash)."""
    return hashlib.sha256(content.encode()).hexdigest()


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
    fingerprint: dict[str, object] = field(default_factory=dict)
    files: dict[str, dict] = field(default_factory=dict)
    batch: dict | None = None

    @classmethod
    def load(cls, path: str | Path = INGEST_STATE_PATH) -> "IngestionState":
        """Load state, or return an empty one if absent/unreadable.

        A corrupt state file is not fatal: an empty state means "rebuild
        everything", which is always safe.
        """
        p = Path(path)
        if not p.exists():
            return cls(path=p)
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("ingestion_state_unreadable", path=str(p), error=str(e))
            return cls(path=p)

        return cls(
            path=p,
            fingerprint=data.get("fingerprint", {}),
            files=data.get("files", {}),
            batch=data.get("batch"),
        )

    def save(self) -> None:
        """Write state atomically, so a crash mid-write cannot corrupt it."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": STATE_VERSION,
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

    def classify(self, md_files: list[Path], source_dir: Path) -> FileChanges:
        """Split the source tree into new / changed / unchanged, plus removed entries.

        Reads each file to hash it — cheap next to embedding and summarizing, and
        it means an mtime-only touch does not trigger reprocessing.
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

    def reset_for_rebuild(self) -> None:
        """Clear per-file state and stamp the current fingerprint (full rebuild)."""
        self.files = {}
        self.batch = None
        self.fingerprint = current_fingerprint()
