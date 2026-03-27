"""Monitoring service for tracking application metrics."""
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from threading import Lock


@dataclass
class MetricValue:
    """Single metric value with timestamp."""

    value: float
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class MetricSummary:
    """Summary statistics for a metric."""

    count: int
    min: float
    max: float
    avg: float
    p95: float
    p99: float
    last_value: float
    last_updated: datetime


class MetricsStore:
    """Thread-safe storage for metrics."""

    def __init__(self, max_values: int = 10000):
        """
        Initialize metrics store.

        Args:
            max_values: Maximum values to keep per metric.
        """
        self._metrics: Dict[str, List[MetricValue]] = defaultdict(list)
        self._max_values = max_values
        self._lock = Lock()

    def add(self, name: str, value: float, timestamp: Optional[datetime] = None) -> None:
        """
        Add a metric value.

        Args:
            name: Metric name.
            value: Metric value.
            timestamp: Optional timestamp (defaults to now).
        """
        if timestamp is None:
            timestamp = datetime.utcnow()

        with self._lock:
            self._metrics[name].append(MetricValue(value=value, timestamp=timestamp))

            # Trim old values if needed
            if len(self._metrics[name]) > self._max_values:
                self._metrics[name] = self._metrics[name][-self._max_values:]

    def get_summary(
        self,
        name: str,
        since: Optional[datetime] = None,
    ) -> Optional[MetricSummary]:
        """
        Get summary statistics for a metric.

        Args:
            name: Metric name.
            since: Optional start time for filtering.

        Returns:
            MetricSummary or None if no values exist.
        """
        with self._lock:
            values = self._metrics.get(name, [])

            if not values:
                return None

            # Filter by time if needed
            if since is not None:
                values = [v for v in values if v.timestamp >= since]

            if not values:
                return None

            sorted_values = sorted([v.value for v in values])
            count = len(sorted_values)

            # Calculate percentiles
            p95_idx = int(count * 0.95)
            p99_idx = int(count * 0.99)

            return MetricSummary(
                count=count,
                min=min(sorted_values),
                max=max(sorted_values),
                avg=sum(sorted_values) / count,
                p95=sorted_values[p95_idx] if p95_idx < count else sorted_values[-1],
                p99=sorted_values[p99_idx] if p99_idx < count else sorted_values[-1],
                last_value=values[-1].value,
                last_updated=values[-1].timestamp,
            )

    def get_all_metrics(self) -> List[str]:
        """Get all metric names."""
        with self._lock:
            return list(self._metrics.keys())

    def clear(self, name: Optional[str] = None) -> None:
        """
        Clear metric values.

        Args:
            name: Optional metric name. If None, clears all metrics.
        """
        with self._lock:
            if name:
                self._metrics.pop(name, None)
            else:
                self._metrics.clear()


class MetricsRegistry:
    """Registry for tracking application metrics."""

    def __init__(self):
        """Initialize metrics registry."""
        self._store = MetricsStore()
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
        self._lock = Lock()

    def increment(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """
        Increment a counter metric.

        Args:
            name: Metric name.
            value: Value to increment by.
            labels: Optional labels for the metric.
        """
        full_name = self._format_name(name, labels)
        with self._lock:
            self._counters[full_name] += value
        self._store.add(full_name, self._counters[full_name])

    def gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """
        Set a gauge metric.

        Args:
            name: Metric name.
            value: Gauge value.
            labels: Optional labels for the metric.
        """
        full_name = self._format_name(name, labels)
        with self._lock:
            self._gauges[full_name] = value
        self._store.add(full_name, value)

    def timing(self, name: str, duration: float, labels: Optional[Dict[str, str]] = None) -> None:
        """
        Record a timing metric.

        Args:
            name: Metric name.
            duration: Duration in seconds.
            labels: Optional labels for the metric.
        """
        full_name = self._format_name(name, labels)
        self._store.add(full_name, duration)

    def get_counter(self, name: str, labels: Optional[Dict[str, str]] = None) -> Optional[int]:
        """
        Get a counter value.

        Args:
            name: Metric name.
            labels: Optional labels for the metric.

        Returns:
            Counter value or None if not found.
        """
        full_name = self._format_name(name, labels)
        return self._counters.get(full_name)

    def get_gauge(self, name: str, labels: Optional[Dict[str, str]] = None) -> Optional[float]:
        """
        Get a gauge value.

        Args:
            name: Metric name.
            labels: Optional labels for the metric.

        Returns:
            Gauge value or None if not found.
        """
        full_name = self._format_name(name, labels)
        return self._gauges.get(full_name)

    def get_summary(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None,
        since: Optional[datetime] = None,
    ) -> Optional[MetricSummary]:
        """
        Get metric summary.

        Args:
            name: Metric name.
            labels: Optional labels for the metric.
            since: Optional start time for filtering.

        Returns:
            MetricSummary or None if no values exist.
        """
        full_name = self._format_name(name, labels)
        return self._store.get_summary(full_name, since)

    def get_all_summaries(self, since: Optional[datetime] = None) -> Dict[str, MetricSummary]:
        """
        Get summaries for all metrics.

        Args:
            since: Optional start time for filtering.

        Returns:
            Dictionary mapping metric names to summaries.
        """
        summaries = {}
        for name in self._store.get_all_metrics():
            summary = self._store.get_summary(name, since)
            if summary:
                summaries[name] = summary
        return summaries

    def reset(self) -> None:
        """Reset all metrics."""
        self._store.clear()
        with self._lock:
            self._counters.clear()
            self._gauges.clear()

    def _format_name(self, name: str, labels: Optional[Dict[str, str]] = None) -> str:
        """
        Format metric name with labels.

        Args:
            name: Base metric name.
            labels: Optional labels.

        Returns:
            Formatted metric name.
        """
        if labels:
            label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
            return f"{name}{{{label_str}}}"
        return name


# Global metrics registry
_metrics_registry: Optional[MetricsRegistry] = None


def get_metrics() -> MetricsRegistry:
    """Get or create global metrics registry."""
    global _metrics_registry
    if _metrics_registry is None:
        _metrics_registry = MetricsRegistry()
    return _metrics_registry


class RequestContext:
    """Context for tracking request metrics."""

    def __init__(self, request_id: str, method: str, path: str):
        """
        Initialize request context.

        Args:
            request_id: Unique request identifier.
            method: HTTP method.
            path: Request path.
        """
        self.request_id = request_id
        self.method = method
        self.path = path
        self.start_time = time.time()
        self.labels = {
            "method": method,
            "path": path,
        }

    def record_completion(self, status_code: int) -> float:
        """
        Record request completion metrics.

        Args:
            status_code: HTTP status code.

        Returns:
            Request duration in seconds.
        """
        duration = time.time() - self.start_time
        metrics = get_metrics()

        # Record request duration
        labels = {
            **self.labels,
            "status": str(status_code),
        }
        metrics.timing("http_request_duration", duration, labels)

        # Increment request counter
        metrics.increment("http_requests_total", 1.0, labels)

        # Track errors
        if status_code >= 500:
            metrics.increment("http_errors_total", 1.0, labels)

        return duration


class HealthStatus:
    """Health check status."""

    def __init__(self):
        """Initialize health status."""
        self._checks: Dict[str, Dict[str, Any]] = {}

    def set_status(
        self,
        name: str,
        status: str,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Set health check status.

        Args:
            name: Check name.
            status: Status (healthy, unhealthy, degraded).
            message: Optional message.
            details: Optional additional details.
        """
        self._checks[name] = {
            "status": status,
            "message": message,
            "details": details or {},
            "timestamp": datetime.utcnow().isoformat(),
        }

    def get_status(self, name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get health status.

        Args:
            name: Optional check name. If None, returns overall status.

        Returns:
            Health status information.
        """
        if name:
            return self._checks.get(name, {"status": "unknown"})

        # Calculate overall status
        if not self._checks:
            overall = "healthy"
        else:
            statuses = [check["status"] for check in self._checks.values()]
            if any(s == "unhealthy" for s in statuses):
                overall = "unhealthy"
            elif any(s == "degraded" for s in statuses):
                overall = "degraded"
            else:
                overall = "healthy"

        return {
            "status": overall,
            "checks": self._checks,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def is_healthy(self) -> bool:
        """Check if system is healthy."""
        overall = self.get_status()
        return overall["status"] == "healthy"

    def is_ready(self) -> bool:
        """Check if system is ready to accept traffic."""
        # Readiness checks can be different from liveness
        overall = self.get_status()
        return overall["status"] in ("healthy", "degraded")


# Global health status
_health_status: Optional[HealthStatus] = None


def get_health_status() -> HealthStatus:
    """Get or create global health status."""
    global _health_status
    if _health_status is None:
        _health_status = HealthStatus()
    return _health_status
