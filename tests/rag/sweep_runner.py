"""RAG parameter sweep runner for optimization experiments.

Runs RAG tests with different parameter values to find optimal configurations.
"""

from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
import itertools

from tests.rag.test_runner import RAGTestRunner
from tests.rag.test_case_models import RAGTestResult, RAGTestSummary
from src.lib.constants import (
    RAG_MAX_CHUNKS,
    RAG_MIN_RELEVANCE,
    RRF_K,
    BM25_K1,
    BM25_B,
    BM25_WEIGHT,
    EMBEDDING_MODEL,
    MARKDOWN_CHUNK_HEADER_LEVEL,
)
from src.lib.logging import get_logger
from src.services.rag.vector_db import VectorDBService
from src.services.rag.ingestor import RAGIngestor
from src.services.rag.chunker import MarkdownChunker
from src.services.rag.embeddings import EmbeddingService
from src.services.rag.validator import DocumentValidator
from src.models.rule_document import RuleDocument
from src.lib.tokens import get_embedding_token_limit

logger = get_logger(__name__)


@dataclass
class ParameterConfig:
    """Configuration for a single parameter sweep run."""

    max_chunks: int = RAG_MAX_CHUNKS
    min_relevance: float = RAG_MIN_RELEVANCE
    rrf_k: int = RRF_K
    bm25_k1: float = BM25_K1
    bm25_b: float = BM25_B
    bm25_weight: float = BM25_WEIGHT
    embedding_model: str = EMBEDDING_MODEL
    chunk_header_level: int = MARKDOWN_CHUNK_HEADER_LEVEL

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    def get_identifier(self) -> str:
        """Get unique identifier string for this configuration."""
        # Shorten embedding model name for file paths
        embed_short = self.embedding_model.replace("text-embedding-", "embed-").replace("-", "")
        return (
            f"mc{self.max_chunks}_"
            f"mr{self.min_relevance:.2f}_"
            f"rrf{self.rrf_k}_"
            f"bm25k1{self.bm25_k1:.1f}_"
            f"bm25b{self.bm25_b:.2f}_"
            f"bm25w{self.bm25_weight:.2f}_"
            f"em{embed_short}_"
            f"chl{self.chunk_header_level}"
        )

    def get_description(self) -> str:
        """Get human-readable description."""
        return (
            f"max_chunks={self.max_chunks}, "
            f"min_relevance={self.min_relevance}, "
            f"rrf_k={self.rrf_k}, "
            f"bm25_k1={self.bm25_k1}, "
            f"bm25_b={self.bm25_b}, "
            f"bm25_weight={self.bm25_weight}, "
            f"embedding_model={self.embedding_model}, "
            f"chunk_header_level={self.chunk_header_level}"
        )


@dataclass
class SweepResult:
    """Result of a single parameter configuration run."""

    config: ParameterConfig
    results: List[RAGTestResult]
    summary: RAGTestSummary
    total_time: float


class RAGSweepRunner:
    """Runs parameter sweeps for RAG optimization."""

    def __init__(
        self,
        test_cases_dir: Path = Path("tests/rag/test_cases"),
        results_base_dir: Path = Path("tests/rag/results"),
        use_ragas: bool = False,
    ):
        """Initialize sweep runner.

        Args:
            test_cases_dir: Directory containing YAML test cases
            results_base_dir: Base directory for results
            use_ragas: Whether to calculate Ragas metrics
        """
        self.test_cases_dir = test_cases_dir
        self.results_base_dir = results_base_dir
        self.use_ragas = use_ragas

        # Track last ingested configuration to avoid unnecessary reingestion
        self.last_ingested_embedding_model: Optional[str] = None
        self.last_ingested_chunk_header_level: Optional[int] = None

        logger.info(
            "rag_sweep_runner_initialized",
            test_cases_dir=str(test_cases_dir),
            results_base_dir=str(results_base_dir),
            use_ragas=use_ragas,
        )

    def sweep_parameter(
        self,
        param_name: str,
        param_values: List[Any],
        test_id: Optional[str] = None,
        runs: int = 1,
        base_config: Optional[ParameterConfig] = None,
    ) -> List[SweepResult]:
        """Run tests sweeping a single parameter.

        Args:
            param_name: Name of parameter to sweep (e.g., "rrf_k", "max_chunks")
            param_values: List of values to test
            test_id: Optional specific test ID (otherwise run all)
            runs: Number of runs per configuration
            base_config: Base configuration (defaults used if None)

        Returns:
            List of SweepResult objects (one per parameter value)
        """
        if base_config is None:
            base_config = ParameterConfig()

        logger.info(
            "starting_parameter_sweep",
            param_name=param_name,
            values=param_values,
            test_id=test_id,
            runs=runs,
        )

        sweep_results = []

        for value in param_values:
            # Create configuration with this parameter value
            config = ParameterConfig(**asdict(base_config))
            setattr(config, param_name, value)

            logger.info(
                "running_sweep_config",
                param_name=param_name,
                value=value,
                config=config.get_description(),
            )

            # Run tests with this configuration
            result = self._run_config(
                config=config,
                test_id=test_id,
                runs=runs,
            )

            sweep_results.append(result)

            logger.info(
                "sweep_config_completed",
                param_name=param_name,
                value=value,
                map_score=result.summary.mean_map,
            )

        logger.info(
            "parameter_sweep_completed",
            param_name=param_name,
            configs_tested=len(sweep_results),
        )

        return sweep_results

    def grid_search(
        self,
        param_grid: Dict[str, List[Any]],
        test_id: Optional[str] = None,
        runs: int = 1,
    ) -> List[SweepResult]:
        """Run tests for all combinations of parameters (grid search).

        Args:
            param_grid: Dictionary mapping parameter names to lists of values
                Example: {"max_chunks": [10, 15, 20], "rrf_k": [50, 60, 70]}
            test_id: Optional specific test ID (otherwise run all)
            runs: Number of runs per configuration

        Returns:
            List of SweepResult objects (one per combination)
        """
        # Generate all parameter combinations
        param_names = list(param_grid.keys())
        param_value_lists = [param_grid[name] for name in param_names]
        combinations = list(itertools.product(*param_value_lists))

        total_configs = len(combinations)

        logger.info(
            "starting_grid_search",
            parameters=param_names,
            combinations=total_configs,
            test_id=test_id,
            runs=runs,
        )

        sweep_results = []

        for i, combination in enumerate(combinations, start=1):
            # Create configuration for this combination
            config = ParameterConfig()
            for param_name, value in zip(param_names, combination):
                setattr(config, param_name, value)

            logger.info(
                "running_grid_config",
                progress=f"{i}/{total_configs}",
                config=config.get_description(),
            )

            # Run tests with this configuration
            result = self._run_config(
                config=config,
                test_id=test_id,
                runs=runs,
            )

            sweep_results.append(result)

            logger.info(
                "grid_config_completed",
                progress=f"{i}/{total_configs}",
                map_score=result.summary.mean_map,
            )

        logger.info(
            "grid_search_completed",
            total_configs=total_configs,
        )

        return sweep_results

    def _run_config(
        self,
        config: ParameterConfig,
        test_id: Optional[str],
        runs: int,
    ) -> SweepResult:
        """Run tests for a single configuration.

        Args:
            config: Parameter configuration
            test_id: Optional specific test ID
            runs: Number of runs

        Returns:
            SweepResult
        """
        # Check if we need to reset and reingest due to embedding or chunking changes
        # Compare against last ingested config, not constants.py values
        needs_reingest = (
            self.last_ingested_embedding_model is None
            or self.last_ingested_chunk_header_level is None
            or config.embedding_model != self.last_ingested_embedding_model
            or config.chunk_header_level != self.last_ingested_chunk_header_level
        )

        if needs_reingest:
            logger.info(
                "config_requires_reingest",
                embedding_model=config.embedding_model,
                chunk_header_level=config.chunk_header_level,
                last_ingested_embedding_model=self.last_ingested_embedding_model,
                last_ingested_chunk_header_level=self.last_ingested_chunk_header_level,
            )

            if self.last_ingested_embedding_model is None:
                print(f"\n⚠️  Initial database setup required:")
            else:
                print(f"\n⚠️  Configuration change requires database reset and re-ingestion:")
                print(f"   Previous embedding model: {self.last_ingested_embedding_model}")
                print(f"   Previous chunk header level: {self.last_ingested_chunk_header_level}")

            print(f"   New embedding model: {config.embedding_model}")
            print(f"   New chunk header level: {config.chunk_header_level}")

            self._reset_and_reingest(
                embedding_model=config.embedding_model,
                chunk_header_level=config.chunk_header_level,
            )

            # Update tracking variables
            self.last_ingested_embedding_model = config.embedding_model
            self.last_ingested_chunk_header_level = config.chunk_header_level

        # Create test runner with this configuration
        runner = RAGTestRunner(
            test_cases_dir=self.test_cases_dir,
            rrf_k=config.rrf_k,
            bm25_k1=config.bm25_k1,
            bm25_b=config.bm25_b,
            bm25_weight=config.bm25_weight,
            embedding_model=config.embedding_model,
            use_ragas=self.use_ragas,
        )

        # Run tests
        results, total_time = runner.run_tests(
            test_id=test_id,
            runs=runs,
            max_chunks=config.max_chunks,
            min_relevance=config.min_relevance,
        )

        # Calculate summary
        summary = runner.calculate_summary(
            results=results,
            total_time_seconds=total_time,
            max_chunks=config.max_chunks,
            min_relevance=config.min_relevance,
        )

        return SweepResult(
            config=config,
            results=results,
            summary=summary,
            total_time=total_time,
        )

    def _reset_and_reingest(
        self,
        embedding_model: str,
        chunk_header_level: int,
    ) -> None:
        """Reset vector DB and reingest rules with custom parameters.

        Args:
            embedding_model: Embedding model to use
            chunk_header_level: Markdown chunk header level (2-4)
        """
        print(f"\n🗑️  Resetting vector database...")

        # Reset vector DB
        vector_db = VectorDBService()
        count_before = vector_db.get_count()
        vector_db.reset()

        logger.info(
            "vector_db_reset_for_sweep",
            embeddings_deleted=count_before,
        )

        print(f"   Deleted {count_before} embeddings")

        # Re-ingest with custom parameters
        print(f"\n📥 Re-ingesting rules...")
        print(f"   Embedding model: {embedding_model}")
        print(f"   Chunk header level: {chunk_header_level}")

        # Load rule documents with proper validation
        rules_dir = Path("extracted-rules")
        markdown_files = list(rules_dir.glob("**/*.md"))
        validator = DocumentValidator()

        documents = []
        for md_file in markdown_files:
            try:
                content = md_file.read_text(encoding="utf-8")

                # Validate and extract metadata
                is_valid, error, metadata = validator.validate_content(
                    content, md_file.name
                )

                if not is_valid:
                    logger.warning(f"Skipping {md_file.name}: {error}")
                    print(f"   ⚠️  Skipping {md_file.name}: {error}")
                    continue

                # Create RuleDocument using the class method
                doc = RuleDocument.from_markdown_file(
                    filename=md_file.name,
                    content=content,
                    metadata=metadata,
                )
                documents.append(doc)
            except Exception as e:
                logger.warning(f"Failed to load {md_file.name}: {e}")
                print(f"   ⚠️  Failed to load {md_file.name}: {e}")
                continue

        # Create custom services
        chunker = MarkdownChunker(
            chunk_level=chunk_header_level,
            model=embedding_model,
        )
        embedding_service = EmbeddingService(model=embedding_model)

        # Ingest
        ingestor = RAGIngestor(
            chunker=chunker,
            embedding_service=embedding_service,
            vector_db_service=vector_db,
        )

        result = ingestor.ingest(documents)

        print(f"   ✅ Ingested {result.documents_processed} documents")
        print(f"   ✅ Created {result.embedding_count} embeddings")

        logger.info(
            "reingest_completed_for_sweep",
            documents_processed=result.documents_processed,
            embedding_count=result.embedding_count,
            embedding_model=embedding_model,
            chunk_header_level=chunk_header_level,
        )

    def save_sweep_results(
        self,
        sweep_results: List[SweepResult],
        sweep_name: str,
    ) -> Path:
        """Save sweep results to timestamped directory.

        Args:
            sweep_results: List of sweep results
            sweep_name: Name for this sweep (e.g., "rrf_k_sweep", "grid_search")

        Returns:
            Path to results directory
        """
        # Create timestamped directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        sweep_dir = self.results_base_dir / f"{timestamp}_{sweep_name}"
        sweep_dir.mkdir(parents=True, exist_ok=True)

        # Save each configuration's results in subdirectory
        for i, sweep_result in enumerate(sweep_results):
            config_dir = sweep_dir / f"config_{i+1}_{sweep_result.config.get_identifier()}"
            config_dir.mkdir(parents=True, exist_ok=True)

            # Save configuration file
            config_file = config_dir / "config.txt"
            with open(config_file, "w") as f:
                f.write(sweep_result.config.get_description())

        logger.info(
            "sweep_results_saved",
            sweep_dir=str(sweep_dir),
            num_configs=len(sweep_results),
        )

        return sweep_dir
