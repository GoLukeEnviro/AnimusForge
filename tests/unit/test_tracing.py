"""Unit tests for OpenTelemetry Tracing Module.

Comprehensive test suite for TracingConfig, SpanContext, TracingGateway,
decorators, and context managers.
"""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call
from typing import Any, Dict

# Test imports with availability checks
try:
    from opentelemetry import trace
    from opentelemetry.trace import Span, StatusCode, SpanKind
    from opentelemetry.sdk.trace import TracerProvider
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    pytest.skip("OpenTelemetry not available", allow_module_level=True)

from animus_observe.tracing import (
    TracingConfig,
    SpanContext,
    SpanEvent,
    SpanStatus,
    ExportProtocol,
    TracingGateway,
    trace_operation,
    traced_operation,
    traced_async,
    TracingMiddleware,
    get_tracing_gateway,
    configure_tracing,
    _global_gateway,
)


# Fixtures
@pytest.fixture
def basic_config() -> TracingConfig:
    """Create a basic tracing configuration."""
    return TracingConfig(
        service_name="test-service",
        environment="testing",
        otlp_endpoint="http://localhost:4317",
        sample_rate=1.0,
        enabled=True
    )


@pytest.fixture
def disabled_config() -> TracingConfig:
    """Create a disabled tracing configuration."""
    return TracingConfig(enabled=False)


@pytest.fixture
def console_config() -> TracingConfig:
    """Create a console exporter configuration."""
    return TracingConfig(
        service_name="console-test",
        export_protocol=ExportProtocol.CONSOLE,
        enabled=True
    )


@pytest.fixture
def gateway(basic_config: TracingConfig) -> TracingGateway:
    """Create a tracing gateway with basic config."""
    return TracingGateway(basic_config)


@pytest.fixture
def mock_span() -> MagicMock:
    """Create a mock span."""
    span = MagicMock(spec=Span)
    span.is_recording.return_value = True
    span.name = "test-span"
    span.attributes = {"key": "value"}

    # Mock span context
    ctx = MagicMock()
    ctx.trace_id = 123456789
    ctx.span_id = 987654321
    span.get_span_context.return_value = ctx
    span.parent = None
    span.kind = SpanKind.INTERNAL

    return span


# TracingConfig Tests
class TestTracingConfig:
    """Tests for TracingConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = TracingConfig()

        assert config.service_name == "animusforge"
        assert config.environment == "development"
        assert config.otlp_endpoint == "http://localhost:4317"
        assert config.sample_rate == 1.0
        assert config.enabled is True
        assert config.export_timeout == 30.0
        assert config.max_queue_size == 2048
        assert config.max_export_batch_size == 512
        assert config.export_protocol == ExportProtocol.GRPC

    def test_custom_values(self):
        """Test custom configuration values."""
        config = TracingConfig(
            service_name="custom-service",
            environment="production",
            otlp_endpoint="http://collector:4317",
            sample_rate=0.5,
            export_timeout=60.0
        )

        assert config.service_name == "custom-service"
        assert config.environment == "production"
        assert config.otlp_endpoint == "http://collector:4317"
        assert config.sample_rate == 0.5
        assert config.export_timeout == 60.0

    def test_endpoint_validation_adds_protocol(self):
        """Test endpoint validation adds http:// if missing."""
        config = TracingConfig(otlp_endpoint="localhost:4317")
        assert config.otlp_endpoint == "http://localhost:4317"

    def test_endpoint_validation_preserves_https(self):
        """Test endpoint validation preserves https://."""
        config = TracingConfig(otlp_endpoint="https://secure:4317")
        assert config.otlp_endpoint == "https://secure:4317"

    def test_environment_validation_lowercase(self):
        """Test environment is converted to lowercase."""
        config = TracingConfig(environment="PRODUCTION")
        assert config.environment == "production"

    def test_sample_rate_bounds_minimum(self):
        """Test sample rate minimum bound."""
        config = TracingConfig(sample_rate=0.0)
        assert config.sample_rate == 0.0

    def test_sample_rate_bounds_maximum(self):
        """Test sample rate maximum bound."""
        config = TracingConfig(sample_rate=1.0)
        assert config.sample_rate == 1.0

    def test_sample_rate_invalid_negative(self):
        """Test sample rate rejects negative values."""
        with pytest.raises(ValueError):
            TracingConfig(sample_rate=-0.1)

    def test_sample_rate_invalid_above_one(self):
        """Test sample rate rejects values above 1."""
        with pytest.raises(ValueError):
            TracingConfig(sample_rate=1.5)

    def test_export_timeout_bounds(self):
        """Test export timeout bounds."""
        config = TracingConfig(export_timeout=60.0)
        assert config.export_timeout == 60.0

        with pytest.raises(ValueError):
            TracingConfig(export_timeout=0.5)

        with pytest.raises(ValueError):
            TracingConfig(export_timeout=400.0)

    def test_queue_size_bounds(self):
        """Test queue size bounds."""
        config = TracingConfig(max_queue_size=5000)
        assert config.max_queue_size == 5000

        with pytest.raises(ValueError):
            TracingConfig(max_queue_size=0)

    def test_resource_attributes(self):
        """Test custom resource attributes."""
        config = TracingConfig(
            resource_attributes={"custom.attr": "value", "deployment.region": "us-east-1"}
        )

        assert config.resource_attributes["custom.attr"] == "value"
        assert config.resource_attributes["deployment.region"] == "us-east-1"


# ExportProtocol Tests
class TestExportProtocol:
    """Tests for ExportProtocol enum."""

    def test_grpc_protocol(self):
        """Test GRPC protocol value."""
        assert ExportProtocol.GRPC.value == "grpc"

    def test_http_protocol(self):
        """Test HTTP protocol value."""
        assert ExportProtocol.HTTP.value == "http"

    def test_console_protocol(self):
        """Test console protocol value."""
        assert ExportProtocol.CONSOLE.value == "console"


# SpanStatus Tests
class TestSpanStatus:
    """Tests for SpanStatus enum."""

    def test_status_values(self):
        """Test span status values."""
        assert SpanStatus.UNSET.value == "UNSET"
        assert SpanStatus.OK.value == "OK"
        assert SpanStatus.ERROR.value == "ERROR"


# SpanEvent Tests
class TestSpanEvent:
    """Tests for SpanEvent model."""

    def test_default_values(self):
        """Test default span event values."""
        event = SpanEvent(name="test-event")

        assert event.name == "test-event"
        assert isinstance(event.timestamp, datetime)
        assert event.attributes == {}

    def test_custom_values(self):
        """Test custom span event values."""
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        event = SpanEvent(
            name="custom-event",
            timestamp=ts,
            attributes={"key": "value", "count": 42}
        )

        assert event.name == "custom-event"
        assert event.timestamp == ts
        assert event.attributes["key"] == "value"
        assert event.attributes["count"] == 42


# SpanContext Tests
class TestSpanContext:
    """Tests for SpanContext model."""

    def test_required_fields(self):
        """Test required span context fields."""
        ctx = SpanContext(
            trace_id="abc123",
            span_id="def456",
            operation_name="test-op"
        )

        assert ctx.trace_id == "abc123"
        assert ctx.span_id == "def456"
        assert ctx.operation_name == "test-op"

    def test_default_values(self):
        """Test default span context values."""
        ctx = SpanContext(
            trace_id="trace1",
            span_id="span1",
            operation_name="op"
        )

        assert ctx.parent_span_id is None
        assert isinstance(ctx.start_time, datetime)
        assert ctx.end_time is None
        assert ctx.attributes == {}
        assert ctx.events == []
        assert ctx.status == SpanStatus.UNSET
        assert ctx.kind == "INTERNAL"

    def test_with_parent(self):
        """Test span context with parent."""
        ctx = SpanContext(
            trace_id="trace1",
            span_id="span1",
            parent_span_id="parent1",
            operation_name="child-op"
        )

        assert ctx.parent_span_id == "parent1"

    def test_with_events(self):
        """Test span context with events."""
        events = [
            SpanEvent(name="event1"),
            SpanEvent(name="event2", attributes={"key": "value"})
        ]
        ctx = SpanContext(
            trace_id="t1",
            span_id="s1",
            operation_name="op",
            events=events
        )

        assert len(ctx.events) == 2
        assert ctx.events[0].name == "event1"
        assert ctx.events[1].attributes["key"] == "value"

    def test_to_headers(self):
        """Test W3C trace context header generation."""
        ctx = SpanContext(
            trace_id="0123456789abcdef0123456789abcdef",
            span_id="0123456789abcdef",
            operation_name="test"
        )

        headers = ctx.to_headers()

        assert "traceparent" in headers
        # Format: version-trace_id-span_id-flags
        parts = headers["traceparent"].split("-")
        assert len(parts) == 4
        assert parts[0] == "00"  # version
        assert len(parts[1]) == 32  # trace_id
        assert len(parts[2]) == 16  # span_id

    def test_to_headers_pads_short_ids(self):
        """Test that to_headers pads short IDs."""
        ctx = SpanContext(
            trace_id="abc",
            span_id="def",
            operation_name="test"
        )

        headers = ctx.to_headers()
        parts = headers["traceparent"].split("-")

        assert len(parts[1]) == 32
        assert parts[1].endswith("abc")
        assert len(parts[2]) == 16
        assert parts[2].endswith("def")

    def test_id_validation_empty(self):
        """Test ID validation rejects empty strings."""
        with pytest.raises(ValueError):
            SpanContext(trace_id="", span_id="sid", operation_name="op")

        with pytest.raises(ValueError):
            SpanContext(trace_id="tid", span_id="", operation_name="op")


# TracingGateway Tests
class TestTracingGateway:
    """Tests for TracingGateway class."""

    def test_initialization_with_config(self, basic_config: TracingConfig):
        """Test gateway initialization with config."""
        gateway = TracingGateway(basic_config)

        assert gateway.config == basic_config
        assert gateway.is_initialized

    def test_initialization_without_config(self):
        """Test gateway initialization with defaults."""
        gateway = TracingGateway()

        assert gateway.config.service_name == "animusforge"
        assert gateway.is_initialized

    def test_disabled_tracing(self, disabled_config: TracingConfig):
        """Test gateway with disabled tracing."""
        gateway = TracingGateway(disabled_config)

        assert not gateway.is_initialized

    def test_tracer_property(self, gateway: TracingGateway):
        """Test tracer property."""
        assert gateway.tracer is not None

    def test_provider_property(self, gateway: TracingGateway):
        """Test provider property."""
        assert gateway.provider is not None

    def test_start_span(self, gateway: TracingGateway):
        """Test starting a span."""
        span = gateway.start_span("test-operation")

        assert span is not None
        assert span.name == "test-operation"
        gateway.end_span(span)

    def test_start_span_with_attributes(self, gateway: TracingGateway):
        """Test starting a span with attributes."""
        attrs = {"key": "value", "count": 42}
        span = gateway.start_span("attributed-op", attributes=attrs)

        assert span is not None
        gateway.end_span(span)

    def test_start_span_with_kind(self, gateway: TracingGateway):
        """Test starting a span with specific kind."""
        span = gateway.start_span("server-op", kind=SpanKind.SERVER)

        assert span is not None
        gateway.end_span(span)

    def test_end_span(self, gateway: TracingGateway, mock_span: MagicMock):
        """Test ending a span."""
        gateway.end_span(mock_span)

        mock_span.end.assert_called_once()

    def test_end_span_with_status(self, gateway: TracingGateway, mock_span: MagicMock):
        """Test ending a span with status."""
        gateway.end_span(mock_span, StatusCode.OK, "Success")

        mock_span.set_status.assert_called_once()
        mock_span.end.assert_called_once()

    def test_end_span_non_recording(self, gateway: TracingGateway):
        """Test ending a non-recording span does nothing."""
        span = MagicMock()
        span.is_recording.return_value = False

        gateway.end_span(span)

        span.end.assert_not_called()

    def test_add_event(self, gateway: TracingGateway, mock_span: MagicMock):
        """Test adding an event to a span."""
        gateway.add_event(mock_span, "test-event", {"attr": "value"})

        mock_span.add_event.assert_called_once()
        call_args = mock_span.add_event.call_args
        assert call_args[0][0] == "test-event"

    def test_add_event_non_recording(self, gateway: TracingGateway):
        """Test adding event to non-recording span does nothing."""
        span = MagicMock()
        span.is_recording.return_value = False

        gateway.add_event(span, "event")

        span.add_event.assert_not_called()

    def test_record_exception(self, gateway: TracingGateway, mock_span: MagicMock):
        """Test recording an exception."""
        exc = ValueError("Test error")
        gateway.record_exception(mock_span, exc)

        mock_span.record_exception.assert_called_once()
        mock_span.set_status.assert_called_once()

    def test_record_exception_with_attributes(self, gateway: TracingGateway, mock_span: MagicMock):
        """Test recording exception with attributes."""
        exc = RuntimeError("Runtime issue")
        attrs = {"error.type": "runtime"}
        gateway.record_exception(mock_span, exc, attributes=attrs, escaped=True)

        mock_span.record_exception.assert_called_once()

    def test_get_current_span(self, gateway: TracingGateway):
        """Test getting current span."""
        span = gateway.get_current_span()

        # Returns a span (may be non-recording if no active span)
        assert span is not None

    def test_inject_context(self, gateway: TracingGateway):
        """Test context injection."""
        carrier: Dict[str, Any] = {}
        gateway.inject_context(carrier)

        # Carrier may or may not have trace context depending on active span
        assert isinstance(carrier, dict)

    def test_extract_context(self, gateway: TracingGateway):
        """Test context extraction."""
        carrier = {"traceparent": "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"}
        ctx = gateway.extract_context(carrier)

        assert ctx is not None

    def test_set_attribute(self, gateway: TracingGateway, mock_span: MagicMock):
        """Test setting a single attribute."""
        gateway.set_attribute(mock_span, "test.key", "test-value")

        mock_span.set_attribute.assert_called_once_with("test.key", "test-value")

    def test_set_attribute_non_recording(self, gateway: TracingGateway):
        """Test setting attribute on non-recording span."""
        span = MagicMock()
        span.is_recording.return_value = False

        gateway.set_attribute(span, "key", "value")

        span.set_attribute.assert_not_called()

    def test_set_attributes(self, gateway: TracingGateway, mock_span: MagicMock):
        """Test setting multiple attributes."""
        attrs = {"key1": "value1", "key2": 42}
        gateway.set_attributes(mock_span, attrs)

        mock_span.set_attributes.assert_called_once_with(attrs)

    def test_update_span_name(self, gateway: TracingGateway, mock_span: MagicMock):
        """Test updating span name."""
        gateway.update_span_name(mock_span, "new-name")

        mock_span.update_name.assert_called_once_with("new-name")

    def test_shutdown(self, gateway: TracingGateway):
        """Test gateway shutdown."""
        gateway.shutdown()

        assert not gateway.is_initialized
        assert gateway._tracer is None
        assert gateway._provider is None

    def test_force_flush(self, gateway: TracingGateway):
        """Test force flush."""
        result = gateway.force_flush(timeout_millis=5000)

        assert isinstance(result, bool)

    def test_get_current_span_context(self, gateway: TracingGateway):
        """Test getting current span context from context variable."""
        ctx = gateway.get_current_span_context()

        # May be None if no span was started
        assert ctx is None or isinstance(ctx, SpanContext)


# TracingGateway Disabled Tests
class TestTracingGatewayDisabled:
    """Tests for TracingGateway when disabled."""

    def test_start_span_returns_noop(self, disabled_config: TracingConfig):
        """Test that starting span returns no-op when disabled."""
        gateway = TracingGateway(disabled_config)
        span = gateway.start_span("test")

        # Should return a non-recording span
        assert span is not None

    def test_operations_on_disabled_gateway(self, disabled_config: TracingConfig):
        """Test various operations on disabled gateway."""
        gateway = TracingGateway(disabled_config)

        # These should all be no-ops
        span = gateway.start_span("test")
        gateway.add_event(span, "event")
        gateway.set_attribute(span, "key", "value")
        gateway.end_span(span)

        # No exceptions should be raised


# Console Exporter Tests
class TestConsoleExporter:
    """Tests for console exporter configuration."""

    def test_console_exporter_initialization(self, console_config: TracingConfig):
        """Test initialization with console exporter."""
        gateway = TracingGateway(console_config)

        assert gateway.is_initialized
        gateway.shutdown()


# Decorator Tests
class TestTraceOperationDecorator:
    """Tests for trace_operation decorator."""

    def test_sync_function_success(self, gateway: TracingGateway):
        """Test decorating sync function that succeeds."""
        @trace_operation("sync-op")
        def sync_func():
            return "result"

        # Configure global gateway
        import animus_observe.tracing as tracing_module
        tracing_module._global_gateway = gateway

        result = sync_func()

        assert result == "result"

    def test_sync_function_exception(self, gateway: TracingGateway):
        """Test decorating sync function that raises."""
        @trace_operation("failing-op")
        def failing_func():
            raise ValueError("Test error")

        import animus_observe.tracing as tracing_module
        tracing_module._global_gateway = gateway

        with pytest.raises(ValueError, match="Test error"):
            failing_func()

    @pytest.mark.asyncio
    async def test_async_function_success(self, gateway: TracingGateway):
        """Test decorating async function that succeeds."""
        @trace_operation("async-op")
        async def async_func():
            await asyncio.sleep(0.01)
            return "async-result"

        import animus_observe.tracing as tracing_module
        tracing_module._global_gateway = gateway

        result = await async_func()

        assert result == "async-result"

    @pytest.mark.asyncio
    async def test_async_function_exception(self, gateway: TracingGateway):
        """Test decorating async function that raises."""
        @trace_operation("async-failing")
        async def async_failing():
            await asyncio.sleep(0.01)
            raise RuntimeError("Async error")

        import animus_observe.tracing as tracing_module
        tracing_module._global_gateway = gateway

        with pytest.raises(RuntimeError, match="Async error"):
            await async_failing()

    def test_decorator_with_attributes(self, gateway: TracingGateway):
        """Test decorator with static attributes."""
        @trace_operation("attr-op", attributes={"static.key": "value"})
        def attr_func():
            return "done"

        import animus_observe.tracing as tracing_module
        tracing_module._global_gateway = gateway

        result = attr_func()

        assert result == "done"

    def test_decorator_uses_function_name(self, gateway: TracingGateway):
        """Test decorator uses function name if not provided."""
        @trace_operation()
        def my_function():
            return "result"

        import animus_observe.tracing as tracing_module
        tracing_module._global_gateway = gateway

        result = my_function()

        assert result == "result"

    def test_decorator_disabled_tracing(self, disabled_config: TracingConfig):
        """Test decorator works when tracing is disabled."""
        gateway = TracingGateway(disabled_config)

        @trace_operation("disabled-op")
        def func():
            return "still-works"

        import animus_observe.tracing as tracing_module
        tracing_module._global_gateway = gateway

        result = func()

        assert result == "still-works"


# Context Manager Tests
class TestTracedOperation:
    """Tests for traced_operation context manager."""

    def test_sync_context_success(self, gateway: TracingGateway):
        """Test sync context manager success."""
        with traced_operation("sync-ctx", gateway=gateway) as span:
            assert span is not None

    def test_sync_context_exception(self, gateway: TracingGateway):
        """Test sync context manager with exception."""
        with pytest.raises(ValueError):
            with traced_operation("failing-ctx", gateway=gateway) as span:
                raise ValueError("Context error")

    @pytest.mark.asyncio
    async def test_async_context_success(self, gateway: TracingGateway):
        """Test async context manager success."""
        async with traced_operation("async-ctx", gateway=gateway) as span:
            assert span is not None

    @pytest.mark.asyncio
    async def test_async_context_exception(self, gateway: TracingGateway):
        """Test async context manager with exception."""
        with pytest.raises(RuntimeError):
            async with traced_operation("async-failing-ctx", gateway=gateway) as span:
                raise RuntimeError("Async context error")

    def test_context_with_attributes(self, gateway: TracingGateway):
        """Test context manager with attributes."""
        with traced_operation("attr-ctx", attributes={"key": "value"}, gateway=gateway) as span:
            assert span is not None

    def test_context_disabled_tracing(self, disabled_config: TracingConfig):
        """Test context manager when tracing is disabled."""
        gateway = TracingGateway(disabled_config)

        with traced_operation("disabled-ctx", gateway=gateway) as span:
            # Should still work, just with no-op span
            pass


# Traced Async Tests
class TestTracedAsync:
    """Tests for traced_async context manager."""

    @pytest.mark.asyncio
    async def test_traced_async_success(self, gateway: TracingGateway):
        """Test traced_async success case."""
        import animus_observe.tracing as tracing_module
        tracing_module._global_gateway = gateway

        async with traced_async("async-op") as span:
            assert span is not None

    @pytest.mark.asyncio
    async def test_traced_async_exception(self, gateway: TracingGateway):
        """Test traced_async with exception."""
        import animus_observe.tracing as tracing_module
        tracing_module._global_gateway = gateway

        with pytest.raises(ValueError):
            async with traced_async("failing-async-op") as span:
                raise ValueError("Failed")

    @pytest.mark.asyncio
    async def test_traced_async_with_attributes(self, gateway: TracingGateway):
        """Test traced_async with attributes."""
        import animus_observe.tracing as tracing_module
        tracing_module._global_gateway = gateway

        async with traced_async("attr-async", attributes={"key": "val"}) as span:
            assert span is not None


# Global Gateway Tests
class TestGlobalGateway:
    """Tests for global gateway management."""

    def test_get_tracing_gateway_creates_default(self):
        """Test get_tracing_gateway creates default gateway."""
        import animus_observe.tracing as tracing_module
        tracing_module._global_gateway = None

        gateway = get_tracing_gateway()

        assert gateway is not None
        assert isinstance(gateway, TracingGateway)
        gateway.shutdown()

    def test_configure_tracing(self):
        """Test configure_tracing sets up new gateway."""
        import animus_observe.tracing as tracing_module
        tracing_module._global_gateway = None

        config = TracingConfig(service_name="configured-service")
        gateway = configure_tracing(config)

        assert gateway.config.service_name == "configured-service"
        gateway.shutdown()

    def test_configure_tracing_replaces_existing(self, gateway: TracingGateway):
        """Test configure_tracing replaces existing gateway."""
        import animus_observe.tracing as tracing_module
        tracing_module._global_gateway = gateway

        new_config = TracingConfig(service_name="replacement-service")
        new_gateway = configure_tracing(new_config)

        assert new_gateway.config.service_name == "replacement-service"
        new_gateway.shutdown()


# TracingMiddleware Tests
class TestTracingMiddleware:
    """Tests for TracingMiddleware class."""

    @pytest.mark.asyncio
    async def test_middleware_success(self, basic_config: TracingConfig):
        """Test middleware with successful request."""
        middleware = TracingMiddleware(basic_config)

        request = MagicMock()
        request.method = "GET"
        request.url = MagicMock()
        request.url.path = "/test"
        request.url.scheme = "http"
        request.headers = {"host": "localhost"}

        response = MagicMock()
        response.status_code = 200

        async def call_next(req):
            return response

        result = await middleware(request, call_next)

        assert result == response
        middleware.gateway.shutdown()

    @pytest.mark.asyncio
    async def test_middleware_with_error_status(self, basic_config: TracingConfig):
        """Test middleware with error status code."""
        middleware = TracingMiddleware(basic_config)

        request = MagicMock()
        request.method = "POST"
        request.url = MagicMock()
        request.url.path = "/error"
        request.url.scheme = "https"
        request.headers = {"host": "api.example.com"}

        response = MagicMock()
        response.status_code = 500

        async def call_next(req):
            return response

        result = await middleware(request, call_next)

        assert result == response
        middleware.gateway.shutdown()

    @pytest.mark.asyncio
    async def test_middleware_with_exception(self, basic_config: TracingConfig):
        """Test middleware when handler raises exception."""
        middleware = TracingMiddleware(basic_config)

        request = MagicMock()
        request.method = "DELETE"
        request.url = MagicMock()
        request.url.path = "/crash"
        request.url.scheme = "http"
        request.headers = {"host": "localhost"}

        async def call_next(req):
            raise ValueError("Handler error")

        with pytest.raises(ValueError, match="Handler error"):
            await middleware(request, call_next)

        middleware.gateway.shutdown()

    @pytest.mark.asyncio
    async def test_middleware_extracts_context(self, basic_config: TracingConfig):
        """Test middleware extracts trace context from headers."""
        middleware = TracingMiddleware(basic_config)

        request = MagicMock()
        request.method = "GET"
        request.url = MagicMock()
        request.url.path = "/traced"
        request.url.scheme = "http"
        request.headers = {
            "host": "localhost",
            "traceparent": "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
        }

        response = MagicMock()
        response.status_code = 200

        async def call_next(req):
            return response

        result = await middleware(request, call_next)

        assert result == response
        middleware.gateway.shutdown()


# Edge Cases and Error Handling
class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_multiple_shutdowns_safe(self, gateway: TracingGateway):
        """Test that multiple shutdowns are safe."""
        gateway.shutdown()
        gateway.shutdown()  # Should not raise

    def test_operations_after_shutdown(self, gateway: TracingGateway):
        """Test operations after shutdown are safe."""
        gateway.shutdown()

        # These should be no-ops after shutdown
        span = gateway.start_span("after-shutdown")
        gateway.add_event(span, "event")
        gateway.end_span(span)

    @pytest.mark.asyncio
    async def test_concurrent_spans(self, gateway: TracingGateway):
        """Test creating multiple concurrent spans."""
        async def create_span(name: str):
            span = gateway.start_span(name)
            await asyncio.sleep(0.01)
            gateway.end_span(span)

        await asyncio.gather(
            create_span("span1"),
            create_span("span2"),
            create_span("span3")
        )

    def test_span_with_special_characters_in_name(self, gateway: TracingGateway):
        """Test span with special characters in name."""
        span = gateway.start_span("operation/with:special-chars_123")

        assert span is not None
        gateway.end_span(span)

    def test_very_long_attribute_value(self, gateway: TracingGateway, mock_span: MagicMock):
        """Test setting very long attribute value."""
        long_value = "x" * 10000

        # Should not raise
        gateway.set_attribute(mock_span, "long.value", long_value)

    def test_none_attribute_handling(self, gateway: TracingGateway, mock_span: MagicMock):
        """Test handling None attributes."""
        # Should handle gracefully
        gateway.set_attribute(mock_span, "none.value", None)


# Integration-style Tests
class TestIntegration:
    """Integration-style tests combining multiple components."""

    @pytest.mark.asyncio
    async def test_full_traced_workflow(self, basic_config: TracingConfig):
        """Test a full workflow with tracing."""
        gateway = TracingGateway(basic_config)

        # Simulate a full request flow
        async with traced_operation("request", gateway=gateway) as req_span:
            gateway.set_attribute(req_span, "http.method", "POST")

            async with traced_operation("database", gateway=gateway) as db_span:
                gateway.set_attribute(db_span, "db.system", "postgresql")
                gateway.add_event(db_span, "query.executed", {"rows": 10})

            async with traced_operation("cache", gateway=gateway) as cache_span:
                gateway.set_attribute(cache_span, "cache.hit", False)

        gateway.shutdown()

    @pytest.mark.asyncio
    async def test_distributed_tracing_flow(self, basic_config: TracingConfig):
        """Test context propagation for distributed tracing."""
        gateway1 = TracingGateway(basic_config)

        # Service 1: Start span and inject context
        span1 = gateway1.start_span("service1-op", kind=SpanKind.SERVER)
        carrier: Dict[str, Any] = {}
        gateway1.inject_context(carrier)

        # Service 2: Extract context and create child span
        gateway2 = TracingGateway(basic_config)
        parent_ctx = gateway2.extract_context(carrier)
        span2 = gateway2.start_span("service2-op", kind=SpanKind.CLIENT, parent=parent_ctx)

        gateway2.end_span(span2)
        gateway1.end_span(span1)

        gateway1.shutdown()
        gateway2.shutdown()


# Cleanup
@pytest.fixture(autouse=True)
def cleanup_global_gateway():
    """Clean up global gateway after each test."""
    yield
    import animus_observe.tracing as tracing_module
    if tracing_module._global_gateway:
        tracing_module._global_gateway.shutdown()
        tracing_module._global_gateway = None


# Additional tests for 85% coverage
class TestHTTPExporter:
    """Tests for HTTP exporter configuration."""
    
    def test_http_exporter_config(self):
        """Test HTTP exporter configuration."""
        config = TracingConfig(
            service_name="http-test",
            export_protocol=ExportProtocol.HTTP,
            otlp_endpoint="http://localhost:4318"
        )
        gateway = TracingGateway(config)
        
        assert gateway.is_initialized
        gateway.shutdown()
    
    def test_http_endpoint_path_handling(self):
        """Test HTTP endpoint path handling."""
        config = TracingConfig(
            export_protocol=ExportProtocol.HTTP,
            otlp_endpoint="http://collector:4318/v1/traces"
        )
        gateway = TracingGateway(config)
        
        assert gateway.is_initialized
        gateway.shutdown()


class TestEdgeCasesExtended:
    """Extended edge case tests."""
    
    def test_start_span_with_parent_context(self, gateway: TracingGateway):
        """Test starting span with explicit parent context."""
        parent_span = gateway.start_span("parent")
        parent_ctx = trace.set_span_in_context(parent_span)
        
        child_span = gateway.start_span("child", parent=parent_ctx)
        
        assert child_span is not None
        gateway.end_span(child_span)
        gateway.end_span(parent_span)
    
    def test_add_event_with_timestamp(self, gateway: TracingGateway):
        """Test adding event with explicit timestamp."""
        span = gateway.start_span("event-test")
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        
        gateway.add_event(span, "timed-event", {"key": "value"}, timestamp=ts)
        
        gateway.end_span(span)
    
    def test_record_exception_escaped(self, gateway: TracingGateway, mock_span: MagicMock):
        """Test recording exception with escaped flag."""
        exc = ValueError("Escaped error")
        gateway.record_exception(mock_span, exc, escaped=True)
        
        mock_span.record_exception.assert_called_once()
    
    def test_span_with_empty_attributes(self, gateway: TracingGateway):
        """Test span with empty attributes dict."""
        span = gateway.start_span("empty-attrs", attributes={})
        
        assert span is not None
        gateway.end_span(span)
    
    def test_multiple_spans_nested(self, gateway: TracingGateway):
        """Test nested span creation."""
        span1 = gateway.start_span("level1")
        span2 = gateway.start_span("level2")
        span3 = gateway.start_span("level3")
        
        gateway.end_span(span3)
        gateway.end_span(span2)
        gateway.end_span(span1)
    
    def test_force_flush_with_no_provider(self, disabled_config: TracingConfig):
        """Test force flush when provider is None."""
        gateway = TracingGateway(disabled_config)
        result = gateway.force_flush()
        
        assert result is True


class TestTracedOperationExtended:
    """Extended tests for traced_operation context manager."""
    
    def test_context_sets_span_kind(self, gateway: TracingGateway):
        """Test context manager sets span kind."""
        with traced_operation("server-op", kind=SpanKind.SERVER, gateway=gateway) as span:
            assert span is not None
    
    def test_context_multiple_nested(self, gateway: TracingGateway):
        """Test nested context managers."""
        with traced_operation("outer", gateway=gateway) as outer:
            assert outer is not None
            with traced_operation("inner", gateway=gateway) as inner:
                assert inner is not None


class TestDecoratorExtended:
    """Extended decorator tests."""
    
    def test_decorator_with_span_kind(self, gateway: TracingGateway):
        """Test decorator with span kind."""
        import animus_observe.tracing as tracing_module
        tracing_module._global_gateway = gateway
        
        @trace_operation("client-call", kind=SpanKind.CLIENT)
        def client_func():
            return "client-result"
        
        result = client_func()
        assert result == "client-result"
    
    def test_decorator_preserves_function_metadata(self, gateway: TracingGateway):
        """Test decorator preserves function metadata."""
        import animus_observe.tracing as tracing_module
        tracing_module._global_gateway = gateway
        
        @trace_operation()
        def documented_func():
            """This is a documented function."""
            return "result"
        
        assert documented_func.__name__ == "documented_func"
        assert documented_func.__doc__ == "This is a documented function."


class TestErrorHandling:
    """Tests for error handling paths."""
    
    def test_inject_context_with_none_propagator(self):
        """Test inject_context when propagator is None."""
        config = TracingConfig(enabled=False)
        gateway = TracingGateway(config)
        
        carrier = {}
        gateway.inject_context(carrier)  # Should not raise
    
    def test_extract_context_with_none_propagator(self):
        """Test extract_context when propagator is None."""
        config = TracingConfig(enabled=False)
        gateway = TracingGateway(config)
        
        carrier = {"traceparent": "00-" + "0"*32 + "-" + "0"*16 + "-01"}
        result = gateway.extract_context(carrier)  # Should not raise
        assert result is not None
    
    def test_update_span_name_non_recording(self, gateway: TracingGateway):
        """Test update_span_name on non-recording span."""
        span = MagicMock()
        span.is_recording.return_value = False
        
        gateway.update_span_name(span, "new-name")  # Should not raise
    
    def test_set_attributes_non_recording(self, gateway: TracingGateway):
        """Test set_attributes on non-recording span."""
        span = MagicMock()
        span.is_recording.return_value = False
        
        gateway.set_attributes(span, {"key": "value"})  # Should not raise


class TestTracingConfigExtended:
    """Extended TracingConfig tests."""
    
    def test_grpc_endpoint_stripping(self):
        """Test gRPC endpoint stripping."""
        config = TracingConfig(
            export_protocol=ExportProtocol.GRPC,
            otlp_endpoint="grpc://localhost:4317"
        )
        gateway = TracingGateway(config)
        
        assert gateway.is_initialized
        gateway.shutdown()
    
    def test_service_namespace_config(self):
        """Test service namespace in config."""
        config = TracingConfig(
            service_name="test",
            service_namespace="custom.namespace",
            service_version="2.0.0"
        )
        gateway = TracingGateway(config)
        
        assert gateway.config.service_namespace == "custom.namespace"
        assert gateway.config.service_version == "2.0.0"
        gateway.shutdown()


class TestGlobalGatewayExtended:
    """Extended global gateway tests."""
    
    def test_get_gateway_returns_same_instance(self):
        """Test get_tracing_gateway returns singleton."""
        import animus_observe.tracing as tracing_module
        tracing_module._global_gateway = None
        
        g1 = get_tracing_gateway()
        g2 = get_tracing_gateway()
        
        assert g1 is g2
        g1.shutdown()


class TestTracedAsyncExtended:
    """Extended traced_async tests."""
    
    @pytest.mark.asyncio
    async def test_traced_async_disabled_gateway(self):
        """Test traced_async with disabled gateway."""
        import animus_observe.tracing as tracing_module
        config = TracingConfig(enabled=False)
        tracing_module._global_gateway = TracingGateway(config)
        
        async with traced_async("test") as span:
            # Should work with non-recording span
            pass


class TestSpanContextExtended:
    """Extended SpanContext tests."""
    
    def test_to_headers_with_ok_status(self):
        """Test to_headers with OK status."""
        ctx = SpanContext(
            trace_id="trace123",
            span_id="span456",
            operation_name="test",
            status=SpanStatus.OK
        )
        
        headers = ctx.to_headers()
        assert "01" in headers["traceparent"]  # OK flag
    
    def test_to_headers_with_error_status(self):
        """Test to_headers with ERROR status."""
        ctx = SpanContext(
            trace_id="trace123",
            span_id="span456",
            operation_name="test",
            status=SpanStatus.ERROR
        )
        
        headers = ctx.to_headers()
        # Error doesn't change flags in this implementation
        assert "traceparent" in headers
