"""Retry with Backoff - Comprehensive retry logic with multiple backoff strategies.

This module provides production-ready retry functionality with:
- Multiple backoff strategies (fixed, linear, exponential, exponential with jitter)
- Configurable retryable exceptions and status codes
- Metrics collection for monitoring
- Decorator support for easy integration
- Async support for modern Python applications
"""

from __future__ import annotations

import asyncio
import functools
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar, Union

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class BackoffStrategy(str, Enum):
    """Backoff strategies for retry delays."""
    
    FIXED = "fixed"
    """Fixed delay between retries."""
    
    LINEAR = "linear"
    """Linear increase: delay = base_delay * attempt"""
    
    EXPONENTIAL = "exponential"
    """Exponential increase: delay = base_delay * (2 ** attempt)"""
    
    EXPONENTIAL_JITTER = "exponential_jitter"
    """Exponential with jitter: delay = base_delay * (2 ** attempt) * (1 + jitter_factor * random())"""


class RetryConfig(BaseModel):
    """Configuration for retry behavior.
    
    Attributes:
        max_attempts: Maximum number of retry attempts (including initial call).
        base_delay: Base delay in seconds for backoff calculations.
        max_delay: Maximum delay in seconds between retries.
        backoff_strategy: Strategy for calculating delays between retries.
        jitter_factor: Factor for random jitter (0.0 to 1.0).
        retryable_exceptions: List of exception types that trigger retry.
        retryable_status_codes: HTTP status codes that trigger retry.
        on_retry_callback: Optional callback called before each retry.
    """
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    max_attempts: int = Field(default=3, ge=1, le=100)
    base_delay: float = Field(default=1.0, ge=0.0, le=3600.0)
    max_delay: float = Field(default=60.0, ge=0.0, le=86400.0)
    backoff_strategy: BackoffStrategy = Field(default=BackoffStrategy.EXPONENTIAL_JITTER)
    jitter_factor: float = Field(default=0.5, ge=0.0, le=1.0)
    retryable_exceptions: List[Type[Exception]] = Field(default_factory=lambda: [Exception])
    retryable_status_codes: List[int] = Field(
        default_factory=lambda: [429, 500, 502, 503, 504]
    )
    on_retry_callback: Optional[Callable[[int, Exception, float], None]] = Field(default=None)


class RetryResult(BaseModel):
    """Result of a retry operation.
    
    Attributes:
        success: Whether the operation ultimately succeeded.
        attempts: Number of attempts made (including initial call).
        total_delay: Total time spent waiting between retries in seconds.
        last_exception: The last exception encountered, if any.
        result: The result of the operation if successful.
    """
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    success: bool
    attempts: int
    total_delay: float
    last_exception: Optional[Exception] = None
    result: Any = None


class RetryMetrics(BaseModel):
    """Metrics collected from retry operations.
    
    Attributes:
        total_calls: Total number of operations executed.
        successful_first_try: Operations that succeeded on first attempt.
        successful_after_retry: Operations that succeeded after at least one retry.
        failed_after_retries: Operations that failed after exhausting retries.
        total_retries: Total number of retry attempts made.
        average_attempts: Average number of attempts per operation.
    """
    
    model_config = ConfigDict(frozen=False)
    
    total_calls: int = 0
    successful_first_try: int = 0
    successful_after_retry: int = 0
    failed_after_retries: int = 0
    total_retries: int = 0
    
    @property
    def average_attempts(self) -> float:
        """Calculate average number of attempts per operation."""
        if self.total_calls == 0:
            return 0.0
        return (self.total_calls + self.total_retries) / self.total_calls
    
    @property
    def success_rate(self) -> float:
        """Calculate overall success rate."""
        if self.total_calls == 0:
            return 0.0
        return (self.successful_first_try + self.successful_after_retry) / self.total_calls


class Retrier:
    """Production-ready retry executor with configurable backoff strategies.
    
    Provides comprehensive retry logic with metrics collection and
    support for multiple backoff strategies.
    
    Example:
        >>> config = RetryConfig(
        ...     max_attempts=3,
        ...     backoff_strategy=BackoffStrategy.EXPONENTIAL_JITTER
        ... )
        >>> retrier = Retrier(config)
        >>> result = await retrier.execute(some_async_function, arg1, arg2)
    """
    
    def __init__(self, config: Optional[RetryConfig] = None):
        """Initialize the Retrier with configuration.
        
        Args:
            config: Retry configuration. Uses defaults if not provided.
        """
        self.config = config or RetryConfig()
        self._metrics = RetryMetrics()
    
    @property
    def metrics(self) -> RetryMetrics:
        """Get current retry metrics."""
        return self._metrics
    
    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for a given attempt number.
        
        Args:
            attempt: The attempt number (0-indexed).
            
        Returns:
            Delay in seconds before the next retry.
        """
        base = self.config.base_delay
        
        if self.config.backoff_strategy == BackoffStrategy.FIXED:
            delay = base
        
        elif self.config.backoff_strategy == BackoffStrategy.LINEAR:
            delay = base * (attempt + 1)
        
        elif self.config.backoff_strategy == BackoffStrategy.EXPONENTIAL:
            delay = base * (2 ** attempt)
        
        elif self.config.backoff_strategy == BackoffStrategy.EXPONENTIAL_JITTER:
            exponential_delay = base * (2 ** attempt)
            jitter_mult = 1 + self.config.jitter_factor * random.random()
            delay = base * (2 ** attempt) * jitter_mult
        
        else:
            delay = base
        
        return min(delay, self.config.max_delay)
    
    def is_retryable(self, exception: Exception) -> bool:
        """Check if an exception should trigger a retry.
        
        Args:
            exception: The exception to check.
            
        Returns:
            True if the exception is retryable, False otherwise.
        """
        # Check if exception type is in retryable_exceptions
        for retryable_type in self.config.retryable_exceptions:
            if isinstance(exception, retryable_type):
                return True
        
        # Check for status code attribute
        status_code = getattr(exception, 'status_code', None)
        if status_code is not None and status_code in self.config.retryable_status_codes:
            return True
        
        # Check for response attribute with status code
        response = getattr(exception, 'response', None)
        if response is not None:
            resp_status = getattr(response, 'status_code', None)
            if resp_status is not None and resp_status in self.config.retryable_status_codes:
                return True
        
        return False
    
    async def execute(
        self,
        func: Callable[..., T],
        *args,
        **kwargs
    ) -> RetryResult:
        """Execute a function with retry logic.
        
        Args:
            func: The async or sync function to execute.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.
            
        Returns:
            RetryResult containing success status, attempts, and result.
        """
        attempts = 0
        total_delay = 0.0
        last_exception: Optional[Exception] = None
        
        while attempts < self.config.max_attempts:
            attempts += 1
            
            try:
                # Handle both async and sync functions
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                # Update metrics
                self._metrics.total_calls += 1
                if attempts == 1:
                    self._metrics.successful_first_try += 1
                else:
                    self._metrics.successful_after_retry += 1
                    self._metrics.total_retries += attempts - 1
                
                return RetryResult(
                    success=True,
                    attempts=attempts,
                    total_delay=total_delay,
                    last_exception=None,
                    result=result
                )
            
            except Exception as e:
                last_exception = e
                
                # Check if we should retry
                if attempts < self.config.max_attempts and self.is_retryable(e):
                    delay = self.calculate_delay(attempts - 1)
                    total_delay += delay
                    
                    # Call retry callback if provided
                    if self.config.on_retry_callback:
                        try:
                            self.config.on_retry_callback(attempts, e, delay)
                        except Exception:
                            pass  # Don't let callback errors affect retry logic
                    
                    await asyncio.sleep(delay)
                else:
                    # Non-retryable exception or max attempts reached
                    break
        
        # All retries exhausted
        self._metrics.total_calls += 1
        self._metrics.failed_after_retries += 1
        if attempts > 1:
            self._metrics.total_retries += attempts - 1
        
        return RetryResult(
            success=False,
            attempts=attempts,
            total_delay=total_delay,
            last_exception=last_exception,
            result=None
        )
    
    def get_metrics(self) -> RetryMetrics:
        """Get current retry metrics.
        
        Returns:
            Copy of current metrics.
        """
        return RetryMetrics(
            total_calls=self._metrics.total_calls,
            successful_first_try=self._metrics.successful_first_try,
            successful_after_retry=self._metrics.successful_after_retry,
            failed_after_retries=self._metrics.failed_after_retries,
            total_retries=self._metrics.total_retries
        )
    
    def reset_metrics(self) -> None:
        """Reset all metrics to initial state."""
        self._metrics = RetryMetrics()


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL_JITTER,
    jitter_factor: float = 0.5,
    retryable_exceptions: Optional[List[Type[Exception]]] = None,
    retryable_status_codes: Optional[List[int]] = None,
    on_retry_callback: Optional[Callable[[int, Exception, float], None]] = None,
) -> Callable:
    """Decorator for automatic retry with configurable backoff.
    
    Can be applied to async functions for automatic retry behavior.
    
    Args:
        max_attempts: Maximum number of retry attempts.
        base_delay: Base delay in seconds.
        max_delay: Maximum delay in seconds.
        backoff_strategy: Strategy for calculating delays.
        jitter_factor: Factor for random jitter.
        retryable_exceptions: Exceptions that trigger retry.
        retryable_status_codes: HTTP status codes that trigger retry.
        on_retry_callback: Callback before each retry.
        
    Returns:
        Decorated function with retry logic.
    
    Example:
        >>> @retry(max_attempts=3, backoff=BackoffStrategy.EXPONENTIAL_JITTER)
        >>> async def my_api_call():
        ...     return await some_http_request()
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        config = RetryConfig(
            max_attempts=max_attempts,
            base_delay=base_delay,
            max_delay=max_delay,
            backoff_strategy=backoff_strategy,
            jitter_factor=jitter_factor,
            retryable_exceptions=retryable_exceptions or [Exception],
            retryable_status_codes=retryable_status_codes or [429, 500, 502, 503, 504],
            on_retry_callback=on_retry_callback
        )
        retrier = Retrier(config)
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            result = await retrier.execute(func, *args, **kwargs)
            if result.success:
                return result.result
            raise result.last_exception or Exception("Retry failed")
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            # Run async wrapper in event loop
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(async_wrapper(*args, **kwargs))
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


class RetryRegistry:
    """Registry for managing multiple named Retrier instances.
    
    Provides centralized management and monitoring of retry operations
    across an application.
    
    Example:
        >>> registry = RetryRegistry()
        >>> retrier = registry.get_or_create('api_calls', config)
        >>> metrics = registry.get_all_metrics()
    """
    
    def __init__(self):
        """Initialize the registry."""
        self._retriers: Dict[str, Retrier] = {}
    
    def get_or_create(
        self,
        name: str,
        config: Optional[RetryConfig] = None
    ) -> Retrier:
        """Get an existing Retrier or create a new one.
        
        Args:
            name: Unique name for the retrier.
            config: Configuration for new retrier. Ignored if retrier exists.
            
        Returns:
            Retrier instance.
        """
        if name not in self._retriers:
            self._retriers[name] = Retrier(config)
        return self._retriers[name]
    
    def get_metrics(self, name: str) -> Optional[RetryMetrics]:
        """Get metrics for a specific retrier.
        
        Args:
            name: Name of the retrier.
            
        Returns:
            Metrics if retrier exists, None otherwise.
        """
        retrier = self._retriers.get(name)
        return retrier.get_metrics() if retrier else None
    
    def get_all_metrics(self) -> Dict[str, RetryMetrics]:
        """Get metrics for all registered retriers.
        
        Returns:
            Dictionary mapping names to metrics.
        """
        return {name: retrier.get_metrics() for name, retrier in self._retriers.items()}
    
    def reset_all_metrics(self) -> None:
        """Reset metrics for all retriers."""
        for retrier in self._retriers.values():
            retrier.reset_metrics()
    
    def remove(self, name: str) -> bool:
        """Remove a retrier from the registry.
        
        Args:
            name: Name of the retrier to remove.
            
        Returns:
            True if retrier was removed, False if not found.
        """
        if name in self._retriers:
            del self._retriers[name]
            return True
        return False
    
    def clear(self) -> None:
        """Remove all retriers from the registry."""
        self._retriers.clear()
    
    @property
    def names(self) -> List[str]:
        """Get list of all registered retrier names."""
        return list(self._retriers.keys())


# Global registry for convenience
_global_registry: Optional[RetryRegistry] = None


def get_global_registry() -> RetryRegistry:
    """Get the global retry registry instance.
    
    Creates the registry on first call.
    
    Returns:
        Global RetryRegistry instance.
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = RetryRegistry()
    return _global_registry


def reset_global_registry() -> None:
    """Reset the global registry (mainly for testing)."""
    global _global_registry
    _global_registry = None
