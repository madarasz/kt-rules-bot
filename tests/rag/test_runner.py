"""RAG test runner - executes RAG retrieval tests.

Loads test cases, runs retrieval, evaluates metrics, generates reports.
"""

from pathlib import Path
from typing import List, Optional
from uuid import uuid4
import time

from tests.rag.test_case_models import RAGTestCase, RAGTestResult, RAGTestSummary
from tests.rag.evaluator import RAGEvaluator
from src.services.rag.retriever import RAGRetriever, RetrieveRequest
from src.lib.constants import RAG_MAX_CHUNKS, RAG_MIN_RELEVANCE, EMBEDDING_MODEL
from src.lib.tokens import estimate_embedding_cost
from src.lib.logging import get_logger

logger = get_logger(__name__)


class RAGTestRunner:
    """Runs RAG retrieval tests and generates reports."""

    def __init__(
        self,
        test_cases_dir: Path = Path("tests/rag/test_cases"),
        results_dir: Path = Path("tests/rag/results"),
    ):
        """Initialize test runner.

        Args:
            test_cases_dir: Directory containing YAML test cases
            results_dir: Directory for test results
        """
        self.test_cases_dir = test_cases_dir
        self.results_dir = results_dir
        self.evaluator = RAGEvaluator()
        self.retriever = RAGRetriever()

        logger.info(
            "rag_test_runner_initialized",
            test_cases_dir=str(test_cases_dir),
            results_dir=str(results_dir),
        )

    def load_test_cases(self, test_id: Optional[str] = None) -> List[RAGTestCase]:
        """Load test cases from YAML files.

        Args:
            test_id: Optional specific test ID to load (otherwise load all)

        Returns:
            List of RAGTestCase objects
        """
        if not self.test_cases_dir.exists():
            raise FileNotFoundError(f"Test cases directory not found: {self.test_cases_dir}")

        test_cases = []
        yaml_files = list(self.test_cases_dir.glob("*.yaml")) + list(
            self.test_cases_dir.glob("*.yml")
        )

        if not yaml_files:
            raise ValueError(f"No YAML test case files found in {self.test_cases_dir}")

        for yaml_file in yaml_files:
            test_case = RAGTestCase.from_yaml(yaml_file)

            # Filter by test_id if specified
            if test_id and test_case.test_id != test_id:
                continue

            test_cases.append(test_case)
            logger.debug("test_case_loaded", test_id=test_case.test_id, file=yaml_file.name)

        if test_id and not test_cases:
            raise ValueError(f"Test case not found: {test_id}")

        logger.info("test_cases_loaded", count=len(test_cases))
        return test_cases

    def run_test(
        self,
        test_case: RAGTestCase,
        max_chunks: int = RAG_MAX_CHUNKS,
        min_relevance: float = RAG_MIN_RELEVANCE,
        run_number: int = 1,
    ) -> RAGTestResult:
        """Run a single test case.

        Args:
            test_case: Test case to run
            max_chunks: Maximum chunks to retrieve
            min_relevance: Minimum relevance threshold
            run_number: Run number (for multi-run tests)

        Returns:
            RAGTestResult
        """
        logger.info(
            "running_rag_test",
            test_id=test_case.test_id,
            run=run_number,
            max_chunks=max_chunks,
            min_relevance=min_relevance,
        )

        # Create retrieval request
        query_id = uuid4()
        request = RetrieveRequest(
            query=test_case.query,
            context_key="rag-test",
            max_chunks=max_chunks,
            min_relevance=min_relevance,
            use_hybrid=True,
        )

        # Calculate embedding cost
        embedding_cost = estimate_embedding_cost(test_case.query, model=EMBEDDING_MODEL)

        # Retrieve chunks
        start_time = time.time()
        rag_context = self.retriever.retrieve(request, query_id)
        retrieval_time = time.time() - start_time

        # Evaluate
        result = self.evaluator.evaluate(
            test_case=test_case,
            retrieved_chunks=rag_context.document_chunks,
            retrieval_time_seconds=retrieval_time,
            embedding_cost_usd=embedding_cost,
            run_number=run_number,
        )

        logger.info(
            "rag_test_completed",
            test_id=test_case.test_id,
            run=run_number,
            map=f"{result.map_score:.3f}",
            recall_at_5=f"{result.recall_at_5:.3f}",
            precision_at_3=f"{result.precision_at_3:.3f}",
            duration=f"{retrieval_time:.2f}s",
            cost=f"${embedding_cost:.6f}",
        )

        return result

    def run_tests(
        self,
        test_id: Optional[str] = None,
        runs: int = 1,
        max_chunks: int = RAG_MAX_CHUNKS,
        min_relevance: float = RAG_MIN_RELEVANCE,
    ) -> tuple[List[RAGTestResult], float]:
        """Run all or specific test(s) multiple times.

        Args:
            test_id: Optional specific test ID (otherwise run all)
            runs: Number of runs per test
            max_chunks: Maximum chunks to retrieve
            min_relevance: Minimum relevance threshold

        Returns:
            Tuple of (list of all test results, total time in seconds)
        """
        test_cases = self.load_test_cases(test_id)

        all_results = []
        total_start_time = time.time()

        for test_case in test_cases:
            for run_num in range(1, runs + 1):
                result = self.run_test(
                    test_case=test_case,
                    max_chunks=max_chunks,
                    min_relevance=min_relevance,
                    run_number=run_num,
                )
                all_results.append(result)

        total_time = time.time() - total_start_time

        return all_results, total_time

    def calculate_summary(
        self,
        results: List[RAGTestResult],
        total_time_seconds: float,
        max_chunks: int = RAG_MAX_CHUNKS,
        min_relevance: float = RAG_MIN_RELEVANCE,
    ) -> RAGTestSummary:
        """Calculate summary statistics across all results.

        Args:
            results: List of test results
            total_time_seconds: Total time for all tests
            max_chunks: RAG_MAX_CHUNKS used
            min_relevance: RAG_MIN_RELEVANCE used

        Returns:
            RAGTestSummary
        """
        if not results:
            return RAGTestSummary(
                total_tests=0,
                mean_map=0.0,
                mean_recall_at_5=0.0,
                mean_recall_at_10=0.0,
                mean_precision_at_3=0.0,
                mean_precision_at_5=0.0,
                mean_mrr=0.0,
                total_time_seconds=0.0,
                avg_retrieval_time_seconds=0.0,
                total_cost_usd=0.0,
                rag_max_chunks=max_chunks,
                rag_min_relevance=min_relevance,
                embedding_model=EMBEDDING_MODEL,
            )

        # Calculate means
        mean_map = sum(r.map_score for r in results) / len(results)
        mean_recall_5 = sum(r.recall_at_5 for r in results) / len(results)
        mean_recall_10 = sum(r.recall_at_10 for r in results) / len(results)
        mean_prec_3 = sum(r.precision_at_3 for r in results) / len(results)
        mean_prec_5 = sum(r.precision_at_5 for r in results) / len(results)
        mean_mrr = sum(r.mrr for r in results) / len(results)

        # Calculate performance metrics
        avg_retrieval_time = sum(r.retrieval_time_seconds for r in results) / len(results)
        total_cost = sum(r.embedding_cost_usd for r in results)

        # Calculate standard deviations if multiple runs
        if len(results) > 1:
            import statistics

            std_map = statistics.stdev([r.map_score for r in results])
            std_recall_5 = statistics.stdev([r.recall_at_5 for r in results])
            std_prec_3 = statistics.stdev([r.precision_at_3 for r in results])
        else:
            std_map = 0.0
            std_recall_5 = 0.0
            std_prec_3 = 0.0

        # Get RRF k value from hybrid retriever
        rrf_k = 60  # Default
        if self.retriever.hybrid_retriever:
            rrf_k = self.retriever.hybrid_retriever.k

        return RAGTestSummary(
            total_tests=len(results),
            mean_map=mean_map,
            mean_recall_at_5=mean_recall_5,
            mean_recall_at_10=mean_recall_10,
            mean_precision_at_3=mean_prec_3,
            mean_precision_at_5=mean_prec_5,
            mean_mrr=mean_mrr,
            std_dev_map=std_map,
            std_dev_recall_at_5=std_recall_5,
            std_dev_precision_at_3=std_prec_3,
            total_time_seconds=total_time_seconds,
            avg_retrieval_time_seconds=avg_retrieval_time,
            total_cost_usd=total_cost,
            rag_max_chunks=max_chunks,
            rag_min_relevance=min_relevance,
            embedding_model=EMBEDDING_MODEL,
            rrf_k=rrf_k,
            hybrid_enabled=self.retriever.enable_hybrid,
        )
