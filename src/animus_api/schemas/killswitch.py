"""Kill-Switch schemas for emergency persona control."""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from .base import BaseSchema, PaginatedResponse, UUIDMixin


class KillSwitchTrigger(str, Enum):
    """Kill-switch trigger types."""
    MANUAL = "manual"
    SAFETY_VIOLATION = "safety_violation"
    ETHICS_VIOLATION = "ethics_violation"
    BEHAVIOR_ANOMALY = "behavior_anomaly"
    RESOURCE_LIMIT = "resource_limit"
    SECURITY_BREACH = "security_breach"
    CASCADE = "cascade"
    SCHEDULED = "scheduled"


class KillSwitchSeverity(str, Enum):
    """Kill-switch severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class KillSwitchStatus(str, Enum):
    """Kill-switch status."""
    TRIGGERED = "triggered"
    ACTIVE = "active"
    RECOVERING = "recovering"
    RECOVERED = "recovered"
    FAILED = "failed"
    EXPIRED = "expired"


class RecoveryStrategy(str, Enum):
    """Recovery strategy options."""
    AUTOMATIC = "automatic"
    MANUAL = "manual"
    INCREMENTAL = "incremental"
    CHECKPOINT = "checkpoint"
    FULL_RESET = "full_reset"
    ROLLBACK = "rollback"


class KillSwitchTriggerRequest(BaseSchema):
    """Request to trigger kill-switch."""
    persona_id: UUID = Field(description="Target persona ID")
    trigger_type: KillSwitchTrigger = Field(description="Trigger type")
    severity: KillSwitchSeverity = Field(default=KillSwitchSeverity.HIGH, description="Severity level")
    reason: str = Field(min_length=1, max_length=2000, description="Trigger reason")
    immediate: bool = Field(default=True, description="Immediate execution")
    cascade: bool = Field(default=False, description="Cascade to dependent personas")
    notify_stakeholders: bool = Field(default=True, description="Notify stakeholders")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class KillSwitchTriggerResponse(BaseSchema):
    """Response after triggering kill-switch."""
    incident_id: UUID = Field(description="Incident ID")
    persona_id: UUID = Field(description="Persona ID")
    status: KillSwitchStatus = Field(description="Current status")
    triggered_at: datetime = Field(default_factory=datetime.utcnow, description="Trigger timestamp")
    trigger_type: KillSwitchTrigger = Field(description="Trigger type")
    severity: KillSwitchSeverity = Field(description="Severity level")
    affected_operations: List[str] = Field(default_factory=list, description="Affected operations")
    cascade_targets: List[UUID] = Field(default_factory=list, description="Cascade target IDs")
    estimated_recovery_time: Optional[int] = Field(default=None, description="Estimated recovery time (seconds)")


class KillSwitchStatusResponse(BaseSchema):
    """Kill-switch status response."""
    persona_id: UUID = Field(description="Persona ID")
    active: bool = Field(description="Kill-switch active")
    status: KillSwitchStatus = Field(description="Current status")
    incident_id: Optional[UUID] = Field(default=None, description="Current incident ID")
    triggered_at: Optional[datetime] = Field(default=None, description="Trigger timestamp")
    trigger_type: Optional[KillSwitchTrigger] = Field(default=None, description="Trigger type")
    severity: Optional[KillSwitchSeverity] = Field(default=None, description="Severity level")
    reason: Optional[str] = Field(default=None, description="Trigger reason")
    recovery_available: bool = Field(description="Recovery available")
    recovery_strategies: List[RecoveryStrategy] = Field(default_factory=list, description="Available strategies")


class RecoveryRequest(BaseSchema):
    """Request to recover from kill-switch."""
    persona_id: UUID = Field(description="Persona ID")
    strategy: RecoveryStrategy = Field(description="Recovery strategy")
    checkpoint_id: Optional[UUID] = Field(default=None, description="Checkpoint ID for rollback")
    validation_steps: List[str] = Field(default_factory=list, description="Validation steps to perform")
    auto_validate: bool = Field(default=True, description="Auto-validate recovery")
    notify_stakeholders: bool = Field(default=True, description="Notify stakeholders")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class RecoveryResponse(BaseSchema):
    """Response after recovery attempt."""
    persona_id: UUID = Field(description="Persona ID")
    incident_id: UUID = Field(description="Related incident ID")
    success: bool = Field(description="Recovery success")
    status: KillSwitchStatus = Field(description="Current status")
    strategy: RecoveryStrategy = Field(description="Strategy used")
    recovered_at: datetime = Field(default_factory=datetime.utcnow, description="Recovery timestamp")
    validation_results: Dict[str, bool] = Field(default_factory=dict, description="Validation results")
    warnings: List[str] = Field(default_factory=list, description="Recovery warnings")
    rollback_available: bool = Field(description="Rollback available")


class IncidentSummary(BaseSchema):
    """Incident summary for listings."""
    id: UUID = Field(description="Incident ID")
    persona_id: UUID = Field(description="Persona ID")
    trigger_type: KillSwitchTrigger = Field(description="Trigger type")
    severity: KillSwitchSeverity = Field(description="Severity level")
    status: KillSwitchStatus = Field(description="Current status")
    triggered_at: datetime = Field(description="Trigger timestamp")
    recovered_at: Optional[datetime] = Field(default=None, description="Recovery timestamp")
    duration_seconds: Optional[int] = Field(default=None, description="Incident duration")


class IncidentDetail(IncidentSummary):
    """Detailed incident information."""
    reason: str = Field(description="Trigger reason")
    trigger_metadata: Dict[str, Any] = Field(default_factory=dict, description="Trigger metadata")
    affected_operations: List[str] = Field(default_factory=list, description="Affected operations")
    cascade_targets: List[UUID] = Field(default_factory=list, description="Cascade targets")
    recovery_strategy: Optional[RecoveryStrategy] = Field(default=None, description="Recovery strategy used")
    recovery_metadata: Dict[str, Any] = Field(default_factory=dict, description="Recovery metadata")
    timeline: List[Dict[str, Any]] = Field(default_factory=list, description="Event timeline")


class IncidentListResponse(PaginatedResponse[IncidentSummary]):
    """Paginated incident list response."""
    pass
