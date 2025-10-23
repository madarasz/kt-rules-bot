"""CLI command for running quality tests."""

import asyncio
import sys
from typing import Optional, List
from datetime import datetime, timezone
from pathlib import Path
import time

from tests.quality.test_runner import QualityTestRunner
from tests.quality.reporting.report_models import QualityReport
from tests.quality.reporting.aggregator import aggregate_results
from tests.quality.reporting.report_generator import ReportGenerator
from src.lib.logging import get_logger
from src.lib.constants import QUALITY_TEST_JUDGE_MODEL, QUALITY_TEST_PROVIDERS, RAG_MAX_HOPS

logger = get_logger(__name__)


def quality_test(
    test_id: Optional[str] = None,
    model: Optional[str] = None,
    all_models: bool = False,
    judge_model: str = QUALITY_TEST_JUDGE_MODEL,
    skip_confirm: bool = False,
    runs: int = 1,
    max_hops: Optional[int] = None,
) -> None:
    """Run quality tests for RAG + LLM pipeline."""
    # Override RAG_MAX_HOPS if specified
    if max_hops is not None:
        import src.lib.constants as constants
        original_max_hops = constants.RAG_MAX_HOPS
        constants.RAG_MAX_HOPS = max_hops
        logger.info(f"Overriding RAG_MAX_HOPS to {max_hops} for quality tests")
    else:
        original_max_hops = None

    models_to_run: List[str]
    if all_models:
        models_to_run = QUALITY_TEST_PROVIDERS
    elif model:
        models_to_run = [model]
    else:
        from src.lib.config import get_config
        models_to_run = [get_config().default_llm_provider]

    runner = QualityTestRunner(judge_model=judge_model)
    
    try:
        test_cases_to_run = runner.load_test_cases(test_id)
    except Exception as e:
        logger.error(f"Failed to load test cases: {e}", exc_info=True)
        print(f"❌ Failed to load test cases: {e}")
        sys.exit(1)

    if not test_cases_to_run:
        print(f"❌ No test cases found" + (f" for test ID: {test_id}" if test_id else ""))
        sys.exit(1)

    # Configuration and Confirmation
    _print_configuration(test_cases_to_run, models_to_run, runs, judge_model)
    if not skip_confirm:
        response = input("\nProceed with tests? (y/N): ")
        if response.lower() not in ["y", "yes"]:
            print("Cancelled.")
            sys.exit(0)

    # Setup report directory
    timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    report_dir = Path(f"tests/quality/results/{timestamp_str}")
    report_dir.mkdir(parents=True, exist_ok=True)

    print("\nRunning tests...")
    start_time = time.time()

    try:
        # Run all tests in parallel
        results = asyncio.run(
            runner.run_tests_in_parallel(
                runs=runs,
                report_dir=report_dir,
                test_id=test_id,
                models=models_to_run,
            )
        )

        total_time = time.time() - start_time
        total_cost = sum(r.cost_usd for r in results)

        # Create the main report object
        report = QualityReport(
            results=results,
            total_time_seconds=total_time,
            total_cost_usd=total_cost,
            runs=runs,
            models=models_to_run,
            test_cases=[tc.test_id for tc in test_cases_to_run],
            report_dir=str(report_dir),
            prompt_path=str(report_dir / "prompt.md"),
        )

        # Aggregate results
        aggregate_results(report)

        # Generate reports (includes chart generation)
        report_generator = ReportGenerator(report)
        main_report_path = report_generator.generate_all_reports()

        # Print console summary
        console_output = report_generator.get_console_output()
        print(console_output)

    except Exception as e:
        logger.error(f"Quality tests failed: {e}", exc_info=True)
        print(f"\n❌ Quality tests failed: {e}")
        sys.exit(1)
    finally:
        # Restore original RAG_MAX_HOPS if overridden
        if original_max_hops is not None:
            import src.lib.constants as constants
            constants.RAG_MAX_HOPS = original_max_hops
            logger.info(f"Restored RAG_MAX_HOPS to {original_max_hops}")


def _print_configuration(test_cases, models, runs, judge_model):
    """Prints the test configuration to the console."""
    print("\n" + "=" * 60)
    print("Quality Test Configuration")
    print("=" * 60)
    print(f"Test cases: {len(test_cases)} ({', '.join(tc.test_id for tc in test_cases)})")
    print(f"Models: {', '.join(models)}")
    print(f"Runs per test: {runs}")
    print(f"Total queries: {len(test_cases) * len(models) * runs}")
    print(f"Judge model: {judge_model}")
    print("=" * 60)


if __name__ == "__main__":
    # This allows running as: python -m src.cli.quality_test
    # A simple CLI parser can be added here if needed for standalone execution
    quality_test()
