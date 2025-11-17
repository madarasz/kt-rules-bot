"""Generate comparison reports and charts for parameter sweeps.

Creates markdown reports and matplotlib charts comparing RAG performance
across different parameter values.
"""

import csv
from datetime import datetime
from pathlib import Path

import numpy as np

from src.lib.logging import get_logger
from tests.rag.reporting.chart_utils import (
    create_heatmap,
    create_multi_line_chart,
)
from tests.rag.sweep_runner import SweepResult

logger = get_logger(__name__)


class ComparisonGenerator:
    """Generates comparison reports for parameter sweep results."""

    def generate_parameter_sweep_report(
        self,
        sweep_results: list[SweepResult],
        param_name: str,
        output_dir: Path,
    ) -> None:
        """Generate full comparison report for single parameter sweep.

        Args:
            sweep_results: List of sweep results
            param_name: Name of swept parameter
            output_dir: Directory to save reports
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        charts_dir = output_dir / "charts"
        charts_dir.mkdir(exist_ok=True)

        logger.info(
            "generating_parameter_sweep_report",
            param_name=param_name,
            num_configs=len(sweep_results),
            output_dir=str(output_dir),
        )

        # Extract parameter values and metrics
        param_values = [getattr(result.config, param_name) for result in sweep_results]

        # Generate CSV export
        self._generate_csv(sweep_results, param_name, output_dir / "comparison_metrics.csv")

        # Generate individual metric charts
        self._generate_metric_charts(
            sweep_results=sweep_results,
            param_values=param_values,
            param_name=param_name,
            charts_dir=charts_dir,
        )

        # Generate multi-metric comparison chart
        self._generate_multi_metric_chart(
            sweep_results=sweep_results,
            param_values=param_values,
            param_name=param_name,
            charts_dir=charts_dir,
        )

        # Generate markdown report
        self._generate_markdown_report(
            sweep_results=sweep_results,
            param_values=param_values,
            param_name=param_name,
            output_dir=output_dir,
            charts_dir=charts_dir,
        )

        logger.info(
            "parameter_sweep_report_generated",
            output_dir=str(output_dir),
        )

    def generate_grid_search_report(
        self,
        sweep_results: list[SweepResult],
        param_grid: dict[str, list],
        output_dir: Path,
    ) -> None:
        """Generate full comparison report for grid search.

        Args:
            sweep_results: List of sweep results
            param_grid: Dictionary of parameter names to value lists
            output_dir: Directory to save reports
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        charts_dir = output_dir / "charts"
        charts_dir.mkdir(exist_ok=True)

        logger.info(
            "generating_grid_search_report",
            num_configs=len(sweep_results),
            output_dir=str(output_dir),
        )

        # Generate CSV export
        self._generate_grid_csv(sweep_results, param_grid, output_dir / "grid_results.csv")

        # Generate heatmaps for 2D grid searches
        if len(param_grid) == 2:
            self._generate_heatmaps(
                sweep_results=sweep_results,
                param_grid=param_grid,
                charts_dir=charts_dir,
            )

        # Generate markdown report
        self._generate_grid_markdown_report(
            sweep_results=sweep_results,
            param_grid=param_grid,
            output_dir=output_dir,
            charts_dir=charts_dir,
        )

        logger.info(
            "grid_search_report_generated",
            output_dir=str(output_dir),
        )

    def _generate_csv(
        self,
        sweep_results: list[SweepResult],
        param_name: str,
        output_path: Path,
    ) -> None:
        """Generate CSV file with all metrics for each parameter value."""
        with open(output_path, 'w', newline='') as csvfile:
            fieldnames = [
                param_name,
                'mean_ragas_context_precision',
                'mean_ragas_context_recall',
                'std_dev_ragas_context_precision',
                'std_dev_ragas_context_recall',
                'total_time_seconds',
                'avg_retrieval_time_seconds',
                'total_cost_usd',
            ]

            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for result in sweep_results:
                param_value = getattr(result.config, param_name)
                writer.writerow({
                    param_name: param_value,
                    'mean_ragas_context_precision': result.summary.mean_ragas_context_precision,
                    'mean_ragas_context_recall': result.summary.mean_ragas_context_recall,
                    'std_dev_ragas_context_precision': result.summary.std_dev_ragas_context_precision,
                    'std_dev_ragas_context_recall': result.summary.std_dev_ragas_context_recall,
                    'total_time_seconds': result.summary.total_time_seconds,
                    'avg_retrieval_time_seconds': result.summary.avg_retrieval_time_seconds,
                    'total_cost_usd': result.summary.total_cost_usd,
                })

        logger.info("csv_generated", output_path=str(output_path))

    def _generate_grid_csv(
        self,
        sweep_results: list[SweepResult],
        param_grid: dict[str, list],
        output_path: Path,
    ) -> None:
        """Generate CSV file for grid search results."""
        param_names = list(param_grid.keys())

        with open(output_path, 'w', newline='') as csvfile:
            fieldnames = param_names + [
                'mean_ragas_context_precision',
                'mean_ragas_context_recall',
                'total_time_seconds',
                'total_cost_usd',
            ]

            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for result in sweep_results:
                row = {}
                for param_name in param_names:
                    row[param_name] = getattr(result.config, param_name)

                row.update({
                    'mean_ragas_context_precision': result.summary.mean_ragas_context_precision,
                    'mean_ragas_context_recall': result.summary.mean_ragas_context_recall,
                    'total_time_seconds': result.summary.total_time_seconds,
                    'total_cost_usd': result.summary.total_cost_usd,
                })

                writer.writerow(row)

        logger.info("grid_csv_generated", output_path=str(output_path))

    def _generate_metric_charts(
        self,
        sweep_results: list[SweepResult],
        param_values: list,
        param_name: str,
        charts_dir: Path,
    ) -> None:
        """Generate individual line charts for each metric."""
        # Ragas Metrics - combined chart
        if sweep_results[0].summary.mean_ragas_context_precision is not None:
            ragas_cp_values = [r.summary.mean_ragas_context_precision for r in sweep_results]
            ragas_cr_values = [r.summary.mean_ragas_context_recall for r in sweep_results]

            # Combined Ragas metrics chart (both lines)
            create_multi_line_chart(
                x_values=param_values,
                y_values_dict={
                    'Context Precision': ragas_cp_values,
                    'Context Recall': ragas_cr_values,
                },
                x_label=param_name,
                y_label='Ragas Score',
                title=f'Ragas Metrics vs {param_name}',
                output_path=charts_dir / 'ragas_metrics_comparison.png',
            )

        logger.info("metric_charts_generated", charts_dir=str(charts_dir))

    def _generate_multi_metric_chart(
        self,
        sweep_results: list[SweepResult],
        param_values: list,
        param_name: str,
        charts_dir: Path,
    ) -> None:
        """Generate grouped bar chart comparing Ragas metrics."""
        # This method is kept for backwards compatibility but now only handles Ragas
        # The actual Ragas chart is already generated in _generate_metric_charts
        logger.info("multi_metric_chart_skipped_ragas_already_generated")

    def _generate_heatmaps(
        self,
        sweep_results: list[SweepResult],
        param_grid: dict[str, list],
        charts_dir: Path,
    ) -> None:
        """Generate heatmaps for 2D grid search."""
        param_names = list(param_grid.keys())
        param1_name, param2_name = param_names[0], param_names[1]
        param1_values = param_grid[param1_name]
        param2_values = param_grid[param2_name]

        # Create data matrices for Ragas metrics only
        metrics = {}
        if sweep_results[0].summary.mean_ragas_context_precision is not None:
            metrics['ragas_context_precision'] = ('Ragas Context Precision', 'ragas_context_precision_heatmap.png')
            metrics['ragas_context_recall'] = ('Ragas Context Recall', 'ragas_context_recall_heatmap.png')

        for metric_key, (metric_label, filename) in metrics.items():
            data = np.zeros((len(param2_values), len(param1_values)))

            for result in sweep_results:
                param1_val = getattr(result.config, param1_name)
                param2_val = getattr(result.config, param2_name)

                i = param2_values.index(param2_val)
                j = param1_values.index(param1_val)

                metric_value = getattr(result.summary, f'mean_{metric_key}')
                data[i, j] = metric_value

            create_heatmap(
                data=data,
                x_labels=[str(v) for v in param1_values],
                y_labels=[str(v) for v in param2_values],
                x_param_name=param1_name,
                y_param_name=param2_name,
                value_label=metric_label,
                title=f'{metric_label} Grid Search: {param1_name} vs {param2_name}',
                output_path=charts_dir / filename,
                vmin=0.0,
                vmax=1.0,
            )

        logger.info("heatmaps_generated", charts_dir=str(charts_dir))

    def _generate_markdown_report(
        self,
        sweep_results: list[SweepResult],
        param_values: list,
        param_name: str,
        output_dir: Path,
        charts_dir: Path,
    ) -> None:
        """Generate markdown comparison report."""
        content = []

        # Header
        content.append(f"# RAG Parameter Sweep Report: {param_name}")
        content.append("")
        content.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        content.append("")
        content.append(f"**Parameter**: {param_name}")
        content.append(f"**Values tested**: {param_values}")
        content.append(f"**Configurations**: {len(sweep_results)}")
        content.append("")

        # Overall statistics
        total_time = sum(r.total_time for r in sweep_results)
        total_cost = sum(r.summary.total_cost_usd for r in sweep_results)
        content.append("## Overall Statistics")
        content.append("")
        content.append(f"- **Total sweep time**: {total_time:.2f}s ({total_time/60:.2f} minutes)")
        content.append(f"- **Total sweep cost**: ${total_cost:.6f}")
        content.append(f"- **Average time per configuration**: {total_time/len(sweep_results):.2f}s")
        content.append(f"- **Average cost per configuration**: ${total_cost/len(sweep_results):.6f}")
        content.append("")

        # Summary table
        content.append("## Summary Table")
        content.append("")

        # Check if Ragas metrics are available
        has_ragas = sweep_results[0].summary.mean_ragas_context_precision is not None

        if has_ragas:
            content.append(f"| {param_name} | Context Precision | Context Recall | Avg Time (s) | Cost (USD) |")
            content.append("|" + "-" * 12 + "|" + "-" * 19 + "|" + "-" * 16 + "|" + "-" * 14 + "|" + "-" * 12 + "|")

            for param_val, result in zip(param_values, sweep_results, strict=False):
                s = result.summary
                content.append(
                    f"| {param_val} | {s.mean_ragas_context_precision:.3f} | {s.mean_ragas_context_recall:.3f} | "
                    f"{s.avg_retrieval_time_seconds:.3f} | ${s.total_cost_usd:.6f} |"
                )
        else:
            content.append(f"| {param_name} | Avg Time (s) | Cost (USD) |")
            content.append("|" + "-" * 12 + "|" + "-" * 14 + "|" + "-" * 12 + "|")

            for param_val, result in zip(param_values, sweep_results, strict=False):
                s = result.summary
                content.append(
                    f"| {param_val} | {s.avg_retrieval_time_seconds:.3f} | ${s.total_cost_usd:.6f} |"
                )

        content.append("")

        # Best configuration (based on Ragas Context Precision)
        if has_ragas:
            best_idx = max(range(len(sweep_results)), key=lambda i: sweep_results[i].summary.mean_ragas_context_precision)
        else:
            best_idx = 0  # Fallback if no metrics available

        best_result = sweep_results[best_idx]
        best_param_val = param_values[best_idx]

        content.append("## Best Configuration")
        content.append("")
        content.append(f"**{param_name}**: {best_param_val}")
        content.append("")

        if has_ragas:
            content.append("**Ragas Metrics:**")
            content.append(f"- Context Precision: {best_result.summary.mean_ragas_context_precision:.3f}")
            content.append(f"- Context Recall: {best_result.summary.mean_ragas_context_recall:.3f}")
            content.append("")

        # Charts
        content.append("## Charts")
        content.append("")

        if has_ragas:
            content.append("### Ragas Metrics Comparison")
            content.append(f"![Ragas Metrics vs {param_name}](charts/ragas_metrics_comparison.png)")

        # Recommendations
        content.append("## Recommendations")
        content.append("")
        if has_ragas:
            content.append(f"Based on Ragas Context Precision, the optimal value for **{param_name}** is **{best_param_val}**.")
            content.append("")
            content.append("**Ragas Metrics:**")
            content.append("- **Context Precision**: Proportion of retrieved contexts containing ground truth information")
            content.append("- **Context Recall**: Proportion of ground truth information found in retrieved contexts")
        else:
            content.append(f"Optimal value for **{param_name}**: **{best_param_val}**")
        content.append("")

        # Write report
        report_path = output_dir / "comparison_report.md"
        with open(report_path, 'w') as f:
            f.write("\n".join(content))

        logger.info("markdown_report_generated", report_path=str(report_path))

    def _generate_grid_markdown_report(
        self,
        sweep_results: list[SweepResult],
        param_grid: dict[str, list],
        output_dir: Path,
        charts_dir: Path,
    ) -> None:
        """Generate markdown report for grid search."""
        param_names = list(param_grid.keys())
        content = []

        # Header
        content.append("# RAG Grid Search Report")
        content.append("")
        content.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        content.append("")
        content.append(f"**Parameters**: {', '.join(param_names)}")
        content.append(f"**Total configurations**: {len(sweep_results)}")
        content.append("")

        # Overall statistics
        total_time = sum(r.total_time for r in sweep_results)
        total_cost = sum(r.summary.total_cost_usd for r in sweep_results)
        content.append("## Overall Statistics")
        content.append("")
        content.append(f"- **Total grid search time**: {total_time:.2f}s ({total_time/60:.2f} minutes)")
        content.append(f"- **Total grid search cost**: ${total_cost:.6f}")
        content.append(f"- **Average time per configuration**: {total_time/len(sweep_results):.2f}s")
        content.append(f"- **Average cost per configuration**: ${total_cost/len(sweep_results):.6f}")
        content.append("")

        # Best configuration (based on Ragas Context Precision if available)
        has_ragas = sweep_results[0].summary.mean_ragas_context_precision is not None
        if has_ragas:
            best_idx = max(range(len(sweep_results)), key=lambda i: sweep_results[i].summary.mean_ragas_context_precision)
        else:
            best_idx = 0

        best_result = sweep_results[best_idx]

        content.append("## Best Configuration")
        content.append("")
        for param_name in param_names:
            param_val = getattr(best_result.config, param_name)
            content.append(f"- **{param_name}**: {param_val}")
        content.append("")

        if has_ragas:
            content.append("**Ragas Metrics:**")
            content.append(f"- Context Precision: {best_result.summary.mean_ragas_context_precision:.3f}")
            content.append(f"- Context Recall: {best_result.summary.mean_ragas_context_recall:.3f}")
            content.append("")

        # Heatmaps (if 2D grid)
        if len(param_names) == 2 and has_ragas:
            content.append("## Heatmaps")
            content.append("")
            content.append("### Ragas Context Precision Heatmap")
            content.append("![Ragas Context Precision Heatmap](charts/ragas_context_precision_heatmap.png)")
            content.append("")
            content.append("### Ragas Context Recall Heatmap")
            content.append("![Ragas Context Recall Heatmap](charts/ragas_context_recall_heatmap.png)")
            content.append("")

        # Full results table
        content.append("## All Configurations")
        content.append("")

        # Build table header with Ragas columns if available
        if has_ragas:
            header = "| " + " | ".join(param_names) + " | Context Prec | Context Rec | Time (s) | Cost (USD) |"
            separator = "|" + "|".join(["-" * 12 for _ in range(len(param_names) + 4)]) + "|"

            content.append(header)
            content.append(separator)

            for result in sorted(sweep_results, key=lambda r: r.summary.mean_ragas_context_precision, reverse=True):
                row = "| "
                for param_name in param_names:
                    row += f"{getattr(result.config, param_name)} | "
                row += (
                    f"{result.summary.mean_ragas_context_precision:.3f} | {result.summary.mean_ragas_context_recall:.3f} | "
                    f"{result.summary.avg_retrieval_time_seconds:.3f} | ${result.summary.total_cost_usd:.6f} |"
                )
                content.append(row)
        else:
            header = "| " + " | ".join(param_names) + " | Time (s) | Cost (USD) |"
            separator = "|" + "|".join(["-" * 12 for _ in range(len(param_names) + 2)]) + "|"

            content.append(header)
            content.append(separator)

            for result in sweep_results:
                row = "| "
                for param_name in param_names:
                    row += f"{getattr(result.config, param_name)} | "
                row += f"{result.summary.avg_retrieval_time_seconds:.3f} | ${result.summary.total_cost_usd:.6f} |"
                content.append(row)

        content.append("")

        # Write report
        report_path = output_dir / "comparison_report.md"
        with open(report_path, 'w') as f:
            f.write("\n".join(content))

        logger.info("grid_markdown_report_generated", report_path=str(report_path))
