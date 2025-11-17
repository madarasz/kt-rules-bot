"""RAG retrieval request models."""

from dataclasses import dataclass

from src.lib.constants import RAG_MAX_CHUNKS, RAG_MAX_HOPS, RAG_MIN_RELEVANCE


@dataclass
class RetrieveRequest:
    """RAG retrieval request parameters."""

    query: str  # User question (sanitized)
    context_key: str  # "{channel_id}:{user_id}" for conversation tracking
    max_chunks: int = RAG_MAX_CHUNKS  # Maximum document chunks to retrieve
    min_relevance: float = RAG_MIN_RELEVANCE  # Minimum cosine similarity threshold
    use_hybrid: bool = True  # Enable hybrid search (BM25 + vector)
    use_multi_hop: bool = RAG_MAX_HOPS > 0  # Enable multi-hop retrieval (if max_hops > 0)
