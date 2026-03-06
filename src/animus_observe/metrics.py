"""Prometheus/OpenTelemetry Metrics Module for AnimusForge.

Provides production-ready metrics collection with Prometheus export,
OpenTelemetry integration, decorators, and default system metrics.
"""

from __future__ import annotations

import functools
import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar, ParamSpec, Generator

from pydantic import BaseModel, Field, field_validator

# Prometheus client imports with graceful fallback
try:
    from prometheus_client import (
        Counter as PromCounter,
        Gauge as PromGauge,
        Histogram as PromHistogram,
        Summary as PromSummary,
        Info as PromInfo,
        CollectorRegistry,
        generate_latest,
        CONTENT_TYPE_LATEST,
        REGISTRY,
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    PromCounter = Any  # type: ignore[misc]
    PromGauge = Any  # type: ignore[misc]
    PromHistogram = Any  # type: ignore[misc]
    PromSummary = Any  # type: ignore[misc]
    PromInfo = Any  # type: ignore[misc]
    CollectorRegistry = Any  # type: ignore[misc]
    REGISTRY = None

# OpenTelemetry imports with graceful fallback
try:
    from opentelemetry import metrics as otel_metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    OTEL_METRICS_AVAILABLE = True
except ImportError:
    OTEL_METRICS_AVAILABLE = False
    MeterProvider = Any  # type: ignore[misc]
    otel_metrics = None  # type: ignore[misc]

# OTLP exporter
try:
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    OTLP_METRIC_EXPORTER_AVAILABLE = True
except ImportError:
    OTLP_METRIC_EXPORTER_AVAILABLE = False
    OTLPMetricExporter = None  # type: ignore[misc]


logger = logging.getLogger(__name__)

# Type variables for generic decorators
P = ParamSpec("P")
R = TypeVar("R")

# Context variable for current timing operation
_current_timing_context: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "_current_timing_context", default=None
)


class MetricType(str, Enum):
    """Type of metric."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


class MetricConfig(BaseModel):
    """Configuration for metrics collection.

    Attributes:
        namespace: Namespace prefix for all metrics (e.g., 'animusforge').
        subsystem: Subsystem name for metric grouping (e.g., 'core').
        enable_default_metrics: Whether to register default system metrics.
        prometheus_port: Port for Prometheus HTTP server (if started).
        otlp_endpoint: Optional OTLP collector endpoint for OpenTelemetry export.
        export_interval: Interval in seconds for OTLP metric export.
    """

    namespace: str = Field(default="animusforge", description="Metric namespace prefix")
    subsystem: str = Field(default="core", description="Subsystem name")
    enable_default_metrics: bool = Field(default=True, description="Enable default metrics")
    prometheus_port: int = Field(default=9090, ge=1, le=65535, description="Prometheus port")
    otlp_endpoint: Optional[str] = Field(default=None, description="OTLP endpoint URL")
    export_interval: float = Field(default=60.0, ge=1.0, description="Export interval in seconds")

    @field_validator("otlp_endpoint")
    @classmethod
    def validate_endpoint(cls, v: Optional[str]) -> Optional[str]:
        """Validate OTLP endpoint format."""
        if v is None:
            return None
        if not v:
            raise ValueError("OTLP endpoint cannot be empty string")
        if not v.startswith(("http://", "https://", "grpc://")):
            v = f"http://{v}"
        return v


class MetricDefinition(BaseModel):
    """Definition for a metric to be registered.

    Attributes:
        name: Name of the metric (without namespace prefix).
        metric_type: Type of metric (counter, gauge, histogram, summary).
        description: Human-readable description of the metric.
        labels: List of label names for the metric.
        buckets: Bucket boundaries for histogram metrics.
        unit: Optional unit of measurement.
    """

    name: str = Field(description="Metric name")
    metric_type: MetricType = Field(description="Metric type")
    description: str = Field(description="Metric description")
    labels: List[str] = Field(default_factory=list, description="Label names")
    buckets: Optional[List[float]] = Field(default=None, description="Histogram buckets")
    unit: Optional[str] = Field(default=None, description="Unit of measurement")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate metric name follows Prometheus naming conventions."""
        if not v:
            raise ValueError("Metric name cannot be empty")
        # Prometheus names: [a-zA-Z_:][a-zA-Z0-9_:]*
        import re
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", v):
            raise ValueError(f"Invalid metric name '{v}': must match [a-zA-Z_][a-zA-Z0-9_]*")
        return v

    @field_validator("buckets")
    @classmethod
    def validate_buckets(cls, v: Optional[List[float]], info) -> Optional[List[float]]:
        """Validate histogram buckets."""
        if v is None:
            return None
        if info.data.get("metric_type") != MetricType.HISTOGRAM and v:
            raise ValueError("Buckets are only valid for histogram metrics")
        if not v:
            raise ValueError("Buckets list cannot be empty")
        if len(v) != len(set(v)):
            raise ValueError("Buckets must be unique")
        if v != sorted(v):
            raise ValueError("Buckets must be sorted in ascending order")
        return v


class MetricsGateway:
    """Gateway for Prometheus/OpenTelemetry metrics operations.

    Provides a unified interface for metric registration, recording,
    and export with production-ready defaults.

    Example:
        >>> config = MetricConfig(namespace="animusforge")
        >>> gateway = MetricsGateway(config)
        >>> gateway.register_metric(MetricDefinition(
        ...     name="requests_total",
        ...     metric_type=MetricType.COUNTER,
        ...     description="Total requests"
        ... ))
        >>> gateway.counter("requests_total")
        >>> print(gateway.get_metrics())
    """

    # Default histogram buckets (in seconds)
    DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0, float("inf"))

    def __init__(self, config: Optional[MetricConfig] = None):
        """Initialize the metrics gateway.

        Args:
            config: Metrics configuration. Uses defaults if not provided.
        """
        self.config = config or MetricConfig()
        self._metrics: Dict[str, Any] = {}
        self._registry: Optional[CollectorRegistry] = None
        self._meter_provider: Optional[MeterProvider] = None
        self._meter: Optional[Any] = None
        self._otel_metrics: Dict[str, Any] = {}
        self._initialized = False

        self._initialize()

    def _initialize(self) -> None:
        """Initialize the metrics backend."""
        if not PROMETHEUS_AVAILABLE:
            logger.warning("prometheus_client not available. Metrics collection disabled.")
            self._initialized = False
            return

        try:
            # Create isolated registry to avoid global state pollution
            self._registry = CollectorRegistry()

            # Initialize OpenTelemetry if endpoint configured
            if self.config.otlp_endpoint and OTEL_METRICS_AVAILABLE:
                self._initialize_otel()

            # Register default metrics if enabled
            if self.config.enable_default_metrics:
                self._register_default_metrics()

            self._initialized = True
            logger.info(
                f"Metrics initialized: namespace={self.config.namespace}, "
                f"subsystem={self.config.subsystem}"
            )

        except Exception as e:
            logger.error(f"Failed to initialize metrics: {e}")
            self._initialized = False

    def _initialize_otel(self) -> None:
        """Initialize OpenTelemetry metrics provider."""
        if not OTEL_METRICS_AVAILABLE or not OTLP_METRIC_EXPORTER_AVAILABLE:
            logger.warning("OpenTelemetry or OTLP exporter not available")
            return

        try:
            resource = Resource.create({"service.name": self.config.namespace})

            endpoint = self.config.otlp_endpoint
            if endpoint:
                # Strip protocol for gRPC
                if endpoint.startswith("http://"):
                    endpoint = endpoint[7:]
                elif endpoint.startswith("https://"):
                    endpoint = endpoint[8:]

                exporter = OTLPMetricExporter(endpoint=endpoint)
                reader = PeriodicExportingMetricReader(
                    exporter,
                    export_interval_millis=int(self.config.export_interval * 1000)
                )
                self._meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
                otel_metrics.set_meter_provider(self._meter_provider)
                self._meter = otel_metrics.get_meter(self.config.namespace)
                logger.info(f"OpenTelemetry metrics initialized: endpoint={self.config.otlp_endpoint}")
        except Exception as e:
            logger.error(f"Failed to initialize OpenTelemetry: {e}")

    def _register_default_metrics(self) -> None:
        """Register default system metrics for AnimusForge."""
        default_metrics = [
            MetricDefinition(
                name="http_requests_total",
                metric_type=MetricType.COUNTER,
                description="Total HTTP requests",
                labels=["method", "endpoint", "status_code"]
            ),
            MetricDefinition(
                name="http_request_duration_seconds",
                metric_type=MetricType.HISTOGRAM,
                description="HTTP request duration in seconds",
                labels=["method", "endpoint"],
                buckets=list(self.DEFAULT_BUCKETS)
            ),
            MetricDefinition(
                name="llm_calls_total",
                metric_type=MetricType.COUNTER,
                description="Total LLM API calls",
                labels=["provider", "model", "status"]
            ),
            MetricDefinition(
                name="llm_tokens_total",
                metric_type=MetricType.COUNTER,
                description="Total LLM tokens processed",
                labels=["provider", "model", "type"]  # type: input/output
            ),
            MetricDefinition(
                name="memory_operations_total",
                metric_type=MetricType.COUNTER,
                description="Total memory store operations",
                labels=["operation", "store_type", "status"]
            ),
            MetricDefinition(
                name="errors_total",
                metric_type=MetricType.COUNTER,
                description="Total errors encountered",
                labels=["component", "error_type"]
            ),
            MetricDefinition(
                name="active_personas",
                metric_type=MetricType.GAUGE,
                description="Number of currently active personas",
                labels=["status"]
            ),
        ]

        for metric_def in default_metrics:
            try:
                self.register_metric(metric_def)
            except Exception as e:
                logger.warning(f"Failed to register default metric '{metric_def.name}': {e}")

    def _get_full_name(self, name: str) -> str:
        """Get full metric name with namespace and subsystem.

        Args:
            name: Base metric name.

        Returns:
            Full metric name (namespace_subsystem_name).
        """
        return f"{self.config.namespace}_{self.config.subsystem}_{name}"

    @property
    def is_initialized(self) -> bool:
        """Check if metrics gateway is initialized and ready."""
        return self._initialized

    @property
    def registry(self) -> Optional[CollectorRegistry]:
        """Get the Prometheus registry."""
        return self._registry

    def register_metric(self, definition: MetricDefinition) -> None:
        """Register a new metric.

        Args:
            definition: Metric definition specifying name, type, description, etc.

        Raises:
            ValueError: If metric already exists or configuration is invalid.
        """
        if not PROMETHEUS_AVAILABLE or self._registry is None:
            raise RuntimeError("Prometheus client not available")

        full_name = self._get_full_name(definition.name)

        if full_name in self._metrics:
            raise ValueError(f"Metric '{full_name}' already registered")

        try:
            if definition.metric_type == MetricType.COUNTER:
                metric = PromCounter(
                    full_name,
                    definition.description,
                    definition.labels,
                    registry=self._registry
                )
            elif definition.metric_type == MetricType.GAUGE:
                metric = PromGauge(
                    full_name,
                    definition.description,
                    definition.labels,
                    registry=self._registry
                )
            elif definition.metric_type == MetricType.HISTOGRAM:
                buckets = tuple(definition.buckets) if definition.buckets else self.DEFAULT_BUCKETS
                metric = PromHistogram(
                    full_name,
                    definition.description,
                    definition.labels,
                    buckets=buckets,
                    registry=self._registry
                )
            elif definition.metric_type == MetricType.SUMMARY:
                metric = PromSummary(
                    full_name,
                    definition.description,
                    definition.labels,
                    registry=self._registry
                )
            else:
                raise ValueError(f"Unknown metric type: {definition.metric_type}")

            self._metrics[full_name] = {
                "metric": metric,
                "definition": definition,
                "type": definition.metric_type
            }

            # Also register in OpenTelemetry if available
            if self._meter:
                self._register_otel_metric(definition)

            logger.debug(f"Registered metric: {full_name}")

        except Exception as e:
            logger.error(f"Failed to register metric '{full_name}': {e}")
            raise

    def _register_otel_metric(self, definition: MetricDefinition) -> None:
        """Register metric in OpenTelemetry.

        Args:
            definition: Metric definition.
        """
        if not self._meter:
            return

        try:
            full_name = self._get_full_name(definition.name)

            if definition.metric_type == MetricType.COUNTER:
                self._otel_metrics[full_name] = self._meter.create_counter(
                    name=full_name,
                    description=definition.description,
                    unit=definition.unit or "1"
                )
            elif definition.metric_type == MetricType.GAUGE:
                # OpenTelemetry uses ObservableGauge for gauges
                self._otel_metrics[full_name] = self._meter.create_gauge(
                    name=full_name,
                    description=definition.description,
                    unit=definition.unit or "1"
                )
            elif definition.metric_type == MetricType.HISTOGRAM:
                self._otel_metrics[full_name] = self._meter.create_histogram(
                    name=full_name,
                    description=definition.description,
                    unit=definition.unit or "s"
                )
        except Exception as e:
            logger.warning(f"Failed to register OpenTelemetry metric: {e}")

    def _get_metric(self, name: str) -> Optional[Dict[str, Any]]:
        """Get metric by name.

        Args:
            name: Metric name (without namespace prefix).

        Returns:
            Metric dict or None if not found.
        """
        full_name = self._get_full_name(name)
        return self._metrics.get(full_name)

    def counter(self, name: str, labels: Optional[Dict[str, str]] = None, value: float = 1.0) -> None:
        """Increment a counter metric.

        Args:
            name: Metric name.
            labels: Optional label key-value pairs.
            value: Value to increment by (default 1.0).
        """
        metric_info = self._get_metric(name)
        if not metric_info:
            logger.warning(f"Counter metric '{name}' not found")
            return

        try:
            metric = metric_info["metric"]
            if labels:
                metric.labels(**labels).inc(value)
            else:
                metric.inc(value)

            # Also record in OpenTelemetry
            self._record_otel_counter(name, value, labels)

        except Exception as e:
            logger.error(f"Failed to increment counter '{name}': {e}")

    def _record_otel_counter(self, name: str, value: float, labels: Optional[Dict[str, str]]) -> None:
        """Record counter in OpenTelemetry."""
        full_name = self._get_full_name(name)
        otel_metric = self._otel_metrics.get(full_name)
        if otel_metric and hasattr(otel_metric, 'add'):
            try:
                otel_metric.add(value, labels or {})
            except Exception as e:
                logger.debug(f"Failed to record OTel counter: {e}")

    def gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Set a gauge metric value.

        Args:
            name: Metric name.
            value: Value to set.
            labels: Optional label key-value pairs.
        """
        metric_info = self._get_metric(name)
        if not metric_info:
            logger.warning(f"Gauge metric '{name}' not found")
            return

        try:
            metric = metric_info["metric"]
            if labels:
                metric.labels(**labels).set(value)
            else:
                metric.set(value)

        except Exception as e:
            logger.error(f"Failed to set gauge '{name}': {e}")

    def histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Observe a value in a histogram metric.

        Args:
            name: Metric name.
            value: Value to observe.
            labels: Optional label key-value pairs.
        """
        metric_info = self._get_metric(name)
        if not metric_info:
            logger.warning(f"Histogram metric '{name}' not found")
            return

        try:
            metric = metric_info["metric"]
            if labels:
                metric.labels(**labels).observe(value)
            else:
                metric.observe(value)

            # Also record in OpenTelemetry
            self._record_otel_histogram(name, value, labels)

        except Exception as e:
            logger.error(f"Failed to observe histogram '{name}': {e}")

    def _record_otel_histogram(self, name: str, value: float, labels: Optional[Dict[str, str]]) -> None:
        """Record histogram in OpenTelemetry."""
        full_name = self._get_full_name(name)
        otel_metric = self._otel_metrics.get(full_name)
        if otel_metric and hasattr(otel_metric, 'record'):
            try:
                otel_metric.record(value, labels or {})
            except Exception as e:
                logger.debug(f"Failed to record OTel histogram: {e}")

    def increment(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """Increment a counter or gauge metric.

        Args:
            name: Metric name.
            value: Value to increment by.
            labels: Optional label key-value pairs.
        """
        metric_info = self._get_metric(name)
        if not metric_info:
            logger.warning(f"Metric '{name}' not found for increment")
            return

        metric_type = metric_info["type"]
        if metric_type == MetricType.COUNTER:
            self.counter(name, labels, value)
        elif metric_type == MetricType.GAUGE:
            try:
                metric = metric_info["metric"]
                if labels:
                    metric.labels(**labels).inc(value)
                else:
                    metric.inc(value)
            except Exception as e:
                logger.error(f"Failed to increment gauge '{name}': {e}")
        else:
            logger.warning(f"Cannot increment metric of type {metric_type}")

    def decrement(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """Decrement a gauge metric.

        Args:
            name: Metric name.
            value: Value to decrement by.
            labels: Optional label key-value pairs.
        """
        metric_info = self._get_metric(name)
        if not metric_info:
            logger.warning(f"Metric '{name}' not found for decrement")
            return

        if metric_info["type"] != MetricType.GAUGE:
            logger.warning(f"Cannot decrement metric of type {metric_info['type']}")
            return

        try:
            metric = metric_info["metric"]
            if labels:
                metric.labels(**labels).dec(value)
            else:
                metric.dec(value)
        except Exception as e:
            logger.error(f"Failed to decrement gauge '{name}': {e}")

    @contextmanager
    def time(self, name: str, labels: Optional[Dict[str, str]] = None) -> Generator[None, None, None]:
        """Context manager for timing operations.

        Automatically records duration in a histogram metric.

        Args:
            name: Histogram metric name.
            labels: Optional label key-value pairs.

        Yields:
            None

        Example:
            >>> with gateway.time("operation_duration"):
            ...     # do work
            ...     pass
        """
        start_time = time.perf_counter()
        token = _current_timing_context.set({"name": name, "labels": labels, "start": start_time})

        try:
            yield
        finally:
            elapsed = time.perf_counter() - start_time
            self.histogram(name, elapsed, labels)
            _current_timing_context.reset(token)

    def observe(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Observe a value in a histogram or summary metric.

        Args:
            name: Metric name.
            value: Value to observe.
            labels: Optional label key-value pairs.
        """
        metric_info = self._get_metric(name)
        if not metric_info:
            logger.warning(f"Metric '{name}' not found for observe")
            return

        metric_type = metric_info["type"]
        if metric_type in (MetricType.HISTOGRAM, MetricType.SUMMARY):
            self.histogram(name, value, labels)
        else:
            logger.warning(f"Cannot observe metric of type {metric_type}")

    def get_metrics(self) -> str:
        """Get all metrics in Prometheus text format.

        Returns:
            String containing all metrics in Prometheus exposition format.
        """
        if not PROMETHEUS_AVAILABLE or self._registry is None:
            return "# Metrics collection not available\n"

        try:
            return generate_latest(self._registry).decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to generate metrics: {e}")
            return f"# Error generating metrics: {e}\n"

    def get_metric_names(self) -> List[str]:
        """Get list of all registered metric names.

        Returns:
            List of full metric names.
        """
        return list(self._metrics.keys())

    def clear_metrics(self) -> None:
        """Clear all registered metrics.

        Warning: This removes all metrics from the registry.
        """
        if not PROMETHEUS_AVAILABLE or self._registry is None:
            return

        try:
            # Unregister all metrics we've registered
            for full_name, metric_info in self._metrics.items():
                try:
                    self._registry.unregister(metric_info["metric"])
                except Exception:
                    pass  # Metric may not be registered

            self._metrics.clear()
            self._otel_metrics.clear()
            logger.info("All metrics cleared")

        except Exception as e:
            logger.error(f"Failed to clear metrics: {e}")

    def shutdown(self) -> None:
        """Shutdown the metrics gateway.

        Flushes any pending exports and cleans up resources.
        """
        try:
            if self._meter_provider:
                self._meter_provider.shutdown()
                logger.info("OpenTelemetry meter provider shutdown")

            self._initialized = False
            logger.info("Metrics gateway shutdown complete")

        except Exception as e:
            logger.error(f"Error during metrics shutdown: {e}")


# Global gateway instance
_global_gateway: Optional[MetricsGateway] = None


def get_metrics_gateway() -> MetricsGateway:
    """Get or create the global metrics gateway.

    Returns:
        The global MetricsGateway instance.
    """
    global _global_gateway
    if _global_gateway is None:
        _global_gateway = MetricsGateway()
    return _global_gateway


def configure_metrics(config: MetricConfig) -> MetricsGateway:
    """Configure the global metrics gateway.

    Args:
        config: Metrics configuration.

    Returns:
        The configured MetricsGateway instance.
    """
    global _global_gateway
    if _global_gateway:
        _global_gateway.shutdown()
    _global_gateway = MetricsGateway(config)
    return _global_gateway


def timed(
    metric_name: Optional[str] = None,
    labels: Optional[Dict[str, str]] = None
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator for automatic timing of functions.

    Records execution duration in a histogram metric.

    Args:
        metric_name: Name of the histogram metric (defaults to function name).
        labels: Static label key-value pairs.

    Returns:
        Decorated function with automatic timing.

    Example:
        >>> @timed("database_query", {"db": "postgres"})
        ... async def query_users():
        ...     # ... query logic ...
        ...     pass
    """
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        name = metric_name or f"{func.__name__}_duration_seconds"

        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            gateway = get_metrics_gateway()

            if not gateway.is_initialized:
                return await func(*args, **kwargs)  # type: ignore[misc]

            with gateway.time(name, labels):
                return await func(*args, **kwargs)  # type: ignore[misc]

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            gateway = get_metrics_gateway()

            if not gateway.is_initialized:
                return func(*args, **kwargs)

            with gateway.time(name, labels):
                return func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper  # type: ignore[return-value]

    return decorator


def counted(
    metric_name: Optional[str] = None,
    labels: Optional[Dict[str, str]] = None
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator for automatic counting of function calls.

    Increments a counter each time the function is called.

    Args:
        metric_name: Name of the counter metric (defaults to function name).
        labels: Static label key-value pairs.

    Returns:
        Decorated function with automatic counting.

    Example:
        >>> @counted("api_requests", {"endpoint": "/users"})
        ... async def get_users():
        ...     # ... handler logic ...
        ...     pass
    """
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        name = metric_name or f"{func.__name__}_calls_total"

        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            gateway = get_metrics_gateway()

            if gateway.is_initialized:
                gateway.counter(name, labels)

            return await func(*args, **kwargs)  # type: ignore[misc]

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            gateway = get_metrics_gateway()

            if gateway.is_initialized:
                gateway.counter(name, labels)

            return func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper  # type: ignore[return-value]

    return decorator


# Convenience functions for default metrics
def record_http_request(method: str, endpoint: str, status_code: int) -> None:
    """Record an HTTP request metric.

    Args:
        method: HTTP method (GET, POST, etc.).
        endpoint: Request endpoint path.
        status_code: HTTP response status code.
    """
    gateway = get_metrics_gateway()
    if gateway.is_initialized:
        gateway.counter(
            "http_requests_total",
            labels={"method": method, "endpoint": endpoint, "status_code": str(status_code)}
        )


def record_http_duration(method: str, endpoint: str, duration: float) -> None:
    """Record HTTP request duration.

    Args:
        method: HTTP method.
        endpoint: Request endpoint path.
        duration: Request duration in seconds.
    """
    gateway = get_metrics_gateway()
    if gateway.is_initialized:
        gateway.histogram(
            "http_request_duration_seconds",
            duration,
            labels={"method": method, "endpoint": endpoint}
        )


def record_llm_call(provider: str, model: str, status: str) -> None:
    """Record an LLM API call.

    Args:
        provider: LLM provider name.
        model: Model identifier.
        status: Call status (success, error, timeout, etc.).
    """
    gateway = get_metrics_gateway()
    if gateway.is_initialized:
        gateway.counter(
            "llm_calls_total",
            labels={"provider": provider, "model": model, "status": status}
        )


def record_llm_tokens(provider: str, model: str, token_type: str, count: int) -> None:
    """Record LLM token usage.

    Args:
        provider: LLM provider name.
        model: Model identifier.
        token_type: Token type (input/output).
        count: Number of tokens.
    """
    gateway = get_metrics_gateway()
    if gateway.is_initialized:
        gateway.counter(
            "llm_tokens_total",
            labels={"provider": provider, "model": model, "type": token_type},
            value=float(count)
        )


def record_memory_operation(operation: str, store_type: str, status: str) -> None:
    """Record a memory store operation.

    Args:
        operation: Operation type (read, write, delete, etc.).
        store_type: Store type (vector, graph, cache, etc.).
        status: Operation status.
    """
    gateway = get_metrics_gateway()
    if gateway.is_initialized:
        gateway.counter(
            "memory_operations_total",
            labels={"operation": operation, "store_type": store_type, "status": status}
        )


def record_error(component: str, error_type: str) -> None:
    """Record an error.

    Args:
        component: Component where error occurred.
        error_type: Error type/exception name.
    """
    gateway = get_metrics_gateway()
    if gateway.is_initialized:
        gateway.counter(
            "errors_total",
            labels={"component": component, "error_type": error_type}
        )


def set_active_personas(count: int, status: str = "active") -> None:
    """Set the number of active personas.

    Args:
        count: Number of active personas.
        status: Persona status.
    """
    gateway = get_metrics_gateway()
    if gateway.is_initialized:
        gateway.gauge(
            "active_personas",
            float(count),
            labels={"status": status}
        )
