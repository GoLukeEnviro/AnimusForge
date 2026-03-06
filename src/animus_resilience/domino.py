"""
AnimusForge DOMINO Cascade Prevention System

Production-ready cascade prevention with dependency graph tracking,
automatic service isolation, circuit breaker integration, and recovery management.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Callable, Awaitable

import httpx
from pydantic import BaseModel, Field, ConfigDict

# Configure logging
logger = logging.getLogger(__name__)


class DominoState(str, Enum):
    """Service states in the cascade prevention system."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    ISOLATED = "isolated"
    FAILED = "failed"


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Failing, rejecting requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreaker:
    """
    Circuit Breaker for service protection.
    
    Attributes:
        failure_threshold: Failures before opening circuit
        success_threshold: Successes before closing circuit
        timeout_seconds: Recovery attempt timeout
    """
    failure_threshold: int = 3
    success_threshold: int = 2
    timeout_seconds: float = 30.0
    
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _success_count: int = field(default=0, init=False)
    _last_failure_time: Optional[float] = field(default=None, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    
    @property
    def state(self) -> CircuitState:
        return self._state
    
    @property
    def is_available(self) -> bool:
        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.OPEN:
            if self._last_failure_time is None:
                return False
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.timeout_seconds:
                self._state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker transitioning to HALF_OPEN")
                return True
            return False
        return True
    
    async def record_success(self) -> None:
        async with self._lock:
            self._failure_count = 0
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._success_count = 0
                    logger.info("Circuit breaker recovered - CLOSED")
            elif self._state == CircuitState.OPEN:
                self._state = CircuitState.HALF_OPEN
                self._success_count = 1
    
    async def record_failure(self) -> None:
        async with self._lock:
            self._success_count = 0
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning("Circuit breaker recovery failed - back to OPEN")
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.error(f"Circuit breaker opened after {self._failure_count} failures")
    
    def reset(self) -> None:
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None


class ServiceDependency(BaseModel):
    """Service dependency configuration."""
    model_config = ConfigDict(frozen=False)
    
    service_id: str
    depends_on: List[str] = Field(default_factory=list)
    health_endpoint: str
    timeout_seconds: float = 5.0
    failure_threshold: int = 3
    recovery_timeout: float = 30.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CascadeEvent(BaseModel):
    """Cascade event record for audit trail."""
    model_config = ConfigDict(frozen=False)
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_service: str
    affected_services: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    cascade_depth: int = 0
    contained: bool = False
    recovery_actions: List[str] = Field(default_factory=list)
    reason: str = ""
    isolation_duration_seconds: Optional[float] = None


class DominoConfig(BaseModel):
    """DOMINO cascade prevention configuration."""
    model_config = ConfigDict(frozen=True)
    
    max_cascade_depth: int = 3
    isolation_timeout: float = 60.0
    health_check_interval: float = 10.0
    auto_recovery_enabled: bool = True
    auto_recovery_interval: float = 30.0
    notification_webhook: Optional[str] = None
    circuit_failure_threshold: int = 3
    circuit_success_threshold: int = 2
    circuit_timeout: float = 30.0


class DominoPrevention:
    """
    DOMINO Cascade Prevention Engine.
    
    Features:
    - Dependency graph tracking with BFS/DFS traversal
    - Cascade risk detection and prediction
    - Automatic service isolation
    - Circuit breaker integration
    - Health check monitoring
    - Recovery attempt management
    - Event history and audit trail
    
    Usage:
        prevention = DominoPrevention(config)
        await prevention.register_service(service)
        at_risk = await prevention.check_cascade_risk("service-a")
        event = await prevention.isolate_service("service-a", "Health check failed")
    """
    
    def __init__(self, config: Optional[DominoConfig] = None) -> None:
        self.config = config or DominoConfig()
        self.services: Dict[str, ServiceDependency] = {}
        self.states: Dict[str, DominoState] = {}
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.cascade_history: List[CascadeEvent] = []
        self._dependency_graph: Dict[str, Set[str]] = defaultdict(set)
        self._reverse_graph: Dict[str, Set[str]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._health_check_task: Optional[asyncio.Task] = None
        self._recovery_task: Optional[asyncio.Task] = None
        self._running = False
        self._http_client: Optional[httpx.AsyncClient] = None
        self._notification_callbacks: List[Callable[[CascadeEvent], Awaitable[None]]] = []
        self._isolation_timestamps: Dict[str, float] = {}
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client
    
    def register_notification_callback(
        self, callback: Callable[[CascadeEvent], Awaitable[None]]
    ) -> None:
        self._notification_callbacks.append(callback)
    
    async def _notify(self, event: CascadeEvent) -> None:
        for callback in self._notification_callbacks:
            try:
                await callback(event)
            except Exception as e:
                logger.error(f"Notification callback failed: {e}")
        
        if self.config.notification_webhook:
            try:
                client = await self._get_client()
                await client.post(
                    self.config.notification_webhook,
                    json=event.model_dump(),
                )
            except Exception as e:
                logger.error(f"Webhook notification failed: {e}")
    
    async def register_service(self, service: ServiceDependency) -> None:
        """Register a service with its dependencies."""
        async with self._lock:
            self.services[service.service_id] = service
            self.states[service.service_id] = DominoState.HEALTHY
            self.circuit_breakers[service.service_id] = CircuitBreaker(
                failure_threshold=service.failure_threshold,
                timeout_seconds=service.recovery_timeout,
            )
            
            # Build dependency graph
            self._dependency_graph[service.service_id] = set(service.depends_on)
            
            # Build reverse graph (dependents)
            for dep in service.depends_on:
                self._reverse_graph[dep].add(service.service_id)
            
            logger.info(f"Registered service: {service.service_id} depends on: {service.depends_on}")
    
    async def unregister_service(self, service_id: str) -> None:
        """Unregister a service."""
        async with self._lock:
            if service_id not in self.services:
                return
            
            service = self.services.pop(service_id)
            self.states.pop(service_id, None)
            self.circuit_breakers.pop(service_id, None)
            self._isolation_timestamps.pop(service_id, None)
            
            # Clean dependency graph
            deps = self._dependency_graph.pop(service_id, set())
            for dep in deps:
                self._reverse_graph[dep].discard(service_id)
            
            # Clean reverse graph
            dependents = self._reverse_graph.pop(service_id, set())
            for dep in dependents:
                self._dependency_graph[dep].discard(service_id)
            
            logger.info(f"Unregistered service: {service_id}")
    
    async def check_cascade_risk(self, service_id: str) -> List[str]:
        """
        Check cascade risk using BFS to find all potentially affected services.
        
        Args:
            service_id: Service to check from
            
        Returns:
            List of service IDs at risk of cascade failure
        """
        async with self._lock:
            if service_id not in self.services:
                return []
            
            at_risk: List[str] = []
            visited: Set[str] = set()
            queue: deque = deque([(service_id, 0)])
            
            while queue:
                current, depth = queue.popleft()
                
                if current in visited:
                    continue
                visited.add(current)
                
                if depth > 0:  # Don't include the source
                    at_risk.append(current)
                
                if depth >= self.config.max_cascade_depth:
                    continue
                
                # Find dependents (services that depend on current)
                for dependent in self._reverse_graph.get(current, set()):
                    if dependent not in visited:
                        queue.append((dependent, depth + 1))
            
            logger.debug(f"Cascade risk from {service_id}: {at_risk}")
            return at_risk
    
    async def isolate_service(self, service_id: str, reason: str) -> CascadeEvent:
        """
        Isolate a failing service to prevent cascade.
        
        Args:
            service_id: Service to isolate
            reason: Reason for isolation
            
        Returns:
            CascadeEvent with isolation details
        """
        async with self._lock:
            if service_id not in self.services:
                raise ValueError(f"Unknown service: {service_id}")
            
            # Get affected services before isolation
            at_risk = []
            visited: Set[str] = {service_id}
            queue: deque = deque([(service_id, 0)])
            
            while queue:
                current, depth = queue.popleft()
                if depth >= self.config.max_cascade_depth:
                    continue
                for dependent in self._reverse_graph.get(current, set()):
                    if dependent not in visited:
                        visited.add(dependent)
                        at_risk.append(dependent)
                        queue.append((dependent, depth + 1))
            
            # Isolate the service
            self.states[service_id] = DominoState.ISOLATED
            self._isolation_timestamps[service_id] = time.monotonic()
            
            # Mark dependents as degraded
            for dependent in at_risk:
                if self.states.get(dependent) == DominoState.HEALTHY:
                    self.states[dependent] = DominoState.DEGRADED
            
            # Open circuit breaker
            if service_id in self.circuit_breakers:
                cb = self.circuit_breakers[service_id]
                cb._state = CircuitState.OPEN
                cb._last_failure_time = time.monotonic()
            
            event = CascadeEvent(
                source_service=service_id,
                affected_services=at_risk,
                cascade_depth=max(1, len(at_risk)),
                contained=True,
                reason=reason,
                recovery_actions=["isolation", "circuit_breaker_opened"],
            )
            
            self.cascade_history.append(event)
            
            logger.warning(
                f"Isolated service {service_id}: {reason}. "
                f"Affected: {len(at_risk)} services"
            )
            
            await self._notify(event)
            return event
    
    async def attempt_recovery(self, service_id: str) -> bool:
        """
        Attempt to recover an isolated service.
        
        Args:
            service_id: Service to recover
            
        Returns:
            True if recovery successful
        """
        async with self._lock:
            if service_id not in self.services:
                return False
            
            current_state = self.states.get(service_id)
            if current_state not in (DominoState.ISOLATED, DominoState.FAILED):
                return True  # Already healthy
            
            service = self.services[service_id]
            
            # Check health
            is_healthy = await self._check_service_health(service)
            
            if is_healthy:
                # Check dependencies are healthy
                deps_healthy = True
                for dep_id in service.depends_on:
                    if dep_id in self.states:
                        dep_state = self.states[dep_id]
                        if dep_state in (DominoState.ISOLATED, DominoState.FAILED):
                            deps_healthy = False
                            break
                
                if deps_healthy:
                    self.states[service_id] = DominoState.HEALTHY
                    self._isolation_timestamps.pop(service_id, None)
                    
                    if service_id in self.circuit_breakers:
                        self.circuit_breakers[service_id].reset()
                    
                    # Restore degraded dependents
                    for dependent in self._reverse_graph.get(service_id, set()):
                        if self.states.get(dependent) == DominoState.DEGRADED:
                            # Check if all their deps are healthy
                            all_healthy = True
                            for dep in self.services.get(dependent, ServiceDependency(
                                service_id=dependent, health_endpoint=""
                            )).depends_on:
                                if dep in self.states:
                                    if self.states[dep] != DominoState.HEALTHY:
                                        all_healthy = False
                                        break
                            if all_healthy:
                                self.states[dependent] = DominoState.HEALTHY
                    
                    logger.info(f"Service {service_id} recovered successfully")
                    return True
            
            logger.warning(f"Recovery attempt failed for {service_id}")
            return False
    
    async def _check_service_health(self, service: ServiceDependency) -> bool:
        """Check health of a single service."""
        try:
            client = await self._get_client()
            response = await client.get(
                service.health_endpoint,
                timeout=service.timeout_seconds,
            )
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Health check failed for {service.service_id}: {e}")
            return False
    
    async def get_service_state(self, service_id: str) -> DominoState:
        """Get current state of a service."""
        return self.states.get(service_id, DominoState.FAILED)
    
    async def get_dependency_graph(self) -> Dict[str, List[str]]:
        """Get the full dependency graph."""
        async with self._lock:
            return {
                service_id: list(deps)
                for service_id, deps in self._dependency_graph.items()
            }
    
    async def health_check_all(self) -> Dict[str, bool]:
        """Check health of all registered services."""
        results: Dict[str, bool] = {}
        
        for service_id, service in list(self.services.items()):
            if self.states.get(service_id) == DominoState.ISOLATED:
                results[service_id] = False
                continue
            
            is_healthy = await self._check_service_health(service)
            results[service_id] = is_healthy
            
            if not is_healthy:
                cb = self.circuit_breakers.get(service_id)
                if cb:
                    await cb.record_failure()
                    
                    if not cb.is_available:
                        await self.isolate_service(
                            service_id,
                            f"Health check failed, circuit breaker opened"
                        )
            else:
                cb = self.circuit_breakers.get(service_id)
                if cb:
                    await cb.record_success()
        
        return results
    
    async def start_monitoring(self) -> None:
        """Start background monitoring tasks."""
        if self._running:
            return
        
        self._running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        
        if self.config.auto_recovery_enabled:
            self._recovery_task = asyncio.create_task(self._recovery_loop())
        
        logger.info("DOMINO monitoring started")
    
    async def stop_monitoring(self) -> None:
        """Stop background monitoring tasks."""
        self._running = False
        
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None
        
        if self._recovery_task:
            self._recovery_task.cancel()
            try:
                await self._recovery_task
            except asyncio.CancelledError:
                pass
            self._recovery_task = None
        
        logger.info("DOMINO monitoring stopped")
    
    async def _health_check_loop(self) -> None:
        """Background health check loop."""
        while self._running:
            try:
                await self.health_check_all()
            except Exception as e:
                logger.error(f"Health check loop error: {e}")
            
            await asyncio.sleep(self.config.health_check_interval)
    
    async def _recovery_loop(self) -> None:
        """Background recovery attempt loop."""
        while self._running:
            try:
                for service_id in list(self.states.keys()):
                    if self.states[service_id] in (DominoState.ISOLATED, DominoState.FAILED):
                        # Check isolation timeout
                        isolation_time = self._isolation_timestamps.get(service_id)
                        if isolation_time:
                            elapsed = time.monotonic() - isolation_time
                            if elapsed >= self.config.isolation_timeout:
                                await self.attempt_recovery(service_id)
            except Exception as e:
                logger.error(f"Recovery loop error: {e}")
            
            await asyncio.sleep(self.config.auto_recovery_interval)
    
    async def close(self) -> None:
        """Cleanup resources."""
        await self.stop_monitoring()
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()


class DominoGateway:
    """
    Gateway for DOMINO Cascade Prevention system.
    
    Provides high-level interface for monitoring and control.
    
    Usage:
        gateway = DominoGateway(config)
        await gateway.start()
        health = await gateway.get_system_health()
        event = await gateway.force_isolate("service-a")
    """
    
    def __init__(
        self,
        config: Optional[DominoConfig] = None,
        prevention: Optional[DominoPrevention] = None,
    ) -> None:
        self.config = config or DominoConfig()
        self.prevention = prevention or DominoPrevention(self.config)
        self._started = False
    
    async def start(self) -> None:
        """Start monitoring and protection."""
        if self._started:
            return
        await self.prevention.start_monitoring()
        self._started = True
        logger.info("DominoGateway started")
    
    async def stop(self) -> None:
        """Stop monitoring."""
        await self.prevention.stop_monitoring()
        self._started = False
        logger.info("DominoGateway stopped")
    
    async def monitor_and_protect(self) -> None:
        """Start background monitoring task."""
        await self.start()
    
    async def force_isolate(self, service_id: str) -> CascadeEvent:
        """
        Force isolation of a service.
        
        Args:
            service_id: Service to isolate
            
        Returns:
            CascadeEvent with isolation details
        """
        return await self.prevention.isolate_service(
            service_id,
            reason="Manual isolation requested"
        )
    
    async def get_cascade_history(
        self,
        limit: int = 100,
        service_id: Optional[str] = None,
    ) -> List[CascadeEvent]:
        """
        Get cascade event history.
        
        Args:
            limit: Maximum events to return
            service_id: Filter by service (optional)
            
        Returns:
            List of CascadeEvents
        """
        events = self.prevention.cascade_history
        
        if service_id:
            events = [
                e for e in events
                if e.source_service == service_id or service_id in e.affected_services
            ]
        
        return events[-limit:]
    
    async def get_system_health(self) -> Dict[str, Any]:
        """
        Get comprehensive system health report.
        
        Returns:
            Dict with health metrics, states, and risk assessment
        """
        states = dict(self.prevention.states)
        health_counts = {
            DominoState.HEALTHY: 0,
            DominoState.DEGRADED: 0,
            DominoState.ISOLATED: 0,
            DominoState.FAILED: 0,
        }
        
        for state in states.values():
            health_counts[state] += 1
        
        # Calculate risk scores
        high_risk_services: List[str] = []
        for service_id in self.prevention.services:
            at_risk = await self.prevention.check_cascade_risk(service_id)
            if len(at_risk) >= self.config.max_cascade_depth - 1:
                high_risk_services.append(service_id)
        
        circuit_states = {
            sid: cb.state.value
            for sid, cb in self.prevention.circuit_breakers.items()
        }
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "total_services": len(self.prevention.services),
            "states": {
                state.value: count
                for state, count in health_counts.items()
            },
            "service_states": {
                sid: state.value
                for sid, state in states.items()
            },
            "circuit_breakers": circuit_states,
            "high_risk_services": high_risk_services,
            "recent_events": len([
                e for e in self.prevention.cascade_history
                if (datetime.utcnow() - e.timestamp).total_seconds() < 3600
            ]),
            "monitoring_active": self._started,
        }
    
    async def register_service(self, service: ServiceDependency) -> None:
        """Register a service."""
        await self.prevention.register_service(service)
    
    async def unregister_service(self, service_id: str) -> None:
        """Unregister a service."""
        await self.prevention.unregister_service(service_id)
    
    async def attempt_recovery(self, service_id: str) -> bool:
        """Attempt service recovery."""
        return await self.prevention.attempt_recovery(service_id)
    
    async def get_dependency_graph(self) -> Dict[str, List[str]]:
        """Get dependency graph."""
        return await self.prevention.get_dependency_graph()
    
    async def close(self) -> None:
        """Cleanup resources."""
        await self.stop()
        await self.prevention.close()


def create_domino_gateway(
    max_cascade_depth: int = 3,
    health_check_interval: float = 10.0,
    auto_recovery_enabled: bool = True,
    notification_webhook: Optional[str] = None,
) -> DominoGateway:
    """
    Create configured DOMINO Gateway.
    
    Args:
        max_cascade_depth: Maximum cascade depth to track
        health_check_interval: Seconds between health checks
        auto_recovery_enabled: Enable automatic recovery attempts
        notification_webhook: Webhook URL for notifications
        
    Returns:
        Configured DominoGateway instance
    """
    config = DominoConfig(
        max_cascade_depth=max_cascade_depth,
        health_check_interval=health_check_interval,
        auto_recovery_enabled=auto_recovery_enabled,
        notification_webhook=notification_webhook,
    )
    return DominoGateway(config=config)
