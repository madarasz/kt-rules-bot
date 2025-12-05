"""Quality test runner for response quality testing.

Runs quality tests against the RAG + LLM pipeline.
"""

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import yaml

from src.lib.config import get_config
from src.lib.constants import (
    LLM_GENERATION_TIMEOUT,
    QUALITY_TEST_JUDGE_MODEL,
    QUALITY_TEST_JUDGING,
    QUALITY_TEST_MAX_CONCURRENT_LLM_REQUESTS,
    RAG_MAX_CHUNKS,
    RAG_MAX_HOPS,
)
from src.lib.logging import get_logger
from src.lib.tokens import estimate_cost
from src.models.rag_context_serializer import RAGContextSerializationError, load_rag_context
from src.models.structured_response import StructuredLLMResponse
from src.services.llm.base import (
    AuthenticationError,
    ContentFilterError,
    GenerationConfig,
    RateLimitError,
)
from src.services.llm.base import TimeoutError as LLMTimeoutError
from src.services.llm.factory import LLMProviderFactory
from src.services.llm.retry import retry_with_rate_limit_backoff
from src.services.orchestrator import QueryOrchestrator
from src.services.rag.embeddings import EmbeddingService
from src.services.rag.retriever import RAGRetriever
from src.services.rag.vector_db import VectorDBService
from tests.quality.metadata_generator import MetadataFormatter, MetadataGenerator, OutputMetadata
from tests.quality.ragas_evaluator import RagasEvaluator
from tests.quality.reporting.report_models import IndividualTestResult
from tests.quality.test_case_models import GroundTruthAnswer, GroundTruthContext, TestCase

logger = get_logger(__name__)


class QualityTestRunner:
    """Runs quality tests and generates results."""

    def __init__(
        self,
        test_cases_dir: str = "tests/quality/test_cases",
        judge_model: str = QUALITY_TEST_JUDGE_MODEL,
    ):
        """Initialize test runner."""
        self.test_cases_dir = Path(test_cases_dir)
        self.judge_model = judge_model
        self.ragas_evaluator = RagasEvaluator(llm_model=judge_model)
        self.config = get_config()
        self.vector_db = VectorDBService(collection_name="kill_team_rules")
        self.embedding_service = EmbeddingService()
        self.rag_retriever = RAGRetriever(
            vector_db_service=self.vector_db, embedding_service=self.embedding_service
        )
        # Initialize LLM factory
        self.llm_factory = LLMProviderFactory()

        # Initialize shared orchestrator for consistent RAG + LLM behavior
        self.orchestrator = QueryOrchestrator(
            rag_retriever=self.rag_retriever,
            llm_factory=self.llm_factory,
            enable_quote_validation=True,  # Enable quote validation for quality tests
        )

        # Semaphore to limit concurrent LLM requests (prevents rate limit errors)
        self.llm_semaphore = asyncio.Semaphore(QUALITY_TEST_MAX_CONCURRENT_LLM_REQUESTS)
        # Semaphore to serialize Ragas evaluations (Ragas is not thread-safe for parallel execution)
        self.ragas_semaphore = asyncio.Semaphore(1)

        # Log quality test configuration
        logger.info(
            "quality_test_config",
            judging_mode=QUALITY_TEST_JUDGING,
            judge_model=judge_model if QUALITY_TEST_JUDGING == "RAGAS" else "N/A",
        )

    def load_test_cases(self, test_id: str | None = None) -> list[TestCase]:
        """Load test cases from YAML files with new key-based format.

        Expected YAML format:
            ground_truth_answers:
              - key: "answer_1"
                text: "Answer text"
                priority: "critical"  # optional, defaults to "critical"

            ground_truth_contexts:
              - key: "context_1"
                text: "Context text"
                priority: "critical"  # optional
        """
        test_cases = []
        files = (
            [self.test_cases_dir / f"{test_id}.yaml"]
            if test_id
            else list(self.test_cases_dir.glob("*.yaml"))
        )
        for file in files:
            if not file.exists():
                logger.warning(f"Test file not found: {file}")
                continue
            try:
                with open(file) as f:
                    data = yaml.safe_load(f)

                # Parse ground_truth_answers (new format with keys)
                answers_data = data.get("ground_truth_answers", [])
                answers = []
                for ans_data in answers_data:
                    if isinstance(ans_data, dict) and "key" in ans_data:
                        # New format: {key, text, priority}
                        answers.append(
                            GroundTruthAnswer(
                                key=ans_data["key"],
                                text=ans_data["text"],
                                priority=ans_data.get("priority", "critical"),
                            )
                        )
                    else:
                        raise ValueError(
                            f"Invalid ground_truth_answers format in {file.name}. "
                            f"Expected dict with 'key' and 'text' fields. "
                            f"Got: {type(ans_data)}"
                        )

                # Parse ground_truth_contexts (new format with keys)
                contexts_data = data.get("ground_truth_contexts", [])
                contexts = []
                for ctx_data in contexts_data:
                    if isinstance(ctx_data, dict) and "key" in ctx_data:
                        # New format: {key, text, priority}
                        contexts.append(
                            GroundTruthContext(
                                key=ctx_data["key"],
                                text=ctx_data["text"],
                                priority=ctx_data.get("priority", "critical"),
                            )
                        )
                    else:
                        raise ValueError(
                            f"Invalid ground_truth_contexts format in {file.name}. "
                            f"Expected dict with 'key' and 'text' fields. "
                            f"Got: {type(ctx_data)}"
                        )

                test_cases.append(
                    TestCase(
                        test_id=data["test_id"],
                        query=data["query"],
                        ground_truth_answers=answers,
                        ground_truth_contexts=contexts,
                        context_file=data.get("context_file", None),  # Optional cached context
                        requirements=data.get("requirements", None),  # Legacy field
                    )
                )
                logger.info(f"Loaded test case: {data['test_id']} ({len(answers)} answers, {len(contexts)} contexts)")
            except Exception as e:
                logger.error(f"Failed to load test case from {file}: {e}")
        return test_cases

    async def run_test(
        self,
        test_case: TestCase,
        model: str,
        run_num: int,
        report_dir: Path,
        rag_context=None,
        hop_evaluations=None,
        embedding_cost=0.0,
        query_id=None,
        no_eval: bool = False,
    ) -> IndividualTestResult:
        """Run a single test case.

        Args:
            test_case: The test case to run
            model: The LLM model to use
            run_num: The run number (for multiple runs)
            report_dir: Directory to save outputs
            rag_context: Pre-retrieved RAG context (optional)
            hop_evaluations: Pre-retrieved hop evaluations (optional)
            embedding_cost: Pre-calculated embedding cost (optional)
            query_id: Query UUID for correlation (optional)
            no_eval: If True, skip Ragas evaluation (only generate outputs)
        """
        eval_mode = " (no-eval)" if no_eval else ""
        logger.info(
            f"Running test '{test_case.test_id}' with model '{model}' (Run #{run_num}){eval_mode}"
        )

        multi_hop_cost = 0.0

        if rag_context is None:
            # Fallback: retrieve RAG context if not provided
            # This path is for backward compatibility when run_test is called directly
            from uuid import uuid4

            query_id = query_id or uuid4()
            rag_context, hop_evaluations, _, embedding_cost = await self.orchestrator.retrieve_rag(
                query=test_case.query,
                query_id=query_id,
                max_chunks=RAG_MAX_CHUNKS,
                context_key="quality_test",
                use_multi_hop=RAG_MAX_HOPS > 0,
            )

        # Calculate multi-hop evaluation costs if any
        if hop_evaluations:
            multi_hop_cost = sum(hop.cost_usd for hop in hop_evaluations)
            logger.debug(
                "multi_hop_costs_calculated",
                num_hops=len(hop_evaluations),
                total_cost=multi_hop_cost,
            )

        # Create LLM provider for this model
        llm_provider = LLMProviderFactory.create(model)
        GenerationConfig(timeout_seconds=LLM_GENERATION_TIMEOUT)
        output_filename = report_dir / f"output_{test_case.test_id}_{model}_{run_num}.md"

        # Ensure we have a query_id
        if query_id is None:
            from uuid import uuid4
            query_id = uuid4()

        error_str = None
        llm_response_text = ""
        token_count = 0
        json_formatted = False
        structured_quotes_count = 0
        structured_llm_response = None  # For Ragas evaluation
        generation_time = 0.0  # Initialize to 0 in case of early errors
        actual_prompt_tokens = 0  # Initialize to 0 in case of errors
        actual_completion_tokens = 0  # Initialize to 0 in case of errors
        actual_model_id = model  # Initialize to friendly name, update from response if successful

        try:
            # Use semaphore to limit concurrent requests and prevent rate limits
            async with self.llm_semaphore:
                # Start timing right before LLM API call
                llm_start_time = datetime.now(UTC)

                # Wrap orchestrator call with quality test retry strategy
                async def generate_with_orchestrator():
                    return await self.orchestrator.generate_with_context(
                        query=test_case.query,
                        query_id=query_id,
                        model=model,
                        rag_context=rag_context,
                        llm_provider=llm_provider,
                        generation_timeout=LLM_GENERATION_TIMEOUT,
                    )

                llm_response, _chunk_ids = await retry_with_rate_limit_backoff(
                    generate_with_orchestrator,
                    timeout_seconds=LLM_GENERATION_TIMEOUT,
                )

                # Stop timing immediately after LLM response
                generation_time = (datetime.now(UTC) - llm_start_time).total_seconds()

            llm_response_text = llm_response.answer_text
            token_count = llm_response.token_count
            # Capture actual token split and model version from LLM response
            actual_prompt_tokens = llm_response.prompt_tokens
            actual_completion_tokens = llm_response.completion_tokens
            actual_model_id = llm_response.model_version  # Use actual model ID for accurate cost calculation

            # Keep original JSON for Ragas evaluation
            llm_response_json = llm_response_text
            llm_response_markdown = llm_response_text

            # Try to parse structured JSON response
            if llm_response_text.strip().startswith("{"):
                try:
                    structured_data = StructuredLLMResponse.from_json(llm_response_text)
                    structured_data.validate()
                    json_formatted = True
                    structured_quotes_count = len(structured_data.quotes)
                    structured_llm_response = structured_data  # Save for Ragas
                    logger.debug(
                        f"Parsed structured JSON for {test_case.test_id}: "
                        f"{structured_quotes_count} quotes, smalltalk={structured_data.smalltalk}"
                    )
                    # Convert to markdown for display/saving
                    llm_response_markdown = structured_data.to_markdown()
                except (ValueError, json.JSONDecodeError) as e:
                    logger.warning(f"Failed to parse structured JSON for {test_case.test_id}: {e}")
                    json_formatted = False

        except LLMTimeoutError as e:
            logger.error(f"LLM timeout for {test_case.test_id} on {model}: {e}")
            error_str = f"Timeout after {LLM_GENERATION_TIMEOUT}s"
            llm_response_json = f"[LLM Timeout Error: {error_str}]"
            llm_response_markdown = llm_response_json
        except RateLimitError as e:
            logger.error(f"LLM rate limit for {test_case.test_id} on {model}: {e}")
            error_str = f"Rate limit exceeded: {str(e)}"
            llm_response_json = f"[LLM Rate Limit Error: {error_str}]"
            llm_response_markdown = llm_response_json
        except ContentFilterError as e:
            logger.error(f"LLM content filter for {test_case.test_id} on {model}: {e}")
            error_str = f"Content filtered: {str(e)}"
            llm_response_json = f"[LLM Content Filter Error: {error_str}]"
            llm_response_markdown = llm_response_json
        except AuthenticationError as e:
            logger.error(f"LLM authentication error for {test_case.test_id} on {model}: {e}")
            error_str = f"Authentication failed: {str(e)}"
            llm_response_json = f"[LLM Authentication Error: {error_str}]"
            llm_response_markdown = llm_response_json
        except Exception as e:
            logger.error(f"LLM generation failed for {test_case.test_id} on {model}: {e}")
            error_str = f"{type(e).__name__}: {str(e)}"
            llm_response_json = f"[LLM Generation Failed: {error_str}]"
            llm_response_markdown = llm_response_json

        # Evaluate with Ragas metrics (skip if no_eval is True)
        # Note: We save output AFTER evaluation to include metrics in the report
        if no_eval:
            # Skip Ragas evaluation - create empty metrics
            from tests.quality.ragas_evaluator import RagasMetrics

            ragas_metrics = RagasMetrics()
            score = 0.0
            passed = False
        else:
            # Use semaphore to serialize Ragas evaluations (Ragas is not thread-safe)
            async with self.ragas_semaphore:
                ragas_metrics = await self.ragas_evaluator.evaluate(
                    query=test_case.query,
                    llm_response=structured_llm_response,
                    context_chunks=rag_context.document_chunks,  # Pass DocumentChunk objects (not just text)
                    ground_truth_answers=test_case.ground_truth_answers,
                    ground_truth_contexts=test_case.ground_truth_contexts,
                )

            # Calculate aggregate score from Ragas metrics
            score = self.ragas_evaluator.calculate_aggregate_score(ragas_metrics)
            passed = score >= 80.0  # 80% threshold for passing

        # Check if any Ragas metrics failed (are None when they should have values)
        # This indicates a Ragas evaluation failure that should be tracked for grey bar visualization
        ragas_evaluation_error = False
        # Check if any of the LLM-based Ragas metrics failed
        # (quote_precision and quote_recall are locally calculated and should always succeed)
        # Only flag as error if judging mode is RAGAS (otherwise None is expected)
        if (
            not no_eval
            and structured_llm_response is not None
            and QUALITY_TEST_JUDGING == "RAGAS"
            and (
                ragas_metrics.quote_faithfulness is None
                or ragas_metrics.explanation_faithfulness is None
                or ragas_metrics.answer_correctness is None
            )
        ):
            ragas_evaluation_error = True
            logger.error(
                f"Ragas evaluation failed for test {test_case.test_id} on model {model} - "
                f"some metrics returned None/NaN"
            )

        # Check if custom judge evaluation failed (for CUSTOM judging mode)
        # The error is stored in ragas_metrics.error by the evaluator
        if (
            not no_eval
            and structured_llm_response is not None
            and QUALITY_TEST_JUDGING == "CUSTOM"
            and ragas_metrics.error
        ):
            ragas_evaluation_error = True
            logger.error(
                f"Custom judge evaluation failed for test {test_case.test_id} on model {model} - "
                f"Error: {ragas_metrics.error}"
            )

        # Calculate main LLM cost using actual token split and model ID
        cost = estimate_cost(
            prompt_tokens=actual_prompt_tokens,
            completion_tokens=actual_completion_tokens,
            model=actual_model_id,
        )

        # Log comprehensive cost breakdown
        total_cost = cost + multi_hop_cost + ragas_metrics.total_cost_usd + embedding_cost
        logger.info(
            "test_cost_breakdown",
            test_id=test_case.test_id,
            model=model,
            main_llm_cost=cost,
            multi_hop_cost=multi_hop_cost,
            ragas_cost=ragas_metrics.total_cost_usd,
            embedding_cost=embedding_cost,
            total_cost=total_cost,
        )

        # Defensive handling: Convert NaN to 0 before int conversion
        # This should not happen anymore after our fixes, but be extra defensive
        import math

        if isinstance(score, float) and math.isnan(score):
            logger.error(
                f"Score is NaN for test {test_case.test_id} on model {model} - converting to 0"
            )
            score = 0.0
            ragas_evaluation_error = True

        # Save markdown output for human reading (with metrics and metadata if available)
        self._save_output(
            output_filename,
            test_case.query,
            llm_response_markdown,
            ragas_metrics=ragas_metrics if not no_eval else None,
            # Metadata parameters for replay support
            test_id=test_case.test_id,
            model=model,
            run_num=run_num,
            llm_response=llm_response if error_str is None else None,  # Only if LLM call succeeded
            cost_usd=cost,
            multi_hop_cost_usd=multi_hop_cost,
            embedding_cost_usd=embedding_cost,
            generation_time_seconds=generation_time,
        )

        return IndividualTestResult(
            test_id=test_case.test_id,
            query=test_case.query,
            model=model,
            score=int(score),
            max_score=test_case.max_score,
            passed=passed,
            tokens=token_count,
            cost_usd=cost,
            multi_hop_cost_usd=multi_hop_cost,
            ragas_cost_usd=ragas_metrics.total_cost_usd,
            embedding_cost_usd=embedding_cost,
            output_char_count=len(llm_response_markdown),
            generation_time_seconds=generation_time,
            output_filename=str(output_filename),
            error=error_str,
            json_formatted=json_formatted,
            structured_quotes_count=structured_quotes_count,
            quote_precision=ragas_metrics.quote_precision,
            quote_recall=ragas_metrics.quote_recall,
            quote_faithfulness=ragas_metrics.quote_faithfulness,
            explanation_faithfulness=ragas_metrics.explanation_faithfulness,
            answer_correctness=ragas_metrics.answer_correctness,
            ragas_error=ragas_metrics.error,
            quote_precision_feedback=ragas_metrics.quote_precision_feedback,
            quote_recall_feedback=ragas_metrics.quote_recall_feedback,
            quote_faithfulness_feedback=ragas_metrics.quote_faithfulness_feedback,
            explanation_faithfulness_feedback=ragas_metrics.explanation_faithfulness_feedback,
            answer_correctness_feedback=ragas_metrics.answer_correctness_feedback,
            feedback=ragas_metrics.feedback,  # Unified custom judge feedback
            ragas_evaluation_error=ragas_evaluation_error,
            quote_faithfulness_details=ragas_metrics.quote_faithfulness_details,
            answer_correctness_details=ragas_metrics.answer_correctness_details,
            llm_quotes_structured=ragas_metrics.llm_quotes_structured,
            requirements=None,  # Legacy field, no longer used
        )

    async def run_tests_in_parallel(
        self,
        runs: int,
        report_dir: Path,
        test_id: str | None = None,
        models: list[str] | None = None,
        no_eval: bool = False,
        force_rag: bool = False,
    ) -> list[IndividualTestResult]:
        """Run all test combinations in parallel with concurrency control.

        Tests are run in parallel but LLM requests are limited by semaphore
        to prevent rate limit errors. Maximum concurrent LLM requests is
        controlled by QUALITY_TEST_MAX_CONCURRENT_LLM_REQUESTS constant.

        Args:
            runs: Number of times to run each test
            report_dir: Directory to save results
            test_id: Specific test ID to run (default: all tests)
            models: List of models to test
            no_eval: If True, skip Ragas evaluation (only generate outputs)
            force_rag: If True, ignore cached context files and run RAG
        """
        test_cases = self.load_test_cases(test_id)
        if not test_cases:
            raise ValueError(
                f"No test cases found for test_id: {test_id}" if test_id else "No test cases found."
            )

        models_to_run = models or [self.config.default_llm_provider]

        # Save the current prompt to prompt.md once
        gen_config = GenerationConfig(timeout_seconds=LLM_GENERATION_TIMEOUT)
        self._save_prompt(report_dir / "prompt.md", gen_config.system_prompt)

        tasks = []
        for run_num in range(1, runs + 1):
            for test_case in test_cases:
                from uuid import uuid4

                query_id = uuid4()

                # Try to load cached context if available (and not forcing RAG)
                if test_case.context_file and not force_rag:
                    try:
                        # Load cached RAG context from file
                        rag_context, hop_evaluations, _, embedding_cost = load_rag_context(
                            test_case.context_file
                        )
                        logger.info(
                            f"Using cached context from {test_case.context_file} "
                            f"for test '{test_case.test_id}' (Run #{run_num})"
                        )
                    except RAGContextSerializationError as e:
                        # Don't fallback to RAG - raise error to fail fast
                        raise RAGContextSerializationError(
                            f"Failed to load cached context for test '{test_case.test_id}': {e}\n"
                            f"File: {test_case.context_file}\n"
                            f"Use --force-rag to ignore cached context and run RAG instead."
                        ) from e
                elif test_case.context_file and force_rag:
                    # Ignore cached context - run RAG normally
                    logger.info(
                        f"Ignoring cached context (--force-rag enabled) "
                        f"for test '{test_case.test_id}' (Run #{run_num})"
                    )
                    rag_context, hop_evaluations, _, embedding_cost = await self.orchestrator.retrieve_rag(
                        query=test_case.query,
                        query_id=query_id,
                        max_chunks=RAG_MAX_CHUNKS,
                        context_key="quality_test",
                        use_multi_hop=RAG_MAX_HOPS > 0,
                    )
                else:
                    # No cached context - run RAG normally
                    rag_context, hop_evaluations, _, embedding_cost = await self.orchestrator.retrieve_rag(
                        query=test_case.query,
                        query_id=query_id,
                        max_chunks=RAG_MAX_CHUNKS,
                        context_key="quality_test",
                        use_multi_hop=RAG_MAX_HOPS > 0,
                    )

                # Create tasks for each model using the same RAG context
                for model in models_to_run:
                    tasks.append(
                        self.run_test(
                            test_case,
                            model,
                            run_num,
                            report_dir,
                            rag_context,
                            hop_evaluations,
                            embedding_cost,
                            query_id,
                            no_eval,
                        )
                    )

        results = await asyncio.gather(*tasks)
        return results

    async def replay_tests_from_outputs(
        self,
        output_dir: Path,
        models: list[str] | None = None,
    ) -> tuple[list[IndividualTestResult], Path]:
        """
        Replay quality tests from saved outputs (skip RAG + LLM, re-run judge only).

        This method enables fast, cheap judge evaluation by reusing saved LLM outputs.
        Perfect for iterating on judge prompts or comparing different judge models.

        Args:
            output_dir: Path to existing results folder with output_*.md files
            models: Optional filter for specific models

        Returns:
            Tuple of (list[IndividualTestResult] with new judge evaluations, Path to replay results directory)

        Raises:
            ValueError: If output directory doesn't exist or contains no valid outputs
        """
        import shutil

        from tests.quality.output_parser import parse_output_directory

        logger.info(f"🔄 Replaying tests from: {output_dir}")

        if not output_dir.exists():
            raise ValueError(f"Output directory does not exist: {output_dir}")

        # 1. Parse all output files
        parsed_outputs = parse_output_directory(output_dir, models=models)

        if not parsed_outputs:
            raise ValueError(f"No valid output files found in {output_dir}")

        logger.info(f"Found {len(parsed_outputs)} output files to replay")

        # 2. Create new results folder
        original_name = output_dir.name
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M-%S")
        new_results_dir = (Path("tests/quality/results") / f"{timestamp}_REPLAYS_{original_name}").absolute()
        new_results_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created replay results folder: {new_results_dir}")

        # 3. Copy original outputs and prompt
        for po in parsed_outputs:
            shutil.copy(po.file_path, new_results_dir)

        prompt_md = output_dir / "prompt.md"
        if prompt_md.exists():
            shutil.copy(prompt_md, new_results_dir)
            logger.debug("Copied prompt.md")

        # 4. Load test cases
        test_cases_map = self._load_test_cases_for_outputs(parsed_outputs)

        # 5. Evaluate parsed outputs in parallel (with semaphore for judge evaluation)
        tasks = []
        for po in parsed_outputs:
            test_id = po.metadata.test_metadata["test_id"]

            if test_id not in test_cases_map:
                logger.warning(
                    f"Test case '{test_id}' not found in test suite, skipping {po.file_path.name}"
                )
                continue

            test_case = test_cases_map[test_id]

            # Create evaluation task
            tasks.append(self._evaluate_parsed_output(po, test_case))

        logger.info(f"Evaluating {len(tasks)} outputs with judge...")
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions and log errors
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Evaluation failed for output {i}: {result}")
            else:
                valid_results.append(result)

        logger.info(f"✅ Replay complete: {len(valid_results)}/{len(results)} successful")
        logger.info(f"Results saved to: {new_results_dir}")

        return valid_results, new_results_dir

    def _load_test_cases_for_outputs(
        self, parsed_outputs: list
    ) -> dict[str, TestCase]:
        """
        Load test cases referenced by parsed outputs.

        Args:
            parsed_outputs: List of ParsedOutput objects

        Returns:
            Dict mapping test_id to TestCase
        """
        # Get unique test IDs from outputs
        test_ids = {po.metadata.test_metadata["test_id"] for po in parsed_outputs}

        # Load all test cases (filtered to ones we need)
        test_cases_map = {}
        for test_id in test_ids:
            test_cases = self.load_test_cases(test_id)
            if test_cases:
                test_cases_map[test_id] = test_cases[0]

        logger.debug(f"Loaded {len(test_cases_map)} test cases")
        return test_cases_map

    async def _evaluate_parsed_output(
        self,
        parsed_output,  # ParsedOutput type
        test_case: TestCase,
    ) -> IndividualTestResult:
        """
        Evaluate a single parsed output (reuse deterministic metrics, re-run judge).

        This method reconstructs the evaluation context from saved metadata and runs
        only the judge evaluation (expensive LLM-based metrics). Deterministic metrics
        (quote precision/recall/faithfulness) are loaded from metadata.

        Args:
            parsed_output: ParsedOutput with metadata and reconstructed LLM response
            test_case: Original test case definition

        Returns:
            IndividualTestResult with original costs + new judge costs
        """
        from src.models.structured_response import StructuredLLMResponse
        from tests.quality.ragas_evaluator import RagasMetrics

        po = parsed_output
        metadata = po.metadata

        # Parse LLM response JSON to StructuredLLMResponse for evaluation
        try:
            structured_llm_response = StructuredLLMResponse.from_json(po.llm_response.answer_text)
        except Exception as e:
            logger.error(
                f"Failed to parse LLM response for {metadata.test_metadata['test_id']}: {e}"
            )
            # Create error result
            return self._create_error_result(metadata, test_case, f"Parse error: {e}")

        # Load saved deterministic metrics from metadata
        deterministic_metrics = MetadataGenerator.extract_deterministic_metrics_from_metadata(
            metadata
        )

        # Run judge evaluation based on QUALITY_TEST_JUDGING mode
        judge_cost = 0.0

        if QUALITY_TEST_JUDGING == "OFF":
            # No judge - use deterministic metrics only
            ragas_metrics = RagasMetrics(**deterministic_metrics)

        elif QUALITY_TEST_JUDGING == "CUSTOM":
            # Run custom judge (single LLM call) with semaphore
            from tests.quality.custom_judge import CustomJudge

            judge = CustomJudge(model=QUALITY_TEST_JUDGE_MODEL)

            # Use semaphore to serialize judge evaluations
            async with self.ragas_semaphore:
                try:
                    judge_result = await judge.evaluate(
                        query=po.query,
                        llm_response_text=structured_llm_response.to_json(),  # JSON string
                        llm_quotes_structured=deterministic_metrics["llm_quotes_structured"],
                        ground_truth_answers=test_case.ground_truth_answers,
                        ground_truth_contexts=[ctx.text for ctx in test_case.ground_truth_contexts],  # Just text
                    )

                    # Combine deterministic + judge metrics
                    # Update deterministic_metrics dict with judge results to avoid duplicate keyword args
                    deterministic_metrics.update({
                        "explanation_faithfulness": judge_result.explanation_faithfulness,
                        "answer_correctness": judge_result.answer_correctness,  # Not _aggregate
                        "answer_correctness_details": judge_result.answer_correctness_details,
                        "feedback": judge_result.feedback,
                    })
                    ragas_metrics = RagasMetrics(**deterministic_metrics)

                    # Calculate judge cost from actual tokens
                    judge_cost = estimate_cost(
                        prompt_tokens=judge_result.prompt_tokens,
                        completion_tokens=judge_result.completion_tokens,
                        model=QUALITY_TEST_JUDGE_MODEL,
                    )

                except Exception as e:
                    logger.error(
                        f"Custom judge evaluation failed for {metadata.test_metadata['test_id']}: {e}"
                    )
                    # Use deterministic metrics only
                    ragas_metrics = RagasMetrics(
                        **deterministic_metrics, error=f"Judge error: {e}"
                    )

        elif QUALITY_TEST_JUDGING == "RAGAS":
            # Run ragas evaluator (2 LLM calls) with semaphore
            async with self.ragas_semaphore:
                try:
                    ragas_result = await self.ragas_evaluator.evaluate(
                        query=po.query,
                        llm_response=structured_llm_response,
                        context_chunks=[],  # Not needed for judge-only evaluation
                        ground_truth_answers=test_case.ground_truth_answers,
                        ground_truth_contexts=test_case.ground_truth_contexts,
                    )

                    # Combine deterministic + ragas metrics
                    ragas_metrics = RagasMetrics(
                        **deterministic_metrics,
                        explanation_faithfulness=ragas_result.explanation_faithfulness,
                        answer_correctness=ragas_result.answer_correctness,
                        feedback=ragas_result.feedback,
                    )

                    judge_cost = ragas_result.total_cost_usd

                except Exception as e:
                    logger.error(
                        f"Ragas evaluation failed for {metadata.test_metadata['test_id']}: {e}"
                    )
                    # Use deterministic metrics only
                    ragas_metrics = RagasMetrics(
                        **deterministic_metrics, error=f"Ragas error: {e}"
                    )

        # Calculate aggregate score
        score = self.ragas_evaluator.calculate_aggregate_score(ragas_metrics)
        passed = score >= 80.0

        # Build result with original costs + new judge cost
        return IndividualTestResult(
            test_id=metadata.test_metadata["test_id"],
            query=po.query,
            model=metadata.test_metadata["model"],
            score=int(score),
            max_score=test_case.max_score,
            passed=passed,
            tokens=metadata.tokens["total"],
            # Original costs (NOT re-incurred)
            cost_usd=metadata.costs["llm_generation_usd"],
            multi_hop_cost_usd=metadata.costs["multi_hop_usd"],
            embedding_cost_usd=metadata.costs["embedding_usd"],
            # NEW judge cost
            ragas_cost_usd=judge_cost,
            output_char_count=len(structured_llm_response.to_markdown()),
            # Original latency
            generation_time_seconds=metadata.latency["llm_generation_seconds"],
            output_filename="",  # Not needed for replay
            error=None,
            json_formatted=True,  # Assume formatted if we could parse metadata
            structured_quotes_count=len(structured_llm_response.quotes),
            # Metrics (deterministic from metadata + judge from evaluation)
            quote_precision=ragas_metrics.quote_precision,
            quote_recall=ragas_metrics.quote_recall,
            quote_faithfulness=ragas_metrics.quote_faithfulness,
            explanation_faithfulness=ragas_metrics.explanation_faithfulness,
            answer_correctness=ragas_metrics.answer_correctness,
            ragas_error=ragas_metrics.error,
            quote_precision_feedback=ragas_metrics.quote_precision_feedback,
            quote_recall_feedback=ragas_metrics.quote_recall_feedback,
            quote_faithfulness_feedback=ragas_metrics.quote_faithfulness_feedback,
            explanation_faithfulness_feedback=ragas_metrics.explanation_faithfulness_feedback,
            answer_correctness_feedback=ragas_metrics.answer_correctness_feedback,
            feedback=ragas_metrics.feedback,
            ragas_evaluation_error=ragas_metrics.error is not None,
            quote_faithfulness_details=ragas_metrics.quote_faithfulness_details,
            answer_correctness_details=ragas_metrics.answer_correctness_details,
            llm_quotes_structured=ragas_metrics.llm_quotes_structured,
        )

    def _create_error_result(
        self, metadata: "OutputMetadata", test_case: TestCase, error_msg: str
    ) -> IndividualTestResult:
        """Create an error result when evaluation fails."""
        return IndividualTestResult(
            test_id=metadata.test_metadata["test_id"],
            query=test_case.query,
            model=metadata.test_metadata["model"],
            score=0,
            max_score=test_case.max_score,
            passed=False,
            tokens=metadata.tokens["total"],
            cost_usd=metadata.costs["llm_generation_usd"],
            multi_hop_cost_usd=metadata.costs["multi_hop_usd"],
            embedding_cost_usd=metadata.costs["embedding_usd"],
            ragas_cost_usd=0.0,
            output_char_count=0,
            generation_time_seconds=metadata.latency["llm_generation_seconds"],
            output_filename="",
            error=error_msg,
        )

    def _save_output(
        self,
        filename: Path,
        query: str,
        response: str,
        ragas_metrics=None,
        # Metadata generation parameters (optional, for replay support)
        test_id: str | None = None,
        model: str | None = None,
        run_num: int | None = None,
        llm_response=None,  # LLMResponse object
        cost_usd: float | None = None,
        multi_hop_cost_usd: float | None = None,
        embedding_cost_usd: float | None = None,
        generation_time_seconds: float | None = None,
    ):
        """Saves the query and response to a file with quality metrics and metadata.

        Args:
            filename: Path to save output file
            query: Original query text
            response: LLM response (markdown format)
            ragas_metrics: Evaluation metrics (optional)
            test_id: Test case ID (for metadata)
            model: Model name (for metadata)
            run_num: Run number (for metadata)
            llm_response: LLMResponse object (for metadata token counts)
            cost_usd: LLM generation cost (for metadata)
            multi_hop_cost_usd: Multi-hop RAG cost (for metadata)
            embedding_cost_usd: Embedding cost (for metadata)
            generation_time_seconds: LLM generation latency (for metadata)
        """
        content = f"# Query\n\n{query}\n\n---\n\n# Response\n\n{response}\n\n"

        # Add quote validation issues if available
        if (
            ragas_metrics
            and hasattr(ragas_metrics, "quote_faithfulness_details")
            and ragas_metrics.quote_faithfulness_details
        ):
            failed_quotes = [
                (chunk_id, similarity)
                for chunk_id, similarity in ragas_metrics.quote_faithfulness_details.items()
                if similarity < 1.0
            ]

            if failed_quotes:
                content += "---\n\n## ⚠️ Quote Validation Issues\n\n"
                if ragas_metrics.quote_faithfulness is not None:
                    content += f"**Quote Faithfulness Score**: {ragas_metrics.quote_faithfulness:.2f}\n\n"

                # Get the quote scores with full details if available
                if hasattr(ragas_metrics, "llm_quotes_structured"):
                    # Try to match failed quotes with full quote data
                    quote_map = {}
                    if ragas_metrics.llm_quotes_structured:
                        for quote_dict in ragas_metrics.llm_quotes_structured:
                            chunk_id = quote_dict.get("chunk_id", "")
                            if chunk_id:
                                # Extract last 8 chars if it's a full UUID
                                short_id = chunk_id[-8:] if len(chunk_id) > 8 else chunk_id
                                quote_map[short_id] = quote_dict

                    for chunk_id, similarity in failed_quotes:
                        content += f"### Quote `{chunk_id}` (similarity: {similarity:.2f})\n\n"

                        # Show quote details if available
                        if chunk_id in quote_map:
                            quote_data = quote_map[chunk_id]
                            content += f"**Title**: {quote_data.get('quote_title', 'Unknown')}\n\n"
                            content += f"**Quote Text**:\n```\n{quote_data.get('quote_text', '')}\n```\n\n"
                else:
                    # Fallback: just list chunk IDs and similarities
                    for chunk_id, similarity in failed_quotes:
                        content += f"- Chunk `{chunk_id}`: similarity {similarity:.2f}\n"
                        content += "\n"

        # Add answer correctness issues if available
        if (
            ragas_metrics
            and hasattr(ragas_metrics, "answer_correctness_details")
            and ragas_metrics.answer_correctness_details
        ):
            failed_answers = [
                (key, score)
                for key, score in ragas_metrics.answer_correctness_details.items()
                if score < 1.0
            ]

            if failed_answers:
                content += "---\n\n## ⚠️ Answer Correctness Issues\n\n"
                if ragas_metrics.answer_correctness is not None:
                    content += f"**Answer Correctness Score**: {ragas_metrics.answer_correctness:.2f}\n\n"

                for answer_key, score in failed_answers:
                    content += f"- **{answer_key}**: {score:.2f}\n"
                content += "\n"

        # Generate and append metadata if all required parameters are provided
        if all(
            [
                test_id is not None,
                model is not None,
                run_num is not None,
                llm_response is not None,
                ragas_metrics is not None,
                cost_usd is not None,
                generation_time_seconds is not None,
            ]
        ):
            # Create a minimal IndividualTestResult for metadata generation
            # (MetadataGenerator.generate_metadata() expects this)
            result = IndividualTestResult(
                test_id=test_id,
                query=query,
                model=model,
                score=0,  # Not needed for metadata
                max_score=0,  # Not needed for metadata
                passed=False,  # Not needed for metadata
                tokens=llm_response.token_count,
                cost_usd=cost_usd,
                multi_hop_cost_usd=multi_hop_cost_usd or 0.0,
                embedding_cost_usd=embedding_cost_usd or 0.0,
                output_char_count=0,  # Not needed for metadata
                generation_time_seconds=generation_time_seconds,
                output_filename="",  # Not needed for metadata
            )

            metadata = MetadataGenerator.generate_metadata(
                test_id=test_id,
                model=model,
                run_num=run_num,
                llm_response=llm_response,
                result=result,
                metrics=ragas_metrics,
            )

            metadata_block = MetadataFormatter.format_metadata_block(metadata)
            content += metadata_block

        os.makedirs(filename.parent, exist_ok=True)
        with open(filename, "w") as f:
            f.write(content)

    def _save_prompt(self, filename: Path, system_prompt: str):
        """Saves the current LLM prompt to a file."""
        content = f"# Current LLM System Prompt\n\n```\n{system_prompt}\n```\n"
        os.makedirs(filename.parent, exist_ok=True)
        with open(filename, "w") as f:
            f.write(content)
