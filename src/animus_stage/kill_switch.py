"""
AnimusForge Kill-Switch System
3-Level Emergency Shutdown with Recovery Options

SPRINT1-002 Implementation
"""

from __future__ import annotations

import asyncio
import json
import logging
import traceback
from datetime import datetime, timezone
from enum import Enum, IntEnum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class KillSwitchLevel(IntEnum):
    """Kill-Switch severity levels with increasing impact."""
    SOFT = 1
    HARD = 2
    EMERGENCY = 3

    def __str__(self) -> str:
        return self.name


class RecoveryOption(Enum):
    """Available recovery strategies after kill-switch activation."""
    AUTO_RESTART = "auto_restart"
    MANUAL_RESUME = "manual_resume"
    DISCARD = "discard"

    def __str__(self) -> str:
        return self.value


class TriggerSource(Enum):
    """Sources that can trigger a kill-switch."""
    RESOURCE_LIMIT = "resource_limit"
    CONTENT_FILTER = "content_filter"
    ANOMALY_DETECTION = "anomaly_detection"
    SECURITY_VIOLATION = "security_violation"
    MANUAL_API = "manual_api"
    HEALTH_CHECK_FAILURE = "health_check_failure"

    def __str__(self) -> str:
        return self.value


class HealthStatus(Enum):
    """Health check status indicators."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return self.value


class ResourceMetrics(BaseModel):
    """System resource metrics snapshot."""
    model_config = ConfigDict(frozen=True)

    cpu_percent: float = Field(ge=0.0, le=100.0, description="CPU usage percentage")
    memory_percent: float = Field(ge=0.0, le=100.0, description="Memory usage percentage")
    disk_percent: Optional[float] = Field(None, ge=0.0, le=100.0)
    network_io_bytes: Optional[int] = Field(None, ge=0)
    active_threads: Optional[int] = Field(None, ge=0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StateSnapshot(BaseModel):
    """Complete state snapshot for persistence and recovery."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    persona_id: str
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    state_data: Dict[str, Any] = Field(default_factory=dict)
    conversation_context: List[Dict[str, Any]] = Field(default_factory=list)
    active_tasks: List[Dict[str, Any]] = Field(default_factory=list)
    memory_references: List[str] = Field(default_factory=list)
    tool_states: Dict[str, Any] = Field(default_factory=dict)
    metrics: Optional[ResourceMetrics] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_json(self) -> str:
        import json
        return json.dumps(self.model_dump(mode='json'), indent=2, default=str)

    @classmethod
    def from_json(cls, json_str: str) -> "StateSnapshot":
        return cls.model_validate_json(json_str)


class IncidentReport(BaseModel):
    """Detailed incident report for emergency situations."""
    model_config = ConfigDict(frozen=True)

    incident_id: str = Field(default_factory=lambda: str(uuid4()))
    persona_id: str
    kill_switch_level: KillSwitchLevel
    trigger_source: TriggerSource
    reason: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    stack_trace: Optional[str] = None
    state_snapshot_id: Optional[str] = None
    recovery_option: RecoveryOption
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    additional_data: Dict[str, Any] = Field(default_factory=dict)


class KillSwitchResult(BaseModel):
    """Result of a kill-switch trigger operation."""
    model_config = ConfigDict(frozen=True)

    success: bool
    persona_id: str
    level: KillSwitchLevel
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    state_snapshot_id: Optional[str] = None
    incident_id: Optional[str] = None
    recovery_options: List[RecoveryOption] = Field(default_factory=list)
    message: str = ""
    execution_time_ms: float = 0.0


class HealthCheckResult(BaseModel):
    """Result of a health check operation."""
    model_config = ConfigDict(frozen=True)

    persona_id: str
    status: HealthStatus
    metrics: Optional[ResourceMetrics] = None
    issues: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class KillSwitchConfig(BaseModel):
    """Configuration for kill-switch behavior."""
    model_config = ConfigDict(frozen=False)

    cpu_threshold_percent: float = Field(default=90.0, ge=0.0, le=100.0)
    memory_threshold_percent: float = Field(default=95.0, ge=0.0, le=100.0)
    disk_threshold_percent: float = Field(default=95.0, ge=0.0, le=100.0)
    health_check_interval_seconds: float = Field(default=5.0, ge=1.0)
    graceful_shutdown_timeout_seconds: float = Field(default=30.0, ge=5.0)
    state_persistence_path: Optional[Path] = Field(default=None)
    max_state_snapshots: int = Field(default=10, ge=1)
    auto_restart_delay_seconds: float = Field(default=5.0, ge=1.0)
    max_restart_attempts: int = Field(default=3, ge=1)
    log_level: str = Field(default="INFO")
    enable_incident_reports: bool = Field(default=True)


class Monitor:
    """Base class for health and resource monitors."""

    def __init__(self, name: str, threshold: float = 90.0):
        self.name = name
        self.threshold = threshold
        self._callbacks: List[Callable[[str, float], None]] = []

    async def check(self, persona_id: str) -> float:
        raise NotImplementedError

    def register_callback(self, callback: Callable[[str, float], None]) -> None:
        self._callbacks.append(callback)

    async def _notify_callbacks(self, persona_id: str, value: float) -> None:
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(persona_id, value)
                else:
                    callback(persona_id, value)
            except Exception as e:
                logger.error(f"Monitor callback error: {e}")


class CPUMonitor(Monitor):
    """CPU usage monitor."""

    def __init__(self, threshold: float = 90.0):
        super().__init__("cpu_monitor", threshold)

    async def check(self, persona_id: str) -> float:
        try:
            import psutil
            return psutil.cpu_percent(interval=0.1)
        except ImportError:
            logger.warning("psutil not available, returning mock CPU value")
            return 45.0


class MemoryMonitor(Monitor):
    """Memory usage monitor."""

    def __init__(self, threshold: float = 95.0):
        super().__init__("memory_monitor", threshold)

    async def check(self, persona_id: str) -> float:
        try:
            import psutil
            return psutil.virtual_memory().percent
        except ImportError:
            logger.warning("psutil not available, returning mock memory value")
            return 50.0


class KillSwitch:
    """Individual kill-switch instance for a persona."""

    def __init__(
        self,
        persona_id: str,
        level: KillSwitchLevel,
        trigger_source: TriggerSource,
        reason: str,
        state_snapshot: Optional[StateSnapshot] = None
    ):
        self.persona_id = persona_id
        self.level = level
        self.trigger_source = trigger_source
        self.reason = reason
        self.timestamp = datetime.now(timezone.utc)
        self.state_snapshot = state_snapshot
        self._incident_report: Optional[IncidentReport] = None
        self._recovery_executed = False

    @property
    def incident_report(self) -> Optional[IncidentReport]:
        return self._incident_report

    @property
    def recovery_option(self) -> RecoveryOption:
        level_to_recovery = {
            KillSwitchLevel.SOFT: RecoveryOption.AUTO_RESTART,
            KillSwitchLevel.HARD: RecoveryOption.MANUAL_RESUME,
            KillSwitchLevel.EMERGENCY: RecoveryOption.DISCARD,
        }
        return level_to_recovery[self.level]

    async def get_recovery_options(self) -> List[RecoveryOption]:
        if self.level == KillSwitchLevel.SOFT:
            return [RecoveryOption.AUTO_RESTART, RecoveryOption.MANUAL_RESUME]
        elif self.level == KillSwitchLevel.HARD:
            return [RecoveryOption.MANUAL_RESUME, RecoveryOption.DISCARD]
        return [RecoveryOption.DISCARD]

    async def execute_recovery(
        self,
        option: RecoveryOption,
        recovery_handler: Optional[Callable[[str, RecoveryOption, StateSnapshot], bool]] = None
    ) -> bool:
        if self._recovery_executed:
            logger.warning(f"Recovery already executed for persona {self.persona_id}")
            return False

        available_options = await self.get_recovery_options()
        if option not in available_options:
            logger.error(f"Invalid recovery option {option} for level {self.level}")
            return False

        try:
            if recovery_handler:
                if asyncio.iscoroutinefunction(recovery_handler):
                    result = await recovery_handler(self.persona_id, option, self.state_snapshot)
                else:
                    result = recovery_handler(self.persona_id, option, self.state_snapshot)
            else:
                result = await self._default_recovery(option)

            self._recovery_executed = True
            logger.info(f"Recovery {option} executed for persona {self.persona_id}")
            return result
        except Exception as e:
            logger.error(f"Recovery execution failed: {e}")
            return False

    async def _default_recovery(self, option: RecoveryOption) -> bool:
        logger.info(f"Default recovery {option} for persona {self.persona_id}")
        return True

    def generate_incident_report(self) -> IncidentReport:
        self._incident_report = IncidentReport(
            persona_id=self.persona_id,
            kill_switch_level=self.level,
            trigger_source=self.trigger_source,
            reason=self.reason,
            stack_trace=traceback.format_exc() if traceback.format_exc() != "NoneType: None\n" else None,
            state_snapshot_id=self.state_snapshot.session_id if self.state_snapshot else None,
            recovery_option=self.recovery_option,
        )
        return self._incident_report


class KillSwitchController:
    """Central controller managing all kill-switches for registered personas."""

    def __init__(
        self,
        config: Optional[KillSwitchConfig] = None,
        state_persistence_path: Optional[Path] = None
    ):
        self.config = config or KillSwitchConfig()
        self._switches: Dict[str, KillSwitch] = {}
        self._personas: Dict[str, Dict[str, Any]] = {}
        self._monitors: List[Monitor] = []
        self._health_status: Dict[str, HealthStatus] = {}
        self._state_snapshots: Dict[str, List[StateSnapshot]] = {}
        self._incident_reports: List[IncidentReport] = []
        self._recovery_handlers: Dict[str, Callable] = {}
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None

        self._setup_default_monitors()

        if state_persistence_path:
            self.config.state_persistence_path = state_persistence_path

        logging.basicConfig(level=getattr(logging, self.config.log_level.upper()))

    def _setup_default_monitors(self) -> None:
        self._monitors = [
            CPUMonitor(threshold=self.config.cpu_threshold_percent),
            MemoryMonitor(threshold=self.config.memory_threshold_percent),
        ]

    def add_monitor(self, monitor: Monitor) -> None:
        self._monitors.append(monitor)
        monitor.register_callback(self._handle_threshold_violation)

    async def _handle_threshold_violation(self, persona_id: str, value: float) -> None:
        logger.warning(f"Threshold violation for {persona_id}: {value}")
        if value >= 95:
            level = KillSwitchLevel.EMERGENCY
        elif value >= 90:
            level = KillSwitchLevel.HARD
        else:
            level = KillSwitchLevel.SOFT

        await self.trigger(
            persona_id=persona_id,
            level=level,
            reason=f"Resource threshold exceeded: {value}%",
            trigger_source=TriggerSource.RESOURCE_LIMIT
        )

    async def register_persona(
        self,
        persona_id: str,
        initial_state: Optional[Dict[str, Any]] = None,
        recovery_handler: Optional[Callable] = None
    ) -> bool:
        if persona_id in self._personas:
            logger.warning(f"Persona {persona_id} already registered")
            return False

        self._personas[persona_id] = {
            "registered_at": datetime.now(timezone.utc),
            "state": initial_state or {},
            "restart_attempts": 0,
        }
        self._health_status[persona_id] = HealthStatus.UNKNOWN
        self._state_snapshots[persona_id] = []

        if recovery_handler:
            self._recovery_handlers[persona_id] = recovery_handler

        logger.info(f"Persona {persona_id} registered")
        return True

    async def unregister_persona(self, persona_id: str) -> bool:
        if persona_id not in self._personas:
            return False

        if self._health_status.get(persona_id) != HealthStatus.CRITICAL:
            await self.trigger(
                persona_id=persona_id,
                level=KillSwitchLevel.SOFT,
                reason="Persona unregistration",
                trigger_source=TriggerSource.MANUAL_API
            )

        del self._personas[persona_id]
        self._health_status.pop(persona_id, None)
        self._state_snapshots.pop(persona_id, None)
        self._recovery_handlers.pop(persona_id, None)
        self._switches.pop(persona_id, None)

        logger.info(f"Persona {persona_id} unregistered")
        return True

    async def check_health(self, persona_id: str) -> HealthCheckResult:
        if persona_id not in self._personas:
            return HealthCheckResult(
                persona_id=persona_id,
                status=HealthStatus.UNKNOWN,
                issues=["Persona not registered"],
            )

        issues: List[str] = []
        recommendations: List[str] = []
        metrics_data: Dict[str, float] = {}

        for monitor in self._monitors:
            try:
                value = await monitor.check(persona_id)
                metrics_data[monitor.name] = value

                if value >= monitor.threshold:
                    issues.append(f"{monitor.name} threshold exceeded: {value}%")
                    recommendations.append(f"Consider reducing {monitor.name} usage")
            except Exception as e:
                issues.append(f"{monitor.name} check failed: {e}")

        if len(issues) == 0:
            status = HealthStatus.HEALTHY
        elif any("exceeded" in issue for issue in issues):
            # Check if any metric value is >= 95 (critical threshold)
            critical = any(v >= 95.0 for v in metrics_data.values() if isinstance(v, (int, float)))
            status = HealthStatus.CRITICAL if critical else HealthStatus.DEGRADED
        else:
            status = HealthStatus.DEGRADED

        self._health_status[persona_id] = status

        metrics = ResourceMetrics(
            cpu_percent=metrics_data.get("cpu_monitor", 0.0),
            memory_percent=metrics_data.get("memory_monitor", 0.0),
        )

        return HealthCheckResult(
            persona_id=persona_id,
            status=status,
            metrics=metrics,
            issues=issues,
            recommendations=recommendations,
        )

    async def trigger(
        self,
        persona_id: str,
        level: KillSwitchLevel,
        reason: str,
        trigger_source: TriggerSource = TriggerSource.MANUAL_API,
        state_data: Optional[Dict[str, Any]] = None
    ) -> KillSwitchResult:
        start_time = datetime.now(timezone.utc)

        if persona_id not in self._personas:
            return KillSwitchResult(
                success=False,
                persona_id=persona_id,
                level=level,
                message=f"Persona {persona_id} not registered",
            )

        try:
            state_snapshot = await self._capture_state_snapshot(persona_id, level, state_data)

            kill_switch = KillSwitch(
                persona_id=persona_id,
                level=level,
                trigger_source=trigger_source,
                reason=reason,
                state_snapshot=state_snapshot,
            )

            await self._execute_kill_switch_actions(kill_switch)
            self._switches[persona_id] = kill_switch

            incident_id = None
            if level >= KillSwitchLevel.HARD and self.config.enable_incident_reports:
                report = kill_switch.generate_incident_report()
                self._incident_reports.append(report)
                incident_id = report.incident_id

            state_snapshot_id = None
            if state_snapshot:
                state_snapshot_id = state_snapshot.session_id
                await self._persist_state_snapshot(persona_id, state_snapshot)

            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            self._health_status[persona_id] = HealthStatus.CRITICAL
            recovery_options = await kill_switch.get_recovery_options()

            return KillSwitchResult(
                success=True,
                persona_id=persona_id,
                level=level,
                state_snapshot_id=state_snapshot_id,
                incident_id=incident_id,
                recovery_options=recovery_options,
                message=f"Kill-switch {level.name} triggered successfully",
                execution_time_ms=execution_time,
            )
        except Exception as e:
            logger.error(f"Kill-switch trigger failed: {e}")
            return KillSwitchResult(
                success=False,
                persona_id=persona_id,
                level=level,
                message=f"Kill-switch trigger failed: {str(e)}",
            )

    async def _capture_state_snapshot(
        self,
        persona_id: str,
        level: KillSwitchLevel,
        additional_data: Optional[Dict[str, Any]] = None
    ) -> StateSnapshot:
        persona_data = self._personas.get(persona_id, {})

        metrics = None
        try:
            cpu = await self._monitors[0].check(persona_id) if self._monitors else 0
            mem = await self._monitors[1].check(persona_id) if len(self._monitors) > 1 else 0
            metrics = ResourceMetrics(cpu_percent=cpu, memory_percent=mem)
        except Exception as e:
            logger.warning(f"Failed to capture metrics: {e}")

        snapshot = StateSnapshot(
            persona_id=persona_id,
            state_data={**persona_data.get("state", {}), **(additional_data or {})},
            metadata={
                "kill_switch_level": level.name,
                "captured_at": datetime.now(timezone.utc).isoformat(),
            },
            metrics=metrics,
        )
        return snapshot

    async def _execute_kill_switch_actions(self, kill_switch: KillSwitch) -> None:
        level = kill_switch.level
        persona_id = kill_switch.persona_id

        if level == KillSwitchLevel.SOFT:
            logger.info(f"Executing SOFT kill-switch for {persona_id}")
            await self._graceful_shutdown(persona_id)
        elif level == KillSwitchLevel.HARD:
            logger.warning(f"Executing HARD kill-switch for {persona_id}")
            await self._immediate_stop(persona_id)
        elif level == KillSwitchLevel.EMERGENCY:
            logger.critical(f"Executing EMERGENCY kill-switch for {persona_id}")
            await self._force_kill(persona_id)

    async def _graceful_shutdown(self, persona_id: str) -> None:
        logger.info(f"Initiating graceful shutdown for {persona_id}")
        await asyncio.sleep(0.1)
        if persona_id in self._personas:
            self._personas[persona_id]["shutting_down"] = True

    async def _immediate_stop(self, persona_id: str) -> None:
        logger.warning(f"Immediate stop for {persona_id}")
        if persona_id in self._personas:
            self._personas[persona_id]["stopped"] = True

    async def _force_kill(self, persona_id: str) -> None:
        logger.critical(f"Force kill for {persona_id}")
        if persona_id in self._personas:
            self._personas[persona_id]["killed"] = True

    async def _persist_state_snapshot(self, persona_id: str, snapshot: StateSnapshot) -> None:
        if persona_id not in self._state_snapshots:
            self._state_snapshots[persona_id] = []

        self._state_snapshots[persona_id].append(snapshot)

        max_snapshots = self.config.max_state_snapshots
        if len(self._state_snapshots[persona_id]) > max_snapshots:
            self._state_snapshots[persona_id] = self._state_snapshots[persona_id][-max_snapshots:]

        if self.config.state_persistence_path:
            try:
                path = self.config.state_persistence_path
                path.mkdir(parents=True, exist_ok=True)
                file_path = path / f"{persona_id}_{snapshot.session_id}.json"
                file_path.write_text(snapshot.to_json())
                logger.info(f"State snapshot persisted to {file_path}")
            except Exception as e:
                logger.error(f"Failed to persist state snapshot: {e}")

    async def get_recovery_options(self, persona_id: str) -> List[RecoveryOption]:
        kill_switch = self._switches.get(persona_id)
        if not kill_switch:
            return []
        return await kill_switch.get_recovery_options()

    async def execute_recovery(self, persona_id: str, option: RecoveryOption) -> bool:
        kill_switch = self._switches.get(persona_id)
        if not kill_switch:
            logger.error(f"No kill-switch found for persona {persona_id}")
            return False

        recovery_handler = self._recovery_handlers.get(persona_id)
        result = await kill_switch.execute_recovery(option, recovery_handler)

        if result:
            self._health_status[persona_id] = HealthStatus.HEALTHY
            del self._switches[persona_id]

        return result

    async def start_monitoring(self) -> None:
        if self._running:
            return
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Kill-switch monitoring started")

    async def stop_monitoring(self) -> None:
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        logger.info("Kill-switch monitoring stopped")

    async def _monitoring_loop(self) -> None:
        while self._running:
            try:
                for persona_id in list(self._personas.keys()):
                    result = await self.check_health(persona_id)
                    if result.status == HealthStatus.CRITICAL:
                        await self.trigger(
                            persona_id=persona_id,
                            level=KillSwitchLevel.HARD,
                            reason="Critical health status detected",
                            trigger_source=TriggerSource.HEALTH_CHECK_FAILURE
                        )
                await asyncio.sleep(self.config.health_check_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                await asyncio.sleep(1.0)

    def get_active_kill_switch(self, persona_id: str) -> Optional[KillSwitch]:
        return self._switches.get(persona_id)

    def get_incident_reports(self, persona_id: Optional[str] = None) -> List[IncidentReport]:
        if persona_id:
            return [r for r in self._incident_reports if r.persona_id == persona_id]
        return self._incident_reports.copy()

    def get_state_snapshots(self, persona_id: Optional[str] = None) -> List[StateSnapshot]:
        if persona_id:
            return self._state_snapshots.get(persona_id, []).copy()
        all_snapshots = []
        for snapshots in self._state_snapshots.values():
            all_snapshots.extend(snapshots)
        return all_snapshots

    async def load_state_snapshot(self, persona_id: str, session_id: str) -> Optional[StateSnapshot]:
        snapshots = self._state_snapshots.get(persona_id, [])
        for snapshot in snapshots:
            if snapshot.session_id == session_id:
                return snapshot

        if self.config.state_persistence_path:
            file_path = self.config.state_persistence_path / f"{persona_id}_{session_id}.json"
            if file_path.exists():
                try:
                    return StateSnapshot.from_json(file_path.read_text())
                except Exception as e:
                    logger.error(f"Failed to load snapshot: {e}")
        return None


def create_controller(
    cpu_threshold: float = 90.0,
    memory_threshold: float = 95.0,
    persistence_path: Optional[Path] = None
) -> KillSwitchController:
    """Factory function to create a configured KillSwitchController."""
    config = KillSwitchConfig(
        cpu_threshold_percent=cpu_threshold,
        memory_threshold_percent=memory_threshold,
        state_persistence_path=persistence_path,
    )
    return KillSwitchController(config=config)


async def quick_trigger(
    controller: KillSwitchController,
    persona_id: str,
    level: KillSwitchLevel,
    reason: str
) -> KillSwitchResult:
    """Quick trigger utility for immediate kill-switch activation."""
    if persona_id not in controller._personas:
        await controller.register_persona(persona_id)
    return await controller.trigger(persona_id, level, reason)
