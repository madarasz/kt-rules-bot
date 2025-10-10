"""Chart generation for quality test reports."""

import os
from typing import List, Optional, Dict, Set
import numpy as np
from pathlib import Path

try:
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

from tests.quality.reporting.report_models import (
    QualityReport,
    IndividualTestResult,
)


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
        
        # Generate per-test-case charts for multi-model scenarios
        if self.report.is_multi_test_case and self.report.is_multi_model:
            for test_id, test_case_report in self.report.per_test_case_reports.items():
                chart_path = self._generate_test_case_chart(test_id, test_case_report.results)
                if chart_path:
                    test_case_report.chart_path = chart_path

    def _generate_main_chart(self) -> Optional[str]:
        """Generate the main visualization chart comparing models."""
        if not MATPLOTLIB_AVAILABLE or not self.report.is_multi_model:
            return None
        
        chart_path = os.path.join(self.report_dir, "chart.png")
        
        # Aggregate data by model
        model_data = {}
        test_queries = set()
        
        for result in self.report.results:
            # Remove escape characters from query text for display
            clean_query = result.query.replace('\\"', '"').replace("\\'", "'")
            test_queries.add(clean_query)
            
            if result.model not in model_data:
                model_data[result.model] = {
                    'scores': [],
                    'times': [],
                    'costs': [],
                    'chars': []
                }
            model_data[result.model]['scores'].append(result.score_percentage)
            model_data[result.model]['times'].append(result.generation_time_seconds)
            model_data[result.model]['costs'].append(result.cost_usd)
            model_data[result.model]['chars'].append(result.output_char_count)
        
        models = list(model_data.keys())
        avg_scores = [np.mean(model_data[m]['scores']) for m in models]
        avg_times = [np.mean(model_data[m]['times']) for m in models]
        avg_costs = [np.mean(model_data[m]['costs']) for m in models]
        avg_chars = [np.mean(model_data[m]['chars']) for m in models]
        
        # Error bars for multi-run scenarios
        std_scores = [np.std(model_data[m]['scores']) if len(model_data[m]['scores']) > 1 else 0 for m in models]
        std_times = [np.std(model_data[m]['times']) if len(model_data[m]['times']) > 1 else 0 for m in models]
        std_costs = [np.std(model_data[m]['costs']) if len(model_data[m]['costs']) > 1 else 0 for m in models]
        std_chars = [np.std(model_data[m]['chars']) if len(model_data[m]['chars']) > 1 else 0 for m in models]
        
        return self._create_chart(
            chart_path=chart_path,
            models=models,
            avg_scores=avg_scores,
            avg_times=avg_times,
            avg_costs=avg_costs,
            avg_chars=avg_chars,
            std_scores=std_scores,
            std_times=std_times,
            std_costs=std_costs,
            std_chars=std_chars,
            test_queries=test_queries,
            title="Model Performance Comparison"
        )

    def _generate_test_case_chart(self, test_id: str, results: List[IndividualTestResult]) -> Optional[str]:
        """Generate a chart for a specific test case comparing models."""
        if not MATPLOTLIB_AVAILABLE or len(set(r.model for r in results)) <= 1:
            return None
        
        chart_path = os.path.join(self.report_dir, f"chart_{test_id}.png")
        
        # Aggregate data by model for this test case
        model_data = {}
        for result in results:
            if result.model not in model_data:
                model_data[result.model] = {
                    'scores': [],
                    'times': [],
                    'costs': [],
                    'chars': []
                }
            model_data[result.model]['scores'].append(result.score_percentage)
            model_data[result.model]['times'].append(result.generation_time_seconds)
            model_data[result.model]['costs'].append(result.cost_usd)
            model_data[result.model]['chars'].append(result.output_char_count)
        
        models = list(model_data.keys())
        avg_scores = [np.mean(model_data[m]['scores']) for m in models]
        avg_times = [np.mean(model_data[m]['times']) for m in models]
        avg_costs = [np.mean(model_data[m]['costs']) for m in models]
        avg_chars = [np.mean(model_data[m]['chars']) for m in models]
        
        # Error bars for multi-run scenarios
        std_scores = [np.std(model_data[m]['scores']) if len(model_data[m]['scores']) > 1 else 0 for m in models]
        std_times = [np.std(model_data[m]['times']) if len(model_data[m]['times']) > 1 else 0 for m in models]
        std_costs = [np.std(model_data[m]['costs']) if len(model_data[m]['costs']) > 1 else 0 for m in models]
        std_chars = [np.std(model_data[m]['chars']) if len(model_data[m]['chars']) > 1 else 0 for m in models]
        
        return self._create_chart(
            chart_path=chart_path,
            models=models,
            avg_scores=avg_scores,
            avg_times=avg_times,
            avg_costs=avg_costs,
            avg_chars=avg_chars,
            std_scores=std_scores,
            std_times=std_times,
            std_costs=std_costs,
            std_chars=std_chars,
            test_queries=set(),  # Don't include queries for per-test-case charts
            title=f"Model Performance Comparison - {test_id}"
        )

    def _create_chart(
        self,
        chart_path: str,
        models: List[str],
        avg_scores: List[float],
        avg_times: List[float],
        avg_costs: List[float],
        avg_chars: List[float],
        std_scores: List[float],
        std_times: List[float],
        std_costs: List[float],
        std_chars: List[float],
        test_queries: Set[str],
        title: str
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
        
        # Calculate LLM error percentages and earned scores
        earned_scores, llm_error_scores = self._calculate_score_breakdown(models)
        
        # Colors
        color_earned = '#2ecc71'  # Green for earned points
        color_llm_error = '#95a5a6'  # Grey for LLM errors
        color_time = '#3498db'  # Blue
        color_cost = '#e74c3c'  # Red
        color_chars = '#8B4513'  # Brown
        
        # Plot score % on primary axis - use stacked bars like the old visualization
        bars_earned = ax1.bar(pos1, earned_scores, width, 
                             label='Score % (earned)', color=color_earned, alpha=0.8)
        bars_llm_error = ax1.bar(pos1, llm_error_scores, width, bottom=earned_scores,
                                label='LLM Error %', color=color_llm_error, alpha=0.8)
        
        # Add error bars to the total (earned + LLM error) if multi-run
        if show_error_bars:
            total_scores = [e + l for e, l in zip(earned_scores, llm_error_scores)]
            ax1.errorbar(pos1, total_scores, yerr=std_scores, fmt='none', 
                        ecolor=color_llm_error, capsize=5, capthick=2, alpha=0.7)
        
        # Add individual data points for different queries if multi-run or multi-test-case
        if self.report.is_multi_run or self.report.is_multi_test_case:
            self._add_individual_points(ax1, pos1, models, 'scores')
        
        ax1.set_xlabel('Model', fontsize=12, fontweight='bold')
        ax1.set_ylabel('Score %', fontsize=12, fontweight='bold', color=color_earned)
        ax1.tick_params(axis='y', labelcolor=color_earned)
        ax1.set_ylim(0, 100)
        ax1.set_xticks(x)
        ax1.set_xticklabels(models, rotation=45, ha='right')
        
        # Create secondary axes
        ax2 = ax1.twinx()
        bars_time = ax2.bar(pos2, avg_times, width, label='Time (s)', color=color_time, alpha=0.8)
        if show_error_bars:
            ax2.errorbar(pos2, avg_times, yerr=std_times, fmt='none', 
                        ecolor=color_llm_error, capsize=5, capthick=2, alpha=0.7)
        if self.report.is_multi_run or self.report.is_multi_test_case:
            self._add_individual_points(ax2, pos2, models, 'times')
        ax2.set_ylabel('Time (seconds)', fontsize=12, fontweight='bold', color=color_time)
        ax2.tick_params(axis='y', labelcolor=color_time)
        # Ensure time axis starts from 0
        ax2.set_ylim(bottom=0)
        
        ax3 = ax1.twinx()
        ax3.spines['right'].set_position(('outward', 60))
        bars_cost = ax3.bar(pos3, avg_costs, width, label='Cost (USD)', color=color_cost, alpha=0.8)
        if show_error_bars:
            ax3.errorbar(pos3, avg_costs, yerr=std_costs, fmt='none', 
                        ecolor=color_llm_error, capsize=5, capthick=2, alpha=0.7)
        if self.report.is_multi_run or self.report.is_multi_test_case:
            self._add_individual_points(ax3, pos3, models, 'costs')
        ax3.set_ylabel('Cost (USD)', fontsize=12, fontweight='bold', color=color_cost)
        ax3.tick_params(axis='y', labelcolor=color_cost)
        # Ensure cost axis starts from 0
        ax3.set_ylim(bottom=0)
        
        ax4 = ax1.twinx()
        ax4.spines['right'].set_position(('outward', 120))
        bars_chars = ax4.bar(pos4, avg_chars, width, label='Characters', color=color_chars, alpha=0.8)
        if show_error_bars:
            ax4.errorbar(pos4, avg_chars, yerr=std_chars, fmt='none', 
                        ecolor=color_llm_error, capsize=5, capthick=2, alpha=0.7)
        if self.report.is_multi_run or self.report.is_multi_test_case:
            self._add_individual_points(ax4, pos4, models, 'chars')
        ax4.set_ylabel('Response Characters', fontsize=12, fontweight='bold', color=color_chars)
        ax4.tick_params(axis='y', labelcolor=color_chars)
        # Ensure characters axis starts from 0
        ax4.set_ylim(bottom=0)
        
        # Title and legend
        plt.title(title, fontsize=14, fontweight='bold', pad=20)
        
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        lines3, labels3 = ax3.get_legend_handles_labels()
        lines4, labels4 = ax4.get_legend_handles_labels()
        ax1.legend(lines1 + lines2 + lines3 + lines4, labels1 + labels2 + labels3 + labels4, loc='upper left')
        
        ax1.grid(axis='y', alpha=0.3, linestyle='--')
        
        # Add test queries at bottom if provided
        if test_queries:
            sorted_queries = sorted(test_queries)
            query_lines = ["Test Queries:"] + [f"• {q}" for q in sorted_queries]
            query_text = "\n".join(query_lines)
            plt.figtext(0.1, 0.02, query_text, fontsize=9, va='top', linespacing=1.2)
            plt.subplots_adjust(bottom=0.25)
        else:
            plt.tight_layout()
        
        plt.savefig(chart_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        return chart_path

    def _calculate_score_breakdown(self, models: List[str]) -> tuple:
        """Calculate earned scores and LLM error scores for each model."""
        earned_scores = []
        llm_error_scores = []
        
        for model in models:
            model_results = [r for r in self.report.results if r.model == model]
            if not model_results:
                earned_scores.append(0.0)
                llm_error_scores.append(0.0)
                continue
            
            total_score = sum(r.score for r in model_results)
            total_max = sum(r.max_score for r in model_results)
            
            # Calculate LLM errors - look for results with errors
            total_llm_error = 0
            for result in model_results:
                if result.error:  # LLM generation failed
                    total_llm_error += result.max_score - result.score
            
            if total_max > 0:
                earned_pct = (total_score / total_max) * 100
                llm_error_pct = (total_llm_error / total_max) * 100
            else:
                earned_pct = 0.0
                llm_error_pct = 0.0
            
            earned_scores.append(earned_pct)
            llm_error_scores.append(llm_error_pct)
        
        return earned_scores, llm_error_scores

    def _add_individual_points(self, ax, positions, models: List[str], metric: str):
        """Add individual data points as small circles on the chart."""
        for i, model in enumerate(models):
            model_results = [r for r in self.report.results if r.model == model]
            if not model_results:
                continue
            
            values = []
            for result in model_results:
                if metric == 'scores':
                    values.append(result.score_percentage)
                elif metric == 'times':
                    values.append(result.generation_time_seconds)
                elif metric == 'costs':
                    values.append(result.cost_usd)
                elif metric == 'chars':
                    values.append(result.output_char_count)
            
            if values:
                # Add small jitter to x-position to avoid overlapping points
                x_positions = [positions[i] + np.random.uniform(-0.02, 0.02) for _ in values]
                ax.scatter(x_positions, values, color='white', s=20, alpha=0.8, 
                          edgecolors='black', linewidth=1, zorder=10)