"""Health Monitor - System health monitoring and Kubernetes probes.

This module provides comprehensive health monitoring for AnimusForge components
with periodic health checks, failure/recovery thresholds, and Kubernetes-compatible
liveness/readiness probes.
"""

from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Awaitable
from datetime import datetime, timezone
from pydantic import BaseModel, Field, field_validator
import asyncio
import logging
import time
from functools import wraps

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Health status levels for components and system."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"


class ComponentHealth(BaseModel):
    """Health status of a single component."""
    name: str = Field(..., description="Component name")
    status: HealthStatus = Field(..., description="Current health status")
    latency_ms: float = Field(..., ge=0, description="Check latency in milliseconds")
    last_check: datetime = Field(..., description="Timestamp of last health check")
    error_message: Optional[str] = Field(None, description="Error message if unhealthy")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional component metadata")
    consecutive_failures: int = Field(default=0, ge=0, description="Consecutive failure count")
    consecutive_successes: int = Field(default=0, ge=0, description="Consecutive success count")

    model_config = {"extra": "forbid"}


class SystemHealth(BaseModel):
    """Overall system health status."""
    overall_status: HealthStatus = Field(..., description="Aggregated system health status")
    components: Dict[str, ComponentHealth] = Field(..., description="Health status by component")
    uptime_seconds: float = Field(..., ge=0, description="System uptime in seconds")
    version: str = Field(default="1.0.0", description="System version")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Health check timestamp")

    model_config = {"extra": "forbid"}

    @field_validator("overall_status", mode="before")
    @classmethod
    def validate_overall_status(cls, v: Any) -> HealthStatus:
        """Ensure overall status is a valid HealthStatus."""
        if isinstance(v, HealthStatus):
            return v
        return HealthStatus(v)


class HealthCheckConfig(BaseModel):
    """Configuration for health monitoring."""
    check_interval: float = Field(default=30.0, gt=0, description="Interval between health checks in seconds")
    timeout: float = Field(default=5.0, gt=0, description="Timeout for individual health checks in seconds")
    failure_threshold: int = Field(default=3, ge=1, description="Consecutive failures before marking unhealthy")
    recovery_threshold: int = Field(default=2, ge=1, description="Consecutive successes before marking healthy")
    components: List[str] = Field(
        default=["database", "cache", "vector_store", "graph_store", "llm_gateway"],
        description="List of components to monitor"
    )
    enable_periodic_checks: bool = Field(default=True, description="Enable periodic background health checks")

    model_config = {"extra": "forbid"}


class HealthCheckError(Exception):
    """Exception raised when a health check fails."""
    def __init__(self, component: str, message: str, original_error: Optional[Exception] = None):
        self.component = component
        self.message = message
        self.original_error = original_error
        super().__init__(f"Health check failed for {component}: {message}")


class HealthMonitor:
    """Monitors health of system components with periodic checks.

    Features:
    - Component registration with custom health check functions
    - Periodic background health monitoring
    - Failure/recovery threshold handling
    - System-wide health aggregation

    Example:
        monitor = HealthMonitor(config)
        await monitor.register_component("database", check_db_connection)
        await monitor.start_monitoring()
        health = monitor.get_system_health()
    """

    def __init__(self, config: Optional[HealthCheckConfig] = None):
        """Initialize health monitor with configuration.

        Args:
            config: Health check configuration. Uses defaults if not provided.
        """
        self.config = config or HealthCheckConfig()
        self._component_status: Dict[str, ComponentHealth] = {}
        self._check_functions: Dict[str, Callable[[], Awaitable[bool]]] = {}
        self._check_tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        self._start_time = time.monotonic()
        self._lock = asyncio.Lock()
        logger.info(f"HealthMonitor initialized with config: {self.config}")

    async def register_component(
        self, 
        name: str, 
        check_fn: Callable[[], Awaitable[bool]],
        initial_status: HealthStatus = HealthStatus.HEALTHY,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Register a component for health monitoring.

        Args:
            name: Unique component name
            check_fn: Async function that returns True if healthy, False otherwise
            initial_status: Initial health status before first check
            metadata: Additional component metadata
        """
        async with self._lock:
            self._check_functions[name] = check_fn
            self._component_status[name] = ComponentHealth(
                name=name,
                status=initial_status,
                latency_ms=0.0,
                last_check=datetime.now(timezone.utc),
                error_message=None,
                metadata=metadata or {}
            )
            logger.info(f"Registered component: {name}")

    async def unregister_component(self, name: str) -> None:
        """Unregister a component from health monitoring.

        Args:
            name: Component name to unregister
        """
        async with self._lock:
            if name in self._check_functions:
                del self._check_functions[name]
            if name in self._component_status:
                del self._component_status[name]
            if name in self._check_tasks:
                self._check_tasks[name].cancel()
                del self._check_tasks[name]
            logger.info(f"Unregistered component: {name}")

    async def check_component(self, name: str) -> ComponentHealth:
        """Perform a health check on a specific component.

        Args:
            name: Component name to check

        Returns:
            ComponentHealth with current status

        Raises:
            HealthCheckError: If component is not registered
        """
        if name not in self._check_functions:
            raise HealthCheckError(name, f"Component {name} is not registered")

        check_fn = self._check_functions[name]
        start_time = time.monotonic()
        error_message = None
        is_healthy = False

        try:
            is_healthy = await asyncio.wait_for(
                check_fn(),
                timeout=self.config.timeout
            )
        except asyncio.TimeoutError:
            error_message = f"Health check timed out after {self.config.timeout}s"
            logger.warning(f"Health check timeout for {name}")
        except Exception as e:
            error_message = str(e)
            logger.error(f"Health check error for {name}: {e}")

        latency_ms = (time.monotonic() - start_time) * 1000

        async with self._lock:
            current = self._component_status.get(name)
            if not current:
                current = ComponentHealth(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    latency_ms=latency_ms,
                    last_check=datetime.now(timezone.utc),
                    error_message=error_message
                )

            # Update failure/success counters
            if is_healthy:
                consecutive_failures = 0
                consecutive_successes = current.consecutive_successes + 1
            else:
                consecutive_failures = current.consecutive_failures + 1
                consecutive_successes = 0

            # Determine new status based on thresholds
            new_status = self._calculate_status(
                current.status,
                consecutive_failures,
                consecutive_successes,
                is_healthy
            )

            updated_health = ComponentHealth(
                name=name,
                status=new_status,
                latency_ms=latency_ms,
                last_check=datetime.now(timezone.utc),
                error_message=error_message,
                metadata=current.metadata,
                consecutive_failures=consecutive_failures,
                consecutive_successes=consecutive_successes
            )

            self._component_status[name] = updated_health

            if new_status != current.status:
                logger.info(f"Component {name} status changed: {current.status} -> {new_status}")

            return updated_health

    def _calculate_status(
        self,
        current_status: HealthStatus,
        consecutive_failures: int,
        consecutive_successes: int,
        is_healthy: bool
    ) -> HealthStatus:
        """Calculate new health status based on thresholds."""
        if is_healthy:
            # Recovery logic
            if consecutive_successes >= self.config.recovery_threshold:
                return HealthStatus.HEALTHY
            elif current_status == HealthStatus.CRITICAL:
                return HealthStatus.DEGRADED
            return current_status
        else:
            # Failure logic
            if consecutive_failures >= self.config.failure_threshold:
                if consecutive_failures >= self.config.failure_threshold * 2:
                    return HealthStatus.CRITICAL
                return HealthStatus.UNHEALTHY
            elif consecutive_failures > 0:
                return HealthStatus.DEGRADED
            return current_status

    async def check_all(self) -> SystemHealth:
        """Perform health checks on all registered components.

        Returns:
            SystemHealth with aggregated status
        """
        tasks = [self.check_component(name) for name in self._check_functions.keys()]

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        return self.get_system_health()

    async def start_monitoring(self) -> None:
        """Start periodic health monitoring for all components."""
        if self._running:
            logger.warning("Health monitoring already running")
            return

        self._running = True

        if not self.config.enable_periodic_checks:
            logger.info("Periodic health checks disabled")
            return

        for name in self._check_functions.keys():
            task = asyncio.create_task(self._monitor_loop(name))
            self._check_tasks[name] = task

        logger.info(f"Started health monitoring for {len(self._check_functions)} components")

    async def stop_monitoring(self) -> None:
        """Stop periodic health monitoring."""
        self._running = False

        for name, task in self._check_tasks.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._check_tasks.clear()
        logger.info("Stopped health monitoring")

    async def _monitor_loop(self, name: str) -> None:
        """Background monitoring loop for a component."""
        while self._running:
            try:
                await self.check_component(name)
            except Exception as e:
                logger.error(f"Error in monitor loop for {name}: {e}")

            await asyncio.sleep(self.config.check_interval)

    def get_component_health(self, name: str) -> Optional[ComponentHealth]:
        """Get health status of a specific component.

        Args:
            name: Component name

        Returns:
            ComponentHealth or None if not registered
        """
        return self._component_status.get(name)

    def get_system_health(self) -> SystemHealth:
        """Get aggregated system health status.

        Returns:
            SystemHealth with overall status
        """
        uptime = time.monotonic() - self._start_time
        overall_status = self._aggregate_status()

        return SystemHealth(
            overall_status=overall_status,
            components=dict(self._component_status),
            uptime_seconds=uptime,
            version="1.0.0"
        )

    def _aggregate_status(self) -> HealthStatus:
        """Aggregate component statuses into overall system status."""
        if not self._component_status:
            return HealthStatus.HEALTHY

        statuses = [h.status for h in self._component_status.values()]

        if HealthStatus.CRITICAL in statuses:
            return HealthStatus.CRITICAL
        elif HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED

        return HealthStatus.HEALTHY

    @property
    def is_running(self) -> bool:
        """Check if monitoring is active."""
        return self._running

    @property
    def registered_components(self) -> List[str]:
        """Get list of registered component names."""
        return list(self._check_functions.keys())


class HealthGateway:
    """Gateway for health checks with Kubernetes probe support.

    Provides endpoints for:
    - Overall health status
    - Kubernetes liveness probes (is the service running?)
    - Kubernetes readiness probes (is the service ready to accept traffic?)
    """

    def __init__(self, monitor: HealthMonitor):
        """Initialize health gateway.

        Args:
            monitor: HealthMonitor instance
        """
        self.monitor = monitor
        self._startup_complete = False
        logger.info("HealthGateway initialized")

    async def get_health(self) -> SystemHealth:
        """Get full system health status.

        Returns:
            SystemHealth with all component details
        """
        return await self.monitor.check_all()

    async def get_liveness(self) -> Dict[str, Any]:
        """Get liveness probe response.

        Kubernetes liveness probe - indicates if the service is running.
        If this fails, Kubernetes will restart the pod.

        Returns:
            Simple status dict
        """
        return {
            "status": "alive",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    async def get_readiness(self) -> Dict[str, Any]:
        """Get readiness probe response.

        Kubernetes readiness probe - indicates if the service is ready
        to accept traffic. If this fails, Kubernetes will stop sending
        traffic but won't restart the pod.

        Returns:
            Status dict with readiness info
        """
        health = self.monitor.get_system_health()
        is_ready = health.overall_status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]

        return {
            "status": "ready" if is_ready else "not_ready",
            "overall_health": health.overall_status.value,
            "components_checked": len(health.components),
            "timestamp": health.timestamp.isoformat()
        }

    async def force_check(self, component: str) -> ComponentHealth:
        """Force an immediate health check on a component.

        Args:
            component: Component name to check

        Returns:
            ComponentHealth with current status

        Raises:
            HealthCheckError: If component is not registered
        """
        return await self.monitor.check_component(component)

    def mark_startup_complete(self) -> None:
        """Mark that startup is complete for readiness checks."""
        self._startup_complete = True
        logger.info("Startup marked as complete")

    @property
    def is_ready(self) -> bool:
        """Check if service is ready to accept traffic."""
        if not self._startup_complete:
            return False

        health = self.monitor.get_system_health()
        return health.overall_status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]


def create_health_monitor(
    check_interval: float = 30.0,
    timeout: float = 5.0,
    failure_threshold: int = 3,
    recovery_threshold: int = 2,
    components: Optional[List[str]] = None,
    enable_periodic_checks: bool = True
) -> HealthMonitor:
    """Factory function to create a configured HealthMonitor.

    Args:
        check_interval: Interval between health checks
        timeout: Timeout for individual checks
        failure_threshold: Failures before marking unhealthy
        recovery_threshold: Successes before marking healthy
        components: List of components to monitor
        enable_periodic_checks: Enable background monitoring

    Returns:
        Configured HealthMonitor instance
    """
    config = HealthCheckConfig(
        check_interval=check_interval,
        timeout=timeout,
        failure_threshold=failure_threshold,
        recovery_threshold=recovery_threshold,
        components=components or ["database", "cache", "vector_store", "graph_store", "llm_gateway"],
        enable_periodic_checks=enable_periodic_checks
    )
    return HealthMonitor(config)


def create_health_gateway(monitor: Optional[HealthMonitor] = None) -> HealthGateway:
    """Factory function to create a HealthGateway.

    Args:
        monitor: Optional HealthMonitor. Creates new one if not provided.

    Returns:
        HealthGateway instance
    """
    if monitor is None:
        monitor = create_health_monitor()
    return HealthGateway(monitor)
