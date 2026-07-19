"""Chart generation for quality test reports."""

import os

import numpy as np

from src.lib.constants import QUALITY_TEST_JUDGING

try:
    import matplotlib

    matplotlib.use("Agg")  # Use non-interactive backend
    import matplotlib.pyplot as plt

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

from tests.quality.reporting.report_models import IndividualTestResult, QualityReport

# Score-bar segment colors (single source of truth for the stacked score bar).
COLOR_EARNED = "#2ecc71"  # Green — score earned on runs that never errored
COLOR_RECOVERED = "#f1c40f"  # Gold — score recovered by re-requesting a failed batch item
COLOR_ERROR = "#95a5a6"  # Grey — score lost to unrecoverable (LLM + Ragas) errors


class ChartGenerator:
    """Generates visualization charts for quality test reports."""

    def __init__(self, report: QualityReport):
        self.report = report
        self.report_dir = report.report_dir

    def generate_all_charts(self) -> None:
        """Generate all visualization charts for the report."""
        if not MATPLOTLIB_AVAILABLE:
            return

        # Generate main chart for multi-model scenarios
        if self.report.is_multi_model:
            chart_path = self._generate_main_chart()
            if chart_path:
                self.report.chart_path = chart_path

            # Generate Ragas metrics chart for multi-model scenarios
            ragas_chart_path = self._generate_ragas_metrics_chart()
            if ragas_chart_path:
                self.report.ragas_chart_path = ragas_chart_path

        # Generate per-test-case charts for multi-model scenarios
        if self.report.is_multi_test_case and self.report.is_multi_model:
            for test_id, test_case_report in self.report.per_test_case_reports.items():
                chart_path = self._generate_test_case_chart(test_id, test_case_report.results)
                if chart_path:
                    test_case_report.chart_path = chart_path

    def _generate_main_chart(self) -> str | None:
        """Generate the main visualization chart comparing models."""
        if not MATPLOTLIB_AVAILABLE or not self.report.is_multi_model:
            return None

        chart_path = os.path.join(self.report_dir, "chart.png")

        # Aggregate data by model and test case
        # Structure: model -> test_id -> list of results
        model_test_data = {}
        test_queries = set()

        for result in self.report.results:
            # Remove escape characters from query text for display
            clean_query = result.query.replace('\\"', '"').replace("\\'", "'")
            test_queries.add(clean_query)

            if result.model not in model_test_data:
                model_test_data[result.model] = {}
            if result.test_id not in model_test_data[result.model]:
                model_test_data[result.model][result.test_id] = {
                    "scores": [],
                    "times": [],
                    "costs": [],
                    "chars": [],
                }

            model_test_data[result.model][result.test_id]["scores"].append(result.score_percentage)
            model_test_data[result.model][result.test_id]["times"].append(
                result.generation_time_seconds
            )
            model_test_data[result.model][result.test_id]["costs"].append(result.cost_usd + result.cache_savings_usd)
            model_test_data[result.model][result.test_id]["chars"].append(result.output_char_count)

        # Calculate per-run averages, then overall averages and std devs
        models = list(model_test_data.keys())
        avg_scores = []
        avg_times = []
        avg_costs = []
        avg_chars = []
        std_scores = []
        std_times = []
        std_costs = []
        std_chars = []

        # Store per-run averages for individual point plotting
        model_run_averages = {}

        for model in models:
            # Determine max number of runs across all tests for this model
            max_runs = max(
                len(model_test_data[model][test_id]["scores"])
                for test_id in model_test_data[model]
            )

            # Calculate average for each run (across all tests)
            run_avg_scores = []
            run_avg_times = []
            run_avg_costs = []
            run_avg_chars = []

            for run_idx in range(max_runs):
                # Collect all test results for this run
                run_scores = []
                run_times = []
                run_costs = []
                run_chars = []

                for test_id in model_test_data[model]:
                    test_data = model_test_data[model][test_id]
                    if run_idx < len(test_data["scores"]):
                        run_scores.append(test_data["scores"][run_idx])
                        run_times.append(test_data["times"][run_idx])
                        run_costs.append(test_data["costs"][run_idx])
                        run_chars.append(test_data["chars"][run_idx])

                # Average across all tests for this run
                if run_scores:
                    run_avg_scores.append(np.mean(run_scores))
                    run_avg_times.append(np.mean(run_times))
                    run_avg_costs.append(np.mean(run_costs))
                    run_avg_chars.append(np.mean(run_chars))

            # Store per-run averages for this model
            model_run_averages[model] = {
                "scores": run_avg_scores,
                "times": run_avg_times,
                "costs": run_avg_costs,
                "chars": run_avg_chars,
            }

            # Overall average is the mean of per-run averages
            avg_scores.append(np.mean(run_avg_scores))
            avg_times.append(np.mean(run_avg_times))
            avg_costs.append(np.mean(run_avg_costs))
            avg_chars.append(np.mean(run_avg_chars))

            # Std dev is calculated from per-run averages (between-run variability)
            std_scores.append(np.std(run_avg_scores) if len(run_avg_scores) > 1 else 0)
            std_times.append(np.std(run_avg_times) if len(run_avg_times) > 1 else 0)
            std_costs.append(np.std(run_avg_costs) if len(run_avg_costs) > 1 else 0)
            std_chars.append(np.std(run_avg_chars) if len(run_avg_chars) > 1 else 0)

        return self._create_chart(
            chart_path=chart_path,
            models=models,
            avg_times=avg_times,
            avg_costs=avg_costs,
            avg_chars=avg_chars,
            std_scores=std_scores,
            std_times=std_times,
            std_costs=std_costs,
            std_chars=std_chars,
            test_queries=test_queries,
            title="Model Performance Comparison",
            model_run_averages=model_run_averages,
        )

    def _generate_test_case_chart(
        self, test_id: str, results: list[IndividualTestResult]
    ) -> str | None:
        """Generate a chart for a specific test case comparing models."""
        if not MATPLOTLIB_AVAILABLE or len({r.model for r in results}) <= 1:
            return None

        chart_path = os.path.join(self.report_dir, f"chart_{test_id}.png")

        # Aggregate data by model for this test case
        model_data = {}
        for result in results:
            if result.model not in model_data:
                model_data[result.model] = {"scores": [], "times": [], "costs": [], "chars": []}
            model_data[result.model]["scores"].append(result.score_percentage)
            model_data[result.model]["times"].append(result.generation_time_seconds)
            model_data[result.model]["costs"].append(result.cost_usd + result.cache_savings_usd)
            model_data[result.model]["chars"].append(result.output_char_count)

        models = list(model_data.keys())
        avg_times = [np.mean(model_data[m]["times"]) for m in models]
        avg_costs = [np.mean(model_data[m]["costs"]) for m in models]
        avg_chars = [np.mean(model_data[m]["chars"]) for m in models]

        # Error bars for multi-run scenarios
        std_scores = [
            np.std(model_data[m]["scores"]) if len(model_data[m]["scores"]) > 1 else 0
            for m in models
        ]
        std_times = [
            np.std(model_data[m]["times"]) if len(model_data[m]["times"]) > 1 else 0 for m in models
        ]
        std_costs = [
            np.std(model_data[m]["costs"]) if len(model_data[m]["costs"]) > 1 else 0 for m in models
        ]
        std_chars = [
            np.std(model_data[m]["chars"]) if len(model_data[m]["chars"]) > 1 else 0 for m in models
        ]

        return self._create_chart(
            chart_path=chart_path,
            models=models,
            avg_times=avg_times,
            avg_costs=avg_costs,
            avg_chars=avg_chars,
            std_scores=std_scores,
            std_times=std_times,
            std_costs=std_costs,
            std_chars=std_chars,
            test_queries=set(),  # Don't include queries for per-test-case charts
            title=f"Model Performance Comparison - {test_id}",
            filtered_model_data=model_data,  # Pass filtered data for scatter points
        )

    def _create_chart(
        self,
        chart_path: str,
        models: list[str],
        avg_times: list[float],
        avg_costs: list[float],
        avg_chars: list[float],
        std_scores: list[float],
        std_times: list[float],
        std_costs: list[float],
        std_chars: list[float],
        test_queries: set[str],
        title: str,
        model_run_averages: dict | None = None,
        filtered_model_data: dict | None = None,
    ) -> str:
        """Create a chart with the given data."""
        # Create figure
        fig, ax1 = plt.subplots(figsize=(14, 8))

        # Set up x-axis
        x = np.arange(len(models))
        width = 0.2

        # Bar positions
        pos1 = x - 1.5 * width
        pos2 = x - 0.5 * width
        pos3 = x + 0.5 * width
        pos4 = x + 1.5 * width

        # Determine if we should show error bars (multi-run scenario)
        show_error_bars = self.report.is_multi_run

        # Calculate earned / recovered / error percentages for the stacked score bar
        earned_scores, recovered_scores, llm_error_scores = self._calculate_score_breakdown(models)

        # Colors
        color_earned = COLOR_EARNED  # Green for earned points
        color_recovered = COLOR_RECOVERED  # Gold for score recovered by re-request
        color_llm_error = COLOR_ERROR  # Grey for evaluation errors (LLM + Ragas)
        color_time = "#3498db"  # Blue
        color_cost = "#e74c3c"  # Red
        color_chars = "#8B4513"  # Brown

        # Plot score % on primary axis — stack green (earned) + gold (recovered by
        # re-request) + grey (lost to unrecoverable errors).
        ax1.bar(pos1, earned_scores, width, label="Score % (earned)", color=color_earned, alpha=0.8)
        recovered_label = (
            "Score % (recovered)" if any(r > 0 for r in recovered_scores) else None
        )
        ax1.bar(
            pos1,
            recovered_scores,
            width,
            bottom=earned_scores,
            label=recovered_label,
            color=color_recovered,
            alpha=0.8,
        )
        earned_plus_recovered = [
            e + rv for e, rv in zip(earned_scores, recovered_scores, strict=False)
        ]
        # Only add error label to legend if there are actual errors
        error_label = "Evaluation Error % (LLM + Ragas)" if any(e > 0 for e in llm_error_scores) else None
        ax1.bar(
            pos1,
            llm_error_scores,
            width,
            bottom=earned_plus_recovered,
            label=error_label,
            color=color_llm_error,
            alpha=0.8,
        )

        # Add error bars to the total (earned + recovered + LLM error) if multi-run
        if show_error_bars:
            total_scores = [
                e + rv + llm_val
                for e, rv, llm_val in zip(
                    earned_scores, recovered_scores, llm_error_scores, strict=False
                )
            ]
            ax1.errorbar(
                pos1,
                total_scores,
                yerr=std_scores,
                fmt="none",
                ecolor=color_llm_error,
                capsize=5,
                capthick=2,
                alpha=0.7,
            )

        # Add individual data points for different queries if multi-run or multi-test-case
        if self.report.is_multi_run or self.report.is_multi_test_case:
            self._add_individual_points(ax1, pos1, models, "scores", model_run_averages, filtered_model_data)

        ax1.set_xlabel("Model", fontsize=12, fontweight="bold")
        ax1.set_ylabel("Score %", fontsize=12, fontweight="bold", color=color_earned)
        ax1.tick_params(axis="y", labelcolor=color_earned)
        ax1.set_ylim(0, 100)
        ax1.set_xticks(x)
        ax1.set_xticklabels(models, rotation=45, ha="right")

        # Create secondary axes
        ax2 = ax1.twinx()
        ax2.bar(pos2, avg_times, width, label="Time (s)", color=color_time, alpha=0.8)
        if show_error_bars:
            ax2.errorbar(
                pos2,
                avg_times,
                yerr=std_times,
                fmt="none",
                ecolor=color_llm_error,
                capsize=5,
                capthick=2,
                alpha=0.7,
            )
        if self.report.is_multi_run or self.report.is_multi_test_case:
            self._add_individual_points(ax2, pos2, models, "times", model_run_averages, filtered_model_data)
        ax2.set_ylabel("Time (seconds)", fontsize=12, fontweight="bold", color=color_time)
        ax2.tick_params(axis="y", labelcolor=color_time)
        # Ensure time axis starts from 0
        ax2.set_ylim(bottom=0)

        ax3 = ax1.twinx()
        ax3.spines["right"].set_position(("outward", 60))
        ax3.bar(pos3, avg_costs, width, label="Cost (USD)", color=color_cost, alpha=0.8)
        if show_error_bars:
            ax3.errorbar(
                pos3,
                avg_costs,
                yerr=std_costs,
                fmt="none",
                ecolor=color_llm_error,
                capsize=5,
                capthick=2,
                alpha=0.7,
            )
        if self.report.is_multi_run or self.report.is_multi_test_case:
            self._add_individual_points(ax3, pos3, models, "costs", model_run_averages, filtered_model_data)
        ax3.set_ylabel("Cost (USD)", fontsize=12, fontweight="bold", color=color_cost)
        ax3.tick_params(axis="y", labelcolor=color_cost)
        # Ensure cost axis starts from 0
        ax3.set_ylim(bottom=0)

        ax4 = ax1.twinx()
        ax4.spines["right"].set_position(("outward", 120))
        ax4.bar(pos4, avg_chars, width, label="Characters", color=color_chars, alpha=0.8)
        if show_error_bars:
            ax4.errorbar(
                pos4,
                avg_chars,
                yerr=std_chars,
                fmt="none",
                ecolor=color_llm_error,
                capsize=5,
                capthick=2,
                alpha=0.7,
            )
        if self.report.is_multi_run or self.report.is_multi_test_case:
            self._add_individual_points(ax4, pos4, models, "chars", model_run_averages, filtered_model_data)
        ax4.set_ylabel("Response Characters", fontsize=12, fontweight="bold", color=color_chars)
        ax4.tick_params(axis="y", labelcolor=color_chars)
        # Ensure characters axis starts from 0
        ax4.set_ylim(bottom=0)

        # Title and legend
        plt.title(title, fontsize=14, fontweight="bold", pad=20)

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        lines3, labels3 = ax3.get_legend_handles_labels()
        lines4, labels4 = ax4.get_legend_handles_labels()
        ax1.legend(
            lines1 + lines2 + lines3 + lines4,
            labels1 + labels2 + labels3 + labels4,
            loc="best",
        )

        ax1.grid(axis="y", alpha=0.3, linestyle="--")

        # Add test queries at bottom if provided
        if test_queries:
            sorted_queries = sorted(test_queries)
            query_lines = ["Test Queries:"] + [f"• {q}" for q in sorted_queries]
            query_text = "\n".join(query_lines)
            plt.figtext(0.1, 0.02, query_text, fontsize=9, va="top", linespacing=1.2)
            plt.subplots_adjust(bottom=0.25)
        else:
            plt.tight_layout()

        plt.savefig(chart_path, dpi=150, bbox_inches="tight")
        plt.close()

        return chart_path

    def _calculate_score_breakdown(self, models: list[str]) -> tuple:
        """Calculate earned / recovered / error score percentages per model.

        Three stacked segments (green + gold + grey), chosen so the total bar
        height and the grey portion are identical to the pre-recovery chart —
        recovered work is only recolored, not added:
        - earned (green): score of runs that did NOT recover from an error.
        - recovered (gold): score of runs that succeeded only after a batch
          re-request (recovered_from_error=True).
        - error (grey): score lost (max_score - score) on any run that still
          carries an LLM/Ragas error — including the rare double-fault where a
          recovered generation was followed by a permanent judge error, whose
          earned portion lands in gold and whose lost portion lands in grey.
        """
        earned_scores = []
        recovered_scores = []
        error_scores = []

        for model in models:
            model_results = [r for r in self.report.results if r.model == model]
            if not model_results:
                earned_scores.append(0.0)
                recovered_scores.append(0.0)
                error_scores.append(0.0)
                continue

            total_max = sum(r.max_score for r in model_results)
            earned = 0
            recovered = 0
            error_lost = 0
            for result in model_results:
                if getattr(result, "recovered_from_error", False):
                    recovered += result.score
                else:
                    earned += result.score
                # Score lost to an unrecoverable error (grey), unchanged semantics.
                if result.error or result.ragas_evaluation_error:
                    error_lost += result.max_score - result.score

            if total_max > 0:
                earned_scores.append((earned / total_max) * 100)
                recovered_scores.append((recovered / total_max) * 100)
                error_scores.append((error_lost / total_max) * 100)
            else:
                earned_scores.append(0.0)
                recovered_scores.append(0.0)
                error_scores.append(0.0)

        return earned_scores, recovered_scores, error_scores

    def _calculate_ragas_metric_breakdown(
        self, models: list[str], metric_name: str
    ) -> tuple[list[float], list[float]]:
        """Calculate earned and error portions for a specific Ragas metric.

        For each model, calculates:
        - Earned: Average of successful evaluations
        - Error: Lost potential from failed evaluations (estimated using avg of successful)

        Args:
            models: List of model names
            metric_name: Name of the metric attribute (e.g., 'quote_precision')

        Returns:
            Tuple of (earned_values, error_values) lists
        """
        earned_values = []
        error_values = []

        for model in models:
            model_results = [r for r in self.report.results if r.model == model]
            if not model_results:
                earned_values.append(0.0)
                error_values.append(0.0)
                continue

            # Separate successful and failed evaluations
            successful_values = []
            failed_count = 0

            for result in model_results:
                metric_value = getattr(result, metric_name, None)

                # Check if this specific metric failed
                if metric_value is None and result.ragas_evaluation_error:
                    failed_count += 1
                elif metric_value is not None:
                    successful_values.append(metric_value)
                # If metric is None but ragas_evaluation_error is False, it's a successful 0.0

            total_count = len(model_results)

            if total_count == 0:
                earned_values.append(0.0)
                error_values.append(0.0)
                continue

            # Calculate earned portion (average of successful)
            if successful_values:
                avg_successful = sum(successful_values) / len(successful_values)
                earned = (sum(successful_values) / total_count)
            else:
                # All evaluations failed - assume they would have scored 0.5 (middle of range)
                avg_successful = 0.5
                earned = 0.0

            # Calculate error portion (lost potential from failures)
            # Estimate lost score: if evaluations had succeeded, they would have scored avg_successful
            error = (avg_successful * failed_count) / total_count if failed_count > 0 else 0.0

            earned_values.append(earned)
            error_values.append(error)

        return earned_values, error_values

    def _add_individual_points(
        self,
        ax,
        positions,
        models: list[str],
        metric: str,
        model_run_averages: dict | None = None,
        filtered_model_data: dict | None = None,
    ):
        """Add individual data points as small circles on the chart.

        If model_run_averages is provided, plots per-run averages (average across all tests for each run).
        If filtered_model_data is provided, uses that data (for per-test-case charts).
        Otherwise, falls back to self.report.results (should not happen in practice).
        """
        for i, model in enumerate(models):
            # Use per-run averages if provided (for multi-run main chart)
            if model_run_averages and model in model_run_averages:
                values = model_run_averages[model].get(metric, [])
            elif filtered_model_data and model in filtered_model_data:
                # Use filtered data for per-test-case charts
                values = filtered_model_data[model].get(metric, [])
            else:
                # Fall back to individual test results (should not happen in practice)
                model_results = [r for r in self.report.results if r.model == model]
                if not model_results:
                    continue

                values = []
                for result in model_results:
                    if metric == "scores":
                        values.append(result.score_percentage)
                    elif metric == "times":
                        values.append(result.generation_time_seconds)
                    elif metric == "costs":
                        values.append(result.cost_usd + result.cache_savings_usd)
                    elif metric == "chars":
                        values.append(result.output_char_count)

            if values:
                # Add small jitter to x-position to avoid overlapping points
                x_positions = [positions[i] + np.random.uniform(-0.02, 0.02) for _ in values]
                ax.scatter(
                    x_positions,
                    values,
                    color="white",
                    s=20,
                    alpha=0.8,
                    edgecolors="black",
                    linewidth=1,
                    zorder=10,
                )

    def _generate_ragas_metrics_chart(self) -> str | None:
        """Generate a chart showing individual Ragas metrics per model.

        X-axis shows metrics, with each model as a separate colored bar within
        each metric group.

        Returns:
            Path to the generated chart, or None if chart generation is not applicable.
        """
        if not MATPLOTLIB_AVAILABLE or not self.report.is_multi_model:
            return None

        # Check if we have any Ragas metrics to display
        has_ragas_data = any(r.ragas_metrics_available for r in self.report.results)
        if not has_ragas_data:
            return None

        chart_path = os.path.join(self.report_dir, "chart_metrics.png")

        # Get unique models
        models = sorted({r.model for r in self.report.results})

        # Define all possible metrics with their properties (color no longer used per-metric)
        all_metrics = [
            ("quote_precision", "Quote Precision"),
            ("quote_recall", "Quote Recall"),
            ("quote_faithfulness", "Quote Faithfulness"),
            ("explanation_faithfulness", "Explanation Faithfulness"),
            ("answer_correctness", "Answer Correctness"),
        ]

        # Filter metrics to only include those with actual data
        metrics_to_plot = []
        for metric_name, label in all_metrics:
            # Check if any result has this metric
            has_data = any(
                getattr(r, metric_name, None) is not None for r in self.report.results
            )
            if has_data:
                metrics_to_plot.append((metric_name, label))

        if not metrics_to_plot:
            return None  # No metrics have data

        # Color palette for models (distinct colors)
        model_colors = [
            "#3498db",  # Blue
            "#2ecc71",  # Green
            "#9b59b6",  # Purple
            "#e74c3c",  # Red
            "#f39c12",  # Orange
            "#1abc9c",  # Teal
            "#34495e",  # Dark grey-blue
            "#e91e63",  # Pink
            "#00bcd4",  # Cyan
            "#8bc34a",  # Light green
        ]
        color_error = "#95a5a6"  # Grey for evaluation errors

        # Create figure
        fig, ax = plt.subplots(figsize=(14, 8))

        # Set up x-axis: one position per metric
        x = np.arange(len(metrics_to_plot))
        num_models = len(models)
        width = 0.8 / num_models  # Adjust width based on number of models

        # Calculate bar positions centered around each metric
        positions = []
        for i in range(num_models):
            offset = (i - (num_models - 1) / 2) * width
            positions.append(x + offset)

        # Pre-compute all error values to determine if any exist
        all_error_values = {}
        for model in models:
            error_values = []
            for metric_name, _label in metrics_to_plot:
                _earned_list, error_list = self._calculate_ragas_metric_breakdown(
                    [model], metric_name
                )
                error_values.append(error_list[0] if error_list else 0.0)
            all_error_values[model] = error_values

        # Check if any errors exist across all models
        has_any_errors = any(
            any(e > 0 for e in error_values)
            for error_values in all_error_values.values()
        )

        # Plot stacked bars for each model (earned + error portions)
        for i, model in enumerate(models):
            pos = positions[i]
            color = model_colors[i % len(model_colors)]

            # Calculate earned values for this model across all metrics
            earned_values = []
            for metric_name, _label in metrics_to_plot:
                # Get earned for this specific model and metric
                earned_list, _error_list = self._calculate_ragas_metric_breakdown(
                    [model], metric_name
                )
                earned_values.append(earned_list[0] if earned_list else 0.0)

            # Get pre-computed error values
            error_values = all_error_values[model]

            # Plot earned portion (colored bar)
            ax.bar(pos, earned_values, width, label=model, color=color, alpha=0.8)

            # Plot error portion (grey bar stacked on top)
            # Only add "Evaluation Errors" label once, and only if there are actual errors
            error_label = "Evaluation Errors" if i == 0 and has_any_errors else None
            ax.bar(
                pos,
                error_values,
                width,
                bottom=earned_values,
                label=error_label,
                color=color_error,
                alpha=0.8,
            )

        # Labels and title
        ax.set_xlabel("Metric", fontsize=12, fontweight="bold")
        ax.set_ylabel("Metric Score (0-1)", fontsize=12, fontweight="bold")
        ax.set_ylim(0, 1.0)
        ax.set_xticks(x)
        # Extract metric labels for x-axis
        metric_labels = [label for _name, label in metrics_to_plot]
        ax.set_xticklabels(metric_labels, rotation=45, ha="right")
        ax.legend(loc="best", fontsize=10)
        ax.grid(axis="y", alpha=0.3, linestyle="--")

        # Add note about LLM-based judging mode
        title = "Model Comparison by Metric"
        if QUALITY_TEST_JUDGING == "OFF":
            title += "\n(LLM-based judging: OFF - only local metrics shown)"

        plt.title(title, fontsize=14, fontweight="bold", pad=20)
        plt.tight_layout()

        plt.savefig(chart_path, dpi=150, bbox_inches="tight")
        plt.close()

        return chart_path
