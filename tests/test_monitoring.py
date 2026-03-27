"""Tests for monitoring service."""
from datetime import datetime, timedelta

import pytest

from services.monitoring import (
    MetricValue,
    MetricSummary,
    MetricsStore,
    MetricsRegistry,
    RequestContext,
    HealthStatus,
    get_metrics,
    get_health_status,
)


class TestMetricValue:
    """Test cases for MetricValue dataclass."""

    def test_metric_value_creation(self):
        """Test MetricValue creation."""
        timestamp = datetime.utcnow()
        value = MetricValue(value=10.5, timestamp=timestamp)

        assert value.value == 10.5
        assert value.timestamp == timestamp


class TestMetricSummary:
    """Test cases for MetricSummary dataclass."""

    def test_metric_summary_creation(self):
        """Test MetricSummary creation."""
        summary = MetricSummary(
            count=100,
            min=1.0,
            max=100.0,
            avg=50.5,
            p95=95.0,
            p99=99.0,
            last_value=75.5,
            last_updated=datetime.utcnow(),
        )

        assert summary.count == 100
        assert summary.min == 1.0
        assert summary.max == 100.0
        assert summary.avg == 50.5
        assert summary.p95 == 95.0
        assert summary.p99 == 99.0
        assert summary.last_value == 75.5


class TestMetricsStore:
    """Test cases for MetricsStore class."""

    @pytest.fixture
    def store(self):
        """Create MetricsStore instance for testing."""
        return MetricsStore(max_values=10)

    def test_add_metric_value(self, store):
        """Test adding a metric value."""
        timestamp = datetime.utcnow()
        store.add("test_metric", 10.5, timestamp)

        summary = store.get_summary("test_metric")
        assert summary is not None
        assert summary.count == 1
        assert summary.last_value == 10.5

    def test_get_summary_empty_metric(self, store):
        """Test getting summary for non-existent metric."""
        summary = store.get_summary("nonexistent")
        assert summary is None

    def test_add_multiple_values(self, store):
        """Test adding multiple metric values."""
        store.add("test_metric", 1.0)
        store.add("test_metric", 2.0)
        store.add("test_metric", 3.0)

        summary = store.get_summary("test_metric")
        assert summary.count == 3
        assert summary.min == 1.0
        assert summary.max == 3.0
        assert summary.avg == 2.0

    def test_max_values_limit(self, store):
        """Test max values limit enforcement."""
        # Add more values than max_values
        for i in range(15):
            store.add("test_metric", float(i))

        summary = store.get_summary("test_metric")
        assert summary.count == 10  # Should be limited

    def test_get_summary_with_time_filter(self, store):
        """Test getting summary with time filtering."""
        now = datetime.utcnow()
        past = now - timedelta(hours=1)

        store.add("test_metric", 1.0, timestamp=past)
        store.add("test_metric", 2.0, timestamp=now)

        # Only get values from last 30 minutes
        since = now - timedelta(minutes=30)
        summary = store.get_summary("test_metric", since=since)

        assert summary.count == 1
        assert summary.last_value == 2.0

    def test_get_all_metrics(self, store):
        """Test getting all metric names."""
        store.add("metric1", 1.0)
        store.add("metric2", 2.0)
        store.add("metric3", 3.0)

        metrics = store.get_all_metrics()
        assert len(metrics) == 3
        assert "metric1" in metrics
        assert "metric2" in metrics
        assert "metric3" in metrics

    def test_clear_specific_metric(self, store):
        """Test clearing a specific metric."""
        store.add("test_metric", 1.0)
        store.add("test_metric", 2.0)

        store.clear("test_metric")

        summary = store.get_summary("test_metric")
        assert summary is None

    def test_clear_all_metrics(self, store):
        """Test clearing all metrics."""
        store.add("metric1", 1.0)
        store.add("metric2", 2.0)

        store.clear(None)

        assert len(store.get_all_metrics()) == 0


class TestMetricsRegistry:
    """Test cases for MetricsRegistry class."""

    @pytest.fixture
    def registry(self):
        """Create MetricsRegistry instance for testing."""
        return MetricsRegistry()

    def test_increment_counter(self, registry):
        """Test incrementing a counter metric."""
        registry.increment("test_counter", 1.0)

        assert registry.get_counter("test_counter") == 1.0

        # Increment again
        registry.increment("test_counter", 2.0)
        assert registry.get_counter("test_counter") == 3.0

    def test_increment_with_labels(self, registry):
        """Test incrementing counter with labels."""
        registry.increment("test_counter", 1.0, labels={"endpoint": "/api/v1/vps"})

        counter = registry.get_counter("test_counter", labels={"endpoint": "/api/v1/vps"})
        assert counter == 1.0

    def test_set_gauge(self, registry):
        """Test setting a gauge metric."""
        registry.gauge("test_gauge", 50.0)

        assert registry.get_gauge("test_gauge") == 50.0

        # Set again
        registry.gauge("test_gauge", 75.0)
        assert registry.get_gauge("test_gauge") == 75.0

    def test_gauge_with_labels(self, registry):
        """Test setting gauge with labels."""
        registry.gauge("test_gauge", 50.0, labels={"vps_id": "1"})

        gauge = registry.get_gauge("test_gauge", labels={"vps_id": "1"})
        assert gauge == 50.0

    def test_record_timing(self, registry):
        """Test recording a timing metric."""
        registry.timing("test_timing", 1.5)
        registry.timing("test_timing", 2.5)
        registry.timing("test_timing", 3.0)

        summary = registry.get_summary("test_timing")
        assert summary.count == 3
        assert summary.min == 1.5
        assert summary.max == 3.0

    def test_timing_with_labels(self, registry):
        """Test recording timing with labels."""
        registry.timing("test_timing", 1.5, labels={"method": "GET"})

        summary = registry.get_summary("test_timing", labels={"method": "GET"})
        assert summary is not None
        assert summary.last_value == 1.5

    def test_get_summary(self, registry):
        """Test getting metric summary from registry."""
        for i in range(10):
            registry.timing("test_timing", float(i))

        summary = registry.get_summary("test_timing")
        assert summary.count == 10
        assert summary.min == 0.0
        assert summary.max == 9.0

    def test_get_summary_with_time_filter(self, registry):
        """Test getting summary with time filter."""
        now = datetime.utcnow()

        # Add old value
        old_time = now - timedelta(hours=1)
        registry.timing("test_timing", 1.0, timestamp=old_time)

        # Add new value
        registry.timing("test_timing", 2.0, timestamp=now)

        # Get summary since 30 minutes ago
        since = now - timedelta(minutes=30)
        summary = registry.get_summary("test_timing", since=since)

        assert summary.count == 1
        assert summary.last_value == 2.0

    def test_get_all_summaries(self, registry):
        """Test getting all metric summaries."""
        registry.increment("counter1", 1.0)
        registry.gauge("gauge1", 50.0)
        registry.timing("timing1", 1.5)

        summaries = registry.get_all_summaries()

        assert "counter1" in summaries
        assert "gauge1" in summaries
        assert "timing1" in summaries

    def test_reset(self, registry):
        """Test resetting metrics registry."""
        registry.increment("test_counter", 1.0)
        registry.gauge("test_gauge", 50.0)

        registry.reset()

        assert registry.get_counter("test_counter") is None
        assert registry.get_gauge("test_gauge") is None
        assert len(registry.get_all_summaries()) == 0

    def test_format_name(self, registry):
        """Test metric name formatting."""
        # Without labels
        name = registry._format_name("test_metric", None)
        assert name == "test_metric"

        # With labels
        name = registry._format_name("test_metric", {"label": "value"})
        assert "label" in name
        assert '"value"' in name


class TestRequestContext:
    """Test cases for RequestContext class."""

    def test_request_context_creation(self):
        """Test RequestContext creation."""
        context = RequestContext("req-123", "GET", "/api/v1/vps")

        assert context.request_id == "req-123"
        assert context.method == "GET"
        assert context.path == "/api/v1/vps"
        assert context.labels["method"] == "GET"
        assert context.labels["path"] == "/api/v1/vps"

    def test_record_completion(self):
        """Test recording request completion."""
        context = RequestContext("req-123", "GET", "/api/v1/vps")

        # Record completion with 200 status
        duration = context.record_completion(200)

        assert duration >= 0
        assert duration < 1.0  # Should be very fast


class TestHealthStatus:
    """Test cases for HealthStatus class."""

    @pytest.fixture
    def health(self):
        """Create HealthStatus instance for testing."""
        return HealthStatus()

    def test_set_status(self, health):
        """Test setting health check status."""
        health.set_status("database", "healthy", "Database connected")

        status = health.get_status("database")
        assert status["status"] == "healthy"
        assert status["message"] == "Database connected"

    def test_set_status_with_details(self, health):
        """Test setting status with details."""
        health.set_status(
            "ssh_pool",
            "degraded",
            "Some connections failed",
            details={"failed": 2, "total": 10},
        )

        status = health.get_status("ssh_pool")
        assert status["status"] == "degraded"
        assert status["details"]["failed"] == 2

    def test_get_overall_status_healthy(self, health):
        """Test overall status when all checks are healthy."""
        health.set_status("check1", "healthy")
        health.set_status("check2", "healthy")

        status = health.get_status()
        assert status["status"] == "healthy"

    def test_get_overall_status_unhealthy(self, health):
        """Test overall status when one check is unhealthy."""
        health.set_status("check1", "healthy")
        health.set_status("check2", "unhealthy")

        status = health.get_status()
        assert status["status"] == "unhealthy"

    def test_get_overall_status_degraded(self, health):
        """Test overall status when one check is degraded."""
        health.set_status("check1", "healthy")
        health.set_status("check2", "degraded")

        status = health.get_status()
        assert status["status"] == "degraded"

    def test_get_overall_status_no_checks(self, health):
        """Test overall status when no checks exist."""
        status = health.get_status()
        assert status["status"] == "healthy"

    def test_is_healthy(self, health):
        """Test is_healthy method."""
        health.set_status("check1", "healthy")
        assert health.is_healthy() is True

        health.set_status("check1", "unhealthy")
        assert health.is_healthy() is False

    def test_is_ready(self, health):
        """Test is_ready method."""
        health.set_status("check1", "healthy")
        assert health.is_ready() is True

        health.set_status("check1", "degraded")
        assert health.is_ready() is True  # Degraded is still ready

        health.set_status("check1", "unhealthy")
        assert health.is_ready() is False


class TestGlobalFunctions:
    """Test cases for global functions."""

    @pytest.fixture(autouse=True)
    def reset_globals(self):
        """Reset global instances before each test."""
        from services import monitoring
        monitoring._metrics_registry = None
        monitoring._health_status = None
        yield
        monitoring._metrics_registry = None
        monitoring._health_status = None

    def test_get_metrics_creates_singleton(self):
        """Test get_metrics creates singleton instance."""
        metrics1 = get_metrics()
        metrics2 = get_metrics()

        assert metrics1 is metrics2
        assert isinstance(metrics1, MetricsRegistry)

    def test_get_health_status_creates_singleton(self):
        """Test get_health_status creates singleton instance."""
        health1 = get_health_status()
        health2 = get_health_status()

        assert health1 is health2
        assert isinstance(health1, HealthStatus)
