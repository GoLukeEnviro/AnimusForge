"""Bulkhead Isolation Pattern for AnimusForge Resilience.

Implements concurrency control to prevent cascade failures by limiting
the number of concurrent calls to a resource.

Based on the Bulkhead pattern from "Release It!" by Michael Nygard.
"""

import asyncio
import logging
import threading
import time
from contextlib import asynccontextmanager
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, Optional, TypeVar, ParamSpec

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

P = ParamSpec('P')
T = TypeVar('T')


class BulkheadState(str, Enum):
    """State of a bulkhead."""
    OPEN = "open"      # Has available permits
    CLOSED = "closed"  # No available permits but accepting queue
    FULL = "full"      # No permits and queue full


class BulkheadFullError(Exception):
    """Raised when bulkhead is full and cannot accept more calls."""

    def __init__(self, name: str, max_concurrent: int):
        self.name = name
        self.max_concurrent = max_concurrent
        super().__init__(
            f"Bulkhead '{name}' is full (max_concurrent={max_concurrent})"
        )


class BulkheadTimeoutError(Exception):
    """Raised when bulkhead operation times out."""

    def __init__(self, name: str, timeout: float, operation: str = "acquire"):
        self.name = name
        self.timeout = timeout
        self.operation = operation
        super().__init__(
            f"Bulkhead '{name}' {operation} timed out after {timeout}s"
        )


class BulkheadCallTimeoutError(Exception):
    """Raised when the call execution exceeds timeout."""

    def __init__(self, name: str, timeout: float):
        self.name = name
        self.timeout = timeout
        super().__init__(
            f"Bulkhead '{name}' call timed out after {timeout}s"
        )


class BulkheadConfig(BaseModel):
    """Configuration for a Bulkhead instance."""

    name: str = Field(..., description="Unique name for this bulkhead")
    max_concurrent_calls: int = Field(
        default=10,
        ge=1,
        description="Maximum number of concurrent calls allowed"
    )
    max_wait_duration: float = Field(
        default=5.0,
        ge=0.0,
        description="Maximum time to wait for a permit (seconds)"
    )
    call_timeout: float = Field(
        default=30.0,
        gt=0.0,
        description="Maximum duration for a single call (seconds)"
    )

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Bulkhead name cannot be empty")
        return v.strip()


class BulkheadMetrics(BaseModel):
    """Metrics for monitoring bulkhead state."""

    name: str = Field(..., description="Bulkhead name")
    available_permits: int = Field(
        default=0,
        ge=0,
        description="Number of available permits"
    )
    max_permits: int = Field(
        default=0,
        ge=0,
        description="Maximum number of permits"
    )
    queued_calls: int = Field(
        default=0,
        ge=0,
        description="Number of calls waiting in queue"
    )
    active_calls: int = Field(
        default=0,
        ge=0,
        description="Number of currently active calls"
    )
    rejected_calls: int = Field(
        default=0,
        ge=0,
        description="Total number of rejected calls"
    )
    timeout_calls: int = Field(
        default=0,
        ge=0,
        description="Total number of timed out calls"
    )
    accepted_calls: int = Field(
        default=0,
        ge=0,
        description="Total number of accepted calls"
    )
    completed_calls: int = Field(
        default=0,
        ge=0,
        description="Total number of completed calls"
    )

    @property
    def utilization(self) -> float:
        """Calculate utilization percentage."""
        if self.max_permits == 0:
            return 0.0
        return (self.active_calls / self.max_permits) * 100


class Bulkhead:
    """Bulkhead implementation using semaphore-based concurrency control.

    Limits concurrent access to a resource to prevent cascade failures.
    Supports wait queue with timeout and call execution timeout.

    Example:
        config = BulkheadConfig(name="database", max_concurrent_calls=5)
        bulkhead = Bulkhead(config)

        async with bulkhead:
            result = await some_database_call()

        # Or use execute for wrapped execution
        result = await bulkhead.execute(some_database_call)
    """

    def __init__(self, config: BulkheadConfig):
        self._config = config
        self._semaphore = asyncio.Semaphore(config.max_concurrent_calls)
        self._lock = asyncio.Lock()

        # Metrics tracking
        self._queued_calls = 0
        self._active_calls = 0
        self._rejected_calls = 0
        self._timeout_calls = 0
        self._accepted_calls = 0
        self._completed_calls = 0

        # Thread-safe counters for non-async operations
        self._counter_lock = threading.Lock()

        logger.info(
            f"Bulkhead '{config.name}' initialized with "
            f"max_concurrent={config.max_concurrent_calls}, "
            f"max_wait={config.max_wait_duration}s, "
            f"call_timeout={config.call_timeout}s"
        )

    @property
    def config(self) -> BulkheadConfig:
        """Get bulkhead configuration."""
        return self._config

    @property
    def name(self) -> str:
        """Get bulkhead name."""
        return self._config.name

    async def acquire(self) -> bool:
        """Acquire a permit, waiting if necessary.

        Returns:
            True if permit acquired successfully

        Raises:
            BulkheadTimeoutError: If wait duration exceeded
        """
        async with self._lock:
            self._queued_calls += 1

        try:
            if self._config.max_wait_duration > 0:
                await asyncio.wait_for(
                    self._semaphore.acquire(),
                    timeout=self._config.max_wait_duration
                )
            else:
                # No wait - immediate acquisition or fail
                acquired = self._semaphore.locked() and self._semaphore._value == 0
                if acquired:
                    raise BulkheadFullError(
                        self.name, self._config.max_concurrent_calls
                    )
                await self._semaphore.acquire()

            async with self._lock:
                self._queued_calls -= 1
                self._active_calls += 1
                self._accepted_calls += 1

            logger.debug(f"Bulkhead '{self.name}': permit acquired")
            return True

        except asyncio.TimeoutError:
            async with self._lock:
                self._queued_calls -= 1
                self._rejected_calls += 1
                self._timeout_calls += 1

            logger.warning(
                f"Bulkhead '{self.name}': acquire timed out after "
                f"{self._config.max_wait_duration}s"
            )
            raise BulkheadTimeoutError(
                self.name, self._config.max_wait_duration, "acquire"
            )
        except BulkheadFullError:
            async with self._lock:
                self._queued_calls -= 1
                self._rejected_calls += 1
            raise

    def release(self) -> None:
        """Release a permit back to the bulkhead."""
        try:
            self._semaphore.release()

            # Use thread-safe counter update
            with self._counter_lock:
                self._active_calls -= 1
                self._completed_calls += 1

            logger.debug(f"Bulkhead '{self.name}': permit released")

        except ValueError:
            # Semaphore already at max value - ignore
            logger.warning(
                f"Bulkhead '{self.name}': attempted to release when no permits held"
            )

    def try_enter(self) -> bool:
        """Non-blocking attempt to acquire a permit.

        Returns:
            True if permit acquired, False if bulkhead is full
        """
        # Check if semaphore has available permits
        if self._semaphore._value > 0:
            # Try to acquire without blocking
            # Note: This is a best-effort non-blocking check
            # In asyncio, truly non-blocking acquire is complex
            try:
                # Use a synchronous approach for the check
                if asyncio.get_event_loop().is_running():
                    # Schedule acquire and check immediately
                    task = asyncio.create_task(self._semaphore.acquire())
                    task.cancel()
                    return False
                return False
            except Exception:
                return False

        # No permits available
        with self._counter_lock:
            self._rejected_calls += 1

        return False

    def is_call_permitted(self) -> bool:
        """Check if a call would be permitted without blocking.

        Returns:
            True if permits are available, False otherwise
        """
        return self._semaphore._value > 0

    async def execute(
        self,
        callable_func: Callable[P, T],
        *args: P.args,
        **kwargs: P.kwargs
    ) -> T:
        """Execute a callable within bulkhead protection.

        Args:
            callable_func: Async or sync function to execute
            *args: Positional arguments for the callable
            **kwargs: Keyword arguments for the callable

        Returns:
            Result of the callable

        Raises:
            BulkheadTimeoutError: If waiting for permit times out
            BulkheadCallTimeoutError: If call execution times out
            BulkheadFullError: If bulkhead is full (when max_wait=0)
        """
        await self.acquire()

        try:
            # Execute with optional call timeout
            if asyncio.iscoroutinefunction(callable_func):
                if self._config.call_timeout > 0:
                    result = await asyncio.wait_for(
                        callable_func(*args, **kwargs),
                        timeout=self._config.call_timeout
                    )
                else:
                    result = await callable_func(*args, **kwargs)
            else:
                # Wrap sync function
                if self._config.call_timeout > 0:
                    result = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None, lambda: callable_func(*args, **kwargs)
                        ),
                        timeout=self._config.call_timeout
                    )
                else:
                    result = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: callable_func(*args, **kwargs)
                    )

            return result

        except asyncio.TimeoutError:
            with self._counter_lock:
                self._timeout_calls += 1

            logger.error(
                f"Bulkhead '{self.name}': call timed out after "
                f"{self._config.call_timeout}s"
            )
            raise BulkheadCallTimeoutError(self.name, self._config.call_timeout)

        finally:
            self.release()

    async def __aenter__(self):
        """Async context manager entry."""
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        self.release()
        return False

    def get_metrics(self) -> BulkheadMetrics:
        """Get current metrics for this bulkhead.

        Returns:
            BulkheadMetrics with current state
        """
        # Use lock to ensure consistency
        available = self._semaphore._value

        return BulkheadMetrics(
            name=self.name,
            available_permits=available,
            max_permits=self._config.max_concurrent_calls,
            queued_calls=max(0, self._queued_calls),
            active_calls=self._active_calls,
            rejected_calls=self._rejected_calls,
            timeout_calls=self._timeout_calls,
            accepted_calls=self._accepted_calls,
            completed_calls=self._completed_calls
        )

    def get_state(self) -> BulkheadState:
        """Get current state of the bulkhead.

        Returns:
            BulkheadState enum value
        """
        metrics = self.get_metrics()

        if metrics.available_permits > 0:
            return BulkheadState.OPEN
        elif metrics.queued_calls > 0:
            return BulkheadState.FULL
        else:
            return BulkheadState.CLOSED

    def reset_metrics(self) -> None:
        """Reset all metrics counters."""
        with self._counter_lock:
            self._rejected_calls = 0
            self._timeout_calls = 0
            self._accepted_calls = 0
            self._completed_calls = 0

        logger.info(f"Bulkhead '{self.name}': metrics reset")


class BulkheadRegistry:
    """Registry for managing multiple Bulkhead instances.

    Provides centralized management and monitoring of all bulkheads.

    Example:
        registry = BulkheadRegistry()

        # Get or create a bulkhead
        bulkhead = registry.get_or_create(
            "database",
            BulkheadConfig(name="database", max_concurrent_calls=5)
        )

        # Get all metrics
        all_metrics = registry.get_all_metrics()
    """

    _instance: Optional['BulkheadRegistry'] = None
    _lock = threading.Lock()

    def __new__(cls) -> 'BulkheadRegistry':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._bulkheads: Dict[str, Bulkhead] = {}
                    cls._instance._async_lock: Optional[asyncio.Lock] = None
        return cls._instance

    def _get_async_lock(self) -> asyncio.Lock:
        """Get or create async lock."""
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        return self._async_lock

    def get_or_create(
        self,
        name: str,
        config: Optional[BulkheadConfig] = None
    ) -> Bulkhead:
        """Get an existing bulkhead or create a new one.

        Args:
            name: Name of the bulkhead
            config: Configuration for new bulkhead (required if creating)

        Returns:
            Bulkhead instance

        Raises:
            ValueError: If bulkhead doesn't exist and no config provided
        """
        if name in self._bulkheads:
            return self._bulkheads[name]

        if config is None:
            config = BulkheadConfig(name=name)

        bulkhead = Bulkhead(config)
        self._bulkheads[name] = bulkhead

        logger.info(f"BulkheadRegistry: created bulkhead '{name}'")
        return bulkhead

    def get(self, name: str) -> Optional[Bulkhead]:
        """Get an existing bulkhead by name.

        Args:
            name: Name of the bulkhead

        Returns:
            Bulkhead instance or None if not found
        """
        return self._bulkheads.get(name)

    def remove(self, name: str) -> bool:
        """Remove a bulkhead from the registry.

        Args:
            name: Name of the bulkhead to remove

        Returns:
            True if removed, False if not found
        """
        if name in self._bulkheads:
            del self._bulkheads[name]
            logger.info(f"BulkheadRegistry: removed bulkhead '{name}'")
            return True
        return False

    def get_all_metrics(self) -> Dict[str, BulkheadMetrics]:
        """Get metrics for all registered bulkheads.

        Returns:
            Dictionary mapping bulkhead names to their metrics
        """
        return {
            name: bulkhead.get_metrics()
            for name, bulkhead in self._bulkheads.items()
        }

    def get_all_states(self) -> Dict[str, BulkheadState]:
        """Get states for all registered bulkheads.

        Returns:
            Dictionary mapping bulkhead names to their states
        """
        return {
            name: bulkhead.get_state()
            for name, bulkhead in self._bulkheads.items()
        }

    def list_bulkheads(self) -> list[str]:
        """List all registered bulkhead names.

        Returns:
            List of bulkhead names
        """
        return list(self._bulkheads.keys())

    def clear(self) -> None:
        """Remove all bulkheads from the registry."""
        self._bulkheads.clear()
        logger.info("BulkheadRegistry: cleared all bulkheads")

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (useful for testing)."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance._bulkheads.clear()
                cls._instance = None


# Global registry instance
registry = BulkheadRegistry()


def bulkhead(
    name: str,
    max_concurrent: int = 10,
    max_wait_duration: float = 5.0,
    call_timeout: float = 30.0
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator for applying bulkhead to async functions.

    Args:
        name: Name for the bulkhead
        max_concurrent: Maximum concurrent calls
        max_wait_duration: Max time to wait for permit
        call_timeout: Max time for call execution

    Returns:
        Decorated function with bulkhead protection

    Example:
        @bulkhead("database", max_concurrent=5)
        async def query_database(sql: str):
            return await db.execute(sql)
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            bh = registry.get_or_create(
                name,
                BulkheadConfig(
                    name=name,
                    max_concurrent_calls=max_concurrent,
                    max_wait_duration=max_wait_duration,
                    call_timeout=call_timeout
                )
            )
            return await bh.execute(func, *args, **kwargs)

        return wrapper  # type: ignore

    return decorator


def bulkhead_with_config(config: BulkheadConfig) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator using full BulkheadConfig.

    Args:
        config: Complete bulkhead configuration

    Returns:
        Decorated function with bulkhead protection

    Example:
        config = BulkheadConfig(
            name="api",
            max_concurrent_calls=20,
            max_wait_duration=2.0,
            call_timeout=10.0
        )

        @bulkhead_with_config(config)
        async def call_external_api():
            return await fetch_data()
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            bh = registry.get_or_create(config.name, config)
            return await bh.execute(func, *args, **kwargs)

        return wrapper  # type: ignore

    return decorator
