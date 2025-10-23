"""Data models for RAG test cases.

Based on tests/rag/CLAUDE.md specification.
"""

from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path
import yaml

from src.lib.constants import (
    RAG_MAX_CHUNKS,
    RAG_MIN_RELEVANCE,
    EMBEDDING_MODEL,
    RRF_K,
    BM25_K1,
    BM25_B,
    RAG_ENABLE_QUERY_NORMALIZATION,
    RAG_ENABLE_QUERY_EXPANSION,
)


@dataclass
class RAGTestCase:
    """RAG test case definition."""

    test_id: str
    query: str
    required_chunks: List[str]  # List of chunk headers that must be retrieved (legacy)

    # Optional Ragas fields (backward compatible)
    ground_truth_contexts: Optional[List[str]] = None  # Substrings of expected chunks for Ragas evaluation

    def get_ground_truth_contexts(self) -> List[str]:
        """Get ground truth contexts for Ragas evaluation.

        Falls back to required_chunks if ground_truth_contexts is not explicitly set.
        This allows using the same test cases for both custom IR metrics and Ragas metrics.

        Returns:
            List of ground truth context strings
        """
        if self.ground_truth_contexts is not None:
            return self.ground_truth_contexts
        else:
            # Fall back to required_chunks
            return self.required_chunks

    @classmethod
    def from_yaml(cls, file_path: Path) -> List["RAGTestCase"]:
        """Load test case(s) from YAML file.

        Supports both formats:
        1. Single test case (dict with test_id, query, required_chunks)
        2. Multiple test cases (list of dicts)

        Args:
            file_path: Path to YAML file

        Returns:
            List of RAGTestCase instances (even if single test)
        """
        with open(file_path, "r") as f:
            data = yaml.safe_load(f)

        # Handle both single test case (dict) and multiple test cases (list)
        if isinstance(data, dict):
            # Single test case format
            return [cls(
                test_id=data["test_id"],
                query=data["query"],
                required_chunks=data["required_chunks"],
                ground_truth_contexts=data.get("ground_truth_contexts"),  # Optional
            )]
        elif isinstance(data, list):
            # Multiple test cases format
            return [
                cls(
                    test_id=test_case["test_id"],
                    query=test_case["query"],
                    required_chunks=test_case["required_chunks"],
                    ground_truth_contexts=test_case.get("ground_truth_contexts"),  # Optional
                )
                for test_case in data
            ]
        else:
            raise ValueError(
                f"Invalid YAML format in {file_path}. "
                "Expected dict (single test) or list (multiple tests)."
            )


@dataclass
class RAGTestResult:
    """Result of a single RAG test run."""

    test_id: str
    query: str
    required_chunks: List[str]
    retrieved_chunks: List[str]  # Headers of retrieved chunks in order
    retrieved_chunk_texts: List[str]  # Full text of retrieved chunks
    retrieved_relevance_scores: List[float]  # Relevance scores for each retrieved chunk
    retrieved_chunk_metadata: List[dict]  # Metadata including vector_similarity, rrf_score, etc.

    # Custom IR Metrics
    map_score: float  # Mean Average Precision
    recall_at_5: float  # Recall@5
    recall_at_10: float  # Recall@10
    recall_at_all: float  # Recall@All (percentage of required chunks found, regardless of position)
    precision_at_3: float  # Precision@3
    precision_at_5: float  # Precision@5
    mrr: float  # Mean Reciprocal Rank

    # Details
    found_chunks: List[str]  # Which required chunks were found
    missing_chunks: List[str]  # Which required chunks were not found
    ranks_of_required: List[int]  # Rank positions of required chunks (1-indexed)

    # Performance
    retrieval_time_seconds: float  # Time taken for retrieval
    embedding_cost_usd: float  # Cost of generating query embedding

    run_number: int = 1  # For multi-run tests

    # Ragas Metrics (optional, calculated if ground_truth_contexts provided)
    ragas_context_precision: Optional[float] = None  # Ragas context precision (0-1)
    ragas_context_recall: Optional[float] = None  # Ragas context recall (0-1)


@dataclass
class RAGTestSummary:
    """Aggregated results across multiple tests."""

    total_tests: int
    mean_map: float
    mean_recall_at_5: float
    mean_recall_at_all: float
    mean_recall_at_10: float
    mean_precision_at_3: float
    mean_precision_at_5: float
    mean_mrr: float

    # Performance metrics
    total_time_seconds: float  # Total time for all tests
    avg_retrieval_time_seconds: float  # Average time per retrieval
    total_cost_usd: float  # Total cost for all embeddings

    # Multi-run statistics (if applicable)
    std_dev_map: float = 0.0
    std_dev_recall_at_5: float = 0.0
    std_dev_recall_at_all: float = 0.0
    std_dev_precision_at_3: float = 0.0

    # Ragas aggregate metrics (optional, if any tests have ground_truth_contexts)
    mean_ragas_context_precision: Optional[float] = None
    mean_ragas_context_recall: Optional[float] = None
    std_dev_ragas_context_precision: float = 0.0
    std_dev_ragas_context_recall: float = 0.0

    # Configuration
    rag_max_chunks: int = RAG_MAX_CHUNKS
    rag_min_relevance: float = RAG_MIN_RELEVANCE
    embedding_model: str = EMBEDDING_MODEL
    rrf_k: int = RRF_K
    bm25_k1: float = BM25_K1
    bm25_b: float = BM25_B
    hybrid_enabled: bool = True
    query_normalization_enabled: bool = RAG_ENABLE_QUERY_NORMALIZATION
    query_expansion_enabled: bool = RAG_ENABLE_QUERY_EXPANSION
