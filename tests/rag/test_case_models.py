"""Data models for RAG test cases.

Based on tests/rag/CLAUDE.md specification.
"""

from dataclasses import dataclass
from typing import List
from pathlib import Path
import yaml


@dataclass
class RAGTestCase:
    """RAG test case definition."""

    test_id: str
    query: str
    required_chunks: List[str]  # List of chunk headers that must be retrieved

    @classmethod
    def from_yaml(cls, file_path: Path) -> "RAGTestCase":
        """Load test case from YAML file.

        Args:
            file_path: Path to YAML file

        Returns:
            RAGTestCase instance
        """
        with open(file_path, "r") as f:
            data = yaml.safe_load(f)

        return cls(
            test_id=data["test_id"],
            query=data["query"],
            required_chunks=data["required_chunks"],
        )


@dataclass
class RAGTestResult:
    """Result of a single RAG test run."""

    test_id: str
    query: str
    required_chunks: List[str]
    retrieved_chunks: List[str]  # Headers of retrieved chunks in order
    retrieved_chunk_texts: List[str]  # Full text of retrieved chunks

    # Metrics
    map_score: float  # Mean Average Precision
    recall_at_5: float  # Recall@5
    recall_at_10: float  # Recall@10
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


@dataclass
class RAGTestSummary:
    """Aggregated results across multiple tests."""

    total_tests: int
    mean_map: float
    mean_recall_at_5: float
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
    std_dev_precision_at_3: float = 0.0

    # Configuration
    rag_max_chunks: int = 15
    rag_min_relevance: float = 0.45
    embedding_model: str = "text-embedding-3-small"
    rrf_k: int = 60
    hybrid_enabled: bool = True
