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
from src.lib.constants import RAG_MAX_CHUNKS, RAG_MIN_RELEVANCE, RRF_K, BM25_K1, BM25_B
from src.lib.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ParameterConfig:
    """Configuration for a single parameter sweep run."""

    max_chunks: int = RAG_MAX_CHUNKS
    min_relevance: float = RAG_MIN_RELEVANCE
    rrf_k: int = RRF_K
    bm25_k1: float = BM25_K1
    bm25_b: float = BM25_B

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    def get_identifier(self) -> str:
        """Get unique identifier string for this configuration."""
        return (
            f"mc{self.max_chunks}_"
            f"mr{self.min_relevance:.2f}_"
            f"rrf{self.rrf_k}_"
            f"bm25k1{self.bm25_k1:.1f}_"
            f"bm25b{self.bm25_b:.2f}"
        )

    def get_description(self) -> str:
        """Get human-readable description."""
        return (
            f"max_chunks={self.max_chunks}, "
            f"min_relevance={self.min_relevance}, "
            f"rrf_k={self.rrf_k}, "
            f"bm25_k1={self.bm25_k1}, "
            f"bm25_b={self.bm25_b}"
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
    ):
        """Initialize sweep runner.

        Args:
            test_cases_dir: Directory containing YAML test cases
            results_base_dir: Base directory for results
        """
        self.test_cases_dir = test_cases_dir
        self.results_base_dir = results_base_dir

        logger.info(
            "rag_sweep_runner_initialized",
            test_cases_dir=str(test_cases_dir),
            results_base_dir=str(results_base_dir),
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
        # Create test runner with this configuration
        runner = RAGTestRunner(
            test_cases_dir=self.test_cases_dir,
            rrf_k=config.rrf_k,
            bm25_k1=config.bm25_k1,
            bm25_b=config.bm25_b,
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
        sweep_dir = self.results_base_dir / f"{sweep_name}_{timestamp}"
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
