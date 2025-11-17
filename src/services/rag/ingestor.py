"""RAG ingestion service implementing the RAG pipeline contract.

Implements ingest() method from specs/001-we-are-building/contracts/rag-pipeline.md
"""

import time
from dataclasses import dataclass
from uuid import UUID, uuid4

from src.lib.logging import get_logger
from src.models.rule_document import RuleDocument
from src.services.rag.chunker import MarkdownChunker
from src.services.rag.embeddings import EmbeddingService
from src.services.rag.keyword_extractor import KeywordExtractor
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
        db_path: str | None = None,
    ):
        """Initialize RAG ingestor.

        Args:
            chunker: Markdown chunker (creates if None)
            embedding_service: Embedding service (creates if None)
            vector_db_service: Vector DB service (creates if None)
            keyword_extractor: Keyword extractor (creates if None)
            db_path: Optional database path (only used if vector_db_service is None)
        """
        self.chunker = chunker or MarkdownChunker()
        self.embedding_service = embedding_service or EmbeddingService()
        self.vector_db = vector_db_service or VectorDBService(db_path=db_path)
        self.keyword_extractor = keyword_extractor or KeywordExtractor()
        self.document_hashes: dict[str, str] = {}  # filename -> hash mapping

        logger.info("rag_ingestor_initialized")

    def ingest(self, documents: list[RuleDocument]) -> IngestionResult:
        """Ingest rule documents into the RAG system.

        Implements the RAG pipeline contract from contracts/rag-pipeline.md.

        Process:
        1. Validate documents
        2. Chunk markdown content
        3. Generate embeddings
        4. Store in vector DB with metadata

        Args:
            documents: List of RuleDocument objects

        Returns:
            IngestionResult with statistics

        Raises:
            VectorDBWriteError: If vector DB write fails (aborts job)
        """
        start_time = time.time()
        job_id = uuid4()

        documents_processed = 0
        documents_failed = 0
        embedding_count = 0
        errors: list[str] = []
        warnings: list[str] = []
        all_chunks = []  # Collect all chunks for keyword extraction

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

                # Chunk the document
                chunks = self.chunker.chunk(document.content)

                # Collect chunks for keyword extraction
                all_chunks.extend(chunks)

                logger.debug(
                    "document_chunked",
                    document_id=str(document.document_id),
                    chunk_count=len(chunks),
                )

                # Generate embeddings for chunks
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
        )

        logger.info(
            "ingestion_completed",
            job_id=str(job_id),
            processed=documents_processed,
            failed=documents_failed,
            embeddings=embedding_count,
            duration=duration,
        )

        return result

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
