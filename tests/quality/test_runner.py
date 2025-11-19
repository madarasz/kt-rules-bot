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
    QUALITY_TEST_MAX_CONCURRENT_LLM_REQUESTS,
    RAG_MAX_CHUNKS,
)
from src.lib.logging import get_logger
from src.lib.tokens import estimate_cost, estimate_embedding_cost
from src.models.rag_request import RetrieveRequest
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
from src.services.rag.embeddings import EmbeddingService
from src.services.rag.retriever import RAGRetriever
from src.services.rag.vector_db import VectorDBService
from tests.quality.ragas_evaluator import RagasEvaluator
from tests.quality.reporting.report_models import IndividualTestResult
from tests.quality.test_case_models import TestCase

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
        # Semaphore to limit concurrent LLM requests (prevents rate limit errors)
        self.llm_semaphore = asyncio.Semaphore(QUALITY_TEST_MAX_CONCURRENT_LLM_REQUESTS)
        # Semaphore to serialize Ragas evaluations (Ragas is not thread-safe for parallel execution)
        self.ragas_semaphore = asyncio.Semaphore(1)

    def load_test_cases(self, test_id: str | None = None) -> list[TestCase]:
        """Load test cases from YAML files."""
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

                # Support both new format (ground_truth) and legacy format (requirements)
                test_cases.append(
                    TestCase(
                        test_id=data["test_id"],
                        query=data["query"],
                        ground_truth_answers=data.get("ground_truth_answers", []),
                        ground_truth_contexts=data.get("ground_truth_contexts", []),
                        requirements=data.get("requirements", None),
                    )
                )
                logger.info(f"Loaded test case: {data['test_id']}")
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
            no_eval: If True, skip Ragas evaluation (only generate outputs)
        """
        eval_mode = " (no-eval)" if no_eval else ""
        logger.info(
            f"Running test '{test_case.test_id}' with model '{model}' (Run #{run_num}){eval_mode}"
        )

        multi_hop_cost = 0.0
        embedding_cost = 0.0

        if rag_context is None:
            from uuid import uuid4

            rag_context, hop_evaluations_result, _ = self.rag_retriever.retrieve(
                RetrieveRequest(
                    query=test_case.query, context_key="quality_test", max_chunks=RAG_MAX_CHUNKS
                ),
                query_id=uuid4(),
            )
            hop_evaluations = hop_evaluations_result

            # Calculate embedding cost for the query
            embedding_cost = estimate_embedding_cost(test_case.query)

        # Calculate multi-hop evaluation costs if any
        if hop_evaluations:
            multi_hop_cost = sum(hop.cost_usd for hop in hop_evaluations)
            logger.debug(
                "multi_hop_costs_calculated",
                num_hops=len(hop_evaluations),
                total_cost=multi_hop_cost,
            )

        llm_provider = LLMProviderFactory.create(model)
        gen_config = GenerationConfig(timeout_seconds=LLM_GENERATION_TIMEOUT)
        output_filename = report_dir / f"output_{test_case.test_id}_{model}_{run_num}.md"

        error_str = None
        llm_response_text = ""
        token_count = 0
        json_formatted = False
        structured_quotes_count = 0
        structured_llm_response = None  # For Ragas evaluation
        generation_time = 0.0  # Initialize to 0 in case of early errors

        try:
            # Use semaphore to limit concurrent requests and prevent rate limits
            async with self.llm_semaphore:
                # Start timing right before LLM API call
                llm_start_time = datetime.now(UTC)
                llm_response = await retry_with_rate_limit_backoff(
                    llm_provider.generate,
                    GenerationRequest(
                        prompt=test_case.query,
                        context=[chunk.text for chunk in rag_context.document_chunks],
                        config=gen_config,
                    ),
                    timeout_seconds=LLM_GENERATION_TIMEOUT,
                )
                # Stop timing immediately after LLM response
                generation_time = (datetime.now(UTC) - llm_start_time).total_seconds()
            llm_response_text = llm_response.answer_text
            token_count = llm_response.token_count

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

        # Save markdown output for human reading
        self._save_output(output_filename, test_case.query, llm_response_markdown)

        # Evaluate with Ragas metrics (skip if no_eval is True)
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
                    context_chunks=[chunk.text for chunk in rag_context.document_chunks],
                    ground_truth_answers=test_case.ground_truth_answers,
                    ground_truth_contexts=test_case.ground_truth_contexts,
                )

            # Calculate aggregate score from Ragas metrics
            score = self.ragas_evaluator.calculate_aggregate_score(ragas_metrics)
            passed = score >= 80.0  # 80% threshold for passing

        # Check if any Ragas metrics failed (are None when they should have values)
        # This indicates a Ragas evaluation failure that should be tracked for grey bar visualization
        ragas_evaluation_error = False
        if not no_eval and structured_llm_response is not None:
            # Check if any of the LLM-based Ragas metrics failed
            # (quote_precision and quote_recall are locally calculated and should always succeed)
            if (
                ragas_metrics.quote_faithfulness is None
                or ragas_metrics.explanation_faithfulness is None
                or ragas_metrics.answer_correctness is None
            ):
                ragas_evaluation_error = True
                logger.error(
                    f"Ragas evaluation failed for test {test_case.test_id} on model {model} - "
                    f"some metrics returned None/NaN"
                )

        # Calculate main LLM cost
        cost = estimate_cost(
            prompt_tokens=int(token_count * 0.7),
            completion_tokens=int(token_count * 0.3),
            model=model,
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
            ragas_evaluation_error=ragas_evaluation_error,
            requirements=None,  # Legacy field, no longer used
        )

    async def run_tests_in_parallel(
        self,
        runs: int,
        report_dir: Path,
        test_id: str | None = None,
        models: list[str] | None = None,
        no_eval: bool = False,
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
                # RAG is done once per test case per run to ensure context is fresh
                from uuid import uuid4

                rag_context, hop_evaluations, _ = self.rag_retriever.retrieve(
                    RetrieveRequest(
                        query=test_case.query, context_key="quality_test", max_chunks=RAG_MAX_CHUNKS
                    ),
                    query_id=uuid4(),
                )
                for model in models_to_run:
                    tasks.append(
                        self.run_test(
                            test_case,
                            model,
                            run_num,
                            report_dir,
                            rag_context,
                            hop_evaluations,
                            no_eval,
                        )
                    )

        results = await asyncio.gather(*tasks)
        return results

    def _save_output(self, filename: Path, query: str, response: str):
        """Saves the query and response to a file."""
        content = f"# Query\n\n{query}\n\n---\n\n# Response\n\n{response}\n\n"
        os.makedirs(filename.parent, exist_ok=True)
        with open(filename, "w") as f:
            f.write(content)

    def _save_prompt(self, filename: Path, system_prompt: str):
        """Saves the current LLM prompt to a file."""
        content = f"# Current LLM System Prompt\n\n```\n{system_prompt}\n```\n"
        os.makedirs(filename.parent, exist_ok=True)
        with open(filename, "w") as f:
            f.write(content)
