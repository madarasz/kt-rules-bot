"""Vector database service using Chroma.

Stores and retrieves embeddings with metadata filtering.
Based on specs/001-we-are-building/research.md Decision 2.
"""

from typing import Any
from uuid import UUID

import chromadb
from chromadb.config import Settings

from src.lib.config import get_config
from src.lib.logging import get_logger

logger = get_logger(__name__)


class VectorDBService:
    """Service for vector database operations using Chroma."""

    def __init__(self, collection_name: str = "kill_team_rules", db_path: str | None = None):
        """Initialize vector database service.

        Args:
            collection_name: Name of the Chroma collection
            db_path: Optional path to database (defaults to config path)
        """
        config = get_config()

        # Use provided path or fall back to config
        path = db_path if db_path is not None else config.vector_db_path

        # Initialize Chroma client with persistence
        self.client = chromadb.PersistentClient(
            path=path, settings=Settings(anonymized_telemetry=False, allow_reset=True)
        )

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name, metadata={"description": "Kill Team 3rd edition rules embeddings"}
        )

        logger.info(
            "vector_db_initialized",
            collection=collection_name,
            path=path,
            count=self.collection.count(),
        )

    def add_embeddings(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Add embeddings to the vector database.

        Args:
            ids: List of unique IDs (typically chunk UUIDs as strings)
            embeddings: List of embedding vectors
            documents: List of document texts
            metadatas: List of metadata dictionaries

        Raises:
            ValueError: If input lists have different lengths
        """
        if not (len(ids) == len(embeddings) == len(documents) == len(metadatas)):
            raise ValueError("All input lists must have the same length")

        try:
            self.collection.add(
                ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
            )

            logger.info("embeddings_added", count=len(ids), collection=self.collection.name)

        except Exception as e:
            logger.error("add_embeddings_failed", error=str(e), count=len(ids))
            raise

    def upsert_embeddings(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Upsert embeddings (update if exists, insert if not).

        Args:
            ids: List of unique IDs
            embeddings: List of embedding vectors
            documents: List of document texts
            metadatas: List of metadata dictionaries
        """
        if not (len(ids) == len(embeddings) == len(documents) == len(metadatas)):
            raise ValueError("All input lists must have the same length")

        try:
            self.collection.upsert(
                ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
            )

            logger.info("embeddings_upserted", count=len(ids), collection=self.collection.name)

        except Exception as e:
            logger.error("upsert_embeddings_failed", error=str(e), count=len(ids))
            raise

    def query(
        self,
        query_embeddings: list[list[float]],
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Query the vector database for similar embeddings.

        Args:
            query_embeddings: Query embedding vectors
            n_results: Number of results to return per query
            where: Metadata filter (optional)

        Returns:
            Query results dictionary with ids, documents, metadatas, distances
        """
        try:
            results = self.collection.query(
                query_embeddings=query_embeddings, n_results=n_results, where=where
            )

            logger.debug(
                "vector_db_queried",
                n_queries=len(query_embeddings),
                n_results=n_results,
                has_filter=where is not None,
            )

            return results

        except Exception as e:
            logger.error("query_failed", error=str(e), n_results=n_results)
            raise

    def delete_by_document_id(self, document_id: UUID) -> int:
        """Delete all embeddings for a document.

        Args:
            document_id: Document UUID

        Returns:
            Number of embeddings deleted
        """
        doc_id_str = str(document_id)

        try:
            # Query to find all chunks for this document
            results = self.collection.get(where={"document_id": doc_id_str})

            if not results["ids"]:
                logger.info("no_embeddings_to_delete", document_id=doc_id_str)
                return 0

            # Delete the embeddings
            self.collection.delete(ids=results["ids"])

            count = len(results["ids"])

            logger.info("embeddings_deleted", document_id=doc_id_str, count=count)

            return count

        except Exception as e:
            logger.error("delete_failed", error=str(e), document_id=doc_id_str)
            raise

    def get_count(self) -> int:
        """Get total number of embeddings in the collection.

        Returns:
            Number of embeddings
        """
        return self.collection.count()

    def reset(self) -> None:
        """Reset the collection (delete all data).

        Warning: This is destructive and cannot be undone.
        """
        logger.warning("resetting_collection", collection=self.collection.name)

        self.client.delete_collection(name=self.collection.name)
        self.collection = self.client.create_collection(
            name=self.collection.name,
            metadata={"description": "Kill Team 3rd edition rules embeddings"},
        )

        logger.info("collection_reset", collection=self.collection.name)
