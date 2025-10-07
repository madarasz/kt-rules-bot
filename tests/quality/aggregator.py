"""Aggregation utilities for multi-run quality test results.

Computes statistics across multiple test runs.
"""

from collections import defaultdict
from typing import Dict, List
import statistics

from tests.quality.models import QualityTestSuite, TestResult
from src.lib.logging import get_logger

logger = get_logger(__name__)


class MultiRunAggregator:
    """Aggregates statistics across multiple quality test runs."""

    def __init__(self, run_suites: List[QualityTestSuite]):
        """Initialize aggregator with multiple test run results.

        Args:
            run_suites: List of QualityTestSuite from multiple runs
        """
        self.run_suites = run_suites
        self.run_count = len(run_suites)

        if self.run_count == 0:
            raise ValueError("Cannot aggregate zero runs")

        # Group results by model
        self._model_results: Dict[str, List[TestResult]] = defaultdict(list)
        for suite in run_suites:
            for result in suite.test_results:
                self._model_results[result.model].append(result)

    @property
    def models(self) -> List[str]:
        """Get list of models tested."""
        return sorted(self._model_results.keys())

    def get_model_averages(self, model: str) -> Dict[str, float]:
        """Get averaged metrics for a specific model.

        Args:
            model: Model name

        Returns:
            Dict with keys: score_pct, time, cost, chars, llm_error_pct
        """
        results = self._model_results.get(model, [])
        if not results:
            return {
                'score_pct': 0.0,
                'time': 0.0,
                'cost': 0.0,
                'chars': 0.0,
                'llm_error_pct': 0.0,
            }

        # Calculate score percentages for each result
        score_pcts = []
        llm_error_pcts = []
        for result in results:
            if result.max_score > 0:
                score_pcts.append((result.score / result.max_score) * 100)
                llm_error_pcts.append(
                    (result.points_lost_to_llm_error / result.max_score) * 100
                )
            else:
                score_pcts.append(0.0)
                llm_error_pcts.append(0.0)

        return {
            'score_pct': statistics.mean(score_pcts) if score_pcts else 0.0,
            'time': statistics.mean(r.generation_time_seconds for r in results),
            'cost': statistics.mean(r.cost_usd for r in results),
            'chars': statistics.mean(r.response_chars for r in results),
            'llm_error_pct': statistics.mean(llm_error_pcts) if llm_error_pcts else 0.0,
        }

    def get_model_std_devs(self, model: str) -> Dict[str, float]:
        """Get standard deviations for a specific model.

        Args:
            model: Model name

        Returns:
            Dict with keys: score_pct, time, cost, chars, llm_error_pct
        """
        results = self._model_results.get(model, [])
        if not results or len(results) < 2:
            return {
                'score_pct': 0.0,
                'time': 0.0,
                'cost': 0.0,
                'chars': 0.0,
                'llm_error_pct': 0.0,
            }

        # Calculate score percentages for each result
        score_pcts = []
        llm_error_pcts = []
        for result in results:
            if result.max_score > 0:
                score_pcts.append((result.score / result.max_score) * 100)
                llm_error_pcts.append(
                    (result.points_lost_to_llm_error / result.max_score) * 100
                )
            else:
                score_pcts.append(0.0)
                llm_error_pcts.append(0.0)

        return {
            'score_pct': statistics.stdev(score_pcts) if len(score_pcts) > 1 else 0.0,
            'time': statistics.stdev(r.generation_time_seconds for r in results),
            'cost': statistics.stdev(r.cost_usd for r in results),
            'chars': statistics.stdev(r.response_chars for r in results),
            'llm_error_pct': statistics.stdev(llm_error_pcts) if len(llm_error_pcts) > 1 else 0.0,
        }

    def get_model_raw_values(self, model: str, metric: str) -> List[float]:
        """Get raw values for a specific metric across all runs.

        Args:
            model: Model name
            metric: Metric name (score_pct, time, cost, chars, llm_error_pct)

        Returns:
            List of raw values for the metric
        """
        results = self._model_results.get(model, [])
        if not results:
            return []

        if metric == 'score_pct':
            return [
                (r.score / r.max_score) * 100 if r.max_score > 0 else 0.0
                for r in results
            ]
        elif metric == 'llm_error_pct':
            return [
                (r.points_lost_to_llm_error / r.max_score) * 100 if r.max_score > 0 else 0.0
                for r in results
            ]
        elif metric == 'time':
            return [r.generation_time_seconds for r in results]
        elif metric == 'cost':
            return [r.cost_usd for r in results]
        elif metric == 'chars':
            return [float(r.response_chars) for r in results]
        else:
            raise ValueError(f"Unknown metric: {metric}")

    def get_overall_averages(self) -> Dict[str, float]:
        """Get overall averages across all models and runs.

        Returns:
            Dict with keys: score_pct, time, cost, chars, llm_error_pct
        """
        all_score_pcts = []
        all_llm_error_pcts = []
        all_times = []
        all_costs = []
        all_chars = []

        for suite in self.run_suites:
            for result in suite.test_results:
                if result.max_score > 0:
                    all_score_pcts.append((result.score / result.max_score) * 100)
                    all_llm_error_pcts.append(
                        (result.points_lost_to_llm_error / result.max_score) * 100
                    )
                else:
                    all_score_pcts.append(0.0)
                    all_llm_error_pcts.append(0.0)

                all_times.append(result.generation_time_seconds)
                all_costs.append(result.cost_usd)
                all_chars.append(result.response_chars)

        return {
            'score_pct': statistics.mean(all_score_pcts) if all_score_pcts else 0.0,
            'time': statistics.mean(all_times) if all_times else 0.0,
            'cost': statistics.mean(all_costs) if all_costs else 0.0,
            'chars': statistics.mean(all_chars) if all_chars else 0.0,
            'llm_error_pct': statistics.mean(all_llm_error_pcts) if all_llm_error_pcts else 0.0,
        }

    def get_overall_std_devs(self) -> Dict[str, float]:
        """Get overall standard deviations across all models and runs.

        Returns:
            Dict with keys: score_pct, time, cost, chars, llm_error_pct
        """
        all_score_pcts = []
        all_llm_error_pcts = []
        all_times = []
        all_costs = []
        all_chars = []

        for suite in self.run_suites:
            for result in suite.test_results:
                if result.max_score > 0:
                    all_score_pcts.append((result.score / result.max_score) * 100)
                    all_llm_error_pcts.append(
                        (result.points_lost_to_llm_error / result.max_score) * 100
                    )
                else:
                    all_score_pcts.append(0.0)
                    all_llm_error_pcts.append(0.0)

                all_times.append(result.generation_time_seconds)
                all_costs.append(result.cost_usd)
                all_chars.append(result.response_chars)

        return {
            'score_pct': statistics.stdev(all_score_pcts) if len(all_score_pcts) > 1 else 0.0,
            'time': statistics.stdev(all_times) if len(all_times) > 1 else 0.0,
            'cost': statistics.stdev(all_costs) if len(all_costs) > 1 else 0.0,
            'chars': statistics.stdev(all_chars) if len(all_chars) > 1 else 0.0,
            'llm_error_pct': statistics.stdev(all_llm_error_pcts) if len(all_llm_error_pcts) > 1 else 0.0,
        }
