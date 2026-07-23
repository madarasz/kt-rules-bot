"""Chunk summarization through a provider Batch API.

Summarization is the only LLM cost in ingestion, and it is not latency-sensitive:
nothing downstream needs the summaries until the upsert, and embeddings are built
from `chunk.text` alone. That makes it a good fit for the Batch APIs, which trade
turnaround time (<=24h, typically minutes) for a per-token discount.

One batch request per markdown file, matching the live path's granularity
(`ChunkSummarizer.generate_summaries` summarizes a whole file in one call). The
prompt is built by `ChunkSummarizer.build_request`, so batch and live summaries
are interchangeable.

State lives under the `"batch"` key of data/ingestion_state.json, so a run
interrupted mid-wait resumes with `ingest --batch-collect` instead of paying for
the same batch twice.
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.lib.constants import (
    INGEST_BATCH_MAX_WAIT,
    INGEST_BATCH_POLL_INTERVAL,
    INGEST_MAX_BATCH_ITEM_RETRIES,
    SUMMARY_ENABLED,
    SUMMARY_LLM_MODEL,
)
from src.lib.logging import get_logger
from src.lib.pricing import calculate_llm_cost
from src.models.rule_document import RuleDocument
from src.services.llm.batch.custom_id import safe_custom_id
from src.services.llm.batch.errors import CLASS_TRANSIENT, classify_batch_error, extract_item_error
from src.services.llm.schemas import ChunkSummaries
from src.services.rag.chunker import MarkdownChunk, MarkdownChunker
from src.services.rag.ingestion_state import IngestionState
from src.services.rag.ingestor import RAGIngestor
from src.services.rag.summarizer import ChunkSummarizer, summaries_complete

logger = get_logger(__name__)

BATCH_LABEL = "kt-rules-ingestion"

# Every state a backend's poll() can report that means "stop waiting". Backends
# normalize to these; "expired" and "failed" are dead ends, not slow successes.
TERMINAL_BATCH_STATES = frozenset({"ended", "failed", "expired"})


@dataclass
class BatchCosts:
    """Cost of a batch summarization round, in USD."""

    cost_usd: float = 0.0  # What was actually charged (post-discount)
    cache_savings_usd: float = 0.0  # Saved by prompt caching
    batch_savings_usd: float = 0.0  # Saved by the batch discount vs. live pricing

    def add(self, other: "BatchCosts") -> None:
        self.cost_usd += other.cost_usd
        self.cache_savings_usd += other.cache_savings_usd
        self.batch_savings_usd += other.batch_savings_usd


@dataclass
class _Request:
    """One file's in-flight batch item."""

    custom_id: str
    relative_path: str
    file_hash: str
    status: str = "pending"  # pending | succeeded | failed_retryable | failed_permanent
    attempts: int = 0
    error: str | None = None
    error_class: str | None = None

    def to_dict(self) -> dict:
        return {
            "custom_id": self.custom_id,
            "relative_path": self.relative_path,
            "file_hash": self.file_hash,
            "status": self.status,
            "attempts": self.attempts,
            "error": self.error,
            "error_class": self.error_class,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "_Request":
        return cls(**{k: data.get(k) for k in cls.__dataclass_fields__ if k in data})


@dataclass
class BatchSummarizer:
    """Summarize many files in one provider batch, then apply the results."""

    state: IngestionState
    chunker: MarkdownChunker = field(default_factory=MarkdownChunker)

    def __post_init__(self) -> None:
        from src.services.llm.batch.backends import resolve_backend

        self.model = SUMMARY_LLM_MODEL
        self.summarizer: ChunkSummarizer | None = None
        self.provider = None
        self.backend = None

        # Mirror RAGIngestor's gate. Without it, a disabled summarizer still gets
        # constructed and called: ChunkSummarizer.__init__ returns early, and
        # build_request() would then send an empty prompt to a live batch.
        if not SUMMARY_ENABLED:
            logger.info("batch_summarization_disabled", reason="SUMMARY_ENABLED=False")
            return

        self.summarizer = ChunkSummarizer()
        # Reuse the summarizer's own client rather than building a second one for
        # the same model — they must agree on which provider built the request.
        self.provider = self.summarizer.provider
        if self.provider is None:
            logger.warning("batch_summarization_no_provider", model=self.model)
            return

        self.backend = resolve_backend(self.model)

    # ------------------------------------------------------------------ public

    def run(
        self, documents: list[RuleDocument]
    ) -> tuple[dict[str, list[MarkdownChunk]], BatchCosts]:
        """Submit, wait, and collect. Returns {relative_path: summarized chunks}.

        Falls back to live summarization (returning no prepared chunks, so the
        ingestor summarizes normally) when the summary model has no batch backend.
        """
        if self.backend is None or self.provider is None:
            logger.warning(
                "batch_summarization_unavailable",
                model=self.model,
                reason=self._unavailable_reason(),
            )
            print(f"⚠️  Batch summarization unavailable ({self._unavailable_reason()})")
            print("   Falling back to live summaries.")
            return {}, BatchCosts()

        chunks_by_path = self._chunk_documents(documents)
        lines, requests = self._build_lines(documents, chunks_by_path)

        if not lines:
            return {}, BatchCosts()

        batch_id = self.backend.submit(lines, label=BATCH_LABEL)
        # Print before persisting: the submission is already billable, so the id must
        # reach the operator even if writing the state file is what fails.
        print(f"📤 Submitted batch {batch_id} ({len(lines)} files) via {self.backend.name}")
        self._save_batch_state([batch_id], requests)

        return self._wait_and_collect([batch_id], requests, documents, chunks_by_path)

    def resume(
        self, documents: list[RuleDocument]
    ) -> tuple[dict[str, list[MarkdownChunk]], BatchCosts]:
        """Continue an already-submitted batch recorded in the state file."""
        batch_state = self.state.batch or {}
        batch_ids = self._stored_batch_ids(batch_state)
        if not batch_ids or self.backend is None or self.provider is None:
            print("❌ Stored batch state is unusable (no batch id or no backend).")
            return {}, BatchCosts()

        # The results were produced by the model recorded at submit time. Summarizing
        # half a corpus with one model and half with another is not a state we can
        # detect later, so refuse rather than silently mix — and never poll one
        # provider's batch id against another provider's API.
        stored_model = batch_state.get("model")
        if stored_model and stored_model != self.model:
            print(
                f"❌ Batch was submitted with SUMMARY_LLM_MODEL={stored_model!r}, "
                f"but it is now {self.model!r}."
            )
            print(f"   Restore {stored_model!r} to collect it, or discard with --force.")
            return {}, BatchCosts()

        stored_backend = batch_state.get("backend")
        if stored_backend and stored_backend != self.backend.name:
            from src.services.llm.batch.backends import make_backend

            backend = make_backend(stored_backend)
            if backend is None:
                print(f"❌ No batch backend named {stored_backend!r} for the stored batch.")
                return {}, BatchCosts()
            self.backend = backend

        requests = [_Request.from_dict(r) for r in batch_state.get("requests", [])]
        chunks_by_path = self._chunk_documents(documents)
        print(f"📥 Resuming batch {', '.join(batch_ids)} ({len(requests)} files)")

        return self._wait_and_collect(batch_ids, requests, documents, chunks_by_path)

    def _unavailable_reason(self) -> str:
        if not SUMMARY_ENABLED:
            return "SUMMARY_ENABLED=False"
        if self.provider is None:
            return f"no LLM provider for {self.model}"
        return f"{self.model} has no Batch API backend"

    @staticmethod
    def _stored_batch_ids(batch_state: dict) -> list[str]:
        """Every batch id belonging to this run, oldest first.

        A run can own more than one: each transient-failure retry submits a fresh
        batch. `batch_id` is the pre-list layout, still read so a state file written
        by an older version resumes instead of stranding a paid-for batch.
        """
        ids = batch_state.get("batch_ids")
        if ids:
            return list(ids)
        single = batch_state.get("batch_id")
        return [single] if single else []

    # ----------------------------------------------------------------- internal

    def _chunk_documents(
        self, documents: list[RuleDocument]
    ) -> dict[str, list[MarkdownChunk]]:
        """Chunk every document with deterministic ids.

        Chunking is a pure function of the file content, so doing it again on the
        resume path reproduces exactly the chunks the batch was built from — as
        long as the file has not changed, which `_apply_results` verifies.
        """
        result: dict[str, list[MarkdownChunk]] = {}
        for document in documents:
            chunks = self.chunker.chunk(document.content)
            RAGIngestor.assign_chunk_ids(document, chunks)
            result[document.relative_path or document.filename] = chunks
        return result

    def _build_lines(
        self,
        documents: list[RuleDocument],
        chunks_by_path: dict[str, list[MarkdownChunk]],
        only_paths: set[str] | None = None,
    ) -> tuple[list[dict], list[_Request]]:
        """Build provider batch lines (and their tracking rows) for the documents."""
        lines: list[dict] = []
        requests: list[_Request] = []

        for document in documents:
            rel_path = document.relative_path or document.filename
            if only_paths is not None and rel_path not in only_paths:
                continue
            chunks = chunks_by_path.get(rel_path) or []
            if not chunks:
                continue

            custom_id = safe_custom_id(f"sum__{rel_path}")
            request = self.summarizer.build_request(chunks)
            lines.append(self.provider.build_batch_request(request, custom_id))
            requests.append(
                _Request(
                    custom_id=custom_id,
                    relative_path=rel_path,
                    file_hash=document.hash,
                )
            )
        return lines, requests

    def _save_batch_state(self, batch_ids: list[str], requests: list[_Request]) -> None:
        self.state.batch = {
            "backend": self.backend.name,
            "batch_ids": list(batch_ids),
            "model": self.model,
            "submitted_at": datetime.now(UTC).isoformat(),
            "requests": [r.to_dict() for r in requests],
        }
        self.state.save()

    def _wait_and_collect(
        self,
        batch_ids: list[str],
        requests: list[_Request],
        documents: list[RuleDocument],
        chunks_by_path: dict[str, list[MarkdownChunk]],
    ) -> tuple[dict[str, list[MarkdownChunk]], BatchCosts]:
        """Poll to completion, apply results, retry transients, fall back on failures.

        Does not clear `state.batch`: the summaries only become durable once the
        caller has embedded and upserted them, so the caller owns that clearing.
        """
        costs = BatchCosts()
        by_path = {d.relative_path or d.filename: d for d in documents}
        batch_ids = list(batch_ids)

        # Later batches re-use the same custom_ids, so merging in submission order
        # lets a retry result supersede the failure it was submitted to replace.
        items: dict[str, dict] = {}
        for bid in batch_ids:
            self._poll(bid)
            items.update(self.backend.fetch(bid))
        prepared = self._apply_results(items, requests, by_path, chunks_by_path, costs)

        # Bounded retry: transient failures get a fresh (small) batch, which we are
        # already waiting on anyway, so there is no reason to defer it to a later run.
        by_cid = {r.custom_id: r for r in requests}
        for attempt in range(INGEST_MAX_BATCH_ITEM_RETRIES):
            retryable = [r for r in requests if r.status == "failed_retryable"]
            if not retryable:
                break
            paths = {r.relative_path for r in retryable}
            print(f"🔁 Re-requesting {len(paths)} transient failure(s), attempt {attempt + 1}")
            lines, retry_rows = self._build_lines(documents, chunks_by_path, only_paths=paths)
            if not lines:
                break
            for row in retry_rows:
                tracked = by_cid.get(row.custom_id)
                row.attempts = (tracked.attempts + 1) if tracked else 1
            retry_batch_id = self.backend.submit(lines, label=f"{BATCH_LABEL}-retry")
            batch_ids.append(retry_batch_id)
            # Persist before waiting, exactly as the first submission does: this batch
            # is already billable, and an interrupted wait must resume it rather than
            # strand it and pay for a third submission.
            self._save_batch_state(batch_ids, requests)
            self._poll(retry_batch_id)
            retry_items = self.backend.fetch(retry_batch_id)
            prepared.update(
                self._apply_results(retry_items, retry_rows, by_path, chunks_by_path, costs)
            )
            # Fold the retry outcome back into the tracked rows
            for row in retry_rows:
                tracked = by_cid.get(row.custom_id)
                if tracked is not None:
                    tracked.status, tracked.attempts = row.status, row.attempts
                    tracked.error, tracked.error_class = row.error, row.error_class

        # Anything still unresolved gets one live call. If that fails too the chunks
        # come back with blank summaries; they are still handed over so the text is
        # indexed, and RAGIngestor.ingest() detects the blanks and reports the path in
        # summary_failed_paths, which keeps the CLI from recording it as clean.
        for row in requests:
            if row.status == "succeeded" or row.relative_path in prepared:
                continue
            chunks = chunks_by_path.get(row.relative_path)
            if not chunks:
                continue
            print(f"↩️  {row.relative_path}: batch failed ({row.error}) — summarizing live")
            live_cost = self._summarize_live(chunks)
            costs.add(live_cost)
            if not summaries_complete(chunks):
                print(f"⚠️  {row.relative_path}: live summarization also failed — will retry")
                logger.warning("ingest_batch_live_fallback_failed", file=row.relative_path)
            prepared[row.relative_path] = chunks

        return prepared, costs

    def _poll(self, batch_id: str) -> None:
        """Block until the batch reaches a terminal state (or the wait cap is hit).

        "expired" is terminal too — the OpenAI-compatible, Mistral and Gemini
        backends report it for a batch the provider gave up on. Waiting on one is
        pure dead time; fetch() then returns whatever completed and the missing
        items fall through to retry / live fallback.
        """
        waited = 0
        while waited < INGEST_BATCH_MAX_WAIT:
            status = self.backend.poll(batch_id)
            if status in TERMINAL_BATCH_STATES:
                if status != "ended":
                    # Individual items are still classified below; a whole-batch
                    # failure just means fetch() will surface per-item errors.
                    logger.warning("ingest_batch_terminal", batch_id=batch_id, status=status)
                    print(f"\n⚠️  batch {batch_id} ended as '{status}' — salvaging what completed")
                return
            mins, secs = divmod(waited, 60)
            print(f"   ⏳ batch {batch_id} in progress ({mins}m{secs:02d}s elapsed)", end="\r")
            time.sleep(INGEST_BATCH_POLL_INTERVAL)
            waited += INGEST_BATCH_POLL_INTERVAL

        raise TimeoutError(
            f"Batch {batch_id} did not finish within {INGEST_BATCH_MAX_WAIT}s. "
            f"State is saved — resume with: ingest <source> --batch-collect"
        )

    def _apply_results(
        self,
        items: dict[str, dict],
        requests: list[_Request],
        by_path: dict[str, RuleDocument],
        chunks_by_path: dict[str, list[MarkdownChunk]],
        costs: BatchCosts,
    ) -> dict[str, list[MarkdownChunk]]:
        """Parse each returned item onto its chunks; mark failures for retry/fallback."""
        prepared: dict[str, list[MarkdownChunk]] = {}

        for row in requests:
            item = items.get(row.custom_id)
            if item is None:
                row.status = "failed_retryable"
                row.error = "missing from batch results"
                row.error_class = CLASS_TRANSIENT
                continue

            error = extract_item_error(item)
            if error:
                error_class, reason = classify_batch_error(error)
                row.error, row.error_class = error, error_class
                row.status = (
                    "failed_retryable" if error_class == CLASS_TRANSIENT else "failed_permanent"
                )
                logger.warning(
                    "ingest_batch_item_failed",
                    file=row.relative_path,
                    error=error,
                    error_class=error_class,
                    reason=reason,
                )
                continue

            document = by_path.get(row.relative_path)
            chunks = chunks_by_path.get(row.relative_path)
            if document is None or not chunks:
                row.status = "failed_permanent"
                row.error = "file no longer present in this run"
                continue

            # The file must still be the one we summarized, or the summaries would
            # describe text that is no longer in these chunks. Permanent rather than
            # retryable: the returned result can never become valid, and the live
            # fallback resummarizes the current content in one call instead of
            # waiting out another whole batch round-trip.
            if document.hash != row.file_hash:
                row.status = "failed_permanent"
                row.error = "file changed after submission"
                logger.warning("ingest_batch_file_changed", file=row.relative_path)
                continue

            try:
                response = self.provider.parse_batch_result(item)
                data = response.structured_output
                if data is None:
                    data = json.loads(response.answer_text)
                self.summarizer.apply_summaries(chunks, ChunkSummaries.model_validate(data))
            except Exception as e:  # noqa: BLE001 - any parse failure is per-item, not fatal
                error_class, _ = classify_batch_error(str(e))
                row.error, row.error_class = str(e), error_class
                row.status = (
                    "failed_retryable" if error_class == CLASS_TRANSIENT else "failed_permanent"
                )
                logger.warning(
                    "ingest_batch_parse_failed", file=row.relative_path, error=str(e)
                )
                continue

            # A schema-valid response can still be short: ChunkSummaries has no
            # minimum length, and a truncated one covers only the first few chunks.
            # apply_summaries() blanks the rest, so "parsed without raising" is not
            # the same as "summarized". Send it round the retry / live-fallback path
            # rather than recording a half-summarized file as succeeded.
            if not summaries_complete(chunks):
                row.status = "failed_retryable"
                row.error = "incomplete summaries in batch result"
                row.error_class = CLASS_TRANSIENT
                logger.warning(
                    "ingest_batch_summaries_incomplete",
                    file=row.relative_path,
                    with_summary=sum(1 for c in chunks if c.summary),
                    chunk_count=len(chunks),
                )
                continue

            costs.add(
                self._cost_of(
                    response.prompt_tokens,
                    response.completion_tokens,
                    response.cache_read_tokens,
                    response.cache_creation_tokens,
                    response.model_version or self.model,
                )
            )
            row.status = "succeeded"
            prepared[row.relative_path] = chunks

        return prepared

    def _cost_of(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        cache_read_tokens: int,
        cache_creation_tokens: int,
        model: str,
    ) -> BatchCosts:
        """Cost of one batched summarization call, including what batching saved."""
        breakdown = calculate_llm_cost(
            prompt_tokens,
            completion_tokens,
            model,
            cache_read_tokens,
            cache_creation_tokens,
            batch=True,
            batch_backend=self.backend.name,
        )
        return BatchCosts(
            cost_usd=breakdown.total_cost,
            cache_savings_usd=breakdown.cache_savings,
            batch_savings_usd=breakdown.batch_savings,
        )

    def _summarize_live(self, chunks: list[MarkdownChunk]) -> BatchCosts:
        """Last-resort live summarization for a file the batch could not deliver."""
        (
            _chunks,
            prompt_tokens,
            completion_tokens,
            cache_read_tokens,
            cache_creation_tokens,
            model,
        ) = asyncio.run(self.summarizer.generate_summaries(chunks))

        if prompt_tokens <= 0:
            return BatchCosts()

        breakdown = calculate_llm_cost(
            prompt_tokens,
            completion_tokens,
            model,
            cache_read_tokens,
            cache_creation_tokens,
        )
        return BatchCosts(
            cost_usd=breakdown.total_cost,
            cache_savings_usd=breakdown.cache_savings,
        )
