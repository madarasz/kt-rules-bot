"""CLI command for running quality tests."""
# ruff: noqa: E402

import asyncio
import sys
import time
import warnings
from datetime import UTC, datetime
from pathlib import Path

import src.lib.constants as constants
from src.lib.config import get_config
from src.lib.constants import QUALITY_TEST_JUDGE_MODEL, QUALITY_TEST_PROVIDERS
from src.lib.logging import get_logger
from tests.quality.reporting.aggregator import aggregate_results
from tests.quality.reporting.report_generator import ReportGenerator
from tests.quality.reporting.report_models import QualityReport
from tests.quality.test_runner import QualityTestRunner

logger = get_logger(__name__)

# Suppress ResourceWarnings from async HTTP clients cleanup
# This occurs when Ragas (and other async libraries) try to clean up connections
# after the event loop has closed. It's harmless and doesn't affect results.
warnings.filterwarnings("ignore", category=ResourceWarning, message=".*unclosed.*")

# Filter asyncio "Event loop is closed" errors that occur during cleanup
# These happen when Ragas' async HTTP clients try to close after the event loop is shut down
# The errors occur AFTER we get our results, so they don't affect functionality
import logging

logging.getLogger("asyncio").setLevel(logging.CRITICAL)


def _suppress_event_loop_closed_errors() -> None:
    """Suppress 'Event loop is closed' errors during shutdown.

    These errors occur when async HTTP clients (from Ragas) try to cleanup
    after the event loop has been closed by asyncio.run(). They're harmless
    and don't affect test results - they only appear during final cleanup.
    """
    # Store original excepthook
    original_excepthook = sys.excepthook

    def custom_excepthook(exc_type, exc_value, exc_traceback):
        # Suppress RuntimeError: Event loop is closed
        if exc_type is RuntimeError and "Event loop is closed" in str(exc_value):
            return  # Silently ignore
        # Call original excepthook for all other exceptions
        original_excepthook(exc_type, exc_value, exc_traceback)

    sys.excepthook = custom_excepthook


def quality_test(
    test_id: str | None = None,
    model: str | None = None,
    all_models: bool = False,
    judge_model: str = QUALITY_TEST_JUDGE_MODEL,
    skip_confirm: bool = False,
    runs: int = 1,
    max_hops: int | None = None,
    no_eval: bool = False,
    force_rag: bool = False,
    from_output: str | None = None,
) -> None:
    """Run quality tests for RAG + LLM pipeline, or replay from saved outputs.

    Args:
        test_id: Specific test ID to run (default: all tests)
        model: Specific model to test
        all_models: Test all available models
        judge_model: Model to use for Ragas evaluation
        skip_confirm: Skip confirmation prompt
        runs: Number of times to run each test
        max_hops: Override RAG_MAX_HOPS constant
        no_eval: Skip Ragas evaluation (only generate outputs)
        force_rag: Ignore cached context files and run RAG
        from_output: Path to existing output folder for replay mode (skips RAG + LLM generation)
    """
    # Suppress event loop cleanup errors from Ragas (only if we're running eval)
    if not no_eval:
        _suppress_event_loop_closed_errors()

    # Override RAG_MAX_HOPS if specified
    if max_hops is not None:
        original_max_hops = constants.RAG_MAX_HOPS
        constants.RAG_MAX_HOPS = max_hops
        logger.info(f"Overriding RAG_MAX_HOPS to {max_hops} for quality tests")
    else:
        original_max_hops = None

    models_to_run: list[str]
    if all_models:
        models_to_run = QUALITY_TEST_PROVIDERS
    elif model:
        models_to_run = [model]
    else:
        models_to_run = [get_config().default_llm_provider]

    runner = QualityTestRunner(judge_model=judge_model)

    # REPLAY MODE: Load from existing outputs
    if from_output:
        output_dir = Path(from_output)
        if not output_dir.exists():
            print(f"❌ Output directory does not exist: {output_dir}")
            sys.exit(1)

        print("\n" + "=" * 60)
        print("Quality Test Replay Mode")
        print("=" * 60)
        print(f"Source: {output_dir}")
        print(f"Judge model: {judge_model}")
        if model:
            print(f"Filter by model: {model}")
            models_to_run = [model]
        elif all_models:
            print(f"Models: {', '.join(models_to_run)} (all available)")
        else:
            models_to_run = None  # All models in output directory
            print("Models: All found in output directory")
        print("=" * 60)

        if not skip_confirm:
            response = input("\nProceed with replay? (y/N): ")
            if response.lower() not in ["y", "yes"]:
                print("Cancelled.")
                sys.exit(0)

        print("\n🔄 Replaying tests from saved outputs...")
        print("  (Skipping RAG retrieval and LLM generation)")
        start_time = time.time()

        try:
            # Run replay
            results = asyncio.run(
                runner.replay_tests_from_outputs(
                    output_dir=output_dir,
                    models=models_to_run,
                )
            )

            total_time = time.time() - start_time
            total_cost = sum(r.total_cost_usd for r in results)

            # Infer test cases and models from results
            test_cases_inferred = list(set(r.test_id for r in results))
            models_inferred = list(set(r.model for r in results))

            # Create the main report object
            report = QualityReport(
                results=results,
                total_time_seconds=total_time,
                total_cost_usd=total_cost,
                runs=1,  # Replay doesn't support multi-run detection yet
                models=models_inferred,
                test_cases=test_cases_inferred,
                report_dir=str(Path(results[0].output_filename).parent) if results else "",
                prompt_path=str(output_dir / "prompt.md"),
            )

            # Aggregate results
            aggregate_results(report)

            # Generate reports (includes chart generation)
            report_generator = ReportGenerator(report)
            report_generator.generate_all_reports()

            # Print console summary
            console_output = report_generator.get_console_output()
            print(console_output)

            print(f"\n✅ Replay completed in {total_time:.1f}s")
            print(f"   Original LLM costs: ${total_cost - sum(r.ragas_cost_usd for r in results):.4f}")
            print(f"   New judge costs: ${sum(r.ragas_cost_usd for r in results):.4f}")
            print(f"   Total costs (original + judge): ${total_cost:.4f}")

        except Exception as e:
            logger.error(f"Replay failed: {e}", exc_info=True)
            print(f"\n❌ Replay failed: {e}")
            sys.exit(1)
        finally:
            # Restore original RAG_MAX_HOPS if overridden
            if original_max_hops is not None:
                constants.RAG_MAX_HOPS = original_max_hops

        return  # Exit after replay

    try:
        test_cases_to_run = runner.load_test_cases(test_id)
    except Exception as e:
        logger.error(f"Failed to load test cases: {e}", exc_info=True)
        print(f"❌ Failed to load test cases: {e}")
        sys.exit(1)

    if not test_cases_to_run:
        print("❌ No test cases found" + (f" for test ID: {test_id}" if test_id else ""))
        sys.exit(1)

    # Configuration and Confirmation
    _print_configuration(test_cases_to_run, models_to_run, runs, judge_model, no_eval)
    if not skip_confirm:
        response = input("\nProceed with tests? (y/N): ")
        if response.lower() not in ["y", "yes"]:
            print("Cancelled.")
            sys.exit(0)

    # Setup report directory
    timestamp_str = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M-%S")
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
                force_rag=force_rag,
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
        report_generator.generate_all_reports()

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
        print("Evaluation: DISABLED (outputs only)")
    else:
        print(f"Judge model: {judge_model}")
    print("=" * 60)


if __name__ == "__main__":
    # This allows running as: python -m src.cli.quality_test
    # A simple CLI parser can be added here if needed for standalone execution
    quality_test()
