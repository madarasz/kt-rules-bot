"""CLI command to ingest markdown rules into vector database.

Incremental by default: only files whose content hash changed since the last run
are re-summarized, re-embedded and re-written. State lives in
``data/ingestion_state.json`` (see src/services/rag/ingestion_state.py).

Usage:
    python -m src.cli ingest extracted-rules/
    python -m src.cli ingest extracted-rules/ --batch
    python -m src.cli ingest extracted-rules/ --batch-collect
    python -m src.cli ingest extracted-rules/ --force
"""

import sys
from pathlib import Path
from uuid import uuid4

from src.lib.config import get_config
from src.lib.logging import get_logger
from src.models.rule_document import RuleDocument
from src.services.rag.chunker import MarkdownChunk
from src.services.rag.embeddings import EmbeddingService
from src.services.rag.ingestion_state import IngestionState, current_fingerprint
from src.services.rag.ingestor import IngestionResult, RAGIngestor
from src.services.rag.summarizer_batch import BatchCosts, BatchSummarizer
from src.services.rag.validator import DocumentValidator
from src.services.rag.vector_db import VectorDBService

logger = get_logger(__name__)


def find_markdown_files(source_dir: Path) -> list[Path]:
    """Find all markdown files in source directory.

    Args:
        source_dir: Directory to search

    Returns:
        List of markdown file paths
    """
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    md_files = list(source_dir.rglob("*.md"))
    return sorted(md_files)


def _build_document(
    md_file: Path, source_path: Path, validator: DocumentValidator
) -> tuple[RuleDocument | None, str, str]:
    """Read + validate one markdown file into a RuleDocument.

    Returns:
        (document | None, relative_path, error_message)
    """
    relative_path = md_file.relative_to(source_path).as_posix()
    content = md_file.read_text(encoding="utf-8")

    is_valid, error, metadata = validator.validate_content(content, relative_path)
    if not is_valid:
        return None, relative_path, error

    document = RuleDocument.from_markdown_file(
        filename=md_file.name,
        content=content,
        metadata=metadata,
        relative_path=relative_path,
    )
    return document, relative_path, ""


def ingest_rules(
    source_dir: str,
    force: bool = False,
    batch: bool = False,
    batch_collect: bool = False,
) -> None:
    """Ingest markdown rules from source directory.

    Args:
        source_dir: Path to directory containing markdown files
        force: Full rebuild — reset the collection and re-ingest every file
        batch: Route summarization through the provider Batch API (cheaper, slower)
        batch_collect: Resume an interrupted batch run from the state file
    """
    get_config()
    source_path = Path(source_dir)

    logger.info(f"Starting ingestion from {source_path}")

    # Initialize services
    try:
        vector_db = VectorDBService(collection_name="kill_team_rules")
        embedding_service = EmbeddingService()
        ingestor = RAGIngestor(vector_db_service=vector_db, embedding_service=embedding_service)
        validator = DocumentValidator()
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}", exc_info=True)
        print(f"❌ Error initializing services: {e}")
        sys.exit(1)

    state = IngestionState.load()

    if batch_collect:
        _resume_batch(state, source_path, ingestor, validator)
        return

    md_files = find_markdown_files(source_path)
    if not md_files:
        logger.warning(f"No markdown files found in {source_path}")
        print(f"⚠️  No markdown files found in {source_path}")
        return

    print(f"Found {len(md_files)} markdown files")

    # A stale fingerprint means the stored hashes describe chunks/embeddings that
    # these settings would no longer produce, so incremental skipping is unsafe.
    # A *different source tree* is worse: `classify` derives "removed" by
    # subtraction, so comparing against another tree (e.g. ingesting one
    # subdirectory) would report every file outside it as deleted and drop its
    # chunks. Rebuilding is the only safe way to re-point the state at a new tree.
    same_tree = state.matches_source_dir(source_path)
    if not same_tree and not force:
        print(f"\n❌ State file was built from {state.source_dir}")
        print(f"   but this run targets {IngestionState.normalize_source_dir(source_path)}.")
        print("   Ingest the original directory, or re-point the state with --force.")
        sys.exit(1)

    rebuild = force or state.is_stale()
    if rebuild:
        reason = "--force" if force else _stale_reason(state)
        print(f"\n🔄 Full rebuild ({reason}) — resetting collection")
        # Invalidate the state *before* the destructive reset. Otherwise a crash
        # between the two leaves a state file that still lists every file with a
        # matching fingerprint, and the next incremental run reports "nothing to
        # ingest" against an empty collection.
        state.reset_for_rebuild(source_path)
        state.save()
        vector_db.reset()
        ingestor.keyword_extractor.clear_keywords()
        changes = state.classify(md_files, source_path)  # everything is "new" now
    else:
        changes = state.classify(md_files, source_path)
        print(
            f"  {len(changes.new)} new, {len(changes.changed)} changed, "
            f"{len(changes.unchanged)} unchanged, {len(changes.removed)} removed"
        )

    # Drop chunks of files that no longer exist on disk
    removed_chunks = 0
    for rel_path in changes.removed:
        doc_id = state.document_id_for(rel_path)
        if doc_id:
            removed_chunks += ingestor.delete_document(doc_id)
        state.forget(rel_path)
        print(f"🗑  {rel_path} - removed from source, chunks deleted")
    if changes.removed:
        state.save()

    if not changes.to_ingest:
        print("\n✅ Nothing to ingest — all files unchanged")
        _print_summary(
            processed=0,
            unchanged=len(changes.unchanged),
            removed=len(changes.removed),
            removed_chunks=removed_chunks,
            validation_errors=0,
            total_chunks=0,
            summary_cost=0.0,
            cache_savings=0.0,
            batch_savings=0.0,
        )
        return

    # Build documents for everything that needs (re-)ingesting
    documents: list[RuleDocument] = []
    validation_errors = 0
    for md_file in changes.to_ingest:
        try:
            document, relative_path, error = _build_document(md_file, source_path, validator)
            if document is None:
                logger.warning(f"Validation failed for {relative_path}: {error}")
                print(f"⚠️  {relative_path}: {error}")
                validation_errors += 1
                continue
            documents.append(document)
        except Exception as e:
            logger.error(f"Error reading {md_file}: {e}", exc_info=True)
            print(f"❌ {md_file.name}: {e}")
            validation_errors += 1

    if not documents:
        print("\n⚠️  No valid documents to ingest")
        return

    prepared_chunks = None
    batch_costs = BatchCosts()
    if batch:
        summarizer = BatchSummarizer(state=state)
        prepared_chunks, batch_costs = summarizer.run(documents)

    result = _ingest_documents(ingestor, documents, state, prepared_chunks)

    # Only now are the batched summaries durable (embedded and upserted), so only
    # now may the resume record be dropped. Clearing it earlier would mean a
    # failure during embedding discarded a batch that had already been paid for.
    if state.batch is not None:
        state.batch = None
        state.save()

    # Batched summaries are paid for by BatchSummarizer, live ones by the ingestor;
    # a run can contain both (batch items that failed fall back to live).
    _print_summary(
        processed=result.documents_processed,
        unchanged=len(changes.unchanged),
        removed=len(changes.removed),
        removed_chunks=removed_chunks,
        validation_errors=validation_errors,
        total_chunks=result.embedding_count,
        summary_cost=result.summary_cost_usd + batch_costs.cost_usd,
        cache_savings=result.summary_cache_savings_usd + batch_costs.cache_savings_usd,
        batch_savings=batch_costs.batch_savings_usd,
        summary_failures=len(result.summary_failed_paths),
    )


def _stale_reason(state: IngestionState) -> str:
    """Human-readable explanation of why the fingerprint mismatched."""
    if not state.fingerprint:
        return "no previous ingestion state"
    current = current_fingerprint()
    diffs = [
        f"{key}: {state.fingerprint.get(key)!r} → {value!r}"
        for key, value in current.items()
        if state.fingerprint.get(key) != value
    ]
    return "config changed — " + "; ".join(diffs) if diffs else "state fingerprint mismatch"


def _ingest_documents(
    ingestor: RAGIngestor,
    documents: list[RuleDocument],
    state: IngestionState,
    prepared_chunks: dict[str, list[MarkdownChunk]] | None,
) -> IngestionResult:
    """Ingest documents one at a time, persisting state after each success.

    One call per document (rather than one call for the whole list) so a crash
    halfway through does not discard the work already done.
    """
    totals = IngestionResult(
        job_id=uuid4(),
        documents_processed=0,
        documents_failed=0,
        embedding_count=0,
        errors=[],
        warnings=[],
        duration_seconds=0.0,
    )

    for document in documents:
        rel_path = document.relative_path or document.filename

        try:
            # `flush_keywords=False`: the library is rewritten in full on every
            # flush, so with one call per document that is N rewrites of the same
            # file. It is saved once after the loop instead.
            result = ingestor.ingest(
                [document], prepared_chunks=prepared_chunks, flush_keywords=False
            )
        except Exception as e:
            # One unwritable document must not abandon the rest of the run (and the
            # end-of-run report). RAGIngestor raises VectorDBWriteError on any Chroma
            # failure and lets unexpected errors escape; both are per-document.
            logger.error(f"Error ingesting {rel_path}: {e}", exc_info=True)
            print(f"❌ {rel_path}: {e}")
            totals.documents_failed += 1
            totals.errors.append(rel_path)
            continue

        totals.documents_processed += result.documents_processed
        totals.documents_failed += result.documents_failed
        totals.embedding_count += result.embedding_count
        totals.errors.extend(result.errors)
        totals.warnings.extend(result.warnings)
        totals.duration_seconds += result.duration_seconds
        totals.summary_cost_usd += result.summary_cost_usd
        totals.summary_cache_savings_usd += result.summary_cache_savings_usd
        totals.summary_failed_paths |= result.summary_failed_paths

        if not result.documents_processed:
            print(f"❌ {rel_path} - not ingested")
            continue

        if rel_path in result.summary_failed_paths:
            # Chunks are in the store and searchable, just without summaries. Leaving
            # the file out of the state means the next run picks it up again — a
            # transient summarization failure must not become permanent.
            print(
                f"⚠️  {rel_path} - {result.embedding_count} embeddings, "
                f"but summaries failed (will retry on next run)"
            )
            continue

        state.record(
            relative_path=rel_path,
            content_hash=document.hash,
            document_id=str(document.document_id),
            chunks=result.chunks_by_path.get(rel_path, result.embedding_count),
        )
        # The fingerprint is *not* re-stamped here. It is set once by
        # reset_for_rebuild() on the rebuild path, and on the incremental path it
        # already matches (that is what `is_stale()` established). Stamping it
        # per document let the resume path — which never checks staleness — write
        # a fresh fingerprint over entries built under the previous config.
        state.save()
        print(f"✓ {rel_path} - {result.embedding_count} embeddings")

    ingestor.keyword_extractor.save_keywords()
    return totals


def _resume_batch(
    state: IngestionState,
    source_path: Path,
    ingestor: RAGIngestor,
    validator: DocumentValidator,
) -> None:
    """Resume an interrupted `--batch` run from data/ingestion_state.json."""
    if not state.batch:
        print("❌ No in-flight batch run in the ingestion state file.")
        print("   Start one with: python -m src.cli ingest <source> --batch")
        sys.exit(1)

    # The batch was built from the chunks these settings produced. Re-chunking under
    # a changed config yields a different split, and summaries are matched to chunks
    # by ordinal position — so resuming would bind each summary to unrelated text,
    # with the file-content hash check passing throughout.
    if state.is_stale():
        print(f"❌ Config changed since the batch was submitted ({_stale_reason(state)}).")
        print("   Restore the previous settings to collect it, or discard it with --force.")
        sys.exit(1)

    if not state.matches_source_dir(source_path):
        print(f"❌ Batch was submitted against {state.source_dir}, not {source_path}.")
        print("   Re-run --batch-collect from the original source directory.")
        sys.exit(1)

    documents: list[RuleDocument] = []
    for request in state.batch.get("requests", []):
        md_file = source_path / request["relative_path"]
        if not md_file.exists():
            print(f"⚠️  {request['relative_path']} no longer exists — skipping")
            continue
        document, relative_path, error = _build_document(md_file, source_path, validator)
        if document is None:
            print(f"⚠️  {relative_path}: {error}")
            continue
        documents.append(document)

    if not documents:
        # Leave state.batch intact: the submission is already paid for, and the usual
        # cause is a wrong working directory rather than genuinely missing files.
        # Clearing it here would make the batch permanently uncollectable.
        print("❌ None of the batched files could be re-read.")
        print(f"   Check that {source_path} is the directory the batch was submitted from.")
        print("   The batch id is preserved; re-run --batch-collect with the right source.")
        sys.exit(1)

    summarizer = BatchSummarizer(state=state)
    prepared_chunks, batch_costs = summarizer.resume(documents)
    result = _ingest_documents(ingestor, documents, state, prepared_chunks)

    if state.batch is not None:
        state.batch = None
        state.save()

    _print_summary(
        processed=result.documents_processed,
        unchanged=0,
        removed=0,
        removed_chunks=0,
        validation_errors=0,
        total_chunks=result.embedding_count,
        summary_cost=result.summary_cost_usd + batch_costs.cost_usd,
        cache_savings=result.summary_cache_savings_usd + batch_costs.cache_savings_usd,
        batch_savings=batch_costs.batch_savings_usd,
        summary_failures=len(result.summary_failed_paths),
    )


def _print_summary(
    processed: int,
    unchanged: int,
    removed: int,
    removed_chunks: int,
    validation_errors: int,
    total_chunks: int,
    summary_cost: float,
    cache_savings: float,
    batch_savings: float,
    summary_failures: int = 0,
) -> None:
    """Print the end-of-run report."""
    full_price = summary_cost + cache_savings + batch_savings
    pct_cache = (cache_savings / full_price * 100) if full_price > 0 else 0.0
    pct_batch = (batch_savings / full_price * 100) if full_price > 0 else 0.0

    print(f"\n{'=' * 60}")
    print("Ingestion complete")
    print(f"  Documents ingested: {processed}")
    print(f"  Documents unchanged (skipped): {unchanged}")
    print(f"  Documents removed: {removed} ({removed_chunks} chunks deleted)")
    print(f"  Validation errors: {validation_errors}")
    if summary_failures:
        print(f"  ⚠️  Summarization failed: {summary_failures} (retried on next run)")
    print(f"  Total chunks created: {total_chunks}")
    print(f"  Summarization cost: ${summary_cost:.4f} (after discounts)")
    print(f"  Cache savings: ${cache_savings:.4f} ({pct_cache:.1f}% saved)")
    if batch_savings > 0:
        print(f"  Batch savings: ${batch_savings:.4f} ({pct_batch:.1f}% saved)")
    print(f"{'=' * 60}")

    logger.info(
        "Ingestion complete",
        extra={
            "documents_processed": processed,
            "documents_unchanged": unchanged,
            "documents_removed": removed,
            "validation_errors": validation_errors,
            "summary_failures": summary_failures,
            "total_chunks": total_chunks,
            "total_summary_cost_usd": f"${summary_cost:.4f}",
            "total_cache_savings_usd": f"${cache_savings:.4f}",
            "total_batch_savings_usd": f"${batch_savings:.4f}",
        },
    )


# No module-level argparse entry point here on purpose: `src/cli/__main__.py` owns
# the `ingest` subcommand and its flags. A second parser in this file drifted from
# it (it took `--source` where the real command takes a positional argument, with
# different help text), and only one of the two was reachable via the documented
# `python -m src.cli ingest`.
