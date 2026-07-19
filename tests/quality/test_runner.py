"""Quality test runner for response quality testing.

Runs quality tests against the RAG + LLM pipeline.
"""

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from tests.quality.batch.manifest import BatchManifest

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
from src.lib.tokens import calculate_llm_cost
from src.models.rag_context_serializer import RAGContextSerializationError, load_rag_context
from src.models.structured_response import StructuredLLMResponse
from src.services.llm.base import (
    AuthenticationError,
    ContentFilterError,
    GenerationConfig,
    GenerationRequest,
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
            judge_model=judge_model if QUALITY_TEST_JUDGING != "OFF" else "N/A",
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
        defer_judge: bool = False,
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
            defer_judge: If True, compute the deterministic quote metrics but skip
                the LLM judge, persisting metrics so a later pass (batch-collect)
                judges once. Used for the live fallback of batch-submit.
        """
        eval_mode = " (no-eval)" if no_eval else " (defer-judge)" if defer_judge else ""
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
        llm_response = None
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
        elif defer_judge:
            # Compute the deterministic (non-LLM) quote metrics now and skip the
            # judge; the deferred scoring pass runs the judge exactly once. Same
            # persisted shape as the batch-generation path.
            from tests.quality.ragas_evaluator import RagasMetrics

            if structured_llm_response is not None:
                ragas_metrics = self.ragas_evaluator.compute_deterministic_metrics(
                    llm_response=structured_llm_response,
                    context_texts=[c.text for c in rag_context.document_chunks],
                    chunk_ids=[str(c.chunk_id) for c in rag_context.document_chunks],
                    ground_truth_contexts=test_case.ground_truth_contexts,
                )
            else:
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
            and not defer_judge
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
        llm_breakdown = calculate_llm_cost(
            prompt_tokens=actual_prompt_tokens,
            completion_tokens=actual_completion_tokens,
            model=actual_model_id,
            cache_read_tokens=llm_response.cache_read_tokens if llm_response is not None else 0,
            cache_creation_tokens=llm_response.cache_creation_tokens if llm_response is not None else 0,
        )
        cost = llm_breakdown.total_cost
        cache_savings = llm_breakdown.cache_savings

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
            cache_savings=cache_savings,
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
            cache_savings_usd=cache_savings,
        )

        return IndividualTestResult(
            test_id=test_case.test_id,
            query=test_case.query,
            model=model,
            run_num=run_num,
            score=int(score),
            max_score=test_case.max_score,
            passed=passed,
            tokens=token_count,
            cost_usd=cost,
            multi_hop_cost_usd=multi_hop_cost,
            ragas_cost_usd=ragas_metrics.total_cost_usd,
            embedding_cost_usd=embedding_cost,
            cache_savings_usd=cache_savings,
            judge_cache_savings_usd=ragas_metrics.cache_savings_usd,
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
                        # Note: We ignore the cached costs (_cached_embedding_cost, hop_evaluations costs)
                        # because no RAG retrieval is performed when using cache
                        rag_context, hop_evaluations, _, _cached_embedding_cost = load_rag_context(
                            test_case.context_file
                        )
                        # Zero out RAG-related costs since no API calls were made
                        embedding_cost = 0.0
                        # Clear hop evaluations to prevent multi_hop_cost calculation in run_test()
                        hop_evaluations = []
                        logger.info(
                            f"Using cached context from {test_case.context_file} "
                            f"for test '{test_case.test_id}' (Run #{run_num}) "
                            f"(RAG costs zeroed)"
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

    # ------------------------------------------------------------------
    # Batch API: two-phase submit/collect state machine
    # ------------------------------------------------------------------

    async def _retrieve_rag_for_test(self, test_case, query_id, force_rag):
        """Retrieve (or load cached) RAG context for one test. Mirrors the live
        path's cached-context handling. Returns (rag_context, hop_evaluations,
        embedding_cost)."""
        if test_case.context_file and not force_rag:
            rag_context, hop_evaluations, _, _cached = load_rag_context(test_case.context_file)
            return rag_context, [], 0.0
        rag_context, hop_evaluations, _, embedding_cost = await self.orchestrator.retrieve_rag(
            query=test_case.query,
            query_id=query_id,
            max_chunks=RAG_MAX_CHUNKS,
            context_key="quality_test",
            use_multi_hop=RAG_MAX_HOPS > 0,
        )
        return rag_context, hop_evaluations, embedding_cost

    async def submit_batch_run(
        self,
        report_dir: Path,
        test_id: str | None,
        models: list[str],
        runs: int,
        judge_model: str,
        force_rag: bool = False,
    ) -> "BatchManifest":
        """Build generation requests, submit batchable ones, run non-batch models
        live now, and persist batch_state.json (phase=generation_submitted)."""
        from uuid import uuid4

        from tests.quality.batch.backends import batch_group_key, resolve_backend
        from tests.quality.batch.manifest import BatchManifest

        test_cases = self.load_test_cases(test_id)
        if not test_cases:
            raise ValueError(f"No test cases found for test_id: {test_id}")
        models_to_run = models or [self.config.default_llm_provider]

        gen_config = GenerationConfig(timeout_seconds=LLM_GENERATION_TIMEOUT)
        self._save_prompt(report_dir / "prompt.md", gen_config.system_prompt)

        backend_lines: dict[str, list] = {}
        backends_by_name: dict[str, object] = {}
        live_tasks = []
        requests_meta: list[dict] = []
        live_done: list[str] = []
        # Retrieval context is shared by every model of a (test, run); persist it
        # once here (keyed by test+run) so collect can recompute the deterministic
        # quote metrics hours later without bloating the state file per-request.
        contexts: dict[str, dict] = {}

        for run_num in range(1, runs + 1):
            for test_case in test_cases:
                query_id = uuid4()
                rag_context, hop_evaluations, embedding_cost = await self._retrieve_rag_for_test(
                    test_case, query_id, force_rag
                )
                multi_hop_cost = sum(h.cost_usd for h in hop_evaluations) if hop_evaluations else 0.0
                context_texts = [c.text for c in rag_context.document_chunks]
                chunk_ids = [str(c.chunk_id) for c in rag_context.document_chunks]
                contexts[f"{test_case.test_id}__run{run_num}"] = {
                    "context": context_texts,
                    "chunk_ids": chunk_ids,
                }

                for model in models_to_run:
                    custom_id = BatchManifest.make_custom_id("gen", test_case.test_id, model, run_num)
                    backend = resolve_backend(model)
                    # Group key, not bare backend name: OpenAI-compat backends need
                    # one batch per model (see batch_group_key). Every downstream
                    # lookup (manifest.generation, row["backend"], resubmit/retry)
                    # keys off this same value.
                    group_key = batch_group_key(backend, model) if backend else None
                    requests_meta.append({
                        "custom_id": custom_id,
                        "test_id": test_case.test_id,
                        "model": model,
                        "run_num": run_num,
                        "kind": "gen",
                        "backend": group_key,
                        "batchable": backend is not None,
                        "embedding_cost": embedding_cost,
                        "multi_hop_cost": multi_hop_cost,
                        "status": "pending",
                        "attempts": 0,
                    })
                    if backend is not None:
                        provider = LLMProviderFactory.create(model)
                        if provider is None:
                            raise ValueError(
                                f"Cannot build batch request for {model!r}: "
                                f"LLMProviderFactory.create returned None (missing API key). "
                                f"Set the required API key before submitting a batch run."
                            )
                        req = GenerationRequest(
                            prompt=test_case.query,
                            context=context_texts,
                            config=gen_config,
                            chunk_ids=chunk_ids,
                        )
                        line = provider.build_batch_request(req, custom_id)
                        # Gemini carries a sentence map for collect-time quote
                        # reconstruction; persist it on the request row.
                        if line.get("_gemini_sentences"):
                            requests_meta[-1]["gemini_sentences"] = line["_gemini_sentences"]
                        backend_lines.setdefault(group_key, []).append(line)
                        backends_by_name[group_key] = backend
                    else:
                        live_tasks.append(
                            self.run_test(
                                test_case, model, run_num, report_dir, rag_context,
                                hop_evaluations, embedding_cost, query_id,
                                defer_judge=True,
                            )
                        )
                        live_done.append(custom_id)

        if live_tasks:
            logger.info(f"Running {len(live_tasks)} non-batch model(s) live at submit...")
            # Tolerate individual live-run failures like _judge_parsed_outputs: a
            # single non-batch model raising must not abort the whole submit and
            # lose the batch work built above.
            live_results = await asyncio.gather(*live_tasks, return_exceptions=True)
            for cid, res in zip(live_done, live_results, strict=True):
                if isinstance(res, Exception):
                    logger.error(f"Live generation for {cid} failed at submit: {res}")

        # generation is shared by reference with manifest.generation below, so
        # each successful submit is persisted before the next backend is tried —
        # a later submit failure can't orphan an already-submitted (billed) batch.
        generation: dict[str, dict] = {}
        manifest = BatchManifest(
            phase="generation_submitted",
            created_at=datetime.now(UTC).isoformat(),
            models=models_to_run,
            judge_model=judge_model,
            runs=runs,
            test_ids=[tc.test_id for tc in test_cases],
            report_dir=str(report_dir),
            generation=generation,
            judge={},
            requests=requests_meta,
            live_done=live_done,
            contexts=contexts,
        )
        try:
            for name, lines in backend_lines.items():
                batch_id = backends_by_name[name].submit(lines)
                generation[name] = {
                    "batch_id": batch_id,
                    "status": "in_progress",
                    "attempts": 0,
                    "collected": False,
                }
        finally:
            manifest.save()
        return manifest

    def _rebuild_gen_lines_for_backend(
        self, manifest, backend_name: str, custom_ids: set[str] | None = None
    ) -> list[dict]:
        """Rebuild generation batch lines for one backend from persisted manifest
        state (used to resubmit an expired batch, or just the failed_retryable
        items when custom_ids is given). RAG context is persisted in
        manifest.contexts, so lines are byte-for-byte what submit_batch_run built."""
        gen_config = GenerationConfig(timeout_seconds=LLM_GENERATION_TIMEOUT)
        lines: list[dict] = []
        for row in manifest.requests:
            if row["kind"] != "gen" or row.get("backend") != backend_name:
                continue
            if row["custom_id"] in manifest.live_done:
                continue
            if custom_ids is not None and row["custom_id"] not in custom_ids:
                continue
            ctx = manifest.contexts[f"{row['test_id']}__run{row['run_num']}"]
            query = self.load_test_cases(row["test_id"])[0].query
            provider = LLMProviderFactory.create(row["model"])
            req = GenerationRequest(
                prompt=query,
                context=ctx["context"],
                config=gen_config,
                chunk_ids=ctx["chunk_ids"],
            )
            lines.append(provider.build_batch_request(req, row["custom_id"]))
        return lines

    async def collect_batch_run(self, report_dir: Path | str) -> str:
        """Single-pass advance of the batch state machine. Returns the new phase."""
        from tests.quality.batch.manifest import BatchManifest

        manifest = BatchManifest.load(report_dir)
        if manifest.phase == "generation_submitted":
            return await self._collect_generation(manifest)
        if manifest.phase == "judge_submitted":
            return await self._collect_judge(manifest)
        print("Batch run already complete (phase=done).")
        return manifest.phase

    async def _collect_generation(self, manifest) -> str:
        from src.lib.constants import QUALITY_TEST_MAX_BATCH_ITEM_RETRIES
        from tests.quality.batch.backends import make_backend, resolve_backend
        from tests.quality.batch.errors import classify_batch_error
        from tests.quality.output_parser import parse_output_directory

        report_dir = Path(manifest.report_dir)
        gen_backends = {name: make_backend(name) for name in manifest.generation}
        gen_meta = {
            r["custom_id"]: r
            for r in manifest.requests
            if r["kind"] == "gen" and r["batchable"]
        }

        # Advance each generation backend independently. A backend is "collected"
        # once all its rows are terminal (succeeded / failed_permanent); collected
        # backends are skipped so they aren't re-polled/re-fetched while another
        # backend is still retrying its items.
        all_collected = True
        for name, info in manifest.generation.items():
            if info.get("collected"):
                continue
            status = gen_backends[name].poll(info["batch_id"])
            info["status"] = status

            if status == "in_progress":
                all_collected = False
                continue

            if status == "expired":
                # Whole batch expired before completing — resubmit its still-unfetched
                # requests (deterministic: RAG context is persisted) and keep waiting.
                lines = self._rebuild_gen_lines_for_backend(manifest, name)
                new_id = gen_backends[name].submit(lines)
                info.update({"batch_id": new_id, "status": "in_progress"})
                print(f"Generation batch {name} expired — resubmitted as {new_id}.")
                all_collected = False
                continue

            if status == "failed":
                # Whole-batch failure: resubmit once (transient), then salvage the
                # succeeded items and mark the rest permanent instead of aborting.
                if info.get("attempts", 0) < 1:
                    lines = self._rebuild_gen_lines_for_backend(manifest, name)
                    try:
                        new_id = gen_backends[name].submit(lines)
                        info.update({
                            "batch_id": new_id,
                            "status": "in_progress",
                            "attempts": info.get("attempts", 0) + 1,
                        })
                        print(f"Generation batch {name} failed — resubmitted as {new_id}.")
                    except Exception as e:
                        logger.error(f"Resubmit of failed batch {name} raised: {e}")
                    all_collected = False
                    continue
                for row in manifest.requests:
                    if (
                        row.get("kind") == "gen"
                        and row.get("backend") == name
                        and row.get("status") in (None, "pending", "failed_retryable")
                    ):
                        row["status"] = "failed_permanent"
                        row.setdefault("error", f"backend batch {name} failed")
                        row["error_class"] = "permanent"
                info["collected"] = True
                print(f"Generation batch {name} failed twice — salvaging succeeded items.")
                continue

            # status == "ended": fetch + write each item, classifying failures.
            for cid, item in gen_backends[name].fetch(info["batch_id"]).items():
                row = gen_meta.get(cid)
                if row is None or row.get("status") in ("succeeded", "failed_permanent"):
                    continue
                outcome, error_text = self._write_batch_generation_output(
                    report_dir, row, item, manifest.contexts
                )
                if outcome == "succeeded":
                    row["status"] = "succeeded"
                    continue
                error_class, _reason = classify_batch_error(error_text)
                row["error"] = error_text
                row["error_class"] = error_class
                if (
                    error_class == "transient"
                    and row.get("attempts", 0) < QUALITY_TEST_MAX_BATCH_ITEM_RETRIES
                ):
                    row["status"] = "failed_retryable"
                else:
                    row["status"] = "failed_permanent"

            # Re-request this backend's still-retryable items as a fresh small batch.
            retry_ids = manifest.retryable_custom_ids("gen", name)
            if retry_ids:
                lines = self._rebuild_gen_lines_for_backend(manifest, name, custom_ids=retry_ids)
                new_id = gen_backends[name].submit(lines)
                for row in manifest.requests:
                    if row["custom_id"] in retry_ids:
                        row["attempts"] = row.get("attempts", 0) + 1
                        row["status"] = "pending"  # back in flight
                info.update({"batch_id": new_id, "status": "in_progress"})
                print(f"Re-requested {len(retry_ids)} failed gen item(s) on {name} as {new_id}.")
                all_collected = False
            else:
                info["collected"] = True

        manifest.save()
        if not all_collected:
            statuses = {n: i["status"] for n, i in manifest.generation.items()}
            print(f"Generation batches not ready: {statuses} — re-run batch-collect later.")
            return "generation_submitted"

        # Judge: batch if the judge model is batchable and produced any items,
        # else run live now.
        parsed = parse_output_directory(report_dir)
        test_cases_map = self._load_test_cases_for_outputs(parsed)
        judge_backend = resolve_backend(manifest.judge_model)
        if judge_backend is not None and self._submit_judge_batch(
            manifest, parsed, test_cases_map, judge_backend
        ):
            manifest.phase = "judge_submitted"
            manifest.save()
            print(f"Judge batch submitted ({judge_backend.name}) — re-run batch-collect later.")
            return "judge_submitted"

        results = await self._judge_parsed_outputs(parsed, test_cases_map)
        self._finalize_report(results, report_dir, manifest)
        manifest.phase = "done"
        manifest.save()
        print(f"Batch run complete: report at {report_dir}/report.md")
        return "done"

    def _write_batch_generation_output(
        self, report_dir: Path, meta: dict, item: dict, contexts: dict[str, dict]
    ) -> tuple[str, str | None]:
        """Parse a batch gen item into an LLMResponse and write output_*.md
        (no-eval style: metadata only, judging happens later).

        Returns an outcome for the caller's retry logic: ("succeeded", None) after
        the output file is written, or ("error", error_text) when the item could
        not be parsed (the caller classifies + decides whether to re-request)."""
        from tests.quality.batch.errors import extract_item_error
        from tests.quality.ragas_evaluator import RagasMetrics

        model = meta["model"]
        adapter_class = LLMProviderFactory._model_registry[model][0]
        try:
            llm_response = adapter_class.parse_batch_result(item)
        except Exception as e:
            error_text = extract_item_error(item) or f"{type(e).__name__}: {e}"
            logger.error(f"Batch gen item {meta['custom_id']} failed: {error_text}")
            return ("error", error_text)
        if not llm_response.model_version:
            llm_response.model_version = LLMProviderFactory._model_registry[model][1]

        # Gemini quote reconstruction: parse_batch_result returns GeminiAnswer JSON
        # with sentence_numbers and empty quote_text; fill it here using the sentence
        # map persisted at submit + the retrieval context (mirrors generate()).
        if llm_response.provider == "gemini" and meta.get("gemini_sentences"):
            import json as _json

            from src.services.llm.gemini_quote_extractor import post_process_gemini_response

            ctx = contexts.get(f"{meta['test_id']}__run{meta['run_num']}", {})
            try:
                answer_dict = _json.loads(llm_response.answer_text)
                answer_dict = post_process_gemini_response(
                    answer_dict,
                    ctx.get("context", []),
                    ctx.get("chunk_ids", []),
                    meta["gemini_sentences"],
                )
                llm_response.answer_text = _json.dumps(answer_dict)
                llm_response.structured_output = answer_dict
            except Exception as e:
                logger.error(f"Failed to post-process Gemini response for {meta['custom_id']}: {e}")

        breakdown = calculate_llm_cost(
            prompt_tokens=llm_response.prompt_tokens,
            completion_tokens=llm_response.completion_tokens,
            model=llm_response.model_version,
            cache_read_tokens=llm_response.cache_read_tokens,
            cache_creation_tokens=llm_response.cache_creation_tokens,
            batch=True,
            batch_backend=meta.get("backend"),
        )
        try:
            structured = StructuredLLMResponse.from_json(llm_response.answer_text)
            markdown = structured.to_markdown()
        except Exception:
            structured = None
            markdown = llm_response.answer_text

        test_case = self.load_test_cases(meta["test_id"])[0]
        # Recompute the deterministic quote metrics now (from the persisted
        # retrieval context) so they land in this output's metadata; scoring
        # later reads them from there rather than an empty RagasMetrics().
        if structured is not None:
            ctx = contexts.get(f"{meta['test_id']}__run{meta['run_num']}", {})
            ragas_metrics = self.ragas_evaluator.compute_deterministic_metrics(
                llm_response=structured,
                context_texts=ctx.get("context", []),
                chunk_ids=ctx.get("chunk_ids", []),
                ground_truth_contexts=test_case.ground_truth_contexts,
            )
        else:
            ragas_metrics = RagasMetrics()
        output_filename = report_dir / f"output_{meta['test_id']}_{model}_{meta['run_num']}.md"
        self._save_output(
            output_filename,
            test_case.query,
            markdown,
            ragas_metrics=ragas_metrics,
            test_id=meta["test_id"],
            model=model,
            run_num=meta["run_num"],
            llm_response=llm_response,
            cost_usd=breakdown.total_cost,
            multi_hop_cost_usd=meta.get("multi_hop_cost", 0.0),
            embedding_cost_usd=meta.get("embedding_cost", 0.0),
            generation_time_seconds=0.0,
            batch=True,
            batch_savings_usd=breakdown.batch_savings,
            cache_savings_usd=breakdown.cache_savings,
        )
        return ("succeeded", None)

    def _build_judge_lines(
        self, parsed, test_cases_map, provider, judge, custom_ids=None
    ) -> tuple[list[dict], list[dict]]:
        """Build judge batch request lines from parsed generation outputs.

        Returns (lines, rows): request lines to submit, and the matching manifest
        request rows (kind="judge"). When custom_ids is given, only those judge
        items are (re)built — used both for the initial submit and for resubmitting
        just the failed_retryable items."""
        from tests.quality.batch.manifest import BatchManifest

        lines: list[dict] = []
        rows: list[dict] = []
        for po in parsed:
            meta = po.metadata
            test_id = meta.test_metadata["test_id"]
            if test_id not in test_cases_map:
                continue
            test_case = test_cases_map[test_id]
            cid = BatchManifest.make_custom_id(
                "judge", test_id, meta.test_metadata["model"], meta.test_metadata["run_num"]
            )
            if custom_ids is not None and cid not in custom_ids:
                continue
            try:
                dm = MetadataGenerator.extract_deterministic_metrics_from_metadata(meta)
                structured = StructuredLLMResponse.from_json(po.llm_response.answer_text)
                gen_req = judge.build_judge_request(
                    query=po.query,
                    llm_response_text=structured.to_json(),
                    llm_quotes_structured=dm["llm_quotes_structured"],
                    ground_truth_answers=test_case.ground_truth_answers,
                    ground_truth_contexts=[c.text for c in test_case.ground_truth_contexts],
                )
                request_line = provider.build_batch_request(gen_req, cid)
            except Exception as e:
                logger.error(f"Judge batch item for {test_id} failed to build: {e} — skipping")
                continue
            lines.append(request_line)
            rows.append({
                "custom_id": cid,
                "test_id": test_id,
                "model": meta.test_metadata["model"],
                "run_num": meta.test_metadata["run_num"],
                "kind": "judge",
                "backend": None,
                "batchable": True,
                "status": "pending",
                "attempts": 0,
            })
        return lines, rows

    def _submit_judge_batch(self, manifest, parsed, test_cases_map, judge_backend) -> bool:
        """Build + submit a judge batch for all parsed outputs (batchable judge).

        Persists one kind="judge" row per item in manifest.requests so the judge
        phase can track and re-request failed items individually. Returns True if a
        batch was submitted, False if there was nothing to submit (no judge provider
        / every item failed to build) so the caller can fall back to the live judge.
        """
        from tests.quality.custom_judge import CustomJudge

        judge = CustomJudge(model=manifest.judge_model)
        provider = LLMProviderFactory.create(manifest.judge_model)
        if provider is None:
            logger.error(
                f"Judge provider {manifest.judge_model!r} unavailable (missing API key) "
                f"— falling back to live judge."
            )
            return False
        lines, rows = self._build_judge_lines(parsed, test_cases_map, provider, judge)
        if not lines:
            logger.error("No judge batch items built — falling back to live judge.")
            return False
        for row in rows:
            row["backend"] = judge_backend.name
            manifest.requests.append(row)
        batch_id = judge_backend.submit(lines)
        manifest.judge[judge_backend.name] = {
            "batch_id": batch_id,
            "status": "in_progress",
            "attempts": 0,
            "collected": False,
        }
        return True

    def _resubmit_judge(self, manifest, backend_name: str, custom_ids: set[str]) -> str:
        """Rebuild judge lines for the given custom_ids and submit as a new batch."""
        from tests.quality.batch.backends import make_backend
        from tests.quality.custom_judge import CustomJudge
        from tests.quality.output_parser import parse_output_directory

        report_dir = Path(manifest.report_dir)
        parsed = parse_output_directory(report_dir)
        test_cases_map = self._load_test_cases_for_outputs(parsed)
        judge = CustomJudge(model=manifest.judge_model)
        provider = LLMProviderFactory.create(manifest.judge_model)
        lines, _rows = self._build_judge_lines(
            parsed, test_cases_map, provider, judge, custom_ids=custom_ids
        )
        return make_backend(backend_name).submit(lines)

    def _score_judge_item(
        self, manifest, backend_name, row, item, test_case, judge, judge_adapter
    ) -> None:
        """Parse + score one judge batch item, persisting the outcome on its row.

        On success stores the judge metrics/cost on the row (status=succeeded); on
        failure classifies transient vs permanent and marks the row failed_retryable
        (if under the retry cap) or failed_permanent."""
        from src.lib.constants import QUALITY_TEST_MAX_BATCH_ITEM_RETRIES
        from tests.quality.batch.errors import classify_batch_error, extract_item_error

        try:
            judge_response = judge_adapter.parse_batch_result(item)
            jr = judge.parse_result(judge_response, test_case.ground_truth_answers)
            jb = calculate_llm_cost(
                prompt_tokens=jr.prompt_tokens,
                completion_tokens=jr.completion_tokens,
                model=manifest.judge_model,
                cache_read_tokens=jr.cache_read_tokens,
                cache_creation_tokens=jr.cache_creation_tokens,
                batch=True,
                batch_backend=backend_name,
            )
            row["judge_metrics"] = {
                "explanation_faithfulness": jr.explanation_faithfulness,
                "answer_correctness": jr.answer_correctness,
                "answer_correctness_details": jr.answer_correctness_details,
                "feedback": jr.feedback,
            }
            row["judge_cost"] = jb.total_cost
            row["judge_batch_savings"] = jb.batch_savings
            row["status"] = "succeeded"
            row.pop("error", None)
            row.pop("error_class", None)
        except Exception as e:
            error_text = extract_item_error(item) or f"{type(e).__name__}: {e}"
            error_class, _reason = classify_batch_error(error_text)
            row["error"] = error_text
            row["error_class"] = error_class
            if (
                error_class == "transient"
                and row.get("attempts", 0) < QUALITY_TEST_MAX_BATCH_ITEM_RETRIES
            ):
                row["status"] = "failed_retryable"
            else:
                row["status"] = "failed_permanent"

    async def _collect_judge(self, manifest) -> str:
        from tests.quality.batch.backends import make_backend
        from tests.quality.batch.manifest import BatchManifest
        from tests.quality.custom_judge import CustomJudge
        from tests.quality.output_parser import parse_output_directory

        report_dir = Path(manifest.report_dir)
        name, info = next(iter(manifest.judge.items()))
        backend = make_backend(name)
        status = backend.poll(info["batch_id"])
        info["status"] = status
        judge_rows = {r["custom_id"]: r for r in manifest.requests if r.get("kind") == "judge"}

        def _pending_judge_ids() -> set[str]:
            return {
                cid
                for cid, r in judge_rows.items()
                if r.get("status") in (None, "pending", "failed_retryable")
            }

        if status == "in_progress":
            manifest.save()
            print(f"Judge batch not ready ({status}) — re-run batch-collect later.")
            return "judge_submitted"

        if status == "expired":
            pending = _pending_judge_ids()
            new_id = self._resubmit_judge(manifest, name, pending)
            info.update({"batch_id": new_id, "status": "in_progress"})
            manifest.save()
            print(f"Judge batch {name} expired — resubmitted {len(pending)} item(s) as {new_id}.")
            return "judge_submitted"

        if status == "failed":
            # Resubmit once (transient), then mark remaining items permanent and
            # score the succeeded ones instead of aborting the whole run.
            if info.get("attempts", 0) < 1:
                pending = _pending_judge_ids()
                try:
                    new_id = self._resubmit_judge(manifest, name, pending)
                    info.update({
                        "batch_id": new_id,
                        "status": "in_progress",
                        "attempts": info.get("attempts", 0) + 1,
                    })
                    print(f"Judge batch {name} failed — resubmitted as {new_id}.")
                except Exception as e:
                    logger.error(f"Resubmit of failed judge batch {name} raised: {e}")
                manifest.save()
                return "judge_submitted"
            for r in judge_rows.values():
                if r.get("status") in (None, "pending", "failed_retryable"):
                    r["status"] = "failed_permanent"
                    r.setdefault("error", f"judge backend {name} failed")
                    r["error_class"] = "permanent"
            print(f"Judge batch {name} failed twice — scoring succeeded items.")
        else:
            # status == "ended": fetch + score each item, classifying failures.
            judge_items = backend.fetch(info["batch_id"])
            judge = CustomJudge(model=manifest.judge_model)
            judge_adapter = LLMProviderFactory._model_registry[manifest.judge_model][0]
            parsed = parse_output_directory(report_dir)
            test_cases_map = self._load_test_cases_for_outputs(parsed)
            cid_to_test_case: dict[str, object] = {}
            for po in parsed:
                meta = po.metadata
                tid = meta.test_metadata["test_id"]
                if tid not in test_cases_map:
                    continue
                jcid = BatchManifest.make_custom_id(
                    "judge", tid, meta.test_metadata["model"], meta.test_metadata["run_num"]
                )
                cid_to_test_case[jcid] = test_cases_map[tid]

            for cid, item in judge_items.items():
                row = judge_rows.get(cid)
                if row is None or row.get("status") in ("succeeded", "failed_permanent"):
                    continue
                test_case = cid_to_test_case.get(cid)
                if test_case is None:
                    row["status"] = "failed_permanent"
                    row["error"] = "no matching generation output"
                    row["error_class"] = "permanent"
                    continue
                self._score_judge_item(manifest, name, row, item, test_case, judge, judge_adapter)

            retry_ids = {
                cid for cid, r in judge_rows.items() if r.get("status") == "failed_retryable"
            }
            if retry_ids:
                new_id = self._resubmit_judge(manifest, name, retry_ids)
                for cid in retry_ids:
                    judge_rows[cid]["attempts"] = judge_rows[cid].get("attempts", 0) + 1
                    judge_rows[cid]["status"] = "pending"
                info.update({"batch_id": new_id, "status": "in_progress"})
                manifest.save()
                print(f"Re-requested {len(retry_ids)} failed judge item(s) on {name} as {new_id}.")
                return "judge_submitted"

        # All judge rows terminal — assemble results from persisted rows + finalize.
        info["collected"] = True
        results = self._score_from_judge_batch(manifest)
        self._finalize_report(results, report_dir, manifest)
        manifest.phase = "done"
        manifest.save()
        print(f"Batch run complete: report at {report_dir}/report.md")
        return "done"

    def _score_from_judge_batch(self, manifest) -> list[IndividualTestResult]:
        """Assemble results from persisted judge rows + saved generation metadata.

        Judge scoring happens incrementally in _score_judge_item (persisted per row
        so successes survive across the retry passes); here we only combine each
        row's stored judge metrics with its generation metadata. A row that never
        succeeded is scored with its recorded error (grey bar)."""
        from tests.quality.batch.manifest import BatchManifest
        from tests.quality.output_parser import parse_output_directory
        from tests.quality.ragas_evaluator import RagasMetrics

        report_dir = Path(manifest.report_dir)
        parsed = parse_output_directory(report_dir)
        test_cases_map = self._load_test_cases_for_outputs(parsed)
        judge_rows = {r["custom_id"]: r for r in manifest.requests if r.get("kind") == "judge"}

        results = []
        for po in parsed:
            meta = po.metadata
            test_id = meta.test_metadata["test_id"]
            if test_id not in test_cases_map:
                continue
            test_case = test_cases_map[test_id]
            cid = BatchManifest.make_custom_id(
                "judge", test_id, meta.test_metadata["model"], meta.test_metadata["run_num"]
            )
            dm = MetadataGenerator.extract_deterministic_metrics_from_metadata(meta)
            row = judge_rows.get(cid)
            judge_cost = 0.0
            judge_batch_savings = 0.0
            if row and row.get("judge_metrics"):
                dm.update(row["judge_metrics"])
                metrics = RagasMetrics(**dm)
                judge_cost = row.get("judge_cost", 0.0)
                judge_batch_savings = row.get("judge_batch_savings", 0.0)
            else:
                err = (row or {}).get("error") or "judge item missing"
                metrics = RagasMetrics(**dm, error=f"Judge error: {err}")

            score = self.ragas_evaluator.calculate_aggregate_score(metrics)
            results.append(IndividualTestResult(
                test_id=test_id,
                query=po.query,
                model=meta.test_metadata["model"],
                run_num=meta.test_metadata["run_num"],
                score=int(score),
                max_score=test_case.max_score,
                passed=score >= 80.0,
                tokens=meta.tokens["total"],
                cost_usd=meta.costs["llm_generation_usd"],
                multi_hop_cost_usd=meta.costs["multi_hop_usd"],
                embedding_cost_usd=meta.costs["embedding_usd"],
                ragas_cost_usd=judge_cost,
                output_char_count=0,
                generation_time_seconds=meta.latency["llm_generation_seconds"],
                output_filename=str(po.file_path),
                error=None,
                json_formatted=True,
                quote_precision=metrics.quote_precision,
                quote_recall=metrics.quote_recall,
                quote_faithfulness=metrics.quote_faithfulness,
                explanation_faithfulness=metrics.explanation_faithfulness,
                answer_correctness=metrics.answer_correctness,
                ragas_error=metrics.error,
                feedback=metrics.feedback,
                ragas_evaluation_error=metrics.error is not None,
                answer_correctness_details=metrics.answer_correctness_details,
                llm_quotes_structured=metrics.llm_quotes_structured,
                batch_savings_usd=getattr(meta, "batch_savings_usd", 0.0),
                cache_savings_usd=getattr(meta, "cache_savings_usd", 0.0),
                judge_batch_savings_usd=judge_batch_savings,
            ))
        return results

    def _synthesize_error_result_from_row(
        self, row: dict, error: str, error_class: str
    ) -> IndividualTestResult:
        """Build a score-0 error result for a batch gen row that produced no output.

        Permanently-failed generation items write no output_*.md, so the judge
        paths never see them — this makes them appear in the report + grey bar
        instead of silently vanishing (the pre-change behavior)."""
        test_case = self.load_test_cases(row["test_id"])[0]
        return IndividualTestResult(
            test_id=row["test_id"],
            query=test_case.query,
            model=row["model"],
            run_num=row.get("run_num"),
            score=0,
            max_score=test_case.max_score,
            passed=False,
            tokens=0,
            cost_usd=0.0,
            multi_hop_cost_usd=row.get("multi_hop_cost", 0.0),
            embedding_cost_usd=row.get("embedding_cost", 0.0),
            ragas_cost_usd=0.0,
            output_char_count=0,
            generation_time_seconds=0.0,
            output_filename="",
            error=error,
            error_class=error_class,
        )

    def _enrich_and_synthesize_results(self, results, manifest) -> list[IndividualTestResult]:
        """Tag results with batch recovery info and add synthesized error rows.

        Single choke point (called by _finalize_report for both the live-judge and
        batch-judge finalize paths, before aggregation). Matches each result to its
        gen/judge manifest rows via the deterministic custom_id, marks
        recovered_from_error / recovery_attempts / error_class, and appends a
        score-0 result for every failed_permanent gen row that produced no output."""
        from tests.quality.batch.manifest import BatchManifest

        gen_rows = {r["custom_id"]: r for r in manifest.requests if r.get("kind") == "gen"}
        judge_rows = {r["custom_id"]: r for r in manifest.requests if r.get("kind") == "judge"}

        matched_gen_cids: set[str] = set()
        for res in results:
            if res.run_num is None:
                continue
            gen_cid = BatchManifest.make_custom_id("gen", res.test_id, res.model, res.run_num)
            judge_cid = BatchManifest.make_custom_id("judge", res.test_id, res.model, res.run_num)
            matched_gen_cids.add(gen_cid)
            gen_row = gen_rows.get(gen_cid)
            judge_row = judge_rows.get(judge_cid)

            recovered = False
            attempts = 0
            if gen_row and BatchManifest.is_recovered(gen_row):
                recovered = True
                attempts = max(attempts, gen_row.get("attempts", 0))
            if judge_row and BatchManifest.is_recovered(judge_row):
                recovered = True
                attempts = max(attempts, judge_row.get("attempts", 0))
            res.recovered_from_error = recovered
            res.recovery_attempts = attempts

            if res.error or res.ragas_evaluation_error:
                if judge_row and judge_row.get("error_class"):
                    res.error_class = judge_row["error_class"]
                elif gen_row and gen_row.get("error_class"):
                    res.error_class = gen_row["error_class"]

        synthesized = [
            self._synthesize_error_result_from_row(
                row,
                row.get("error") or "generation failed",
                row.get("error_class") or "permanent",
            )
            for cid, row in gen_rows.items()
            if row.get("status") == "failed_permanent" and cid not in matched_gen_cids
        ]
        return results + synthesized

    def _finalize_report(self, results, report_dir: Path, manifest) -> None:
        """Aggregate results and generate the report into report_dir."""
        from tests.quality.reporting.aggregator import aggregate_results
        from tests.quality.reporting.report_generator import ReportGenerator
        from tests.quality.reporting.report_models import QualityReport

        # Tag recovery info + add synthesized error rows BEFORE aggregation so the
        # averages, chart, and error log all include permanently-failed runs.
        results = self._enrich_and_synthesize_results(results, manifest)
        total_cost = sum(r.total_cost_usd for r in results)
        report = QualityReport(
            results=results,
            total_time_seconds=0.0,
            total_cost_usd=total_cost,
            runs=manifest.runs,
            models=manifest.models,
            test_cases=manifest.test_ids,
            report_dir=str(report_dir),
            judge_model=manifest.judge_model,
            prompt_path=str(report_dir / "prompt.md"),
        )
        aggregate_results(report)
        ReportGenerator(report).generate_all_reports()

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

        # 5. Evaluate parsed outputs with the live judge (shared with batch-collect).
        valid_results = await self._judge_parsed_outputs(parsed_outputs, test_cases_map)

        logger.info(f"✅ Replay complete: {len(valid_results)}/{len(parsed_outputs)} successful")
        logger.info(f"Results saved to: {new_results_dir}")

        return valid_results, new_results_dir

    async def _judge_parsed_outputs(
        self, parsed_outputs: list, test_cases_map: dict[str, TestCase]
    ) -> list[IndividualTestResult]:
        """Run the live judge over parsed outputs, in parallel with a semaphore.

        Shared by replay_tests_from_outputs and the batch-collect scoring step so
        the live-judge path is identical in both. Skips outputs whose test case is
        not in the suite; drops (and logs) any evaluation that raised.
        """
        tasks = []
        for po in parsed_outputs:
            test_id = po.metadata.test_metadata["test_id"]
            if test_id not in test_cases_map:
                logger.warning(
                    f"Test case '{test_id}' not found in test suite, skipping {po.file_path.name}"
                )
                continue
            tasks.append(self._evaluate_parsed_output(po, test_cases_map[test_id]))

        logger.info(f"Evaluating {len(tasks)} outputs with judge...")
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Evaluation failed for output {i}: {result}")
            else:
                valid_results.append(result)
        return valid_results

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
        judge_cache_savings = 0.0

        if QUALITY_TEST_JUDGING == "OFF":
            # No judge - use deterministic metrics only
            ragas_metrics = RagasMetrics(**deterministic_metrics)

        elif QUALITY_TEST_JUDGING == "CUSTOM":
            # Run custom judge (single LLM call) with semaphore
            from tests.quality.custom_judge import CustomJudge

            judge = CustomJudge(model=self.judge_model)

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

                    # Calculate judge cost from actual tokens, including prompt-cache
                    # tokens so cached judge calls are costed and credited correctly.
                    judge_breakdown = calculate_llm_cost(
                        prompt_tokens=judge_result.prompt_tokens,
                        completion_tokens=judge_result.completion_tokens,
                        model=self.judge_model,
                        cache_read_tokens=judge_result.cache_read_tokens,
                        cache_creation_tokens=judge_result.cache_creation_tokens,
                    )
                    judge_cost = judge_breakdown.total_cost
                    judge_cache_savings = judge_breakdown.cache_savings

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
                    judge_cache_savings = ragas_result.cache_savings_usd

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
            run_num=metadata.test_metadata.get("run_num"),
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
            judge_cache_savings_usd=judge_cache_savings,
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
            # Generation-time savings attributed at submit, carried through metadata.
            batch_savings_usd=getattr(metadata, "batch_savings_usd", 0.0),
            cache_savings_usd=getattr(metadata, "cache_savings_usd", 0.0),
        )

    def _create_error_result(
        self, metadata: "OutputMetadata", test_case: TestCase, error_msg: str
    ) -> IndividualTestResult:
        """Create an error result when evaluation fails."""
        return IndividualTestResult(
            test_id=metadata.test_metadata["test_id"],
            query=test_case.query,
            model=metadata.test_metadata["model"],
            run_num=metadata.test_metadata.get("run_num"),
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
            batch_savings_usd=getattr(metadata, "batch_savings_usd", 0.0),
            cache_savings_usd=getattr(metadata, "cache_savings_usd", 0.0),
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
        batch: bool = False,
        batch_savings_usd: float = 0.0,
        cache_savings_usd: float = 0.0,
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
                run_num=run_num,
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
                batch_savings_usd=batch_savings_usd,
                cache_savings_usd=cache_savings_usd,
            )

            metadata = MetadataGenerator.generate_metadata(
                test_id=test_id,
                model=model,
                run_num=run_num,
                llm_response=llm_response,
                result=result,
                metrics=ragas_metrics,
                batch=batch,
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
