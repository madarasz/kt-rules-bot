"""Multi-run visualization utilities for quality test results.

Generates charts showing averaged metrics with error bars across multiple runs.
"""

from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # Use non-interactive backend
import matplotlib.pyplot as plt
import numpy as np

from src.lib.logging import get_logger
from tests.quality.aggregator import MultiRunAggregator
from tests.quality.models import MultiRunTestSuite

logger = get_logger(__name__)


def generate_multi_run_visualization(
    multi_run_suite: MultiRunTestSuite, output_file: str | None = None
) -> str:
    """Generate visualization chart from multi-run test suite results.

    Creates a grouped bar chart showing averaged metrics per model with:
    - Average bars for score %, time, cost, characters
    - Error bars showing standard deviation
    - Individual data points overlaid on bars

    Args:
        multi_run_suite: Multi-run test suite results
        output_file: Optional file path to write chart to

    Returns:
        Path to generated PNG file
    """
    # Generate timestamp for filename
    dt = datetime.fromisoformat(multi_run_suite.last_run_timestamp)
    timestamp_str = dt.strftime("%Y-%m-%d_%H-%M-%S")

    if output_file is None:
        output_dir = Path("tests/quality/results")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = (
            output_dir
            / f"quality_test_{timestamp_str}_chart_multirun_{multi_run_suite.run_count}x.png"
        )
    else:
        output_file = Path(output_file)

    # Create aggregator
    aggregator = MultiRunAggregator(multi_run_suite.run_suites)

    # Get models
    models = aggregator.models
    if not models:
        logger.warning("No models found in multi-run test suite")
        return str(output_file)

    # Collect averaged metrics and std devs
    avg_earned_pcts = []
    avg_llm_error_pcts = []
    avg_times = []
    avg_costs = []
    avg_chars = []

    std_earned_pcts = []
    std_llm_error_pcts = []
    std_times = []
    std_costs = []
    std_chars = []

    # Raw values for individual data points
    raw_earned_pcts_by_model = []
    raw_llm_error_pcts_by_model = []
    raw_times_by_model = []
    raw_costs_by_model = []
    raw_chars_by_model = []

    for model in models:
        avgs = aggregator.get_model_averages(model)
        stds = aggregator.get_model_std_devs(model)

        avg_earned_pcts.append(avgs["score_pct"])
        avg_llm_error_pcts.append(avgs["llm_error_pct"])
        avg_times.append(avgs["time"])
        avg_costs.append(avgs["cost"])
        avg_chars.append(avgs["chars"])

        std_earned_pcts.append(stds["score_pct"])
        std_llm_error_pcts.append(stds["llm_error_pct"])
        std_times.append(stds["time"])
        std_costs.append(stds["cost"])
        std_chars.append(stds["chars"])

        # Get raw values for scatter plot
        raw_earned_pcts_by_model.append(aggregator.get_model_raw_values(model, "score_pct"))
        raw_llm_error_pcts_by_model.append(aggregator.get_model_raw_values(model, "llm_error_pct"))
        raw_times_by_model.append(aggregator.get_model_raw_values(model, "time"))
        raw_costs_by_model.append(aggregator.get_model_raw_values(model, "cost"))
        raw_chars_by_model.append(aggregator.get_model_raw_values(model, "chars"))

    # Create figure with space for queries at bottom
    fig, ax1 = plt.subplots(figsize=(14, 8))

    # Set up x-axis
    x = np.arange(len(models))
    width = 0.2  # Width of bars (adjusted for 4 bars)

    # Bar positions
    pos1 = x - 1.5 * width
    pos2 = x - 0.5 * width
    pos3 = x + 0.5 * width
    pos4 = x + 1.5 * width

    # Colors
    color_earned = "#2ecc71"  # Green for earned points
    color_llm_error = "#95a5a6"  # Grey for LLM errors
    color_time = "#3498db"  # Blue
    color_cost = "#e74c3c"  # Red
    color_chars = "#8B4513"  # Brown

    # Plot score % on left axis - use stacked bars with error bars
    # Bottom layer: earned score
    ax1.bar(
        pos1,
        avg_earned_pcts,
        width,
        label="Score % (earned)",
        color=color_earned,
        alpha=0.8,
        yerr=std_earned_pcts,
        capsize=3,
        error_kw={"elinewidth": 1, "alpha": 0.7},
    )

    # Top layer: LLM error (stacked on earned)
    ax1.bar(
        pos1,
        avg_llm_error_pcts,
        width,
        bottom=avg_earned_pcts,
        label="LLM Error %",
        color=color_llm_error,
        alpha=0.8,
        yerr=std_llm_error_pcts,
        capsize=3,
        error_kw={"elinewidth": 1, "alpha": 0.7},
    )

    # Overlay individual data points for score %
    for i, _model in enumerate(models):
        # Earned points
        raw_vals = raw_earned_pcts_by_model[i]
        if raw_vals:
            x_positions = np.full(len(raw_vals), pos1[i])
            ax1.scatter(
                x_positions,
                raw_vals,
                color=color_earned,
                s=20,
                alpha=0.6,
                zorder=10,
                edgecolors="black",
                linewidths=0.5,
            )

        # LLM error points (stacked on earned)
        raw_llm_vals = raw_llm_error_pcts_by_model[i]
        if raw_llm_vals and raw_vals:
            # Stack on top of earned
            stacked_vals = [e + llm_val for e, llm_val in zip(raw_vals, raw_llm_vals, strict=False)]
            x_positions = np.full(len(stacked_vals), pos1[i])
            ax1.scatter(
                x_positions,
                stacked_vals,
                color=color_llm_error,
                s=20,
                alpha=0.6,
                zorder=10,
                edgecolors="black",
                linewidths=0.5,
            )

    ax1.set_xlabel("Model", fontsize=12, fontweight="bold")
    ax1.set_ylabel("Score %", fontsize=12, fontweight="bold", color=color_earned)
    ax1.tick_params(axis="y", labelcolor=color_earned)
    ax1.set_ylim(0, 100)
    ax1.set_xticks(x)
    ax1.set_xticklabels(models, rotation=45, ha="right")

    # Create second y-axis for time
    ax2 = ax1.twinx()
    ax2.bar(
        pos2,
        avg_times,
        width,
        label="Time (s)",
        color=color_time,
        alpha=0.8,
        yerr=std_times,
        capsize=3,
        error_kw={"elinewidth": 1, "alpha": 0.7},
    )

    # Overlay individual data points for time
    for i, _model in enumerate(models):
        raw_vals = raw_times_by_model[i]
        if raw_vals:
            x_positions = np.full(len(raw_vals), pos2[i])
            ax2.scatter(
                x_positions,
                raw_vals,
                color=color_time,
                s=20,
                alpha=0.6,
                zorder=10,
                edgecolors="black",
                linewidths=0.5,
            )

    ax2.set_ylabel("Time (seconds)", fontsize=12, fontweight="bold", color=color_time)
    ax2.tick_params(axis="y", labelcolor=color_time)
    ax2.set_ylim(bottom=0)

    # Create third y-axis for cost
    ax3 = ax1.twinx()
    # Offset the third axis
    ax3.spines["right"].set_position(("outward", 60))
    ax3.bar(
        pos3,
        avg_costs,
        width,
        label="Cost (USD)",
        color=color_cost,
        alpha=0.8,
        yerr=std_costs,
        capsize=3,
        error_kw={"elinewidth": 1, "alpha": 0.7},
    )

    # Overlay individual data points for cost
    for i, _model in enumerate(models):
        raw_vals = raw_costs_by_model[i]
        if raw_vals:
            x_positions = np.full(len(raw_vals), pos3[i])
            ax3.scatter(
                x_positions,
                raw_vals,
                color=color_cost,
                s=20,
                alpha=0.6,
                zorder=10,
                edgecolors="black",
                linewidths=0.5,
            )

    ax3.set_ylabel("Cost (USD)", fontsize=12, fontweight="bold", color=color_cost)
    ax3.tick_params(axis="y", labelcolor=color_cost)
    ax3.set_ylim(bottom=0)

    # Create fourth y-axis for characters
    ax4 = ax1.twinx()
    # Offset the fourth axis
    ax4.spines["right"].set_position(("outward", 120))
    ax4.bar(
        pos4,
        avg_chars,
        width,
        label="Characters",
        color=color_chars,
        alpha=0.8,
        yerr=std_chars,
        capsize=3,
        error_kw={"elinewidth": 1, "alpha": 0.7},
    )

    # Overlay individual data points for characters
    for i, _model in enumerate(models):
        raw_vals = raw_chars_by_model[i]
        if raw_vals:
            x_positions = np.full(len(raw_vals), pos4[i])
            ax4.scatter(
                x_positions,
                raw_vals,
                color=color_chars,
                s=20,
                alpha=0.6,
                zorder=10,
                edgecolors="black",
                linewidths=0.5,
            )

    ax4.set_ylabel("Response Characters", fontsize=12, fontweight="bold", color=color_chars)
    ax4.tick_params(axis="y", labelcolor=color_chars)
    ax4.set_ylim(bottom=0)

    # Title
    plt.title(
        f"Model Performance Comparison (N={multi_run_suite.run_count} runs, averaged)",
        fontsize=14,
        fontweight="bold",
        pad=20,
    )

    # Add legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    lines3, labels3 = ax3.get_legend_handles_labels()
    lines4, labels4 = ax4.get_legend_handles_labels()
    ax1.legend(
        lines1 + lines2 + lines3 + lines4,
        labels1 + labels2 + labels3 + labels4,
        loc="upper left",
        fontsize=9,
    )

    # Grid for readability
    ax1.grid(axis="y", alpha=0.3, linestyle="--")

    # Add test queries at the bottom with reduced spacing
    # Get unique queries from first run
    test_queries = set()
    if multi_run_suite.run_suites:
        for result in multi_run_suite.run_suites[0].test_results:
            clean_query = result.query.replace('\\"', '"').replace("\\'", "'")
            test_queries.add(clean_query)

    sorted_queries = sorted(test_queries)
    query_lines = ["Test Queries:"]
    for q in sorted_queries:
        query_lines.append(f"• {q}")

    # Join with minimal spacing
    query_text = "\n".join(query_lines)
    plt.figtext(0.1, 0.02, query_text, fontsize=9, va="top", linespacing=1)  # Reduced line spacing

    # Note about error bars
    # note_text = f"Error bars show standard deviation across {multi_run_suite.run_count} runs. Dots show individual run values."
    # plt.figtext(0.1, 0.01, note_text, fontsize=8, va='top',
    #             style='italic', color='#666666')

    # Adjust layout to make room for queries
    plt.subplots_adjust(bottom=0.25)

    # Save figure
    plt.savefig(output_file, dpi=150, bbox_inches="tight")
    plt.close()

    logger.info(f"Multi-run visualization saved to {output_file}")
    return str(output_file)
