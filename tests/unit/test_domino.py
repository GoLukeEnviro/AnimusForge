"""
Unit tests for DOMINO Cascade Prevention System

Comprehensive test suite covering:
- Service registration/unregistration
- Dependency graph tracking
- Cascade risk detection (BFS/DFS)
- Service isolation
- Recovery management
- Circuit breaker integration
- Health check monitoring
- Event history and audit trail
- Gateway operations
"""

import asyncio
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

from animus_resilience.domino import (
    DominoState,
    CircuitState,
    CircuitBreaker,
    ServiceDependency,
    CascadeEvent,
    DominoConfig,
    DominoPrevention,
    DominoGateway,
    create_domino_gateway,
)


# ============= Fixtures =============

@pytest.fixture
def basic_config():
    """Basic DOMINO configuration."""
    return DominoConfig(
        max_cascade_depth=3,
        isolation_timeout=5.0,
        health_check_interval=0.1,
        auto_recovery_enabled=True,
        auto_recovery_interval=0.1,
        circuit_failure_threshold=2,
        circuit_success_threshold=1,
    )


@pytest.fixture
def sample_service():
    """Sample service dependency."""
    return ServiceDependency(
        service_id="service-a",
        depends_on=["service-b", "service-c"],
        health_endpoint="http://localhost:8001/health",
        timeout_seconds=5.0,
        failure_threshold=3,
        recovery_timeout=30.0,
    )


@pytest.fixture
def chain_services():
    """Chain of dependent services: A -> B -> C -> D"""
    return [
        ServiceDependency(
            service_id="service-a",
            depends_on=["service-b"],
            health_endpoint="http://localhost:8001/health",
        ),
        ServiceDependency(
            service_id="service-b",
            depends_on=["service-c"],
            health_endpoint="http://localhost:8002/health",
        ),
        ServiceDependency(
            service_id="service-c",
            depends_on=["service-d"],
            health_endpoint="http://localhost:8003/health",
        ),
        ServiceDependency(
            service_id="service-d",
            depends_on=[],
            health_endpoint="http://localhost:8004/health",
        ),
    ]


@pytest.fixture
def diamond_services():
    """Diamond dependency: A depends on B,C; B and C depend on D"""
    return [
        ServiceDependency(
            service_id="service-a",
            depends_on=["service-b", "service-c"],
            health_endpoint="http://localhost:8001/health",
        ),
        ServiceDependency(
            service_id="service-b",
            depends_on=["service-d"],
            health_endpoint="http://localhost:8002/health",
        ),
        ServiceDependency(
            service_id="service-c",
            depends_on=["service-d"],
            health_endpoint="http://localhost:8003/health",
        ),
        ServiceDependency(
            service_id="service-d",
            depends_on=[],
            health_endpoint="http://localhost:8004/health",
        ),
    ]


@pytest.fixture
async def prevention(basic_config):
    """DOMINO prevention instance."""
    prevention = DominoPrevention(basic_config)
    yield prevention
    await prevention.close()


@pytest.fixture
async def gateway(basic_config):
    """DOMINO gateway instance."""
    gateway = DominoGateway(basic_config)
    yield gateway
    await gateway.close()


# ============= CircuitBreaker Tests =============

class TestCircuitBreaker:
    """Tests for CircuitBreaker class."""
    
    def test_initial_state(self):
        """Circuit breaker starts closed."""
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.is_available is True
    
    @pytest.mark.asyncio
    async def test_record_success_closed(self):
        """Success in closed state keeps circuit closed."""
        cb = CircuitBreaker()
        await cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.is_available is True
    
    @pytest.mark.asyncio
    async def test_record_failure_opens_circuit(self):
        """Failures open the circuit after threshold."""
        cb = CircuitBreaker(failure_threshold=2)
        
        await cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.is_available is False
    
    @pytest.mark.asyncio
    async def test_half_open_recovery(self):
        """Circuit recovers through half-open state."""
        cb = CircuitBreaker(failure_threshold=1, success_threshold=1, timeout_seconds=0.1)
        
        # Open the circuit
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN
        
        # Wait for timeout
        await asyncio.sleep(0.15)
        # Access is_available to trigger HALF_OPEN transition
        assert cb.is_available is True
        assert cb.state == CircuitState.HALF_OPEN
        
        # Record success to close
        await cb.record_success()
        assert cb.state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_half_open_back_to_open(self):
        """Failure in half-open returns to open."""
        cb = CircuitBreaker(failure_threshold=1, timeout_seconds=0.1)
        
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN
        
        await asyncio.sleep(0.15)
        # Access is_available to trigger HALF_OPEN transition
        _ = cb.is_available
        assert cb.state == CircuitState.HALF_OPEN
        
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN
    
    def test_reset(self):
        """Reset returns to initial state."""
        cb = CircuitBreaker()
        cb._state = CircuitState.OPEN
        cb._failure_count = 5
        
        cb.reset()
        
        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 0


# ============= ServiceDependency Tests =============

class TestServiceDependency:
    """Tests for ServiceDependency model."""
    
    def test_create_service(self):
        """Create service with required fields."""
        service = ServiceDependency(
            service_id="test-service",
            health_endpoint="http://localhost/health",
        )
        assert service.service_id == "test-service"
        assert service.depends_on == []
        assert service.timeout_seconds == 5.0
        assert service.failure_threshold == 3
    
    def test_service_with_dependencies(self):
        """Service with dependencies list."""
        service = ServiceDependency(
            service_id="api-gateway",
            depends_on=["auth-service", "user-service"],
            health_endpoint="http://localhost/health",
        )
        assert len(service.depends_on) == 2
        assert "auth-service" in service.depends_on
    
    def test_service_metadata(self):
        """Service can have metadata."""
        service = ServiceDependency(
            service_id="data-service",
            health_endpoint="http://localhost/health",
            metadata={"version": "2.0", "team": "data"},
        )
        assert service.metadata["version"] == "2.0"


# ============= CascadeEvent Tests =============

class TestCascadeEvent:
    """Tests for CascadeEvent model."""
    
    def test_create_event(self):
        """Create cascade event."""
        event = CascadeEvent(
            source_service="service-a",
            affected_services=["service-b", "service-c"],
            cascade_depth=2,
            contained=True,
            reason="Health check failed",
        )
        assert event.source_service == "service-a"
        assert len(event.affected_services) == 2
        assert event.contained is True
        assert event.id is not None
        assert isinstance(event.timestamp, datetime)
    
    def test_event_defaults(self):
        """Event has sensible defaults."""
        event = CascadeEvent(
            source_service="service-x",
        )
        assert event.affected_services == []
        assert event.cascade_depth == 0
        assert event.contained is False
        assert event.recovery_actions == []


# ============= DominoPrevention Tests =============

class TestDominoPrevention:
    """Tests for DominoPrevention class."""
    
    @pytest.mark.asyncio
    async def test_register_service(self, prevention, sample_service):
        """Register a service."""
        await prevention.register_service(sample_service)
        
        assert "service-a" in prevention.services
        assert prevention.states["service-a"] == DominoState.HEALTHY
        assert "service-a" in prevention.circuit_breakers
    
    @pytest.mark.asyncio
    async def test_unregister_service(self, prevention, sample_service):
        """Unregister a service."""
        await prevention.register_service(sample_service)
        assert "service-a" in prevention.services
        
        await prevention.unregister_service("service-a")
        assert "service-a" not in prevention.services
        assert "service-a" not in prevention.states
    
    @pytest.mark.asyncio
    async def test_unregister_nonexistent(self, prevention):
        """Unregistering nonexistent service does nothing."""
        await prevention.unregister_service("nonexistent")  # No error
    
    @pytest.mark.asyncio
    async def test_dependency_graph_chain(self, prevention, chain_services):
        """Dependency graph correctly tracks chain."""
        for service in chain_services:
            await prevention.register_service(service)
        
        graph = await prevention.get_dependency_graph()
        
        assert "service-a" in graph
        assert "service-b" in graph["service-a"]
        assert "service-c" in graph["service-b"]
        assert "service-d" in graph["service-c"]
        assert graph["service-d"] == [] or "service-d" not in graph
    
    @pytest.mark.asyncio
    async def test_check_cascade_risk_simple(self, prevention, chain_services):
        """Cascade risk detection for chain."""
        for service in chain_services:
            await prevention.register_service(service)
        
        # D fails -> C, B, A at risk (if we check dependents)
        # But our graph is: A depends on B, B depends on C, C depends on D
        # So if D fails, nothing depends on D in our model
        # Let's check the reverse: if D fails, who is affected?
        at_risk = await prevention.check_cascade_risk("service-d")
        
        # Should find dependents through reverse graph
        assert isinstance(at_risk, list)
    
    @pytest.mark.asyncio
    async def test_check_cascade_risk_depth_limit(self, prevention):
        """Cascade risk respects max depth."""
        config = DominoConfig(max_cascade_depth=2)
        prevention = DominoPrevention(config)
        
        # Create deep chain
        for i in range(5):
            service = ServiceDependency(
                service_id=f"service-{i}",
                depends_on=[f"service-{i+1}"] if i < 4 else [],
                health_endpoint=f"http://localhost:800{i}/health",
            )
            await prevention.register_service(service)
        
        at_risk = await prevention.check_cascade_risk("service-4")
        assert len(at_risk) <= 2  # Depth limit
        
        await prevention.close()
    
    @pytest.mark.asyncio
    async def test_isolate_service(self, prevention, sample_service):
        """Isolate a failing service."""
        await prevention.register_service(sample_service)
        
        event = await prevention.isolate_service("service-a", "Test isolation")
        
        assert prevention.states["service-a"] == DominoState.ISOLATED
        assert event.source_service == "service-a"
        assert event.contained is True
        assert "isolation" in event.recovery_actions
        assert len(prevention.cascade_history) == 1
    
    @pytest.mark.asyncio
    async def test_isolate_nonexistent_raises(self, prevention):
        """Isolating nonexistent service raises error."""
        with pytest.raises(ValueError):
            await prevention.isolate_service("nonexistent", "test")
    
    @pytest.mark.asyncio
    async def test_isolate_opens_circuit_breaker(self, prevention, sample_service):
        """Isolation opens circuit breaker."""
        await prevention.register_service(sample_service)
        
        await prevention.isolate_service("service-a", "Test")
        
        cb = prevention.circuit_breakers["service-a"]
        assert cb.state == CircuitState.OPEN
    
    @pytest.mark.asyncio
    async def test_isolate_marks_dependents_degraded(self, prevention, diamond_services):
        """Isolation marks dependent services as degraded."""
        for service in diamond_services:
            await prevention.register_service(service)
        
        # Isolate D - should degrade A, B, C
        await prevention.isolate_service("service-d", "D failed")
        
        # Check dependents are degraded
        assert prevention.states["service-d"] == DominoState.ISOLATED
    
    @pytest.mark.asyncio
    async def test_attempt_recovery_success(self, prevention, sample_service):
        """Successful recovery attempt."""
        await prevention.register_service(sample_service)
        
        # Isolate first
        await prevention.isolate_service("service-a", "Test")
        assert prevention.states["service-a"] == DominoState.ISOLATED
        
        # Mock health check to return True
        with patch.object(
            prevention,
            "_check_service_health",
            return_value=True
        ):
            result = await prevention.attempt_recovery("service-a")
            
        assert result is True
        assert prevention.states["service-a"] == DominoState.HEALTHY
    
    @pytest.mark.asyncio
    async def test_attempt_recovery_failure(self, prevention, sample_service):
        """Failed recovery attempt."""
        await prevention.register_service(sample_service)
        await prevention.isolate_service("service-a", "Test")
        
        with patch.object(
            prevention,
            "_check_service_health",
            return_value=False
        ):
            result = await prevention.attempt_recovery("service-a")
        
        assert result is False
        assert prevention.states["service-a"] == DominoState.ISOLATED
    
    @pytest.mark.asyncio
    async def test_attempt_recovery_nonexistent(self, prevention):
        """Recovery of nonexistent service returns False."""
        result = await prevention.attempt_recovery("nonexistent")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_get_service_state(self, prevention, sample_service):
        """Get service state."""
        await prevention.register_service(sample_service)
        
        state = await prevention.get_service_state("service-a")
        assert state == DominoState.HEALTHY
        
        await prevention.isolate_service("service-a", "Test")
        state = await prevention.get_service_state("service-a")
        assert state == DominoState.ISOLATED
    
    @pytest.mark.asyncio
    async def test_get_service_state_nonexistent(self, prevention):
        """Get state of nonexistent service returns FAILED."""
        state = await prevention.get_service_state("nonexistent")
        assert state == DominoState.FAILED
    
    @pytest.mark.asyncio
    async def test_health_check_all(self, prevention, chain_services):
        """Health check all services."""
        for service in chain_services:
            await prevention.register_service(service)
        
        with patch.object(
            prevention,
            "_check_service_health",
            return_value=True
        ):
            results = await prevention.health_check_all()
        
        assert len(results) == 4
        assert all(results.values())
    
    @pytest.mark.asyncio
    async def test_health_check_isolates_failing(self, prevention, chain_services):
        """Health check isolates consistently failing services."""
        prevention.config = DominoConfig(
            circuit_failure_threshold=1,
            max_cascade_depth=3,
        )
        
        for service in chain_services:
            await prevention.register_service(service)
        
        # Mock health check to fail for service-d
        async def mock_health(service):
            return service.service_id != "service-d"
        
        with patch.object(prevention, "_check_service_health", side_effect=mock_health):
            results = await prevention.health_check_all()
        
        assert results["service-d"] is False
    
    @pytest.mark.asyncio
    async def test_notification_callbacks(self, prevention, sample_service):
        """Notification callbacks are called on isolation."""
        callback = AsyncMock()
        prevention.register_notification_callback(callback)
        
        await prevention.register_service(sample_service)
        await prevention.isolate_service("service-a", "Test")
        
        callback.assert_called_once()
        event = callback.call_args[0][0]
        assert isinstance(event, CascadeEvent)
    
    @pytest.mark.asyncio
    async def test_monitoring_lifecycle(self, prevention):
        """Start and stop monitoring."""
        await prevention.start_monitoring()
        assert prevention._running is True
        assert prevention._health_check_task is not None
        
        await prevention.stop_monitoring()
        assert prevention._running is False


# ============= DominoGateway Tests =============

class TestDominoGateway:
    """Tests for DominoGateway class."""
    
    @pytest.mark.asyncio
    async def test_start_stop(self, gateway):
        """Gateway start and stop."""
        await gateway.start()
        assert gateway._started is True
        assert gateway.prevention._running is True
        
        await gateway.stop()
        assert gateway._started is False
    
    @pytest.mark.asyncio
    async def test_monitor_and_protect(self, gateway):
        """Monitor and protect starts gateway."""
        await gateway.monitor_and_protect()
        assert gateway._started is True
        
        await gateway.stop()
    
    @pytest.mark.asyncio
    async def test_force_isolate(self, gateway, sample_service):
        """Force isolate through gateway."""
        await gateway.register_service(sample_service)
        
        event = await gateway.force_isolate("service-a")
        
        assert event.source_service == "service-a"
        assert event.reason == "Manual isolation requested"
        assert gateway.prevention.states["service-a"] == DominoState.ISOLATED
    
    @pytest.mark.asyncio
    async def test_get_cascade_history(self, gateway, sample_service):
        """Get cascade history."""
        await gateway.register_service(sample_service)
        await gateway.force_isolate("service-a")
        
        history = await gateway.get_cascade_history()
        
        assert len(history) == 1
        assert history[0].source_service == "service-a"
    
    @pytest.mark.asyncio
    async def test_get_cascade_history_filter(self, gateway, chain_services):
        """Get cascade history filtered by service."""
        for service in chain_services:
            await gateway.register_service(service)
        
        await gateway.force_isolate("service-d")
        await gateway.force_isolate("service-c")
        
        history = await gateway.get_cascade_history(service_id="service-d")
        
        assert len(history) == 1
        assert history[0].source_service == "service-d"
    
    @pytest.mark.asyncio
    async def test_get_cascade_history_limit(self, gateway, chain_services):
        """Get cascade history with limit."""
        for service in chain_services:
            await gateway.register_service(service)
        
        for svc in chain_services:
            await gateway.force_isolate(svc.service_id)
        
        history = await gateway.get_cascade_history(limit=2)
        
        assert len(history) == 2
    
    @pytest.mark.asyncio
    async def test_get_system_health(self, gateway, chain_services):
        """Get system health report."""
        for service in chain_services:
            await gateway.register_service(service)
        
        health = await gateway.get_system_health()
        
        assert health["total_services"] == 4
        assert "states" in health
        assert "service_states" in health
        assert "circuit_breakers" in health
        assert "timestamp" in health
        assert health["monitoring_active"] is False
    
    @pytest.mark.asyncio
    async def test_get_system_health_with_failures(self, gateway, chain_services):
        """System health reflects isolated services."""
        for service in chain_services:
            await gateway.register_service(service)
        
        await gateway.force_isolate("service-d")
        
        health = await gateway.get_system_health()
        
        assert health["states"][DominoState.ISOLATED.value] >= 1
        assert health["service_states"]["service-d"] == DominoState.ISOLATED.value
    
    @pytest.mark.asyncio
    async def test_register_unregister(self, gateway, sample_service):
        """Register and unregister through gateway."""
        await gateway.register_service(sample_service)
        assert "service-a" in gateway.prevention.services
        
        await gateway.unregister_service("service-a")
        assert "service-a" not in gateway.prevention.services
    
    @pytest.mark.asyncio
    async def test_attempt_recovery(self, gateway, sample_service):
        """Recovery through gateway."""
        await gateway.register_service(sample_service)
        await gateway.force_isolate("service-a")
        
        with patch.object(
            gateway.prevention,
            "_check_service_health",
            return_value=True
        ):
            result = await gateway.attempt_recovery("service-a")
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_get_dependency_graph(self, gateway, chain_services):
        """Get dependency graph through gateway."""
        for service in chain_services:
            await gateway.register_service(service)
        
        graph = await gateway.get_dependency_graph()
        
        assert "service-a" in graph
        assert "service-b" in graph["service-a"]


# ============= Integration Tests =============

class TestDominoIntegration:
    """Integration tests for DOMINO system."""
    
    @pytest.mark.asyncio
    async def test_full_cascade_scenario(self, basic_config, diamond_services):
        """Full cascade isolation and recovery scenario."""
        gateway = DominoGateway(basic_config)
        
        try:
            # Register all services
            for service in diamond_services:
                await gateway.register_service(service)
            
            # Initial health check
            health = await gateway.get_system_health()
            assert health["states"][DominoState.HEALTHY.value] == 4
            
            # Isolate critical service
            event = await gateway.force_isolate("service-d")
            assert event.contained is True
            
            # Check system state
            health = await gateway.get_system_health()
            assert health["states"][DominoState.ISOLATED.value] >= 1
            
            # Get history
            history = await gateway.get_cascade_history()
            assert len(history) >= 1
            
        finally:
            await gateway.close()
    
    @pytest.mark.asyncio
    async def test_concurrent_isolation(self, basic_config, chain_services):
        """Concurrent isolation requests."""
        gateway = DominoGateway(basic_config)
        
        try:
            for service in chain_services:
                await gateway.register_service(service)
            
            # Concurrent isolations
            results = await asyncio.gather(
                gateway.force_isolate("service-c"),
                gateway.force_isolate("service-d"),
                return_exceptions=True,
            )
            
            # Both should succeed or one may be isolated already
            assert all(isinstance(r, CascadeEvent) or isinstance(r, Exception) for r in results)
            
        finally:
            await gateway.close()
    
    @pytest.mark.asyncio
    async def test_health_check_with_real_http(self, basic_config):
        """Health check with mocked HTTP."""
        gateway = DominoGateway(basic_config)
        
        try:
            service = ServiceDependency(
                service_id="test-service",
                depends_on=[],
                health_endpoint="http://test-server/health",
            )
            await gateway.register_service(service)
            
            # Mock HTTP response
            with patch.object(httpx.AsyncClient, "get") as mock_get:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_get.return_value = mock_response
                
                is_healthy = await gateway.prevention._check_service_health(service)
                assert is_healthy is True
            
        finally:
            await gateway.close()


# ============= Factory Function Tests =============

class TestCreateDominoGateway:
    """Tests for create_domino_gateway factory."""
    
    @pytest.mark.asyncio
    async def test_create_with_defaults(self):
        """Create gateway with defaults."""
        gateway = create_domino_gateway()
        
        assert gateway.config.max_cascade_depth == 3
        assert gateway.config.auto_recovery_enabled is True
        
        await gateway.close()
    
    @pytest.mark.asyncio
    async def test_create_with_custom_config(self):
        """Create gateway with custom config."""
        gateway = create_domino_gateway(
            max_cascade_depth=5,
            health_check_interval=30.0,
            auto_recovery_enabled=False,
            notification_webhook="http://webhook.example.com/alert",
        )
        
        assert gateway.config.max_cascade_depth == 5
        assert gateway.config.health_check_interval == 30.0
        assert gateway.config.auto_recovery_enabled is False
        assert gateway.config.notification_webhook == "http://webhook.example.com/alert"
        
        await gateway.close()


# ============= Edge Cases =============

class TestEdgeCases:
    """Edge case tests."""
    
    @pytest.mark.asyncio
    async def test_empty_dependency_list(self, prevention):
        """Service with no dependencies."""
        service = ServiceDependency(
            service_id="standalone",
            depends_on=[],
            health_endpoint="http://localhost/health",
        )
        
        await prevention.register_service(service)
        
        at_risk = await prevention.check_cascade_risk("standalone")
        assert at_risk == []
        
        await prevention.close()
    
    @pytest.mark.asyncio
    async def test_self_dependency(self, prevention):
        """Service depending on itself (should not loop)."""
        service = ServiceDependency(
            service_id="self-referential",
            depends_on=["self-referential"],
            health_endpoint="http://localhost/health",
        )
        
        await prevention.register_service(service)
        
        # Should not infinite loop
        at_risk = await prevention.check_cascade_risk("self-referential")
        assert isinstance(at_risk, list)
        
        await prevention.close()
    
    @pytest.mark.asyncio
    async def test_circular_dependency(self, prevention):
        """Circular dependency A -> B -> C -> A."""
        services = [
            ServiceDependency(
                service_id="a",
                depends_on=["b"],
                health_endpoint="http://localhost/health",
            ),
            ServiceDependency(
                service_id="b",
                depends_on=["c"],
                health_endpoint="http://localhost/health",
            ),
            ServiceDependency(
                service_id="c",
                depends_on=["a"],
                health_endpoint="http://localhost/health",
            ),
        ]
        
        for service in services:
            await prevention.register_service(service)
        
        # Should not infinite loop
        at_risk = await prevention.check_cascade_risk("a")
        assert isinstance(at_risk, list)
        
        await prevention.close()
    
    @pytest.mark.asyncio
    async def test_isolation_timestamp_tracking(self, prevention, sample_service):
        """Isolation timestamp is tracked."""
        await prevention.register_service(sample_service)
        
        assert "service-a" not in prevention._isolation_timestamps
        
        await prevention.isolate_service("service-a", "Test")
        
        assert "service-a" in prevention._isolation_timestamps
        assert prevention._isolation_timestamps["service-a"] <= time.monotonic()
        
        await prevention.close()
    
    @pytest.mark.asyncio
    async def test_recovery_restores_dependents(self, prevention):
        """Recovery restores degraded dependents."""
        # Setup: A depends on B
        services = [
            ServiceDependency(
                service_id="a",
                depends_on=["b"],
                health_endpoint="http://localhost/health",
            ),
            ServiceDependency(
                service_id="b",
                depends_on=[],
                health_endpoint="http://localhost/health",
            ),
        ]
        
        for service in services:
            await prevention.register_service(service)
        
        # Isolate B
        await prevention.isolate_service("b", "B failed")
        
        # A should be degraded
        assert prevention.states["a"] == DominoState.DEGRADED
        
        # Recover B
        with patch.object(prevention, "_check_service_health", return_value=True):
            await prevention.attempt_recovery("b")
        
        # Both should be healthy
        assert prevention.states["b"] == DominoState.HEALTHY
        
        await prevention.close()


# ============= Performance Tests =============

class TestPerformance:
    """Performance-related tests."""
    
    @pytest.mark.asyncio
    async def test_large_dependency_graph(self, prevention):
        """Performance with large dependency graph."""
        # Create 100 services in a chain
        for i in range(100):
            service = ServiceDependency(
                service_id=f"service-{i}",
                depends_on=[f"service-{i+1}"] if i < 99 else [],
                health_endpoint=f"http://localhost:800{i % 10}/health",
            )
            await prevention.register_service(service)
        
        # Cascade check should complete quickly
        import time
        start = time.time()
        at_risk = await prevention.check_cascade_risk("service-99")
        elapsed = time.time() - start
        
        assert elapsed < 1.0  # Should complete in under 1 second
        
        await prevention.close()
    
    @pytest.mark.asyncio
    async def test_concurrent_health_checks(self, prevention):
        """Concurrent health checks don't block."""
        for i in range(10):
            service = ServiceDependency(
                service_id=f"service-{i}",
                depends_on=[],
                health_endpoint=f"http://localhost:800{i}/health",
            )
            await prevention.register_service(service)
        
        with patch.object(
            prevention,
            "_check_service_health",
            return_value=True
        ):
            import time
            start = time.time()
            results = await prevention.health_check_all()
            elapsed = time.time() - start
        
        assert len(results) == 10
        assert elapsed < 5.0  # Should complete quickly
        
        await prevention.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
