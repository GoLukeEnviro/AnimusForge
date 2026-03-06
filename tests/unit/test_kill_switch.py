"""
Unit Tests for AnimusForge Kill-Switch System
SPRINT1-002 Test Suite

Tests cover:
- KillSwitchLevel, RecoveryOption, TriggerSource enums
- Pydantic models validation
- KillSwitch class functionality
- KillSwitchController operations
- Monitor implementations
- Error handling and edge cases
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

# Import module under test
from animus_stage.kill_switch import (
    # Enums
    KillSwitchLevel,
    RecoveryOption,
    TriggerSource,
    HealthStatus,
    # Models
    ResourceMetrics,
    StateSnapshot,
    IncidentReport,
    KillSwitchResult,
    HealthCheckResult,
    KillSwitchConfig,
    # Classes
    KillSwitch,
    KillSwitchController,
    # Monitors
    Monitor,
    CPUMonitor,
    MemoryMonitor,
    # Convenience functions
    create_controller,
    quick_trigger,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def sample_persona_id() -> str:
    """Sample persona ID for testing."""
    return "test-persona-001"


@pytest.fixture
def sample_state_data() -> Dict[str, Any]:
    """Sample state data for testing."""
    return {
        "conversation_id": "conv-123",
        "turn_count": 5,
        "context": {"topic": "testing"},
    }


@pytest.fixture
def temp_persistence_path():
    """Temporary directory for state persistence."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def controller(temp_persistence_path):
    """Create a KillSwitchController instance for testing."""
    config = KillSwitchConfig(
        cpu_threshold_percent=90.0,
        memory_threshold_percent=95.0,
        state_persistence_path=temp_persistence_path,
        health_check_interval_seconds=1.0,
    )
    return KillSwitchController(config=config)


@pytest.fixture
def registered_controller(controller, sample_persona_id):
    """Controller with a pre-registered persona."""
    asyncio.run(controller.register_persona(sample_persona_id))
    return controller


# ============================================================================
# ENUM TESTS
# ============================================================================

class TestKillSwitchLevel:
    """Tests for KillSwitchLevel enum."""

    def test_level_values(self):
        """Test enum values are correctly ordered."""
        assert KillSwitchLevel.SOFT.value == 1
        assert KillSwitchLevel.HARD.value == 2
        assert KillSwitchLevel.EMERGENCY.value == 3

    def test_level_ordering(self):
        """Test level comparison."""
        assert KillSwitchLevel.SOFT < KillSwitchLevel.HARD
        assert KillSwitchLevel.HARD < KillSwitchLevel.EMERGENCY
        assert KillSwitchLevel.EMERGENCY > KillSwitchLevel.SOFT

    def test_level_string_representation(self):
        """Test string representation."""
        assert str(KillSwitchLevel.SOFT) == "SOFT"
        assert str(KillSwitchLevel.HARD) == "HARD"
        assert str(KillSwitchLevel.EMERGENCY) == "EMERGENCY"


class TestRecoveryOption:
    """Tests for RecoveryOption enum."""

    def test_option_values(self):
        """Test enum values."""
        assert RecoveryOption.AUTO_RESTART.value == "auto_restart"
        assert RecoveryOption.MANUAL_RESUME.value == "manual_resume"
        assert RecoveryOption.DISCARD.value == "discard"

    def test_option_string_representation(self):
        """Test string representation."""
        assert str(RecoveryOption.AUTO_RESTART) == "auto_restart"


class TestTriggerSource:
    """Tests for TriggerSource enum."""

    def test_all_sources_defined(self):
        """Test all trigger sources are defined."""
        sources = [
            TriggerSource.RESOURCE_LIMIT,
            TriggerSource.CONTENT_FILTER,
            TriggerSource.ANOMALY_DETECTION,
            TriggerSource.SECURITY_VIOLATION,
            TriggerSource.MANUAL_API,
            TriggerSource.HEALTH_CHECK_FAILURE,
        ]
        assert len(sources) == 6


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_status_values(self):
        """Test status values."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.CRITICAL.value == "critical"
        assert HealthStatus.UNKNOWN.value == "unknown"


# ============================================================================
# MODEL TESTS
# ============================================================================

class TestResourceMetrics:
    """Tests for ResourceMetrics model."""

    def test_valid_metrics(self):
        """Test creating valid metrics."""
        metrics = ResourceMetrics(
            cpu_percent=45.5,
            memory_percent=62.3
        )
        assert metrics.cpu_percent == 45.5
        assert metrics.memory_percent == 62.3
        assert metrics.timestamp is not None

    def test_metrics_with_all_fields(self):
        """Test metrics with all optional fields."""
        metrics = ResourceMetrics(
            cpu_percent=50.0,
            memory_percent=60.0,
            disk_percent=70.0,
            network_io_bytes=1024,
            active_threads=8
        )
        assert metrics.disk_percent == 70.0
        assert metrics.network_io_bytes == 1024
        assert metrics.active_threads == 8

    def test_invalid_cpu_percent(self):
        """Test validation rejects invalid CPU percentage."""
        with pytest.raises(ValidationError):
            ResourceMetrics(cpu_percent=150.0, memory_percent=50.0)

        with pytest.raises(ValidationError):
            ResourceMetrics(cpu_percent=-10.0, memory_percent=50.0)

    def test_invalid_memory_percent(self):
        """Test validation rejects invalid memory percentage."""
        with pytest.raises(ValidationError):
            ResourceMetrics(cpu_percent=50.0, memory_percent=200.0)


class TestStateSnapshot:
    """Tests for StateSnapshot model."""

    def test_valid_snapshot(self, sample_persona_id):
        """Test creating a valid snapshot."""
        snapshot = StateSnapshot(
            persona_id=sample_persona_id,
            state_data={"key": "value"}
        )
        assert snapshot.persona_id == sample_persona_id
        assert snapshot.state_data == {"key": "value"}
        assert snapshot.session_id is not None
        assert snapshot.timestamp is not None

    def test_snapshot_to_json(self, sample_persona_id):
        """Test JSON serialization."""
        snapshot = StateSnapshot(
            persona_id=sample_persona_id,
            state_data={"test": 123}
        )
        json_str = snapshot.to_json()
        assert isinstance(json_str, str)
        data = json.loads(json_str)
        assert data["persona_id"] == sample_persona_id

    def test_snapshot_from_json(self, sample_persona_id):
        """Test JSON deserialization."""
        original = StateSnapshot(
            persona_id=sample_persona_id,
            state_data={"nested": {"key": "value"}},
            conversation_context=[{"role": "user", "content": "test"}]
        )
        json_str = original.to_json()
        restored = StateSnapshot.from_json(json_str)

        assert restored.persona_id == original.persona_id
        assert restored.state_data == original.state_data
        assert restored.conversation_context == original.conversation_context

    def test_snapshot_with_metrics(self, sample_persona_id):
        """Test snapshot with resource metrics."""
        metrics = ResourceMetrics(cpu_percent=55.0, memory_percent=65.0)
        snapshot = StateSnapshot(
            persona_id=sample_persona_id,
            metrics=metrics
        )
        assert snapshot.metrics.cpu_percent == 55.0


class TestIncidentReport:
    """Tests for IncidentReport model."""

    def test_valid_incident_report(self, sample_persona_id):
        """Test creating a valid incident report."""
        report = IncidentReport(
            persona_id=sample_persona_id,
            kill_switch_level=KillSwitchLevel.HARD,
            trigger_source=TriggerSource.RESOURCE_LIMIT,
            reason="CPU threshold exceeded",
            recovery_option=RecoveryOption.MANUAL_RESUME
        )
        assert report.persona_id == sample_persona_id
        assert report.incident_id is not None
        assert report.resolved is False

    def test_incident_report_with_stack_trace(self, sample_persona_id):
        """Test incident report with stack trace."""
        report = IncidentReport(
            persona_id=sample_persona_id,
            kill_switch_level=KillSwitchLevel.EMERGENCY,
            trigger_source=TriggerSource.SECURITY_VIOLATION,
            reason="Security breach detected",
            stack_trace="Traceback...",
            recovery_option=RecoveryOption.DISCARD
        )
        assert report.stack_trace == "Traceback..."


class TestKillSwitchResult:
    """Tests for KillSwitchResult model."""

    def test_successful_result(self, sample_persona_id):
        """Test successful kill-switch result."""
        result = KillSwitchResult(
            success=True,
            persona_id=sample_persona_id,
            level=KillSwitchLevel.SOFT,
            message="Kill-switch triggered successfully"
        )
        assert result.success is True
        assert result.level == KillSwitchLevel.SOFT

    def test_failed_result(self, sample_persona_id):
        """Test failed kill-switch result."""
        result = KillSwitchResult(
            success=False,
            persona_id=sample_persona_id,
            level=KillSwitchLevel.HARD,
            message="Persona not registered"
        )
        assert result.success is False


class TestHealthCheckResult:
    """Tests for HealthCheckResult model."""

    def test_healthy_result(self, sample_persona_id):
        """Test healthy check result."""
        result = HealthCheckResult(
            persona_id=sample_persona_id,
            status=HealthStatus.HEALTHY,
            issues=[],
            recommendations=[]
        )
        assert result.status == HealthStatus.HEALTHY
        assert len(result.issues) == 0

    def test_degraded_result(self, sample_persona_id):
        """Test degraded check result."""
        result = HealthCheckResult(
            persona_id=sample_persona_id,
            status=HealthStatus.DEGRADED,
            issues=["CPU usage high"],
            recommendations=["Reduce load"]
        )
        assert result.status == HealthStatus.DEGRADED
        assert len(result.issues) == 1


class TestKillSwitchConfig:
    """Tests for KillSwitchConfig model."""

    def test_default_config(self):
        """Test default configuration values."""
        config = KillSwitchConfig()
        assert config.cpu_threshold_percent == 90.0
        assert config.memory_threshold_percent == 95.0
        assert config.health_check_interval_seconds == 5.0

    def test_custom_config(self):
        """Test custom configuration."""
        config = KillSwitchConfig(
            cpu_threshold_percent=85.0,
            memory_threshold_percent=90.0,
            health_check_interval_seconds=10.0,
            max_state_snapshots=20
        )
        assert config.cpu_threshold_percent == 85.0
        assert config.memory_threshold_percent == 90.0
        assert config.max_state_snapshots == 20

    def test_invalid_threshold(self):
        """Test validation rejects invalid thresholds."""
        with pytest.raises(ValidationError):
            KillSwitchConfig(cpu_threshold_percent=150.0)


# ============================================================================
# KILL SWITCH CLASS TESTS
# ============================================================================

class TestKillSwitch:
    """Tests for KillSwitch class."""

    def test_kill_switch_creation(self, sample_persona_id):
        """Test creating a KillSwitch instance."""
        ks = KillSwitch(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.SOFT,
            trigger_source=TriggerSource.MANUAL_API,
            reason="Test trigger"
        )
        assert ks.persona_id == sample_persona_id
        assert ks.level == KillSwitchLevel.SOFT
        assert ks.trigger_source == TriggerSource.MANUAL_API
        assert ks.reason == "Test trigger"
        assert ks.timestamp is not None

    def test_kill_switch_with_snapshot(self, sample_persona_id):
        """Test KillSwitch with state snapshot."""
        snapshot = StateSnapshot(
            persona_id=sample_persona_id,
            state_data={"key": "value"}
        )
        ks = KillSwitch(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.HARD,
            trigger_source=TriggerSource.RESOURCE_LIMIT,
            reason="Resource exceeded",
            state_snapshot=snapshot
        )
        assert ks.state_snapshot is not None
        assert ks.state_snapshot.state_data == {"key": "value"}

    @pytest.mark.asyncio
    async def test_get_recovery_options_soft(self, sample_persona_id):
        """Test recovery options for SOFT level."""
        ks = KillSwitch(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.SOFT,
            trigger_source=TriggerSource.MANUAL_API,
            reason="Test"
        )
        options = await ks.get_recovery_options()
        assert RecoveryOption.AUTO_RESTART in options
        assert RecoveryOption.MANUAL_RESUME in options
        assert RecoveryOption.DISCARD not in options

    @pytest.mark.asyncio
    async def test_get_recovery_options_hard(self, sample_persona_id):
        """Test recovery options for HARD level."""
        ks = KillSwitch(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.HARD,
            trigger_source=TriggerSource.MANUAL_API,
            reason="Test"
        )
        options = await ks.get_recovery_options()
        assert RecoveryOption.MANUAL_RESUME in options
        assert RecoveryOption.DISCARD in options
        assert RecoveryOption.AUTO_RESTART not in options

    @pytest.mark.asyncio
    async def test_get_recovery_options_emergency(self, sample_persona_id):
        """Test recovery options for EMERGENCY level."""
        ks = KillSwitch(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.EMERGENCY,
            trigger_source=TriggerSource.MANUAL_API,
            reason="Test"
        )
        options = await ks.get_recovery_options()
        assert RecoveryOption.DISCARD in options
        assert RecoveryOption.AUTO_RESTART not in options
        assert RecoveryOption.MANUAL_RESUME not in options

    def test_recovery_option_property(self, sample_persona_id):
        """Test default recovery option property."""
        ks_soft = KillSwitch(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.SOFT,
            trigger_source=TriggerSource.MANUAL_API,
            reason="Test"
        )
        assert ks_soft.recovery_option == RecoveryOption.AUTO_RESTART

        ks_hard = KillSwitch(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.HARD,
            trigger_source=TriggerSource.MANUAL_API,
            reason="Test"
        )
        assert ks_hard.recovery_option == RecoveryOption.MANUAL_RESUME

        ks_emergency = KillSwitch(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.EMERGENCY,
            trigger_source=TriggerSource.MANUAL_API,
            reason="Test"
        )
        assert ks_emergency.recovery_option == RecoveryOption.DISCARD

    @pytest.mark.asyncio
    async def test_execute_recovery_valid(self, sample_persona_id):
        """Test executing valid recovery."""
        ks = KillSwitch(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.SOFT,
            trigger_source=TriggerSource.MANUAL_API,
            reason="Test"
        )
        result = await ks.execute_recovery(RecoveryOption.AUTO_RESTART)
        assert result is True

    @pytest.mark.asyncio
    async def test_execute_recovery_invalid(self, sample_persona_id):
        """Test executing invalid recovery option."""
        ks = KillSwitch(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.EMERGENCY,
            trigger_source=TriggerSource.MANUAL_API,
            reason="Test"
        )
        # EMERGENCY only allows DISCARD, not AUTO_RESTART
        result = await ks.execute_recovery(RecoveryOption.AUTO_RESTART)
        assert result is False

    @pytest.mark.asyncio
    async def test_execute_recovery_twice(self, sample_persona_id):
        """Test executing recovery twice fails."""
        ks = KillSwitch(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.SOFT,
            trigger_source=TriggerSource.MANUAL_API,
            reason="Test"
        )
        result1 = await ks.execute_recovery(RecoveryOption.AUTO_RESTART)
        result2 = await ks.execute_recovery(RecoveryOption.AUTO_RESTART)
        assert result1 is True
        assert result2 is False  # Already executed

    @pytest.mark.asyncio
    async def test_custom_recovery_handler(self, sample_persona_id):
        """Test custom recovery handler."""
        handler_called = []

        async def custom_handler(pid, option, snapshot):
            handler_called.append((pid, option))
            return True

        ks = KillSwitch(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.SOFT,
            trigger_source=TriggerSource.MANUAL_API,
            reason="Test"
        )
        result = await ks.execute_recovery(
            RecoveryOption.AUTO_RESTART,
            recovery_handler=custom_handler
        )
        assert result is True
        assert len(handler_called) == 1

    def test_generate_incident_report(self, sample_persona_id):
        """Test incident report generation."""
        ks = KillSwitch(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.HARD,
            trigger_source=TriggerSource.ANOMALY_DETECTION,
            reason="Anomaly detected"
        )
        report = ks.generate_incident_report()
        assert report.persona_id == sample_persona_id
        assert report.kill_switch_level == KillSwitchLevel.HARD
        assert report.trigger_source == TriggerSource.ANOMALY_DETECTION
        assert ks.incident_report is not None


# ============================================================================
# KILL SWITCH CONTROLLER TESTS
# ============================================================================

class TestKillSwitchController:
    """Tests for KillSwitchController class."""

    def test_controller_creation(self):
        """Test creating a controller."""
        ctrl = KillSwitchController()
        assert ctrl.config is not None
        assert len(ctrl._monitors) >= 2  # CPU and Memory monitors

    def test_controller_with_config(self, temp_persistence_path):
        """Test creating controller with custom config."""
        config = KillSwitchConfig(
            cpu_threshold_percent=80.0,
            memory_threshold_percent=85.0,
            state_persistence_path=temp_persistence_path
        )
        ctrl = KillSwitchController(config=config)
        assert ctrl.config.cpu_threshold_percent == 80.0

    @pytest.mark.asyncio
    async def test_register_persona(self, controller, sample_persona_id):
        """Test registering a persona."""
        result = await controller.register_persona(sample_persona_id)
        assert result is True
        assert sample_persona_id in controller._personas
        assert controller._health_status[sample_persona_id] == HealthStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_register_persona_duplicate(self, controller, sample_persona_id):
        """Test registering duplicate persona fails."""
        await controller.register_persona(sample_persona_id)
        result = await controller.register_persona(sample_persona_id)
        assert result is False

    @pytest.mark.asyncio
    async def test_register_persona_with_state(
        self, controller, sample_persona_id, sample_state_data
    ):
        """Test registering persona with initial state."""
        result = await controller.register_persona(
            sample_persona_id,
            initial_state=sample_state_data
        )
        assert result is True
        assert controller._personas[sample_persona_id]["state"] == sample_state_data

    @pytest.mark.asyncio
    async def test_register_persona_with_handler(self, controller, sample_persona_id):
        """Test registering persona with recovery handler."""
        async def handler(pid, option, snapshot):
            return True

        result = await controller.register_persona(
            sample_persona_id,
            recovery_handler=handler
        )
        assert result is True
        assert sample_persona_id in controller._recovery_handlers

    @pytest.mark.asyncio
    async def test_unregister_persona(self, controller, sample_persona_id):
        """Test unregistering a persona."""
        await controller.register_persona(sample_persona_id)
        result = await controller.unregister_persona(sample_persona_id)
        assert result is True
        assert sample_persona_id not in controller._personas

    @pytest.mark.asyncio
    async def test_unregister_nonexistent_persona(self, controller):
        """Test unregistering non-existent persona."""
        result = await controller.unregister_persona("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_check_health_unregistered(self, controller):
        """Test health check for unregistered persona."""
        result = await controller.check_health("unregistered")
        assert result.status == HealthStatus.UNKNOWN
        assert "not registered" in result.issues[0]

    @pytest.mark.asyncio
    async def test_check_health_healthy(self, registered_controller, sample_persona_id):
        """Test health check for healthy persona."""
        with patch.object(
            registered_controller._monitors[0], 
            'check', 
            return_value=45.0
        ), patch.object(
            registered_controller._monitors[1], 
            'check', 
            return_value=50.0
        ):
            result = await registered_controller.check_health(sample_persona_id)
            assert result.status == HealthStatus.HEALTHY
            assert len(result.issues) == 0

    @pytest.mark.asyncio
    async def test_check_health_degraded(self, registered_controller, sample_persona_id):
        """Test health check for degraded persona."""
        with patch.object(
            registered_controller._monitors[0],
            'check',
            return_value=92.0  # Above 90% threshold
        ), patch.object(
            registered_controller._monitors[1],
            'check',
            return_value=50.0
        ):
            result = await registered_controller.check_health(sample_persona_id)
            assert result.status == HealthStatus.DEGRADED
            assert len(result.issues) > 0

    @pytest.mark.asyncio
    async def test_check_health_critical(self, registered_controller, sample_persona_id):
        """Test health check for critical persona."""
        with patch.object(
            registered_controller._monitors[0],
            'check',
            return_value=96.0  # Above 95%
        ), patch.object(
            registered_controller._monitors[1],
            'check',
            return_value=98.0  # Above 95%
        ):
            result = await registered_controller.check_health(sample_persona_id)
            assert result.status == HealthStatus.CRITICAL

    @pytest.mark.asyncio
    async def test_trigger_soft(self, registered_controller, sample_persona_id):
        """Test triggering SOFT kill-switch."""
        result = await registered_controller.trigger(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.SOFT,
            reason="Test soft trigger",
            trigger_source=TriggerSource.MANUAL_API
        )
        assert result.success is True
        assert result.level == KillSwitchLevel.SOFT
        assert result.execution_time_ms < 1000  # Less than 1 second
        assert RecoveryOption.AUTO_RESTART in result.recovery_options

    @pytest.mark.asyncio
    async def test_trigger_hard(self, registered_controller, sample_persona_id):
        """Test triggering HARD kill-switch."""
        result = await registered_controller.trigger(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.HARD,
            reason="Test hard trigger",
            trigger_source=TriggerSource.RESOURCE_LIMIT
        )
        assert result.success is True
        assert result.level == KillSwitchLevel.HARD
        assert result.incident_id is not None  # Incident report generated

    @pytest.mark.asyncio
    async def test_trigger_emergency(self, registered_controller, sample_persona_id):
        """Test triggering EMERGENCY kill-switch."""
        result = await registered_controller.trigger(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.EMERGENCY,
            reason="Test emergency trigger",
            trigger_source=TriggerSource.SECURITY_VIOLATION
        )
        assert result.success is True
        assert result.level == KillSwitchLevel.EMERGENCY
        assert RecoveryOption.DISCARD in result.recovery_options

    @pytest.mark.asyncio
    async def test_trigger_unregistered(self, controller):
        """Test triggering for unregistered persona."""
        result = await controller.trigger(
            persona_id="unregistered",
            level=KillSwitchLevel.SOFT,
            reason="Test"
        )
        assert result.success is False
        assert "not registered" in result.message

    @pytest.mark.asyncio
    async def test_trigger_with_state_data(self, registered_controller, sample_persona_id):
        """Test triggering with additional state data."""
        result = await registered_controller.trigger(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.SOFT,
            reason="Test",
            state_data={"custom_key": "custom_value"}
        )
        assert result.success is True
        assert result.state_snapshot_id is not None

    @pytest.mark.asyncio
    async def test_get_recovery_options(self, registered_controller, sample_persona_id):
        """Test getting recovery options."""
        await registered_controller.trigger(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.SOFT,
            reason="Test"
        )
        options = await registered_controller.get_recovery_options(sample_persona_id)
        assert len(options) > 0

    @pytest.mark.asyncio
    async def test_execute_recovery(self, registered_controller, sample_persona_id):
        """Test executing recovery."""
        await registered_controller.trigger(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.SOFT,
            reason="Test"
        )
        result = await registered_controller.execute_recovery(
            sample_persona_id,
            RecoveryOption.AUTO_RESTART
        )
        assert result is True
        # Kill-switch should be cleared
        assert registered_controller.get_active_kill_switch(sample_persona_id) is None

    @pytest.mark.asyncio
    async def test_execute_recovery_no_kill_switch(
        self, registered_controller, sample_persona_id
    ):
        """Test executing recovery without active kill-switch."""
        result = await registered_controller.execute_recovery(
            sample_persona_id,
            RecoveryOption.AUTO_RESTART
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_state_persistence(self, temp_persistence_path, sample_persona_id):
        """Test state snapshot persistence."""
        config = KillSwitchConfig(
            state_persistence_path=temp_persistence_path,
        )
        ctrl = KillSwitchController(config=config)
        await ctrl.register_persona(sample_persona_id)

        result = await ctrl.trigger(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.SOFT,
            reason="Test persistence"
        )

        assert result.success is True
        assert result.state_snapshot_id is not None

        # Check file was created
        snapshot_files = list(temp_persistence_path.glob("*.json"))
        assert len(snapshot_files) > 0

    @pytest.mark.asyncio
    async def test_get_incident_reports(self, registered_controller, sample_persona_id):
        """Test getting incident reports."""
        await registered_controller.trigger(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.HARD,
            reason="Test incident"
        )

        reports = registered_controller.get_incident_reports(sample_persona_id)
        assert len(reports) > 0
        assert reports[0].persona_id == sample_persona_id

    @pytest.mark.asyncio
    async def test_get_state_snapshots(self, registered_controller, sample_persona_id):
        """Test getting state snapshots."""
        await registered_controller.trigger(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.SOFT,
            reason="Test snapshot"
        )

        snapshots = registered_controller.get_state_snapshots(sample_persona_id)
        assert len(snapshots) > 0

    @pytest.mark.asyncio
    async def test_add_custom_monitor(self, controller, sample_persona_id):
        """Test adding custom monitor."""
        class CustomMonitor(Monitor):
            async def check(self, persona_id: str) -> float:
                return 50.0

        custom = CustomMonitor("custom", threshold=80.0)
        controller.add_monitor(custom)

        assert custom in controller._monitors

    @pytest.mark.asyncio
    async def test_start_stop_monitoring(self, controller, sample_persona_id):
        """Test starting and stopping monitoring."""
        await controller.register_persona(sample_persona_id)

        # Start monitoring
        await controller.start_monitoring()
        assert controller._running is True
        assert controller._monitor_task is not None

        # Let it run briefly
        await asyncio.sleep(0.1)

        # Stop monitoring
        await controller.stop_monitoring()
        assert controller._running is False
        assert controller._monitor_task is None

    @pytest.mark.asyncio
    async def test_threshold_violation_callback(self, controller, sample_persona_id):
        """Test threshold violation triggers kill-switch."""
        await controller.register_persona(sample_persona_id)

        # Simulate threshold violation
        await controller._handle_threshold_violation(sample_persona_id, 92.0)

        # Check that kill-switch was triggered
        ks = controller.get_active_kill_switch(sample_persona_id)
        assert ks is not None


# ============================================================================
# MONITOR TESTS
# ============================================================================

class TestMonitors:
    """Tests for Monitor implementations."""

    def test_monitor_creation(self):
        """Test creating a monitor."""
        monitor = CPUMonitor(threshold=85.0)
        assert monitor.name == "cpu_monitor"
        assert monitor.threshold == 85.0

    def test_monitor_callback_registration(self):
        """Test registering callbacks."""
        monitor = CPUMonitor()
        callback_called = []

        def callback(pid, value):
            callback_called.append((pid, value))

        monitor.register_callback(callback)
        assert len(monitor._callbacks) == 1

    @pytest.mark.asyncio
    async def test_cpu_monitor_check(self):
        """Test CPU monitor check."""
        monitor = CPUMonitor()
        value = await monitor.check("test-persona")
        assert isinstance(value, float)
        assert 0.0 <= value <= 100.0

    @pytest.mark.asyncio
    async def test_memory_monitor_check(self):
        """Test memory monitor check."""
        monitor = MemoryMonitor()
        value = await monitor.check("test-persona")
        assert isinstance(value, float)
        assert 0.0 <= value <= 100.0

    @pytest.mark.asyncio
    async def test_monitor_callback_notification(self):
        """Test monitor callback notification."""
        monitor = CPUMonitor()
        callback_called = []

        async def async_callback(pid, value):
            callback_called.append((pid, value))

        monitor.register_callback(async_callback)
        await monitor._notify_callbacks("test-pid", 95.0)

        assert len(callback_called) == 1
        assert callback_called[0] == ("test-pid", 95.0)


# ============================================================================
# CONVENIENCE FUNCTION TESTS
# ============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_create_controller(self):
        """Test create_controller factory function."""
        ctrl = create_controller(
            cpu_threshold=85.0,
            memory_threshold=90.0
        )
        assert isinstance(ctrl, KillSwitchController)
        assert ctrl.config.cpu_threshold_percent == 85.0
        assert ctrl.config.memory_threshold_percent == 90.0

    @pytest.mark.asyncio
    async def test_quick_trigger(self):
        """Test quick_trigger function."""
        ctrl = create_controller()
        result = await quick_trigger(
            controller=ctrl,
            persona_id="quick-test",
            level=KillSwitchLevel.SOFT,
            reason="Quick test"
        )
        assert result.success is True
        assert result.level == KillSwitchLevel.SOFT


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_trigger_updates_health_status(self, registered_controller, sample_persona_id):
        """Test that trigger updates health status to CRITICAL."""
        await registered_controller.trigger(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.HARD,
            reason="Test"
        )
        assert registered_controller._health_status[sample_persona_id] == HealthStatus.CRITICAL

    @pytest.mark.asyncio
    async def test_recovery_updates_health_status(self, registered_controller, sample_persona_id):
        """Test that recovery updates health status to HEALTHY."""
        await registered_controller.trigger(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.SOFT,
            reason="Test"
        )
        await registered_controller.execute_recovery(
            sample_persona_id,
            RecoveryOption.AUTO_RESTART
        )
        assert registered_controller._health_status[sample_persona_id] == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_max_state_snapshots_limit(self, temp_persistence_path, sample_persona_id):
        """Test that snapshot limit is enforced."""
        config = KillSwitchConfig(
            state_persistence_path=temp_persistence_path,
            max_state_snapshots=3
        )
        ctrl = KillSwitchController(config=config)
        await ctrl.register_persona(sample_persona_id)

        # Trigger multiple times
        for i in range(5):
            await ctrl.trigger(
                persona_id=sample_persona_id,
                level=KillSwitchLevel.SOFT,
                reason=f"Test {i}"
            )
            # Clear kill-switch for next trigger
            await ctrl.execute_recovery(sample_persona_id, RecoveryOption.AUTO_RESTART)

        # Should only have max_state_snapshots stored
        snapshots = ctrl.get_state_snapshots(sample_persona_id)
        assert len(snapshots) <= 3

    @pytest.mark.asyncio
    async def test_load_nonexistent_snapshot(self, controller, sample_persona_id):
        """Test loading non-existent snapshot."""
        await controller.register_persona(sample_persona_id)
        snapshot = await controller.load_state_snapshot(sample_persona_id, "nonexistent-id")
        assert snapshot is None

    @pytest.mark.asyncio
    async def test_concurrent_triggers(self, registered_controller, sample_persona_id):
        """Test concurrent trigger handling."""
        # Trigger first one
        result1 = await registered_controller.trigger(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.SOFT,
            reason="First"
        )

        # Second trigger should overwrite
        result2 = await registered_controller.trigger(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.HARD,
            reason="Second"
        )

        assert result1.success is True
        assert result2.success is True

        # Should have HARD level (last trigger)
        ks = registered_controller.get_active_kill_switch(sample_persona_id)
        assert ks.level == KillSwitchLevel.HARD

    @pytest.mark.asyncio
    async def test_monitor_with_exception(self, controller, sample_persona_id):
        """Test handling monitor that raises exception."""
        class FailingMonitor(Monitor):
            async def check(self, persona_id: str) -> float:
                raise RuntimeError("Monitor failed")

        failing = FailingMonitor("failing", threshold=90.0)
        controller.add_monitor(failing)
        await controller.register_persona(sample_persona_id)

        # Should handle exception gracefully
        result = await controller.check_health(sample_persona_id)
        assert result.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]

    @pytest.mark.asyncio
    async def test_sync_recovery_handler(self, controller, sample_persona_id):
        """Test synchronous recovery handler."""
        handler_called = []

        def sync_handler(pid, option, snapshot):
            handler_called.append(pid)
            return True

        await controller.register_persona(
            sample_persona_id,
            recovery_handler=sync_handler
        )

        await controller.trigger(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.SOFT,
            reason="Test"
        )

        result = await controller.execute_recovery(
            sample_persona_id,
            RecoveryOption.AUTO_RESTART
        )

        assert result is True
        assert len(handler_called) == 1


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================

class TestPerformance:
    """Tests for performance requirements."""

    @pytest.mark.asyncio
    async def test_trigger_response_time(self, registered_controller, sample_persona_id):
        """Test trigger response time < 1 second."""
        result = await registered_controller.trigger(
            persona_id=sample_persona_id,
            level=KillSwitchLevel.SOFT,
            reason="Performance test"
        )

        assert result.success is True
        assert result.execution_time_ms < 1000,             f"Response time {result.execution_time_ms}ms exceeds 1000ms requirement"

    @pytest.mark.asyncio
    async def test_health_check_response_time(self, registered_controller, sample_persona_id):
        """Test health check completes quickly."""
        import time
        start = time.time()

        await registered_controller.check_health(sample_persona_id)

        elapsed = (time.time() - start) * 1000
        assert elapsed < 1000, f"Health check took {elapsed}ms"

    @pytest.mark.asyncio
    async def test_multiple_personas_performance(self, controller):
        """Test handling multiple registered personas."""
        # Register 10 personas
        for i in range(10):
            await controller.register_persona(f"persona-{i}")

        # Trigger all
        results = []
        for i in range(10):
            result = await controller.trigger(
                persona_id=f"persona-{i}",
                level=KillSwitchLevel.SOFT,
                reason="Load test"
            )
            results.append(result)

        # All should succeed
        assert all(r.success for r in results)


# ============================================================================
# RUN CONFIGURATION
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=kill_switch", "--cov-report=term-missing"])
