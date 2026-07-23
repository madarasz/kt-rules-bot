"""RAG ingestion service implementing the RAG pipeline contract.

Implements ingest() method from specs/001-we-are-building/contracts/rag-pipeline.md
"""

import asyncio
import time
from dataclasses import dataclass, field
from uuid import UUID, uuid4, uuid5

from src.lib.constants import SUMMARY_ENABLED
from src.lib.logging import get_logger
from src.lib.pricing import calculate_llm_cost
from src.models.rule_document import RuleDocument
from src.services.rag.chunker import MarkdownChunk, MarkdownChunker
from src.services.rag.embeddings import EmbeddingService
from src.services.rag.keyword_extractor import KeywordExtractor
from src.services.rag.summarizer import ChunkSummarizer
from src.services.rag.vector_db import VectorDBService

logger = get_logger(__name__)


@dataclass
class IngestionResult:
    """Result of document ingestion."""

    job_id: UUID
    documents_processed: int
    documents_failed: int
    embedding_count: int  # Total embeddings created
    errors: list[str]  # Filenames that failed
    warnings: list[str]  # Non-fatal issues
    duration_seconds: float
    summary_cost_usd: float = 0.0  # Total cost of summary generation (discounted, if enabled)
    summary_cache_savings_usd: float = 0.0  # Saved by prompt caching vs. full price
    chunks_by_path: dict[str, int] = field(default_factory=dict)  # relative path -> chunk count
    # Relative paths ingested with empty summaries because summarization failed.
    # The chunks are usable (summaries only enrich BM25), but the caller must not
    # record them as cleanly ingested, or incremental runs would never retry them.
    summary_failed_paths: set[str] = field(default_factory=set)
    # Batch-API costs are not tracked here: batched summaries are paid for before
    # ingest() is called, and reported by BatchSummarizer as BatchCosts.


class InvalidDocumentError(Exception):
    """Document validation error."""

    pass


class EmbeddingFailureError(Exception):
    """Embedding generation error."""

    pass


class VectorDBWriteError(Exception):
    """Vector DB write error."""

    pass


class RAGIngestor:
    """Service for ingesting documents into the RAG system."""

    def __init__(
        self,
        chunker: MarkdownChunker | None = None,
        embedding_service: EmbeddingService | None = None,
        vector_db_service: VectorDBService | None = None,
        keyword_extractor: KeywordExtractor | None = None,
        summarizer: ChunkSummarizer | None = None,
        db_path: str | None = None,
    ):
        """Initialize RAG ingestor.

        Args:
            chunker: Markdown chunker (creates if None)
            embedding_service: Embedding service (creates if None)
            vector_db_service: Vector DB service (creates if None)
            keyword_extractor: Keyword extractor (creates if None)
            summarizer: Chunk summarizer (creates if None and SUMMARY_ENABLED)
            db_path: Optional database path (only used if vector_db_service is None)
        """
        self.chunker = chunker or MarkdownChunker()
        self.embedding_service = embedding_service or EmbeddingService()
        self.vector_db = vector_db_service or VectorDBService(db_path=db_path)
        self.keyword_extractor = keyword_extractor or KeywordExtractor()
        self.summarizer = summarizer or (ChunkSummarizer() if SUMMARY_ENABLED else None)
        self.document_hashes: dict[str, str] = {}  # filename -> hash mapping

        logger.info(
            "rag_ingestor_initialized", summary_generation_enabled=SUMMARY_ENABLED
        )

    def ingest(
        self,
        documents: list[RuleDocument],
        prepared_chunks: dict[str, list[MarkdownChunk]] | None = None,
    ) -> IngestionResult:
        """Ingest rule documents into the RAG system.

        Implements the RAG pipeline contract from contracts/rag-pipeline.md.

        Process:
        1. Validate documents
        2. Chunk markdown content
        3. Generate embeddings
        4. Store in vector DB with metadata

        Args:
            documents: List of RuleDocument objects
            prepared_chunks: Optional {relative_path: chunks} whose summaries are
                already populated (the Batch API path). Those documents skip the
                chunk + live-summarize steps; everything else is unchanged.

        Returns:
            IngestionResult with statistics

        Raises:
            VectorDBWriteError: If vector DB write fails (aborts job)
        """
        prepared_chunks = prepared_chunks or {}
        start_time = time.time()
        job_id = uuid4()

        documents_processed = 0
        documents_failed = 0
        embedding_count = 0
        total_summary_cost = 0.0  # Track summary generation costs (discounted)
        total_cache_savings = 0.0  # Track savings from prompt caching
        errors: list[str] = []
        warnings: list[str] = []
        all_chunks = []  # Collect all chunks for keyword extraction
        chunks_by_path: dict[str, int] = {}  # For the caller's state file
        summary_failed_paths: set[str] = set()

        logger.info("ingestion_started", job_id=str(job_id), document_count=len(documents))

        for document in documents:
            try:
                # Validate document
                self._validate_document(document, warnings)

                # Check if document already exists (upsert logic)
                # Delete existing embeddings for this document
                deleted_count = self.vector_db.delete_by_document_id(document.document_id)
                if deleted_count > 0:
                    logger.info(
                        "document_updated",
                        document_id=str(document.document_id),
                        deleted_embeddings=deleted_count,
                    )

                # Chunk the document, unless the caller already did it and attached
                # summaries (batch path — its cost is accounted for by the caller).
                presummarized = prepared_chunks.get(document.relative_path or document.filename)
                if presummarized is not None:
                    chunks = presummarized
                else:
                    chunks = self.chunker.chunk(document.content)
                    self.assign_chunk_ids(document, chunks)

                # Collect chunks for keyword extraction
                all_chunks.extend(chunks)

                logger.debug(
                    "document_chunked",
                    document_id=str(document.document_id),
                    chunk_count=len(chunks),
                )

                # Generate summaries for chunks (if enabled)
                if self.summarizer and presummarized is None:
                    (
                        chunks,
                        prompt_tokens,
                        completion_tokens,
                        cache_read_tokens,
                        cache_creation_tokens,
                        model,
                    ) = asyncio.run(self.summarizer.generate_summaries(chunks))
                    if prompt_tokens > 0:  # Only calculate cost if summary was generated
                        breakdown = calculate_llm_cost(
                            prompt_tokens,
                            completion_tokens,
                            model,
                            cache_read_tokens,
                            cache_creation_tokens,
                        )
                        total_summary_cost += breakdown.total_cost
                        total_cache_savings += breakdown.cache_savings
                        logger.debug(
                            "summaries_generated",
                            document_id=str(document.document_id),
                            chunk_count=len(chunks),
                            cost_usd=f"${breakdown.total_cost:.4f}",
                            cache_savings_usd=f"${breakdown.cache_savings:.4f}",
                        )
                    elif chunks:
                        # generate_summaries() reports failure as zero tokens and
                        # blanks every summary (see its except branch). Flag the
                        # file so the caller leaves it out of the state, otherwise
                        # a transient API blip would permanently cost this document
                        # its summaries — incremental runs never revisit a file
                        # recorded as clean.
                        summary_failed_paths.add(document.relative_path or document.filename)
                        logger.warning(
                            "summaries_missing_will_retry_next_run",
                            document_id=str(document.document_id),
                            filename=document.filename,
                        )

                # Generate embeddings for chunks
                # Use original chunk text only (summary stored in metadata)
                chunk_texts = [chunk.text for chunk in chunks]
                embeddings = self._generate_embeddings_with_retry(chunk_texts, document.filename)

                # Prepare data for vector DB
                ids = [str(chunk.chunk_id) for chunk in chunks]
                metadatas = [
                    {
                        "document_id": str(document.document_id),
                        "source": document.metadata.get("source", document.version),
                        "doc_type": document.document_type,
                        "last_update_date": document.last_update_date.isoformat(),
                        "section": document.metadata.get("section", ""),
                        "header": chunk.header,
                        "header_level": chunk.header_level,
                        "position": chunk.position,
                        "filename": document.filename,
                        "relative_path": document.relative_path or document.filename,
                        "summary": chunk.summary,  # Add summary to metadata
                    }
                    for chunk in chunks
                ]

                # Store in vector DB (atomic operation per document)
                try:
                    self.vector_db.upsert_embeddings(
                        ids=ids, embeddings=embeddings, documents=chunk_texts, metadatas=metadatas
                    )

                    embedding_count += len(embeddings)
                    documents_processed += 1
                    chunks_by_path[document.relative_path or document.filename] = len(chunks)

                    # Store document hash for deduplication
                    self.document_hashes[document.filename] = document.hash

                    logger.info(
                        "document_ingested",
                        document_id=str(document.document_id),
                        filename=document.filename,
                        embeddings=len(embeddings),
                    )

                except Exception as e:
                    # Vector DB write failure is critical - abort job
                    logger.error(
                        "vector_db_write_failed",
                        document_id=str(document.document_id),
                        error=str(e),
                    )
                    raise VectorDBWriteError(
                        f"Vector DB write failed for {document.filename}: {e}"
                    ) from e

            except InvalidDocumentError as e:
                # Skip invalid document
                documents_failed += 1
                errors.append(document.filename)
                logger.warning(
                    "document_validation_failed", filename=document.filename, error=str(e)
                )

            except EmbeddingFailureError as e:
                # Skip document with embedding failure
                documents_failed += 1
                errors.append(document.filename)
                logger.warning(
                    "embedding_generation_failed", filename=document.filename, error=str(e)
                )

        duration = time.time() - start_time

        # Extract keywords from all chunks and update keyword library
        if all_chunks:
            keywords = self.keyword_extractor.extract_from_chunks(all_chunks)
            added_count = self.keyword_extractor.add_keywords(keywords)
            self.keyword_extractor.save_keywords()

            logger.info(
                "keywords_updated",
                job_id=str(job_id),
                new_keywords=added_count,
                total_keywords=self.keyword_extractor.get_keyword_count(),
            )

        result = IngestionResult(
            job_id=job_id,
            documents_processed=documents_processed,
            documents_failed=documents_failed,
            embedding_count=embedding_count,
            errors=errors,
            warnings=warnings,
            duration_seconds=duration,
            summary_cost_usd=total_summary_cost,
            summary_cache_savings_usd=total_cache_savings,
            chunks_by_path=chunks_by_path,
            summary_failed_paths=summary_failed_paths,
        )

        logger.info(
            "ingestion_completed",
            job_id=str(job_id),
            processed=documents_processed,
            failed=documents_failed,
            embeddings=embedding_count,
            duration=duration,
            summary_cost_usd=f"${total_summary_cost:.4f}",
            summary_cache_savings_usd=f"${total_cache_savings:.4f}",
        )

        return result

    def delete_document(self, document_id: str | UUID) -> int:
        """Remove every chunk of a document from the vector store.

        Used when a markdown file disappears from the source tree — without this
        its chunks would keep being retrieved forever.

        Returns:
            Number of embeddings deleted.
        """
        doc_uuid = document_id if isinstance(document_id, UUID) else UUID(str(document_id))
        return self.vector_db.delete_by_document_id(doc_uuid)

    @staticmethod
    def assign_chunk_ids(document: RuleDocument, chunks: list[MarkdownChunk]) -> None:
        """Replace the chunker's random chunk ids with deterministic ones, in place.

        The chunker cannot see the document, so it emits uuid4 ids. Re-deriving them
        here from (document_id, position, header) means re-ingesting an unchanged
        file rewrites the same rows rather than inserting duplicates under new ids.
        """
        for chunk in chunks:
            chunk.chunk_id = uuid5(document.document_id, f"{chunk.position}:{chunk.header}")

    def _validate_document(self, document: RuleDocument, warnings: list[str]) -> None:
        """Validate document has required metadata.

        Args:
            document: Document to validate
            warnings: Warning list to append to

        Raises:
            InvalidDocumentError: If document is invalid
        """
        # Check required metadata fields
        required_fields = ["source", "last_update_date", "document_type"]
        missing_fields = [field for field in required_fields if field not in document.metadata]

        if missing_fields:
            raise InvalidDocumentError(f"Missing required metadata: {', '.join(missing_fields)}")

        # Warn about ambiguous structure
        if "##" not in document.content and "###" not in document.content:
            warning = f"{document.filename}: No header structure (## or ###)"
            warnings.append(warning)
            logger.warning("ambiguous_markdown_structure", filename=document.filename)

    def _generate_embeddings_with_retry(
        self, texts: list[str], filename: str, max_retries: int = 3
    ) -> list[list[float]]:
        """Generate embeddings with retry logic.

        Args:
            texts: Texts to embed
            filename: Document filename (for logging)
            max_retries: Maximum retry attempts

        Returns:
            List of embeddings

        Raises:
            EmbeddingFailureError: If all retries fail
        """
        for attempt in range(max_retries):
            try:
                return self.embedding_service.embed_batch(texts)

            except Exception as e:
                if attempt == max_retries - 1:
                    # Final attempt failed
                    raise EmbeddingFailureError(
                        f"Embedding failed after {max_retries} attempts: {e}"
                    ) from e

                logger.warning(
                    "embedding_retry",
                    filename=filename,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    error=str(e),
                )

                # Exponential backoff
                time.sleep(2**attempt)

        # Should never reach here
        raise EmbeddingFailureError("Unexpected error in retry logic")
