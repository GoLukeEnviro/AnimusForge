"""Structured Logging Module for AnimusForge.

Provides production-ready structured logging with structlog integration,
OpenTelemetry trace context injection, file rotation, and decorator support.
"""

from __future__ import annotations

import functools
import inspect
import json
import logging
import os
import sys
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from enum import Enum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union, ParamSpec

from pydantic import BaseModel, Field, field_validator, model_validator

# structlog imports with graceful fallback
try:
    import structlog
    from structlog.types import Processor, WrappedLogger
    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False
    structlog = None  # type: ignore[misc]
    Processor = Any  # type: ignore[misc]
    WrappedLogger = Any  # type: ignore[misc]

# OpenTelemetry imports for trace context
try:
    from opentelemetry import trace
    from opentelemetry.trace import format_span_id, format_trace_id, get_current_span
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    trace = None  # type: ignore[misc]
    get_current_span = None  # type: ignore[misc]


# Type variables for generic decorators
P = ParamSpec("P")
R = TypeVar("R")

# Context variable for storing current log context
_current_log_context: ContextVar[Optional["LogContext"]] = ContextVar("_current_log_context", default=None)


class LogLevel(str, Enum):
    """Log levels for structured logging."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

    def to_logging_level(self) -> int:
        """Convert to Python logging level."""
        mapping = {
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.INFO: logging.INFO,
            LogLevel.WARNING: logging.WARNING,
            LogLevel.ERROR: logging.ERROR,
            LogLevel.CRITICAL: logging.CRITICAL,
        }
        return mapping[self]


class LoggingConfig(BaseModel):
    """Configuration for structured logging.

    Attributes:
        service_name: Name of the service for log identification.
        environment: Deployment environment (development, staging, production).
        level: Minimum log level.
        json_format: Whether to use JSON format for logs.
        include_timestamp: Whether to include timestamp in logs.
        include_caller: Whether to include caller information.
        include_trace_context: Whether to include OpenTelemetry trace context.
        log_file: Optional path to log file.
        max_file_size: Maximum size of log file before rotation.
        backup_count: Number of backup files to keep.
        include_process_info: Whether to include process/thread info.
        colorize: Whether to colorize console output (development only).
        extra_processors: Additional structlog processors.
    """
    
    service_name: str = Field(default="animusforge", description="Service name for log identification")
    environment: str = Field(default="development", description="Deployment environment")
    level: LogLevel = Field(default=LogLevel.INFO, description="Minimum log level")
    json_format: bool = Field(default=True, description="Use JSON format for logs")
    include_timestamp: bool = Field(default=True, description="Include timestamp in logs")
    include_caller: bool = Field(default=True, description="Include caller information")
    include_trace_context: bool = Field(default=True, description="Include OpenTelemetry trace context")
    log_file: Optional[str] = Field(default=None, description="Optional path to log file")
    max_file_size: int = Field(default=10 * 1024 * 1024, description="Max log file size (bytes)")
    backup_count: int = Field(default=5, description="Number of backup files to keep")
    include_process_info: bool = Field(default=False, description="Include process/thread info")
    colorize: bool = Field(default=False, description="Colorize console output")
    extra_processors: List[str] = Field(default_factory=list, description="Additional processor names")

    @field_validator("service_name")
    @classmethod
    def validate_service_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("service_name cannot be empty")
        return v.strip()

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production", "testing"}
        if v not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return v

    @field_validator("max_file_size")
    @classmethod
    def validate_max_file_size(cls, v: int) -> int:
        if v < 1024:  # Minimum 1KB
            raise ValueError("max_file_size must be at least 1024 bytes")
        if v > 1024 * 1024 * 1024:  # Maximum 1GB
            raise ValueError("max_file_size cannot exceed 1GB")
        return v

    @field_validator("backup_count")
    @classmethod
    def validate_backup_count(cls, v: int) -> int:
        if v < 0:
            raise ValueError("backup_count cannot be negative")
        if v > 100:
            raise ValueError("backup_count cannot exceed 100")
        return v


class LogContext(BaseModel):
    """Context information for structured logging.

    Provides trace context and additional metadata for log entries.

    Attributes:
        trace_id: OpenTelemetry trace ID.
        span_id: OpenTelemetry span ID.
        persona_id: ID of the persona generating the log.
        user_id: ID of the user generating the log.
        session_id: Session ID for request correlation.
        extra: Additional context key-value pairs.
    """
    
    trace_id: Optional[str] = Field(default=None, description="OpenTelemetry trace ID")
    span_id: Optional[str] = Field(default=None, description="OpenTelemetry span ID")
    persona_id: Optional[str] = Field(default=None, description="Persona ID")
    user_id: Optional[str] = Field(default=None, description="User ID")
    session_id: Optional[str] = Field(default=None, description="Session ID")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Additional context")

    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary, excluding None values."""
        result = {}
        if self.trace_id:
            result["trace_id"] = self.trace_id
        if self.span_id:
            result["span_id"] = self.span_id
        if self.persona_id:
            result["persona_id"] = self.persona_id
        if self.user_id:
            result["user_id"] = self.user_id
        if self.session_id:
            result["session_id"] = self.session_id
        if self.extra:
            result.update(self.extra)
        return result

    def merge_with(self, **kwargs: Any) -> Dict[str, Any]:
        """Merge context with additional key-value pairs."""
        result = self.to_dict()
        result.update(kwargs)
        return result


class LoggingGateway:
    """Gateway for structured logging with structlog integration.

    Provides a unified interface for logging with automatic trace context
    injection, context binding, and support for multiple output formats.

    Attributes:
        config: Logging configuration.
        logger: Bound structlog logger instance.
    """
    
    def __init__(self, config: Optional[LoggingConfig] = None, name: Optional[str] = None):
        """Initialize the logging gateway.

        Args:
            config: Logging configuration. Uses defaults if not provided.
            name: Optional logger name for module identification.
        """
        self.config = config or LoggingConfig()
        self._name = name or self.config.service_name
        self._bound_context: Dict[str, Any] = {}
        
        if not STRUCTLOG_AVAILABLE:
            # Fallback to standard logging
            self._fallback_logger = logging.getLogger(self._name)
            self._fallback_logger.setLevel(self.config.level.to_logging_level())
            self._setup_fallback_handlers()
            self.logger = None  # type: ignore[misc]
        else:
            self._setup_structlog()
            self.logger = structlog.get_logger(self._name)
    
    def _setup_fallback_handlers(self) -> None:
        """Setup handlers for fallback logging (when structlog unavailable)."""
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(self.config.level.to_logging_level())
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        self._fallback_logger.addHandler(handler)
        
        if self.config.log_file:
            self._setup_file_handler(self._fallback_logger)
    
    def _setup_file_handler(self, logger: logging.Logger) -> None:
        """Setup rotating file handler."""
        log_path = Path(self.config.log_file)  # type: ignore[arg-type]
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = RotatingFileHandler(
            self.config.log_file,
            maxBytes=self.config.max_file_size,
            backupCount=self.config.backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(self.config.level.to_logging_level())
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    def _setup_structlog(self) -> None:
        """Configure structlog with processors."""
        processors: List[Any] = []
        
        # Add timestamp processor
        if self.config.include_timestamp:
            processors.append(structlog.processors.TimeStamper(fmt="iso"))
        
        # Add log level processor
        processors.append(structlog.stdlib.add_log_level)
        
        # Add caller info
        if self.config.include_caller:
            processors.append(structlog.processors.CallsiteParameterAdder(
                parameters={
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.LINENO,
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                }
            ))
        
        # Add process info
        if self.config.include_process_info:
            processors.append(structlog.processors.ProcessInfoAdder())
        
        # Add trace context processor
        if self.config.include_trace_context:
            processors.append(self._add_trace_context)
        
        # Add bound context processor
        processors.append(self._add_bound_context)
        
        # Final renderer
        if self.config.json_format:
            processors.append(structlog.processors.JSONRenderer())
        elif self.config.colorize and self.config.environment == "development":
            processors.append(structlog.dev.ConsoleRenderer(colors=True))
        else:
            processors.append(structlog.dev.ConsoleRenderer(colors=False))
        
        # Configure structlog
        structlog.configure(
            processors=processors,
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
        
        # Setup standard logging for file output
        if self.config.log_file:
            root_logger = logging.getLogger()
            root_logger.setLevel(self.config.level.to_logging_level())
            self._setup_file_handler(root_logger)
    
    def _add_trace_context(self, logger: WrappedLogger, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Processor to add OpenTelemetry trace context."""
        if not OTEL_AVAILABLE or not self.config.include_trace_context:
            return event_dict
        
        try:
            span = get_current_span()  # type: ignore[misc]
            if span and span.get_span_context():
                ctx = span.get_span_context()
                if ctx.trace_id != 0:
                    event_dict["trace_id"] = format_trace_id(ctx.trace_id)
                if ctx.span_id != 0:
                    event_dict["span_id"] = format_span_id(ctx.span_id)
        except Exception:
            pass  # Silently ignore trace context extraction errors
        
        return event_dict
    
    def _add_bound_context(self, logger: WrappedLogger, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Processor to add bound context."""
        # Add bound context
        if self._bound_context:
            event_dict.update(self._bound_context)
        
        # Add context from context variable
        ctx = _current_log_context.get()
        if ctx:
            event_dict.update(ctx.to_dict())
        
        return event_dict

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log a debug message."""
        self._log(LogLevel.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log an info message."""
        self._log(LogLevel.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log a warning message."""
        self._log(LogLevel.WARNING, message, **kwargs)

    def error(self, message: str, exception: Optional[Exception] = None, **kwargs: Any) -> None:
        """Log an error message with optional exception."""
        if exception:
            kwargs["exception_type"] = type(exception).__name__
            kwargs["exception_message"] = str(exception)
        self._log(LogLevel.ERROR, message, **kwargs)

    def critical(self, message: str, exception: Optional[Exception] = None, **kwargs: Any) -> None:
        """Log a critical message with optional exception."""
        if exception:
            kwargs["exception_type"] = type(exception).__name__
            kwargs["exception_message"] = str(exception)
        self._log(LogLevel.CRITICAL, message, **kwargs)

    def _log(self, level: LogLevel, message: str, **kwargs: Any) -> None:
        """Internal logging method."""
        if not STRUCTLOG_AVAILABLE:
            # Fallback to standard logging
            log_method = getattr(self._fallback_logger, level.value)
            if kwargs:
                message = f"{message} | {json.dumps(kwargs)}"
            log_method(message)
            return
        
        log_method = getattr(self.logger, level.value)
        log_method(message, **kwargs)

    def bind(self, **kwargs: Any) -> "LoggingGateway":
        """Create a new gateway with bound context.

        Args:
            **kwargs: Key-value pairs to bind to the context.

        Returns:
            New LoggingGateway instance with bound context.
        """
        new_gateway = LoggingGateway.__new__(LoggingGateway)
        new_gateway.config = self.config
        new_gateway._name = self._name
        new_gateway._bound_context = {**self._bound_context, **kwargs}
        new_gateway.logger = self.logger.bind(**kwargs) if self.logger else None
        return new_gateway

    def unbind(self, *keys: str) -> "LoggingGateway":
        """Create a new gateway with specified keys removed from context.

        Args:
            *keys: Keys to remove from bound context.

        Returns:
            New LoggingGateway instance with keys removed.
        """
        new_bound = {k: v for k, v in self._bound_context.items() if k not in keys}
        new_gateway = LoggingGateway.__new__(LoggingGateway)
        new_gateway.config = self.config
        new_gateway._name = self._name
        new_gateway._bound_context = new_bound
        if self.logger:
            try:
                new_gateway.logger = self.logger.unbind(*keys)
            except KeyError:
                # structlog raises KeyError for non-existent keys, just use current logger
                new_gateway.logger = self.logger
        else:
            new_gateway.logger = None
        return new_gateway

    def with_context(self, context: LogContext) -> "LoggingGateway":
        """Create a new gateway with LogContext.

        Args:
            context: LogContext instance with trace and session info.

        Returns:
            New LoggingGateway with context bound.
        """
        return self.bind(**context.to_dict())

    def get_logger(self) -> Any:
        """Get the underlying structlog logger.

        Returns:
            structlog.BoundLogger or standard logging.Logger.
        """
        if STRUCTLOG_AVAILABLE and self.logger:
            return self.logger
        return self._fallback_logger

    @contextmanager
    def span_context(self, **kwargs: Any) -> Any:
        """Context manager to temporarily bind context.

        Args:
            **kwargs: Key-value pairs to bind within context.

        Yields:
            Self with bound context.
        """
        bound = self.bind(**kwargs)
        try:
            yield bound
        finally:
            pass  # Context automatically cleaned up


def get_logger(name: Optional[str] = None, config: Optional[LoggingConfig] = None) -> LoggingGateway:
    """Get a configured LoggingGateway instance.

    Args:
        name: Optional logger name for module identification.
        config: Optional logging configuration.

    Returns:
        Configured LoggingGateway instance.
    """
    return LoggingGateway(config=config, name=name)


def set_log_context(context: LogContext) -> None:
    """Set the current log context for all loggers.

    Args:
        context: LogContext to set as current.
    """
    _current_log_context.set(context)


def get_log_context() -> Optional[LogContext]:
    """Get the current log context.

    Returns:
        Current LogContext or None.
    """
    return _current_log_context.get()


def clear_log_context() -> None:
    """Clear the current log context."""
    _current_log_context.set(None)


def logged(
    log_args: bool = True,
    log_result: bool = False,
    level: LogLevel = LogLevel.DEBUG,
    message: Optional[str] = None,
    include_timing: bool = True,
    logger: Optional[LoggingGateway] = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to automatically log function calls.

    Args:
        log_args: Whether to log function arguments.
        log_result: Whether to log function result.
        level: Log level for messages.
        message: Custom log message template.
        include_timing: Whether to include execution timing.
        logger: Optional custom logger to use.

    Returns:
        Decorated function with automatic logging.

    Example:
        @logged(log_args=True, log_result=False, level=LogLevel.DEBUG)
        async def my_function(arg1, arg2):
            pass
    """
    _logger = logger or get_logger()

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        func_name = func.__qualname__
        is_async = inspect.iscoroutinefunction(func)

        if is_async:
            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                log_data = {"function": func_name}
                
                if log_args:
                    sig = inspect.signature(func)
                    bound = sig.bind(*args, **kwargs)
                    bound.apply_defaults()
                    log_data["args"] = {k: _safe_repr(v) for k, v in bound.arguments.items()}
                
                msg = message or f"Calling {func_name}"
                _logger._log(level, msg, **log_data)
                
                start_time = datetime.now(timezone.utc)
                try:
                    result = await func(*args, **kwargs)  # type: ignore[misc]
                    
                    if include_timing:
                        duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                        log_data["duration_ms"] = round(duration_ms, 2)
                    
                    if log_result:
                        log_data["result"] = _safe_repr(result)
                    
                    _logger._log(level, f"Completed {func_name}", **log_data)
                    return result
                except Exception as e:
                    if include_timing:
                        duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                        log_data["duration_ms"] = round(duration_ms, 2)
                    
                    _logger.error(f"Failed {func_name}", exception=e, **log_data)
                    raise

            return async_wrapper  # type: ignore[return-value]
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                log_data = {"function": func_name}
                
                if log_args:
                    sig = inspect.signature(func)
                    bound = sig.bind(*args, **kwargs)
                    bound.apply_defaults()
                    log_data["args"] = {k: _safe_repr(v) for k, v in bound.arguments.items()}
                
                msg = message or f"Calling {func_name}"
                _logger._log(level, msg, **log_data)
                
                start_time = datetime.now(timezone.utc)
                try:
                    result = func(*args, **kwargs)
                    
                    if include_timing:
                        duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                        log_data["duration_ms"] = round(duration_ms, 2)
                    
                    if log_result:
                        log_data["result"] = _safe_repr(result)
                    
                    _logger._log(level, f"Completed {func_name}", **log_data)
                    return result
                except Exception as e:
                    if include_timing:
                        duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                        log_data["duration_ms"] = round(duration_ms, 2)
                    
                    _logger.error(f"Failed {func_name}", exception=e, **log_data)
                    raise

            return sync_wrapper

    return decorator


def _safe_repr(value: Any, max_length: int = 200) -> Any:
    """Create a safe string representation of a value.

    Args:
        value: Value to represent.
        max_length: Maximum length of string representation.

    Returns:
        Safe representation of value.
    """
    try:
        repr_str = repr(value)
        if len(repr_str) > max_length:
            return repr_str[:max_length] + "..."
        return value
    except Exception:
        return "<unrepresentable>"


class LogDuration:
    """Context manager for logging operation duration.

    Logs the duration of an operation automatically.

    Example:
        async with LogDuration("database_query", level=LogLevel.INFO):
            await db.execute(query)
    """

    def __init__(
        self,
        operation: str,
        level: LogLevel = LogLevel.INFO,
        logger: Optional[LoggingGateway] = None,
        **extra: Any,
    ):
        """Initialize duration logger.

        Args:
            operation: Name of the operation being timed.
            level: Log level for the duration message.
            logger: Optional custom logger to use.
            **extra: Additional context to include in log.
        """
        self.operation = operation
        self.level = level
        self._logger = logger or get_logger()
        self._extra = extra
        self._start_time: Optional[datetime] = None
        self._end_time: Optional[datetime] = None
        self._exception: Optional[Exception] = None

    def __enter__(self) -> "LogDuration":
        """Enter context and start timing."""
        self._start_time = datetime.now(timezone.utc)
        self._logger._log(
            LogLevel.DEBUG,
            f"Starting {self.operation}",
            **self._extra
        )
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context and log duration."""
        self._end_time = datetime.now(timezone.utc)
        duration_ms = (self._end_time - self._start_time).total_seconds() * 1000  # type: ignore[operator]
        
        log_data = {
            "operation": self.operation,
            "duration_ms": round(duration_ms, 2),
            **self._extra
        }
        
        if exc_type is not None:
            self._exception = exc_val  # type: ignore[assignment]
            log_data["success"] = False
            self._logger.error(
                f"Failed {self.operation}",
                exception=self._exception,
                **log_data
            )
        else:
            log_data["success"] = True
            self._logger._log(
                self.level,
                f"Completed {self.operation}",
                **log_data
            )

    async def __aenter__(self) -> "LogDuration":
        """Async enter context and start timing."""
        return self.__enter__()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async exit context and log duration."""
        self.__exit__(exc_type, exc_val, exc_tb)


@asynccontextmanager
async def log_duration(
    operation: str,
    level: LogLevel = LogLevel.INFO,
    logger: Optional[LoggingGateway] = None,
    **extra: Any,
) -> AsyncGenerator[LogDuration, None]:
    """Async context manager for logging operation duration.

    Args:
        operation: Name of the operation being timed.
        level: Log level for the duration message.
        logger: Optional custom logger to use.
        **extra: Additional context to include in log.

    Yields:
        LogDuration instance.

    Example:
        async with log_duration("api_call", level=LogLevel.INFO) as ld:
            await make_api_request()
            # ld._start_time available if needed
    """
    duration_logger = LogDuration(operation, level, logger, **extra)
    async with duration_logger:
        yield duration_logger


# Convenience function for getting trace context from current span
def get_current_trace_context() -> Dict[str, str]:
    """Get trace context from current OpenTelemetry span.

    Returns:
        Dictionary with trace_id and span_id if available.
    """
    if not OTEL_AVAILABLE:
        return {}
    
    try:
        span = get_current_span()  # type: ignore[misc]
        if span and span.get_span_context():
            ctx = span.get_span_context()
            result = {}
            if ctx.trace_id != 0:
                result["trace_id"] = format_trace_id(ctx.trace_id)
            if ctx.span_id != 0:
                result["span_id"] = format_span_id(ctx.span_id)
            return result
    except Exception:
        pass
    
    return {}


# Module-level default logger
_default_logger: Optional[LoggingGateway] = None


def get_default_logger() -> LoggingGateway:
    """Get or create the default module logger.

    Returns:
        Default LoggingGateway instance.
    """
    global _default_logger
    if _default_logger is None:
        _default_logger = get_logger()
    return _default_logger


def configure_logging(config: LoggingConfig) -> LoggingGateway:
    """Configure and return the default logger.

    Args:
        config: Logging configuration.

    Returns:
        Configured LoggingGateway instance.
    """
    global _default_logger
    _default_logger = get_logger(config=config)
    return _default_logger
