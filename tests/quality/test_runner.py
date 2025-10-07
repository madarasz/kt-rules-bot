"""Quality test runner for response quality testing.

Runs quality tests against the RAG + LLM pipeline and generates reports.
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
import yaml

from tests.quality.models import (
    TestCase,
    TestRequirement,
    TestResult,
    QualityTestSuite,
    MultiRunTestSuite,
)
from tests.quality.evaluator import RequirementEvaluator
from tests.quality.visualization import generate_visualization
from tests.quality.report_generator import generate_markdown_report
from tests.quality.multi_run_visualization import generate_multi_run_visualization
from tests.quality.aggregator import MultiRunAggregator
from src.services.llm.factory import LLMProviderFactory
from src.services.rag.retriever import RAGRetriever, RetrieveRequest
from src.services.rag.vector_db import VectorDBService
from src.services.rag.embeddings import EmbeddingService
from src.services.llm.base import GenerationRequest, GenerationConfig, ContentFilterError
from src.lib.config import get_config
from src.lib.logging import get_logger
from src.lib.tokens import estimate_cost

logger = get_logger(__name__)


class QualityTestRunner:
    """Runs quality tests and generates reports."""

    def __init__(
        self,
        test_cases_dir: str = "tests/quality/test_cases",
        judge_model: str = "gpt-4.1-mini",
    ):
        """Initialize test runner.

        Args:
            test_cases_dir: Directory containing YAML test cases
            judge_model: Model to use for LLM-based requirement evaluation
        """
        self.test_cases_dir = Path(test_cases_dir)
        self.judge_model = judge_model
        self.evaluator = RequirementEvaluator(judge_model=judge_model)

        # Initialize services
        self.config = get_config()
        self.vector_db = VectorDBService(collection_name="kill_team_rules")
        self.embedding_service = EmbeddingService()
        self.rag_retriever = RAGRetriever(
            vector_db_service=self.vector_db,
            embedding_service=self.embedding_service,
        )

    def load_test_cases(self, test_id: Optional[str] = None) -> List[TestCase]:
        """Load test cases from YAML files.

        Args:
            test_id: Optional specific test ID to load. If None, loads all tests.

        Returns:
            List of TestCase objects
        """
        test_cases = []

        # Find YAML files
        if test_id:
            yaml_files = [self.test_cases_dir / f"{test_id}.yaml"]
        else:
            yaml_files = list(self.test_cases_dir.glob("*.yaml"))

        for yaml_file in yaml_files:
            if not yaml_file.exists():
                logger.warning(f"Test file not found: {yaml_file}")
                continue

            try:
                with open(yaml_file, "r") as f:
                    data = yaml.safe_load(f)

                # Parse requirements
                requirements = []
                for req_data in data.get("requirements", []):
                    requirements.append(
                        TestRequirement(
                            type=req_data["type"],
                            description=req_data["description"],
                            points=req_data["points"],
                            check=req_data.get("check", ""),
                        )
                    )

                test_case = TestCase(
                    test_id=data["test_id"],
                    query=data["query"],
                    requirements=requirements,
                )

                test_cases.append(test_case)
                logger.info(f"Loaded test case: {test_case.test_id}")

            except Exception as e:
                logger.error(f"Failed to load test case from {yaml_file}: {e}")
                continue

        return test_cases

    async def run_test(self, test_case: TestCase, model: str, rag_context=None) -> TestResult:
        """Run a single test case with a specific model.

        Args:
            test_case: Test case to run
            model: Model to test with
            rag_context: Optional pre-retrieved RAG context (for performance optimization)

        Returns:
            TestResult
        """
        logger.info(f"Running test '{test_case.test_id}' with model '{model}'")

        start_time = datetime.now(timezone.utc)

        # Step 1: RAG Retrieval (only if not provided)
        if rag_context is None:
            from uuid import uuid4

            query_id = uuid4()
            rag_context = self.rag_retriever.retrieve(
                RetrieveRequest(
                    query=test_case.query,
                    context_key="quality_test",
                    max_chunks=15,
                ),
                query_id=query_id,
            )

        # Step 2: LLM Generation
        llm_provider = LLMProviderFactory.create(model)

        # Create config and capture system prompt
        gen_config = GenerationConfig(timeout_seconds=60)

        try:
            llm_response = await llm_provider.generate(
                GenerationRequest(
                    prompt=test_case.query,
                    context=[chunk.text for chunk in rag_context.document_chunks],
                    config=gen_config,
                )
            )

            generation_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Step 3: Evaluate requirements
            requirement_results = await self.evaluator.evaluate_all(
                test_case.requirements, llm_response.answer_text
            )

            # Calculate score
            score = sum(r.points_earned for r in requirement_results)

            # Step 4: Calculate cost
            # For LLM response tokens, we need to split into prompt and completion
            # The token_count from LLMResponse is total, so we estimate 70% prompt, 30% completion
            total_tokens = llm_response.token_count
            estimated_prompt_tokens = int(total_tokens * 0.7)
            estimated_completion_tokens = int(total_tokens * 0.3)

            cost = estimate_cost(
                prompt_tokens=estimated_prompt_tokens,
                completion_tokens=estimated_completion_tokens,
                model=model,
            )

            return TestResult(
                test_id=test_case.test_id,
                query=test_case.query,
                model=model,
                response=llm_response.answer_text,
                system_prompt=gen_config.system_prompt,
                requirements=requirement_results,
                score=score,
                max_score=test_case.max_score,
                generation_time_seconds=generation_time,
                token_count=total_tokens,
                cost_usd=cost,
                response_chars=len(llm_response.answer_text),
            )

        except ContentFilterError as e:
            # LLM generation failed due to content filter (e.g., RECITATION)
            generation_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Create failed requirement results for all requirements
            from tests.quality.models import RequirementResult
            requirement_results = [
                RequirementResult(
                    requirement=req,
                    passed=False,
                    points_earned=0,
                    details=f"LLM generation failed: {str(e)}",
                    judge_malfunction=True,
                )
                for req in test_case.requirements
            ]

            return TestResult(
                test_id=test_case.test_id,
                query=test_case.query,
                model=model,
                response=f"[LLM Generation Failed: {str(e)}]",
                system_prompt=gen_config.system_prompt,
                requirements=requirement_results,
                score=0,
                max_score=test_case.max_score,
                generation_time_seconds=generation_time,
                token_count=0,
                cost_usd=0.0,
                response_chars=0,
            )

    async def run_tests(
        self, test_id: Optional[str] = None, models: Optional[List[str]] = None
    ) -> QualityTestSuite:
        """Run quality tests.

        Args:
            test_id: Optional specific test to run. If None, runs all tests.
            models: List of models to test. If None, uses default model from config.

        Returns:
            QualityTestSuite with results
        """
        # Load test cases
        test_cases = self.load_test_cases(test_id)

        if not test_cases:
            raise ValueError(f"No test cases found" + (f" for test_id: {test_id}" if test_id else ""))

        # Determine models to test
        if models is None:
            models = [self.config.default_llm_provider]

        # Run all tests
        test_results = []
        total_time = 0.0
        total_cost = 0.0
        total_chars = 0

        for test_case in test_cases:
            # Perform RAG retrieval once per test case (shared across all models)
            logger.info(f"Retrieving context for test '{test_case.test_id}'")
            from uuid import uuid4

            query_id = uuid4()
            rag_context = self.rag_retriever.retrieve(
                RetrieveRequest(
                    query=test_case.query,
                    context_key="quality_test",
                    max_chunks=15,
                ),
                query_id=query_id,
            )

            # Test with all models using the same RAG context
            for model in models:
                try:
                    result = await self.run_test(test_case, model, rag_context)
                    test_results.append(result)
                    total_time += result.generation_time_seconds
                    total_cost += result.cost_usd
                    total_chars += result.response_chars
                except Exception as e:
                    logger.error(
                        f"Test '{test_case.test_id}' failed with model '{model}': {e}",
                        exc_info=True,
                    )
                    # Create a failed TestResult for unexpected errors
                    from tests.quality.models import RequirementResult
                    requirement_results = [
                        RequirementResult(
                            requirement=req,
                            passed=False,
                            points_earned=0,
                            details=f"Test execution failed: {str(e)}",
                            judge_malfunction=True,
                        )
                        for req in test_case.requirements
                    ]
                    result = TestResult(
                        test_id=test_case.test_id,
                        query=test_case.query,
                        model=model,
                        response=f"[Test Execution Failed: {str(e)}]",
                        system_prompt="",
                        requirements=requirement_results,
                        score=0,
                        max_score=test_case.max_score,
                        generation_time_seconds=0.0,
                        token_count=0,
                        cost_usd=0.0,
                        response_chars=0,
                    )
                    test_results.append(result)

        # Create test suite
        timestamp = datetime.now(timezone.utc).isoformat()
        return QualityTestSuite(
            timestamp=timestamp,
            test_results=test_results,
            total_tests=len(test_cases),
            total_queries=len(test_results),
            total_time_seconds=total_time,
            total_cost_usd=total_cost,
            total_response_chars=total_chars,
            judge_model=self.judge_model,
        )

    async def run_tests_multi(
        self, runs: int, test_id: Optional[str] = None, models: Optional[List[str]] = None
    ) -> MultiRunTestSuite:
        """Run quality tests N times and aggregate results.

        Args:
            runs: Number of times to run each test
            test_id: Optional specific test to run. If None, runs all tests.
            models: List of models to test. If None, uses default model from config.

        Returns:
            MultiRunTestSuite with aggregated results
        """
        if runs < 1:
            raise ValueError(f"Number of runs must be at least 1, got {runs}")

        logger.info(f"Running quality tests {runs} times")

        run_suites = []
        for i in range(runs):
            logger.info(f"Run {i + 1}/{runs}...")
            print(f"\n{'='*60}")
            print(f"Run {i + 1}/{runs}")
            print(f"{'='*60}\n")

            suite = await self.run_tests(test_id=test_id, models=models)
            run_suites.append(suite)

        # Create multi-run test suite
        multi_run_suite = MultiRunTestSuite(
            run_suites=run_suites,
            run_count=runs,
            first_run_timestamp=run_suites[0].timestamp,
            last_run_timestamp=run_suites[-1].timestamp,
        )

        logger.info(f"Completed {runs} test runs")
        return multi_run_suite

    def generate_multi_run_report(
        self, multi_run_suite: MultiRunTestSuite, output_file: Optional[str] = None
    ) -> str:
        """Generate aggregated markdown report from multi-run test suite.

        Args:
            multi_run_suite: Multi-run test suite results
            output_file: Optional file path to write report to

        Returns:
            Path to markdown report file
        """
        # Generate timestamp for filename
        dt = datetime.fromisoformat(multi_run_suite.last_run_timestamp)
        timestamp_str = dt.strftime("%Y-%m-%d_%H-%M-%S")

        if output_file is None:
            output_dir = Path("tests/quality/results")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / f"quality_test_{timestamp_str}_multirun_{multi_run_suite.run_count}x.md"

        # Generate visualization first
        chart_path = generate_multi_run_visualization(multi_run_suite)

        # Create aggregator
        aggregator = MultiRunAggregator(multi_run_suite.run_suites)
        overall_avgs = aggregator.get_overall_averages()
        overall_stds = aggregator.get_overall_std_devs()

        # Build markdown report
        lines = []
        lines.append(f"# Quality Test Results - Multi-Run (N={multi_run_suite.run_count}) - {timestamp_str}")
        lines.append("")
        lines.append(f"## Summary (Averaged across {multi_run_suite.run_count} runs)")
        lines.append("")
        lines.append(f"- **Average score**: {overall_avgs['score_pct']:.1f}% (±{overall_stds['score_pct']:.1f}%)")
        lines.append(f"- **Average time**: {overall_avgs['time']:.2f}s (±{overall_stds['time']:.2f}s)")
        lines.append(f"- **Average cost**: ${overall_avgs['cost']:.4f} (±${overall_stds['cost']:.4f})")
        lines.append(f"- **Average response chars**: {overall_avgs['chars']:.0f} (±{overall_stds['chars']:.0f})")

        if overall_avgs['llm_error_pct'] > 0:
            lines.append(f"- **Average LLM error %**: {overall_avgs['llm_error_pct']:.1f}% (±{overall_stds['llm_error_pct']:.1f}%) 💀")

        lines.append("")

        # Add visualization
        chart_filename = Path(chart_path).name
        lines.append("## Model Performance Visualization")
        lines.append("")
        lines.append(f"![Multi-Run Performance]({chart_filename})")
        lines.append("")
        lines.append(f"The chart shows averaged metrics across {multi_run_suite.run_count} runs:")
        lines.append("- **Score %**: Stacked bars showing earned points (green) and points lost to LLM judge errors (grey)")
        lines.append("- **Time**: Average generation time in seconds (blue bars)")
        lines.append("- **Cost**: Average cost in USD (red bars)")
        lines.append("- **Characters**: Average response characters (brown bars)")
        lines.append("- **Error bars**: Standard deviation across runs")
        lines.append("- **Dots**: Individual run values")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Aggregated results by model table
        lines.append("## Aggregated Results by Model")
        lines.append("")
        lines.append("| Model | Avg Score | Avg Time | Avg Cost | Avg Chars |")
        lines.append("|-------|-----------|----------|----------|-----------|")

        for model in aggregator.models:
            avgs = aggregator.get_model_averages(model)
            stds = aggregator.get_model_std_devs(model)
            lines.append(
                f"| {model} | {avgs['score_pct']:.1f}% (±{stds['score_pct']:.1f}%) | "
                f"{avgs['time']:.2f}s (±{stds['time']:.2f}s) | "
                f"${avgs['cost']:.4f} (±${stds['cost']:.4f}) | "
                f"{avgs['chars']:.0f} (±{stds['chars']:.0f}) |"
            )

        lines.append("")
        lines.append("---")
        lines.append("")

        # Individual run results
        lines.append("## Individual Run Results")
        lines.append("")

        for i, suite in enumerate(multi_run_suite.run_suites):
            dt_run = datetime.fromisoformat(suite.timestamp)
            timestamp_run_str = dt_run.strftime("%Y-%m-%d %H:%M:%S")

            lines.append(f"### Run {i + 1} - {timestamp_run_str}")
            lines.append("")
            lines.append(f"- Total tests: {suite.total_tests}")
            lines.append(f"- Total queries: {suite.total_queries}")
            lines.append(f"- Total time: {suite.total_time_seconds:.2f}s")
            lines.append(f"- Total cost: ${suite.total_cost_usd:.4f}")

            # Link to detailed report
            report_filename = f"quality_test_{dt_run.strftime('%Y-%m-%d_%H-%M-%S')}.md"
            report_path = Path(output_file).parent / report_filename
            if report_path.exists():
                lines.append(f"- See detailed report: [{report_filename}]({report_filename})")

            lines.append("")

        # Write to file
        markdown = "\n".join(lines)
        with open(output_file, "w") as f:
            f.write(markdown)

        logger.info(f"Multi-run report written to {output_file}")
        return str(output_file)


def main():
    """CLI entry point for quality test runner."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run quality tests for RAG + LLM pipeline"
    )
    parser.add_argument(
        "--test",
        "-t",
        help="Specific test ID to run (default: all tests)",
    )
    parser.add_argument(
        "--model",
        "-m",
        help="Specific model to test (default: from config)",
    )
    parser.add_argument(
        "--all-models",
        action="store_true",
        help="Test all available models",
    )
    parser.add_argument(
        "--judge-model",
        default="gpt-4.1-mini",
        help="Model to use for LLM-based evaluation (default: gpt-4.1-mini)",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompt",
    )
    parser.add_argument(
        "--runs",
        "-n",
        type=int,
        default=1,
        help="Number of times to run each test (default: 1)",
    )

    args = parser.parse_args()

    # Determine models to test
    models = None
    if args.all_models:
        models = LLMProviderFactory.get_quality_test_models()
    elif args.model:
        models = [args.model]

    # Show what will be tested
    runner = QualityTestRunner(judge_model=args.judge_model)
    test_cases = runner.load_test_cases(args.test)

    if not test_cases:
        print(f"❌ No test cases found" + (f" for test ID: {args.test}" if args.test else ""))
        sys.exit(1)

    if models is None:
        models = [runner.config.default_llm_provider]

    print("\n" + "=" * 60)
    print("Quality Test Configuration")
    print("=" * 60)
    print(f"Test cases: {len(test_cases)}")
    for tc in test_cases:
        print(f"  - {tc.test_id}")
    print(f"Models: {', '.join(models)}")
    print(f"Queries per run: {len(test_cases) * len(models)}")
    if args.runs > 1:
        print(f"Number of runs: {args.runs}")
        print(f"Total queries: {len(test_cases) * len(models) * args.runs}")
    print(f"Judge model: {args.judge_model}")
    print("=" * 60)

    # Confirmation
    if not args.yes:
        response = input("\nProceed with tests? (y/N): ")
        if response.lower() not in ["y", "yes"]:
            print("Cancelled.")
            sys.exit(0)

    # Run tests
    print("\nRunning tests...")
    try:
        if args.runs == 1:
            # Single run - use existing logic
            test_suite = asyncio.run(runner.run_tests(test_id=args.test, models=models))

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
                runner.run_tests_multi(runs=args.runs, test_id=args.test, models=models)
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

            print("\n" + "=" * 60)
            print(f"Test Results Summary ({args.runs} runs)")
            print("=" * 60)
            print(f"Average score: {overall_avgs['score_pct']:.1f}% (±{overall_stds['score_pct']:.1f}%)")
            print(f"Average time: {overall_avgs['time']:.2f}s (±{overall_stds['time']:.2f}s)")
            print(f"Average cost: ${overall_avgs['cost']:.4f} (±${overall_stds['cost']:.4f})")
            print(f"Average response chars: {overall_avgs['chars']:.0f} (±{overall_stds['chars']:.0f})")
            print("=" * 60)

            # Print per-model averages
            for model in aggregator.models:
                avgs = aggregator.get_model_averages(model)
                stds = aggregator.get_model_std_devs(model)
                print(
                    f"{model}: {avgs['score_pct']:.1f}% (±{stds['score_pct']:.1f}%) | "
                    f"{avgs['time']:.2f}s (±{stds['time']:.2f}s) | "
                    f"${avgs['cost']:.4f} (±${stds['cost']:.4f})"
                )

            print(f"\nAggregated report saved to: {report_path}")

    except Exception as e:
        logger.error(f"Quality tests failed: {e}", exc_info=True)
        print(f"\n❌ Quality tests failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
