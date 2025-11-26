"""Data models for RAG test cases.

Based on tests/rag/CLAUDE.md specification.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from src.lib.constants import (
    BM25_B,
    BM25_K1,
    BM25_WEIGHT,
    EMBEDDING_MODEL,
    MARKDOWN_CHUNK_HEADER_LEVEL,
    MAX_CHUNK_LENGTH_FOR_EVALUATION,
    MAXIMUM_FINAL_CHUNK_COUNT,
    RAG_ENABLE_QUERY_EXPANSION,
    RAG_ENABLE_QUERY_NORMALIZATION,
    RAG_HOP_CHUNK_LIMIT,
    RAG_HOP_EVALUATION_MODEL,
    RAG_MAX_CHUNKS,
    RAG_MAX_HOPS,
    RAG_MIN_RELEVANCE,
    RRF_K,
)


@dataclass
class RAGTestCase:
    """RAG test case definition."""

    test_id: str
    query: str
    ground_truth_contexts: list[dict[str, str]]  # List of {key: value} where key is human-readable identifier and value is text for matching

    @classmethod
    def from_yaml(cls, file_path: Path) -> list["RAGTestCase"]:
        """Load test case(s) from YAML file.

        Supports both formats:
        1. Single test case (dict with test_id, query, ground_truth_contexts)
        2. Multiple test cases (list of dicts)

        Args:
            file_path: Path to YAML file

        Returns:
            List of RAGTestCase instances (even if single test)
        """
        with open(file_path) as f:
            data = yaml.safe_load(f)

        # Handle both single test case (dict) and multiple test cases (list)
        if isinstance(data, dict):
            # Single test case format
            return [
                cls(
                    test_id=data["test_id"],
                    query=data["query"],
                    ground_truth_contexts=data["ground_truth_contexts"],
                )
            ]
        elif isinstance(data, list):
            # Multiple test cases format
            return [
                cls(
                    test_id=test_case["test_id"],
                    query=test_case["query"],
                    ground_truth_contexts=test_case["ground_truth_contexts"],
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
    ground_truth_contexts: list[str]  # Keys only (for display)
    retrieved_chunks: list[str]  # Headers of retrieved chunks in order
    retrieved_chunk_texts: list[str]  # Full text of retrieved chunks
    retrieved_relevance_scores: list[float]  # Relevance scores for each retrieved chunk
    retrieved_chunk_metadata: list[dict]  # Metadata including vector_similarity, rrf_score, etc.

    # Custom IR Metrics
    map_score: float  # Mean Average Precision
    recall_at_5: float  # Recall@5
    recall_at_10: float  # Recall@10
    recall_at_all: (
        float  # Recall@All (percentage of ground_truth_contexts found, regardless of position)
    )
    precision_at_3: float  # Precision@3
    precision_at_5: float  # Precision@5
    mrr: float  # Mean Reciprocal Rank

    # Details
    found_chunks: list[str]  # Which ground_truth_contexts were found
    missing_chunks: list[str]  # Which ground_truth_contexts were not found
    ranks_of_required: list[int]  # Rank positions of ground_truth_contexts (1-indexed)

    # Performance
    retrieval_time_seconds: float  # Time taken for retrieval
    embedding_cost_usd: float  # Cost of generating query embedding

    # Optional fields (with defaults)
    ground_truth_values: dict[str, str] | None = None  # Mapping of key -> value (for matching in reports)
    run_number: int = 1  # For multi-run tests

    # Ragas Metrics (optional, calculated if ground_truth_contexts provided)
    ragas_context_precision: float | None = None  # Ragas context precision (0-1)
    ragas_context_recall: float | None = None  # Ragas context recall (0-1)

    # Multi-hop retrieval data (if enabled)
    hops_used: int = 0  # Number of hops performed
    hop_evaluations: list[dict] = (
        None  # List of hop evaluation dicts (can_answer, reasoning, missing_query)
    )
    chunk_hop_numbers: list[int] = (
        None  # Hop number for each retrieved chunk (parallel to retrieved_chunks)
    )
    filtered_teams_count: int = 0  # Number of teams after filtering for hop evaluation

    # Ground truth rank analysis (for MAXIMUM_FINAL_CHUNK_COUNT tuning)
    max_ground_truth_rank: int = 0  # Highest rank position where a ground truth was found


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

    # Test metadata
    runs_per_test: int = 1  # Number of runs per test case
    total_ground_truths: int = 0  # Total number of ground truth contexts across all test cases (in single run)
    test_set_codename: str | None = None  # Test set codename from YAML file

    # Multi-run statistics (if applicable)
    std_dev_map: float = 0.0
    std_dev_recall_at_5: float = 0.0
    std_dev_recall_at_all: float = 0.0
    std_dev_precision_at_3: float = 0.0

    # Ragas aggregate metrics (optional, if any tests have ground_truth_contexts)
    mean_ragas_context_precision: float | None = None
    mean_ragas_context_recall: float | None = None
    std_dev_ragas_context_precision: float = 0.0
    std_dev_ragas_context_recall: float = 0.0

    # Configuration
    rag_max_chunks: int = RAG_MAX_CHUNKS
    rag_min_relevance: float = RAG_MIN_RELEVANCE
    embedding_model: str = EMBEDDING_MODEL
    chunk_header_level: int = MARKDOWN_CHUNK_HEADER_LEVEL
    max_chunk_length_for_evaluation: int = MAX_CHUNK_LENGTH_FOR_EVALUATION
    rrf_k: int = RRF_K
    bm25_k1: float = BM25_K1
    bm25_b: float = BM25_B
    bm25_weight: float = BM25_WEIGHT
    vector_weight: float = 1.0 - BM25_WEIGHT
    hybrid_enabled: bool = True
    query_normalization_enabled: bool = RAG_ENABLE_QUERY_NORMALIZATION
    query_expansion_enabled: bool = RAG_ENABLE_QUERY_EXPANSION

    # Multi-hop configuration
    rag_max_hops: int = RAG_MAX_HOPS
    rag_hop_chunk_limit: int = RAG_HOP_CHUNK_LIMIT
    rag_hop_evaluation_model: str = RAG_HOP_EVALUATION_MODEL
    maximum_final_chunk_count: int = MAXIMUM_FINAL_CHUNK_COUNT

    # Multi-hop statistics
    avg_hops_used: float = 0.0  # Average hops performed per test
    hop_evaluation_cost_usd: float = 0.0  # Total cost for hop evaluation LLM calls
    avg_ground_truth_found_improvement: float = (
        0.0  # Average number of ground truth chunks found via hops
    )
    avg_filtered_teams_count: float = 0.0  # Average number of teams after filtering for hop evaluation
    ground_truth_chunks_per_hop: list[int] = (
        None  # List of ground truth chunks found in each hop [hop1, hop2, ...]
    )
    hop_can_answer_recall: float = (
        0.0  # Recall: times ground truth missing & hop made / total times ground truth missing
    )
    hop_can_answer_precision: float = (
        0.0  # Precision: times ground truth missing & hop made / total hops made
    )

    # Ground truth rank analysis (for MAXIMUM_FINAL_CHUNK_COUNT tuning)
    max_ground_truth_rank_found: int = 0  # Highest rank where any ground truth was found across all tests
    avg_max_ground_truth_rank: float = 0.0  # Average max rank per test
