"""Metrics and observability tracking.

Performance metrics tracking (latency, token usage, confidence scores).
Based on specs/001-we-are-building/tasks.md T031
Constitution Principle V: Observable and Debuggable
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import mean, median, stdev

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class LatencyMetric:
    """Latency measurement."""

    operation: str
    latency_ms: int
    timestamp: datetime


@dataclass
class TokenUsageMetric:
    """Token usage measurement."""

    operation: str  # "query", "pdf_extraction", etc.
    provider: str  # "claude", "chatgpt", "gemini"
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    timestamp: datetime


@dataclass
class ConfidenceMetric:
    """Confidence score measurement."""

    query_id: str
    llm_confidence: float
    rag_score: float
    validation_passed: bool
    timestamp: datetime


@dataclass
class MetricsSummary:
    """Summary statistics for metrics."""

    count: int
    mean: float
    median: float
    min: float
    max: float
    std_dev: float
    p50: float
    p95: float
    p99: float


class MetricsCollector:
    """Collects and aggregates performance metrics."""

    def __init__(self) -> None:
        """Initialize metrics collector."""
        self.latency_metrics: list[LatencyMetric] = []
        self.token_metrics: list[TokenUsageMetric] = []
        self.confidence_metrics: list[ConfidenceMetric] = []

    def record_latency(self, operation: str, latency_ms: int) -> None:
        """Record latency metric.

        Args:
            operation: Operation name
            latency_ms: Latency in milliseconds
        """
        metric = LatencyMetric(
            operation=operation,
            latency_ms=latency_ms,
            timestamp=datetime.now(UTC),
        )
        self.latency_metrics.append(metric)

        logger.info(
            "latency_recorded",
            operation=operation,
            latency_ms=latency_ms,
        )

    def record_token_usage(
        self,
        operation: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        estimated_cost_usd: float,
    ) -> None:
        """Record token usage metric.

        Args:
            operation: Operation name
            provider: LLM provider
            prompt_tokens: Prompt token count
            completion_tokens: Completion token count
            estimated_cost_usd: Estimated cost
        """
        metric = TokenUsageMetric(
            operation=operation,
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            estimated_cost_usd=estimated_cost_usd,
            timestamp=datetime.now(UTC),
        )
        self.token_metrics.append(metric)

        logger.info(
            "token_usage_recorded",
            operation=operation,
            provider=provider,
            total_tokens=metric.total_tokens,
            cost_usd=estimated_cost_usd,
        )

    def record_confidence(
        self,
        query_id: str,
        llm_confidence: float,
        rag_score: float,
        validation_passed: bool,
    ) -> None:
        """Record confidence metric.

        Args:
            query_id: Query ID
            llm_confidence: LLM confidence score
            rag_score: RAG relevance score
            validation_passed: Whether validation passed
        """
        metric = ConfidenceMetric(
            query_id=query_id,
            llm_confidence=llm_confidence,
            rag_score=rag_score,
            validation_passed=validation_passed,
            timestamp=datetime.now(UTC),
        )
        self.confidence_metrics.append(metric)

        logger.info(
            "confidence_recorded",
            query_id=query_id,
            llm_confidence=llm_confidence,
            rag_score=rag_score,
            validation_passed=validation_passed,
        )

    def get_latency_summary(
        self, operation: str | None = None
    ) -> MetricsSummary | None:
        """Get latency summary statistics.

        Args:
            operation: Filter by operation (optional)

        Returns:
            Summary statistics or None if no data
        """
        metrics = self.latency_metrics
        if operation:
            metrics = [m for m in metrics if m.operation == operation]

        if not metrics:
            return None

        values = [float(m.latency_ms) for m in metrics]
        return self._compute_summary(values)

    def get_token_usage_summary(
        self, operation: str | None = None, provider: str | None = None
    ) -> dict[str, float]:
        """Get token usage summary.

        Args:
            operation: Filter by operation (optional)
            provider: Filter by provider (optional)

        Returns:
            Summary dictionary
        """
        metrics = self.token_metrics

        if operation:
            metrics = [m for m in metrics if m.operation == operation]
        if provider:
            metrics = [m for m in metrics if m.provider == provider]

        if not metrics:
            return {}

        total_tokens = sum(m.total_tokens for m in metrics)
        total_cost = sum(m.estimated_cost_usd for m in metrics)

        return {
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost,
            "count": len(metrics),
            "avg_tokens_per_request": total_tokens / len(metrics),
            "avg_cost_per_request": total_cost / len(metrics),
        }

    def get_confidence_summary(self) -> dict[str, float]:
        """Get confidence score summary.

        Returns:
            Summary dictionary
        """
        if not self.confidence_metrics:
            return {}

        llm_scores = [m.llm_confidence for m in self.confidence_metrics]
        rag_scores = [m.rag_score for m in self.confidence_metrics]
        validation_rate = (
            sum(1 for m in self.confidence_metrics if m.validation_passed)
            / len(self.confidence_metrics)
        )

        return {
            "avg_llm_confidence": mean(llm_scores),
            "avg_rag_score": mean(rag_scores),
            "validation_pass_rate": validation_rate,
            "count": len(self.confidence_metrics),
        }

    def _compute_summary(self, values: list[float]) -> MetricsSummary:
        """Compute summary statistics.

        Args:
            values: List of numeric values

        Returns:
            Summary statistics
        """
        sorted_values = sorted(values)
        count = len(sorted_values)

        return MetricsSummary(
            count=count,
            mean=mean(values),
            median=median(values),
            min=min(values),
            max=max(values),
            std_dev=stdev(values) if count > 1 else 0.0,
            p50=self._percentile(sorted_values, 50),
            p95=self._percentile(sorted_values, 95),
            p99=self._percentile(sorted_values, 99),
        )

    def _percentile(self, sorted_values: list[float], percentile: int) -> float:
        """Calculate percentile.

        Args:
            sorted_values: Sorted list of values
            percentile: Percentile to calculate (0-100)

        Returns:
            Percentile value
        """
        if not sorted_values:
            return 0.0

        index = int((percentile / 100) * len(sorted_values))
        index = min(index, len(sorted_values) - 1)
        return sorted_values[index]

    def clear(self) -> None:
        """Clear all metrics."""
        self.latency_metrics.clear()
        self.token_metrics.clear()
        self.confidence_metrics.clear()

        logger.info("metrics_cleared")


# Global metrics collector
_metrics_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    """Get global metrics collector.

    Returns:
        MetricsCollector instance
    """
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector
