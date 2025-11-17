"""RAG test runner - executes RAG retrieval tests.

Loads test cases, runs retrieval, evaluates metrics, generates reports.
"""

import time
from pathlib import Path
from uuid import uuid4

from src.lib.constants import (
    BM25_B,
    BM25_K1,
    BM25_WEIGHT,
    EMBEDDING_MODEL,
    MARKDOWN_CHUNK_HEADER_LEVEL,
    RAG_MAX_CHUNKS,
    RAG_MAX_HOPS,
    RAG_MIN_RELEVANCE,
    RRF_K,
)
from src.lib.logging import get_logger
from src.lib.tokens import estimate_embedding_cost
from src.models.rag_request import RetrieveRequest
from src.services.rag.embeddings import EmbeddingService
from src.services.rag.retriever import RAGRetriever
from tests.rag.evaluator import RAGEvaluator
from tests.rag.ragas_evaluator import RagasRAGEvaluator, add_ragas_metrics_to_result
from tests.rag.test_case_models import RAGTestCase, RAGTestResult, RAGTestSummary

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
        """
        self.test_cases_dir = test_cases_dir
        self.results_dir = results_dir
        self.rrf_k = rrf_k
        self.bm25_k1 = bm25_k1
        self.bm25_b = bm25_b
        self.bm25_weight = bm25_weight
        self.embedding_model = embedding_model

        # Create evaluators
        self.evaluator = RAGEvaluator()
        self.ragas_evaluator = RagasRAGEvaluator()

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
        )

    def load_test_cases(self, test_id: str | None = None) -> list[RAGTestCase]:
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
            use_multi_hop=(RAG_MAX_HOPS > 0),  # Explicitly set based on current constant value
        )

        # Retrieve chunks (returns tuple: context, hop_evaluations, chunk_hop_map)
        start_time = time.time()
        rag_context, hop_evaluations, chunk_hop_map = self.retriever.retrieve(request, query_id)
        retrieval_time = time.time() - start_time

        # Calculate costs following Discord bot pattern
        # 1. Initial embedding cost
        initial_embedding_cost = estimate_embedding_cost(test_case.query, model=EMBEDDING_MODEL)

        # 2. Hop embedding costs
        hop_embedding_cost = 0.0
        if hop_evaluations:
            for hop_eval in hop_evaluations:
                if hop_eval.missing_query:
                    hop_embedding_cost += estimate_embedding_cost(
                        hop_eval.missing_query, EMBEDDING_MODEL
                    )

        # 3. Hop evaluation LLM costs
        hop_evaluation_cost = (
            sum(hop_eval.cost_usd for hop_eval in hop_evaluations) if hop_evaluations else 0.0
        )

        # Total embedding cost (for backwards compatibility)
        total_embedding_cost = initial_embedding_cost + hop_embedding_cost

        # Total cost (RAG only - no main LLM generation)
        total_cost = total_embedding_cost + hop_evaluation_cost

        # Evaluate with custom metrics
        result = self.evaluator.evaluate(
            test_case=test_case,
            retrieved_chunks=rag_context.document_chunks,
            retrieval_time_seconds=retrieval_time,
            embedding_cost_usd=total_cost,  # Now includes hop costs
            run_number=run_number,
        )

        # Add multi-hop data to result
        result.hops_used = 0
        if hop_evaluations:
            # Convert HopEvaluation objects to dicts (include cost_usd for summary calculation)
            result.hop_evaluations = [
                {
                    "hop_number": i + 1,
                    "can_answer": eval.can_answer,
                    "reasoning": eval.reasoning,
                    "missing_query": eval.missing_query,
                    "cost_usd": eval.cost_usd,
                }
                for i, eval in enumerate(hop_evaluations)
            ]
            for eval in hop_evaluations:
                if eval.can_answer is False:
                    result.hops_used += 1

        # Map chunk IDs to hop numbers
        if chunk_hop_map:
            result.chunk_hop_numbers = [
                chunk_hop_map.get(chunk.chunk_id, 0) for chunk in rag_context.document_chunks
            ]

        # Evaluate with Ragas metrics
        ragas_metrics = self.ragas_evaluator.evaluate(
            test_case=test_case, retrieved_chunks=rag_context.document_chunks
        )
        # Add Ragas metrics to result
        result = add_ragas_metrics_to_result(result, ragas_metrics)

        # Log results
        log_data = {
            "test_id": test_case.test_id,
            "run": run_number,
            "duration": f"{retrieval_time:.2f}s",
            "cost": f"${total_cost:.6f}",
        }

        # Add Ragas metrics to log
        if ragas_metrics:
            if ragas_metrics.context_precision is not None:
                log_data["ragas_context_precision"] = f"{ragas_metrics.context_precision:.3f}"
            if ragas_metrics.context_recall is not None:
                log_data["ragas_context_recall"] = f"{ragas_metrics.context_recall:.3f}"

        logger.info("rag_test_completed", **log_data)

        return result

    def run_tests(
        self,
        test_id: str | None = None,
        runs: int = 1,
        max_chunks: int = RAG_MAX_CHUNKS,
        min_relevance: float = RAG_MIN_RELEVANCE,
    ) -> tuple[list[RAGTestResult], float]:
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
        results: list[RAGTestResult],
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
        import statistics
        from collections import defaultdict

        results_by_test = defaultdict(list)
        for result in results:
            results_by_test[result.test_id].append(result)

        # Calculate per-test-case means and standard deviations
        test_case_means = {
            "map": [],
            "recall_5": [],
            "recall_all": [],
            "recall_10": [],
            "prec_3": [],
            "prec_5": [],
            "mrr": [],
            "ragas_context_precision": [],
            "ragas_context_recall": [],
        }
        test_case_stds = {
            "map": [],
            "recall_5": [],
            "recall_all": [],
            "prec_3": [],
            "ragas_context_precision": [],
            "ragas_context_recall": [],
        }

        for _test_id, test_results in results_by_test.items():
            # Calculate mean for this test case across all runs
            test_case_means["map"].append(
                sum(r.map_score for r in test_results) / len(test_results)
            )
            test_case_means["recall_5"].append(
                sum(r.recall_at_5 for r in test_results) / len(test_results)
            )
            test_case_means["recall_all"].append(
                sum(r.recall_at_all for r in test_results) / len(test_results)
            )
            test_case_means["recall_10"].append(
                sum(r.recall_at_10 for r in test_results) / len(test_results)
            )
            test_case_means["prec_3"].append(
                sum(r.precision_at_3 for r in test_results) / len(test_results)
            )
            test_case_means["prec_5"].append(
                sum(r.precision_at_5 for r in test_results) / len(test_results)
            )
            test_case_means["mrr"].append(sum(r.mrr for r in test_results) / len(test_results))

            # Calculate Ragas means (only if available)
            ragas_context_precision_values = [
                r.ragas_context_precision
                for r in test_results
                if r.ragas_context_precision is not None
            ]
            ragas_context_recall_values = [
                r.ragas_context_recall for r in test_results if r.ragas_context_recall is not None
            ]

            if ragas_context_precision_values:
                test_case_means["ragas_context_precision"].append(
                    sum(ragas_context_precision_values) / len(ragas_context_precision_values)
                )
            if ragas_context_recall_values:
                test_case_means["ragas_context_recall"].append(
                    sum(ragas_context_recall_values) / len(ragas_context_recall_values)
                )

            # Calculate standard deviation for this test case (only if multiple runs)
            if len(test_results) > 1:
                test_case_stds["map"].append(statistics.stdev([r.map_score for r in test_results]))
                test_case_stds["recall_5"].append(
                    statistics.stdev([r.recall_at_5 for r in test_results])
                )
                test_case_stds["recall_all"].append(
                    statistics.stdev([r.recall_at_all for r in test_results])
                )
                test_case_stds["prec_3"].append(
                    statistics.stdev([r.precision_at_3 for r in test_results])
                )

                # Ragas standard deviations
                if len(ragas_context_precision_values) > 1:
                    test_case_stds["ragas_context_precision"].append(
                        statistics.stdev(ragas_context_precision_values)
                    )
                else:
                    test_case_stds["ragas_context_precision"].append(0.0)

                if len(ragas_context_recall_values) > 1:
                    test_case_stds["ragas_context_recall"].append(
                        statistics.stdev(ragas_context_recall_values)
                    )
                else:
                    test_case_stds["ragas_context_recall"].append(0.0)
            else:
                test_case_stds["map"].append(0.0)
                test_case_stds["recall_5"].append(0.0)
                test_case_stds["recall_all"].append(0.0)
                test_case_stds["prec_3"].append(0.0)
                test_case_stds["ragas_context_precision"].append(0.0)
                test_case_stds["ragas_context_recall"].append(0.0)

        # Overall means (average of per-test-case means)
        mean_map = sum(test_case_means["map"]) / len(test_case_means["map"])
        mean_recall_5 = sum(test_case_means["recall_5"]) / len(test_case_means["recall_5"])
        mean_recall_all = sum(test_case_means["recall_all"]) / len(test_case_means["recall_all"])
        mean_recall_10 = sum(test_case_means["recall_10"]) / len(test_case_means["recall_10"])
        mean_prec_3 = sum(test_case_means["prec_3"]) / len(test_case_means["prec_3"])
        mean_prec_5 = sum(test_case_means["prec_5"]) / len(test_case_means["prec_5"])
        mean_mrr = sum(test_case_means["mrr"]) / len(test_case_means["mrr"])

        # Ragas overall means (if available)
        mean_ragas_context_precision = None
        mean_ragas_context_recall = None
        if test_case_means["ragas_context_precision"]:
            mean_ragas_context_precision = sum(test_case_means["ragas_context_precision"]) / len(
                test_case_means["ragas_context_precision"]
            )
        if test_case_means["ragas_context_recall"]:
            mean_ragas_context_recall = sum(test_case_means["ragas_context_recall"]) / len(
                test_case_means["ragas_context_recall"]
            )

        # Overall standard deviations (average of per-test-case standard deviations)
        # This represents the typical variance across runs for a single test case
        std_map = sum(test_case_stds["map"]) / len(test_case_stds["map"])
        std_recall_5 = sum(test_case_stds["recall_5"]) / len(test_case_stds["recall_5"])
        std_recall_all = sum(test_case_stds["recall_all"]) / len(test_case_stds["recall_all"])
        std_prec_3 = sum(test_case_stds["prec_3"]) / len(test_case_stds["prec_3"])

        # Ragas overall standard deviations
        std_ragas_context_precision = 0.0
        std_ragas_context_recall = 0.0
        if test_case_stds["ragas_context_precision"]:
            std_ragas_context_precision = sum(test_case_stds["ragas_context_precision"]) / len(
                test_case_stds["ragas_context_precision"]
            )
        if test_case_stds["ragas_context_recall"]:
            std_ragas_context_recall = sum(test_case_stds["ragas_context_recall"]) / len(
                test_case_stds["ragas_context_recall"]
            )

        # Calculate performance metrics
        avg_retrieval_time = sum(r.retrieval_time_seconds for r in results) / len(results)

        # Calculate actual hop evaluation cost from stored hop evaluation data
        hop_evaluation_cost = 0.0
        for result in results:
            if result.hop_evaluations:
                for hop_eval in result.hop_evaluations:
                    hop_evaluation_cost += hop_eval.get("cost_usd", 0.0)

        # Note: r.embedding_cost_usd now contains TOTAL cost (embeddings + hop evaluations)
        # from line 200 where we stored total_cost in embedding_cost_usd for backwards compatibility
        # So to get just embeddings, we sum embedding_cost_usd and subtract hop_evaluation_cost
        total_cost_all = sum(r.embedding_cost_usd for r in results)
        total_embedding_cost_only = total_cost_all - hop_evaluation_cost

        # Calculate multi-hop statistics
        avg_hops_used = sum(r.hops_used for r in results) / len(results) if results else 0.0

        # Calculate hop-specific ground truth statistics
        # Track how many ground truth chunks were found in each hop across all tests
        from collections import defaultdict

        hop_ground_truth_counts = defaultdict(
            int
        )  # hop_number -> count of ground truth chunks found
        total_ground_truth_improvement = 0  # Total ground truth chunks found via hops (hop > 0)

        for result in results:
            if result.chunk_hop_numbers and result.ground_truth_contexts:
                # For each retrieved chunk, check if it's a ground truth chunk and which hop it came from
                for i, chunk_text in enumerate(result.retrieved_chunk_texts):
                    hop_number = result.chunk_hop_numbers[i]
                    # Check if this chunk matches any ground truth context
                    for gt_context in result.ground_truth_contexts:
                        if gt_context.lower() in chunk_text.lower():
                            hop_ground_truth_counts[hop_number] += 1
                            if hop_number > 0:  # Only count hops, not initial retrieval
                                total_ground_truth_improvement += 1
                            break  # Don't double-count if multiple ground truths match

        # Calculate average improvement per test
        avg_ground_truth_improvement = (
            total_ground_truth_improvement / len(results) if results else 0.0
        )

        # Create list of ground truth chunks found per hop [hop1, hop2, hop3, ...]
        # Find max hop number to determine list size
        max_hop = max(hop_ground_truth_counts.keys()) if hop_ground_truth_counts else 0
        ground_truth_per_hop = [hop_ground_truth_counts.get(i, 0) for i in range(1, max_hop + 1)]

        # Calculate hop "can_answer" precision/recall
        # TP = ground truth missing from current chunks AND hop made (can_answer=false)
        # FP = all ground truths present BUT hop made (unnecessary hop)
        # FN = ground truth missing BUT no hop made (can_answer=true too early)
        true_positives = 0
        false_positives = 0
        false_negatives = 0

        for result in results:
            if result.hop_evaluations and result.ground_truth_contexts:
                # Track accumulated chunks as we iterate through hops
                accumulated_chunk_texts = []

                # Add initial retrieval chunks (hop 0)
                if result.chunk_hop_numbers:
                    for i, hop_num in enumerate(result.chunk_hop_numbers):
                        if hop_num == 0:
                            accumulated_chunk_texts.append(result.retrieved_chunk_texts[i])

                # Evaluate each hop
                for hop_idx, hop_eval in enumerate(result.hop_evaluations):
                    hop_num = hop_idx + 1

                    # Check if all ground truths are present in accumulated chunks at this point
                    all_ground_truths_present = True
                    for gt_context in result.ground_truth_contexts:
                        gt_lower = gt_context.strip().lower()
                        found_in_accumulated = False
                        for chunk_text in accumulated_chunk_texts:
                            if gt_lower in chunk_text.strip().lower().replace("*", ""):
                                found_in_accumulated = True
                                break
                        if not found_in_accumulated:
                            all_ground_truths_present = False
                            break

                    # Determine if hop was made
                    hop_was_made = not hop_eval.get("can_answer")

                    # Calculate TP/FP/FN
                    if not all_ground_truths_present:
                        # Ground truth is missing
                        if hop_was_made:
                            true_positives += 1  # Correctly identified missing context and hopped
                        else:
                            false_negatives += 1  # Should have hopped but didn't
                    else:
                        # All ground truths present
                        if hop_was_made:
                            false_positives += 1  # Unnecessary hop
                        # If no hop was made and all present, that's a true negative (not counted in precision/recall)

                    # Add chunks from this hop to accumulated chunks for next iteration
                    if result.chunk_hop_numbers:
                        for i, chunk_hop in enumerate(result.chunk_hop_numbers):
                            if chunk_hop == hop_num:
                                accumulated_chunk_texts.append(result.retrieved_chunk_texts[i])

        # Calculate precision and recall
        hop_can_answer_recall = 0.0
        hop_can_answer_precision = 0.0

        if (true_positives + false_negatives) > 0:
            hop_can_answer_recall = true_positives / (true_positives + false_negatives)

        if (true_positives + false_positives) > 0:
            hop_can_answer_precision = true_positives / (true_positives + false_positives)

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
            total_cost_usd=total_embedding_cost_only,  # Just embeddings (hop costs tracked separately)
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
            avg_hops_used=avg_hops_used,
            hop_evaluation_cost_usd=hop_evaluation_cost,
            avg_ground_truth_found_improvement=avg_ground_truth_improvement,
            ground_truth_chunks_per_hop=ground_truth_per_hop,
            hop_can_answer_recall=hop_can_answer_recall,
            hop_can_answer_precision=hop_can_answer_precision,
        )
