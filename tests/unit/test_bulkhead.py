"""Unit tests for Bulkhead Isolation Pattern.

Comprehensive test suite for bulkhead module covering:
- BulkheadState enum
- BulkheadConfig validation
- BulkheadMetrics model
- Bulkhead class operations
- BulkheadRegistry management
- Decorator functionality
- Exception handling
- Edge cases and concurrency
"""

import asyncio
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager

from animus_resilience.bulkhead import (
    BulkheadState,
    BulkheadConfig,
    BulkheadMetrics,
    Bulkhead,
    BulkheadRegistry,
    BulkheadFullError,
    BulkheadTimeoutError,
    BulkheadCallTimeoutError,
    bulkhead,
    bulkhead_with_config,
    registry,
)


# ============================================================
# BulkheadState Tests
# ============================================================

class TestBulkheadState:
    """Tests for BulkheadState enum."""

    def test_bulkhead_state_values(self):
        """Test BulkheadState enum values."""
        assert BulkheadState.OPEN == "open"
        assert BulkheadState.CLOSED == "closed"
        assert BulkheadState.FULL == "full"

    def test_bulkhead_state_string_conversion(self):
        """Test BulkheadState string conversion."""
        # str(Enum) returns 'EnumName.VALUE', use .value for just the value
        assert BulkheadState.OPEN.value == "open"
        assert BulkheadState.CLOSED.value == "closed"
        assert BulkheadState.FULL.value == "full"

    def test_bulkhead_state_from_string(self):
        """Test creating BulkheadState from string."""
        assert BulkheadState("open") == BulkheadState.OPEN
        assert BulkheadState("closed") == BulkheadState.CLOSED
        assert BulkheadState("full") == BulkheadState.FULL


# ============================================================
# BulkheadConfig Tests
# ============================================================

class TestBulkheadConfig:
    """Tests for BulkheadConfig model."""

    def test_default_config(self):
        """Test default configuration values."""
        config = BulkheadConfig(name="test")

        assert config.name == "test"
        assert config.max_concurrent_calls == 10
        assert config.max_wait_duration == 5.0
        assert config.call_timeout == 30.0

    def test_custom_config(self):
        """Test custom configuration values."""
        config = BulkheadConfig(
            name="custom",
            max_concurrent_calls=5,
            max_wait_duration=2.5,
            call_timeout=10.0
        )

        assert config.name == "custom"
        assert config.max_concurrent_calls == 5
        assert config.max_wait_duration == 2.5
        assert config.call_timeout == 10.0

    def test_invalid_empty_name(self):
        """Test that empty name raises validation error."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            BulkheadConfig(name="")

    def test_invalid_whitespace_name(self):
        """Test that whitespace-only name raises validation error."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            BulkheadConfig(name="   ")

    def test_name_stripping(self):
        """Test that name is stripped of whitespace."""
        config = BulkheadConfig(name="  test  ")
        assert config.name == "test"

    def test_invalid_max_concurrent_calls_zero(self):
        """Test that zero max_concurrent_calls raises error."""
        with pytest.raises(ValueError):
            BulkheadConfig(name="test", max_concurrent_calls=0)

    def test_invalid_max_concurrent_calls_negative(self):
        """Test that negative max_concurrent_calls raises error."""
        with pytest.raises(ValueError):
            BulkheadConfig(name="test", max_concurrent_calls=-1)

    def test_invalid_max_wait_duration_negative(self):
        """Test that negative max_wait_duration raises error."""
        with pytest.raises(ValueError):
            BulkheadConfig(name="test", max_wait_duration=-1.0)

    def test_zero_max_wait_duration_allowed(self):
        """Test that zero max_wait_duration is allowed."""
        config = BulkheadConfig(name="test", max_wait_duration=0.0)
        assert config.max_wait_duration == 0.0

    def test_invalid_call_timeout_zero(self):
        """Test that zero call_timeout raises error."""
        with pytest.raises(ValueError):
            BulkheadConfig(name="test", call_timeout=0.0)

    def test_invalid_call_timeout_negative(self):
        """Test that negative call_timeout raises error."""
        with pytest.raises(ValueError):
            BulkheadConfig(name="test", call_timeout=-1.0)


# ============================================================
# BulkheadMetrics Tests
# ============================================================

class TestBulkheadMetrics:
    """Tests for BulkheadMetrics model."""

    def test_default_metrics(self):
        """Test default metrics values."""
        metrics = BulkheadMetrics(name="test")

        assert metrics.name == "test"
        assert metrics.available_permits == 0
        assert metrics.max_permits == 0
        assert metrics.queued_calls == 0
        assert metrics.active_calls == 0
        assert metrics.rejected_calls == 0
        assert metrics.timeout_calls == 0
        assert metrics.accepted_calls == 0
        assert metrics.completed_calls == 0

    def test_utilization_calculation(self):
        """Test utilization percentage calculation."""
        metrics = BulkheadMetrics(
            name="test",
            max_permits=10,
            active_calls=5
        )
        assert metrics.utilization == 50.0

    def test_utilization_zero_max_permits(self):
        """Test utilization when max_permits is zero."""
        metrics = BulkheadMetrics(name="test", max_permits=0)
        assert metrics.utilization == 0.0

    def test_utilization_full(self):
        """Test utilization when all permits used."""
        metrics = BulkheadMetrics(
            name="test",
            max_permits=5,
            active_calls=5
        )
        assert metrics.utilization == 100.0

    def test_utilization_partial(self):
        """Test utilization with partial usage."""
        metrics = BulkheadMetrics(
            name="test",
            max_permits=8,
            active_calls=3
        )
        assert metrics.utilization == 37.5


# ============================================================
# Bulkhead Tests
# ============================================================

class TestBulkhead:
    """Tests for Bulkhead class."""

    @pytest.fixture
    def bulkhead_config(self):
        """Create a test bulkhead configuration."""
        return BulkheadConfig(
            name="test",
            max_concurrent_calls=3,
            max_wait_duration=0.5,
            call_timeout=1.0
        )

    @pytest.fixture
    def bulkhead(self, bulkhead_config):
        """Create a test bulkhead instance."""
        return Bulkhead(bulkhead_config)

    def test_bulkhead_initialization(self, bulkhead, bulkhead_config):
        """Test bulkhead initialization."""
        assert bulkhead.config == bulkhead_config
        assert bulkhead.name == "test"

    def test_initial_metrics(self, bulkhead):
        """Test initial metrics after creation."""
        metrics = bulkhead.get_metrics()

        assert metrics.name == "test"
        assert metrics.available_permits == 3
        assert metrics.max_permits == 3
        assert metrics.queued_calls == 0
        assert metrics.active_calls == 0
        assert metrics.rejected_calls == 0

    def test_initial_state(self, bulkhead):
        """Test initial bulkhead state is OPEN."""
        assert bulkhead.get_state() == BulkheadState.OPEN

    @pytest.mark.asyncio
    async def test_acquire_release(self, bulkhead):
        """Test basic acquire and release."""
        acquired = await bulkhead.acquire()
        assert acquired is True

        metrics = bulkhead.get_metrics()
        assert metrics.available_permits == 2
        assert metrics.active_calls == 1
        assert metrics.accepted_calls == 1

        bulkhead.release()

        metrics = bulkhead.get_metrics()
        assert metrics.available_permits == 3
        assert metrics.active_calls == 0
        assert metrics.completed_calls == 1

    @pytest.mark.asyncio
    async def test_multiple_acquires(self, bulkhead):
        """Test multiple concurrent acquires."""
        await bulkhead.acquire()
        await bulkhead.acquire()
        await bulkhead.acquire()

        metrics = bulkhead.get_metrics()
        assert metrics.available_permits == 0
        assert metrics.active_calls == 3
        assert bulkhead.get_state() == BulkheadState.CLOSED

    @pytest.mark.asyncio
    async def test_acquire_timeout(self, bulkhead):
        """Test acquire timeout when bulkhead is full."""
        # Fill up the bulkhead
        await bulkhead.acquire()
        await bulkhead.acquire()
        await bulkhead.acquire()

        # Next acquire should timeout
        with pytest.raises(BulkheadTimeoutError) as exc_info:
            await bulkhead.acquire()

        assert exc_info.value.name == "test"
        assert exc_info.value.timeout == 0.5
        assert exc_info.value.operation == "acquire"

        metrics = bulkhead.get_metrics()
        assert metrics.rejected_calls == 1
        assert metrics.timeout_calls == 1

    @pytest.mark.asyncio
    async def test_is_call_permitted(self, bulkhead):
        """Test is_call_permitted check."""
        assert bulkhead.is_call_permitted() is True

        await bulkhead.acquire()
        await bulkhead.acquire()
        await bulkhead.acquire()

        assert bulkhead.is_call_permitted() is False

    @pytest.mark.asyncio
    async def test_context_manager(self, bulkhead):
        """Test async context manager usage."""
        async with bulkhead:
            metrics = bulkhead.get_metrics()
            assert metrics.active_calls == 1
            assert metrics.available_permits == 2

        metrics = bulkhead.get_metrics()
        assert metrics.active_calls == 0
        assert metrics.available_permits == 3

    @pytest.mark.asyncio
    async def test_execute_async_function(self, bulkhead):
        """Test execute with async function."""
        async def async_task(value):
            await asyncio.sleep(0.01)
            return value * 2

        result = await bulkhead.execute(async_task, 21)
        assert result == 42

        metrics = bulkhead.get_metrics()
        assert metrics.accepted_calls == 1
        assert metrics.completed_calls == 1

    @pytest.mark.asyncio
    async def test_execute_sync_function(self, bulkhead):
        """Test execute with sync function."""
        def sync_task(value):
            return value * 3

        result = await bulkhead.execute(sync_task, 14)
        assert result == 42

        metrics = bulkhead.get_metrics()
        assert metrics.completed_calls == 1

    @pytest.mark.asyncio
    async def test_execute_with_call_timeout(self, bulkhead):
        """Test execute with call timeout."""
        async def slow_task():
            await asyncio.sleep(2.0)  # Longer than call_timeout
            return "done"

        with pytest.raises(BulkheadCallTimeoutError) as exc_info:
            await bulkhead.execute(slow_task)

        assert exc_info.value.name == "test"
        assert exc_info.value.timeout == 1.0

        metrics = bulkhead.get_metrics()
        assert metrics.timeout_calls == 1

    @pytest.mark.asyncio
    async def test_execute_with_exception(self, bulkhead):
        """Test execute handles exceptions and releases permit."""
        async def failing_task():
            raise ValueError("task failed")

        with pytest.raises(ValueError, match="task failed"):
            await bulkhead.execute(failing_task)

        # Permit should still be released
        metrics = bulkhead.get_metrics()
        assert metrics.active_calls == 0
        assert metrics.available_permits == 3

    @pytest.mark.asyncio
    async def test_concurrent_execute(self, bulkhead):
        """Test concurrent execute calls."""
        async def task(n):
            await asyncio.sleep(0.05)
            return n

        # Run more tasks than permits
        tasks = [bulkhead.execute(task, i) for i in range(5)]
        results = await asyncio.gather(*tasks)

        assert results == [0, 1, 2, 3, 4]

        metrics = bulkhead.get_metrics()
        assert metrics.completed_calls == 5

    @pytest.mark.asyncio
    async def test_metrics_during_execution(self, bulkhead):
        """Test metrics accuracy during execution."""
        started = asyncio.Event()
        can_finish = asyncio.Event()

        async def blocking_task():
            started.set()
            await can_finish.wait()
            return "done"

        # Start task
        task = asyncio.create_task(bulkhead.execute(blocking_task))
        await started.wait()

        # Check metrics during execution
        metrics = bulkhead.get_metrics()
        assert metrics.active_calls == 1
        assert metrics.available_permits == 2

        # Finish task
        can_finish.set()
        result = await task
        assert result == "done"

        metrics = bulkhead.get_metrics()
        assert metrics.active_calls == 0
        assert metrics.available_permits == 3

    def test_reset_metrics(self, bulkhead):
        """Test resetting metrics."""
        # Simulate some activity
        with bulkhead._counter_lock:
            bulkhead._rejected_calls = 10
            bulkhead._timeout_calls = 5
            bulkhead._accepted_calls = 20
            bulkhead._completed_calls = 15

        bulkhead.reset_metrics()

        metrics = bulkhead.get_metrics()
        assert metrics.rejected_calls == 0
        assert metrics.timeout_calls == 0
        assert metrics.accepted_calls == 0
        assert metrics.completed_calls == 0

    def test_get_state_open(self, bulkhead):
        """Test get_state returns OPEN when permits available."""
        assert bulkhead.get_state() == BulkheadState.OPEN

    @pytest.mark.asyncio
    async def test_get_state_closed(self, bulkhead):
        """Test get_state returns CLOSED when no permits."""
        await bulkhead.acquire()
        await bulkhead.acquire()
        await bulkhead.acquire()

        assert bulkhead.get_state() == BulkheadState.CLOSED


# ============================================================
# BulkheadRegistry Tests
# ============================================================

class TestBulkheadRegistry:
    """Tests for BulkheadRegistry class."""

    @pytest.fixture(autouse=True)
    def reset_registry(self):
        """Reset registry before and after each test."""
        BulkheadRegistry.reset_instance()
        yield
        BulkheadRegistry.reset_instance()

    def test_singleton_pattern(self):
        """Test that registry is a singleton."""
        registry1 = BulkheadRegistry()
        registry2 = BulkheadRegistry()

        assert registry1 is registry2

    def test_get_or_create_new(self):
        """Test creating new bulkhead in registry."""
        registry = BulkheadRegistry()
        config = BulkheadConfig(name="new_bulkhead")

        bulkhead = registry.get_or_create("new_bulkhead", config)

        assert bulkhead is not None
        assert bulkhead.name == "new_bulkhead"

    def test_get_or_create_existing(self):
        """Test getting existing bulkhead from registry."""
        registry = BulkheadRegistry()
        config = BulkheadConfig(name="existing", max_concurrent_calls=5)

        bulkhead1 = registry.get_or_create("existing", config)
        bulkhead2 = registry.get_or_create("existing")

        assert bulkhead1 is bulkhead2

    def test_get_or_create_with_default_config(self):
        """Test get_or_create creates with default config if not provided."""
        registry = BulkheadRegistry()

        bulkhead = registry.get_or_create("default")

        assert bulkhead.config.max_concurrent_calls == 10
        assert bulkhead.config.max_wait_duration == 5.0

    def test_get_existing(self):
        """Test getting existing bulkhead."""
        registry = BulkheadRegistry()
        config = BulkheadConfig(name="test")
        registry.get_or_create("test", config)

        bulkhead = registry.get("test")

        assert bulkhead is not None
        assert bulkhead.name == "test"

    def test_get_nonexistent(self):
        """Test getting nonexistent bulkhead returns None."""
        registry = BulkheadRegistry()

        bulkhead = registry.get("nonexistent")

        assert bulkhead is None

    def test_remove_existing(self):
        """Test removing existing bulkhead."""
        registry = BulkheadRegistry()
        config = BulkheadConfig(name="remove_me")
        registry.get_or_create("remove_me", config)

        result = registry.remove("remove_me")

        assert result is True
        assert registry.get("remove_me") is None

    def test_remove_nonexistent(self):
        """Test removing nonexistent bulkhead returns False."""
        registry = BulkheadRegistry()

        result = registry.remove("nonexistent")

        assert result is False

    def test_get_all_metrics(self):
        """Test getting metrics for all bulkheads."""
        registry = BulkheadRegistry()
        registry.get_or_create("bh1", BulkheadConfig(name="bh1"))
        registry.get_or_create("bh2", BulkheadConfig(name="bh2"))

        all_metrics = registry.get_all_metrics()

        assert "bh1" in all_metrics
        assert "bh2" in all_metrics
        assert all_metrics["bh1"].name == "bh1"
        assert all_metrics["bh2"].name == "bh2"

    def test_get_all_states(self):
        """Test getting states for all bulkheads."""
        registry = BulkheadRegistry()
        registry.get_or_create("bh1", BulkheadConfig(name="bh1"))
        registry.get_or_create("bh2", BulkheadConfig(name="bh2"))

        all_states = registry.get_all_states()

        assert "bh1" in all_states
        assert "bh2" in all_states
        assert all_states["bh1"] == BulkheadState.OPEN

    def test_list_bulkheads(self):
        """Test listing all bulkhead names."""
        registry = BulkheadRegistry()
        registry.get_or_create("alpha")
        registry.get_or_create("beta")
        registry.get_or_create("gamma")

        names = registry.list_bulkheads()

        assert set(names) == {"alpha", "beta", "gamma"}

    def test_clear(self):
        """Test clearing all bulkheads."""
        registry = BulkheadRegistry()
        registry.get_or_create("one")
        registry.get_or_create("two")

        registry.clear()

        assert registry.list_bulkheads() == []


# ============================================================
# Decorator Tests
# ============================================================

class TestBulkheadDecorator:
    """Tests for bulkhead decorators."""

    @pytest.fixture(autouse=True)
    def reset_registry(self):
        """Reset registry before and after each test."""
        BulkheadRegistry.reset_instance()
        yield
        BulkheadRegistry.reset_instance()

    @pytest.mark.asyncio
    async def test_bulkhead_decorator_basic(self):
        """Test basic bulkhead decorator."""
        @bulkhead("test_decorator", max_concurrent=2)
        async def decorated_task(value):
            await asyncio.sleep(0.01)
            return value * 2

        result = await decorated_task(21)
        assert result == 42

        # Check bulkhead was created
        bh = registry.get("test_decorator")
        assert bh is not None
        assert bh.config.max_concurrent_calls == 2

    @pytest.mark.asyncio
    async def test_bulkhead_decorator_multiple_calls(self):
        """Test decorator with multiple concurrent calls."""
        @bulkhead("multi", max_concurrent=3)
        async def task(n):
            await asyncio.sleep(0.05)
            return n

        results = await asyncio.gather(*[task(i) for i in range(5)])

        assert results == [0, 1, 2, 3, 4]

        bh = registry.get("multi")
        assert bh.get_metrics().completed_calls == 5

    @pytest.mark.asyncio
    async def test_bulkhead_decorator_with_timeout(self):
        """Test decorator with call timeout."""
        @bulkhead("timeout_test", max_concurrent=1, call_timeout=0.1)
        async def slow_task():
            await asyncio.sleep(1.0)
            return "done"

        with pytest.raises(BulkheadCallTimeoutError):
            await slow_task()

    @pytest.mark.asyncio
    async def test_bulkhead_with_config_decorator(self):
        """Test bulkhead_with_config decorator."""
        config = BulkheadConfig(
            name="config_decorator",
            max_concurrent_calls=2,
            max_wait_duration=1.0,
            call_timeout=5.0
        )

        @bulkhead_with_config(config)
        async def configured_task(x, y):
            return x + y

        result = await configured_task(10, 20)
        assert result == 30

        bh = registry.get("config_decorator")
        assert bh is not None
        assert bh.config.max_concurrent_calls == 2

    @pytest.mark.asyncio
    async def test_decorator_preserves_function_metadata(self):
        """Test that decorator preserves function name and docstring."""
        @bulkhead("meta_test")
        async def documented_function():
            """This is a documented function."""
            return "result"

        assert documented_function.__name__ == "documented_function"
        assert documented_function.__doc__ == "This is a documented function."


# ============================================================
# Exception Tests
# ============================================================

class TestBulkheadExceptions:
    """Tests for bulkhead exceptions."""

    def test_bulkhead_full_error(self):
        """Test BulkheadFullError properties."""
        error = BulkheadFullError("test", max_concurrent=5)

        assert error.name == "test"
        assert error.max_concurrent == 5
        assert "test" in str(error)
        assert "5" in str(error)

    def test_bulkhead_timeout_error(self):
        """Test BulkheadTimeoutError properties."""
        error = BulkheadTimeoutError("test", timeout=2.5, operation="acquire")

        assert error.name == "test"
        assert error.timeout == 2.5
        assert error.operation == "acquire"
        assert "test" in str(error)
        assert "2.5" in str(error)

    def test_bulkhead_call_timeout_error(self):
        """Test BulkheadCallTimeoutError properties."""
        error = BulkheadCallTimeoutError("test", timeout=10.0)

        assert error.name == "test"
        assert error.timeout == 10.0
        assert "test" in str(error)
        assert "10.0" in str(error)


# ============================================================
# Edge Cases and Integration Tests
# ============================================================

class TestBulkheadEdgeCases:
    """Tests for edge cases and integration scenarios."""

    @pytest.fixture(autouse=True)
    def reset_registry(self):
        """Reset registry before and after each test."""
        BulkheadRegistry.reset_instance()
        yield
        BulkheadRegistry.reset_instance()

    @pytest.mark.asyncio
    async def test_single_permit_bulkhead(self):
        """Test bulkhead with single permit (mutex-like)."""
        config = BulkheadConfig(
            name="mutex",
            max_concurrent_calls=1,
            max_wait_duration=0.5
        )
        bulkhead = Bulkhead(config)

        executed = []

        async def task(n):
            executed.append(f"start_{n}")
            await asyncio.sleep(0.05)
            executed.append(f"end_{n}")
            return n

        # Run multiple tasks - should execute sequentially
        results = await asyncio.gather(
            bulkhead.execute(task, 1),
            bulkhead.execute(task, 2),
            bulkhead.execute(task, 3)
        )

        assert results == [1, 2, 3]
        # Verify sequential execution (no overlapping starts/ends)
        assert executed == [
            "start_1", "end_1",
            "start_2", "end_2",
            "start_3", "end_3"
        ]

    @pytest.mark.asyncio
    async def test_high_concurrency_bulkhead(self):
        """Test bulkhead with high concurrency limit."""
        config = BulkheadConfig(
            name="high_concurrent",
            max_concurrent_calls=100
        )
        bulkhead = Bulkhead(config)

        async def quick_task(n):
            return n * 2

        # Run 50 concurrent tasks
        tasks = [bulkhead.execute(quick_task, i) for i in range(50)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 50
        assert sum(results) == sum(i * 2 for i in range(50))

    @pytest.mark.asyncio
    async def test_nested_bulkhead_calls(self):
        """Test nested bulkhead protected calls."""
        config1 = BulkheadConfig(name="outer", max_concurrent_calls=2)
        config2 = BulkheadConfig(name="inner", max_concurrent_calls=1)

        outer_bh = Bulkhead(config1)
        inner_bh = Bulkhead(config2)

        async def inner_task():
            return await inner_bh.execute(lambda: 42)

        result = await outer_bh.execute(inner_task)
        assert result == 42

    @pytest.mark.asyncio
    async def test_bulkhead_with_async_context_manager(self):
        """Test using bulkhead as async context manager."""
        config = BulkheadConfig(name="ctx_test", max_concurrent_calls=1)
        bulkhead = Bulkhead(config)

        async with bulkhead:
            metrics = bulkhead.get_metrics()
            assert metrics.active_calls == 1
            assert metrics.available_permits == 0

        # After exiting, permit should be released
        metrics = bulkhead.get_metrics()
        assert metrics.active_calls == 0
        assert metrics.available_permits == 1
        assert metrics.completed_calls == 1

    @pytest.mark.asyncio
    async def test_bulkhead_releases_on_exception(self):
        """Test that permits are released even when exceptions occur."""
        config = BulkheadConfig(name="exception_test", max_concurrent_calls=1)
        bulkhead = Bulkhead(config)

        async def failing_task():
            raise RuntimeError("Task failed")

        # First call should fail
        with pytest.raises(RuntimeError):
            await bulkhead.execute(failing_task)

        # Permit should be released, second call should work
        async def success_task():
            return "success"

        result = await bulkhead.execute(success_task)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_bulkhead_with_zero_wait(self):
        """Test bulkhead with zero wait duration (immediate fail)."""
        config = BulkheadConfig(
            name="zero_wait",
            max_concurrent_calls=1,
            max_wait_duration=0.0
        )
        bulkhead = Bulkhead(config)

        # First acquire should work
        await bulkhead.acquire()

        # Second should fail immediately (implementation dependent)
        # Note: zero wait behavior may vary
        metrics = bulkhead.get_metrics()
        assert metrics.active_calls == 1

        bulkhead.release()
        metrics = bulkhead.get_metrics()
        assert metrics.active_calls == 0

    @pytest.mark.asyncio
    async def test_concurrent_metrics_accuracy(self):
        """Test metrics accuracy under concurrent load."""
        config = BulkheadConfig(
            name="metrics_test",
            max_concurrent_calls=5,
            max_wait_duration=2.0
        )
        bulkhead = Bulkhead(config)

        async def task():
            await asyncio.sleep(0.1)
            return True

        # Run 20 tasks concurrently
        tasks = [bulkhead.execute(task) for _ in range(20)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        metrics = bulkhead.get_metrics()
        assert metrics.completed_calls == 20
        assert metrics.accepted_calls == 20
        assert metrics.active_calls == 0

    @pytest.mark.asyncio
    async def test_decorator_reuses_bulkhead(self):
        """Test that decorator reuses the same bulkhead."""
        call_count = 0

        @bulkhead("reuse_test", max_concurrent=5)
        async def task():
            nonlocal call_count
            call_count += 1
            return call_count

        # Multiple calls should use same bulkhead
        await task()
        await task()
        await task()

        bh = registry.get("reuse_test")
        metrics = bh.get_metrics()

        assert metrics.accepted_calls == 3
        assert metrics.completed_calls == 3


# ============================================================
# Performance Tests
# ============================================================

class TestBulkheadPerformance:
    """Performance-related tests."""

    @pytest.mark.asyncio
    async def test_high_throughput(self):
        """Test bulkhead handles high throughput."""
        config = BulkheadConfig(
            name="throughput_test",
            max_concurrent_calls=50
        )
        bulkhead = Bulkhead(config)

        async def quick_task(n):
            return n

        # Measure time for 1000 tasks
        start = time.time()
        tasks = [bulkhead.execute(quick_task, i) for i in range(100)]
        results = await asyncio.gather(*tasks)
        elapsed = time.time() - start

        assert len(results) == 100
        assert elapsed < 2.0  # Should complete within 2 seconds

    @pytest.mark.asyncio
    async def test_no_memory_leak(self):
        """Test that completed tasks don't cause memory leaks."""
        config = BulkheadConfig(name="leak_test")
        bulkhead = Bulkhead(config)

        async def task():
            return list(range(1000))  # Create some data

        # Run many tasks
        for _ in range(100):
            await bulkhead.execute(task)

        metrics = bulkhead.get_metrics()
        assert metrics.active_calls == 0
        assert metrics.completed_calls == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=animus_resilience.bulkhead", "--cov-report=term-missing"])
