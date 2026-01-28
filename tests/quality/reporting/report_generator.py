"""Generates markdown reports for quality tests."""

import os
from collections import defaultdict

import numpy as np

from src.lib.constants import QUALITY_TEST_JUDGING
from tests.quality.reporting.chart_generator import ChartGenerator
from tests.quality.reporting.report_models import IndividualTestResult, ModelSummary, QualityReport


class ReportGenerator:
    """Generates markdown reports from a QualityReport object."""

    def __init__(self, report: QualityReport):
        self.report = report
        self.report_dir = report.report_dir

    def generate_all_reports(self) -> str:
        """
        Generates all necessary report files based on the test configuration.
        Returns the path to the main report file.
        """
        # Generate charts first (they populate chart_path fields in the report)
        chart_generator = ChartGenerator(self.report)
        chart_generator.generate_all_charts()

        # Always generate the main report
        main_report_path = os.path.join(self.report_dir, "report.md")
        main_report_content = self._generate_main_report()
        self._write_file(main_report_path, main_report_content)

        # Generate per-test-case reports if needed
        if self.report.is_multi_test_case and self.report.is_multi_model:
            for test_id, test_case_report in self.report.per_test_case_reports.items():
                path = os.path.join(self.report_dir, f"report_{test_id}.md")
                content = self._generate_test_case_report(test_id, test_case_report.results)
                self._write_file(path, content)

        # Per-test-case-and-model reports for very detailed analysis in complex scenarios
        if (
            self.report.is_multi_run
            and self.report.is_multi_test_case
            and self.report.is_multi_model
        ):
            for test_id, test_case_report in self.report.per_test_case_reports.items():
                for model_name in self.report.models:
                    results = [r for r in test_case_report.results if r.model == model_name]
                    if results:
                        path = os.path.join(self.report_dir, f"report_{test_id}_{model_name}.md")
                        content = self._generate_test_case_model_report(
                            test_id, model_name, results
                        )
                        self._write_file(path, content)

        return main_report_path

    def _generate_main_report(self) -> str:
        """Generates the content for the main report.md file."""
        content = []
        content.append(self._get_overall_report_header())

        if self.report.is_multi_model:
            content.append("\n" + self._get_model_comparison_table())

        if (
            self.report.is_multi_run
            and self.report.is_multi_test_case
            and not self.report.is_multi_model
        ):
            content.append(self._get_test_case_summary_table())

        # Link to sub-reports or show individual results
        if self.report.is_multi_test_case and self.report.is_multi_model:
            content.append("\n## Detailed Test Case Reports")
            for test_id in self.report.test_cases:
                # Calculate average score for this test case
                if test_id in self.report.per_test_case_reports:
                    test_case_report = self.report.per_test_case_reports[test_id]
                    if test_case_report.results:
                        avg_score = sum(r.score_percentage for r in test_case_report.results) / len(
                            test_case_report.results
                        )
                        content.append(
                            f"- [Report for {test_id}](./report_{test_id}.md) - {avg_score:.1f}%"
                        )
                    else:
                        content.append(f"- [Report for {test_id}](./report_{test_id}.md)")
                else:
                    content.append(f"- [Report for {test_id}](./report_{test_id}.md)")
        else:
            content.append("\n## Individual Test Results")
            content.append(self._get_grouped_individual_results(self.report.results))

        return "\n".join(content)

    def _generate_test_case_report(self, test_id: str, results: list[IndividualTestResult]) -> str:
        """Generates content for a per-test-case report."""
        content = [f"# Test Case Report: {test_id}\n"]

        # Summary and comparison table for this test case
        content.append("## Summary")
        # Simplified model comparison for this specific test case
        # This requires aggregating results just for this test case
        model_summaries_for_test_case: list[ModelSummary] = []
        for model_name in self.report.models:
            model_results = [r for r in results if r.model == model_name]
            if model_results:
                model_summaries_for_test_case.append(ModelSummary(model_name, model_results))

        content.append(self._get_model_comparison_table(model_summaries_for_test_case))

        if self.report.per_test_case_reports[test_id].chart_path:
            chart_name = os.path.basename(self.report.per_test_case_reports[test_id].chart_path)
            content.append(f"\n![Test Case Chart](./{chart_name})")

        content.append("\n## Individual Results")
        if self.report.is_multi_run and self.report.is_multi_model:
            content.append("\n### Detailed Run Reports")
            for model_name in self.report.models:
                content.append(
                    f"- [Report for {test_id} on {model_name}](./report_{test_id}_{model_name}.md)"
                )
        else:
            content.append(self._get_grouped_individual_results(results))

        return "\n".join(content)

    def _generate_test_case_model_report(
        self, test_id: str, model_name: str, results: list[IndividualTestResult]
    ) -> str:
        """Generates a report for a specific test case and model, showing all runs."""
        content = [f"# Report for {test_id} on {model_name}\n"]

        summary = ModelSummary(model_name, results)
        content.append("## Summary of Runs")
        content.append(
            f"- **Average Score:** {summary.avg_score_pct:.2f}% (±{summary.std_dev_score_pct:.2f})"
        )
        content.append(f"- **Average Time:** {summary.avg_time:.2f}s (±{summary.std_dev_time:.2f})")
        content.append(
            f"- **Average Cost:** ${summary.avg_cost:.4f} (±${summary.std_dev_cost:.4f})"
        )

        content.append("\n## Individual Run Results")
        for i, result in enumerate(results):
            content.append(f"\n### Run #{i + 1}")
            content.append(self._get_individual_test_result_section(result, include_header=False))

        return "\n".join(content)

    def _get_overall_report_header(self) -> str:
        """Builds the overall report header string."""
        # Calculate cost breakdown from all results
        total_main = sum(r.cost_usd for r in self.report.results)
        total_multi_hop = sum(r.multi_hop_cost_usd for r in self.report.results)
        total_judge = sum(r.ragas_cost_usd for r in self.report.results)
        total_embedding = sum(r.embedding_cost_usd for r in self.report.results)

        header = [
            "# Quality Test Report",
            f"- **Total time**: {self.report.total_time_seconds // 60:.0f}m {self.report.total_time_seconds % 60:.2f}s",
            f"- **Total cost**: ${self.report.total_cost_usd:.4f}",
        ]

        # Add cost breakdown with percentages
        if self.report.total_cost_usd > 0:
            header.extend([
                f"  - Main LLM: ${total_main:.4f} ({total_main/self.report.total_cost_usd*100:.1f}%)",
                f"  - Multi-hop: ${total_multi_hop:.4f} ({total_multi_hop/self.report.total_cost_usd*100:.1f}%)",
                f"  - Judge: ${total_judge:.4f} ({total_judge/self.report.total_cost_usd*100:.1f}%)",
                f"  - Embeddings: ${total_embedding:.4f} ({total_embedding/self.report.total_cost_usd*100:.1f}%)",
            ])

        header.append(f"- **Total queries**: {self.report.total_queries}")
        if self.report.is_multi_model or self.report.is_multi_run:
            best_model = max(
                self.report.per_model_summaries.values(), key=lambda s: s.avg_score_pct
            )
            header.append(
                f"- **Best score**: {best_model.avg_score_pct:.1f}% - {best_model.model_name}"
            )

        header.append(f"- **Test cases**: {', '.join(self.report.test_cases)}")
        header.append(f"- **Judge model**: {self.report.judge_model} ({QUALITY_TEST_JUDGING} mode)")

        if self.report.chart_path:
            chart_name = os.path.basename(self.report.chart_path)
            header.append(f"\n![Overall Chart](./{chart_name})")

        if self.report.ragas_chart_path:
            ragas_chart_name = os.path.basename(self.report.ragas_chart_path)
            header.append(f"\n![Ragas Metrics Chart](./{ragas_chart_name})")

        return "\n".join(header)

    def _get_model_comparison_table(self, summaries: list[ModelSummary] | None = None) -> str:
        """Builds a markdown table comparing models."""
        if summaries is None:
            summaries = list(self.report.per_model_summaries.values())

        headers = ["Model", "Avg Score %", "Avg Time/Query (s)", "Avg Cost/Query ($)"]
        table = [
            "| " + " | ".join(headers) + " |",
            "|-" + "-|-".join(["-" * len(h) for h in headers]) + "-|",
        ]
        for summary in sorted(summaries, key=lambda s: s.avg_score_pct, reverse=True):
            score_std_dev = (
                f" (±{summary.std_dev_score_pct:.1f})" if self.report.is_multi_run else ""
            )
            time_std_dev = f" (±{summary.std_dev_time:.2f})" if self.report.is_multi_run else ""
            cost_std_dev = f" (±{summary.std_dev_cost:.4f})" if self.report.is_multi_run else ""
            row = [
                summary.model_name,
                f"{summary.avg_score_pct:.1f}%{score_std_dev}",
                f"{summary.avg_time:.2f}{time_std_dev}",
                f"${summary.avg_cost:.4f}{cost_std_dev}",
            ]
            table.append("| " + " | ".join(row) + " |")
        return "\n".join(table)

    def _get_test_case_summary_table(self) -> str:
        """Builds a markdown table summarizing test cases for a single model over multiple runs."""
        headers = ["Test Case", "Avg Score %", "Avg Time (s)", "Avg Cost ($)"]
        table = [
            "| " + " | ".join(headers) + " |",
            "|-" + "-|-".join(["-" * len(h) for h in headers]) + "-|",
        ]
        for test_id, test_case_report in self.report.per_test_case_reports.items():
            # This requires aggregation within the test case report
            avg_score = np.mean([r.score_percentage for r in test_case_report.results])
            std_dev_score = np.std([r.score_percentage for r in test_case_report.results])
            avg_time = np.mean([r.generation_time_seconds for r in test_case_report.results])
            avg_cost = np.mean([r.total_cost_usd for r in test_case_report.results])
            row = [
                test_id,
                f"{avg_score:.1f}% (±{std_dev_score:.1f})",
                f"{avg_time:.2f}",
                f"${avg_cost:.4f}",
            ]
            table.append("| " + " | ".join(row) + " |")
        return "\n## Summary per Test Case\n" + "\n".join(table)

    def _get_grouped_individual_results(self, results: list[IndividualTestResult]) -> str:
        """Group test results by test_id with models as subheaders."""

        # Group results by test case ID
        grouped_results: dict[str, list[IndividualTestResult]] = defaultdict(list)
        for result in results:
            grouped_results[result.test_id].append(result)

        content = []
        for test_id, test_results in grouped_results.items():
            # H3: Test case header
            content.append(f"\n### {test_id}")

            # Add query (belongs to test case, not model)
            if test_results:
                content.append(f"\n**Query:** {test_results[0].query}")

            # Group by model within this test case
            model_results: dict[str, list[IndividualTestResult]] = defaultdict(list)
            for result in test_results:
                model_results[result.model].append(result)

            for model_name, model_test_results in model_results.items():
                # Show each run separately for multiple runs
                for run_idx, result in enumerate(model_test_results, 1):
                    # H4: Model header with run number
                    if len(model_test_results) > 1:
                        content.append(f"\n#### {model_name} - Run #{run_idx}")
                    else:
                        content.append(f"\n#### {model_name}")

                    # Status with emoji - skull for errors (generation or evaluation), warning for partial scores
                    if result.error or result.ragas_evaluation_error:
                        status_emoji = "💀"
                        status_text = "Error"
                    elif result.passed:
                        status_emoji = "✅"
                        status_text = "Passed"
                    elif result.score_percentage >= 50.0:
                        status_emoji = "⚠️"
                        status_text = "Partial"
                    else:
                        status_emoji = "❌"
                        status_text = "Failed"

                    # Use bullet points for metrics
                    content.append(f"- **Status:** {status_emoji} {status_text}")
                    content.append(
                        f"- **Score:** {result.score}/{result.max_score} ({result.score_percentage:.1f}%)"
                    )

                    # Display Ragas metrics if available
                    if result.ragas_metrics_available:
                        judging_mode_label = " (LLM-based judging: OFF)" if QUALITY_TEST_JUDGING == "OFF" else ""
                        content.append(f"\n**Ragas Metrics{judging_mode_label}:**")

                        # Quote Precision
                        if result.quote_precision is not None:
                            content.append(f"- **Quote Precision:** {result.quote_precision:.3f}")
                            if result.quote_precision_feedback:
                                # Indent feedback for better readability
                                feedback_lines = result.quote_precision_feedback.split("\n")
                                for line in feedback_lines:
                                    if line.strip():
                                        content.append(f"  {line}")

                        # Quote Recall
                        if result.quote_recall is not None:
                            content.append(f"- **Quote Recall:** {result.quote_recall:.3f}")
                            if result.quote_recall_feedback:
                                feedback_lines = result.quote_recall_feedback.split("\n")
                                for line in feedback_lines:
                                    if line.strip():
                                        content.append(f"  {line}")

                        # Quote Faithfulness
                        if result.quote_faithfulness is not None:
                            content.append(
                                f"- **Quote Faithfulness:** {result.quote_faithfulness:.3f}"
                            )

                            # Show quotes with faithfulness < 1.0 if detailed scores available
                            if (result.quote_faithfulness_details and
                                result.llm_quotes_structured and
                                any(score < 1.0 for score in result.quote_faithfulness_details.values())):

                                # Build mapping from chunk_id to quote text
                                chunk_id_to_quote = {
                                    q.get("chunk_id"): q.get("quote_text", "")
                                    for q in result.llm_quotes_structured
                                }

                                # List quotes with faithfulness < 1.0
                                imperfect_quotes = [
                                    (chunk_id, score, chunk_id_to_quote.get(chunk_id, "Unknown quote"))
                                    for chunk_id, score in result.quote_faithfulness_details.items()
                                    if score < 1.0
                                ]

                                if imperfect_quotes:
                                    content.append("  **Quotes with issues:**")
                                    for _chunk_id, score, quote_text in sorted(imperfect_quotes, key=lambda x: x[1]):
                                        # Truncate long quotes
                                        quote_display = quote_text[:150] + "..." if len(quote_text) > 150 else quote_text
                                        content.append(f"  - Score: {score:.2f} - \"{quote_display}\"")

                            if result.quote_faithfulness_feedback:
                                feedback_lines = result.quote_faithfulness_feedback.split("\n")
                                for line in feedback_lines:
                                    if line.strip():
                                        content.append(f"  {line}")

                        # Explanation Faithfulness
                        if result.explanation_faithfulness is not None:
                            content.append(
                                f"- **Explanation Faithfulness:** {result.explanation_faithfulness:.3f}"
                            )
                            if result.explanation_faithfulness_feedback:
                                feedback_lines = result.explanation_faithfulness_feedback.split(
                                    "\n"
                                )
                                for line in feedback_lines:
                                    if line.strip():
                                        content.append(f"  {line}")

                        # Answer Correctness
                        if result.answer_correctness is not None:
                            content.append(
                                f"- **Answer Correctness:** {result.answer_correctness:.3f}"
                            )

                            # Show answer details whenever overall score < 1.0 (includes mismatched keys)
                            if result.answer_correctness_details and result.answer_correctness < 1.0:
                                # Show all answers when overall score is imperfect
                                # (helps diagnose key mismatches and scoring issues)
                                for answer_key, score in sorted(result.answer_correctness_details.items(), key=lambda x: x[1]):
                                    content.append(f"  - **{answer_key}**: {score:.2f}")

                            if result.answer_correctness_feedback:
                                feedback_lines = result.answer_correctness_feedback.split("\n")
                                for line in feedback_lines:
                                    if line.strip():
                                        content.append(f"  {line}")

                        # Custom Judge Unified Feedback (when QUALITY_TEST_JUDGING == "CUSTOM")
                        if result.feedback and QUALITY_TEST_JUDGING == "CUSTOM":
                            content.append("\n**Custom Judge Feedback:**")
                            feedback_lines = result.feedback.split("\n")
                            for line in feedback_lines:
                                if line.strip():
                                    content.append(f"  {line}")

                        if result.ragas_error:
                            content.append(f"- **Ragas Error:** {result.ragas_error}")
                        content.append("")  # Blank line after metrics

                    # content.append(f"- **Tokens:** {result.tokens}")
                    content.append(f"- **Cost:** ${result.total_cost_usd:.4f}")
                    if (
                        result.multi_hop_cost_usd > 0
                        or result.ragas_cost_usd > 0
                        or result.embedding_cost_usd > 0
                    ):
                        content.append(f"  - Main LLM: ${result.cost_usd:.4f}")
                        if result.multi_hop_cost_usd > 0:
                            content.append(f"  - Multi-hop: ${result.multi_hop_cost_usd:.4f}")
                        if result.ragas_cost_usd > 0:
                            content.append(f"  - LLM Judge: ${result.ragas_cost_usd:.4f}")
                        if result.embedding_cost_usd > 0:
                            content.append(f"  - Embeddings: ${result.embedding_cost_usd:.4f}")
                    content.append(f"- **Generation Time:** {result.generation_time_seconds:.2f}s")
                    content.append(
                        f"- **Output File:** [{result.output_filename}](./{result.output_filename})"
                    )

                    if result.error:
                        content.append(f"- **Generation Error:** {result.error}")

                    # Show evaluation errors prominently if they occurred outside the metrics block
                    if result.ragas_error and not result.ragas_metrics_available:
                        content.append(f"- **Evaluation Error:** {result.ragas_error}")

                    # Legacy requirements (for backward compatibility during migration)
                    if result.requirements:
                        content.append("\n**Requirements (Legacy):**")
                        for req in result.requirements:
                            # Build requirement line
                            req_line = f"- {req.emoji} **{req.title}** ({req.type}): {req.achieved_score}/{req.max_score} points - {req.description}"
                            content.append(req_line)

                            # Add judge response as sub-bullet for LLM requirements
                            if req.type == "llm" and hasattr(req, "outcome") and req.outcome:
                                content.append(f"  - *{req.outcome}*")

                    content.append("")  # Add spacing between runs

        return "\n".join(content)

    def _get_individual_test_result_section(
        self, result: IndividualTestResult, include_header: bool = True
    ) -> str:
        """Generate individual test result section (legacy method, kept for compatibility)."""
        content = []

        if include_header:
            content.extend(
                [
                    f"\n### {result.test_id}",
                    f"\n**Model:** {result.model}",
                    f"**Query:** {result.query}",
                    f"**Status:** {'Passed' if result.passed else 'Failed'}",
                ]
            )
        else:
            content.extend(
                [
                    f"\n**Model:** {result.model}",
                    f"**Query:** {result.query}",
                    f"**Status:** {'Passed' if result.passed else 'Failed'}",
                ]
            )

        content.append(
            f"**Score:** {result.score}/{result.max_score} ({result.score_percentage:.1f}%)"
        )

        # Display Ragas metrics if available
        if result.ragas_metrics_available:
            content.append("\n**Ragas Metrics:**")
            if result.quote_precision is not None:
                content.append(f"- Quote Precision: {result.quote_precision:.3f}")
            if result.quote_recall is not None:
                content.append(f"- Quote Recall: {result.quote_recall:.3f}")
            if result.quote_faithfulness is not None:
                content.append(f"- Quote Faithfulness: {result.quote_faithfulness:.3f}")
            if result.explanation_faithfulness is not None:
                content.append(f"- Explanation Faithfulness: {result.explanation_faithfulness:.3f}")
            if result.answer_correctness is not None:
                content.append(f"- Answer Correctness: {result.answer_correctness:.3f}")
            if result.ragas_error:
                content.append(f"- Ragas Error: {result.ragas_error}")
            content.append("")  # Blank line

        if result.error:
            content.append(f"\n**Error:**\n{result.error}")

        content.append(f"**Tokens:** {result.tokens}")

        # Comprehensive cost breakdown
        content.append("\n**Cost Breakdown:**")
        content.append(f"- Main LLM: ${result.cost_usd:.4f}")
        if result.multi_hop_cost_usd > 0:
            content.append(f"- Multi-hop evaluation: ${result.multi_hop_cost_usd:.4f}")
        if result.ragas_cost_usd > 0:
            content.append(f"- Judge evaluation: ${result.ragas_cost_usd:.4f}")
        if result.embedding_cost_usd > 0:
            content.append(f"- Embeddings: ${result.embedding_cost_usd:.4f}")
        content.append(f"- **Total: ${result.total_cost_usd:.4f}**")

        content.append(f"\n**Generation Time:** {result.generation_time_seconds:.2f}s")

        # Legacy requirements (for backward compatibility)
        if result.requirements:
            content.append("\n**Requirements (Legacy):**")
            for req in result.requirements:
                content.append(f"- {req.emoji} {req.title}: {req.description}")

        return "\n".join(content)

    def _write_file(self, path: str, content: str):
        """Writes content to a file."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)

    def get_console_output(self) -> str:
        """Generates a concise summary for printing to the console."""
        # Calculate cost breakdown from all results
        total_main = sum(r.cost_usd for r in self.report.results)
        total_multi_hop = sum(r.multi_hop_cost_usd for r in self.report.results)
        total_judge = sum(r.ragas_cost_usd for r in self.report.results)
        total_embedding = sum(r.embedding_cost_usd for r in self.report.results)

        content = []
        content.append("\n" + "=" * 60)
        content.append("Test Results Summary")
        content.append("=" * 60)
        content.append(f"Total tests: {len(self.report.test_cases)}")
        content.append(f"Total queries: {self.report.total_queries}")
        content.append(f"Total time: {self.report.total_time_seconds:.2f}s")
        content.append(f"Total cost: ${self.report.total_cost_usd:.4f}")

        # Add cost breakdown
        if self.report.total_cost_usd > 0:
            content.append(f"  Main LLM: ${total_main:.4f}")
            content.append(f"  Multi-hop: ${total_multi_hop:.4f}")
            content.append(f"  Judge: ${total_judge:.4f}")
            content.append(f"  Embeddings: ${total_embedding:.4f}")

        # Calculate JSON formatting statistics
        json_formatted_count = sum(1 for r in self.report.results if r.json_formatted)
        total_responses = len([r for r in self.report.results if not r.error])
        json_success_rate = (
            (json_formatted_count / total_responses * 100) if total_responses > 0 else 0
        )

        content.append(
            f"JSON formatted: {json_formatted_count}/{total_responses} ({json_success_rate:.1f}%)"
        )

        # Calculate average quotes per response (for successfully formatted JSON)
        json_results = [r for r in self.report.results if r.json_formatted]
        if json_results:
            avg_quotes = np.mean([r.structured_quotes_count for r in json_results])
            content.append(f"Avg quotes per JSON response: {avg_quotes:.1f}")

        # Display average metrics if available
        results_with_ragas = [r for r in self.report.results if r.ragas_metrics_available]
        if results_with_ragas:
            content.append("")
            judging_mode_label = " (LLM-based judging: OFF)" if QUALITY_TEST_JUDGING == "OFF" else ""
            content.append(f"Average Metrics{judging_mode_label}:")

            quote_precision_vals = [
                r.quote_precision for r in results_with_ragas if r.quote_precision is not None
            ]
            if quote_precision_vals:
                content.append(f"  Quote Precision: {np.mean(quote_precision_vals):.3f}")

            quote_recall_vals = [
                r.quote_recall for r in results_with_ragas if r.quote_recall is not None
            ]
            if quote_recall_vals:
                content.append(f"  Quote Recall: {np.mean(quote_recall_vals):.3f}")

            quote_faithfulness_vals = [
                r.quote_faithfulness for r in results_with_ragas if r.quote_faithfulness is not None
            ]
            if quote_faithfulness_vals:
                content.append(f"  Quote Faithfulness: {np.mean(quote_faithfulness_vals):.3f}")

            explanation_faithfulness_vals = [
                r.explanation_faithfulness
                for r in results_with_ragas
                if r.explanation_faithfulness is not None
            ]
            if explanation_faithfulness_vals:
                content.append(
                    f"  Explanation Faithfulness: {np.mean(explanation_faithfulness_vals):.3f}"
                )

            answer_correctness_vals = [
                r.answer_correctness for r in results_with_ragas if r.answer_correctness is not None
            ]
            if answer_correctness_vals:
                content.append(f"  Answer Correctness: {np.mean(answer_correctness_vals):.3f}")

            content.append("")

        if self.report.is_multi_model or self.report.is_multi_run:
            avg_score = np.mean([r.score_percentage for r in self.report.results])
            content.append(f"Average score: {avg_score:.1f}%")

        content.append("=" * 60)

        if self.report.is_multi_model:
            # Re-using the table generation logic for console
            summaries = list(self.report.per_model_summaries.values())
            headers = ["Model", "Avg Score %", "Avg Time/Query", "Avg Cost/Query"]
            table = [headers]
            for summary in sorted(summaries, key=lambda s: s.avg_score_pct, reverse=True):
                score_std_dev = (
                    f" (±{summary.std_dev_score_pct:.1f})" if self.report.is_multi_run else ""
                )
                time_std_dev = f" (±{summary.std_dev_time:.2f})" if self.report.is_multi_run else ""
                cost_std_dev = (
                    f" (±${summary.std_dev_cost:.4f})" if self.report.is_multi_run else ""
                )
                row = [
                    summary.model_name,
                    f"{summary.avg_score_pct:.1f}%{score_std_dev}",
                    f"{summary.avg_time:.2f}s{time_std_dev}",
                    f"${summary.avg_cost:.4f}{cost_std_dev}",
                ]
                table.append(row)

            # Simple console table formatting
            col_widths = [max(len(str(item)) for item in col) for col in zip(*table, strict=False)]
            for row in table:
                content.append(
                    " | ".join(
                        str(item).ljust(width) for item, width in zip(row, col_widths, strict=False)
                    )
                )

        else:  # Single model view
            for result in self.report.results:
                content.append(
                    f"{result.status_emoji} {result.test_id} [{result.model}]: "
                    f"{result.score}/{result.max_score} "
                    f"({result.generation_time_seconds:.2f}s, ${result.total_cost_usd:.4f})"
                )

        main_report_path = os.path.join(self.report_dir, "report.md")
        content.append(f"\nFull report saved to: {main_report_path}")
        return "\n".join(content)
