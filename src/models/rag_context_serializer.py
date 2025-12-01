"""RAG context serialization for caching and reuse.

This module provides functionality to serialize and deserialize RAGContext objects
to/from JSON files, enabling quality tests to use pre-cached RAG retrieval results
for deterministic, faster, and cheaper testing.

Design:
- JSON format preserves all RAGContext + DocumentChunk data
- Includes HopEvaluation objects (multi-hop context evaluations)
- Includes chunk-hop mapping for multi-hop queries
- Handles UUID serialization (str -> UUID conversion)
- Validates data integrity on deserialization

Note: HopEvaluation contains evaluation metadata (can_answer, reasoning, costs, timing)
but not hop-specific context like hop number or chunks added (not available in the model).
"""

import json
from pathlib import Path
from uuid import UUID

from src.lib.logging import get_logger
from src.models.rag_context import DocumentChunk, RAGContext

logger = get_logger(__name__)


class RAGContextSerializationError(Exception):
    """Raised when RAG context serialization/deserialization fails."""

    pass


def serialize_rag_context(
    rag_context: RAGContext,
    hop_evaluations: list | None = None,
    chunk_hop_map: dict | None = None,
    embedding_cost: float = 0.0,
) -> dict:
    """Serialize RAG context to dictionary for JSON export.

    Args:
        rag_context: RAG context with document chunks
        hop_evaluations: Multi-hop evaluation results (optional)
        chunk_hop_map: Mapping of chunk IDs to hop numbers (optional)
        embedding_cost: Embedding cost estimate in USD

    Returns:
        Dictionary containing all RAG context data

    Example output:
        {
            "rag_context": {
                "context_id": "uuid-string",
                "query_id": "uuid-string",
                "total_chunks": 5,
                "avg_relevance": 0.85,
                "meets_threshold": true,
                "document_chunks": [...]
            },
            "hop_evaluations": [
                {
                    "can_answer": false,
                    "reasoning": "Missing information about...",
                    "missing_query": "What are the rules for...",
                    "cost_usd": 0.0001,
                    "retrieval_time_s": 0.5,
                    "evaluation_time_s": 0.3,
                    "filtered_teams_count": 2
                }
            ],
            "chunk_hop_map": {"chunk-uuid": 1, ...},
            "embedding_cost": 0.0001
        }
    """
    # Serialize document chunks
    chunks_data = []
    for chunk in rag_context.document_chunks:
        chunk_dict = {
            "chunk_id": str(chunk.chunk_id),
            "document_id": str(chunk.document_id),
            "text": chunk.text,
            "header": chunk.header,
            "header_level": chunk.header_level,
            "metadata": chunk.metadata,
            "relevance_score": chunk.relevance_score,
            "position_in_doc": chunk.position_in_doc,
        }
        chunks_data.append(chunk_dict)

    # Serialize RAG context
    rag_context_data = {
        "context_id": str(rag_context.context_id),
        "query_id": str(rag_context.query_id),
        "document_chunks": chunks_data,
        "total_chunks": rag_context.total_chunks,
        "avg_relevance": rag_context.avg_relevance,
        "meets_threshold": rag_context.meets_threshold,
    }

    # Serialize hop evaluations (if any)
    hop_evaluations_data = []
    if hop_evaluations:
        for hop_eval in hop_evaluations:
            hop_eval_dict = {
                "can_answer": hop_eval.can_answer,
                "reasoning": hop_eval.reasoning,
                "missing_query": hop_eval.missing_query,
                "cost_usd": hop_eval.cost_usd,
                "retrieval_time_s": hop_eval.retrieval_time_s,
                "evaluation_time_s": hop_eval.evaluation_time_s,
                "filtered_teams_count": hop_eval.filtered_teams_count,
            }
            hop_evaluations_data.append(hop_eval_dict)

    # Serialize chunk-hop map (if any)
    chunk_hop_map_data = {}
    if chunk_hop_map:
        # Convert UUID keys to strings
        chunk_hop_map_data = {str(k): v for k, v in chunk_hop_map.items()}

    return {
        "rag_context": rag_context_data,
        "hop_evaluations": hop_evaluations_data,
        "chunk_hop_map": chunk_hop_map_data,
        "embedding_cost": embedding_cost,
    }


def save_rag_context(
    file_path: str | Path,
    rag_context: RAGContext,
    hop_evaluations: list | None = None,
    chunk_hop_map: dict | None = None,
    embedding_cost: float = 0.0,
) -> None:
    """Save RAG context to JSON file.

    Args:
        file_path: Path to save file (will be created/overwritten)
        rag_context: RAG context with document chunks
        hop_evaluations: Multi-hop evaluation results (optional)
        chunk_hop_map: Mapping of chunk IDs to hop numbers (optional)
        embedding_cost: Embedding cost estimate in USD

    Raises:
        RAGContextSerializationError: If file write fails
    """
    file_path = Path(file_path)

    try:
        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Serialize to dict
        data = serialize_rag_context(
            rag_context=rag_context,
            hop_evaluations=hop_evaluations,
            chunk_hop_map=chunk_hop_map,
            embedding_cost=embedding_cost,
        )

        # Write to file (pretty-printed)
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved RAG context to {file_path}")

    except Exception as e:
        raise RAGContextSerializationError(f"Failed to save RAG context to {file_path}: {e}") from e


def deserialize_rag_context(data: dict) -> tuple[RAGContext, list, dict, float]:
    """Deserialize RAG context from dictionary.

    Args:
        data: Dictionary containing serialized RAG context data

    Returns:
        Tuple of:
        - RAGContext object
        - Hop evaluations list (empty if not present)
        - Chunk-hop map dict (empty if not present)
        - Embedding cost float

    Raises:
        RAGContextSerializationError: If data is malformed or invalid
    """
    try:
        # Extract top-level fields
        rag_context_data = data["rag_context"]
        hop_evaluations_data = data.get("hop_evaluations", [])
        chunk_hop_map_data = data.get("chunk_hop_map", {})
        embedding_cost = data.get("embedding_cost", 0.0)

        # Deserialize document chunks
        chunks = []
        for chunk_dict in rag_context_data["document_chunks"]:
            chunk = DocumentChunk(
                chunk_id=UUID(chunk_dict["chunk_id"]),
                document_id=UUID(chunk_dict["document_id"]),
                text=chunk_dict["text"],
                header=chunk_dict["header"],
                header_level=chunk_dict["header_level"],
                metadata=chunk_dict["metadata"],
                relevance_score=chunk_dict["relevance_score"],
                position_in_doc=chunk_dict["position_in_doc"],
            )
            chunks.append(chunk)

        # Deserialize RAG context
        rag_context = RAGContext(
            context_id=UUID(rag_context_data["context_id"]),
            query_id=UUID(rag_context_data["query_id"]),
            document_chunks=chunks,
            relevance_scores=[chunk.relevance_score for chunk in chunks],
            total_chunks=rag_context_data["total_chunks"],
            avg_relevance=rag_context_data["avg_relevance"],
            meets_threshold=rag_context_data["meets_threshold"],
        )

        # Deserialize hop evaluations (if any)
        hop_evaluations = []
        if hop_evaluations_data:
            # Import here to avoid circular dependency
            from src.services.rag.multi_hop_retriever import HopEvaluation

            for hop_eval_dict in hop_evaluations_data:
                hop_eval = HopEvaluation(
                    can_answer=hop_eval_dict["can_answer"],
                    reasoning=hop_eval_dict["reasoning"],
                    missing_query=hop_eval_dict.get("missing_query"),
                    cost_usd=hop_eval_dict["cost_usd"],
                    retrieval_time_s=hop_eval_dict.get("retrieval_time_s", 0.0),
                    evaluation_time_s=hop_eval_dict.get("evaluation_time_s", 0.0),
                    filtered_teams_count=hop_eval_dict.get("filtered_teams_count", 0),
                )
                hop_evaluations.append(hop_eval)

        # Deserialize chunk-hop map (if any)
        chunk_hop_map = {}
        if chunk_hop_map_data:
            # Convert string keys back to UUIDs
            chunk_hop_map = {UUID(k): v for k, v in chunk_hop_map_data.items()}

        return rag_context, hop_evaluations, chunk_hop_map, embedding_cost

    except KeyError as e:
        raise RAGContextSerializationError(f"Missing required field in RAG context data: {e}") from e
    except (ValueError, TypeError) as e:
        raise RAGContextSerializationError(f"Invalid data format in RAG context: {e}") from e


def load_rag_context(file_path: str | Path) -> tuple[RAGContext, list, dict, float]:
    """Load RAG context from JSON file.

    Args:
        file_path: Path to JSON file containing serialized RAG context

    Returns:
        Tuple of:
        - RAGContext object
        - Hop evaluations list (empty if not present)
        - Chunk-hop map dict (empty if not present)
        - Embedding cost float

    Raises:
        RAGContextSerializationError: If file not found, malformed, or invalid
    """
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
    except Exception as e:
        raise RAGContextSerializationError(f"Failed to load RAG context from {file_path}: {e}") from e
