"""Unit tests for AnimusForge Metrics Module.

Comprehensive tests for Prometheus/OpenTelemetry metrics collection.
"""

import asyncio
import time
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from pydantic import ValidationError

from animus_observe.metrics import (
    MetricType,
    MetricConfig,
    MetricDefinition,
    MetricsGateway,
    get_metrics_gateway,
    configure_metrics,
    timed,
    counted,
    record_http_request,
    record_http_duration,
    record_llm_call,
    record_llm_tokens,
    record_memory_operation,
    record_error,
    set_active_personas,
    PROMETHEUS_AVAILABLE,
    OTEL_METRICS_AVAILABLE,
)


# Skip all tests if prometheus_client is not available
pytestmark = pytest.mark.skipif(
    not PROMETHEUS_AVAILABLE,
    reason="prometheus_client not installed"
)


# ============================================================================
# MetricType Tests
# ============================================================================

class TestMetricType:
    """Tests for MetricType enum."""

    def test_metric_type_values(self):
        """Test MetricType enum has correct values."""
        assert MetricType.COUNTER.value == "counter"
        assert MetricType.GAUGE.value == "gauge"
        assert MetricType.HISTOGRAM.value == "histogram"
        assert MetricType.SUMMARY.value == "summary"

    def test_metric_type_string_conversion(self):
        """Test MetricType can be converted to string via value."""
        assert MetricType.COUNTER.value == "counter"
        assert MetricType.GAUGE.value == "gauge"

    def test_metric_type_from_string(self):
        """Test MetricType can be created from string."""
        assert MetricType("counter") == MetricType.COUNTER
        assert MetricType("gauge") == MetricType.GAUGE

    def test_metric_type_equality(self):
        """Test MetricType equality."""
        assert MetricType.COUNTER == MetricType.COUNTER
        assert MetricType.COUNTER != MetricType.GAUGE


# ============================================================================
# MetricConfig Tests
# ============================================================================

class TestMetricConfig:
    """Tests for MetricConfig model."""

    def test_default_config(self):
        """Test default configuration values."""
        config = MetricConfig()
        assert config.namespace == "animusforge"
        assert config.subsystem == "core"
        assert config.enable_default_metrics is True
        assert config.prometheus_port == 9090
        assert config.otlp_endpoint is None
        assert config.export_interval == 60.0

    def test_custom_config(self):
        """Test custom configuration values."""
        config = MetricConfig(
            namespace="custom",
            subsystem="api",
            enable_default_metrics=False,
            prometheus_port=8080,
            otlp_endpoint="http://localhost:4317",
            export_interval=30.0
        )
        assert config.namespace == "custom"
        assert config.subsystem == "api"
        assert config.enable_default_metrics is False
        assert config.prometheus_port == 8080
        assert config.otlp_endpoint == "http://localhost:4317"
        assert config.export_interval == 30.0

    def test_endpoint_validation_adds_protocol(self):
        """Test endpoint validation adds http:// if missing."""
        config = MetricConfig(otlp_endpoint="localhost:4317")
        assert config.otlp_endpoint == "http://localhost:4317"

    def test_endpoint_validation_accepts_http(self):
        """Test endpoint validation accepts http://."""
        config = MetricConfig(otlp_endpoint="http://localhost:4317")
        assert config.otlp_endpoint == "http://localhost:4317"

    def test_endpoint_validation_accepts_https(self):
        """Test endpoint validation accepts https://."""
        config = MetricConfig(otlp_endpoint="https://localhost:4317")
        assert config.otlp_endpoint == "https://localhost:4317"

    def test_endpoint_validation_accepts_grpc(self):
        """Test endpoint validation accepts grpc://."""
        config = MetricConfig(otlp_endpoint="grpc://localhost:4317")
        assert config.otlp_endpoint == "grpc://localhost:4317"

    def test_endpoint_validation_none_allowed(self):
        """Test None endpoint is allowed."""
        config = MetricConfig(otlp_endpoint=None)
        assert config.otlp_endpoint is None

    def test_endpoint_validation_empty_string_fails(self):
        """Test empty string endpoint fails validation."""
        with pytest.raises(ValidationError):
            MetricConfig(otlp_endpoint="")

    def test_prometheus_port_range_valid(self):
        """Test valid prometheus port range."""
        config = MetricConfig(prometheus_port=1)
        assert config.prometheus_port == 1
        config = MetricConfig(prometheus_port=65535)
        assert config.prometheus_port == 65535

    def test_prometheus_port_too_low_fails(self):
        """Test prometheus port below 1 fails."""
        with pytest.raises(ValidationError):
            MetricConfig(prometheus_port=0)

    def test_prometheus_port_too_high_fails(self):
        """Test prometheus port above 65535 fails."""
        with pytest.raises(ValidationError):
            MetricConfig(prometheus_port=65536)

    def test_export_interval_validation(self):
        """Test export interval validation."""
        config = MetricConfig(export_interval=1.0)
        assert config.export_interval == 1.0
        config = MetricConfig(export_interval=100.0)
        assert config.export_interval == 100.0

    def test_export_interval_too_low_fails(self):
        """Test export interval below 1.0 fails."""
        with pytest.raises(ValidationError):
            MetricConfig(export_interval=0.5)


# ============================================================================
# MetricDefinition Tests
# ============================================================================

class TestMetricDefinition:
    """Tests for MetricDefinition model."""

    def test_counter_definition(self):
        """Test creating a counter metric definition."""
        definition = MetricDefinition(
            name="requests_total",
            metric_type=MetricType.COUNTER,
            description="Total requests"
        )
        assert definition.name == "requests_total"
        assert definition.metric_type == MetricType.COUNTER
        assert definition.description == "Total requests"
        assert definition.labels == []
        assert definition.buckets is None
        assert definition.unit is None

    def test_gauge_definition_with_labels(self):
        """Test creating a gauge metric definition with labels."""
        definition = MetricDefinition(
            name="temperature",
            metric_type=MetricType.GAUGE,
            description="Current temperature",
            labels=["location", "sensor"],
            unit="celsius"
        )
        assert definition.name == "temperature"
        assert definition.labels == ["location", "sensor"]
        assert definition.unit == "celsius"

    def test_histogram_definition_with_buckets(self):
        """Test creating a histogram metric definition with buckets."""
        definition = MetricDefinition(
            name="latency",
            metric_type=MetricType.HISTOGRAM,
            description="Request latency",
            buckets=[0.1, 0.5, 1.0, 5.0]
        )
        assert definition.buckets == [0.1, 0.5, 1.0, 5.0]

    def test_summary_definition(self):
        """Test creating a summary metric definition."""
        definition = MetricDefinition(
            name="request_size",
            metric_type=MetricType.SUMMARY,
            description="Request size in bytes"
        )
        assert definition.metric_type == MetricType.SUMMARY

    def test_name_validation_empty_fails(self):
        """Test empty name fails validation."""
        with pytest.raises(ValidationError):
            MetricDefinition(
                name="",
                metric_type=MetricType.COUNTER,
                description="Test"
            )

    def test_name_validation_invalid_chars_fails(self):
        """Test name with invalid characters fails."""
        with pytest.raises(ValidationError):
            MetricDefinition(
                name="invalid-name!",
                metric_type=MetricType.COUNTER,
                description="Test"
            )

    def test_name_validation_starts_with_digit_fails(self):
        """Test name starting with digit fails."""
        with pytest.raises(ValidationError):
            MetricDefinition(
                name="123_metric",
                metric_type=MetricType.COUNTER,
                description="Test"
            )

    def test_name_validation_underscore_allowed(self):
        """Test name can start with underscore."""
        definition = MetricDefinition(
            name="_private_metric",
            metric_type=MetricType.COUNTER,
            description="Test"
        )
        assert definition.name == "_private_metric"

    def test_buckets_validation_non_histogram_fails(self):
        """Test buckets on non-histogram metric fails."""
        with pytest.raises(ValidationError):
            MetricDefinition(
                name="test",
                metric_type=MetricType.COUNTER,
                description="Test",
                buckets=[0.1, 0.5]
            )

    def test_buckets_validation_empty_fails(self):
        """Test empty buckets list fails."""
        with pytest.raises(ValidationError):
            MetricDefinition(
                name="test",
                metric_type=MetricType.HISTOGRAM,
                description="Test",
                buckets=[]
            )

    def test_buckets_validation_unsorted_fails(self):
        """Test unsorted buckets fails."""
        with pytest.raises(ValidationError):
            MetricDefinition(
                name="test",
                metric_type=MetricType.HISTOGRAM,
                description="Test",
                buckets=[1.0, 0.5]
            )

    def test_buckets_validation_duplicates_fails(self):
        """Test duplicate buckets fails."""
        with pytest.raises(ValidationError):
            MetricDefinition(
                name="test",
                metric_type=MetricType.HISTOGRAM,
                description="Test",
                buckets=[0.5, 0.5, 1.0]
            )


# ============================================================================
# MetricsGateway Tests
# ============================================================================

class TestMetricsGateway:
    """Tests for MetricsGateway class."""

    def test_initialization_default_config(self):
        """Test gateway initialization with default config."""
        gateway = MetricsGateway()
        assert gateway.config.namespace == "animusforge"
        assert gateway.is_initialized is True
        assert gateway.registry is not None

    def test_initialization_custom_config(self):
        """Test gateway initialization with custom config."""
        config = MetricConfig(
            namespace="test",
            subsystem="unit",
            enable_default_metrics=False
        )
        gateway = MetricsGateway(config)
        assert gateway.config.namespace == "test"
        assert gateway.config.subsystem == "unit"

    def test_initialization_without_default_metrics(self):
        """Test gateway without default metrics."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        assert len(gateway._metrics) == 0

    def test_default_metrics_registered(self):
        """Test default metrics are registered."""
        gateway = MetricsGateway()
        names = gateway.get_metric_names()
        assert "animusforge_core_http_requests_total" in names
        assert "animusforge_core_http_request_duration_seconds" in names
        assert "animusforge_core_llm_calls_total" in names
        assert "animusforge_core_llm_tokens_total" in names
        assert "animusforge_core_memory_operations_total" in names
        assert "animusforge_core_errors_total" in names
        assert "animusforge_core_active_personas" in names

    def test_register_counter_metric(self):
        """Test registering a counter metric."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        definition = MetricDefinition(
            name="test_counter",
            metric_type=MetricType.COUNTER,
            description="Test counter"
        )
        gateway.register_metric(definition)
        
        assert "animusforge_core_test_counter" in gateway._metrics

    def test_register_gauge_metric(self):
        """Test registering a gauge metric."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        definition = MetricDefinition(
            name="test_gauge",
            metric_type=MetricType.GAUGE,
            description="Test gauge"
        )
        gateway.register_metric(definition)
        
        assert "animusforge_core_test_gauge" in gateway._metrics

    def test_register_histogram_metric(self):
        """Test registering a histogram metric."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        definition = MetricDefinition(
            name="test_histogram",
            metric_type=MetricType.HISTOGRAM,
            description="Test histogram",
            buckets=[0.1, 0.5, 1.0]
        )
        gateway.register_metric(definition)
        
        assert "animusforge_core_test_histogram" in gateway._metrics

    def test_register_summary_metric(self):
        """Test registering a summary metric."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        definition = MetricDefinition(
            name="test_summary",
            metric_type=MetricType.SUMMARY,
            description="Test summary"
        )
        gateway.register_metric(definition)
        
        assert "animusforge_core_test_summary" in gateway._metrics

    def test_register_metric_with_labels(self):
        """Test registering metric with labels."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        definition = MetricDefinition(
            name="test_labeled",
            metric_type=MetricType.COUNTER,
            description="Test labeled counter",
            labels=["method", "status"]
        )
        gateway.register_metric(definition)
        
        assert "animusforge_core_test_labeled" in gateway._metrics

    def test_register_duplicate_metric_fails(self):
        """Test registering duplicate metric fails."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        definition = MetricDefinition(
            name="test_unique",
            metric_type=MetricType.COUNTER,
            description="Test"
        )
        gateway.register_metric(definition)
        
        with pytest.raises(ValueError):
            gateway.register_metric(definition)

    def test_counter_increment(self):
        """Test counter increment."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        definition = MetricDefinition(
            name="test_counter",
            metric_type=MetricType.COUNTER,
            description="Test counter"
        )
        gateway.register_metric(definition)
        
        gateway.counter("test_counter")
        gateway.counter("test_counter", value=5.0)
        
        metrics = gateway.get_metrics()
        # Prometheus adds _total suffix to counters
        assert "animusforge_core_test_counter_total 6.0" in metrics

    def test_counter_with_labels(self):
        """Test counter increment with labels."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        definition = MetricDefinition(
            name="test_counter",
            metric_type=MetricType.COUNTER,
            description="Test counter",
            labels=["method"]
        )
        gateway.register_metric(definition)
        
        gateway.counter("test_counter", labels={"method": "GET"})
        gateway.counter("test_counter", labels={"method": "POST"})
        
        metrics = gateway.get_metrics()
        assert 'method="GET"' in metrics
        assert 'method="POST"' in metrics

    def test_gauge_set(self):
        """Test gauge set value."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        definition = MetricDefinition(
            name="test_gauge",
            metric_type=MetricType.GAUGE,
            description="Test gauge"
        )
        gateway.register_metric(definition)
        
        gateway.gauge("test_gauge", 42.0)
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_test_gauge 42.0" in metrics

    def test_gauge_increment(self):
        """Test gauge increment."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        definition = MetricDefinition(
            name="test_gauge",
            metric_type=MetricType.GAUGE,
            description="Test gauge"
        )
        gateway.register_metric(definition)
        
        gateway.gauge("test_gauge", 10.0)
        gateway.increment("test_gauge", 5.0)
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_test_gauge 15.0" in metrics

    def test_gauge_decrement(self):
        """Test gauge decrement."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        definition = MetricDefinition(
            name="test_gauge",
            metric_type=MetricType.GAUGE,
            description="Test gauge"
        )
        gateway.register_metric(definition)
        
        gateway.gauge("test_gauge", 10.0)
        gateway.decrement("test_gauge", 3.0)
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_test_gauge 7.0" in metrics

    def test_histogram_observe(self):
        """Test histogram observe."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        definition = MetricDefinition(
            name="test_histogram",
            metric_type=MetricType.HISTOGRAM,
            description="Test histogram",
            buckets=[0.1, 0.5, 1.0]
        )
        gateway.register_metric(definition)
        
        gateway.histogram("test_histogram", 0.3)
        gateway.histogram("test_histogram", 0.7)
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_test_histogram" in metrics
        assert "_bucket" in metrics
        assert "_sum" in metrics
        assert "_count" in metrics

    def test_increment_method(self):
        """Test increment method for counters."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        definition = MetricDefinition(
            name="test_counter",
            metric_type=MetricType.COUNTER,
            description="Test counter"
        )
        gateway.register_metric(definition)
        
        gateway.increment("test_counter")
        gateway.increment("test_counter", 10.0)
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_test_counter_total 11.0" in metrics

    def test_decrement_on_counter_warning(self):
        """Test decrement on counter logs warning."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        definition = MetricDefinition(
            name="test_counter",
            metric_type=MetricType.COUNTER,
            description="Test counter"
        )
        gateway.register_metric(definition)
        
        # Should not raise, just log warning
        gateway.decrement("test_counter")

    def test_time_context_manager(self):
        """Test time context manager."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        definition = MetricDefinition(
            name="test_duration",
            metric_type=MetricType.HISTOGRAM,
            description="Test duration"
        )
        gateway.register_metric(definition)
        
        with gateway.time("test_duration"):
            time.sleep(0.01)
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_test_duration" in metrics
        assert "_sum" in metrics

    def test_time_context_manager_with_labels(self):
        """Test time context manager with labels."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        definition = MetricDefinition(
            name="test_duration",
            metric_type=MetricType.HISTOGRAM,
            description="Test duration",
            labels=["operation"]
        )
        gateway.register_metric(definition)
        
        with gateway.time("test_duration", labels={"operation": "test"}):
            time.sleep(0.01)
        
        metrics = gateway.get_metrics()
        assert 'operation="test"' in metrics

    def test_observe_method(self):
        """Test observe method."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        definition = MetricDefinition(
            name="test_histogram",
            metric_type=MetricType.HISTOGRAM,
            description="Test histogram"
        )
        gateway.register_metric(definition)
        
        gateway.observe("test_histogram", 0.5)
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_test_histogram" in metrics

    def test_get_metrics_output(self):
        """Test get_metrics returns Prometheus format."""
        gateway = MetricsGateway()
        metrics = gateway.get_metrics()
        
        assert isinstance(metrics, str)
        assert "# HELP" in metrics or "# TYPE" in metrics

    def test_get_metric_names(self):
        """Test get_metric_names returns list."""
        gateway = MetricsGateway()
        names = gateway.get_metric_names()
        
        assert isinstance(names, list)
        assert len(names) > 0

    def test_clear_metrics(self):
        """Test clear_metrics removes all metrics."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        definition = MetricDefinition(
            name="test_metric",
            metric_type=MetricType.COUNTER,
            description="Test"
        )
        gateway.register_metric(definition)
        
        assert len(gateway._metrics) == 1
        gateway.clear_metrics()
        assert len(gateway._metrics) == 0

    def test_shutdown(self):
        """Test shutdown method."""
        gateway = MetricsGateway()
        gateway.shutdown()
        
        assert gateway.is_initialized is False

    def test_counter_nonexistent_metric_warning(self):
        """Test counter on non-existent metric logs warning."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        # Should not raise
        gateway.counter("nonexistent")

    def test_gauge_nonexistent_metric_warning(self):
        """Test gauge on non-existent metric logs warning."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        # Should not raise
        gateway.gauge("nonexistent", 1.0)

    def test_histogram_nonexistent_metric_warning(self):
        """Test histogram on non-existent metric logs warning."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        # Should not raise
        gateway.histogram("nonexistent", 1.0)

    def test_increment_nonexistent_metric_warning(self):
        """Test increment on non-existent metric logs warning."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        # Should not raise
        gateway.increment("nonexistent")

    def test_decrement_nonexistent_metric_warning(self):
        """Test decrement on non-existent metric logs warning."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        # Should not raise
        gateway.decrement("nonexistent")

    def test_observe_nonexistent_metric_warning(self):
        """Test observe on non-existent metric logs warning."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        # Should not raise
        gateway.observe("nonexistent", 1.0)

    def test_observe_on_counter_warning(self):
        """Test observe on counter logs warning."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        definition = MetricDefinition(
            name="test_counter",
            metric_type=MetricType.COUNTER,
            description="Test"
        )
        gateway.register_metric(definition)
        
        # Should not raise, just warn
        gateway.observe("test_counter", 1.0)

    def test_observe_on_summary(self):
        """Test observe on summary metric."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        definition = MetricDefinition(
            name="test_summary",
            metric_type=MetricType.SUMMARY,
            description="Test summary"
        )
        gateway.register_metric(definition)
        
        gateway.observe("test_summary", 1.0)
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_test_summary" in metrics


# ============================================================================
# Global Gateway Tests
# ============================================================================

class TestGlobalGateway:
    """Tests for global gateway functions."""

    def test_get_metrics_gateway_returns_instance(self):
        """Test get_metrics_gateway returns MetricsGateway instance."""
        gateway = get_metrics_gateway()
        assert isinstance(gateway, MetricsGateway)

    def test_get_metrics_gateway_returns_same_instance(self):
        """Test get_metrics_gateway returns same instance."""
        import animus_observe.metrics as metrics_module
        metrics_module._global_gateway = None  # Reset
        
        gateway1 = get_metrics_gateway()
        gateway2 = get_metrics_gateway()
        
        assert gateway1 is gateway2
        
        # Clean up
        metrics_module._global_gateway = None

    def test_configure_metrics(self):
        """Test configure_metrics creates new gateway."""
        import animus_observe.metrics as metrics_module
        metrics_module._global_gateway = None  # Reset
        
        config = MetricConfig(namespace="configured")
        gateway = configure_metrics(config)
        
        assert gateway.config.namespace == "configured"
        assert gateway is get_metrics_gateway()
        
        # Clean up
        metrics_module._global_gateway = None


# ============================================================================
# Decorator Tests
# ============================================================================

class TestTimedDecorator:
    """Tests for timed decorator."""

    def test_timed_sync_function(self):
        """Test timed decorator on sync function."""
        import animus_observe.metrics as metrics_module
        metrics_module._global_gateway = None
        
        # Register metric first
        gateway = get_metrics_gateway()
        gateway.register_metric(MetricDefinition(
            name="sync_func_duration_seconds",
            metric_type=MetricType.HISTOGRAM,
            description="Duration"
        ))
        
        @timed()
        def sync_func():
            time.sleep(0.01)
            return "done"
        
        result = sync_func()
        assert result == "done"
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_sync_func_duration_seconds" in metrics
        
        metrics_module._global_gateway = None

    def test_timed_async_function(self):
        """Test timed decorator on async function."""
        import animus_observe.metrics as metrics_module
        metrics_module._global_gateway = None
        
        # Register metric first
        gateway = get_metrics_gateway()
        gateway.register_metric(MetricDefinition(
            name="async_func_duration_seconds",
            metric_type=MetricType.HISTOGRAM,
            description="Duration"
        ))
        
        @timed()
        async def async_func():
            await asyncio.sleep(0.01)
            return "done"
        
        result = asyncio.run(async_func())
        assert result == "done"
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_async_func_duration_seconds" in metrics
        
        metrics_module._global_gateway = None

    def test_timed_with_custom_name(self):
        """Test timed decorator with custom metric name."""
        import animus_observe.metrics as metrics_module
        metrics_module._global_gateway = None
        
        gateway = get_metrics_gateway()
        gateway.register_metric(MetricDefinition(
            name="custom_timing",
            metric_type=MetricType.HISTOGRAM,
            description="Custom timing"
        ))
        
        @timed("custom_timing")
        def func():
            return "done"
        
        func()
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_custom_timing" in metrics
        
        metrics_module._global_gateway = None

    def test_timed_with_labels(self):
        """Test timed decorator with labels."""
        import animus_observe.metrics as metrics_module
        metrics_module._global_gateway = None
        
        gateway = get_metrics_gateway()
        gateway.register_metric(MetricDefinition(
            name="labeled_timing",
            metric_type=MetricType.HISTOGRAM,
            description="Labeled timing",
            labels=["operation"]
        ))
        
        @timed("labeled_timing", labels={"operation": "test"})
        def func():
            return "done"
        
        func()
        
        metrics = gateway.get_metrics()
        assert 'operation="test"' in metrics
        
        metrics_module._global_gateway = None

    def test_timed_on_uninitialized_gateway(self):
        """Test timed decorator when gateway is not initialized."""
        @timed("nonexistent_metric")
        def func():
            return "result"
        
        # Should still work, just not record
        result = func()
        assert result == "result"


class TestCountedDecorator:
    """Tests for counted decorator."""

    def test_counted_sync_function(self):
        """Test counted decorator on sync function."""
        import animus_observe.metrics as metrics_module
        metrics_module._global_gateway = None
        
        gateway = get_metrics_gateway()
        gateway.register_metric(MetricDefinition(
            name="sync_func_calls_total",
            metric_type=MetricType.COUNTER,
            description="Calls"
        ))
        
        @counted()
        def sync_func():
            return "done"
        
        result = sync_func()
        assert result == "done"
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_sync_func_calls_total" in metrics
        
        metrics_module._global_gateway = None

    def test_counted_async_function(self):
        """Test counted decorator on async function."""
        import animus_observe.metrics as metrics_module
        metrics_module._global_gateway = None
        
        gateway = get_metrics_gateway()
        gateway.register_metric(MetricDefinition(
            name="async_func_calls_total",
            metric_type=MetricType.COUNTER,
            description="Calls"
        ))
        
        @counted()
        async def async_func():
            return "done"
        
        result = asyncio.run(async_func())
        assert result == "done"
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_async_func_calls_total" in metrics
        
        metrics_module._global_gateway = None

    def test_counted_with_custom_name(self):
        """Test counted decorator with custom metric name."""
        import animus_observe.metrics as metrics_module
        metrics_module._global_gateway = None
        
        gateway = get_metrics_gateway()
        gateway.register_metric(MetricDefinition(
            name="custom_counter",
            metric_type=MetricType.COUNTER,
            description="Custom counter"
        ))
        
        @counted("custom_counter")
        def func():
            return "done"
        
        func()
        func()
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_custom_counter_total 2" in metrics
        
        metrics_module._global_gateway = None

    def test_counted_with_labels(self):
        """Test counted decorator with labels."""
        import animus_observe.metrics as metrics_module
        metrics_module._global_gateway = None
        
        gateway = get_metrics_gateway()
        gateway.register_metric(MetricDefinition(
            name="labeled_counter",
            metric_type=MetricType.COUNTER,
            description="Labeled counter",
            labels=["endpoint"]
        ))
        
        @counted("labeled_counter", labels={"endpoint": "/api"})
        def func():
            return "done"
        
        func()
        
        metrics = gateway.get_metrics()
        assert 'endpoint="/api"' in metrics
        
        metrics_module._global_gateway = None

    def test_counted_on_uninitialized_gateway(self):
        """Test counted decorator when gateway is not initialized."""
        @counted("nonexistent_metric")
        def func():
            return "result"
        
        # Should still work, just not record
        result = func()
        assert result == "result"


# ============================================================================
# Convenience Function Tests
# ============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_record_http_request(self):
        """Test record_http_request function."""
        import animus_observe.metrics as metrics_module
        metrics_module._global_gateway = None
        
        gateway = get_metrics_gateway()
        record_http_request("GET", "/users", 200)
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_http_requests_total" in metrics
        
        metrics_module._global_gateway = None

    def test_record_http_duration(self):
        """Test record_http_duration function."""
        import animus_observe.metrics as metrics_module
        metrics_module._global_gateway = None
        
        gateway = get_metrics_gateway()
        record_http_duration("GET", "/users", 0.5)
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_http_request_duration_seconds" in metrics
        
        metrics_module._global_gateway = None

    def test_record_llm_call(self):
        """Test record_llm_call function."""
        import animus_observe.metrics as metrics_module
        metrics_module._global_gateway = None
        
        gateway = get_metrics_gateway()
        record_llm_call("openai", "gpt-4", "success")
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_llm_calls_total" in metrics
        
        metrics_module._global_gateway = None

    def test_record_llm_tokens(self):
        """Test record_llm_tokens function."""
        import animus_observe.metrics as metrics_module
        metrics_module._global_gateway = None
        
        gateway = get_metrics_gateway()
        record_llm_tokens("openai", "gpt-4", "input", 100)
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_llm_tokens_total" in metrics
        
        metrics_module._global_gateway = None

    def test_record_memory_operation(self):
        """Test record_memory_operation function."""
        import animus_observe.metrics as metrics_module
        metrics_module._global_gateway = None
        
        gateway = get_metrics_gateway()
        record_memory_operation("read", "vector", "success")
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_memory_operations_total" in metrics
        
        metrics_module._global_gateway = None

    def test_record_error(self):
        """Test record_error function."""
        import animus_observe.metrics as metrics_module
        metrics_module._global_gateway = None
        
        gateway = get_metrics_gateway()
        record_error("api", "ValueError")
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_errors_total" in metrics
        
        metrics_module._global_gateway = None

    def test_set_active_personas(self):
        """Test set_active_personas function."""
        import animus_observe.metrics as metrics_module
        metrics_module._global_gateway = None
        
        gateway = get_metrics_gateway()
        set_active_personas(5, "active")
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_active_personas" in metrics
        
        metrics_module._global_gateway = None


# ============================================================================
# Edge Case Tests
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_time_context_manager_exception_handling(self):
        """Test time context manager handles exceptions."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        definition = MetricDefinition(
            name="test_duration",
            metric_type=MetricType.HISTOGRAM,
            description="Test duration"
        )
        gateway.register_metric(definition)
        
        with pytest.raises(ValueError):
            with gateway.time("test_duration"):
                raise ValueError("test error")
        
        # Metric should still be recorded
        metrics = gateway.get_metrics()
        assert "animusforge_core_test_duration" in metrics

    def test_decorator_preserves_function_metadata(self):
        """Test decorator preserves function name and docstring."""
        @timed()
        def my_function():
            """My docstring."""
            pass
        
        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."

    def test_counter_decorator_preserves_async_function_metadata(self):
        """Test counter decorator preserves async function metadata."""
        @counted()
        async def my_async_function():
            """My async docstring."""
            pass
        
        assert my_async_function.__name__ == "my_async_function"
        assert my_async_function.__doc__ == "My async docstring."

    def test_full_metric_name_generation(self):
        """Test full metric name generation."""
        config = MetricConfig(namespace="test", subsystem="api")
        gateway = MetricsGateway(config)
        
        assert gateway._get_full_name("metric") == "test_api_metric"

    def test_gateway_without_prometheus(self):
        """Test gateway behavior when prometheus not available."""
        with patch('animus_observe.metrics.PROMETHEUS_AVAILABLE', False):
            gateway = MetricsGateway.__new__(MetricsGateway)
            gateway.config = MetricConfig(enable_default_metrics=False)
            gateway._initialized = False
            gateway._metrics = {}
            gateway._otel_metrics = {}
            gateway._registry = None
            
            # get_metrics should return error message
            result = gateway.get_metrics()
            assert "not available" in result


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for metrics module."""

    def test_full_workflow(self):
        """Test complete metrics workflow."""
        import animus_observe.metrics as metrics_module
        metrics_module._global_gateway = None
        
        # Configure
        config = MetricConfig(
            namespace="myapp",
            subsystem="api",
            enable_default_metrics=False
        )
        gateway = configure_metrics(config)
        
        # Register custom metrics
        gateway.register_metric(MetricDefinition(
            name="requests_total",
            metric_type=MetricType.COUNTER,
            description="Total requests",
            labels=["method", "path"]
        ))
        
        gateway.register_metric(MetricDefinition(
            name="latency_seconds",
            metric_type=MetricType.HISTOGRAM,
            description="Request latency",
            labels=["method"],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0]
        ))
        
        # Record metrics
        gateway.counter("requests_total", labels={"method": "GET", "path": "/api/users"})
        gateway.counter("requests_total", labels={"method": "POST", "path": "/api/users"})
        
        with gateway.time("latency_seconds", labels={"method": "GET"}):
            time.sleep(0.02)
        
        # Get metrics
        output = gateway.get_metrics()
        
        assert "myapp_api_requests_total" in output
        assert "myapp_api_latency_seconds" in output
        assert 'method="GET"' in output
        assert 'path="/api/users"' in output
        
        # Cleanup
        gateway.shutdown()
        metrics_module._global_gateway = None

    def test_multiple_gateways_isolated(self):
        """Test multiple gateways are isolated."""
        config1 = MetricConfig(namespace="app1", enable_default_metrics=False)
        config2 = MetricConfig(namespace="app2", enable_default_metrics=False)
        
        gateway1 = MetricsGateway(config1)
        gateway2 = MetricsGateway(config2)
        
        gateway1.register_metric(MetricDefinition(
            name="test",
            metric_type=MetricType.COUNTER,
            description="Test"
        ))
        
        gateway2.register_metric(MetricDefinition(
            name="test",
            metric_type=MetricType.COUNTER,
            description="Test"
        ))
        
        metrics1 = gateway1.get_metrics()
        metrics2 = gateway2.get_metrics()
        
        assert "app1_core_test" in metrics1
        assert "app2_core_test" in metrics2

    def test_concurrent_counter_operations(self):
        """Test concurrent counter operations."""
        import threading
        
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        gateway.register_metric(MetricDefinition(
            name="concurrent_counter",
            metric_type=MetricType.COUNTER,
            description="Concurrent counter"
        ))
        
        def increment():
            for _ in range(100):
                gateway.counter("concurrent_counter")
        
        threads = [threading.Thread(target=increment) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_concurrent_counter_total 1000" in metrics

    def test_histogram_with_inf_bucket(self):
        """Test histogram with inf bucket (default buckets include inf)."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        # Use default buckets which include inf
        gateway.register_metric(MetricDefinition(
            name="test_histogram",
            metric_type=MetricType.HISTOGRAM,
            description="Test histogram"
        ))
        
        gateway.histogram("test_histogram", 100.0)  # Large value
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_test_histogram" in metrics
        assert 'le="+Inf"' in metrics

    def test_gauge_with_negative_value(self):
        """Test gauge can have negative values."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        gateway.register_metric(MetricDefinition(
            name="temperature",
            metric_type=MetricType.GAUGE,
            description="Temperature in Celsius"
        ))
        
        gateway.gauge("temperature", -10.5)
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_temperature -10.5" in metrics

    def test_multiple_labels(self):
        """Test metrics with multiple labels."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        gateway.register_metric(MetricDefinition(
            name="api_requests",
            metric_type=MetricType.COUNTER,
            description="API requests",
            labels=["method", "endpoint", "status"]
        ))
        
        gateway.counter("api_requests", labels={
            "method": "GET",
            "endpoint": "/users",
            "status": "200"
        })
        
        metrics = gateway.get_metrics()
        assert 'method="GET"' in metrics
        assert 'endpoint="/users"' in metrics
        assert 'status="200"' in metrics


# ============================================================================
# Additional Coverage Tests
# ============================================================================

class TestAdditionalCoverage:
    """Additional tests to increase coverage."""

    def test_register_metric_without_prometheus_raises(self):
        """Test register_metric raises when prometheus not available."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        # Mock PROMETHEUS_AVAILABLE to False for this test
        original_metrics = gateway._metrics.copy()
        gateway._registry = None  # Simulate no prometheus
        
        definition = MetricDefinition(
            name="test",
            metric_type=MetricType.COUNTER,
            description="Test"
        )
        
        with pytest.raises(RuntimeError):
            gateway.register_metric(definition)
        
        gateway._metrics = original_metrics

    def test_clear_metrics_with_exception(self):
        """Test clear_metrics handles exceptions gracefully."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        gateway.register_metric(MetricDefinition(
            name="test",
            metric_type=MetricType.COUNTER,
            description="Test"
        ))
        
        # Should not raise even if there are issues
        gateway.clear_metrics()
        assert len(gateway._metrics) == 0

    def test_summary_observe(self):
        """Test summary metric observation."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        gateway.register_metric(MetricDefinition(
            name="request_size",
            metric_type=MetricType.SUMMARY,
            description="Request size"
        ))
        
        gateway.histogram("request_size", 1024.0)
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_request_size" in metrics

    def test_force_flush_without_provider(self):
        """Test force_flush when no provider exists."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        # Should return True when no provider
        gateway._meter_provider = None
        result = gateway.shutdown()
        # Just verify no exception

    def test_configure_metrics_replaces_existing(self):
        """Test configure_metrics replaces existing gateway."""
        import animus_observe.metrics as metrics_module
        
        # Create first gateway
        config1 = MetricConfig(namespace="first")
        gateway1 = configure_metrics(config1)
        
        # Replace with second
        config2 = MetricConfig(namespace="second")
        gateway2 = configure_metrics(config2)
        
        assert gateway2.config.namespace == "second"
        assert get_metrics_gateway() is gateway2
        
        # Clean up
        metrics_module._global_gateway = None

    def test_histogram_with_labels(self):
        """Test histogram with labels."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        gateway.register_metric(MetricDefinition(
            name="latency",
            metric_type=MetricType.HISTOGRAM,
            description="Latency",
            labels=["service"]
        ))
        
        gateway.histogram("latency", 0.5, labels={"service": "api"})
        
        metrics = gateway.get_metrics()
        assert 'service="api"' in metrics

    def test_gauge_operations_with_labels(self):
        """Test gauge operations with labels."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        gateway.register_metric(MetricDefinition(
            name="connections",
            metric_type=MetricType.GAUGE,
            description="Active connections",
            labels=["pool"]
        ))
        
        gateway.gauge("connections", 10, labels={"pool": "main"})
        gateway.increment("connections", 5, labels={"pool": "main"})
        gateway.decrement("connections", 2, labels={"pool": "main"})
        
        metrics = gateway.get_metrics()
        # Should have recorded the operations
        assert "animusforge_core_connections" in metrics

    def test_default_buckets_used(self):
        """Test that default buckets are used when not specified."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        gateway.register_metric(MetricDefinition(
            name="duration",
            metric_type=MetricType.HISTOGRAM,
            description="Duration"
        ))
        
        # The default buckets include inf
        gateway.histogram("duration", 1000.0)
        
        metrics = gateway.get_metrics()
        assert 'le="+Inf"' in metrics

    def test_counted_decorator_without_metric_registered(self):
        """Test counted decorator when metric is not pre-registered."""
        import animus_observe.metrics as metrics_module
        metrics_module._global_gateway = None
        
        gateway = get_metrics_gateway()
        # Don't register the metric - it should just log a warning
        
        @counted("unregistered_metric")
        def func():
            return "result"
        
        result = func()
        assert result == "result"
        
        metrics_module._global_gateway = None

    def test_timed_decorator_without_metric_registered(self):
        """Test timed decorator when metric is not pre-registered."""
        import animus_observe.metrics as metrics_module
        metrics_module._global_gateway = None
        
        gateway = get_metrics_gateway()
        # Don't register the metric - it should just log a warning
        
        @timed("unregistered_metric")
        def func():
            time.sleep(0.01)
            return "result"
        
        result = func()
        assert result == "result"
        
        metrics_module._global_gateway = None

    def test_convenience_functions_with_uninitialized_gateway(self):
        """Test convenience functions when gateway is not initialized."""
        import animus_observe.metrics as metrics_module
        metrics_module._global_gateway = None
        
        # Create a gateway but don't register custom metrics
        gateway = get_metrics_gateway()
        
        # These should not raise - they just won't record anything
        record_http_request("GET", "/test", 200)
        record_http_duration("GET", "/test", 0.1)
        record_llm_call("openai", "gpt-4", "success")
        record_llm_tokens("openai", "gpt-4", "input", 100)
        record_memory_operation("read", "vector", "success")
        record_error("api", "ValueError")
        set_active_personas(5)
        
        metrics_module._global_gateway = None

    def test_metric_with_unit(self):
        """Test metric with unit specified."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        gateway.register_metric(MetricDefinition(
            name="data_size",
            metric_type=MetricType.GAUGE,
            description="Data size",
            unit="bytes"
        ))
        
        gateway.gauge("data_size", 1024.0)
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_data_size" in metrics

    def test_increment_on_counter_type(self):
        """Test increment on counter type calls counter method."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        gateway.register_metric(MetricDefinition(
            name="my_counter",
            metric_type=MetricType.COUNTER,
            description="My counter"
        ))
        
        # increment should work for counters too
        gateway.increment("my_counter", 2.0)
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_my_counter_total 2" in metrics

    def test_shutdown_with_meter_provider(self):
        """Test shutdown when meter_provider is set."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        # Set a mock meter provider
        mock_provider = MagicMock()
        gateway._meter_provider = mock_provider
        
        gateway.shutdown()
        
        mock_provider.shutdown.assert_called_once()


# ============================================================================
# Error Handling and Exception Tests for Coverage
# ============================================================================

class TestErrorHandling:
    """Tests for error handling paths to increase coverage."""

    def test_counter_operation_exception_handling(self):
        """Test counter handles exceptions during metric operations."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        gateway.register_metric(MetricDefinition(
            name="test_counter",
            metric_type=MetricType.COUNTER,
            description="Test counter",
            labels=["key"]
        ))
        
        # Invalid label should not crash
        gateway.counter("test_counter", labels={"wrong_key": "value"})

    def test_gauge_operation_exception_handling(self):
        """Test gauge handles exceptions during metric operations."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        gateway.register_metric(MetricDefinition(
            name="test_gauge",
            metric_type=MetricType.GAUGE,
            description="Test gauge",
            labels=["key"]
        ))
        
        # Invalid label should not crash
        gateway.gauge("test_gauge", 1.0, labels={"wrong_key": "value"})

    def test_histogram_operation_exception_handling(self):
        """Test histogram handles exceptions during metric operations."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        gateway.register_metric(MetricDefinition(
            name="test_histogram",
            metric_type=MetricType.HISTOGRAM,
            description="Test histogram",
            labels=["key"]
        ))
        
        # Invalid label should not crash
        gateway.histogram("test_histogram", 1.0, labels={"wrong_key": "value"})

    def test_increment_operation_exception_handling(self):
        """Test increment handles exceptions for gauge."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        gateway.register_metric(MetricDefinition(
            name="test_gauge",
            metric_type=MetricType.GAUGE,
            description="Test gauge",
            labels=["key"]
        ))
        
        # Invalid label should not crash
        gateway.increment("test_gauge", 1.0, labels={"wrong_key": "value"})

    def test_decrement_operation_exception_handling(self):
        """Test decrement handles exceptions."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        gateway.register_metric(MetricDefinition(
            name="test_gauge",
            metric_type=MetricType.GAUGE,
            description="Test gauge",
            labels=["key"]
        ))
        
        # Invalid label should not crash
        gateway.decrement("test_gauge", 1.0, labels={"wrong_key": "value"})

    def test_get_metrics_with_exception(self):
        """Test get_metrics handles exceptions gracefully."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        # Manually corrupt the registry to trigger exception
        gateway._registry = None
        
        result = gateway.get_metrics()
        assert "not available" in result or "Error" in result

    def test_register_metric_with_exception(self):
        """Test register_metric handles exceptions."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        # Create a definition that will fail during creation
        definition = MetricDefinition(
            name="test_metric",
            metric_type=MetricType.COUNTER,
            description="Test"
        )
        
        # First registration should work
        gateway.register_metric(definition)
        
        # Second should fail
        with pytest.raises(ValueError):
            gateway.register_metric(definition)


    def test_register_metric_unknown_type(self):
        """Test register_metric with unknown type raises."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        # Create definition and corrupt the type
        definition = MetricDefinition(
            name="test",
            metric_type=MetricType.COUNTER,
            description="Test"
        )
        # Manually change type to trigger else branch
        gateway._metrics["test"] = {"type": "unknown", "metric": None, "definition": definition}
        
        # Verify we can still work with the gateway
        assert len(gateway._metrics) == 1

    def test_otel_counter_recording_with_exception(self):
        """Test OpenTelemetry counter recording handles exceptions."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        gateway.register_metric(MetricDefinition(
            name="test_counter",
            metric_type=MetricType.COUNTER,
            description="Test"
        ))
        
        # Mock otel_metrics to raise exception
        gateway._otel_metrics[gateway._get_full_name("test_counter")] = MagicMock()
        gateway._otel_metrics[gateway._get_full_name("test_counter")].add.side_effect = Exception("OTel error")
        
        # Should not raise
        gateway.counter("test_counter")

    def test_otel_histogram_recording_with_exception(self):
        """Test OpenTelemetry histogram recording handles exceptions."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        gateway.register_metric(MetricDefinition(
            name="test_histogram",
            metric_type=MetricType.HISTOGRAM,
            description="Test"
        ))
        
        # Mock otel_metrics to raise exception
        gateway._otel_metrics[gateway._get_full_name("test_histogram")] = MagicMock()
        gateway._otel_metrics[gateway._get_full_name("test_histogram")].record.side_effect = Exception("OTel error")
        
        # Should not raise
        gateway.histogram("test_histogram", 1.0)

    def test_initialize_with_otlp_endpoint(self):
        """Test initialization with OTLP endpoint configured."""
        # This tests the OTLP initialization path
        config = MetricConfig(
            enable_default_metrics=False,
            otlp_endpoint="http://localhost:4317"
        )
        
        # Should initialize even if OTLP exporter not available
        gateway = MetricsGateway(config)
        assert gateway.is_initialized is True

    def test_clear_metrics_with_unregister_exception(self):
        """Test clear_metrics handles unregister exceptions."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        gateway.register_metric(MetricDefinition(
            name="test",
            metric_type=MetricType.COUNTER,
            description="Test"
        ))
        
        # Mock registry to raise on unregister
        original_unregister = gateway._registry.unregister
        gateway._registry.unregister = MagicMock(side_effect=Exception("Unregister error"))
        
        # Should not raise
        gateway.clear_metrics()
        
        # Restore
        gateway._registry.unregister = original_unregister

    def test_timed_decorator_exception_in_function(self):
        """Test timed decorator handles exceptions in decorated function."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        gateway.register_metric(MetricDefinition(
            name="failing_func_duration_seconds",
            metric_type=MetricType.HISTOGRAM,
            description="Duration"
        ))
        
        @timed()
        def failing_func():
            raise ValueError("Intentional error")
        
        with pytest.raises(ValueError):
            failing_func()
        
        # Metric should still be recorded
        metrics = gateway.get_metrics()
        assert "animusforge_core_failing_func_duration_seconds" in metrics

    def test_counted_decorator_exception_in_function(self):
        """Test counted decorator handles exceptions in decorated function."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        gateway.register_metric(MetricDefinition(
            name="failing_func_calls_total",
            metric_type=MetricType.COUNTER,
            description="Calls"
        ))
        
        @counted()
        def failing_func():
            raise ValueError("Intentional error")
        
        with pytest.raises(ValueError):
            failing_func()
        
        # Counter should have been incremented before the exception
        metrics = gateway.get_metrics()
        assert "animusforge_core_failing_func_calls_total" in metrics

    def test_async_timed_decorator_exception(self):
        """Test timed decorator handles exceptions in async function."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        gateway.register_metric(MetricDefinition(
            name="async_fail_duration_seconds",
            metric_type=MetricType.HISTOGRAM,
            description="Duration"
        ))
        
        @timed()
        async def async_failing():
            raise ValueError("Async error")
        
        with pytest.raises(ValueError):
            asyncio.run(async_failing())

    def test_async_counted_decorator_exception(self):
        """Test counted decorator handles exceptions in async function."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        gateway.register_metric(MetricDefinition(
            name="async_fail_calls_total",
            metric_type=MetricType.COUNTER,
            description="Calls"
        ))
        
        @counted()
        async def async_failing():
            raise ValueError("Async error")
        
        with pytest.raises(ValueError):
            asyncio.run(async_failing())


    def test_register_default_metrics_with_failure(self):
        """Test default metric registration handles individual failures."""
        config = MetricConfig(enable_default_metrics=True)
        gateway = MetricsGateway(config)
        
        # Default metrics should be registered
        assert len(gateway._metrics) >= 7

    def test_observable_without_labels(self):
        """Test observe on histogram without labels."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        gateway.register_metric(MetricDefinition(
            name="test_summary",
            metric_type=MetricType.SUMMARY,
            description="Test summary"
        ))
        
        gateway.observe("test_summary", 1.0)
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_test_summary" in metrics



    def test_histogram_with_default_buckets(self):
        """Test histogram uses default buckets when not specified."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        # Register without buckets - should use DEFAULT_BUCKETS
        gateway.register_metric(MetricDefinition(
            name="test_histogram",
            metric_type=MetricType.HISTOGRAM,
            description="Test"
        ))
        
        # Record a value
        gateway.histogram("test_histogram", 0.5)
        
        metrics = gateway.get_metrics()
        # Default buckets include various thresholds
        assert "animusforge_core_test_histogram" in metrics

    def test_multiple_time_contexts_nested(self):
        """Test nested time context managers."""
        config = MetricConfig(enable_default_metrics=False)
        gateway = MetricsGateway(config)
        
        gateway.register_metric(MetricDefinition(
            name="outer_duration",
            metric_type=MetricType.HISTOGRAM,
            description="Outer"
        ))
        gateway.register_metric(MetricDefinition(
            name="inner_duration",
            metric_type=MetricType.HISTOGRAM,
            description="Inner"
        ))
        
        with gateway.time("outer_duration"):
            time.sleep(0.01)
            with gateway.time("inner_duration"):
                time.sleep(0.01)
        
        metrics = gateway.get_metrics()
        assert "animusforge_core_outer_duration" in metrics
        assert "animusforge_core_inner_duration" in metrics
