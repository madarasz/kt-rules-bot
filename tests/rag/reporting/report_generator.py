"""RAG test report generator - creates markdown reports.

Generates comprehensive reports with metrics, test breakdowns, and configuration.
"""

from datetime import datetime
from pathlib import Path

from tests.rag.test_case_models import RAGTestResult, RAGTestSummary


class RAGReportGenerator:
    """Generates markdown reports for RAG test results."""

    def generate_report(
        self, results: list[RAGTestResult], summary: RAGTestSummary, output_path: Path
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

        # Ragas metrics
        if summary.mean_ragas_context_precision is not None:
            content.append("### Ragas Metrics")
            content.append("")
            content.append("| Metric | Value | Description |")
            content.append("|--------|-------|-------------|")
            content.append(
                f"| **Context Precision** | {summary.mean_ragas_context_precision:.3f} | Proportion of retrieved contexts containing ground truth |"
            )
            content.append(
                f"| **Context Recall** | {summary.mean_ragas_context_recall:.3f} | Proportion of ground truth found in retrieved contexts |"
            )
            content.append("")

        # Hopping metrics (if multi-hop enabled and data available)
        if summary.rag_max_hops > 0 and summary.avg_hops_used > 0:
            content.append("### Hopping")
            content.append("")
            content.append("| Metric | Value | Description |")
            content.append("|--------|-------|-------------|")
            content.append(
                f"| **Avg Hops Used** | {summary.avg_hops_used:.2f} | Average number of hops performed per test |"
            )
            content.append(
                f"| **Avg Ground Truth Found in Hops** | {summary.avg_ground_truth_found_improvement:.2f} | Average number of ground truth chunks found via hops |"
            )
            content.append(
                f"| **Can Answer Recall** | {summary.hop_can_answer_recall:.3f} | Proportion of times LLM hopped when ground truth was missing |"
            )
            content.append(
                f"| **Can Answer Precision** | {summary.hop_can_answer_precision:.3f} | Proportion of hops that were made when ground truth was actually missing |"
            )

            # Per-hop breakdown
            if summary.ground_truth_chunks_per_hop:
                for hop_num, count in enumerate(summary.ground_truth_chunks_per_hop, start=1):
                    content.append(
                        f"| **Ground Truth in Hop {hop_num}** | {count} | Total ground truth chunks found in hop {hop_num} across all tests |"
                    )

            content.append("")

        # Missing chunks analysis
        content.append("## Missing Chunks")
        content.append("")
        missing_chunks_found = False
        count_missing_chunks = 0
        for result in results:
            if result.missing_chunks:
                missing_chunks_found = True
                for missing_chunk in result.missing_chunks:
                    content.append(f"- **{result.test_id}**: *{missing_chunk}*")
                    count_missing_chunks += 1
        content.append(f"\n\n**Number of missing chunks**: {count_missing_chunks}")

        if not missing_chunks_found:
            content.append("No missing chunks - all required chunks were retrieved!")
        content.append("")

        # Performance metrics
        content.append("## Performance Metrics")
        content.append("")
        content.append("| Metric | Value |")
        content.append("|--------|-------|")
        content.append(f"| **Total Time** | {summary.total_time_seconds:.2f}s |")
        content.append(f"| **Avg Retrieval Time** | {summary.avg_retrieval_time_seconds:.3f}s |")

        # Calculate total cost including hop evaluations
        total_cost_with_hops = summary.total_cost_usd + summary.hop_evaluation_cost_usd
        content.append(f"| **Total Cost** | ${total_cost_with_hops:.6f} |")

        # Cost breakdown - group embeddings together
        content.append(f"| **RAG Costs** | ${total_cost_with_hops:.6f} |")
        content.append(f"| └─ Embeddings** | ${summary.total_cost_usd:.6f} |")

        # Add hop-specific metrics if multi-hop is enabled
        if summary.rag_max_hops > 0:
            content.append(f"| └─ Hop Evaluations** | ${summary.hop_evaluation_cost_usd:.6f} |")
            content.append(f"| **Avg Hops Used** | {summary.avg_hops_used:.2f} |")

        content.append("")

        # Multi-run statistics
        if (
            summary.mean_ragas_context_precision is not None
            and summary.std_dev_ragas_context_precision > 0
        ):
            content.append("### Multi-Run Statistics")
            content.append("")
            content.append(
                f"- **Context Precision**: {summary.mean_ragas_context_precision:.3f} ± {summary.std_dev_ragas_context_precision:.3f}"
            )
            content.append(
                f"- **Context Recall**: {summary.mean_ragas_context_recall:.3f} ± {summary.std_dev_ragas_context_recall:.3f}"
            )
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
        content.append(
            f"| Query Normalization | {'Enabled' if summary.query_normalization_enabled else 'Disabled'} |"
        )
        content.append(
            f"| Query Expansion | {'Enabled' if summary.query_expansion_enabled else 'Disabled'} |"
        )

        # Add multi-hop configuration if enabled
        if summary.rag_max_hops > 0:
            content.append("| **Multi-Hop Settings** | |")
            content.append(f"| RAG_MAX_HOPS | {summary.rag_max_hops} |")
            content.append(f"| RAG_HOP_CHUNK_LIMIT | {summary.rag_hop_chunk_limit} |")
            content.append(f"| RAG_HOP_EVALUATION_MODEL | {summary.rag_hop_evaluation_model} |")

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
                avg_time = sum(r.retrieval_time_seconds for r in test_results) / len(test_results)
                total_cost = sum(r.embedding_cost_usd for r in test_results)

                # Ragas averages (if available)
                ragas_cp_values = [
                    r.ragas_context_precision
                    for r in test_results
                    if r.ragas_context_precision is not None
                ]
                ragas_cr_values = [
                    r.ragas_context_recall
                    for r in test_results
                    if r.ragas_context_recall is not None
                ]

                content.append(f"**Runs**: {len(test_results)}")
                content.append("")
                content.append("**Average Metrics**:")

                if ragas_cp_values:
                    avg_ragas_cp = sum(ragas_cp_values) / len(ragas_cp_values)
                    avg_ragas_cr = sum(ragas_cr_values) / len(ragas_cr_values)
                    content.append(f"- Context Precision: {avg_ragas_cp:.3f}")
                    content.append(f"- Context Recall: {avg_ragas_cr:.3f}")

                content.append(f"- Avg Retrieval Time: {avg_time:.3f}s")
                content.append(f"- Total Cost: ${total_cost:.6f}")
            else:
                content.append("**Metrics**:")

                if first_result.ragas_context_precision is not None:
                    content.append(
                        f"- Context Precision: {first_result.ragas_context_precision:.3f}"
                    )
                    content.append(f"- Context Recall: {first_result.ragas_context_recall:.3f}")

            content.append("")

            # Found vs Missing (Ground truth contexts are shown here)
            content.append("**Found** ✅:")
            if first_result.found_chunks:
                for chunk in first_result.found_chunks:
                    # Find rank, relevance, and metadata (use substring matching)
                    # Match logic from evaluator.py: check header first, then text
                    chunk_lower = chunk.strip().lower().replace("*", "")
                    rank = None
                    relevance = None
                    metadata = None

                    # Check headers first
                    for i, (retr_header, score, meta) in enumerate(
                        zip(
                            first_result.retrieved_chunks,
                            first_result.retrieved_relevance_scores,
                            first_result.retrieved_chunk_metadata,
                            strict=False,
                        ),
                        start=1,
                    ):
                        # Use substring matching (consistent with evaluator)
                        if chunk_lower in retr_header.strip().lower().replace("*", ""):
                            rank = i
                            relevance = score
                            metadata = meta
                            break

                    # If not found in headers, check chunk text
                    if rank is None:
                        for i, (retr_text, score, meta) in enumerate(
                            zip(
                                first_result.retrieved_chunk_texts,
                                first_result.retrieved_relevance_scores,
                                first_result.retrieved_chunk_metadata,
                                strict=False,
                            ),
                            start=1,
                        ):
                            if chunk_lower in retr_text.strip().lower().replace("*", ""):
                                rank = i
                                relevance = score
                                metadata = meta
                                break

                    # Build score display
                    score_parts = []
                    if relevance is not None:
                        score_parts.append(f"final: {relevance:.4f}")

                    # Vector score - show N/A if not present
                    if metadata:
                        vector_score = metadata.get("vector_similarity")
                        if vector_score is not None:
                            score_parts.append(f"vector: {vector_score:.4f}")
                        else:
                            score_parts.append("vector: N/A")

                        # BM25 score
                        bm25_score = metadata.get("bm25_score")
                        if bm25_score is not None:
                            score_parts.append(f"bm25: {bm25_score:.2f}")

                        # RRF score
                        rrf_score = metadata.get("rrf_score")
                        if rrf_score is not None:
                            score_parts.append(f"rrf: {rrf_score:.4f}")

                    score_display = ", ".join(score_parts) if score_parts else "N/A"
                    content.append(f"- {chunk} (rank #{rank}, {score_display})")
            else:
                content.append("- (none)")
            content.append("")

            if first_result.missing_chunks:
                content.append("**Missing** ❌:")
                for chunk in first_result.missing_chunks:
                    content.append(f"- {chunk}")
                content.append("")

            # Hop evaluations (if multi-hop was used)
            if first_result.hops_used > 0 and first_result.hop_evaluations:
                content.append("**Hop Evaluations**:")
                content.append("")
                for hop_eval in first_result.hop_evaluations:
                    hop_num = hop_eval.get("hop_number", "?")
                    can_answer = (
                        "✅ Can answer" if hop_eval.get("can_answer") else "❌ Cannot answer"
                    )
                    reasoning = hop_eval.get("reasoning", "N/A")
                    missing_query = hop_eval.get("missing_query")

                    content.append(f"**Hop {hop_num}**: {can_answer}")
                    content.append(f"- **Reasoning**: {reasoning}")
                    if missing_query:
                        content.append(f"- **Missing Query**: {missing_query}")
                    content.append("")

            # Retrieved chunks - markdown table format
            content.append("**Retrieved Chunks**:")
            content.append("")

            # Table header - add hop column if multi-hop was used
            if first_result.hops_used > 0:
                content.append("| Rank | Hop | Chunk | Final | Vector | BM25 | RRF |")
                content.append("|------|-----|-------|-------|--------|------|-----|")
            else:
                content.append("| Rank | Chunk | Final | Vector | BM25 | RRF |")
                content.append("|------|-------|-------|--------|------|-----|")

            # Get hop numbers if available
            chunk_hop_numbers = (
                first_result.chunk_hop_numbers
                if first_result.chunk_hop_numbers
                else [0] * len(first_result.retrieved_chunks)
            )

            for i, (chunk_header, chunk_text, relevance, metadata, hop_num) in enumerate(
                zip(
                    first_result.retrieved_chunks,
                    first_result.retrieved_chunk_texts,
                    first_result.retrieved_relevance_scores,
                    first_result.retrieved_chunk_metadata,
                    chunk_hop_numbers,
                    strict=False,
                ),
                start=1,
            ):
                # Mark if it's a required chunk (use substring matching - consistent with evaluator)
                marker = ""
                chunk_header_lower = chunk_header.strip().lower().replace("*", "")
                chunk_text_lower = chunk_text.strip().lower().replace("*", "")
                for found_chunk in first_result.found_chunks:
                    # Check if found_chunk is contained IN chunk_header OR chunk_text (consistent with evaluator.py)
                    found_chunk_lower = found_chunk.strip().lower().replace("*", "")
                    if (
                        found_chunk_lower in chunk_header_lower
                        or found_chunk_lower in chunk_text_lower
                    ):
                        marker = " ✅"
                        break

                # Get scores from metadata
                # Show "N/A" if vector_similarity is missing (BM25-only chunk)
                vector_score = metadata.get("vector_similarity")
                vector_display = f"{vector_score:.4f}" if vector_score is not None else "N/A"

                # Show BM25 score if available
                bm25_score = metadata.get("bm25_score")
                bm25_display = f"{bm25_score:.2f}" if bm25_score is not None else "N/A"

                # RRF score should always be present
                rrf_score = metadata.get("rrf_score", 0.0)

                # Format as table row - include hop number if multi-hop
                if first_result.hops_used > 0:
                    content.append(
                        f"| {i} | {hop_num} | {chunk_header}{marker} | {relevance:.4f} | {vector_display} | {bm25_display} | {rrf_score:.4f} |"
                    )
                else:
                    content.append(
                        f"| {i} | {chunk_header}{marker} | {relevance:.4f} | {vector_display} | {bm25_display} | {rrf_score:.4f} |"
                    )
            content.append("")
            content.append("---")
            content.append("")

        # Write report
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write("\n".join(content))

    def save_retrieved_chunks(self, result: RAGTestResult, output_dir: Path) -> None:
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

        for i, (header, text) in enumerate(
            zip(result.retrieved_chunks, result.retrieved_chunk_texts, strict=False), start=1
        ):
            # Use substring matching to mark required chunks (same logic as evaluator)
            marker = ""
            header_lower = header.strip().lower().replace("*", "")
            text_lower = text.strip().lower().replace("*", "")
            for found_chunk in result.found_chunks:
                # Check if found_chunk is contained IN header or text (consistent with evaluator.py)
                found_chunk_lower = found_chunk.strip().lower().replace("*", "")
                if found_chunk_lower in header_lower or found_chunk_lower in text_lower:
                    marker = "✅ REQUIRED"
                    break
            content.append(f"[{i}] {header} {marker}")
            content.append("-" * 80)
            content.append(text)
            content.append("")
            content.append("=" * 80)
            content.append("")

        with open(output_path, "w") as f:
            f.write("\n".join(content))
