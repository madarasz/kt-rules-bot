"""Utility functions for generating charts with matplotlib.

Helper functions for consistent chart styling and layout.
"""

from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

# Use non-interactive backend for server environments
matplotlib.use('Agg')


# Chart styling constants
CHART_STYLE = 'seaborn-v0_8-darkgrid'
FIGURE_SIZE = (12, 7)
FIGURE_SIZE_HEATMAP = (10, 8)
DPI = 300
COLORS = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D', '#6A994E', '#BC4B51']
FONT_SIZE_TITLE = 14
FONT_SIZE_LABEL = 12
FONT_SIZE_TICK = 10


def setup_plot_style():
    """Set up consistent matplotlib style for all charts."""
    try:
        plt.style.use(CHART_STYLE)
    except:
        # Fall back to default if style not available
        plt.style.use('default')

    plt.rcParams.update({
        'figure.figsize': FIGURE_SIZE,
        'figure.dpi': DPI,
        'font.size': FONT_SIZE_TICK,
        'axes.labelsize': FONT_SIZE_LABEL,
        'axes.titlesize': FONT_SIZE_TITLE,
        'xtick.labelsize': FONT_SIZE_TICK,
        'ytick.labelsize': FONT_SIZE_TICK,
        'legend.fontsize': FONT_SIZE_TICK,
    })


def save_and_close(fig, output_path: Path):
    """Save figure and close to free memory.

    Args:
        fig: Matplotlib figure
        output_path: Path to save PNG
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight', dpi=DPI)
    plt.close(fig)


def create_line_chart(
    x_values: list[Any],
    y_values: list[float],
    x_label: str,
    y_label: str,
    title: str,
    output_path: Path,
    y_errors: list[float] | None = None,
    y_min: float | None = None,
    y_max: float | None = None,
):
    """Create line chart with optional error bars.

    Args:
        x_values: X-axis values
        y_values: Y-axis values
        x_label: X-axis label
        y_label: Y-axis label
        title: Chart title
        output_path: Path to save PNG
        y_errors: Optional error bar values (std dev)
        y_min: Optional Y-axis minimum
        y_max: Optional Y-axis maximum
    """
    setup_plot_style()

    fig, ax = plt.subplots(figsize=FIGURE_SIZE)

    if y_errors:
        ax.errorbar(
            x_values,
            y_values,
            yerr=y_errors,
            marker='o',
            markersize=8,
            linewidth=2,
            capsize=5,
            capthick=2,
            color=COLORS[0],
        )
    else:
        ax.plot(
            x_values,
            y_values,
            marker='o',
            markersize=8,
            linewidth=2,
            color=COLORS[0],
        )

    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_title(title)
    ax.grid(True, alpha=0.3)

    if y_min is not None or y_max is not None:
        current_ylim = ax.get_ylim()
        new_ymin = y_min if y_min is not None else current_ylim[0]
        new_ymax = y_max if y_max is not None else current_ylim[1]
        ax.set_ylim(new_ymin, new_ymax)

    save_and_close(fig, output_path)


def create_multi_line_chart(
    x_values: list[Any],
    y_values_dict: dict[str, list[float]],
    x_label: str,
    y_label: str,
    title: str,
    output_path: Path,
):
    """Create line chart with multiple lines.

    Args:
        x_values: X-axis values (shared)
        y_values_dict: Dictionary mapping line names to Y values
        x_label: X-axis label
        y_label: Y-axis label
        title: Chart title
        output_path: Path to save PNG
    """
    setup_plot_style()

    fig, ax = plt.subplots(figsize=FIGURE_SIZE)

    for i, (name, y_values) in enumerate(y_values_dict.items()):
        color = COLORS[i % len(COLORS)]
        ax.plot(
            x_values,
            y_values,
            marker='o',
            markersize=6,
            linewidth=2,
            color=color,
            label=name,
        )

    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.legend()

    save_and_close(fig, output_path)


def create_grouped_bar_chart(
    categories: list[str],
    values_dict: dict[str, list[float]],
    x_label: str,
    y_label: str,
    title: str,
    output_path: Path,
):
    """Create grouped bar chart for comparing metrics.

    Args:
        categories: Category labels (e.g., parameter values)
        values_dict: Dictionary mapping metric names to values
        x_label: X-axis label
        y_label: Y-axis label
        title: Chart title
        output_path: Path to save PNG
    """
    setup_plot_style()

    fig, ax = plt.subplots(figsize=FIGURE_SIZE)

    num_categories = len(categories)
    num_metrics = len(values_dict)
    bar_width = 0.8 / num_metrics
    x = np.arange(num_categories)

    for i, (metric_name, values) in enumerate(values_dict.items()):
        offset = (i - num_metrics / 2 + 0.5) * bar_width
        color = COLORS[i % len(COLORS)]
        ax.bar(
            x + offset,
            values,
            bar_width,
            label=metric_name,
            color=color,
        )

    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_title(title)
    ax.set_xticks(x)
    ax.set_xticklabels(categories)
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    save_and_close(fig, output_path)


def create_heatmap(
    data: np.ndarray,
    x_labels: list[str],
    y_labels: list[str],
    x_param_name: str,
    y_param_name: str,
    value_label: str,
    title: str,
    output_path: Path,
    vmin: float | None = None,
    vmax: float | None = None,
):
    """Create heatmap for grid search results.

    Args:
        data: 2D numpy array of values
        x_labels: Labels for X-axis (columns)
        y_labels: Labels for Y-axis (rows)
        x_param_name: Name of X parameter
        y_param_name: Name of Y parameter
        value_label: Label for color scale
        title: Chart title
        output_path: Path to save PNG
        vmin: Optional minimum value for color scale
        vmax: Optional maximum value for color scale
    """
    setup_plot_style()

    fig, ax = plt.subplots(figsize=FIGURE_SIZE_HEATMAP)

    # Create heatmap
    im = ax.imshow(data, cmap='RdYlGn', aspect='auto', vmin=vmin, vmax=vmax)

    # Set ticks and labels
    ax.set_xticks(np.arange(len(x_labels)))
    ax.set_yticks(np.arange(len(y_labels)))
    ax.set_xticklabels(x_labels)
    ax.set_yticklabels(y_labels)

    # Rotate x labels if needed
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")

    # Add colorbar
    cbar = ax.figure.colorbar(im, ax=ax)
    cbar.ax.set_ylabel(value_label, rotation=-90, va="bottom")

    # Add text annotations
    for i in range(len(y_labels)):
        for j in range(len(x_labels)):
            text = ax.text(
                j, i, f"{data[i, j]:.3f}",
                ha="center", va="center", color="black", fontsize=9
            )

    ax.set_xlabel(x_param_name)
    ax.set_ylabel(y_param_name)
    ax.set_title(title)

    save_and_close(fig, output_path)
