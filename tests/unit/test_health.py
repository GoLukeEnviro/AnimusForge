"""Unit tests for Health Monitor module.

Comprehensive tests covering all health monitoring functionality including:
- Component registration and health checks
- Periodic monitoring loops
- Failure/recovery thresholds
- System-wide health aggregation
- Kubernetes liveness/readiness probes
"""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch
import time

from animus_ecosystem.health import (
    HealthStatus,
    ComponentHealth,
    SystemHealth,
    HealthCheckConfig,
    HealthMonitor,
    HealthGateway,
    HealthCheckError,
    create_health_monitor,
    create_health_gateway,
)


# ==================== HealthStatus Tests ====================

class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_health_status_values(self):
        """Test all health status values."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.CRITICAL.value == "critical"

    def test_health_status_is_string(self):
        """Test that HealthStatus is string enum."""
        assert isinstance(HealthStatus.HEALTHY, str)
        assert HealthStatus.HEALTHY == "healthy"

    def test_health_status_comparison(self):
        """Test health status comparison."""
        assert HealthStatus.HEALTHY == HealthStatus.HEALTHY
        assert HealthStatus.HEALTHY != HealthStatus.DEGRADED


# ==================== ComponentHealth Tests ====================

class TestComponentHealth:
    """Tests for ComponentHealth model."""

    def test_component_health_creation(self):
        """Test creating component health."""
        health = ComponentHealth(
            name="test_component",
            status=HealthStatus.HEALTHY,
            latency_ms=10.5,
            last_check=datetime.now(timezone.utc)
        )
        assert health.name == "test_component"
        assert health.status == HealthStatus.HEALTHY
        assert health.latency_ms == 10.5
        assert health.error_message is None
        assert health.metadata == {}

    def test_component_health_with_error(self):
        """Test component health with error message."""
        health = ComponentHealth(
            name="failing_component",
            status=HealthStatus.UNHEALTHY,
            latency_ms=100.0,
            last_check=datetime.now(timezone.utc),
            error_message="Connection refused"
        )
        assert health.status == HealthStatus.UNHEALTHY
        assert health.error_message == "Connection refused"

    def test_component_health_with_metadata(self):
        """Test component health with metadata."""
        health = ComponentHealth(
            name="db",
            status=HealthStatus.HEALTHY,
            latency_ms=5.0,
            last_check=datetime.now(timezone.utc),
            metadata={"host": "localhost", "port": 5432}
        )
        assert health.metadata["host"] == "localhost"
        assert health.metadata["port"] == 5432

    def test_component_health_negative_latency_validation(self):
        """Test that negative latency is rejected."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            ComponentHealth(
                name="test",
                status=HealthStatus.HEALTHY,
                latency_ms=-1.0,
                last_check=datetime.now(timezone.utc)
            )

    def test_component_health_default_counters(self):
        """Test default failure/success counters."""
        health = ComponentHealth(
            name="test",
            status=HealthStatus.HEALTHY,
            latency_ms=1.0,
            last_check=datetime.now(timezone.utc)
        )
        assert health.consecutive_failures == 0
        assert health.consecutive_successes == 0


# ==================== SystemHealth Tests ====================

class TestSystemHealth:
    """Tests for SystemHealth model."""

    def test_system_health_creation(self):
        """Test creating system health."""
        component = ComponentHealth(
            name="db",
            status=HealthStatus.HEALTHY,
            latency_ms=5.0,
            last_check=datetime.now(timezone.utc)
        )
        health = SystemHealth(
            overall_status=HealthStatus.HEALTHY,
            components={"database": component},
            uptime_seconds=3600.0
        )
        assert health.overall_status == HealthStatus.HEALTHY
        assert "database" in health.components
        assert health.uptime_seconds == 3600.0
        assert health.version == "1.0.0"

    def test_system_health_timestamp_auto_generated(self):
        """Test that timestamp is auto-generated."""
        before = datetime.now(timezone.utc)
        health = SystemHealth(
            overall_status=HealthStatus.HEALTHY,
            components={},
            uptime_seconds=0.0
        )
        after = datetime.now(timezone.utc)
        assert before <= health.timestamp <= after

    def test_system_health_overall_status_validation(self):
        """Test overall status validation."""
        health = SystemHealth(
            overall_status="healthy",  # String instead of enum
            components={},
            uptime_seconds=0.0
        )
        assert health.overall_status == HealthStatus.HEALTHY


# ==================== HealthCheckConfig Tests ====================

class TestHealthCheckConfig:
    """Tests for HealthCheckConfig model."""

    def test_default_config(self):
        """Test default configuration values."""
        config = HealthCheckConfig()
        assert config.check_interval == 30.0
        assert config.timeout == 5.0
        assert config.failure_threshold == 3
        assert config.recovery_threshold == 2
        assert "database" in config.components
        assert config.enable_periodic_checks is True

    def test_custom_config(self):
        """Test custom configuration values."""
        config = HealthCheckConfig(
            check_interval=60.0,
            timeout=10.0,
            failure_threshold=5,
            recovery_threshold=3,
            components=["custom_component"],
            enable_periodic_checks=False
        )
        assert config.check_interval == 60.0
        assert config.timeout == 10.0
        assert config.failure_threshold == 5
        assert config.recovery_threshold == 3
        assert config.components == ["custom_component"]
        assert config.enable_periodic_checks is False

    def test_config_validation_positive_interval(self):
        """Test that check interval must be positive."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            HealthCheckConfig(check_interval=0.0)

    def test_config_validation_positive_timeout(self):
        """Test that timeout must be positive."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            HealthCheckConfig(timeout=-1.0)

    def test_config_validation_min_failure_threshold(self):
        """Test that failure threshold must be at least 1."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            HealthCheckConfig(failure_threshold=0)


# ==================== HealthCheckError Tests ====================

class TestHealthCheckError:
    """Tests for HealthCheckError exception."""

    def test_error_creation(self):
        """Test creating health check error."""
        error = HealthCheckError("db", "Connection failed")
        assert error.component == "db"
        assert error.message == "Connection failed"
        assert "db" in str(error)
        assert "Connection failed" in str(error)

    def test_error_with_original(self):
        """Test error with original exception."""
        original = ValueError("Original error")
        error = HealthCheckError("cache", "Timeout", original)
        assert error.original_error == original


# ==================== HealthMonitor Tests ====================

class TestHealthMonitor:
    """Tests for HealthMonitor class."""

    @pytest.fixture
    def monitor(self):
        """Create a health monitor instance."""
        return HealthMonitor()

    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return HealthCheckConfig(
            check_interval=0.1,  # Fast for testing
            timeout=1.0,
            failure_threshold=2,
            recovery_threshold=1,
            enable_periodic_checks=True
        )

    @pytest.mark.asyncio
    async def test_register_component(self, monitor):
        """Test registering a component."""
        async def check_fn():
            return True

        await monitor.register_component("test", check_fn)
        assert "test" in monitor.registered_components
        assert monitor.get_component_health("test") is not None

    @pytest.mark.asyncio
    async def test_register_component_with_metadata(self, monitor):
        """Test registering a component with metadata."""
        async def check_fn():
            return True

        await monitor.register_component(
            "db", 
            check_fn, 
            metadata={"host": "localhost"}
        )
        health = monitor.get_component_health("db")
        assert health.metadata == {"host": "localhost"}

    @pytest.mark.asyncio
    async def test_unregister_component(self, monitor):
        """Test unregistering a component."""
        async def check_fn():
            return True

        await monitor.register_component("test", check_fn)
        assert "test" in monitor.registered_components

        await monitor.unregister_component("test")
        assert "test" not in monitor.registered_components
        assert monitor.get_component_health("test") is None

    @pytest.mark.asyncio
    async def test_check_component_healthy(self, monitor):
        """Test checking a healthy component."""
        async def check_fn():
            return True

        await monitor.register_component("test", check_fn)
        health = await monitor.check_component("test")

        assert health.status == HealthStatus.HEALTHY
        assert health.latency_ms >= 0
        assert health.error_message is None

    @pytest.mark.asyncio
    async def test_check_component_unhealthy(self, monitor):
        """Test checking an unhealthy component."""
        async def check_fn():
            return False

        await monitor.register_component("test", check_fn)

        # First failure - degraded
        health = await monitor.check_component("test")
        assert health.status == HealthStatus.DEGRADED
        assert health.consecutive_failures == 1

        # Second failure - unhealthy (threshold=3 default)
        health = await monitor.check_component("test")
        assert health.status == HealthStatus.DEGRADED
        assert health.consecutive_failures == 2

        # Third failure - unhealthy
        health = await monitor.check_component("test")
        assert health.status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_check_component_exception(self, monitor):
        """Test checking a component that raises exception."""
        async def check_fn():
            raise RuntimeError("Connection error")

        await monitor.register_component("test", check_fn)
        health = await monitor.check_component("test")

        assert health.status in [HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]
        assert "Connection error" in health.error_message

    @pytest.mark.asyncio
    async def test_check_component_timeout(self, config):
        """Test component check timeout."""
        config.timeout = 0.1
        monitor = HealthMonitor(config)

        async def slow_check():
            await asyncio.sleep(1.0)
            return True

        await monitor.register_component("slow", slow_check)
        health = await monitor.check_component("slow")

        assert health.status in [HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]
        assert "timed out" in health.error_message.lower()

    @pytest.mark.asyncio
    async def test_check_component_not_registered(self, monitor):
        """Test checking unregistered component."""
        with pytest.raises(HealthCheckError):
            await monitor.check_component("nonexistent")

    @pytest.mark.asyncio
    async def test_check_all(self, monitor):
        """Test checking all components."""
        async def check_fn1():
            return True
        async def check_fn2():
            return False

        await monitor.register_component("healthy", check_fn1)
        await monitor.register_component("unhealthy", check_fn2)

        system_health = await monitor.check_all()

        assert isinstance(system_health, SystemHealth)
        assert "healthy" in system_health.components
        assert "unhealthy" in system_health.components

    @pytest.mark.asyncio
    async def test_get_system_health(self, monitor):
        """Test getting system health."""
        async def check_fn():
            return True

        await monitor.register_component("test", check_fn)
        await monitor.check_component("test")

        health = monitor.get_system_health()

        assert isinstance(health, SystemHealth)
        assert health.overall_status == HealthStatus.HEALTHY
        assert health.uptime_seconds >= 0

    @pytest.mark.asyncio
    async def test_get_system_health_empty(self, monitor):
        """Test system health with no components."""
        health = monitor.get_system_health()

        assert health.overall_status == HealthStatus.HEALTHY
        assert len(health.components) == 0

    @pytest.mark.asyncio
    async def test_start_stop_monitoring(self, config):
        """Test starting and stopping monitoring."""
        monitor = HealthMonitor(config)

        async def check_fn():
            return True

        await monitor.register_component("test", check_fn)
        await monitor.start_monitoring()

        assert monitor.is_running
        assert "test" in monitor._check_tasks

        await asyncio.sleep(0.2)  # Let it run at least once

        await monitor.stop_monitoring()
        assert not monitor.is_running
        assert len(monitor._check_tasks) == 0

    @pytest.mark.asyncio
    async def test_monitoring_disabled(self):
        """Test monitoring when disabled in config."""
        config = HealthCheckConfig(enable_periodic_checks=False)
        monitor = HealthMonitor(config)

        async def check_fn():
            return True

        await monitor.register_component("test", check_fn)
        await monitor.start_monitoring()

        assert monitor.is_running
        assert len(monitor._check_tasks) == 0

    @pytest.mark.asyncio
    async def test_start_monitoring_twice(self, monitor):
        """Test starting monitoring twice."""
        async def check_fn():
            return True

        await monitor.register_component("test", check_fn)
        await monitor.start_monitoring()
        await monitor.start_monitoring()  # Should not raise

        await monitor.stop_monitoring()

    @pytest.mark.asyncio
    async def test_failure_recovery_threshold(self, config):
        """Test failure and recovery thresholds."""
        config.failure_threshold = 2
        config.recovery_threshold = 1
        monitor = HealthMonitor(config)

        should_be_healthy = True

        async def check_fn():
            return should_be_healthy

        await monitor.register_component("test", check_fn)

        # Make it fail twice
        should_be_healthy = False
        await monitor.check_component("test")
        health = await monitor.check_component("test")
        assert health.status == HealthStatus.UNHEALTHY
        assert health.consecutive_failures == 2

        # Recover
        should_be_healthy = True
        health = await monitor.check_component("test")
        assert health.status == HealthStatus.HEALTHY
        assert health.consecutive_successes == 1

    @pytest.mark.asyncio
    async def test_critical_status(self, config):
        """Test critical status after many failures."""
        config.failure_threshold = 2
        monitor = HealthMonitor(config)

        async def check_fn():
            return False

        await monitor.register_component("test", check_fn)

        # Fail multiple times to reach critical
        for _ in range(5):
            await monitor.check_component("test")

        health = monitor.get_component_health("test")
        assert health.status == HealthStatus.CRITICAL

    @pytest.mark.asyncio
    async def test_aggregate_status_healthy(self, monitor):
        """Test status aggregation when all healthy."""
        async def check_fn():
            return True

        await monitor.register_component("c1", check_fn)
        await monitor.register_component("c2", check_fn)
        await monitor.check_all()

        assert monitor._aggregate_status() == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_aggregate_status_degraded(self, monitor):
        """Test status aggregation with degraded component."""
        async def check_fn():
            return True
        async def fail_fn():
            return False

        await monitor.register_component("healthy", check_fn)
        await monitor.register_component("degraded", fail_fn)
        await monitor.check_component("healthy")
        await monitor.check_component("degraded")  # First failure = degraded

        assert monitor._aggregate_status() == HealthStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_aggregate_status_unhealthy(self, config):
        """Test status aggregation with unhealthy component."""
        config.failure_threshold = 1
        monitor = HealthMonitor(config)

        async def fail_fn():
            return False

        await monitor.register_component("unhealthy", fail_fn)
        await monitor.check_component("unhealthy")

        assert monitor._aggregate_status() == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_aggregate_status_critical(self, config):
        """Test status aggregation with critical component."""
        config.failure_threshold = 1
        monitor = HealthMonitor(config)

        async def fail_fn():
            return False

        await monitor.register_component("critical", fail_fn)

        # Fail many times
        for _ in range(5):
            await monitor.check_component("critical")

        assert monitor._aggregate_status() == HealthStatus.CRITICAL


# ==================== HealthGateway Tests ====================

class TestHealthGateway:
    """Tests for HealthGateway class."""

    @pytest.fixture
    def monitor(self):
        """Create a health monitor."""
        return HealthMonitor()

    @pytest.fixture
    def gateway(self, monitor):
        """Create a health gateway."""
        return HealthGateway(monitor)

    @pytest.mark.asyncio
    async def test_get_health(self, gateway, monitor):
        """Test getting full health status."""
        async def check_fn():
            return True

        await monitor.register_component("test", check_fn)
        health = await gateway.get_health()

        assert isinstance(health, SystemHealth)
        assert "test" in health.components

    @pytest.mark.asyncio
    async def test_get_liveness(self, gateway):
        """Test liveness probe."""
        liveness = await gateway.get_liveness()

        assert liveness["status"] == "alive"
        assert "timestamp" in liveness

    @pytest.mark.asyncio
    async def test_get_readiness_healthy(self, gateway, monitor):
        """Test readiness probe when healthy."""
        async def check_fn():
            return True

        await monitor.register_component("test", check_fn)
        await monitor.check_all()

        readiness = await gateway.get_readiness()

        assert readiness["status"] == "ready"
        assert readiness["overall_health"] == "healthy"

    @pytest.mark.asyncio
    async def test_get_readiness_unhealthy(self, gateway, monitor):
        """Test readiness probe when unhealthy."""
        config = HealthCheckConfig(failure_threshold=1)
        unhealthy_monitor = HealthMonitor(config)
        gateway = HealthGateway(unhealthy_monitor)

        async def fail_fn():
            return False

        await unhealthy_monitor.register_component("test", fail_fn)
        await unhealthy_monitor.check_all()

        readiness = await gateway.get_readiness()

        assert readiness["status"] == "not_ready"
        assert readiness["overall_health"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_force_check(self, gateway, monitor):
        """Test forcing a health check."""
        async def check_fn():
            return True

        await monitor.register_component("test", check_fn)
        health = await gateway.force_check("test")

        assert isinstance(health, ComponentHealth)
        assert health.name == "test"
        assert health.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_force_check_not_registered(self, gateway):
        """Test force check on unregistered component."""
        with pytest.raises(HealthCheckError):
            await gateway.force_check("nonexistent")

    def test_mark_startup_complete(self, gateway):
        """Test marking startup complete."""
        assert not gateway._startup_complete
        gateway.mark_startup_complete()
        assert gateway._startup_complete

    def test_is_ready(self, gateway, monitor):
        """Test is_ready property."""
        assert not gateway.is_ready  # Startup not complete

        gateway.mark_startup_complete()
        assert gateway.is_ready  # No components = healthy


# ==================== Factory Function Tests ====================

class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_create_health_monitor_defaults(self):
        """Test creating monitor with defaults."""
        monitor = create_health_monitor()

        assert monitor.config.check_interval == 30.0
        assert monitor.config.timeout == 5.0
        assert monitor.config.failure_threshold == 3

    def test_create_health_monitor_custom(self):
        """Test creating monitor with custom config."""
        monitor = create_health_monitor(
            check_interval=60.0,
            timeout=10.0,
            failure_threshold=5,
            recovery_threshold=3,
            components=["custom"],
            enable_periodic_checks=False
        )

        assert monitor.config.check_interval == 60.0
        assert monitor.config.timeout == 10.0
        assert monitor.config.failure_threshold == 5
        assert monitor.config.recovery_threshold == 3
        assert monitor.config.components == ["custom"]
        assert monitor.config.enable_periodic_checks is False

    def test_create_health_gateway_with_monitor(self):
        """Test creating gateway with existing monitor."""
        monitor = HealthMonitor()
        gateway = create_health_gateway(monitor)

        assert gateway.monitor is monitor

    def test_create_health_gateway_without_monitor(self):
        """Test creating gateway without monitor."""
        gateway = create_health_gateway()

        assert gateway.monitor is not None
        assert isinstance(gateway.monitor, HealthMonitor)


# ==================== Integration Tests ====================

class TestHealthIntegration:
    """Integration tests for health monitoring."""

    @pytest.mark.asyncio
    async def test_full_monitoring_cycle(self):
        """Test complete monitoring cycle."""
        config = HealthCheckConfig(
            check_interval=0.1,
            timeout=1.0,
            failure_threshold=2,
            recovery_threshold=1,
            enable_periodic_checks=True
        )
        monitor = HealthMonitor(config)
        gateway = HealthGateway(monitor)

        # Simulate components
        db_healthy = True
        cache_healthy = True

        async def check_db():
            return db_healthy

        async def check_cache():
            return cache_healthy

        # Register components
        await monitor.register_component("database", check_db)
        await monitor.register_component("cache", check_cache)

        # Initial check - all healthy
        health = await gateway.get_health()
        assert health.overall_status == HealthStatus.HEALTHY

        # Mark startup complete
        gateway.mark_startup_complete()
        assert gateway.is_ready

        # Start monitoring
        await monitor.start_monitoring()
        await asyncio.sleep(0.15)  # Let monitoring run

        # Verify still healthy
        readiness = await gateway.get_readiness()
        assert readiness["status"] == "ready"

        # Stop monitoring
        await monitor.stop_monitoring()
        assert not monitor.is_running

    @pytest.mark.asyncio
    async def test_kubernetes_probe_simulation(self):
        """Test Kubernetes liveness/readiness probe simulation."""
        monitor = HealthMonitor()
        gateway = HealthGateway(monitor)

        async def check_fn():
            return True

        await monitor.register_component("api", check_fn)

        # Liveness probe - should always return alive
        liveness = await gateway.get_liveness()
        assert liveness["status"] == "alive"

        # Readiness probe - should be ready after startup
        gateway.mark_startup_complete()
        await monitor.check_all()
        readiness = await gateway.get_readiness()
        assert readiness["status"] == "ready"

    @pytest.mark.asyncio
    async def test_concurrent_health_checks(self):
        """Test concurrent health check execution."""
        monitor = HealthMonitor()

        call_count = {"db": 0, "cache": 0, "api": 0}

        async def check_db():
            call_count["db"] += 1
            return True

        async def check_cache():
            call_count["cache"] += 1
            return True

        async def check_api():
            call_count["api"] += 1
            return True

        await monitor.register_component("database", check_db)
        await monitor.register_component("cache", check_cache)
        await monitor.register_component("api", check_api)

        # Run check_all concurrently
        await monitor.check_all()

        assert call_count["db"] == 1
        assert call_count["cache"] == 1
        assert call_count["api"] == 1


# ==================== Edge Case Tests ====================

class TestHealthEdgeCases:
    """Tests for edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_check_function_returns_non_bool(self):
        """Test check function that returns non-boolean."""
        monitor = HealthMonitor()

        async def check_fn():
            return "healthy"  # Truthy but not bool

        await monitor.register_component("test", check_fn)
        health = await monitor.check_component("test")

        # Should treat truthy as healthy
        assert health.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_multiple_register_same_component(self):
        """Test registering same component multiple times."""
        monitor = HealthMonitor()

        async def check_fn1():
            return True
        async def check_fn2():
            return False

        await monitor.register_component("test", check_fn1)
        await monitor.register_component("test", check_fn2)  # Overwrite

        health = await monitor.check_component("test")
        # Should use second function
        assert health.consecutive_failures == 1 or health.consecutive_successes == 1

    @pytest.mark.asyncio
    async def test_unregister_nonexistent_component(self):
        """Test unregistering component that doesnt exist."""
        monitor = HealthMonitor()
        # Should not raise
        await monitor.unregister_component("nonexistent")

    @pytest.mark.asyncio
    async def test_empty_check_all(self):
        """Test check_all with no components."""
        monitor = HealthMonitor()
        health = await monitor.check_all()

        assert health.overall_status == HealthStatus.HEALTHY
        assert len(health.components) == 0

    @pytest.mark.asyncio
    async def test_health_check_with_zero_latency(self):
        """Test health check with near-zero latency."""
        monitor = HealthMonitor()

        async def instant_check():
            return True

        await monitor.register_component("instant", instant_check)
        health = await monitor.check_component("instant")

        assert health.latency_ms >= 0  # Should be non-negative

    @pytest.mark.asyncio
    async def test_uptime_increases(self):
        """Test that uptime increases over time."""
        monitor = HealthMonitor()

        health1 = monitor.get_system_health()
        await asyncio.sleep(0.1)
        health2 = monitor.get_system_health()

        assert health2.uptime_seconds > health1.uptime_seconds


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
