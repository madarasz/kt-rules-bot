"""Unit tests for deterministic ids and the incremental ingest flow.

The bug these guard against: before deterministic ids, every ingest run produced
a fresh uuid4 document_id, so the ingestor's delete-then-upsert deleted nothing
and re-ingesting a file left the old chunks behind as duplicates.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.rule_document import RuleDocument
from src.services.rag.chunker import MarkdownChunker
from src.services.rag.ingestor import RAGIngestor

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


# --- Deterministic ids ---


def test_document_id_is_stable_across_runs():
    assert _doc().document_id == _doc().document_id


def test_document_id_differs_per_relative_path():
    """Same basename in different subdirectories must not collide."""
    assert _doc("team/a.md").document_id != _doc("killzone/a.md").document_id


def test_document_id_ignores_content_changes():
    """Editing a file keeps its identity, so its old chunks can be deleted."""
    assert _doc(content=MD).document_id == _doc(content=MD + "\n## Gamma\n").document_id


def test_document_id_defaults_to_filename_when_no_relative_path():
    doc = RuleDocument.from_markdown_file(filename="a.md", content=MD, metadata=META)
    assert doc.relative_path == "a.md"
    assert doc.document_id == RuleDocument.make_document_id("a.md")


def test_chunk_ids_are_stable_and_unique():
    doc = _doc()
    chunker = MarkdownChunker()

    first = chunker.chunk(doc.content)
    RAGIngestor.assign_chunk_ids(doc, first)
    second = chunker.chunk(doc.content)
    RAGIngestor.assign_chunk_ids(doc, second)

    assert [c.chunk_id for c in first] == [c.chunk_id for c in second]
    assert len({c.chunk_id for c in first}) == len(first) > 1


def test_chunk_ids_differ_across_documents():
    chunker = MarkdownChunker()
    a, b = _doc("team/a.md"), _doc("team/b.md")
    chunks_a, chunks_b = chunker.chunk(a.content), chunker.chunk(b.content)
    RAGIngestor.assign_chunk_ids(a, chunks_a)
    RAGIngestor.assign_chunk_ids(b, chunks_b)

    assert {c.chunk_id for c in chunks_a}.isdisjoint({c.chunk_id for c in chunks_b})


# --- Ingestor behaviour ---


@pytest.fixture
def ingestor():
    """RAGIngestor with every external dependency mocked out."""
    vector_db = MagicMock()
    vector_db.delete_by_document_id.return_value = 0
    embeddings = MagicMock()
    embeddings.embed_batch.side_effect = lambda texts: [[0.1] * 3 for _ in texts]
    keywords = MagicMock()
    keywords.extract_from_chunks.return_value = set()
    keywords.add_keywords.return_value = 0

    with patch("src.services.rag.ingestor.SUMMARY_ENABLED", False):
        yield RAGIngestor(
            embedding_service=embeddings,
            vector_db_service=vector_db,
            keyword_extractor=keywords,
            summarizer=None,
        )


def test_ingest_deletes_previous_chunks_before_upsert(ingestor):
    """Re-ingesting must remove the old rows — this is the anti-duplication path."""
    doc = _doc()
    ingestor.vector_db.delete_by_document_id.return_value = 2

    result = ingestor.ingest([doc])

    ingestor.vector_db.delete_by_document_id.assert_called_once_with(doc.document_id)
    assert result.documents_processed == 1
    assert result.embedding_count == 2


def test_ingest_writes_relative_path_into_metadata(ingestor):
    ingestor.ingest([_doc("killzone/volkus.md")])

    metadatas = ingestor.vector_db.upsert_embeddings.call_args.kwargs["metadatas"]
    assert {m["relative_path"] for m in metadatas} == {"killzone/volkus.md"}
    assert {m["filename"] for m in metadatas} == {"volkus.md"}


def test_ingest_reports_chunk_counts_per_path(ingestor):
    result = ingestor.ingest([_doc("team/a.md")])
    assert result.chunks_by_path == {"team/a.md": 2}


def test_prepared_chunks_skip_chunking_and_summarization(ingestor):
    """The batch path hands in already-summarized chunks; ingestor must use them."""
    doc = _doc()
    chunks = MarkdownChunker().chunk(doc.content)
    RAGIngestor.assign_chunk_ids(doc, chunks)
    for chunk in chunks:
        chunk.summary = "precomputed summary"

    summarizer = MagicMock()
    ingestor.summarizer = summarizer

    ingestor.ingest([doc], prepared_chunks={"team/a.md": chunks})

    summarizer.generate_summaries.assert_not_called()
    metadatas = ingestor.vector_db.upsert_embeddings.call_args.kwargs["metadatas"]
    assert {m["summary"] for m in metadatas} == {"precomputed summary"}


def test_failed_summarization_is_flagged_for_retry(ingestor):
    """A transient summary failure must not be recorded as a clean ingest.

    Before incremental ingestion every run re-summarized everything, so a blip
    self-healed next run. Now a file recorded as clean is never revisited, so the
    ingestor has to tell the caller to leave it out of the state.
    """
    summarizer = MagicMock()
    # generate_summaries() signals failure with zero tokens and blank summaries
    summarizer.generate_summaries = AsyncMock(
        return_value=(MarkdownChunker().chunk(MD), 0, 0, 0, 0, "")
    )
    ingestor.summarizer = summarizer

    result = ingestor.ingest([_doc("team/a.md")])

    assert result.summary_failed_paths == {"team/a.md"}
    # The chunks are still stored — summaries only enrich BM25
    assert result.documents_processed == 1
    assert result.embedding_count == 2


def test_successful_summarization_is_not_flagged(ingestor):
    chunks = MarkdownChunker().chunk(MD)
    for chunk in chunks:
        chunk.summary = "a summary"
    summarizer = MagicMock()
    summarizer.generate_summaries = AsyncMock(
        return_value=(chunks, 500, 100, 0, 0, "grok-4.3")
    )
    ingestor.summarizer = summarizer

    result = ingestor.ingest([_doc("team/a.md")])

    assert result.summary_failed_paths == set()
    assert result.summary_cost_usd > 0


def test_prepared_chunks_are_never_flagged(ingestor):
    """The batch path accounts for its own failures; ingest() must not double-flag."""
    doc = _doc()
    chunks = MarkdownChunker().chunk(doc.content)
    RAGIngestor.assign_chunk_ids(doc, chunks)
    ingestor.summarizer = MagicMock()

    result = ingestor.ingest([doc], prepared_chunks={"team/a.md": chunks})

    assert result.summary_failed_paths == set()


def test_delete_document_accepts_string_id(ingestor):
    """State stores document ids as strings; deletion must accept them."""
    doc = _doc()
    ingestor.vector_db.delete_by_document_id.return_value = 7

    deleted = ingestor.delete_document(str(doc.document_id))

    assert deleted == 7
    ingestor.vector_db.delete_by_document_id.assert_called_once_with(doc.document_id)
