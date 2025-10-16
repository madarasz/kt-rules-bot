"""RAG test evaluator - calculates IR metrics.

Implements standard Information Retrieval metrics:
- Mean Average Precision (MAP)
- Recall@k
- Precision@k
- Mean Reciprocal Rank (MRR)
"""

from typing import List, Set
from tests.rag.test_case_models import RAGTestCase, RAGTestResult
from src.models.rag_context import DocumentChunk


class RAGEvaluator:
    """Evaluates RAG retrieval quality using IR metrics."""

    def evaluate(
        self,
        test_case: RAGTestCase,
        retrieved_chunks: List[DocumentChunk],
        retrieval_time_seconds: float,
        embedding_cost_usd: float,
        run_number: int = 1
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
        retrieved_headers = [chunk.header for chunk in retrieved_chunks]
        retrieved_texts = [chunk.text for chunk in retrieved_chunks]
        retrieved_scores = [chunk.relevance_score for chunk in retrieved_chunks]
        retrieved_metadata = [chunk.metadata for chunk in retrieved_chunks]

        # Find which required chunks were found
        # Use SUBSTRING matching: required chunk text must be CONTAINED in retrieved header (case-insensitive)
        found = []
        missing = []
        ranks_of_required = []

        for req_chunk in test_case.required_chunks:
            req_lower = req_chunk.strip().lower()
            found_match = False

            # Check if required chunk is contained in any retrieved header
            for i, retr_header in enumerate(retrieved_headers, start=1):
                if req_lower in retr_header.strip().lower():
                    found.append(req_chunk)
                    ranks_of_required.append(i)
                    found_match = True
                    break  # Only count first match

            if not found_match:
                missing.append(req_chunk)

        # Calculate metrics
        map_score = self._calculate_map(ranks_of_required, len(test_case.required_chunks))
        recall_at_5 = self._calculate_recall_at_k(ranks_of_required, len(test_case.required_chunks), k=5)
        recall_at_all = self._calculate_recall_at_all(len(found), len(test_case.required_chunks))
        recall_at_10 = self._calculate_recall_at_k(ranks_of_required, len(test_case.required_chunks), k=10)
        precision_at_3 = self._calculate_precision_at_k(ranks_of_required, k=3)
        precision_at_5 = self._calculate_precision_at_k(ranks_of_required, k=5)
        mrr = self._calculate_mrr(ranks_of_required)

        return RAGTestResult(
            test_id=test_case.test_id,
            query=test_case.query,
            required_chunks=test_case.required_chunks,
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
        )

    def _calculate_map(self, ranks: List[int], total_relevant: int) -> float:
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

    def _calculate_recall_at_k(self, ranks: List[int], total_relevant: int, k: int) -> float:
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

    def _calculate_precision_at_k(self, ranks: List[int], k: int) -> float:
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

    def _calculate_mrr(self, ranks: List[int]) -> float:
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
