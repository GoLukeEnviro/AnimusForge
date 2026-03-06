"""OpenTelemetry Tracing Module for AnimusForge.

Provides production-ready distributed tracing with OTLP export,
span management, context propagation, and automatic instrumentation.
"""

from __future__ import annotations

import functools
import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union, ParamSpec, AsyncGenerator
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

# OpenTelemetry imports with graceful fallback
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter
    from opentelemetry.sdk.trace.sampling import TraceIdRatioBased, ParentBased
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_NAMESPACE, SERVICE_VERSION, DEPLOYMENT_ENVIRONMENT
    from opentelemetry.trace import Span, Status, StatusCode, Context, SpanKind, get_current_span, set_span_in_context
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator as TraceContextPropagator
    from opentelemetry.context import Context as OtelContext
    from opentelemetry.util.types import Attributes
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    # Type aliases for when OpenTelemetry is not available
    Span = Any  # type: ignore[misc]
    Context = Any  # type: ignore[misc]
    StatusCode = Any  # type: ignore[misc]

# Try OTLP exporter
try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    OTLP_GRPC_AVAILABLE = True
except ImportError:
    OTLP_GRPC_AVAILABLE = False
    OTLPSpanExporter = None  # type: ignore[misc]

try:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter as HTTPOTLPSpanExporter
    OTLP_HTTP_AVAILABLE = True
except ImportError:
    OTLP_HTTP_AVAILABLE = False
    HTTPOTLPSpanExporter = None  # type: ignore[misc]

# Console exporter for development
try:
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter
    CONSOLE_EXPORTER_AVAILABLE = True
except ImportError:
    CONSOLE_EXPORTER_AVAILABLE = False
    ConsoleSpanExporter = None  # type: ignore[misc]


logger = logging.getLogger(__name__)

# Type variables for generic decorators
P = ParamSpec("P")
R = TypeVar("R")

# Context variable for storing current span context
_current_span_context: ContextVar[Optional[SpanContext]] = ContextVar("_current_span_context", default=None)


class SpanStatus(str, Enum):
    """Status of a span."""
    UNSET = "UNSET"
    OK = "OK"
    ERROR = "ERROR"


class ExportProtocol(str, Enum):
    """Export protocol for OTLP."""
    GRPC = "grpc"
    HTTP = "http"
    CONSOLE = "console"


class TracingConfig(BaseModel):
    """Configuration for OpenTelemetry tracing.

    Attributes:
        service_name: Name of the service for trace identification.
        service_namespace: Namespace for service grouping.
        service_version: Version of the service.
        environment: Deployment environment (development, staging, production).
        otlp_endpoint: OTLP collector endpoint URL.
        export_protocol: Protocol to use for export (grpc, http, console).
        sample_rate: Sampling rate for traces (0.0 to 1.0).
        enabled: Whether tracing is enabled.
        export_timeout: Timeout for batch export in seconds.
        max_queue_size: Maximum queue size for batch processor.
        max_export_batch_size: Maximum batch size for export.
        schedule_delay_millis: Delay between batch exports in milliseconds.
        resource_attributes: Additional resource attributes.
    """

    service_name: str = Field(default="animusforge", description="Service name for traces")
    service_namespace: str = Field(default="animusforge.ai", description="Service namespace")
    service_version: str = Field(default="1.0.0", description="Service version")
    environment: str = Field(default="development", description="Deployment environment")
    otlp_endpoint: str = Field(default="http://localhost:4317", description="OTLP collector endpoint")
    export_protocol: ExportProtocol = Field(default=ExportProtocol.GRPC, description="Export protocol")
    sample_rate: float = Field(default=1.0, ge=0.0, le=1.0, description="Sampling rate")
    enabled: bool = Field(default=True, description="Enable tracing")
    export_timeout: float = Field(default=30.0, ge=1.0, le=300.0, description="Export timeout in seconds")
    max_queue_size: int = Field(default=2048, ge=1, le=10000, description="Max queue size")
    max_export_batch_size: int = Field(default=512, ge=1, le=5000, description="Max export batch size")
    schedule_delay_millis: int = Field(default=5000, ge=100, le=60000, description="Schedule delay in ms")
    resource_attributes: Dict[str, Any] = Field(default_factory=dict, description="Additional resource attributes")

    @field_validator("otlp_endpoint")
    @classmethod
    def validate_endpoint(cls, v: str) -> str:
        """Validate OTLP endpoint format."""
        if not v:
            raise ValueError("OTLP endpoint cannot be empty")
        if not v.startswith(("http://", "https://", "grpc://")):
            v = f"http://{v}"
        return v

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment value."""
        allowed = {"development", "staging", "production", "testing"}
        v_lower = v.lower()
        if v_lower not in allowed:
            logger.warning(f"Non-standard environment '{v}', using as-is")
        return v_lower


class SpanEvent(BaseModel):
    """Represents an event within a span.

    Attributes:
        name: Name of the event.
        timestamp: When the event occurred.
        attributes: Event attributes.
    """
    name: str = Field(description="Event name")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Event timestamp")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="Event attributes")


class SpanContext(BaseModel):
    """Represents the context of a span for serialization and tracking.

    Attributes:
        trace_id: Unique identifier for the trace.
        span_id: Unique identifier for this span.
        parent_span_id: ID of the parent span, if any.
        operation_name: Name of the operation being traced.
        start_time: When the span started.
        end_time: When the span ended, if applicable.
        attributes: Span attributes/metadata.
        events: List of events recorded on this span.
        status: Current status of the span.
        kind: Type of span (internal, server, client, etc.).
    """

    trace_id: str = Field(description="Trace ID")
    span_id: str = Field(description="Span ID")
    parent_span_id: Optional[str] = Field(default=None, description="Parent span ID")
    operation_name: str = Field(description="Operation name")
    start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Start time")
    end_time: Optional[datetime] = Field(default=None, description="End time")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="Span attributes")
    events: List[SpanEvent] = Field(default_factory=list, description="Span events")
    status: SpanStatus = Field(default=SpanStatus.UNSET, description="Span status")
    kind: str = Field(default="INTERNAL", description="Span kind")

    @field_validator("trace_id", "span_id")
    @classmethod
    def validate_ids(cls, v: str) -> str:
        """Validate ID format."""
        if not v:
            raise ValueError("ID cannot be empty")
        return v

    def to_headers(self) -> Dict[str, str]:
        """Convert to W3C trace context headers.

        Returns:
            Dict with traceparent header for context propagation.
        """
        # Format: version-trace_id-span_id-flags
        # trace_id: 32 hex chars, span_id: 16 hex chars
        trace_id_padded = self.trace_id.zfill(32)[-32:]
        span_id_padded = self.span_id.zfill(16)[-16:]
        flags = "01" if self.status == SpanStatus.OK else "00"
        return {
            "traceparent": f"00-{trace_id_padded}-{span_id_padded}-{flags}"
        }


class TracingGateway:
    """Gateway for OpenTelemetry tracing operations.

    Provides a unified interface for span creation, context propagation,
    and trace management with production-ready defaults.

    Example:
        >>> config = TracingConfig(service_name="my-service")
        >>> gateway = TracingGateway(config)
        >>> span = gateway.start_span("operation")
        >>> # ... do work ...
        >>> gateway.end_span(span)
    """

    def __init__(self, config: Optional[TracingConfig] = None):
        """Initialize the tracing gateway.

        Args:
            config: Tracing configuration. Uses defaults if not provided.
        """
        self.config = config or TracingConfig()
        self._tracer: Optional[trace.Tracer] = None
        self._provider: Optional[TracerProvider] = None
        self._propagator: Optional[TraceContextPropagator] = None
        self._initialized = False

        if self.config.enabled:
            self._initialize()

    def _initialize(self) -> None:
        """Initialize the OpenTelemetry SDK components."""
        if not OTEL_AVAILABLE:
            logger.warning("OpenTelemetry not available. Tracing disabled.")
            self._initialized = False
            return

        if self._initialized:
            return

        try:
            # Create resource with service information
            resource_attributes = {
                SERVICE_NAME: self.config.service_name,
                SERVICE_NAMESPACE: self.config.service_namespace,
                SERVICE_VERSION: self.config.service_version,
                DEPLOYMENT_ENVIRONMENT: self.config.environment,
                **self.config.resource_attributes
            }
            resource = Resource.create(resource_attributes)

            # Configure sampler
            sampler = ParentBased(TraceIdRatioBased(self.config.sample_rate))

            # Create tracer provider
            self._provider = TracerProvider(
                resource=resource,
                sampler=sampler
            )

            # Add span processor with exporter
            exporter = self._create_exporter()
            if exporter:
                processor = BatchSpanProcessor(
                    exporter,
                    max_queue_size=self.config.max_queue_size,
                    max_export_batch_size=self.config.max_export_batch_size,
                    export_timeout_millis=int(self.config.export_timeout * 1000),
                    schedule_delay_millis=self.config.schedule_delay_millis
                )
                self._provider.add_span_processor(processor)

            # Set global tracer provider
            trace.set_tracer_provider(self._provider)

            # Create tracer
            self._tracer = trace.get_tracer(
                self.config.service_name,
                self.config.service_version
            )

            # Initialize propagator for context propagation
            self._propagator = TraceContextPropagator()

            self._initialized = True
            logger.info(
                f"Tracing initialized: service={self.config.service_name}, "
                f"environment={self.config.environment}, "
                f"endpoint={self.config.otlp_endpoint}"
            )

        except Exception as e:
            logger.error(f"Failed to initialize tracing: {e}")
            self._initialized = False

    def _create_exporter(self) -> Optional[SpanExporter]:  # type: ignore[type-arg]
        """Create the appropriate span exporter based on configuration.

        Returns:
            SpanExporter instance or None if creation fails.
        """
        if self.config.export_protocol == ExportProtocol.CONSOLE:
            if CONSOLE_EXPORTER_AVAILABLE and ConsoleSpanExporter:
                return ConsoleSpanExporter()
            logger.warning("Console exporter not available")
            return None

        if self.config.export_protocol == ExportProtocol.HTTP:
            if OTLP_HTTP_AVAILABLE and HTTPOTLPSpanExporter:
                endpoint = self.config.otlp_endpoint
                if not endpoint.endswith("/v1/traces"):
                    endpoint = f"{endpoint.rstrip('/')}/v1/traces"
                return HTTPOTLPSpanExporter(endpoint=endpoint)
            logger.warning("HTTP OTLP exporter not available, falling back to gRPC")

        # Default to gRPC
        if OTLP_GRPC_AVAILABLE and OTLPSpanExporter:
            endpoint = self.config.otlp_endpoint
            # Strip http/https prefix for gRPC
            if endpoint.startswith("http://"):
                endpoint = endpoint[7:]
            elif endpoint.startswith("https://"):
                endpoint = endpoint[8:]
            return OTLPSpanExporter(endpoint=endpoint)

        logger.warning("No OTLP exporter available")
        return None

    @property
    def tracer(self) -> Optional[trace.Tracer]:
        """Get the tracer instance."""
        return self._tracer

    @property
    def provider(self) -> Optional[TracerProvider]:
        """Get the tracer provider instance."""
        return self._provider

    @property
    def is_initialized(self) -> bool:
        """Check if tracing is initialized and ready."""
        return self._initialized and self._tracer is not None

    def start_span(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
        kind: SpanKind = SpanKind.INTERNAL,
        parent: Optional[Context] = None
    ) -> Span:
        """Start a new span.

        Args:
            name: Name of the span/operation.
            attributes: Initial attributes for the span.
            kind: Type of span (INTERNAL, SERVER, CLIENT, PRODUCER, CONSUMER).
            parent: Parent context for span hierarchy.

        Returns:
            The created span (or a no-op span if tracing is disabled).
        """
        if not self.is_initialized or not self._tracer:
            return trace.NonRecordingSpan(trace.INVALID_SPAN_CONTEXT)

        try:
            span = self._tracer.start_span(
                name,
                attributes=attributes,
                kind=kind,
                context=parent
            )

            # Store context for tracking
            ctx = self._span_to_context(span)
            _current_span_context.set(ctx)

            return span
        except Exception as e:
            logger.error(f"Failed to start span '{name}': {e}")
            return trace.NonRecordingSpan(trace.INVALID_SPAN_CONTEXT)

    def end_span(
        self,
        span: Span,
        status: Optional[StatusCode] = None,
        description: Optional[str] = None
    ) -> None:
        """End a span.

        Args:
            span: The span to end.
            status: Optional status code (OK, ERROR, UNSET).
            description: Optional status description.
        """
        if not span or not span.is_recording():
            return

        try:
            if status:
                span.set_status(Status(status, description))
            span.end()
        except Exception as e:
            logger.error(f"Failed to end span: {e}")

    def add_event(
        self,
        span: Span,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None
    ) -> None:
        """Add an event to a span.

        Args:
            span: The span to add the event to.
            name: Name of the event.
            attributes: Event attributes.
            timestamp: Event timestamp (defaults to now).
        """
        if not span or not span.is_recording():
            return

        try:
            ts_ns = None
            if timestamp:
                ts_ns = int(timestamp.timestamp() * 1e9)

            span.add_event(name, attributes=attributes, timestamp=ts_ns)
        except Exception as e:
            logger.error(f"Failed to add event '{name}' to span: {e}")

    def record_exception(
        self,
        span: Span,
        exception: Exception,
        attributes: Optional[Dict[str, Any]] = None,
        escaped: bool = False
    ) -> None:
        """Record an exception on a span.

        Args:
            span: The span to record the exception on.
            exception: The exception to record.
            attributes: Additional attributes for the exception.
            escaped: Whether the exception escaped to the caller.
        """
        if not span or not span.is_recording():
            return

        try:
            span.record_exception(exception, attributes=attributes, escaped=escaped)
            span.set_status(Status(StatusCode.ERROR, str(exception)))
        except Exception as e:
            logger.error(f"Failed to record exception on span: {e}")

    def get_current_span(self) -> Span:
        """Get the current active span.

        Returns:
            The current span (may be a no-op span if none is active).
        """
        return get_current_span()

    def get_current_span_context(self) -> Optional[SpanContext]:
        """Get the current span context from context variable.

        Returns:
            SpanContext if available, None otherwise.
        """
        return _current_span_context.get()

    def _span_to_context(self, span: Span) -> SpanContext:
        """Convert a span to SpanContext model.

        Args:
            span: The span to convert.

        Returns:
            SpanContext model instance.
        """
        ctx = span.get_span_context()

        # Extract parent span ID if available
        parent_id = None
        parent_context = span.parent
        if parent_context:
            parent_id = format(parent_context.span_id, "016x")

        return SpanContext(
            trace_id=format(ctx.trace_id, "032x"),
            span_id=format(ctx.span_id, "016x"),
            parent_span_id=parent_id,
            operation_name=span.name,
            start_time=datetime.now(timezone.utc),
            attributes=dict(span.attributes) if span.attributes else {},
            status=SpanStatus.UNSET,
            kind=str(span.kind.name) if hasattr(span.kind, 'name') else "INTERNAL"
        )

    def inject_context(self, carrier: Dict[str, Any]) -> None:
        """Inject trace context into a carrier for distributed tracing.

        Injects W3C trace context headers into the carrier for propagation
        to downstream services.

        Args:
            carrier: Dictionary to inject trace context into.
        """
        if not self._propagator:
            return

        try:
            self._propagator.inject(carrier)
        except Exception as e:
            logger.error(f"Failed to inject context: {e}")

    def extract_context(self, carrier: Dict[str, Any]) -> Context:
        """Extract trace context from a carrier for distributed tracing.

        Extracts W3C trace context headers from the carrier to continue
        a trace from an upstream service.

        Args:
            carrier: Dictionary containing trace context headers.

        Returns:
            OpenTelemetry Context for span creation.
        """
        if not self._propagator:
            return {}  # type: ignore[return-value]

        try:
            return self._propagator.extract(carrier)  # type: ignore[no-any-return]
        except Exception as e:
            logger.error(f"Failed to extract context: {e}")
            return {}  # type: ignore[return-value]

    def set_attribute(self, span: Span, key: str, value: Any) -> None:
        """Set an attribute on a span.

        Args:
            span: The span to set the attribute on.
            key: Attribute key.
            value: Attribute value.
        """
        if not span or not span.is_recording():
            return

        try:
            span.set_attribute(key, value)
        except Exception as e:
            logger.error(f"Failed to set attribute '{key}' on span: {e}")

    def set_attributes(self, span: Span, attributes: Dict[str, Any]) -> None:
        """Set multiple attributes on a span.

        Args:
            span: The span to set attributes on.
            attributes: Dictionary of attributes to set.
        """
        if not span or not span.is_recording():
            return

        try:
            span.set_attributes(attributes)
        except Exception as e:
            logger.error(f"Failed to set attributes on span: {e}")

    def update_span_name(self, span: Span, name: str) -> None:
        """Update the name of a span.

        Args:
            span: The span to update.
            name: New name for the span.
        """
        if not span or not span.is_recording():
            return

        try:
            span.update_name(name)
        except Exception as e:
            logger.error(f"Failed to update span name: {e}")

    def shutdown(self) -> None:
        """Shutdown the tracing gateway and flush pending spans.

        This should be called when the application is shutting down
        to ensure all spans are exported.
        """
        if self._provider:
            try:
                self._provider.shutdown()
                logger.info("Tracing gateway shutdown complete")
            except Exception as e:
                logger.error(f"Error during tracing shutdown: {e}")

        self._initialized = False
        self._tracer = None
        self._provider = None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Force flush all pending spans.

        Args:
            timeout_millis: Timeout for flush operation.

        Returns:
            True if flush succeeded, False otherwise.
        """
        if not self._provider:
            return True

        try:
            return self._provider.force_flush(timeout_millis)
        except Exception as e:
            logger.error(f"Error during force flush: {e}")
            return False


# Global gateway instance
_global_gateway: Optional[TracingGateway] = None


def get_tracing_gateway() -> TracingGateway:
    """Get or create the global tracing gateway.

    Returns:
        The global TracingGateway instance.
    """
    global _global_gateway
    if _global_gateway is None:
        _global_gateway = TracingGateway()
    return _global_gateway


def configure_tracing(config: TracingConfig) -> TracingGateway:
    """Configure the global tracing gateway.

    Args:
        config: Tracing configuration.

    Returns:
        The configured TracingGateway instance.
    """
    global _global_gateway
    if _global_gateway:
        _global_gateway.shutdown()
    _global_gateway = TracingGateway(config)
    return _global_gateway


def trace_operation(
    name: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None,
    kind: SpanKind = SpanKind.INTERNAL
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator for automatic tracing of functions.

    Can be used with both sync and async functions.

    Args:
        name: Span name (defaults to function name).
        attributes: Static attributes for the span.
        kind: Type of span.

    Returns:
        Decorated function with automatic tracing.

    Example:
        @trace_operation("database_query", {"db.system": "postgresql"})
        async def query_users():
            # ... query logic ...
            pass
    """
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        span_name = name or func.__name__

        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            gateway = get_tracing_gateway()

            if not gateway.is_initialized:
                return await func(*args, **kwargs)  # type: ignore[misc]

            span = gateway.start_span(span_name, attributes=attributes, kind=kind)

            # Add function metadata
            gateway.set_attribute(span, "code.function", func.__name__)
            gateway.set_attribute(span, "code.module", func.__module__)

            try:
                result = await func(*args, **kwargs)  # type: ignore[misc]
                gateway.end_span(span, StatusCode.OK)
                return result
            except Exception as e:
                gateway.record_exception(span, e)
                gateway.end_span(span, StatusCode.ERROR, str(e))
                raise

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            gateway = get_tracing_gateway()

            if not gateway.is_initialized:
                return func(*args, **kwargs)

            span = gateway.start_span(span_name, attributes=attributes, kind=kind)

            # Add function metadata
            gateway.set_attribute(span, "code.function", func.__name__)
            gateway.set_attribute(span, "code.module", func.__module__)

            try:
                result = func(*args, **kwargs)
                gateway.end_span(span, StatusCode.OK)
                return result
            except Exception as e:
                gateway.record_exception(span, e)
                gateway.end_span(span, StatusCode.ERROR, str(e))
                raise

        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper  # type: ignore[return-value]

    return decorator


class traced_operation:
    """Context manager for automatic tracing of code blocks.

    Provides a convenient way to trace a block of code with automatic
    span lifecycle management.

    Example:
        async with traced_operation("process_request", {"request.id": "123"}):
            # ... processing logic ...
            pass
    """

    def __init__(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
        kind: SpanKind = SpanKind.INTERNAL,
        gateway: Optional[TracingGateway] = None
    ):
        """Initialize the traced operation.

        Args:
            name: Span name.
            attributes: Span attributes.
            kind: Type of span.
            gateway: TracingGateway instance (uses global if not provided).
        """
        self.name = name
        self.attributes = attributes or {}
        self.kind = kind
        self._gateway = gateway or get_tracing_gateway()
        self._span: Optional[Span] = None

    def __enter__(self) -> Span:
        """Enter the traced context (sync version).

        Returns:
            The created span.
        """
        if not self._gateway.is_initialized:
            self._span = trace.NonRecordingSpan(trace.INVALID_SPAN_CONTEXT)
        else:
            self._span = self._gateway.start_span(
                self.name,
                attributes=self.attributes,
                kind=self.kind
            )
        return self._span

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any]
    ) -> None:
        """Exit the traced context (sync version).

        Args:
            exc_type: Exception type if raised.
            exc_val: Exception value if raised.
            exc_tb: Exception traceback if raised.
        """
        if not self._span:
            return

        if exc_type:
            self._gateway.record_exception(self._span, exc_val or Exception("Unknown error"))
            self._gateway.end_span(self._span, StatusCode.ERROR, str(exc_val))
        else:
            self._gateway.end_span(self._span, StatusCode.OK)

    async def __aenter__(self) -> Span:
        """Enter the traced context (async version).

        Returns:
            The created span.
        """
        return self.__enter__()

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any]
    ) -> None:
        """Exit the traced context (async version).

        Args:
            exc_type: Exception type if raised.
            exc_val: Exception value if raised.
            exc_tb: Exception traceback if raised.
        """
        self.__exit__(exc_type, exc_val, exc_tb)


@asynccontextmanager
async def traced_async(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
    kind: SpanKind = SpanKind.INTERNAL
) -> AsyncGenerator[Span, None]:
    """Async context manager for tracing.

    Args:
        name: Span name.
        attributes: Span attributes.
        kind: Type of span.

    Yields:
        The created span.

    Example:
        async with traced_async("http_request", {"http.method": "GET"}) as span:
            # ... request logic ...
            pass
    """
    gateway = get_tracing_gateway()

    if not gateway.is_initialized:
        yield trace.NonRecordingSpan(trace.INVALID_SPAN_CONTEXT)
        return

    span = gateway.start_span(name, attributes=attributes, kind=kind)

    try:
        yield span
        gateway.end_span(span, StatusCode.OK)
    except Exception as e:
        gateway.record_exception(span, e)
        gateway.end_span(span, StatusCode.ERROR, str(e))
        raise


class TracingMiddleware:
    """Middleware for automatic request tracing.

    Can be used with web frameworks like FastAPI for automatic
    request/response tracing.

    Example:
        app = FastAPI()
        middleware = TracingMiddleware(config)
        app.middleware("http")(middleware)
    """

    def __init__(self, config: Optional[TracingConfig] = None):
        """Initialize the middleware.

        Args:
            config: Tracing configuration.
        """
        self.gateway = TracingGateway(config)

    async def __call__(self, request: Any, call_next: Any) -> Any:
        """Process a request with tracing.

        Args:
            request: The incoming request.
            call_next: The next middleware/handler.

        Returns:
            The response.
        """
        # Extract context from incoming headers
        headers = dict(request.headers)
        parent_context = self.gateway.extract_context(headers)

        # Start span
        span_name = f"{request.method} {request.url.path}"
        span = self.gateway.start_span(
            span_name,
            attributes={
                "http.method": request.method,
                "http.url": str(request.url),
                "http.route": request.url.path,
                "http.scheme": request.url.scheme,
                "http.host": request.headers.get("host", "unknown"),
            },
            kind=SpanKind.SERVER,
            parent=parent_context
        )

        try:
            response = await call_next(request)

            # Add response attributes
            self.gateway.set_attribute(span, "http.status_code", response.status_code)

            status = StatusCode.OK if response.status_code < 400 else StatusCode.ERROR
            self.gateway.end_span(span, status)

            return response

        except Exception as e:
            self.gateway.record_exception(span, e)
            self.gateway.end_span(span, StatusCode.ERROR, str(e))
            raise
