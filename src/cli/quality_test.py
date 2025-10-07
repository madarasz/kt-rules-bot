"""CLI command for running quality tests.

Usage:
    python -m src.cli quality-test
    python -m src.cli quality-test --test track-enemy-tacop
    python -m src.cli quality-test --all-models
    python -m src.cli quality-test --all-models --runs 3 --yes
    python -m src.cli quality-test --test track-enemy-tacop --runs 10 --model gemini-2.5-flash
"""

import asyncio
import sys
from typing import Optional, List

from tests.quality.test_runner import QualityTestRunner
from tests.quality.visualization import generate_visualization
from tests.quality.report_generator import generate_markdown_report
from tests.quality.multi_run_visualization import generate_multi_run_visualization
from tests.quality.aggregator import MultiRunAggregator
from src.services.llm.factory import LLMProviderFactory
from src.lib.logging import get_logger
from src.lib.constants import QUALITY_TEST_JUDGE_MODEL

logger = get_logger(__name__)


def quality_test(
    test_id: Optional[str] = None,
    model: Optional[str] = None,
    all_models: bool = False,
    judge_model: str = QUALITY_TEST_JUDGE_MODEL,
    skip_confirm: bool = False,
    runs: int = 1,
) -> None:
    """Run quality tests for RAG + LLM pipeline.

    Args:
        test_id: Specific test ID to run (None = all tests)
        model: Specific model to test (None = default from config)
        all_models: Test all available models
        judge_model: Model to use for LLM-based evaluation
        skip_confirm: Skip confirmation prompt
        runs: Number of times to run each test (default: 1)
    """
    # Determine models to test
    models: Optional[List[str]] = None
    if all_models:
        models = LLMProviderFactory.get_quality_test_models()
    elif model:
        models = [model]

    # Initialize runner
    runner = QualityTestRunner(judge_model=judge_model)

    # Load test cases
    try:
        test_cases = runner.load_test_cases(test_id)
    except Exception as e:
        logger.error(f"Failed to load test cases: {e}", exc_info=True)
        print(f"❌ Failed to load test cases: {e}")
        sys.exit(1)

    if not test_cases:
        print(
            f"❌ No test cases found"
            + (f" for test ID: {test_id}" if test_id else "")
        )
        sys.exit(1)

    if models is None:
        models = [runner.config.default_llm_provider]

    # Show configuration
    print("\n" + "=" * 60)
    print("Quality Test Configuration")
    print("=" * 60)
    print(f"Test cases: {len(test_cases)}")
    for tc in test_cases:
        print(f"  - {tc.test_id}")
    print(f"Models: {', '.join(models)}")
    print(f"Queries per run: {len(test_cases) * len(models)}")
    if runs > 1:
        print(f"Number of runs: {runs}")
        print(f"Total queries: {len(test_cases) * len(models) * runs}")
    print(f"Judge model: {judge_model}")
    print("=" * 60)

    # Confirmation
    if not skip_confirm:
        response = input("\nProceed with tests? (y/N): ")
        if response.lower() not in ["y", "yes"]:
            print("Cancelled.")
            sys.exit(0)

    # Run tests
    print("\nRunning tests...")
    try:
        if runs == 1:
            # Single run - use existing logic
            test_suite = asyncio.run(runner.run_tests(test_id=test_id, models=models))

            # Generate visualization
            chart_path = generate_visualization(test_suite)

            # Generate report
            report_path = generate_markdown_report(test_suite, chart_path=chart_path)

            # Print summary
            print("\n" + "=" * 60)
            print("Test Results Summary")
            print("=" * 60)
            print(f"Total tests: {test_suite.total_tests}")
            print(f"Total queries: {test_suite.total_queries}")
            print(f"Total time: {test_suite.total_time_seconds:.2f}s")
            print(f"Total cost: ${test_suite.total_cost_usd:.4f}")
            print(f"Average score: {test_suite.average_score:.1f}")
            print("=" * 60)

            # Print individual results
            for result in test_suite.test_results:
                status = "✅" if result.passed else "❌"
                print(
                    f"{status} {result.test_id} [{result.model}]: "
                    f"{result.score}/{result.max_score} "
                    f"({result.generation_time_seconds:.2f}s, ${result.cost_usd:.4f})"
                )

            print(f"\nFull report saved to: {report_path}")

        else:
            # Multi-run
            multi_run_suite = asyncio.run(
                runner.run_tests_multi(runs=runs, test_id=test_id, models=models)
            )

            # Generate individual run reports
            for suite in multi_run_suite.run_suites:
                chart_path = generate_visualization(suite)
                generate_markdown_report(suite, chart_path=chart_path)

            # Generate aggregated report
            report_path = runner.generate_multi_run_report(multi_run_suite)

            # Print summary
            aggregator = MultiRunAggregator(multi_run_suite.run_suites)
            overall_avgs = aggregator.get_overall_averages()
            overall_stds = aggregator.get_overall_std_devs()

            # Calculate totals
            total_time = sum(suite.total_time_seconds for suite in multi_run_suite.run_suites)
            total_cost = sum(suite.total_cost_usd for suite in multi_run_suite.run_suites)

            print("\n" + "=" * 60)
            print(f"Test Results Summary ({runs} runs)")
            print("=" * 60)
            print(f"Total time: {total_time:.2f}s")
            print(f"Total cost: ${total_cost:.4f}")
            print(f"Average score: {overall_avgs['score_pct']:.1f}% (±{overall_stds['score_pct']:.1f}%)")
            print(f"Average time per query: {overall_avgs['time']:.2f}s (±{overall_stds['time']:.2f}s)")
            print(f"Average cost per query: ${overall_avgs['cost']:.4f} (±${overall_stds['cost']:.4f})")
            print(f"Average response chars: {overall_avgs['chars']:.0f} (±{overall_stds['chars']:.0f})")
            print("=" * 60)

            # Print per-model averages
            for model_name in aggregator.models:
                avgs = aggregator.get_model_averages(model_name)
                stds = aggregator.get_model_std_devs(model_name)
                print(
                    f"{model_name}: {avgs['score_pct']:.1f}% (±{stds['score_pct']:.1f}%) | "
                    f"{avgs['time']:.2f}s (±{stds['time']:.2f}s) | "
                    f"${avgs['cost']:.4f} (±${stds['cost']:.4f})"
                )

            print(f"\nAggregated report saved to: {report_path}")

    except Exception as e:
        logger.error(f"Quality tests failed: {e}", exc_info=True)
        print(f"\n❌ Quality tests failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # This allows running as: python -m src.cli.quality_test
    quality_test()
