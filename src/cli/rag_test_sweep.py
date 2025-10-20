"""CLI command to run RAG parameter sweeps for optimization.

Usage:
    python -m src.cli rag-test-sweep --param rrf_k --values 40,60,80 --runs 10
    python -m src.cli rag-test-sweep --grid --max-chunks 10,15,20 --min-relevance 0.4,0.5
    python -m src.cli rag-test-sweep --param embedding_model --values text-embedding-3-small,text-embedding-3-large
    python -m src.cli rag-test-sweep --param chunk_header_level --values 2,3,4

Note: Changes to embedding_model or chunk_header_level will automatically reset the
      vector database and re-ingest all documents with the new settings.
"""

import sys
from pathlib import Path
from typing import List, Dict, Any

from tests.rag.sweep_runner import RAGSweepRunner, ParameterConfig
from tests.rag.reporting.comparison_generator import ComparisonGenerator
from src.lib.constants import RAG_MAX_CHUNKS, RAG_MIN_RELEVANCE
from src.lib.logging import get_logger

logger = get_logger(__name__)


def rag_test_sweep(
    param: str | None = None,
    values: str | None = None,
    grid: bool = False,
    test_id: str | None = None,
    runs: int = 1,
    max_chunks: str | None = None,
    min_relevance: str | None = None,
    rrf_k: str | None = None,
    bm25_k1: str | None = None,
    bm25_b: str | None = None,
    bm25_weight: str | None = None,
    embedding_model: str | None = None,
    chunk_header_level: str | None = None,
    use_ragas: bool = False,
) -> None:
    """Run RAG parameter sweep tests.

    Args:
        param: Parameter name to sweep (single-parameter mode)
        values: Comma-separated values for the parameter
        grid: Enable grid search mode
        test_id: Specific test ID to run (otherwise run all)
        runs: Number of times to run each configuration
        max_chunks: Comma-separated max_chunks values (grid mode)
        min_relevance: Comma-separated min_relevance values (grid mode)
        rrf_k: Comma-separated rrf_k values (grid mode)
        bm25_k1: Comma-separated bm25_k1 values (grid mode)
        bm25_b: Comma-separated bm25_b values (grid mode)
        bm25_weight: Comma-separated bm25_weight values (grid mode)
        embedding_model: Comma-separated embedding_model values (grid mode)
        chunk_header_level: Comma-separated chunk_header_level values (grid mode)
        use_ragas: Calculate Ragas metrics alongside custom metrics
    """
    # Validate arguments
    if not grid and (not param or not values):
        print("Error: Either --grid mode or --param with --values must be specified")
        sys.exit(1)

    if grid and param:
        print("Error: Cannot use both --grid and --param modes")
        sys.exit(1)

    # Parse parameter values
    try:
        if grid:
            param_grid = _parse_grid_params(
                max_chunks=max_chunks,
                min_relevance=min_relevance,
                rrf_k=rrf_k,
                bm25_k1=bm25_k1,
                bm25_b=bm25_b,
                bm25_weight=bm25_weight,
                embedding_model=embedding_model,
                chunk_header_level=chunk_header_level,
            )

            if not param_grid:
                print("Error: Grid search requires at least one parameter with multiple values")
                sys.exit(1)

            total_configs = 1
            for param_values in param_grid.values():
                total_configs *= len(param_values)

        else:
            param_values = _parse_parameter_values(param, values)

    except ValueError as e:
        print(f"Error parsing parameter values: {e}")
        sys.exit(1)

    if grid:
        print(f"Grid Search Mode")
        print(f"Parameters:")
        for pname, pvalues in param_grid.items():
            print(f"  {pname}: {pvalues}")
        print(f"Total configurations: {total_configs}")
    else:
        print(f"Parameter Sweep Mode")
        print(f"Parameter: {param}")
        print(f"Values: {param_values}")
        print(f"Configurations: {len(param_values)}")

    print(f"Test ID: {test_id or 'all'}")
    print(f"Runs per configuration: {runs}")
    print(f"Total test executions: {(total_configs if grid else len(param_values)) * runs}")
    print("")

    # Initialize runners
    sweep_runner = RAGSweepRunner(use_ragas=use_ragas)
    comparison_gen = ComparisonGenerator()

    try:
        if grid:
            # Grid search mode
            logger.info(
                "starting_grid_search",
                parameters=list(param_grid.keys()),
                test_id=test_id,
                runs=runs,
                use_ragas=use_ragas,
            )

            print(f"\nRunning grid search...")
            print(f"Parameters: {list(param_grid.keys())}")
            print(f"Total configurations: {total_configs}")
            if use_ragas:
                print(f"Evaluation mode: Custom + Ragas metrics")
            print("")

            sweep_results = sweep_runner.grid_search(
                param_grid=param_grid,
                test_id=test_id,
                runs=runs,
            )

            # Generate report
            sweep_name = "grid_search"
            output_dir = sweep_runner.save_sweep_results(sweep_results, sweep_name)

            print("\nGenerating comparison report and charts...")
            comparison_gen.generate_grid_search_report(
                sweep_results=sweep_results,
                param_grid=param_grid,
                output_dir=output_dir,
            )

        else:
            # Single parameter sweep mode
            logger.info(
                "starting_parameter_sweep",
                param_name=param,
                values=param_values,
                test_id=test_id,
                runs=runs,
                use_ragas=use_ragas,
            )

            print(f"\nRunning parameter sweep...")
            print(f"Parameter: {param}")
            print(f"Values: {param_values}")
            if use_ragas:
                print(f"Evaluation mode: Custom + Ragas metrics")
            print("")

            sweep_results = sweep_runner.sweep_parameter(
                param_name=param,
                param_values=param_values,
                test_id=test_id,
                runs=runs,
            )

            # Generate report
            sweep_name = f"{param}_sweep"
            output_dir = sweep_runner.save_sweep_results(sweep_results, sweep_name)

            print("\nGenerating comparison report and charts...")
            comparison_gen.generate_parameter_sweep_report(
                sweep_results=sweep_results,
                param_name=param,
                output_dir=output_dir,
            )

        # Print summary
        print("\n" + "=" * 80)
        print("SWEEP COMPLETED")
        print("=" * 80)

        # Find best configuration
        best_result = max(sweep_results, key=lambda r: r.summary.mean_map)

        print(f"Best configuration:")
        print(f"  {best_result.config.get_description()}")
        print(f"  MAP: {best_result.summary.mean_map:.3f}")
        print(f"  Recall@5: {best_result.summary.mean_recall_at_5:.3f}")
        print(f"  Recall@All: {best_result.summary.mean_recall_at_all:.3f}")
        print(f"  Precision@3: {best_result.summary.mean_precision_at_3:.3f}")
        print("")

        print(f"Report saved to: {output_dir / 'comparison_report.md'}")
        print(f"Charts saved to: {output_dir / 'charts/'}")
        print(f"CSV data saved to: {output_dir / ('comparison_metrics.csv' if not grid else 'grid_results.csv')}")
        print("")

        logger.info(
            "sweep_completed",
            output_dir=str(output_dir),
            best_map=best_result.summary.mean_map,
        )

    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("\nMake sure test cases exist in tests/rag/test_cases/")
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error("sweep_failed", error=str(e))
        print(f"Error running parameter sweep: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def _parse_parameter_values(param_name: str, values_str: str) -> List:
    """Parse comma-separated parameter values.

    Args:
        param_name: Name of parameter
        values_str: Comma-separated values string

    Returns:
        List of parsed values (int, float, or str depending on parameter)

    Raises:
        ValueError: If values cannot be parsed
    """
    values_list = [v.strip() for v in values_str.split(',')]

    # Determine type based on parameter name
    if param_name in ['max_chunks', 'rrf_k', 'chunk_header_level']:
        # Integer parameters
        return [int(v) for v in values_list]
    elif param_name in ['min_relevance', 'bm25_k1', 'bm25_b', 'bm25_weight']:
        # Float parameters
        return [float(v) for v in values_list]
    elif param_name in ['embedding_model']:
        # String parameters
        return values_list
    else:
        raise ValueError(f"Unknown parameter: {param_name}")


def _parse_grid_params(
    max_chunks: str | None,
    min_relevance: str | None,
    rrf_k: str | None,
    bm25_k1: str | None,
    bm25_b: str | None,
    bm25_weight: str | None,
    embedding_model: str | None,
    chunk_header_level: str | None,
) -> Dict[str, List]:
    """Parse grid search parameters.

    Args:
        max_chunks: Comma-separated max_chunks values
        min_relevance: Comma-separated min_relevance values
        rrf_k: Comma-separated rrf_k values
        bm25_k1: Comma-separated bm25_k1 values
        bm25_b: Comma-separated bm25_b values
        bm25_weight: Comma-separated bm25_weight values
        embedding_model: Comma-separated embedding_model values
        chunk_header_level: Comma-separated chunk_header_level values

    Returns:
        Dictionary mapping parameter names to value lists

    Raises:
        ValueError: If values cannot be parsed
    """
    param_grid = {}

    if max_chunks:
        param_grid['max_chunks'] = [int(v.strip()) for v in max_chunks.split(',')]

    if min_relevance:
        param_grid['min_relevance'] = [float(v.strip()) for v in min_relevance.split(',')]

    if rrf_k:
        param_grid['rrf_k'] = [int(v.strip()) for v in rrf_k.split(',')]

    if bm25_k1:
        param_grid['bm25_k1'] = [float(v.strip()) for v in bm25_k1.split(',')]

    if bm25_b:
        param_grid['bm25_b'] = [float(v.strip()) for v in bm25_b.split(',')]

    if bm25_weight:
        param_grid['bm25_weight'] = [float(v.strip()) for v in bm25_weight.split(',')]

    if embedding_model:
        param_grid['embedding_model'] = [v.strip() for v in embedding_model.split(',')]

    if chunk_header_level:
        param_grid['chunk_header_level'] = [int(v.strip()) for v in chunk_header_level.split(',')]

    return param_grid
