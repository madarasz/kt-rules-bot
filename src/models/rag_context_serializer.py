"""RAG context serialization for caching and reuse.

Serializes/deserializes RAGContext (+ multi-hop evaluations and chunk-hop map)
to/from JSON, so quality tests can reuse pre-cached RAG retrieval results for
deterministic, faster, cheaper runs.

JSON shape::

    {
        "rag_context": {... RAGContext fields, UUIDs as strings ...},
        "hop_evaluations": [{... HopEvaluation.to_dict() ...}],
        "chunk_hop_map": {"chunk-uuid": hop_number, ...},
        "embedding_cost": 0.0001
    }
"""

import json
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from src.lib.logging import get_logger
from src.models.rag_context import DocumentChunk, RAGContext

logger = get_logger(__name__)


class RAGContextSerializationError(Exception):
    """Raised when RAG context serialization/deserialization fails."""


def serialize_rag_context(
    rag_context: RAGContext,
    hop_evaluations: list | None = None,
    chunk_hop_map: dict | None = None,
    embedding_cost: float = 0.0,
) -> dict:
    """Serialize RAG context to a JSON-ready dict (UUIDs stringified on dump)."""
    return {
        "rag_context": asdict(rag_context),
        "hop_evaluations": [h.to_dict() for h in hop_evaluations or []],
        "chunk_hop_map": {str(k): v for k, v in (chunk_hop_map or {}).items()},
        "embedding_cost": embedding_cost,
    }


def save_rag_context(
    file_path: str | Path,
    rag_context: RAGContext,
    hop_evaluations: list | None = None,
    chunk_hop_map: dict | None = None,
    embedding_cost: float = 0.0,
) -> None:
    """Save RAG context to a pretty-printed JSON file (parents created as needed)."""
    file_path = Path(file_path)
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        data = serialize_rag_context(rag_context, hop_evaluations, chunk_hop_map, embedding_cost)
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        logger.info(f"Saved RAG context to {file_path}")
    except Exception as e:
        raise RAGContextSerializationError(f"Failed to save RAG context to {file_path}: {e}") from e


def deserialize_rag_context(data: dict) -> tuple[RAGContext, list, dict, float]:
    """Deserialize RAG context from a dict.

    Returns (RAGContext, hop_evaluations, chunk_hop_map, embedding_cost).
    Raises RAGContextSerializationError on malformed/invalid data.
    """
    try:
        rc = data["rag_context"]
        chunks = [
            DocumentChunk(
                **{**c, "chunk_id": UUID(c["chunk_id"]), "document_id": UUID(c["document_id"])}
            )
            for c in rc["document_chunks"]
        ]
        rag_context = RAGContext(
            context_id=UUID(rc["context_id"]),
            query_id=UUID(rc["query_id"]),
            document_chunks=chunks,
            relevance_scores=[c.relevance_score for c in chunks],
            total_chunks=rc["total_chunks"],
            avg_relevance=rc["avg_relevance"],
            meets_threshold=rc["meets_threshold"],
        )

        hop_evaluations = []
        if data.get("hop_evaluations"):
            # Import here to avoid circular dependency
            from src.services.rag.multi_hop_retriever import HopEvaluation

            hop_evaluations = [HopEvaluation(**h) for h in data["hop_evaluations"]]

        chunk_hop_map = {UUID(k): v for k, v in data.get("chunk_hop_map", {}).items()}
        return rag_context, hop_evaluations, chunk_hop_map, data.get("embedding_cost", 0.0)

    except KeyError as e:
        raise RAGContextSerializationError(f"Missing required field in RAG context data: {e}") from e
    except (ValueError, TypeError) as e:
        raise RAGContextSerializationError(f"Invalid data format in RAG context: {e}") from e


def load_rag_context(file_path: str | Path) -> tuple[RAGContext, list, dict, float]:
    """Load RAG context from a JSON file. See deserialize_rag_context for return shape."""
    file_path = Path(file_path)
    if not file_path.exists():
        raise RAGContextSerializationError(f"RAG context file not found: {file_path}")
    try:
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info(f"Loaded RAG context from {file_path}")
        return deserialize_rag_context(data)
    except json.JSONDecodeError as e:
        raise RAGContextSerializationError(f"Invalid JSON in RAG context file {file_path}: {e}") from e
    except RAGContextSerializationError:
        raise
    except Exception as e:
        raise RAGContextSerializationError(f"Failed to load RAG context from {file_path}: {e}") from e
