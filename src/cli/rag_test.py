"""CLI command to run RAG retrieval tests.

Usage:
    python -m src.cli rag-test
    python -m src.cli rag-test --test banner-carrier-dies --runs 10
"""

import sys
from datetime import datetime
from pathlib import Path

from src.lib.constants import RAG_MAX_CHUNKS, RAG_MIN_RELEVANCE
from src.lib.database import AnalyticsDatabase
from src.lib.logging import get_logger
from tests.rag.reporting.report_generator import RAGReportGenerator
from tests.rag.test_runner import RAGTestRunner

logger = get_logger(__name__)


def rag_test(
    test_id: str | None = None,
    runs: int = 1,
    max_chunks: int = RAG_MAX_CHUNKS,
    min_relevance: float = RAG_MIN_RELEVANCE,
) -> None:
    """Run RAG retrieval tests using Ragas evaluation framework.

    Args:
        test_id: Specific test ID to run (otherwise run all)
        runs: Number of times to run each test
        max_chunks: Maximum chunks to retrieve
        min_relevance: Minimum relevance threshold
    """
    test_desc = f"test '{test_id}'" if test_id else "all tests"
    print(f"Running {test_desc} with {runs} run(s)")
    print(f"Configuration: max_chunks={max_chunks}, min_relevance={min_relevance}")
    print("Evaluation: Ragas metrics")

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

        print("\nRunning RAG retrieval tests...")
        print(f"Test ID: {test_id or 'all'}")
        print(f"Runs: {runs}")
        print("")

        results, total_time = runner.run_tests(
            test_id=test_id, runs=runs, max_chunks=max_chunks, min_relevance=min_relevance
        )

        if not results:
            print("No test results generated.")
            return

        # Calculate summary (use test_id as test set if specific test was run)
        test_set = test_id  # Use the actual test_id, or None if running all tests
        summary = runner.calculate_summary(results, total_time, max_chunks, min_relevance, test_set)

        # Print summary to console
        print("\n" + "=" * 80)
        print("RAGAS METRICS")
        print("=" * 80)
        print(f"Total Tests: {summary.total_tests}")

        # Print Ragas metrics
        if summary.mean_ragas_context_precision is not None:
            print(f"Context Precision: {summary.mean_ragas_context_precision:.3f}")
            print(f"Context Recall: {summary.mean_ragas_context_recall:.3f}")

            if summary.std_dev_ragas_context_precision > 0:
                print("")
                print(f"Context Precision std dev: ±{summary.std_dev_ragas_context_precision:.3f}")
                print(f"Context Recall std dev: ±{summary.std_dev_ragas_context_recall:.3f}")

        print("")
        print("=" * 80)
        print("MISSING CHUNKS")
        print("=" * 80)
        missing_chunks_found = False
        count_missing_chunks = 0
        for result in results:
            if result.missing_chunks:
                missing_chunks_found = True
                for missing_chunk in result.missing_chunks:
                    print(f"- {result.test_id}: {missing_chunk}")
                    count_missing_chunks += 1

        if not missing_chunks_found:
            print("No missing chunks - all required chunks were retrieved!")
        else:
            print(f"\n### Number of missing chunks**: {count_missing_chunks}")

        print("")
        print("=" * 80)
        print("ERROR SUMMARY")
        print("=" * 80)
        errors_found = False
        for result in results:
            if result.error_type:
                errors_found = True
                print(f"❌ {result.test_id} (run {result.run_number}): {result.error_type}")
                print(f"   {result.error_message}")
                print("")

        if not errors_found:
            print("No errors - all tests completed successfully!")

        print("")
        print("=" * 80)
        print("PERFORMANCE METRICS")
        print("=" * 80)
        print(f"Total Time: {summary.total_time_seconds:.2f}s")
        print(f"Avg Retrieval Time: {summary.avg_retrieval_time_seconds:.3f}s")
        print(f"Avg Filtered Teams: {summary.avg_filtered_teams_count:.2f}")

        # Calculate total cost including hop evaluations
        total_cost_with_hops = summary.total_cost_usd + summary.hop_evaluation_cost_usd
        print(f"Total Cost: ${total_cost_with_hops:.6f}")
        print(f"  ├─ Embeddings: ${summary.total_cost_usd:.6f}")
        print(f"  └─ Hop Evaluations: ${summary.hop_evaluation_cost_usd:.6f}")
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

        # Save to analytics database if enabled
        _save_to_database(timestamp, summary, report_path)

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


def _save_to_database(timestamp: str, summary, report_path: Path) -> None:
    """Save RAG test run to analytics database.

    Args:
        timestamp: Timestamp string for run_id
        summary: RAGTestSummary object
        report_path: Path to the generated report markdown file
    """
    try:
        # Initialize database
        db = AnalyticsDatabase.from_config()

        if not db.enabled:
            logger.debug("Analytics database disabled, skipping save")
            return

        # Read the full report markdown
        full_report_md = ""
        if report_path.exists():
            full_report_md = report_path.read_text()

        # Create run data
        # Calculate total cost including hop evaluations (matches report generator)
        total_cost_with_hops = summary.total_cost_usd + summary.hop_evaluation_cost_usd

        run_data = {
            "run_id": timestamp,  # Use timestamp as unique run ID
            "timestamp": datetime.now().isoformat(),
            "test_set": summary.test_set_codename or "",
            "runs_per_test": summary.runs_per_test,
            "avg_retrieval_time": summary.avg_retrieval_time_seconds,
            # saved in cents to avoid floating point issues
            "avg_retrieval_cost": total_cost_with_hops * 100 / summary.total_tests if summary.total_tests > 0 else 0.0,
            "context_recall": summary.mean_ragas_context_recall,
            "avg_hops_used": summary.avg_hops_used,
            "can_answer_recall": summary.hop_can_answer_recall,
            "full_report_md": full_report_md,
        }

        # Insert into database
        db.insert_rag_test_run(run_data)

        print(f"✅ Test results saved to analytics database (run_id: {timestamp})")
        logger.info("rag_test_saved_to_db", run_id=timestamp, test_set=summary.test_set_codename)

    except Exception as e:
        # Don't fail the entire test run if database save fails
        logger.warning(f"Failed to save test results to database: {e}")
        print(f"⚠️  Warning: Failed to save to analytics database: {e}")
