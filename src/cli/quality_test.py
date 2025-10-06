"""CLI command for running quality tests.

Usage:
    python -m src.cli quality-test
    python -m src.cli quality-test --test track-enemy-tacop
    python -m src.cli quality-test --all-models
"""

import asyncio
import sys
from typing import Optional, List

from tests.quality.test_runner import QualityTestRunner
from tests.quality.visualization import generate_visualization
from src.services.llm.factory import LLMProviderFactory
from src.lib.logging import get_logger

logger = get_logger(__name__)


def quality_test(
    test_id: Optional[str] = None,
    model: Optional[str] = None,
    all_models: bool = False,
    judge_model: str = "gpt-4.1-mini",
    skip_confirm: bool = False,
) -> None:
    """Run quality tests for RAG + LLM pipeline.

    Args:
        test_id: Specific test ID to run (None = all tests)
        model: Specific model to test (None = default from config)
        all_models: Test all available models
        judge_model: Model to use for LLM-based evaluation
        skip_confirm: Skip confirmation prompt
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
    print(f"Total queries: {len(test_cases) * len(models)}")
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
        test_suite = asyncio.run(runner.run_tests(test_id=test_id, models=models))

        # Generate report
        from pathlib import Path
        from datetime import datetime

        dt = datetime.fromisoformat(test_suite.timestamp)
        timestamp_str = dt.strftime("%Y-%m-%d_%H-%M-%S")

        output_dir = Path("tests/quality/results")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"quality_test_{timestamp_str}.md"

        # Generate visualization (only if multiple models tested)
        chart_path = None
        if len(models) > 1:
            chart_path = generate_visualization(test_suite)
            print(f"Visualization saved to: {chart_path}")

        # Generate markdown report with chart reference
        runner.generate_markdown_report(test_suite, str(output_file), chart_path)

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
            status = "✓" if result.passed else "✗"
            print(
                f"{status} {result.test_id} [{result.model}]: "
                f"{result.score}/{result.max_score} "
                f"({result.generation_time_seconds:.2f}s, ${result.cost_usd:.4f})"
            )

        print(f"\nFull report saved to: {output_file}")

    except Exception as e:
        logger.error(f"Quality tests failed: {e}", exc_info=True)
        print(f"\n❌ Quality tests failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # This allows running as: python -m src.cli.quality_test
    quality_test()
