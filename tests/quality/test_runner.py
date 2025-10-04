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
)
from tests.quality.evaluator import RequirementEvaluator
from src.services.llm.factory import LLMProviderFactory
from src.services.rag.retriever import RAGRetriever, RetrieveRequest
from src.services.rag.vector_db import VectorDBService
from src.services.rag.embeddings import EmbeddingService
from src.services.llm.base import GenerationRequest, GenerationConfig
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
        llm_response = await llm_provider.generate(
            GenerationRequest(
                prompt=test_case.query,
                context=[chunk.text for chunk in rag_context.document_chunks],
                config=GenerationConfig(timeout_seconds=60),
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
            requirements=requirement_results,
            score=score,
            max_score=test_case.max_score,
            generation_time_seconds=generation_time,
            token_count=total_tokens,
            cost_usd=cost,
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
                except Exception as e:
                    logger.error(
                        f"Test '{test_case.test_id}' failed with model '{model}': {e}",
                        exc_info=True,
                    )
                    # Continue with other tests

        # Create test suite
        timestamp = datetime.now(timezone.utc).isoformat()
        return QualityTestSuite(
            timestamp=timestamp,
            test_results=test_results,
            total_tests=len(test_cases),
            total_queries=len(test_results),
            total_time_seconds=total_time,
            total_cost_usd=total_cost,
            judge_model=self.judge_model,
        )

    def generate_markdown_report(
        self, test_suite: QualityTestSuite, output_file: Optional[str] = None
    ) -> str:
        """Generate markdown report from test suite results.

        Args:
            test_suite: Test suite results
            output_file: Optional file path to write report to

        Returns:
            Markdown report as string
        """
        # Generate timestamp for filename
        dt = datetime.fromisoformat(test_suite.timestamp)
        timestamp_str = dt.strftime("%Y-%m-%d_%H-%M-%S")

        if output_file is None:
            output_dir = Path("tests/quality/results")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / f"quality_test_{timestamp_str}.md"

        # Build markdown report
        lines = []
        lines.append(f"# Quality Test Results - {timestamp_str}")
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Total tests**: {test_suite.total_tests}")
        lines.append(f"- **Total queries**: {test_suite.total_queries}")
        lines.append(f"- **Total time**: {test_suite.total_time_seconds:.2f}s")
        lines.append(f"- **Total cost**: ${test_suite.total_cost_usd:.4f}")
        lines.append(f"- **Judge model**: {test_suite.judge_model}")
        lines.append("")

        # Add per-model summary (one-line format)
        lines.append("### Results by Model")
        lines.append("")
        for result in test_suite.test_results:
            status = "✅" if result.passed else "❌"
            lines.append(
                f"- {status} **{result.test_id}** [{result.model}]: "
                f"{result.score}/{result.max_score} "
                f"({result.generation_time_seconds:.2f}s, ${result.cost_usd:.4f})"
            )
        lines.append("")

        # Group results by test_id
        from collections import defaultdict

        results_by_test = defaultdict(list)
        for result in test_suite.test_results:
            results_by_test[result.test_id].append(result)

        # Individual test results
        lines.append("## Individual Test Results")
        lines.append("")

        for test_id, results in results_by_test.items():
            # Use first result for query (same across models)
            first_result = results[0]

            lines.append(f"### Test: {test_id}")
            lines.append("")
            lines.append(f"**Query:** {first_result.query}")
            lines.append("")

            # Results for each model
            for result in results:
                pass_mark = "✅" if result.passed else "❌"
                lines.append(f"**Model: {result.model}**")
                lines.append("")
                lines.append(
                    f"- Score: {result.score}/{result.max_score} {pass_mark} ({result.pass_rate:.1f}%)"
                )
                lines.append(f"- Time: {result.generation_time_seconds:.2f}s")
                lines.append(f"- Tokens: {result.token_count}")
                lines.append(f"- Cost: ${result.cost_usd:.4f}")
                lines.append("")

                # Requirements breakdown
                lines.append("#### Requirements:")
                lines.append("")
                for req_result in result.requirements:
                    status = "✅" if req_result.passed else "❌"
                    lines.append(
                        f"- {status} **{req_result.requirement.type.upper()}** "
                        f"({req_result.points_earned}/{req_result.requirement.points} pts): "
                        f"{req_result.requirement.description}"
                    )
                    if req_result.details:
                        # Format LLM judge responses differently
                        if req_result.requirement.type == "llm":
                            # Split on first newline to separate YES/NO from explanation
                            details_parts = req_result.details.split('\n', 1)
                            if len(details_parts) == 2:
                                verdict = details_parts[0].strip()
                                explanation = details_parts[1].strip()
                                lines.append(f"  - _{verdict}_")
                                lines.append("")
                                lines.append(f"> {explanation}")
                            else:
                                # Fallback if no newline
                                lines.append(f"  - _{req_result.details}_")
                        else:
                            lines.append(f"  - _{req_result.details}_")
                    lines.append("")

                lines.append("---")
                lines.append("")

                # Save response to separate file
                response_filename = f"{timestamp_str}_{result.test_id}_{result.model}.md"
                response_filepath = Path(output_file).parent / response_filename

                with open(response_filepath, "w") as f:
                    f.write(result.response)

                lines.append(f"#### Response:")
                lines.append("")
                lines.append(f"See [{response_filename}]({response_filename})")
                lines.append("")
                lines.append("---")
                lines.append("")

        # Write to file
        markdown = "\n".join(lines)
        with open(output_file, "w") as f:
            f.write(markdown)

        logger.info(f"Report written to {output_file}")
        return markdown


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

    args = parser.parse_args()

    # Determine models to test
    models = None
    if args.all_models:
        models = LLMProviderFactory.get_available_providers()
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
    print(f"Total queries: {len(test_cases) * len(models)}")
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
        test_suite = asyncio.run(runner.run_tests(test_id=args.test, models=models))

        # Generate report
        markdown_report = runner.generate_markdown_report(test_suite)

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

        print(f"\nFull report saved to: {runner.generate_markdown_report.__defaults__}")

    except Exception as e:
        logger.error(f"Quality tests failed: {e}", exc_info=True)
        print(f"\n❌ Quality tests failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
