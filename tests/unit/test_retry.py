"""Comprehensive unit tests for Retry with Backoff module.

Tests cover:
- BackoffStrategy enum
- RetryConfig validation
- RetryResult and RetryMetrics models
- Retrier class with all backoff strategies
- retry decorator
- RetryRegistry
- Edge cases and error handling
"""

import asyncio
import time
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from animus_resilience.retry import (
    BackoffStrategy,
    RetryConfig,
    RetryResult,
    RetryMetrics,
    Retrier,
    retry,
    RetryRegistry,
    get_global_registry,
    reset_global_registry,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def basic_config():
    """Basic retry configuration."""
    return RetryConfig(
        max_attempts=3,
        base_delay=0.1,
        max_delay=1.0,
        backoff_strategy=BackoffStrategy.FIXED
    )


@pytest.fixture
def exponential_config():
    """Exponential backoff configuration."""
    return RetryConfig(
        max_attempts=3,
        base_delay=0.1,
        max_delay=1.0,
        backoff_strategy=BackoffStrategy.EXPONENTIAL
    )


@pytest.fixture
def jitter_config():
    """Exponential with jitter configuration."""
    return RetryConfig(
        max_attempts=3,
        base_delay=0.1,
        max_delay=1.0,
        backoff_strategy=BackoffStrategy.EXPONENTIAL_JITTER,
        jitter_factor=0.5
    )


@pytest.fixture
def retrier(basic_config):
    """Retrier instance with basic config."""
    return Retrier(basic_config)


@pytest.fixture
def registry():
    """Fresh registry for testing."""
    return RetryRegistry()


# ============================================================================
# BackoffStrategy Tests
# ============================================================================

class TestBackoffStrategy:
    """Tests for BackoffStrategy enum."""
    
    def test_backoff_strategy_values(self):
        """Test that all strategies have correct string values."""
        assert BackoffStrategy.FIXED.value == "fixed"
        assert BackoffStrategy.LINEAR.value == "linear"
        assert BackoffStrategy.EXPONENTIAL.value == "exponential"
        assert BackoffStrategy.EXPONENTIAL_JITTER.value == "exponential_jitter"
    
    def test_backoff_strategy_count(self):
        """Test that all four strategies exist."""
        strategies = list(BackoffStrategy)
        assert len(strategies) == 4
    
    def test_backoff_strategy_is_string_enum(self):
        """Test that BackoffStrategy is a string enum."""
        assert isinstance(BackoffStrategy.FIXED, str)
        assert BackoffStrategy.FIXED == "fixed"


# ============================================================================
# RetryConfig Tests
# ============================================================================

class TestRetryConfig:
    """Tests for RetryConfig model."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.backoff_strategy == BackoffStrategy.EXPONENTIAL_JITTER
        assert config.jitter_factor == 0.5
        assert Exception in config.retryable_exceptions
        assert 429 in config.retryable_status_codes
    
    def test_custom_values(self):
        """Test custom configuration values."""
        config = RetryConfig(
            max_attempts=5,
            base_delay=2.0,
            max_delay=120.0,
            backoff_strategy=BackoffStrategy.LINEAR,
            jitter_factor=0.3
        )
        assert config.max_attempts == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 120.0
        assert config.backoff_strategy == BackoffStrategy.LINEAR
        assert config.jitter_factor == 0.3
    
    def test_max_attempts_validation(self):
        """Test max_attempts validation."""
        # Valid range
        config = RetryConfig(max_attempts=1)
        assert config.max_attempts == 1
        
        config = RetryConfig(max_attempts=100)
        assert config.max_attempts == 100
        
        # Invalid - below minimum
        with pytest.raises(Exception):  # ValidationError
            RetryConfig(max_attempts=0)
        
        # Invalid - above maximum
        with pytest.raises(Exception):
            RetryConfig(max_attempts=101)
    
    def test_base_delay_validation(self):
        """Test base_delay validation."""
        config = RetryConfig(base_delay=0.0)
        assert config.base_delay == 0.0
        
        config = RetryConfig(base_delay=3600.0)
        assert config.base_delay == 3600.0
    
    def test_jitter_factor_validation(self):
        """Test jitter_factor validation (0.0 to 1.0)."""
        config = RetryConfig(jitter_factor=0.0)
        assert config.jitter_factor == 0.0
        
        config = RetryConfig(jitter_factor=1.0)
        assert config.jitter_factor == 1.0
        
        # Invalid - out of range
        with pytest.raises(Exception):
            RetryConfig(jitter_factor=-0.1)
        
        with pytest.raises(Exception):
            RetryConfig(jitter_factor=1.1)
    
    def test_retryable_exceptions_default(self):
        """Test default retryable exceptions."""
        config = RetryConfig()
        assert Exception in config.retryable_exceptions
    
    def test_custom_retryable_exceptions(self):
        """Test custom retryable exceptions."""
        config = RetryConfig(
            retryable_exceptions=[ValueError, TypeError, RuntimeError]
        )
        assert ValueError in config.retryable_exceptions
        assert TypeError in config.retryable_exceptions
        assert RuntimeError in config.retryable_exceptions
    
    def test_retryable_status_codes_default(self):
        """Test default retryable status codes."""
        config = RetryConfig()
        assert 429 in config.retryable_status_codes
        assert 500 in config.retryable_status_codes
        assert 502 in config.retryable_status_codes
        assert 503 in config.retryable_status_codes
        assert 504 in config.retryable_status_codes
    
    def test_custom_retryable_status_codes(self):
        """Test custom retryable status codes."""
        config = RetryConfig(retryable_status_codes=[408, 429])
        assert 408 in config.retryable_status_codes
        assert 429 in config.retryable_status_codes
    
    def test_on_retry_callback(self):
        """Test on_retry_callback configuration."""
        callback = lambda attempt, exc, delay: None
        config = RetryConfig(on_retry_callback=callback)
        assert config.on_retry_callback == callback


# ============================================================================
# RetryResult Tests
# ============================================================================

class TestRetryResult:
    """Tests for RetryResult model."""
    
    def test_success_result(self):
        """Test successful result."""
        result = RetryResult(
            success=True,
            attempts=1,
            total_delay=0.0,
            last_exception=None,
            result="data"
        )
        assert result.success is True
        assert result.attempts == 1
        assert result.total_delay == 0.0
        assert result.last_exception is None
        assert result.result == "data"
    
    def test_failure_result(self):
        """Test failure result."""
        exc = ValueError("test error")
        result = RetryResult(
            success=False,
            attempts=3,
            total_delay=2.5,
            last_exception=exc,
            result=None
        )
        assert result.success is False
        assert result.attempts == 3
        assert result.total_delay == 2.5
        assert result.last_exception == exc
        assert result.result is None
    
    def test_result_with_complex_data(self):
        """Test result with complex data types."""
        data = {"key": [1, 2, 3], "nested": {"a": "b"}}
        result = RetryResult(
            success=True,
            attempts=2,
            total_delay=0.5,
            result=data
        )
        assert result.result == data


# ============================================================================
# RetryMetrics Tests
# ============================================================================

class TestRetryMetrics:
    """Tests for RetryMetrics model."""
    
    def test_default_metrics(self):
        """Test default metrics values."""
        metrics = RetryMetrics()
        assert metrics.total_calls == 0
        assert metrics.successful_first_try == 0
        assert metrics.successful_after_retry == 0
        assert metrics.failed_after_retries == 0
        assert metrics.total_retries == 0
    
    def test_average_attempts_no_calls(self):
        """Test average_attempts with no calls."""
        metrics = RetryMetrics()
        assert metrics.average_attempts == 0.0
    
    def test_average_attempts_with_calls(self):
        """Test average_attempts calculation."""
        metrics = RetryMetrics(
            total_calls=10,
            total_retries=5
        )
        # average = (total_calls + total_retries) / total_calls
        assert metrics.average_attempts == 1.5
    
    def test_success_rate_no_calls(self):
        """Test success_rate with no calls."""
        metrics = RetryMetrics()
        assert metrics.success_rate == 0.0
    
    def test_success_rate_calculation(self):
        """Test success_rate calculation."""
        metrics = RetryMetrics(
            total_calls=10,
            successful_first_try=7,
            successful_after_retry=2
        )
        # success_rate = (7 + 2) / 10 = 0.9
        assert metrics.success_rate == 0.9
    
    def test_success_rate_zero_failures(self):
        """Test success_rate with all successes."""
        metrics = RetryMetrics(
            total_calls=5,
            successful_first_try=5,
            successful_after_retry=0
        )
        assert metrics.success_rate == 1.0
    
    def test_success_rate_all_failures(self):
        """Test success_rate with all failures."""
        metrics = RetryMetrics(
            total_calls=5,
            successful_first_try=0,
            successful_after_retry=0,
            failed_after_retries=5
        )
        assert metrics.success_rate == 0.0


# ============================================================================
# Retrier - Backoff Calculation Tests
# ============================================================================

class TestRetrierBackoffCalculation:
    """Tests for Retrier backoff calculation methods."""
    
    def test_fixed_backoff(self, basic_config):
        """Test fixed backoff strategy."""
        retrier = Retrier(basic_config)
        
        # All attempts should return the same delay
        assert retrier.calculate_delay(0) == 0.1
        assert retrier.calculate_delay(1) == 0.1
        assert retrier.calculate_delay(2) == 0.1
    
    def test_linear_backoff(self):
        """Test linear backoff strategy."""
        config = RetryConfig(
            base_delay=1.0,
            backoff_strategy=BackoffStrategy.LINEAR
        )
        retrier = Retrier(config)
        
        # delay = base_delay * (attempt + 1)
        assert retrier.calculate_delay(0) == 1.0
        assert retrier.calculate_delay(1) == 2.0
        assert retrier.calculate_delay(2) == 3.0
    
    def test_exponential_backoff(self):
        """Test exponential backoff strategy."""
        config = RetryConfig(
            base_delay=1.0,
            backoff_strategy=BackoffStrategy.EXPONENTIAL
        )
        retrier = Retrier(config)
        
        # delay = base_delay * (2 ** attempt)
        assert retrier.calculate_delay(0) == 1.0
        assert retrier.calculate_delay(1) == 2.0
        assert retrier.calculate_delay(2) == 4.0
        assert retrier.calculate_delay(3) == 8.0
    
    def test_exponential_jitter_backoff(self, jitter_config):
        """Test exponential with jitter backoff strategy."""
        retrier = Retrier(jitter_config)
        
        # delay should be exponential * (1 + jitter_factor * random())
        # We cant test exact values due to randomness, but we can test bounds
        for attempt in range(5):
            delay = retrier.calculate_delay(attempt)
            exponential_delay = 0.1 * (2 ** attempt)
            min_delay = exponential_delay
            max_delay = exponential_delay * (1 + 0.5)  # jitter_factor = 0.5
            
            # Account for max_delay cap (1.0 in jitter_config)
            expected_max = min(max_delay, 1.0)
            expected_min = min(min_delay, 1.0)
            
            assert expected_min <= delay <= expected_max * 1.01  # Small margin for floating point
    
    def test_max_delay_cap(self):
        """Test that delays are capped at max_delay."""
        config = RetryConfig(
            base_delay=10.0,
            max_delay=50.0,
            backoff_strategy=BackoffStrategy.EXPONENTIAL
        )
        retrier = Retrier(config)
        
        # Without cap: 10, 20, 40, 80, 160...
        # With cap at 50: 10, 20, 40, 50, 50...
        assert retrier.calculate_delay(0) == 10.0
        assert retrier.calculate_delay(1) == 20.0
        assert retrier.calculate_delay(2) == 40.0
        assert retrier.calculate_delay(3) == 50.0  # Capped
        assert retrier.calculate_delay(10) == 50.0  # Capped
    
    def test_zero_base_delay(self):
        """Test with zero base delay."""
        config = RetryConfig(
            base_delay=0.0,
            backoff_strategy=BackoffStrategy.EXPONENTIAL
        )
        retrier = Retrier(config)
        
        assert retrier.calculate_delay(0) == 0.0
        assert retrier.calculate_delay(1) == 0.0
        assert retrier.calculate_delay(2) == 0.0


# ============================================================================
# Retrier - is_retryable Tests
# ============================================================================

class TestRetrierIsRetryable:
    """Tests for Retrier.is_retryable method."""
    
    def test_retryable_exception_type(self):
        """Test that configured exception types are retryable."""
        config = RetryConfig(retryable_exceptions=[ValueError, RuntimeError])
        retrier = Retrier(config)
        
        assert retrier.is_retryable(ValueError("test")) is True
        assert retrier.is_retryable(RuntimeError("test")) is True
        assert retrier.is_retryable(TypeError("test")) is False
    
    def test_default_exception_is_retryable(self):
        """Test that Exception is retryable by default."""
        retrier = Retrier()
        
        # All exceptions inherit from Exception
        assert retrier.is_retryable(ValueError("test")) is True
        assert retrier.is_retryable(RuntimeError("test")) is True
    
    def test_retryable_status_code_from_exception(self):
        """Test retryable status code from exception attribute."""
        config = RetryConfig(retryable_status_codes=[429, 503])
        retrier = Retrier(config)
        
        # Create exception with status_code attribute
        exc = Exception("test")
        exc.status_code = 429
        assert retrier.is_retryable(exc) is True
        
        exc.status_code = 503
        assert retrier.is_retryable(exc) is True
        
        exc.status_code = 400
        assert retrier.is_retryable(exc) is True  # Still retryable as Exception
    
    def test_retryable_status_code_from_response(self):
        """Test retryable status code from exception's response attribute."""
        config = RetryConfig(
            retryable_exceptions=[ConnectionError],
            retryable_status_codes=[502, 503]
        )
        retrier = Retrier(config)
        
        # Create exception with response attribute
        exc = ConnectionError("test")
        mock_response = MagicMock()
        mock_response.status_code = 502
        exc.response = mock_response
        
        assert retrier.is_retryable(exc) is True
    
    def test_non_retryable_exception(self):
        """Test that non-configured exceptions are not retryable."""
        config = RetryConfig(retryable_exceptions=[ValueError])
        retrier = Retrier(config)
        
        assert retrier.is_retryable(TypeError("test")) is False
        assert retrier.is_retryable(KeyError("test")) is False


# ============================================================================
# Retrier - Execute Tests
# ============================================================================

class TestRetrierExecute:
    """Tests for Retrier.execute method."""
    
    @pytest.mark.asyncio
    async def test_successful_execution_no_retry(self, retrier):
        """Test successful execution without retries."""
        async def success_func():
            return "success"
        
        result = await retrier.execute(success_func)
        
        assert result.success is True
        assert result.attempts == 1
        assert result.total_delay == 0.0
        assert result.last_exception is None
        assert result.result == "success"
    
    @pytest.mark.asyncio
    async def test_successful_execution_after_retry(self, retrier):
        """Test successful execution after retries."""
        call_count = 0
        
        async def eventually_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("temporary error")
            return "success"
        
        result = await retrier.execute(eventually_succeed)
        
        assert result.success is True
        assert result.attempts == 2
        assert call_count == 2
    
    @pytest.mark.asyncio
    async def test_failed_after_all_retries(self, retrier):
        """Test failure after exhausting all retries."""
        async def always_fail():
            raise ValueError("permanent error")
        
        result = await retrier.execute(always_fail)
        
        assert result.success is False
        assert result.attempts == 3
        assert result.last_exception is not None
        assert isinstance(result.last_exception, ValueError)
    
    @pytest.mark.asyncio
    async def test_non_retryable_exception_fails_immediately(self):
        """Test that non-retryable exceptions fail immediately."""
        config = RetryConfig(
            max_attempts=3,
            retryable_exceptions=[ValueError]  # Only ValueError is retryable
        )
        retrier = Retrier(config)
        
        async def fail_with_type_error():
            raise TypeError("non-retryable")
        
        result = await retrier.execute(fail_with_type_error)
        
        assert result.success is False
        assert result.attempts == 1  # No retries
    
    @pytest.mark.asyncio
    async def test_execution_with_arguments(self, retrier):
        """Test execution with positional and keyword arguments."""
        async def func_with_args(a, b, c=None):
            return f"{a}-{b}-{c}"
        
        result = await retrier.execute(func_with_args, "x", "y", c="z")
        
        assert result.success is True
        assert result.result == "x-y-z"
    
    @pytest.mark.asyncio
    async def test_sync_function_execution(self, retrier):
        """Test execution of synchronous functions."""
        def sync_func():
            return "sync success"
        
        result = await retrier.execute(sync_func)
        
        assert result.success is True
        assert result.result == "sync success"
    
    @pytest.mark.asyncio
    async def test_total_delay_tracking(self):
        """Test that total_delay is tracked correctly."""
        config = RetryConfig(
            max_attempts=3,
            base_delay=0.05,
            backoff_strategy=BackoffStrategy.FIXED
        )
        retrier = Retrier(config)
        
        call_count = 0
        
        async def fail_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("error")
            return "success"
        
        result = await retrier.execute(fail_twice)
        
        # 2 retries * 0.05 delay = 0.10
        assert result.success is True
        assert result.total_delay >= 0.10
    
    @pytest.mark.asyncio
    async def test_on_retry_callback_called(self):
        """Test that on_retry_callback is called before retries."""
        callback_calls = []
        
        def callback(attempt, exc, delay):
            callback_calls.append({
                'attempt': attempt,
                'exception': exc,
                'delay': delay
            })
        
        config = RetryConfig(
            max_attempts=3,
            base_delay=0.01,
            backoff_strategy=BackoffStrategy.FIXED,
            on_retry_callback=callback
        )
        retrier = Retrier(config)
        
        call_count = 0
        
        async def fail_once():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("first error")
            return "success"
        
        result = await retrier.execute(fail_once)
        
        assert result.success is True
        assert len(callback_calls) == 1
        assert callback_calls[0]['attempt'] == 1
        assert isinstance(callback_calls[0]['exception'], ValueError)
        assert callback_calls[0]['delay'] == 0.01
    
    @pytest.mark.asyncio
    async def test_callback_exception_does_not_affect_retry(self):
        """Test that callback exceptions don't affect retry logic."""
        def bad_callback(attempt, exc, delay):
            raise RuntimeError("callback error")
        
        config = RetryConfig(
            max_attempts=3,
            base_delay=0.01,
            on_retry_callback=bad_callback
        )
        retrier = Retrier(config)
        
        call_count = 0
        
        async def fail_once():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("error")
            return "success"
        
        result = await retrier.execute(fail_once)
        
        # Should still succeed despite callback error
        assert result.success is True


# ============================================================================
# Retrier - Metrics Tests
# ============================================================================

class TestRetrierMetrics:
    """Tests for Retrier metrics collection."""
    
    @pytest.mark.asyncio
    async def test_metrics_successful_first_try(self, retrier):
        """Test metrics for successful first try."""
        async def success():
            return "ok"
        
        await retrier.execute(success)
        metrics = retrier.get_metrics()
        
        assert metrics.total_calls == 1
        assert metrics.successful_first_try == 1
        assert metrics.successful_after_retry == 0
        assert metrics.failed_after_retries == 0
    
    @pytest.mark.asyncio
    async def test_metrics_successful_after_retry(self, retrier):
        """Test metrics for success after retry."""
        call_count = 0
        
        async def fail_once():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("error")
            return "ok"
        
        await retrier.execute(fail_once)
        metrics = retrier.get_metrics()
        
        assert metrics.total_calls == 1
        assert metrics.successful_first_try == 0
        assert metrics.successful_after_retry == 1
        assert metrics.total_retries == 1
    
    @pytest.mark.asyncio
    async def test_metrics_failed_after_retries(self, retrier):
        """Test metrics for failures after all retries."""
        async def always_fail():
            raise ValueError("error")
        
        await retrier.execute(always_fail)
        metrics = retrier.get_metrics()
        
        assert metrics.total_calls == 1
        assert metrics.successful_first_try == 0
        assert metrics.successful_after_retry == 0
        assert metrics.failed_after_retries == 1
        assert metrics.total_retries == 2  # 3 attempts - 1 initial
    
    @pytest.mark.asyncio
    async def test_metrics_multiple_calls(self, retrier):
        """Test metrics accumulation over multiple calls."""
        async def success():
            return "ok"
        
        async def fail():
            raise ValueError("error")
        
        await retrier.execute(success)
        await retrier.execute(success)
        await retrier.execute(fail)
        
        metrics = retrier.get_metrics()
        assert metrics.total_calls == 3
        assert metrics.successful_first_try == 2
        assert metrics.failed_after_retries == 1
    
    def test_reset_metrics(self, retrier):
        """Test resetting metrics."""
        # Manually update metrics
        retrier._metrics.total_calls = 10
        retrier._metrics.successful_first_try = 8
        
        retrier.reset_metrics()
        metrics = retrier.get_metrics()
        
        assert metrics.total_calls == 0
        assert metrics.successful_first_try == 0
    
    @pytest.mark.asyncio
    async def test_metrics_immutability(self, retrier):
        """Test that get_metrics returns a copy."""
        async def success():
            return "ok"
        
        await retrier.execute(success)
        metrics1 = retrier.get_metrics()
        metrics2 = retrier.get_metrics()
        
        # Modifying returned metrics shouldn't affect internal state
        metrics1.total_calls = 999
        metrics3 = retrier.get_metrics()
        assert metrics3.total_calls == 1


# ============================================================================
# Retry Decorator Tests
# ============================================================================

class TestRetryDecorator:
    """Tests for @retry decorator."""
    
    @pytest.mark.asyncio
    async def test_decorator_success_no_retry(self):
        """Test decorator with successful function."""
        @retry(max_attempts=3)
        async def success_func():
            return "success"
        
        result = await success_func()
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_decorator_success_after_retry(self):
        """Test decorator with function that succeeds after retry."""
        call_count = 0
        
        @retry(max_attempts=3, base_delay=0.01)
        async def eventually_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("error")
            return "success"
        
        result = await eventually_succeed()
        assert result == "success"
        assert call_count == 2
    
    @pytest.mark.asyncio
    async def test_decorator_raises_on_failure(self):
        """Test that decorator raises exception on failure."""
        @retry(max_attempts=2, base_delay=0.01)
        async def always_fail():
            raise ValueError("permanent error")
        
        with pytest.raises(ValueError, match="permanent error"):
            await always_fail()
    
    @pytest.mark.asyncio
    async def test_decorator_with_backoff_strategy(self):
        """Test decorator with specific backoff strategy."""
        @retry(
            max_attempts=3,
            base_delay=0.01,
            backoff_strategy=BackoffStrategy.LINEAR
        )
        async def func():
            return "ok"
        
        result = await func()
        assert result == "ok"
    
    @pytest.mark.asyncio
    async def test_decorator_preserves_function_metadata(self):
        """Test that decorator preserves function name and docstring."""
        @retry()
        async def my_function():
            """My docstring."""
            return "ok"
        
        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."
    
    @pytest.mark.asyncio
    async def test_decorator_with_arguments(self):
        """Test decorator with function arguments."""
        @retry()
        async def func_with_args(a, b, c=None):
            return f"{a}-{b}-{c}"
        
        result = await func_with_args("x", "y", c="z")
        assert result == "x-y-z"
    
    @pytest.mark.asyncio
    async def test_decorator_with_custom_exceptions(self):
        """Test decorator with custom retryable exceptions."""
        call_count = 0
        
        @retry(
            max_attempts=3,
            base_delay=0.01,
            retryable_exceptions=[RuntimeError]
        )
        async def func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("retryable")
            return "ok"
        
        result = await func()
        assert result == "ok"
        assert call_count == 2
    
    @pytest.mark.asyncio
    async def test_decorator_non_retryable_fails_immediately(self):
        """Test decorator with non-retryable exception."""
        @retry(
            max_attempts=3,
            retryable_exceptions=[ValueError]
        )
        async def func():
            raise TypeError("not retryable")
        
        with pytest.raises(TypeError):
            await func()


# ============================================================================
# RetryRegistry Tests
# ============================================================================

class TestRetryRegistry:
    """Tests for RetryRegistry."""
    
    def test_get_or_create_new_retrier(self, registry, basic_config):
        """Test creating a new retrier."""
        retrier = registry.get_or_create('test', basic_config)
        
        assert isinstance(retrier, Retrier)
        assert 'test' in registry.names
    
    def test_get_or_create_existing_retrier(self, registry, basic_config):
        """Test retrieving an existing retrier."""
        retrier1 = registry.get_or_create('test', basic_config)
        retrier2 = registry.get_or_create('test')  # No config needed
        
        assert retrier1 is retrier2
    
    def test_get_metrics_existing(self, registry, basic_config):
        """Test getting metrics for existing retrier."""
        retrier = registry.get_or_create('test', basic_config)
        metrics = registry.get_metrics('test')
        
        assert metrics is not None
        assert isinstance(metrics, RetryMetrics)
    
    def test_get_metrics_nonexistent(self, registry):
        """Test getting metrics for non-existent retrier."""
        metrics = registry.get_metrics('nonexistent')
        assert metrics is None
    
    def test_get_all_metrics(self, registry, basic_config):
        """Test getting all metrics."""
        registry.get_or_create('retrier1', basic_config)
        registry.get_or_create('retrier2', basic_config)
        
        all_metrics = registry.get_all_metrics()
        
        assert 'retrier1' in all_metrics
        assert 'retrier2' in all_metrics
        assert len(all_metrics) == 2
    
    def test_remove_existing(self, registry, basic_config):
        """Test removing an existing retrier."""
        registry.get_or_create('test', basic_config)
        result = registry.remove('test')
        
        assert result is True
        assert 'test' not in registry.names
    
    def test_remove_nonexistent(self, registry):
        """Test removing a non-existent retrier."""
        result = registry.remove('nonexistent')
        assert result is False
    
    def test_clear(self, registry, basic_config):
        """Test clearing all retriers."""
        registry.get_or_create('test1', basic_config)
        registry.get_or_create('test2', basic_config)
        
        registry.clear()
        
        assert len(registry.names) == 0
    
    def test_names_property(self, registry, basic_config):
        """Test names property."""
        registry.get_or_create('alpha', basic_config)
        registry.get_or_create('beta', basic_config)
        
        names = registry.names
        
        assert 'alpha' in names
        assert 'beta' in names
        assert len(names) == 2
    
    @pytest.mark.asyncio
    async def test_registry_metrics_tracking(self, registry, basic_config):
        """Test that registry tracks metrics correctly."""
        retrier = registry.get_or_create('test', basic_config)
        
        async def success():
            return "ok"
        
        await retrier.execute(success)
        
        metrics = registry.get_metrics('test')
        assert metrics.total_calls == 1
        assert metrics.successful_first_try == 1
    
    def test_reset_all_metrics(self, registry, basic_config):
        """Test resetting all metrics."""
        retrier1 = registry.get_or_create('r1', basic_config)
        retrier2 = registry.get_or_create('r2', basic_config)
        
        # Manually set metrics
        retrier1._metrics.total_calls = 10
        retrier2._metrics.total_calls = 20
        
        registry.reset_all_metrics()
        
        assert registry.get_metrics('r1').total_calls == 0
        assert registry.get_metrics('r2').total_calls == 0


# ============================================================================
# Global Registry Tests
# ============================================================================

class TestGlobalRegistry:
    """Tests for global registry functions."""
    
    def test_get_global_registry_singleton(self):
        """Test that get_global_registry returns singleton."""
        reset_global_registry()
        
        registry1 = get_global_registry()
        registry2 = get_global_registry()
        
        assert registry1 is registry2
    
    def test_reset_global_registry(self):
        """Test resetting global registry."""
        registry1 = get_global_registry()
        registry1.get_or_create('test')
        
        reset_global_registry()
        
        registry2 = get_global_registry()
        assert 'test' not in registry2.names


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    @pytest.mark.asyncio
    async def test_zero_max_attempts(self):
        """Test behavior with minimal max_attempts."""
        config = RetryConfig(max_attempts=1)
        retrier = Retrier(config)
        
        async def success():
            return "ok"
        
        result = await retrier.execute(success)
        assert result.success is True
        assert result.attempts == 1
    
    @pytest.mark.asyncio
    async def test_large_max_attempts(self):
        """Test with large max_attempts value."""
        config = RetryConfig(max_attempts=100, base_delay=0.001)
        retrier = Retrier(config)
        
        async def success():
            return "ok"
        
        result = await retrier.execute(success)
        assert result.success is True
        assert result.attempts == 1
    
    @pytest.mark.asyncio
    async def test_very_small_delays(self):
        """Test with very small delays."""
        config = RetryConfig(
            base_delay=0.001,
            backoff_strategy=BackoffStrategy.FIXED
        )
        retrier = Retrier(config)
        
        call_count = 0
        
        async def fail_once():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("error")
            return "ok"
        
        result = await retrier.execute(fail_once)
        assert result.success is True
    
    @pytest.mark.asyncio
    async def test_none_result(self, retrier):
        """Test function that returns None."""
        async def returns_none():
            return None
        
        result = await retrier.execute(returns_none)
        
        assert result.success is True
        assert result.result is None
    
    @pytest.mark.asyncio
    async def test_complex_exception_info(self):
        """Test that exception information is preserved."""
        config = RetryConfig(max_attempts=1)
        retrier = Retrier(config)
        
        async def complex_error():
            e = ValueError("detailed error message")
            e.custom_attr = "custom value"
            raise e
        
        result = await retrier.execute(complex_error)
        
        assert result.success is False
        assert isinstance(result.last_exception, ValueError)
        assert str(result.last_exception) == "detailed error message"
        assert result.last_exception.custom_attr == "custom value"
    
    @pytest.mark.asyncio
    async def test_concurrent_executions(self):
        """Test concurrent executions on same retrier."""
        config = RetryConfig(base_delay=0.01)
        retrier = Retrier(config)
        
        async def func(n):
            return n * 2
        
        # Execute multiple concurrent operations
        tasks = [retrier.execute(func, i) for i in range(10)]
        results = await asyncio.gather(*tasks)
        
        assert all(r.success for r in results)
        assert [r.result for r in results] == [0, 2, 4, 6, 8, 10, 12, 14, 16, 18]
        
        metrics = retrier.get_metrics()
        assert metrics.total_calls == 10
        assert metrics.successful_first_try == 10
    
    @pytest.mark.asyncio
    async def test_exception_with_status_code_attribute(self):
        """Test exception with status_code attribute."""
        config = RetryConfig(
            retryable_exceptions=[Exception],
            retryable_status_codes=[503]
        )
        retrier = Retrier(config)
        
        call_count = 0
        
        async def fail_with_status():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                exc = Exception("service unavailable")
                exc.status_code = 503
                raise exc
            return "ok"
        
        result = await retrier.execute(fail_with_status)
        
        assert result.success is True
        assert result.attempts == 2


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests combining multiple components."""
    
    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Test complete workflow with registry and decorator."""
        registry = RetryRegistry()
        config = RetryConfig(
            max_attempts=3,
            base_delay=0.01,
            backoff_strategy=BackoffStrategy.EXPONENTIAL_JITTER
        )
        
        retrier = registry.get_or_create('api_calls', config)
        
        call_count = 0
        
        async def api_call():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("network error")
            return {"data": "success"}
        
        result = await retrier.execute(api_call)
        
        assert result.success is True
        assert result.attempts == 2
        
        metrics = registry.get_metrics('api_calls')
        assert metrics.successful_after_retry == 1
    
    @pytest.mark.asyncio
    async def test_multiple_retriers_different_configs(self):
        """Test multiple retriers with different configurations."""
        registry = RetryRegistry()
        
        config_fast = RetryConfig(
            max_attempts=2,
            base_delay=0.01,
            backoff_strategy=BackoffStrategy.FIXED
        )
        
        config_slow = RetryConfig(
            max_attempts=5,
            base_delay=0.01,
            backoff_strategy=BackoffStrategy.EXPONENTIAL
        )
        
        fast_retrier = registry.get_or_create('fast', config_fast)
        slow_retrier = registry.get_or_create('slow', config_slow)
        
        async def always_fail():
            raise ValueError("error")
        
        result_fast = await fast_retrier.execute(always_fail)
        result_slow = await slow_retrier.execute(always_fail)
        
        assert result_fast.attempts == 2
        assert result_slow.attempts == 5
        
        all_metrics = registry.get_all_metrics()
        assert len(all_metrics) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
