"""CLI command for running quality tests."""

import asyncio
import sys
import warnings
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

# Suppress ResourceWarnings from async HTTP clients cleanup
# This occurs when Ragas (and other async libraries) try to clean up connections
# after the event loop has closed. It's harmless and doesn't affect results.
warnings.filterwarnings('ignore', category=ResourceWarning, message='.*unclosed.*')

# Filter asyncio "Event loop is closed" errors that occur during cleanup
# These happen when Ragas' async HTTP clients try to close after the event loop is shut down
# The errors occur AFTER we get our results, so they don't affect functionality
import logging
logging.getLogger('asyncio').setLevel(logging.CRITICAL)


def _suppress_event_loop_closed_errors():
    """Suppress 'Event loop is closed' errors during shutdown.

    These errors occur when async HTTP clients (from Ragas) try to cleanup
    after the event loop has been closed by asyncio.run(). They're harmless
    and don't affect test results - they only appear during final cleanup.
    """
    import sys

    # Store original excepthook
    original_excepthook = sys.excepthook

    def custom_excepthook(exc_type, exc_value, exc_traceback):
        # Suppress RuntimeError: Event loop is closed
        if exc_type == RuntimeError and 'Event loop is closed' in str(exc_value):
            return  # Silently ignore
        # Call original excepthook for all other exceptions
        original_excepthook(exc_type, exc_value, exc_traceback)

    sys.excepthook = custom_excepthook


def quality_test(
    test_id: Optional[str] = None,
    model: Optional[str] = None,
    all_models: bool = False,
    judge_model: str = QUALITY_TEST_JUDGE_MODEL,
    skip_confirm: bool = False,
    runs: int = 1,
    max_hops: Optional[int] = None,
    no_eval: bool = False,
) -> None:
    """Run quality tests for RAG + LLM pipeline.

    Args:
        test_id: Specific test ID to run (default: all tests)
        model: Specific model to test
        all_models: Test all available models
        judge_model: Model to use for Ragas evaluation
        skip_confirm: Skip confirmation prompt
        runs: Number of times to run each test
        max_hops: Override RAG_MAX_HOPS constant
        no_eval: Skip Ragas evaluation (only generate outputs)
    """
    # Suppress event loop cleanup errors from Ragas (only if we're running eval)
    if not no_eval:
        _suppress_event_loop_closed_errors()

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
    _print_configuration(test_cases_to_run, models_to_run, runs, judge_model, no_eval)
    if not skip_confirm:
        response = input("\nProceed with tests? (y/N): ")
        if response.lower() not in ["y", "yes"]:
            print("Cancelled.")
            sys.exit(0)

    # Setup report directory
    timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    report_dir = Path(f"tests/quality/results/{timestamp_str}")
    report_dir.mkdir(parents=True, exist_ok=True)

    mode_str = " (no evaluation)" if no_eval else ""
    print(f"\nRunning tests{mode_str}...")
    start_time = time.time()

    try:
        # Run all tests in parallel
        results = asyncio.run(
            runner.run_tests_in_parallel(
                runs=runs,
                report_dir=report_dir,
                test_id=test_id,
                models=models_to_run,
                no_eval=no_eval,
            )
        )

        total_time = time.time() - start_time
        total_cost = sum(r.total_cost_usd for r in results)

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


def _print_configuration(test_cases, models, runs, judge_model, no_eval=False):
    """Prints the test configuration to the console."""
    print("\n" + "=" * 60)
    print("Quality Test Configuration")
    print("=" * 60)
    print(f"Test cases: {len(test_cases)} ({', '.join(tc.test_id for tc in test_cases)})")
    print(f"Models: {', '.join(models)}")
    print(f"Runs per test: {runs}")
    print(f"Total queries: {len(test_cases) * len(models) * runs}")
    if no_eval:
        print(f"Evaluation: DISABLED (outputs only)")
    else:
        print(f"Judge model: {judge_model}")
    print("=" * 60)


if __name__ == "__main__":
    # This allows running as: python -m src.cli.quality_test
    # A simple CLI parser can be added here if needed for standalone execution
    quality_test()
