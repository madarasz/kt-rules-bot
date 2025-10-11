"""RAG test report generator - creates markdown reports.

Generates comprehensive reports with metrics, test breakdowns, and configuration.
"""

from pathlib import Path
from typing import List
from datetime import datetime

from tests.rag.test_case_models import RAGTestResult, RAGTestSummary


class RAGReportGenerator:
    """Generates markdown reports for RAG test results."""

    def generate_report(
        self,
        results: List[RAGTestResult],
        summary: RAGTestSummary,
        output_path: Path,
    ) -> None:
        """Generate comprehensive markdown report.

        Args:
            results: List of test results
            summary: Aggregated summary statistics
            output_path: Path to save report
        """
        content = []

        # Header
        content.append("# RAG Retrieval Test Report")
        content.append("")
        content.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        content.append("")

        # Overall Metrics
        content.append("## Overall Metrics")
        content.append("")
        content.append(f"**Total Tests**: {summary.total_tests}")
        content.append("")

        # Main metrics table
        content.append("| Metric | Value |")
        content.append("|--------|-------|")
        content.append(f"| **Mean MAP** | {summary.mean_map:.3f} |")
        content.append(f"| **Recall@5** | {summary.mean_recall_at_5:.3f} ({summary.mean_recall_at_5*100:.1f}%) |")
        content.append(f"| **Recall@10** | {summary.mean_recall_at_10:.3f} ({summary.mean_recall_at_10*100:.1f}%) |")
        content.append(f"| **Precision@3** | {summary.mean_precision_at_3:.3f} ({summary.mean_precision_at_3*100:.1f}%) |")
        content.append(f"| **Precision@5** | {summary.mean_precision_at_5:.3f} ({summary.mean_precision_at_5*100:.1f}%) |")
        content.append(f"| **MRR** | {summary.mean_mrr:.3f} |")
        content.append("")

        # Performance metrics
        content.append("## Performance Metrics")
        content.append("")
        content.append("| Metric | Value |")
        content.append("|--------|-------|")
        content.append(f"| **Total Time** | {summary.total_time_seconds:.2f}s |")
        content.append(f"| **Avg Retrieval Time** | {summary.avg_retrieval_time_seconds:.3f}s |")
        content.append(f"| **Total Cost** | ${summary.total_cost_usd:.6f} |")
        content.append("")

        # Multi-run statistics
        if summary.std_dev_map > 0:
            content.append("### Multi-Run Statistics")
            content.append("")
            content.append(f"- **MAP**: {summary.mean_map:.3f} ± {summary.std_dev_map:.3f}")
            content.append(f"- **Recall@5**: {summary.mean_recall_at_5:.3f} ± {summary.std_dev_recall_at_5:.3f}")
            content.append(f"- **Precision@3**: {summary.mean_precision_at_3:.3f} ± {summary.std_dev_precision_at_3:.3f}")
            content.append("")

        # Configuration
        content.append("## Configuration")
        content.append("")
        content.append("| Parameter | Value |")
        content.append("|-----------|-------|")
        content.append(f"| RAG_MAX_CHUNKS | {summary.rag_max_chunks} |")
        content.append(f"| RAG_MIN_RELEVANCE | {summary.rag_min_relevance} |")
        content.append(f"| EMBEDDING_MODEL | {summary.embedding_model} |")
        content.append(f"| RRF k | {summary.rrf_k} |")
        content.append(f"| BM25 k1 | {summary.bm25_k1} |")
        content.append(f"| BM25 b | {summary.bm25_b} |")
        content.append(f"| Hybrid Search | {'Enabled' if summary.hybrid_enabled else 'Disabled'} |")
        content.append("")

        # Per-Test Breakdown
        content.append("## Per-Test Results")
        content.append("")

        # Group by test_id
        tests_by_id = {}
        for result in results:
            if result.test_id not in tests_by_id:
                tests_by_id[result.test_id] = []
            tests_by_id[result.test_id].append(result)

        for test_id, test_results in tests_by_id.items():
            # Use first result for test details
            first_result = test_results[0]

            content.append(f"### {test_id}")
            content.append("")
            content.append(f"**Query**: {first_result.query}")
            content.append("")

            # Metrics (averaged if multiple runs)
            if len(test_results) > 1:
                avg_map = sum(r.map_score for r in test_results) / len(test_results)
                avg_recall5 = sum(r.recall_at_5 for r in test_results) / len(test_results)
                avg_prec3 = sum(r.precision_at_3 for r in test_results) / len(test_results)
                avg_time = sum(r.retrieval_time_seconds for r in test_results) / len(test_results)
                total_cost = sum(r.embedding_cost_usd for r in test_results)
                content.append(f"**Runs**: {len(test_results)}")
                content.append("")
                content.append("**Average Metrics**:")
                content.append(f"- MAP: {avg_map:.3f}")
                content.append(f"- Recall@5: {avg_recall5:.3f}")
                content.append(f"- Precision@3: {avg_prec3:.3f}")
                content.append(f"- Avg Retrieval Time: {avg_time:.3f}s")
                content.append(f"- Total Cost: ${total_cost:.6f}")
            else:
                content.append("**Metrics**:")
                content.append(f"- MAP: {first_result.map_score:.3f}")
                content.append(f"- Recall@5: {first_result.recall_at_5:.3f}")
                content.append(f"- Recall@10: {first_result.recall_at_10:.3f}")
                content.append(f"- Precision@3: {first_result.precision_at_3:.3f}")
                content.append(f"- Precision@5: {first_result.precision_at_5:.3f}")
                content.append(f"- MRR: {first_result.mrr:.3f}")
                content.append(f"- Retrieval Time: {first_result.retrieval_time_seconds:.3f}s")
                content.append(f"- Embedding Cost: ${first_result.embedding_cost_usd:.6f}")

            content.append("")

            # Required chunks
            content.append("**Required Chunks**:")
            for chunk in first_result.required_chunks:
                content.append(f"- {chunk}")
            content.append("")

            # Found vs Missing
            content.append("**Found** ✅:")
            if first_result.found_chunks:
                for chunk in first_result.found_chunks:
                    # Find rank
                    chunk_lower = chunk.strip().lower()
                    rank = None
                    for i, retr in enumerate(first_result.retrieved_chunks, start=1):
                        if retr.strip().lower() == chunk_lower:
                            rank = i
                            break
                    content.append(f"- {chunk} (rank #{rank})")
            else:
                content.append("- (none)")
            content.append("")
         
            if first_result.missing_chunks:
                content.append("**Missing** ❌:")
                for chunk in first_result.missing_chunks:
                    content.append(f"- {chunk}")
                content.append("")

            # Retrieved chunks (top 10)
            content.append("**Retrieved Chunks** (top 10):")
            for i, chunk_header in enumerate(first_result.retrieved_chunks[:10], start=1):
                # Mark if it's a required chunk
                marker = "✅" if chunk_header in first_result.found_chunks else ""
                content.append(f"{i}. {chunk_header} {marker}")
            content.append("")
            content.append("---")
            content.append("")

        # Write report
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write("\n".join(content))

    def save_retrieved_chunks(
        self,
        result: RAGTestResult,
        output_dir: Path,
    ) -> None:
        """Save full text of retrieved chunks for manual review.

        Args:
            result: Test result
            output_dir: Directory to save chunk texts
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"retrieved_chunks_{result.test_id}_run{result.run_number}.txt"
        output_path = output_dir / filename

        content = []
        content.append(f"Test: {result.test_id}")
        content.append(f"Query: {result.query}")
        content.append("=" * 80)
        content.append("")

        for i, (header, text) in enumerate(zip(result.retrieved_chunks, result.retrieved_chunk_texts), start=1):
            marker = "✅ REQUIRED" if header in result.found_chunks else ""
            content.append(f"[{i}] {header} {marker}")
            content.append("-" * 80)
            content.append(text)
            content.append("")
            content.append("=" * 80)
            content.append("")

        with open(output_path, "w") as f:
            f.write("\n".join(content))
