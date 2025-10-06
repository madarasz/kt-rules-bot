"""Visualization utilities for quality test results.

Generates charts and graphs for quality test reports.
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import numpy as np

from tests.quality.models import QualityTestSuite
from src.lib.logging import get_logger

logger = get_logger(__name__)


def generate_visualization(
    test_suite: QualityTestSuite, output_file: Optional[str] = None
) -> str:
    """Generate visualization chart from test suite results.

    Creates a grouped bar chart showing score %, total time, total cost,
    and total response characters for each model tested.

    Args:
        test_suite: Test suite results
        output_file: Optional file path to write chart to

    Returns:
        Path to generated PNG file
    """
    # Generate timestamp for filename
    dt = datetime.fromisoformat(test_suite.timestamp)
    timestamp_str = dt.strftime("%Y-%m-%d_%H-%M-%S")

    if output_file is None:
        output_dir = Path("tests/quality/results")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"quality_test_{timestamp_str}_chart.png"
    else:
        output_file = Path(output_file)

    # Aggregate metrics by model
    model_stats: Dict[str, Dict] = {}
    test_queries = set()  # Track unique test queries

    for result in test_suite.test_results:
        # Remove escape characters from query text
        clean_query = result.query.replace('\\"', '"').replace("\\'", "'")
        test_queries.add(clean_query)

        if result.model not in model_stats:
            model_stats[result.model] = {
                'total_score': 0,
                'total_max': 0,
                'total_time': 0.0,
                'total_cost': 0.0,
                'total_chars': 0,
            }
        model_stats[result.model]['total_score'] += result.score
        model_stats[result.model]['total_max'] += result.max_score
        model_stats[result.model]['total_time'] += result.generation_time_seconds
        model_stats[result.model]['total_cost'] += result.cost_usd
        model_stats[result.model]['total_chars'] += result.response_chars

    # Calculate score percentages
    models = list(model_stats.keys())
    score_pcts = []
    times = []
    costs = []
    chars = []

    for model in models:
        stats = model_stats[model]
        if stats['total_max'] > 0:
            score_pct = (stats['total_score'] / stats['total_max']) * 100
        else:
            score_pct = 0.0
        score_pcts.append(score_pct)
        times.append(stats['total_time'])
        costs.append(stats['total_cost'])
        chars.append(stats['total_chars'])

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

    # Plot score % on left axis
    color1 = '#2ecc71'  # Green
    ax1.bar(pos1, score_pcts, width, label='Score %', color=color1, alpha=0.8)
    ax1.set_xlabel('Model', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Score %', fontsize=12, fontweight='bold', color=color1)
    ax1.tick_params(axis='y', labelcolor=color1)
    ax1.set_ylim(0, 100)
    ax1.set_xticks(x)
    ax1.set_xticklabels(models, rotation=45, ha='right')

    # Create second y-axis for time
    ax2 = ax1.twinx()
    color2 = '#3498db'  # Blue
    ax2.bar(pos2, times, width, label='Time (s)', color=color2, alpha=0.8)
    ax2.set_ylabel('Time (seconds)', fontsize=12, fontweight='bold', color=color2)
    ax2.tick_params(axis='y', labelcolor=color2)

    # Create third y-axis for cost
    ax3 = ax1.twinx()
    # Offset the third axis
    ax3.spines['right'].set_position(('outward', 60))
    color3 = '#e74c3c'  # Red
    ax3.bar(pos3, costs, width, label='Cost (USD)', color=color3, alpha=0.8)
    ax3.set_ylabel('Cost (USD)', fontsize=12, fontweight='bold', color=color3)
    ax3.tick_params(axis='y', labelcolor=color3)

    # Create fourth y-axis for characters
    ax4 = ax1.twinx()
    # Offset the fourth axis
    ax4.spines['right'].set_position(('outward', 120))
    color4 = '#8B4513'  # Brown
    ax4.bar(pos4, chars, width, label='Characters', color=color4, alpha=0.8)
    ax4.set_ylabel('Response Characters', fontsize=12, fontweight='bold', color=color4)
    ax4.tick_params(axis='y', labelcolor=color4)

    # Title
    plt.title('Model Performance Comparison', fontsize=14, fontweight='bold', pad=20)

    # Add legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    lines3, labels3 = ax3.get_legend_handles_labels()
    lines4, labels4 = ax4.get_legend_handles_labels()
    ax1.legend(lines1 + lines2 + lines3 + lines4, labels1 + labels2 + labels3 + labels4, loc='upper left')

    # Grid for readability
    ax1.grid(axis='y', alpha=0.3, linestyle='--')

    # Add test queries at the bottom with reduced spacing
    sorted_queries = sorted(test_queries)
    query_lines = ["Test Queries:"]
    for q in sorted_queries:
        query_lines.append(f"• {q}")

    # Join with minimal spacing (using figtext with lineheight control)
    query_text = "\n".join(query_lines)
    plt.figtext(0.1, 0.02, query_text, fontsize=9, va='top',
                linespacing=1.2)  # Reduced line spacing

    # Adjust layout to make room for queries
    plt.subplots_adjust(bottom=0.25)

    # Save figure
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    plt.close()

    logger.info(f"Visualization saved to {output_file}")
    return str(output_file)
