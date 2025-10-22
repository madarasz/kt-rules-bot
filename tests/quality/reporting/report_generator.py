"""Generates markdown reports for quality tests."""

import os
from typing import List, Optional, Dict
from collections import defaultdict
import numpy as np
from tests.quality.reporting.report_models import (
    QualityReport,
    IndividualTestResult,
    ModelSummary,
)
from tests.quality.reporting.chart_generator import ChartGenerator


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
        if self.report.is_multi_run and self.report.is_multi_test_case and self.report.is_multi_model:
            for test_id, test_case_report in self.report.per_test_case_reports.items():
                for model_name in self.report.models:
                    results = [r for r in test_case_report.results if r.model == model_name]
                    if results:
                        path = os.path.join(self.report_dir, f"report_{test_id}_{model_name}.md")
                        content = self._generate_test_case_model_report(test_id, model_name, results)
                        self._write_file(path, content)

        return main_report_path

    def _generate_main_report(self) -> str:
        """Generates the content for the main report.md file."""
        content = []
        content.append(self._get_overall_report_header())

        if self.report.is_multi_model:
            content.append("\n" + self._get_model_comparison_table())

        if self.report.is_multi_run and self.report.is_multi_test_case and not self.report.is_multi_model:
            content.append(self._get_test_case_summary_table())

        # Link to sub-reports or show individual results
        if self.report.is_multi_test_case and self.report.is_multi_model:
            content.append("\n## Detailed Test Case Reports")
            for test_id in self.report.test_cases:
                # Calculate average score for this test case
                if test_id in self.report.per_test_case_reports:
                    test_case_report = self.report.per_test_case_reports[test_id]
                    if test_case_report.results:
                        avg_score = sum(r.score_percentage for r in test_case_report.results) / len(test_case_report.results)
                        content.append(f"- [Report for {test_id}](./report_{test_id}.md) - {avg_score:.1f}%")
                    else:
                        content.append(f"- [Report for {test_id}](./report_{test_id}.md)")
                else:
                    content.append(f"- [Report for {test_id}](./report_{test_id}.md)")
        else:
            content.append("\n## Individual Test Results")
            content.append(self._get_grouped_individual_results(self.report.results))

        return "\n".join(content)

    def _generate_test_case_report(self, test_id: str, results: List[IndividualTestResult]) -> str:
        """Generates content for a per-test-case report."""
        content = [f"# Test Case Report: {test_id}\n"]
        
        # Summary and comparison table for this test case
        content.append("## Summary")
        # Simplified model comparison for this specific test case
        # This requires aggregating results just for this test case
        model_summaries_for_test_case: List[ModelSummary] = []
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
                 content.append(f"- [Report for {test_id} on {model_name}](./report_{test_id}_{model_name}.md)")
        else:
            content.append(self._get_grouped_individual_results(results))

        return "\n".join(content)

    def _generate_test_case_model_report(self, test_id: str, model_name: str, results: List[IndividualTestResult]) -> str:
        """Generates a report for a specific test case and model, showing all runs."""
        content = [f"# Report for {test_id} on {model_name}\n"]
        
        summary = ModelSummary(model_name, results)
        content.append("## Summary of Runs")
        content.append(f"- **Average Score:** {summary.avg_score_pct:.2f}% (±{summary.std_dev_score_pct:.2f})")
        content.append(f"- **Average Time:** {summary.avg_time:.2f}s (±{summary.std_dev_time:.2f})")
        content.append(f"- **Average Cost:** ${summary.avg_cost:.4f} (±${summary.std_dev_cost:.4f})")

        content.append("\n## Individual Run Results")
        for i, result in enumerate(results):
            content.append(f"\n### Run #{i+1}")
            content.append(self._get_individual_test_result_section(result, include_header=False))
            
        return "\n".join(content)

    def _get_overall_report_header(self) -> str:
        """Builds the overall report header string."""
        header = [
            "# Quality Test Report",
            f"- **Total time**: {self.report.total_time_seconds // 60:.0f}m {self.report.total_time_seconds % 60:.2f}s",
            f"- **Total cost**: ${self.report.total_cost_usd:.4f}",
            f"- **Total queries**: {self.report.total_queries}",
        ]
        if self.report.is_multi_model or self.report.is_multi_run:
            best_model = max(self.report.per_model_summaries.values(), key=lambda s: s.avg_score_pct)
            header.append(f"- **Best score**: {best_model.avg_score_pct:.1f}% - {best_model.model_name}")
        
        header.append(f"- **Test cases**: {', '.join(self.report.test_cases)}")
        
        if self.report.chart_path:
            chart_name = os.path.basename(self.report.chart_path)
            header.append(f"\n![Overall Chart](./{chart_name})")

        return "\n".join(header)

    def _get_model_comparison_table(self, summaries: Optional[List[ModelSummary]] = None) -> str:
        """Builds a markdown table comparing models."""
        if summaries is None:
            summaries = list(self.report.per_model_summaries.values())

        headers = ["Model", "Avg Score %", "Avg Time/Query (s)", "Avg Cost/Query ($)"]
        table = [
            "| " + " | ".join(headers) + " |",
            "|-" + "-|-".join(["-" * len(h) for h in headers]) + "-|",
        ]
        for summary in sorted(summaries, key=lambda s: s.avg_score_pct, reverse=True):
            score_std_dev = f" (±{summary.std_dev_score_pct:.1f})" if self.report.is_multi_run else ""
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
            avg_cost = np.mean([r.cost_usd for r in test_case_report.results])
            row = [
                test_id,
                f"{avg_score:.1f}% (±{std_dev_score:.1f})",
                f"{avg_time:.2f}",
                f"${avg_cost:.4f}",
            ]
            table.append("| " + " | ".join(row) + " |")
        return "\n## Summary per Test Case\n" + "\n".join(table)

    def _get_grouped_individual_results(self, results: List[IndividualTestResult]) -> str:
        """Group test results by test_id with models as subheaders."""
        
        # Group results by test case ID
        grouped_results: Dict[str, List[IndividualTestResult]] = defaultdict(list)
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
            model_results: Dict[str, List[IndividualTestResult]] = defaultdict(list)
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
                    
                    # Status with emoji - skull for errors, warning for partial scores
                    if result.error:
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
                    content.append(f"- **Score:** {result.score}/{result.max_score} ({result.score_percentage:.1f}%)")
                    content.append(f"- **Tokens:** {result.tokens}")
                    content.append(f"- **Cost:** ${result.cost_usd:.4f}")
                    content.append(f"- **Generation Time:** {result.generation_time_seconds:.2f}s")
                    content.append(f"- **Output File:** [{result.output_filename}](./{result.output_filename})")
                    
                    if result.error:
                        content.append(f"- **Error:** {result.error}")
                    
                    # Requirements per model per run
                    if result.requirements:
                        content.append(f"\n**Requirements:**")
                        for req in result.requirements:
                            # Build requirement line
                            req_line = f"- {req.emoji} **{req.title}** ({req.type}): {req.achieved_score}/{req.max_score} points - {req.description}"
                            content.append(req_line)
                            
                            # Add judge response as sub-bullet for LLM requirements
                            if req.type == "llm" and hasattr(req, 'outcome') and req.outcome:
                                content.append(f"  - *{req.outcome}*")
                    
                    content.append("")  # Add spacing between runs
        
        return "\n".join(content)

    def _get_individual_test_result_section(self, result: IndividualTestResult, include_header: bool = True) -> str:
        """Generate individual test result section (legacy method, kept for compatibility)."""
        content = []
        
        if include_header:
            content.extend([
                f"\n### {result.test_id}",
                f"\n**Model:** {result.model}",
                f"**Query:** {result.query}",
                f"**Status:** {'Passed' if result.passed else 'Failed'}"
            ])
        else:
            content.extend([
                f"\n**Model:** {result.model}",
                f"**Query:** {result.query}",
                f"**Status:** {'Passed' if result.passed else 'Failed'}"
            ])
        
        content.append(f"**Score:** {result.score}/{result.max_score} ({result.score_percentage:.1f}%)")
        
        if result.error:
            content.append(f"\n**Error:**\n{result.error}")
        
        content.append(f"**Tokens:** {result.tokens}")
        content.append(f"**Cost:** ${result.cost_usd:.4f}")
        content.append(f"**Generation Time:** {result.generation_time_seconds:.2f}s")
        
        # Add requirements check
        if result.requirements:
            content.append("\n**Requirements:**")
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
        content = []
        content.append("\n" + "=" * 60)
        content.append("Test Results Summary")
        content.append("=" * 60)
        content.append(f"Total tests: {len(self.report.test_cases)}")
        content.append(f"Total queries: {self.report.total_queries}")
        content.append(f"Total time: {self.report.total_time_seconds:.2f}s")
        content.append(f"Total cost: ${self.report.total_cost_usd:.4f}")

        # Calculate JSON formatting statistics
        json_formatted_count = sum(1 for r in self.report.results if r.json_formatted)
        total_responses = len([r for r in self.report.results if not r.error])
        json_success_rate = (json_formatted_count / total_responses * 100) if total_responses > 0 else 0

        content.append(f"JSON formatted: {json_formatted_count}/{total_responses} ({json_success_rate:.1f}%)")

        # Calculate average quotes per response (for successfully formatted JSON)
        json_results = [r for r in self.report.results if r.json_formatted]
        if json_results:
            avg_quotes = np.mean([r.structured_quotes_count for r in json_results])
            content.append(f"Avg quotes per JSON response: {avg_quotes:.1f}")

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
                score_std_dev = f" (±{summary.std_dev_score_pct:.1f})" if self.report.is_multi_run else ""
                time_std_dev = f" (±{summary.std_dev_time:.2f})" if self.report.is_multi_run else ""
                cost_std_dev = f" (±${summary.std_dev_cost:.4f})" if self.report.is_multi_run else ""
                row = [
                    summary.model_name,
                    f"{summary.avg_score_pct:.1f}%{score_std_dev}",
                    f"{summary.avg_time:.2f}s{time_std_dev}",
                    f"${summary.avg_cost:.4f}{cost_std_dev}",
                ]
                table.append(row)
            
            # Simple console table formatting
            col_widths = [max(len(str(item)) for item in col) for col in zip(*table)]
            for row in table:
                content.append(" | ".join(str(item).ljust(width) for item, width in zip(row, col_widths)))

        else: # Single model view
            for result in self.report.results:
                content.append(
                    f"{result.status_emoji} {result.test_id} [{result.model}]: "
                    f"{result.score}/{result.max_score} "
                    f"({result.generation_time_seconds:.2f}s, ${result.cost_usd:.4f})"
                )
        
        main_report_path = os.path.join(self.report_dir, "report.md")
        content.append(f"\nFull report saved to: {main_report_path}")
        return "\n".join(content)
