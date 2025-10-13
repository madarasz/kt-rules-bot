"""Quality test runner for response quality testing.

Runs quality tests against the RAG + LLM pipeline.
"""

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
import yaml

from tests.quality.test_case_models import TestCase, TestRequirement
from tests.quality.evaluator import RequirementResult as EvaluatorRequirementResult
from tests.quality.reporting.report_models import (
    IndividualTestResult,
    RequirementResult as ReportRequirementResult,
)
from tests.quality.evaluator import RequirementEvaluator
from src.services.llm.factory import LLMProviderFactory
from src.services.rag.retriever import RAGRetriever, RetrieveRequest
from src.services.rag.vector_db import VectorDBService
from src.services.rag.embeddings import EmbeddingService
from src.services.llm.base import GenerationRequest, GenerationConfig, ContentFilterError
from src.services.llm.retry import retry_on_content_filter
from src.lib.constants import QUALITY_TEST_JUDGE_MODEL, RAG_MAX_CHUNKS, LLM_GENERATION_TIMEOUT
from src.lib.config import get_config
from src.lib.logging import get_logger
from src.lib.tokens import estimate_cost

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
        self.evaluator = RequirementEvaluator(judge_model=judge_model)
        self.config = get_config()
        self.vector_db = VectorDBService(collection_name="kill_team_rules")
        self.embedding_service = EmbeddingService()
        self.rag_retriever = RAGRetriever(
            vector_db_service=self.vector_db,
            embedding_service=self.embedding_service,
        )

    def load_test_cases(self, test_id: Optional[str] = None) -> List[TestCase]:
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
                with open(file, "r") as f:
                    data = yaml.safe_load(f)
                requirements = [
                    TestRequirement(**req) for req in data.get("requirements", [])
                ]
                test_cases.append(
                    TestCase(
                        test_id=data["test_id"],
                        query=data["query"],
                        requirements=requirements,
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
    ) -> IndividualTestResult:
        """Run a single test case."""
        logger.info(f"Running test '{test_case.test_id}' with model '{model}' (Run #{run_num})")
        start_time = datetime.now(timezone.utc)

        if rag_context is None:
            from uuid import uuid4
            rag_context = self.rag_retriever.retrieve(
                RetrieveRequest(
                    query=test_case.query,
                    context_key="quality_test",
                    max_chunks=RAG_MAX_CHUNKS,
                ),
                query_id=uuid4(),
            )

        llm_provider = LLMProviderFactory.create(model)
        gen_config = GenerationConfig(timeout_seconds=LLM_GENERATION_TIMEOUT)
        output_filename = report_dir / f"output_{test_case.test_id}_{model}_{run_num}.md"
        
        error_str = None
        llm_response_text = ""
        token_count = 0
        
        try:
            llm_response = await retry_on_content_filter(
                llm_provider.generate,
                GenerationRequest(
                    prompt=test_case.query,
                    context=[chunk.text for chunk in rag_context.document_chunks],
                    config=gen_config,
                ),
                timeout_seconds=LLM_GENERATION_TIMEOUT,
            )
            llm_response_text = llm_response.answer_text
            token_count = llm_response.token_count
        except (ContentFilterError, Exception) as e:
            logger.error(f"LLM generation failed for {test_case.test_id} on {model}: {e}")
            error_str = str(e)
            llm_response_text = f"[LLM Generation Failed: {error_str}]"

        generation_time = (datetime.now(timezone.utc) - start_time).total_seconds()
        
        # Save output
        self._save_output(output_filename, test_case.query, llm_response_text)

        eval_results: List[EvaluatorRequirementResult] = await self.evaluator.evaluate_all(
            test_case.requirements, llm_response_text
        )

        report_reqs = [
            ReportRequirementResult(
                title=res.requirement.check,
                type=res.requirement.type,
                achieved_score=res.points_earned,
                max_score=res.requirement.points,
                description=res.requirement.description,
                outcome=res.details,
            )
            for res in eval_results
        ]

        score = sum(r.achieved_score for r in report_reqs)
        cost = estimate_cost(
            prompt_tokens=int(token_count * 0.7),
            completion_tokens=int(token_count * 0.3),
            model=model,
        )

        return IndividualTestResult(
            test_id=test_case.test_id,
            query=test_case.query,
            model=model,
            score=score,
            max_score=test_case.max_score,
            passed=score == test_case.max_score,
            tokens=token_count,
            cost_usd=cost,
            output_char_count=len(llm_response_text),
            generation_time_seconds=generation_time,
            requirements=report_reqs,
            output_filename=str(output_filename),
            error=error_str,
        )

    async def run_tests_in_parallel(
        self,
        runs: int,
        report_dir: Path,
        test_id: Optional[str] = None,
        models: Optional[List[str]] = None,
    ) -> List[IndividualTestResult]:
        """Run all test combinations in parallel."""
        test_cases = self.load_test_cases(test_id)
        if not test_cases:
            raise ValueError(f"No test cases found for test_id: {test_id}" if test_id else "No test cases found.")

        models_to_run = models or [self.config.default_llm_provider]
        
        # Save the current prompt to prompt.md once
        gen_config = GenerationConfig(timeout_seconds=LLM_GENERATION_TIMEOUT)
        self._save_prompt(report_dir / "prompt.md", gen_config.system_prompt)
        
        tasks = []
        for run_num in range(1, runs + 1):
            for test_case in test_cases:
                # RAG is done once per test case per run to ensure context is fresh
                from uuid import uuid4
                rag_context = self.rag_retriever.retrieve(
                    RetrieveRequest(
                        query=test_case.query,
                        context_key="quality_test",
                        max_chunks=RAG_MAX_CHUNKS,
                    ),
                    query_id=uuid4(),
                )
                for model in models_to_run:
                    tasks.append(
                        self.run_test(
                            test_case, model, run_num, report_dir, rag_context
                        )
                    )
        
        results = await asyncio.gather(*tasks)
        return results

    def _save_output(self, filename: Path, query: str, response: str):
        """Saves the query and response to a file."""
        content = (
            f"# Query\n\n{query}\n\n"
            f"---\n\n"
            f"# Response\n\n{response}\n\n"
        )
        os.makedirs(filename.parent, exist_ok=True)
        with open(filename, "w") as f:
            f.write(content)

    def _save_prompt(self, filename: Path, system_prompt: str):
        """Saves the current LLM prompt to a file."""
        content = f"# Current LLM System Prompt\n\n```\n{system_prompt}\n```\n"
        os.makedirs(filename.parent, exist_ok=True)
        with open(filename, "w") as f:
            f.write(content)
