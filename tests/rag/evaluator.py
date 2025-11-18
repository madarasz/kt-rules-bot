"""RAG test evaluator - calculates IR metrics.

Implements standard Information Retrieval metrics:
- Mean Average Precision (MAP)
- Recall@k
- Precision@k
- Mean Reciprocal Rank (MRR)
"""

from src.lib.text_utils import ground_truth_matches_text
from src.models.rag_context import DocumentChunk
from tests.rag.test_case_models import RAGTestCase, RAGTestResult


class RAGEvaluator:
    """Evaluates RAG retrieval quality using IR metrics."""

    def evaluate(
        self,
        test_case: RAGTestCase,
        retrieved_chunks: list[DocumentChunk],
        retrieval_time_seconds: float,
        embedding_cost_usd: float,
        run_number: int = 1,
    ) -> RAGTestResult:
        """Evaluate a single RAG test case.

        Args:
            test_case: Test case definition
            retrieved_chunks: Chunks retrieved by RAG system (ordered by relevance)
            retrieval_time_seconds: Time taken for retrieval operation
            embedding_cost_usd: Cost of generating query embedding
            run_number: Run number for multi-run tests

        Returns:
            RAGTestResult with calculated metrics
        """
        # Extract headers, texts, relevance scores, and metadata from retrieved chunks
        # Ensure headers and texts are strings (not None)
        retrieved_headers = [chunk.header or "" for chunk in retrieved_chunks]
        retrieved_texts = [chunk.text or "" for chunk in retrieved_chunks]
        retrieved_scores = [chunk.relevance_score for chunk in retrieved_chunks]
        retrieved_metadata = [chunk.metadata for chunk in retrieved_chunks]

        # Find which ground_truth_contexts were found
        # Use SUBSTRING matching: ground truth text must be CONTAINED in retrieved header or text (case-insensitive)
        found = []
        missing = []
        ranks_of_required = []

        for gt_context in test_case.ground_truth_contexts:
            found_match = False

            # Check if ground truth is contained in any retrieved header
            for i, retr_header in enumerate(retrieved_headers, start=1):
                if ground_truth_matches_text(gt_context, retr_header):
                    found.append(gt_context)
                    ranks_of_required.append(i)
                    found_match = True
                    break  # Only count first match

            # Check if ground truth is contained in any retrieved text (if not found in header)
            if not found_match:
                for i, retr_text in enumerate(retrieved_texts, start=1):
                    if ground_truth_matches_text(gt_context, retr_text):
                        found.append(gt_context)
                        ranks_of_required.append(i)
                        found_match = True
                        break

            if not found_match:
                missing.append(gt_context)

        # Calculate metrics
        map_score = self._calculate_map(ranks_of_required, len(test_case.ground_truth_contexts))
        recall_at_5 = self._calculate_recall_at_k(
            ranks_of_required, len(test_case.ground_truth_contexts), k=5
        )
        recall_at_all = self._calculate_recall_at_all(
            len(found), len(test_case.ground_truth_contexts)
        )
        recall_at_10 = self._calculate_recall_at_k(
            ranks_of_required, len(test_case.ground_truth_contexts), k=10
        )
        precision_at_3 = self._calculate_precision_at_k(ranks_of_required, k=3)
        precision_at_5 = self._calculate_precision_at_k(ranks_of_required, k=5)
        mrr = self._calculate_mrr(ranks_of_required)

        # Calculate max ground truth rank (highest rank where a ground truth was found)
        max_ground_truth_rank = max(ranks_of_required) if ranks_of_required else 0

        return RAGTestResult(
            test_id=test_case.test_id,
            query=test_case.query,
            ground_truth_contexts=test_case.ground_truth_contexts,
            retrieved_chunks=retrieved_headers,
            retrieved_chunk_texts=retrieved_texts,
            retrieved_relevance_scores=retrieved_scores,
            retrieved_chunk_metadata=retrieved_metadata,
            map_score=map_score,
            recall_at_5=recall_at_5,
            recall_at_all=recall_at_all,
            recall_at_10=recall_at_10,
            precision_at_3=precision_at_3,
            precision_at_5=precision_at_5,
            mrr=mrr,
            found_chunks=found,
            missing_chunks=missing,
            ranks_of_required=sorted(ranks_of_required),
            retrieval_time_seconds=retrieval_time_seconds,
            embedding_cost_usd=embedding_cost_usd,
            run_number=run_number,
            max_ground_truth_rank=max_ground_truth_rank,
        )

    def _calculate_map(self, ranks: list[int], total_relevant: int) -> float:
        """Calculate Mean Average Precision.

        MAP = (1/R) * Σ (Precision@k * rel(k))
        where R = total relevant documents, k = rank

        Args:
            ranks: List of ranks where relevant documents appear (1-indexed)
            total_relevant: Total number of relevant documents

        Returns:
            MAP score (0-1)
        """
        if total_relevant == 0:
            return 0.0

        if not ranks:
            return 0.0

        # Sort ranks
        sorted_ranks = sorted(ranks)

        # Calculate precision at each relevant rank
        precisions = []
        for i, rank in enumerate(sorted_ranks, start=1):
            # Precision@rank = number of relevant docs up to rank / rank
            precision_at_rank = i / rank
            precisions.append(precision_at_rank)

        # Average precision for this query
        ap = sum(precisions) / total_relevant

        return ap

    def _calculate_recall_at_k(self, ranks: list[int], total_relevant: int, k: int) -> float:
        """Calculate Recall@k.

        Recall@k = (# of relevant docs in top-k) / (total relevant docs)

        Args:
            ranks: List of ranks where relevant documents appear (1-indexed)
            total_relevant: Total number of relevant documents
            k: Cut-off rank

        Returns:
            Recall@k score (0-1)
        """
        if total_relevant == 0:
            return 0.0

        # Count how many relevant docs appear in top-k
        relevant_in_top_k = sum(1 for rank in ranks if rank <= k)

        return relevant_in_top_k / total_relevant

    def _calculate_recall_at_all(self, found_count: int, total_relevant: int) -> float:
        """Calculate Recall@All (percentage of required chunks found, regardless of position).

        Recall@All = (# of relevant docs found) / (total relevant docs)

        Args:
            found_count: Number of required chunks that were found
            total_relevant: Total number of relevant documents

        Returns:
            Recall@All score (0-1)
        """
        if total_relevant == 0:
            return 0.0

        return found_count / total_relevant

    def _calculate_precision_at_k(self, ranks: list[int], k: int) -> float:
        """Calculate Precision@k.

        Precision@k = (# of relevant docs in top-k) / k

        Args:
            ranks: List of ranks where relevant documents appear (1-indexed)
            k: Cut-off rank

        Returns:
            Precision@k score (0-1)
        """
        # Count how many relevant docs appear in top-k
        relevant_in_top_k = sum(1 for rank in ranks if rank <= k)

        return relevant_in_top_k / k

    def _calculate_mrr(self, ranks: list[int]) -> float:
        """Calculate Mean Reciprocal Rank.

        MRR = 1 / rank_of_first_relevant_doc

        Args:
            ranks: List of ranks where relevant documents appear (1-indexed)

        Returns:
            MRR score (0-1)
        """
        if not ranks:
            return 0.0

        # MRR is 1 / rank of first relevant document
        first_rank = min(ranks)
        return 1.0 / first_rank
