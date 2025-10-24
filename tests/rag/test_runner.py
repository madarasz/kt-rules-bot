"""RAG test runner - executes RAG retrieval tests.

Loads test cases, runs retrieval, evaluates metrics, generates reports.
"""

from pathlib import Path
from typing import List, Optional
from uuid import uuid4
import time

from tests.rag.test_case_models import RAGTestCase, RAGTestResult, RAGTestSummary
from tests.rag.evaluator import RAGEvaluator
from tests.rag.ragas_evaluator import RagasRAGEvaluator, add_ragas_metrics_to_result
from src.services.rag.retriever import RAGRetriever, RetrieveRequest
from src.services.rag.embeddings import EmbeddingService
from src.lib.constants import (
    RAG_MAX_CHUNKS,
    RAG_MIN_RELEVANCE,
    EMBEDDING_MODEL,
    MARKDOWN_CHUNK_HEADER_LEVEL,
    RRF_K,
    BM25_K1,
    BM25_B,
    BM25_WEIGHT,
    RAGAS_ENABLED,
)
from src.lib.tokens import estimate_embedding_cost
from src.lib.logging import get_logger

logger = get_logger(__name__)


class RAGTestRunner:
    """Runs RAG retrieval tests and generates reports."""

    def __init__(
        self,
        test_cases_dir: Path = Path("tests/rag/test_cases"),
        results_dir: Path = Path("tests/rag/results"),
        rrf_k: int = RRF_K,
        bm25_k1: float = BM25_K1,
        bm25_b: float = BM25_B,
        bm25_weight: float = BM25_WEIGHT,
        embedding_model: str = EMBEDDING_MODEL,
        use_ragas: bool = RAGAS_ENABLED,
    ):
        """Initialize test runner.

        Args:
            test_cases_dir: Directory containing YAML test cases
            results_dir: Directory for test results
            rrf_k: RRF constant for hybrid fusion (default: 60)
            bm25_k1: BM25 term frequency saturation parameter (default: 1.5)
            bm25_b: BM25 document length normalization parameter (default: 0.75)
            bm25_weight: Weight for BM25 in fusion (default: 0.5, vector gets 1-bm25_weight)
            embedding_model: Embedding model to use for queries (default: EMBEDDING_MODEL from constants)
            use_ragas: Whether to calculate Ragas metrics (default: RAGAS_ENABLED from constants)
        """
        self.test_cases_dir = test_cases_dir
        self.results_dir = results_dir
        self.rrf_k = rrf_k
        self.bm25_k1 = bm25_k1
        self.bm25_b = bm25_b
        self.bm25_weight = bm25_weight
        self.embedding_model = embedding_model
        self.use_ragas = use_ragas
        self.evaluator = RAGEvaluator()
        self.ragas_evaluator = RagasRAGEvaluator() if use_ragas else None

        # Create embedding service with custom model
        embedding_service = EmbeddingService(model=embedding_model)

        # Create retriever with custom embedding service
        self.retriever = RAGRetriever(
            embedding_service=embedding_service,
            rrf_k=rrf_k,
            bm25_k1=bm25_k1,
            bm25_b=bm25_b,
            bm25_weight=bm25_weight,
        )

        logger.info(
            "rag_test_runner_initialized",
            test_cases_dir=str(test_cases_dir),
            results_dir=str(results_dir),
            rrf_k=rrf_k,
            bm25_k1=bm25_k1,
            bm25_b=bm25_b,
            bm25_weight=bm25_weight,
            embedding_model=embedding_model,
            use_ragas=use_ragas,
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
            # from_yaml now returns a list (supports both single and multiple tests per file)
            loaded_test_cases = RAGTestCase.from_yaml(yaml_file)

            for test_case in loaded_test_cases:
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

        # Evaluate with custom metrics
        result = self.evaluator.evaluate(
            test_case=test_case,
            retrieved_chunks=rag_context.document_chunks,
            retrieval_time_seconds=retrieval_time,
            embedding_cost_usd=embedding_cost,
            run_number=run_number,
        )

        # Evaluate with Ragas metrics (if enabled)
        ragas_metrics = None
        if self.use_ragas and self.ragas_evaluator:
            ragas_metrics = self.ragas_evaluator.evaluate(
                test_case=test_case,
                retrieved_chunks=rag_context.document_chunks,
                use_ragas=True,
            )
            # Add Ragas metrics to result
            result = add_ragas_metrics_to_result(result, ragas_metrics)

        # Log results
        log_data = {
            "test_id": test_case.test_id,
            "run": run_number,
            "map": f"{result.map_score:.3f}",
            "recall_at_5": f"{result.recall_at_5:.3f}",
            "recall_at_all": f"{result.recall_at_all:.3f}",
            "precision_at_3": f"{result.precision_at_3:.3f}",
            "duration": f"{retrieval_time:.2f}s",
            "cost": f"${embedding_cost:.6f}",
        }

        # Add Ragas metrics to log if available
        if ragas_metrics:
            if ragas_metrics.context_precision is not None:
                log_data["ragas_context_precision"] = f"{ragas_metrics.context_precision:.3f}"
            if ragas_metrics.context_recall is not None:
                log_data["ragas_context_recall"] = f"{ragas_metrics.context_recall:.3f}"

        logger.info("rag_test_completed", **log_data)

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
                mean_recall_at_all=0.0,
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
                chunk_header_level=MARKDOWN_CHUNK_HEADER_LEVEL,
            )

        # Group results by test_id to separate test cases
        from collections import defaultdict
        import statistics

        results_by_test = defaultdict(list)
        for result in results:
            results_by_test[result.test_id].append(result)

        # Calculate per-test-case means and standard deviations
        test_case_means = {
            'map': [],
            'recall_5': [],
            'recall_all': [],
            'recall_10': [],
            'prec_3': [],
            'prec_5': [],
            'mrr': [],
            'ragas_context_precision': [],
            'ragas_context_recall': [],
        }
        test_case_stds = {
            'map': [],
            'recall_5': [],
            'recall_all': [],
            'prec_3': [],
            'ragas_context_precision': [],
            'ragas_context_recall': [],
        }

        for test_id, test_results in results_by_test.items():
            # Calculate mean for this test case across all runs
            test_case_means['map'].append(sum(r.map_score for r in test_results) / len(test_results))
            test_case_means['recall_5'].append(sum(r.recall_at_5 for r in test_results) / len(test_results))
            test_case_means['recall_all'].append(sum(r.recall_at_all for r in test_results) / len(test_results))
            test_case_means['recall_10'].append(sum(r.recall_at_10 for r in test_results) / len(test_results))
            test_case_means['prec_3'].append(sum(r.precision_at_3 for r in test_results) / len(test_results))
            test_case_means['prec_5'].append(sum(r.precision_at_5 for r in test_results) / len(test_results))
            test_case_means['mrr'].append(sum(r.mrr for r in test_results) / len(test_results))

            # Calculate Ragas means (only if available)
            ragas_context_precision_values = [r.ragas_context_precision for r in test_results if r.ragas_context_precision is not None]
            ragas_context_recall_values = [r.ragas_context_recall for r in test_results if r.ragas_context_recall is not None]

            if ragas_context_precision_values:
                test_case_means['ragas_context_precision'].append(sum(ragas_context_precision_values) / len(ragas_context_precision_values))
            if ragas_context_recall_values:
                test_case_means['ragas_context_recall'].append(sum(ragas_context_recall_values) / len(ragas_context_recall_values))

            # Calculate standard deviation for this test case (only if multiple runs)
            if len(test_results) > 1:
                test_case_stds['map'].append(statistics.stdev([r.map_score for r in test_results]))
                test_case_stds['recall_5'].append(statistics.stdev([r.recall_at_5 for r in test_results]))
                test_case_stds['recall_all'].append(statistics.stdev([r.recall_at_all for r in test_results]))
                test_case_stds['prec_3'].append(statistics.stdev([r.precision_at_3 for r in test_results]))

                # Ragas standard deviations
                if len(ragas_context_precision_values) > 1:
                    test_case_stds['ragas_context_precision'].append(statistics.stdev(ragas_context_precision_values))
                else:
                    test_case_stds['ragas_context_precision'].append(0.0)

                if len(ragas_context_recall_values) > 1:
                    test_case_stds['ragas_context_recall'].append(statistics.stdev(ragas_context_recall_values))
                else:
                    test_case_stds['ragas_context_recall'].append(0.0)
            else:
                test_case_stds['map'].append(0.0)
                test_case_stds['recall_5'].append(0.0)
                test_case_stds['recall_all'].append(0.0)
                test_case_stds['prec_3'].append(0.0)
                test_case_stds['ragas_context_precision'].append(0.0)
                test_case_stds['ragas_context_recall'].append(0.0)

        # Overall means (average of per-test-case means)
        mean_map = sum(test_case_means['map']) / len(test_case_means['map'])
        mean_recall_5 = sum(test_case_means['recall_5']) / len(test_case_means['recall_5'])
        mean_recall_all = sum(test_case_means['recall_all']) / len(test_case_means['recall_all'])
        mean_recall_10 = sum(test_case_means['recall_10']) / len(test_case_means['recall_10'])
        mean_prec_3 = sum(test_case_means['prec_3']) / len(test_case_means['prec_3'])
        mean_prec_5 = sum(test_case_means['prec_5']) / len(test_case_means['prec_5'])
        mean_mrr = sum(test_case_means['mrr']) / len(test_case_means['mrr'])

        # Ragas overall means (if available)
        mean_ragas_context_precision = None
        mean_ragas_context_recall = None
        if test_case_means['ragas_context_precision']:
            mean_ragas_context_precision = sum(test_case_means['ragas_context_precision']) / len(test_case_means['ragas_context_precision'])
        if test_case_means['ragas_context_recall']:
            mean_ragas_context_recall = sum(test_case_means['ragas_context_recall']) / len(test_case_means['ragas_context_recall'])

        # Overall standard deviations (average of per-test-case standard deviations)
        # This represents the typical variance across runs for a single test case
        std_map = sum(test_case_stds['map']) / len(test_case_stds['map'])
        std_recall_5 = sum(test_case_stds['recall_5']) / len(test_case_stds['recall_5'])
        std_recall_all = sum(test_case_stds['recall_all']) / len(test_case_stds['recall_all'])
        std_prec_3 = sum(test_case_stds['prec_3']) / len(test_case_stds['prec_3'])

        # Ragas overall standard deviations
        std_ragas_context_precision = 0.0
        std_ragas_context_recall = 0.0
        if test_case_stds['ragas_context_precision']:
            std_ragas_context_precision = sum(test_case_stds['ragas_context_precision']) / len(test_case_stds['ragas_context_precision'])
        if test_case_stds['ragas_context_recall']:
            std_ragas_context_recall = sum(test_case_stds['ragas_context_recall']) / len(test_case_stds['ragas_context_recall'])

        # Calculate performance metrics
        avg_retrieval_time = sum(r.retrieval_time_seconds for r in results) / len(results)
        total_cost = sum(r.embedding_cost_usd for r in results)

        # Get BM25 parameters from hybrid retriever
        bm25_k1 = self.bm25_k1
        bm25_b = self.bm25_b
        bm25_weight = self.bm25_weight
        vector_weight = 1.0 - bm25_weight
        if self.retriever.hybrid_retriever and self.retriever.hybrid_retriever.bm25_retriever:
            bm25_k1 = self.retriever.hybrid_retriever.bm25_retriever.k1
            bm25_b = self.retriever.hybrid_retriever.bm25_retriever.b
            bm25_weight = self.retriever.hybrid_retriever.bm25_weight
            vector_weight = self.retriever.hybrid_retriever.vector_weight

        return RAGTestSummary(
            total_tests=len(results),
            mean_map=mean_map,
            mean_recall_at_5=mean_recall_5,
            mean_recall_at_all=mean_recall_all,
            mean_recall_at_10=mean_recall_10,
            mean_precision_at_3=mean_prec_3,
            mean_precision_at_5=mean_prec_5,
            mean_mrr=mean_mrr,
            std_dev_map=std_map,
            std_dev_recall_at_5=std_recall_5,
            std_dev_recall_at_all=std_recall_all,
            std_dev_precision_at_3=std_prec_3,
            mean_ragas_context_precision=mean_ragas_context_precision,
            mean_ragas_context_recall=mean_ragas_context_recall,
            std_dev_ragas_context_precision=std_ragas_context_precision,
            std_dev_ragas_context_recall=std_ragas_context_recall,
            total_time_seconds=total_time_seconds,
            avg_retrieval_time_seconds=avg_retrieval_time,
            total_cost_usd=total_cost,
            rag_max_chunks=max_chunks,
            rag_min_relevance=min_relevance,
            embedding_model=EMBEDDING_MODEL,
            chunk_header_level=MARKDOWN_CHUNK_HEADER_LEVEL,
            rrf_k=self.rrf_k,
            bm25_k1=bm25_k1,
            bm25_b=bm25_b,
            bm25_weight=bm25_weight,
            vector_weight=vector_weight,
            hybrid_enabled=self.retriever.enable_hybrid,
        )
