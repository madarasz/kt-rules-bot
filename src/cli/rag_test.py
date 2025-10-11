"""CLI command to run RAG retrieval tests.

Usage:
    python -m src.cli rag-test
    python -m src.cli rag-test --test banner-carrier-dies --runs 10
"""

import sys
from pathlib import Path
from datetime import datetime

from tests.rag.test_runner import RAGTestRunner
from tests.rag.reporting.report_generator import RAGReportGenerator
from src.lib.constants import RAG_MAX_CHUNKS, RAG_MIN_RELEVANCE
from src.lib.logging import get_logger

logger = get_logger(__name__)


def rag_test(
    test_id: str | None = None,
    runs: int = 1,
    max_chunks: int = RAG_MAX_CHUNKS,
    min_relevance: float = RAG_MIN_RELEVANCE,
    yes: bool = False,
) -> None:
    """Run RAG retrieval tests.

    Args:
        test_id: Specific test ID to run (otherwise run all)
        runs: Number of times to run each test
        max_chunks: Maximum chunks to retrieve
        min_relevance: Minimum relevance threshold
        yes: Skip confirmation prompt
    """
    # Confirmation prompt
    if not yes:
        test_desc = f"test '{test_id}'" if test_id else "all tests"
        print(f"Running {test_desc} with {runs} run(s)")
        print(f"Configuration: max_chunks={max_chunks}, min_relevance={min_relevance}")
        response = input("Continue? [y/N]: ")
        if response.lower() != 'y':
            print("Aborted.")
            return

    # Initialize runner
    runner = RAGTestRunner()
    report_gen = RAGReportGenerator()

    try:
        # Run tests
        logger.info(
            "starting_rag_tests",
            test_id=test_id,
            runs=runs,
            max_chunks=max_chunks,
            min_relevance=min_relevance,
        )

        print(f"\nRunning RAG retrieval tests...")
        print(f"Test ID: {test_id or 'all'}")
        print(f"Runs: {runs}")
        print("")

        results, total_time = runner.run_tests(
            test_id=test_id,
            runs=runs,
            max_chunks=max_chunks,
            min_relevance=min_relevance,
        )

        if not results:
            print("No test results generated.")
            return

        # Calculate summary
        summary = runner.calculate_summary(results, total_time, max_chunks, min_relevance)

        # Print summary to console
        print("\n" + "=" * 80)
        print("OVERALL METRICS")
        print("=" * 80)
        print(f"Total Tests: {summary.total_tests}")
        print(f"Mean MAP: {summary.mean_map:.3f}")
        print(f"Recall@5: {summary.mean_recall_at_5:.3f} ({summary.mean_recall_at_5*100:.1f}%)")
        print(f"Precision@3: {summary.mean_precision_at_3:.3f} ({summary.mean_precision_at_3*100:.1f}%)")
        print(f"MRR: {summary.mean_mrr:.3f}")

        if summary.std_dev_map > 0:
            print("")
            print(f"MAP std dev: ±{summary.std_dev_map:.3f}")
            print(f"Recall@5 std dev: ±{summary.std_dev_recall_at_5:.3f}")

        print("")
        print("=" * 80)
        print("PERFORMANCE METRICS")
        print("=" * 80)
        print(f"Total Time: {summary.total_time_seconds:.2f}s")
        print(f"Avg Retrieval Time: {summary.avg_retrieval_time_seconds:.3f}s")
        print(f"Total Cost: ${summary.total_cost_usd:.6f}")
        print("")

        # Generate report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_dir = Path("tests/rag/results") / timestamp
        results_dir.mkdir(parents=True, exist_ok=True)

        report_path = results_dir / "report.md"
        report_gen.generate_report(results, summary, report_path)

        # Save retrieved chunks for manual review
        for result in results:
            report_gen.save_retrieved_chunks(result, results_dir)

        print(f"Report saved to: {report_path}")
        print(f"Retrieved chunks saved to: {results_dir}/")
        print("")

        logger.info(
            "rag_tests_completed",
            total_tests=summary.total_tests,
            mean_map=f"{summary.mean_map:.3f}",
            report_path=str(report_path),
        )

    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("\nMake sure test cases exist in tests/rag/test_cases/")
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error("rag_test_failed", error=str(e))
        print(f"Error running RAG tests: {e}")
        sys.exit(1)
