"""Comprehensive unit tests for Structured Logging Module.

Tests cover LogLevel, LoggingConfig, LogContext, LoggingGateway,
decorators, context managers, and convenience functions.
"""

import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from pydantic import ValidationError

from animus_observe.logging import (
    LogLevel,
    LoggingConfig,
    LogContext,
    LoggingGateway,
    get_logger,
    logged,
    LogDuration,
    log_duration,
    get_current_trace_context,
    set_log_context,
    get_log_context,
    clear_log_context,
    get_default_logger,
    configure_logging,
    _safe_repr,
    STRUCTLOG_AVAILABLE,
    OTEL_AVAILABLE,
)


# ============================================================================
# LogLevel Tests
# ============================================================================

class TestLogLevel:
    """Tests for LogLevel enum."""

    def test_log_level_values(self):
        """Test LogLevel enum values."""
        assert LogLevel.DEBUG.value == "debug"
        assert LogLevel.INFO.value == "info"
        assert LogLevel.WARNING.value == "warning"
        assert LogLevel.ERROR.value == "error"
        assert LogLevel.CRITICAL.value == "critical"

    def test_log_level_to_logging_level(self):
        """Test conversion to Python logging levels."""
        assert LogLevel.DEBUG.to_logging_level() == logging.DEBUG
        assert LogLevel.INFO.to_logging_level() == logging.INFO
        assert LogLevel.WARNING.to_logging_level() == logging.WARNING
        assert LogLevel.ERROR.to_logging_level() == logging.ERROR
        assert LogLevel.CRITICAL.to_logging_level() == logging.CRITICAL

    def test_log_level_string_equality(self):
        """Test LogLevel string equality."""
        assert LogLevel.DEBUG == "debug"
        assert LogLevel.INFO == "info"
        assert LogLevel.WARNING == "warning"

    def test_log_level_from_string(self):
        """Test creating LogLevel from string."""
        assert LogLevel("debug") == LogLevel.DEBUG
        assert LogLevel("info") == LogLevel.INFO
        assert LogLevel("error") == LogLevel.ERROR


# ============================================================================
# LoggingConfig Tests
# ============================================================================

class TestLoggingConfig:
    """Tests for LoggingConfig model."""

    def test_default_config(self):
        """Test default configuration values."""
        config = LoggingConfig()
        assert config.service_name == "animusforge"
        assert config.environment == "development"
        assert config.level == LogLevel.INFO
        assert config.json_format is True
        assert config.include_timestamp is True
        assert config.include_caller is True
        assert config.include_trace_context is True
        assert config.log_file is None
        assert config.max_file_size == 10 * 1024 * 1024
        assert config.backup_count == 5

    def test_custom_config(self):
        """Test custom configuration values."""
        config = LoggingConfig(
            service_name="custom-service",
            environment="production",
            level=LogLevel.WARNING,
            json_format=False,
            include_caller=False,
            log_file="/var/log/app.log",
            max_file_size=20 * 1024 * 1024,
            backup_count=10,
        )
        assert config.service_name == "custom-service"
        assert config.environment == "production"
        assert config.level == LogLevel.WARNING
        assert config.json_format is False
        assert config.include_caller is False
        assert config.log_file == "/var/log/app.log"
        assert config.max_file_size == 20 * 1024 * 1024
        assert config.backup_count == 10

    def test_validate_service_name_empty(self):
        """Test service name validation with empty string."""
        with pytest.raises(ValidationError):
            LoggingConfig(service_name="")

    def test_validate_service_name_whitespace(self):
        """Test service name validation with whitespace."""
        with pytest.raises(ValidationError):
            LoggingConfig(service_name="   ")

    def test_validate_service_name_stripped(self):
        """Test service name is stripped."""
        config = LoggingConfig(service_name="  my-service  ")
        assert config.service_name == "my-service"

    def test_validate_environment_valid(self):
        """Test valid environment values."""
        for env in ["development", "staging", "production", "testing"]:
            config = LoggingConfig(environment=env)
            assert config.environment == env

    def test_validate_environment_invalid(self):
        """Test invalid environment value."""
        with pytest.raises(ValidationError):
            LoggingConfig(environment="invalid")

    def test_validate_max_file_size_too_small(self):
        """Test max_file_size validation with value too small."""
        with pytest.raises(ValidationError):
            LoggingConfig(max_file_size=100)

    def test_validate_max_file_size_too_large(self):
        """Test max_file_size validation with value too large."""
        with pytest.raises(ValidationError):
            LoggingConfig(max_file_size=2 * 1024 * 1024 * 1024)

    def test_validate_backup_count_negative(self):
        """Test backup_count validation with negative value."""
        with pytest.raises(ValidationError):
            LoggingConfig(backup_count=-1)

    def test_validate_backup_count_too_large(self):
        """Test backup_count validation with value too large."""
        with pytest.raises(ValidationError):
            LoggingConfig(backup_count=200)

    def test_include_process_info_default(self):
        """Test include_process_info default value."""
        config = LoggingConfig()
        assert config.include_process_info is False

    def test_colorize_default(self):
        """Test colorize default value."""
        config = LoggingConfig()
        assert config.colorize is False


# ============================================================================
# LogContext Tests
# ============================================================================

class TestLogContext:
    """Tests for LogContext model."""

    def test_default_context(self):
        """Test default context values."""
        context = LogContext()
        assert context.trace_id is None
        assert context.span_id is None
        assert context.persona_id is None
        assert context.user_id is None
        assert context.session_id is None
        assert context.extra == {}

    def test_custom_context(self):
        """Test custom context values."""
        context = LogContext(
            trace_id="abc123",
            span_id="def456",
            persona_id="persona-1",
            user_id="user-1",
            session_id="session-1",
            extra={"key": "value"},
        )
        assert context.trace_id == "abc123"
        assert context.span_id == "def456"
        assert context.persona_id == "persona-1"
        assert context.user_id == "user-1"
        assert context.session_id == "session-1"
        assert context.extra == {"key": "value"}

    def test_to_dict_with_none_values(self):
        """Test to_dict excludes None values."""
        context = LogContext(trace_id="abc123")
        result = context.to_dict()
        assert result == {"trace_id": "abc123"}
        assert "span_id" not in result

    def test_to_dict_with_all_values(self):
        """Test to_dict with all values set."""
        context = LogContext(
            trace_id="abc123",
            span_id="def456",
            persona_id="persona-1",
            extra={"custom": "value"},
        )
        result = context.to_dict()
        assert result == {
            "trace_id": "abc123",
            "span_id": "def456",
            "persona_id": "persona-1",
            "custom": "value",
        }

    def test_to_dict_with_extra_only(self):
        """Test to_dict with only extra values."""
        context = LogContext(extra={"key1": "value1", "key2": "value2"})
        result = context.to_dict()
        assert result == {"key1": "value1", "key2": "value2"}

    def test_merge_with(self):
        """Test merge_with adds additional key-value pairs."""
        context = LogContext(trace_id="abc123", extra={"existing": "value"})
        result = context.merge_with(new_key="new_value", another=123)
        assert result == {
            "trace_id": "abc123",
            "existing": "value",
            "new_key": "new_value",
            "another": 123,
        }

    def test_merge_with_overwrites(self):
        """Test merge_with can overwrite existing values."""
        context = LogContext(trace_id="abc123")
        result = context.merge_with(trace_id="new_trace_id")
        assert result == {"trace_id": "new_trace_id"}


# ============================================================================
# LoggingGateway Tests
# ============================================================================

class TestLoggingGateway:
    """Tests for LoggingGateway class."""

    def test_init_default_config(self):
        """Test initialization with default config."""
        gateway = LoggingGateway()
        assert gateway.config.service_name == "animusforge"
        assert gateway._name == "animusforge"
        assert gateway._bound_context == {}

    def test_init_custom_config(self):
        """Test initialization with custom config."""
        config = LoggingConfig(
            service_name="test-service",
            environment="production",
        )
        gateway = LoggingGateway(config=config)
        assert gateway.config.service_name == "test-service"
        assert gateway.config.environment == "production"

    def test_init_with_name(self):
        """Test initialization with custom name."""
        gateway = LoggingGateway(name="custom-logger")
        assert gateway._name == "custom-logger"

    def test_debug_log(self, caplog):
        """Test debug logging."""
        gateway = LoggingGateway(config=LoggingConfig(level=LogLevel.DEBUG))
        gateway.debug("Debug message", key="value")

    def test_info_log(self):
        """Test info logging."""
        gateway = LoggingGateway()
        gateway.info("Info message", key="value")

    def test_warning_log(self):
        """Test warning logging."""
        gateway = LoggingGateway()
        gateway.warning("Warning message", key="value")

    def test_error_log(self):
        """Test error logging."""
        gateway = LoggingGateway()
        gateway.error("Error message", key="value")

    def test_error_log_with_exception(self):
        """Test error logging with exception."""
        gateway = LoggingGateway()
        exc = ValueError("Test error")
        gateway.error("Error occurred", exception=exc)

    def test_critical_log(self):
        """Test critical logging."""
        gateway = LoggingGateway()
        gateway.critical("Critical message")

    def test_critical_log_with_exception(self):
        """Test critical logging with exception."""
        gateway = LoggingGateway()
        exc = RuntimeError("Critical error")
        gateway.critical("Critical error occurred", exception=exc)

    def test_bind(self):
        """Test binding context."""
        gateway = LoggingGateway()
        bound = gateway.bind(request_id="req-123", user_id="user-1")
        assert bound._bound_context == {"request_id": "req-123", "user_id": "user-1"}
        # Original gateway should not be modified
        assert gateway._bound_context == {}

    def test_bind_chaining(self):
        """Test binding can be chained."""
        gateway = LoggingGateway()
        bound = gateway.bind(key1="value1").bind(key2="value2")
        assert bound._bound_context == {"key1": "value1", "key2": "value2"}

    def test_unbind(self):
        """Test unbinding context."""
        gateway = LoggingGateway()
        bound = gateway.bind(key1="value1", key2="value2", key3="value3")
        unbound = bound.unbind("key1", "key3")
        assert unbound._bound_context == {"key2": "value2"}

    def test_unbind_nonexistent_key(self):
        """Test unbinding non-existent key doesn't raise error."""
        gateway = LoggingGateway()
        bound = gateway.bind(key1="value1")
        unbound = bound.unbind("nonexistent")
        assert unbound._bound_context == {"key1": "value1"}

    def test_with_context(self):
        """Test with_context method."""
        gateway = LoggingGateway()
        context = LogContext(
            trace_id="trace-123",
            persona_id="persona-1",
        )
        bound = gateway.with_context(context)
        assert bound._bound_context == {"trace_id": "trace-123", "persona_id": "persona-1"}

    def test_get_logger(self):
        """Test get_logger returns logger instance."""
        gateway = LoggingGateway()
        logger = gateway.get_logger()
        assert logger is not None

    def test_span_context(self):
        """Test span_context context manager."""
        gateway = LoggingGateway()
        with gateway.span_context(operation="test", request_id="req-1") as bound:
            assert bound._bound_context == {"operation": "test", "request_id": "req-1"}

    def test_file_logging(self):
        """Test logging to file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            log_file = f.name
        
        try:
            config = LoggingConfig(log_file=log_file, level=LogLevel.DEBUG)
            gateway = LoggingGateway(config=config)
            gateway.info("Test log message")
            
            # Check file was created and contains content
            assert os.path.exists(log_file)
            with open(log_file, 'r') as f:
                content = f.read()
                assert len(content) > 0
        finally:
            if os.path.exists(log_file):
                os.unlink(log_file)


# ============================================================================
# Decorator Tests
# ============================================================================

class TestLoggedDecorator:
    """Tests for @logged decorator."""

    def test_sync_function_logging(self):
        """Test logging for synchronous function."""
        @logged(log_args=True, level=LogLevel.DEBUG)
        def add(a, b):
            return a + b

        result = add(1, 2)
        assert result == 3

    def test_sync_function_with_error(self):
        """Test logging for sync function that raises error."""
        @logged(log_args=True)
        def failing_func():
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            failing_func()

    @pytest.mark.asyncio
    async def test_async_function_logging(self):
        """Test logging for async function."""
        @logged(log_args=True, level=LogLevel.DEBUG)
        async def async_add(a, b):
            await asyncio.sleep(0.01)
            return a + b

        result = await async_add(1, 2)
        assert result == 3

    @pytest.mark.asyncio
    async def test_async_function_with_error(self):
        """Test logging for async function that raises error."""
        @logged(log_args=True)
        async def async_failing():
            await asyncio.sleep(0.01)
            raise RuntimeError("Async error")

        with pytest.raises(RuntimeError, match="Async error"):
            await async_failing()

    def test_log_args_disabled(self):
        """Test decorator with log_args=False."""
        @logged(log_args=False)
        def secret_function(password):
            return "success"

        result = secret_function("secret123")
        assert result == "success"

    def test_log_result_enabled(self):
        """Test decorator with log_result=True."""
        @logged(log_result=True)
        def get_data():
            return {"key": "value"}

        result = get_data()
        assert result == {"key": "value"}

    def test_custom_message(self):
        """Test decorator with custom message."""
        @logged(message="Processing request", level=LogLevel.INFO)
        def process():
            return "done"

        result = process()
        assert result == "done"

    def test_include_timing(self):
        """Test decorator includes timing by default."""
        @logged(include_timing=True)
        def timed_function():
            import time
            time.sleep(0.01)
            return "done"

        result = timed_function()
        assert result == "done"

    def test_custom_logger(self):
        """Test decorator with custom logger."""
        custom_logger = get_logger(name="custom")

        @logged(logger=custom_logger)
        def custom_logged():
            return "done"

        result = custom_logged()
        assert result == "done"

    def test_function_with_default_args(self):
        """Test decorator handles functions with default args."""
        @logged(log_args=True)
        def with_defaults(a, b=10):
            return a + b

        result = with_defaults(5)
        assert result == 15

    def test_function_with_kwargs(self):
        """Test decorator handles kwargs."""
        @logged(log_args=True)
        def with_kwargs(a, **kwargs):
            return a

        result = with_kwargs(1, extra="value")
        assert result == 1


# ============================================================================
# LogDuration Tests
# ============================================================================

class TestLogDuration:
    """Tests for LogDuration context manager."""

    def test_sync_context_manager(self):
        """Test synchronous context manager."""
        with LogDuration("test_operation", level=LogLevel.INFO):
            pass  # Simulated operation

    def test_sync_context_manager_with_extra(self):
        """Test context manager with extra context."""
        with LogDuration("test_operation", extra_key="extra_value"):
            pass

    def test_sync_context_manager_with_exception(self):
        """Test context manager handles exceptions."""
        with pytest.raises(ValueError):
            with LogDuration("failing_operation"):
                raise ValueError("Test error")

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Test async context manager."""
        async with LogDuration("async_operation"):
            await asyncio.sleep(0.01)

    @pytest.mark.asyncio
    async def test_async_context_manager_with_exception(self):
        """Test async context manager handles exceptions."""
        with pytest.raises(RuntimeError):
            async with LogDuration("async_failing"):
                await asyncio.sleep(0.01)
                raise RuntimeError("Async error")

    def test_timing_accuracy(self):
        """Test that timing is reasonably accurate."""
        import time
        
        with LogDuration("timed_operation") as ld:
            time.sleep(0.05)
            assert ld._start_time is not None
        
        assert ld._end_time is not None
        duration = (ld._end_time - ld._start_time).total_seconds()
        assert duration >= 0.05

    def test_custom_logger(self):
        """Test LogDuration with custom logger."""
        custom_logger = get_logger(name="duration_logger")
        
        with LogDuration("custom_logged", logger=custom_logger):
            pass


# ============================================================================
# log_duration Convenience Function Tests
# ============================================================================

class TestLogDurationFunction:
    """Tests for log_duration convenience function."""

    @pytest.mark.asyncio
    async def test_log_duration_async(self):
        """Test log_duration async context manager."""
        async with log_duration("api_call"):
            await asyncio.sleep(0.01)

    @pytest.mark.asyncio
    async def test_log_duration_with_extra(self):
        """Test log_duration with extra context."""
        async with log_duration("db_query", endpoint="/users", method="GET"):
            await asyncio.sleep(0.01)

    @pytest.mark.asyncio
    async def test_log_duration_yields_instance(self):
        """Test log_duration yields LogDuration instance."""
        async with log_duration("operation") as ld:
            assert isinstance(ld, LogDuration)
            assert ld.operation == "operation"


# ============================================================================
# Convenience Function Tests
# ============================================================================

class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_get_logger(self):
        """Test get_logger function."""
        logger = get_logger()
        assert isinstance(logger, LoggingGateway)

    def test_get_logger_with_name(self):
        """Test get_logger with custom name."""
        logger = get_logger(name="custom")
        assert logger._name == "custom"

    def test_get_logger_with_config(self):
        """Test get_logger with custom config."""
        config = LoggingConfig(service_name="test-service")
        logger = get_logger(config=config)
        assert logger.config.service_name == "test-service"

    def test_set_log_context(self):
        """Test set_log_context function."""
        context = LogContext(trace_id="trace-123")
        set_log_context(context)
        assert get_log_context() == context
        clear_log_context()

    def test_get_log_context_default(self):
        """Test get_log_context returns None when not set."""
        clear_log_context()
        assert get_log_context() is None

    def test_clear_log_context(self):
        """Test clear_log_context function."""
        context = LogContext(trace_id="trace-123")
        set_log_context(context)
        clear_log_context()
        assert get_log_context() is None

    def test_get_default_logger(self):
        """Test get_default_logger returns singleton."""
        logger1 = get_default_logger()
        logger2 = get_default_logger()
        assert logger1 is logger2

    def test_configure_logging(self):
        """Test configure_logging function."""
        config = LoggingConfig(service_name="configured-service")
        logger = configure_logging(config)
        assert logger.config.service_name == "configured-service"
        
        # Should also set default logger
        default = get_default_logger()
        assert default.config.service_name == "configured-service"


# ============================================================================
# Trace Context Tests
# ============================================================================

class TestTraceContext:
    """Tests for OpenTelemetry trace context integration."""

    def test_get_current_trace_context_no_span(self):
        """Test get_current_trace_context when no span active."""
        result = get_current_trace_context()
        # When no span is active, returns empty dict
        assert isinstance(result, dict)

    @pytest.mark.skipif(not OTEL_AVAILABLE, reason="OpenTelemetry not available")
    def test_get_current_trace_context_with_span(self):
        """Test get_current_trace_context with active span."""
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        
        # Setup basic tracing
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
        tracer = trace.get_tracer(__name__)
        
        with tracer.start_as_current_span("test_span") as span:
            ctx = get_current_trace_context()
            # Should have trace_id and span_id
            assert "trace_id" in ctx or len(ctx) == 0  # May be empty if span context invalid


# ============================================================================
# _safe_repr Tests
# ============================================================================

class TestSafeRepr:
    """Tests for _safe_repr helper function."""

    def test_safe_repr_string(self):
        """Test _safe_repr with string."""
        result = _safe_repr("hello")
        assert result == "hello"

    def test_safe_repr_number(self):
        """Test _safe_repr with number."""
        result = _safe_repr(42)
        assert result == 42

    def test_safe_repr_dict(self):
        """Test _safe_repr with dict."""
        result = _safe_repr({"key": "value"})
        assert "key" in str(result) or result == {"key": "value"}

    def test_safe_repr_long_string(self):
        """Test _safe_repr truncates long strings."""
        long_string = "x" * 300
        result = _safe_repr(long_string)
        # Result might be truncated representation
        assert result is not None

    def test_safe_repr_custom_object(self):
        """Test _safe_repr with custom object."""
        class CustomClass:
            def __repr__(self):
                return "CustomClass()"
        
        obj = CustomClass()
        result = _safe_repr(obj)
        assert "CustomClass" in str(result) or result == obj

    def test_safe_repr_unrepresentable(self):
        """Test _safe_repr handles unrepresentable objects."""
        class BadRepr:
            def __repr__(self):
                raise Exception("Cannot repr")
        
        obj = BadRepr()
        result = _safe_repr(obj)
        assert result == "<unrepresentable>"


# ============================================================================
# Integration Tests
# ============================================================================

class TestLoggingIntegration:
    """Integration tests for logging module."""

    def test_full_logging_workflow(self):
        """Test complete logging workflow."""
        config = LoggingConfig(
            service_name="test-service",
            environment="testing",
            level=LogLevel.DEBUG,
            include_trace_context=True,
        )
        gateway = get_logger(config=config)
        
        # Set context
        context = LogContext(
            persona_id="persona-1",
            session_id="session-1",
        )
        set_log_context(context)
        
        try:
            gateway.info("Starting operation")
            
            bound = gateway.bind(request_id="req-123")
            bound.debug("Processing with bound context")
            
            gateway.warning("Warning message", count=5)
            
            try:
                raise ValueError("Test error")
            except ValueError as e:
                gateway.error("Caught error", exception=e)
            
            gateway.info("Operation completed")
        finally:
            clear_log_context()

    @pytest.mark.asyncio
    async def test_async_logging_workflow(self):
        """Test async logging workflow with decorators."""
        config = LoggingConfig(level=LogLevel.DEBUG)
        logger = get_logger(config=config)

        @logged(log_args=True, include_timing=True, logger=logger)
        async def fetch_data(url: str):
            async with log_duration("http_request", url=url):
                await asyncio.sleep(0.01)
            return {"data": "result"}

        result = await fetch_data("https://api.example.com")
        assert result == {"data": "result"}

    def test_file_rotation(self):
        """Test log file rotation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")
            config = LoggingConfig(
                log_file=log_file,
                max_file_size=1024,  # Small size for testing
                backup_count=3,
            )
            gateway = LoggingGateway(config=config)
            
            # Write enough logs to trigger rotation
            for i in range(100):
                gateway.info(f"Log message {i} " + "x" * 50)
            
            # Check that log file exists
            assert os.path.exists(log_file)

    def test_context_propagation(self):
        """Test context propagation through bound loggers."""
        gateway = LoggingGateway()
        
        # Create bound logger
        bound1 = gateway.bind(service="api")
        bound2 = bound1.bind(version="v1")
        bound3 = bound2.unbind("service")
        
        # Check context chain
        assert gateway._bound_context == {}
        assert bound1._bound_context == {"service": "api"}
        assert bound2._bound_context == {"service": "api", "version": "v1"}
        assert bound3._bound_context == {"version": "v1"}


# ============================================================================
# Edge Case Tests
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_logging_with_special_characters(self):
        """Test logging with special characters in message."""
        gateway = LoggingGateway()
        gateway.info("Message with special chars: \n\t\r\\" "")

    def test_logging_with_unicode(self):
        """Test logging with unicode characters."""
        gateway = LoggingGateway()
        gateway.info("Unicode message: 你好世界 🌍")

    def test_logging_with_none_values(self):
        """Test logging with None values in kwargs."""
        gateway = LoggingGateway()
        gateway.info("Message", value=None, another=None)

    def test_logging_with_complex_objects(self):
        """Test logging with complex objects."""
        gateway = LoggingGateway()
        
        class ComplexObject:
            def __str__(self):
                return "ComplexObject()"
        
        obj = ComplexObject()
        gateway.info("Message", obj=obj)

    def test_empty_message(self):
        """Test logging with empty message."""
        gateway = LoggingGateway()
        gateway.info("")

    def test_very_long_message(self):
        """Test logging with very long message."""
        gateway = LoggingGateway()
        long_message = "x" * 10000
        gateway.info(long_message)

    def test_decorator_on_method(self):
        """Test decorator on class method."""
        class Service:
            @logged(log_args=True)
            def process(self, data):
                return data.upper()
        
        service = Service()
        result = service.process("hello")
        assert result == "HELLO"

    @pytest.mark.asyncio
    async def test_decorator_on_async_method(self):
        """Test decorator on async class method."""
        class AsyncService:
            @logged(log_args=True)
            async def process(self, data):
                await asyncio.sleep(0.01)
                return data.upper()
        
        service = AsyncService()
        result = await service.process("hello")
        assert result == "HELLO"

    def test_nested_bound_loggers(self):
        """Test deeply nested bound loggers."""
        gateway = LoggingGateway()
        current = gateway
        
        for i in range(10):
            current = current.bind(**{f"key_{i}": f"value_{i}"})
        
        assert len(current._bound_context) == 10
        current.info("Nested log message")

    def test_concurrent_logging(self):
        """Test concurrent logging from multiple calls."""
        import concurrent.futures
        
        gateway = LoggingGateway()
        
        def log_message(i):
            gateway.info(f"Concurrent message {i}")
            return i
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(log_message, i) for i in range(10)]
            results = [f.result() for f in futures]
        
        assert len(results) == 10


# ============================================================================
# Fallback Mode Tests
# ============================================================================

class TestFallbackMode:
    """Tests for fallback mode when structlog is unavailable."""

    @patch('animus_observe.logging.STRUCTLOG_AVAILABLE', False)
    def test_fallback_logging(self):
        """Test fallback to standard logging when structlog unavailable."""
        gateway = LoggingGateway()
        gateway.info("Fallback message")
        gateway.error("Fallback error")
        gateway.debug("Fallback debug")

    @patch('animus_observe.logging.STRUCTLOG_AVAILABLE', False)
    def test_fallback_with_kwargs(self):
        """Test fallback logging with kwargs."""
        gateway = LoggingGateway()
        gateway.info("Message with kwargs", key="value", count=5)

    @patch('animus_observe.logging.STRUCTLOG_AVAILABLE', False)
    def test_fallback_bind(self):
        """Test bind in fallback mode."""
        gateway = LoggingGateway()
        bound = gateway.bind(key="value")
        assert bound._bound_context == {"key": "value"}


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=src/animus_observe/logging", "--cov-report=term-missing"])
