"""Generate comparison reports and charts for parameter sweeps.

Creates markdown reports and matplotlib charts comparing RAG performance
across different parameter values.
"""

from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime
import csv
import numpy as np

from tests.rag.sweep_runner import SweepResult, ParameterConfig
from tests.rag.reporting.chart_utils import (
    create_line_chart,
    create_multi_line_chart,
    create_grouped_bar_chart,
    create_heatmap,
)
from src.lib.logging import get_logger

logger = get_logger(__name__)


class ComparisonGenerator:
    """Generates comparison reports for parameter sweep results."""

    def generate_parameter_sweep_report(
        self,
        sweep_results: List[SweepResult],
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
        sweep_results: List[SweepResult],
        param_grid: Dict[str, List],
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
        sweep_results: List[SweepResult],
        param_name: str,
        output_path: Path,
    ) -> None:
        """Generate CSV file with all metrics for each parameter value."""
        with open(output_path, 'w', newline='') as csvfile:
            fieldnames = [
                param_name,
                'mean_map',
                'mean_recall_at_5',
                'mean_recall_at_10',
                'mean_precision_at_3',
                'mean_precision_at_5',
                'mean_mrr',
                'std_dev_map',
                'std_dev_recall_at_5',
                'std_dev_precision_at_3',
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
                    'mean_map': result.summary.mean_map,
                    'mean_recall_at_5': result.summary.mean_recall_at_5,
                    'mean_recall_at_10': result.summary.mean_recall_at_10,
                    'mean_precision_at_3': result.summary.mean_precision_at_3,
                    'mean_precision_at_5': result.summary.mean_precision_at_5,
                    'mean_mrr': result.summary.mean_mrr,
                    'std_dev_map': result.summary.std_dev_map,
                    'std_dev_recall_at_5': result.summary.std_dev_recall_at_5,
                    'std_dev_precision_at_3': result.summary.std_dev_precision_at_3,
                    'total_time_seconds': result.summary.total_time_seconds,
                    'avg_retrieval_time_seconds': result.summary.avg_retrieval_time_seconds,
                    'total_cost_usd': result.summary.total_cost_usd,
                })

        logger.info("csv_generated", output_path=str(output_path))

    def _generate_grid_csv(
        self,
        sweep_results: List[SweepResult],
        param_grid: Dict[str, List],
        output_path: Path,
    ) -> None:
        """Generate CSV file for grid search results."""
        param_names = list(param_grid.keys())

        with open(output_path, 'w', newline='') as csvfile:
            fieldnames = param_names + [
                'mean_map',
                'mean_recall_at_5',
                'mean_recall_at_10',
                'mean_precision_at_3',
                'mean_precision_at_5',
                'mean_mrr',
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
                    'mean_map': result.summary.mean_map,
                    'mean_recall_at_5': result.summary.mean_recall_at_5,
                    'mean_recall_at_10': result.summary.mean_recall_at_10,
                    'mean_precision_at_3': result.summary.mean_precision_at_3,
                    'mean_precision_at_5': result.summary.mean_precision_at_5,
                    'mean_mrr': result.summary.mean_mrr,
                    'total_time_seconds': result.summary.total_time_seconds,
                    'total_cost_usd': result.summary.total_cost_usd,
                })

                writer.writerow(row)

        logger.info("grid_csv_generated", output_path=str(output_path))

    def _generate_metric_charts(
        self,
        sweep_results: List[SweepResult],
        param_values: List,
        param_name: str,
        charts_dir: Path,
    ) -> None:
        """Generate individual line charts for each metric."""
        # MAP
        map_values = [r.summary.mean_map for r in sweep_results]
        map_errors = [r.summary.std_dev_map for r in sweep_results] if sweep_results[0].summary.std_dev_map > 0 else None

        create_line_chart(
            x_values=param_values,
            y_values=map_values,
            x_label=param_name,
            y_label='MAP Score',
            title=f'Mean Average Precision vs {param_name}',
            output_path=charts_dir / 'map_comparison.png',
            y_errors=map_errors,
            y_min=0.0,
            y_max=1.0,
        )

        # Recall@5
        recall5_values = [r.summary.mean_recall_at_5 for r in sweep_results]
        recall5_errors = [r.summary.std_dev_recall_at_5 for r in sweep_results] if sweep_results[0].summary.std_dev_recall_at_5 > 0 else None

        create_line_chart(
            x_values=param_values,
            y_values=recall5_values,
            x_label=param_name,
            y_label='Recall@5',
            title=f'Recall@5 vs {param_name}',
            output_path=charts_dir / 'recall5_comparison.png',
            y_errors=recall5_errors,
            y_min=0.0,
            y_max=1.0,
        )

        # Precision@3
        prec3_values = [r.summary.mean_precision_at_3 for r in sweep_results]
        prec3_errors = [r.summary.std_dev_precision_at_3 for r in sweep_results] if sweep_results[0].summary.std_dev_precision_at_3 > 0 else None

        create_line_chart(
            x_values=param_values,
            y_values=prec3_values,
            x_label=param_name,
            y_label='Precision@3',
            title=f'Precision@3 vs {param_name}',
            output_path=charts_dir / 'precision3_comparison.png',
            y_errors=prec3_errors,
            y_min=0.0,
            y_max=1.0,
        )

        # MRR
        mrr_values = [r.summary.mean_mrr for r in sweep_results]

        create_line_chart(
            x_values=param_values,
            y_values=mrr_values,
            x_label=param_name,
            y_label='MRR',
            title=f'Mean Reciprocal Rank vs {param_name}',
            output_path=charts_dir / 'mrr_comparison.png',
            y_min=0.0,
            y_max=1.0,
        )

        # Time
        time_values = [r.summary.avg_retrieval_time_seconds for r in sweep_results]

        create_line_chart(
            x_values=param_values,
            y_values=time_values,
            x_label=param_name,
            y_label='Time (seconds)',
            title=f'Avg Retrieval Time vs {param_name}',
            output_path=charts_dir / 'time_comparison.png',
        )

        # Cost
        cost_values = [r.summary.total_cost_usd for r in sweep_results]

        create_line_chart(
            x_values=param_values,
            y_values=cost_values,
            x_label=param_name,
            y_label='Cost (USD)',
            title=f'Total Cost vs {param_name}',
            output_path=charts_dir / 'cost_comparison.png',
        )

        logger.info("metric_charts_generated", charts_dir=str(charts_dir))

    def _generate_multi_metric_chart(
        self,
        sweep_results: List[SweepResult],
        param_values: List,
        param_name: str,
        charts_dir: Path,
    ) -> None:
        """Generate grouped bar chart comparing multiple metrics."""
        categories = [str(v) for v in param_values]

        values_dict = {
            'MAP': [r.summary.mean_map for r in sweep_results],
            'Recall@5': [r.summary.mean_recall_at_5 for r in sweep_results],
            'Precision@3': [r.summary.mean_precision_at_3 for r in sweep_results],
            'MRR': [r.summary.mean_mrr for r in sweep_results],
        }

        create_grouped_bar_chart(
            categories=categories,
            values_dict=values_dict,
            x_label=param_name,
            y_label='Score',
            title=f'All Metrics Comparison: {param_name}',
            output_path=charts_dir / 'multi_metric_comparison.png',
        )

        logger.info("multi_metric_chart_generated")

    def _generate_heatmaps(
        self,
        sweep_results: List[SweepResult],
        param_grid: Dict[str, List],
        charts_dir: Path,
    ) -> None:
        """Generate heatmaps for 2D grid search."""
        param_names = list(param_grid.keys())
        param1_name, param2_name = param_names[0], param_names[1]
        param1_values = param_grid[param1_name]
        param2_values = param_grid[param2_name]

        # Create data matrices for each metric
        metrics = {
            'map': ('MAP Score', 'map_heatmap.png'),
            'recall_at_5': ('Recall@5', 'recall5_heatmap.png'),
            'precision_at_3': ('Precision@3', 'precision3_heatmap.png'),
            'mrr': ('MRR', 'mrr_heatmap.png'),
        }

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
        sweep_results: List[SweepResult],
        param_values: List,
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
        content.append(f"| {param_name} | MAP | Recall@5 | Precision@3 | MRR | Avg Time (s) |")
        content.append("|" + "-" * 12 + "|" + "-" * 7 + "|" + "-" * 11 + "|" + "-" * 14 + "|" + "-" * 7 + "|" + "-" * 14 + "|")

        for param_val, result in zip(param_values, sweep_results):
            s = result.summary
            content.append(
                f"| {param_val} | {s.mean_map:.3f} | {s.mean_recall_at_5:.3f} | "
                f"{s.mean_precision_at_3:.3f} | {s.mean_mrr:.3f} | "
                f"{s.avg_retrieval_time_seconds:.3f} |"
            )

        content.append("")

        # Best configuration
        best_idx = max(range(len(sweep_results)), key=lambda i: sweep_results[i].summary.mean_map)
        best_result = sweep_results[best_idx]
        best_param_val = param_values[best_idx]

        content.append("## Best Configuration")
        content.append("")
        content.append(f"**{param_name}**: {best_param_val}")
        content.append(f"- MAP: {best_result.summary.mean_map:.3f}")
        content.append(f"- Recall@5: {best_result.summary.mean_recall_at_5:.3f}")
        content.append(f"- Precision@3: {best_result.summary.mean_precision_at_3:.3f}")
        content.append(f"- MRR: {best_result.summary.mean_mrr:.3f}")
        content.append("")

        # Charts
        content.append("## Charts")
        content.append("")
        content.append("### MAP Comparison")
        content.append(f"![MAP vs {param_name}](charts/map_comparison.png)")
        content.append("")
        content.append("### Recall@5 Comparison")
        content.append(f"![Recall@5 vs {param_name}](charts/recall5_comparison.png)")
        content.append("")
        content.append("### Precision@3 Comparison")
        content.append(f"![Precision@3 vs {param_name}](charts/precision3_comparison.png)")
        content.append("")
        content.append("### Multi-Metric Comparison")
        content.append("![All Metrics](charts/multi_metric_comparison.png)")
        content.append("")

        # Recommendations
        content.append("## Recommendations")
        content.append("")
        content.append(f"Based on MAP scores, the optimal value for **{param_name}** is **{best_param_val}**.")
        content.append("")
        content.append("Consider the following trade-offs:")
        content.append("- **MAP**: Overall retrieval quality")
        content.append("- **Recall@5**: Ensures all required chunks are found")
        content.append("- **Precision@3**: Reduces noise in top results")
        content.append("")

        # Write report
        report_path = output_dir / "comparison_report.md"
        with open(report_path, 'w') as f:
            f.write("\n".join(content))

        logger.info("markdown_report_generated", report_path=str(report_path))

    def _generate_grid_markdown_report(
        self,
        sweep_results: List[SweepResult],
        param_grid: Dict[str, List],
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

        # Best configuration
        best_idx = max(range(len(sweep_results)), key=lambda i: sweep_results[i].summary.mean_map)
        best_result = sweep_results[best_idx]

        content.append("## Best Configuration")
        content.append("")
        for param_name in param_names:
            param_val = getattr(best_result.config, param_name)
            content.append(f"- **{param_name}**: {param_val}")
        content.append("")
        content.append(f"**Results**:")
        content.append(f"- MAP: {best_result.summary.mean_map:.3f}")
        content.append(f"- Recall@5: {best_result.summary.mean_recall_at_5:.3f}")
        content.append(f"- Precision@3: {best_result.summary.mean_precision_at_3:.3f}")
        content.append(f"- MRR: {best_result.summary.mean_mrr:.3f}")
        content.append("")

        # Heatmaps (if 2D grid)
        if len(param_names) == 2:
            content.append("## Heatmaps")
            content.append("")
            content.append("### MAP Heatmap")
            content.append("![MAP Heatmap](charts/map_heatmap.png)")
            content.append("")
            content.append("### Recall@5 Heatmap")
            content.append("![Recall@5 Heatmap](charts/recall5_heatmap.png)")
            content.append("")

        # Full results table
        content.append("## All Configurations")
        content.append("")
        header = "| " + " | ".join(param_names) + " | MAP | Recall@5 | Precision@3 | MRR |"
        separator = "|" + "|".join(["-" * 12 for _ in range(len(param_names) + 4)]) + "|"
        content.append(header)
        content.append(separator)

        for result in sorted(sweep_results, key=lambda r: r.summary.mean_map, reverse=True):
            row = "| "
            for param_name in param_names:
                row += f"{getattr(result.config, param_name)} | "
            row += (
                f"{result.summary.mean_map:.3f} | {result.summary.mean_recall_at_5:.3f} | "
                f"{result.summary.mean_precision_at_3:.3f} | {result.summary.mean_mrr:.3f} |"
            )
            content.append(row)

        content.append("")

        # Write report
        report_path = output_dir / "comparison_report.md"
        with open(report_path, 'w') as f:
            f.write("\n".join(content))

        logger.info("grid_markdown_report_generated", report_path=str(report_path))
