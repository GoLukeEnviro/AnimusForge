"""Kill-Switch API Routes."""
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, status

from ..schemas.base import ErrorResponse, PaginatedResponse
from ..schemas.killswitch import (
    IncidentDetail,
    IncidentListResponse,
    IncidentSummary,
    KillSwitchSeverity,
    KillSwitchStatus,
    KillSwitchTrigger,
    KillSwitchTriggerRequest,
    KillSwitchTriggerResponse,
    KillSwitchStatusResponse,
    RecoveryRequest,
    RecoveryResponse,
    RecoveryStrategy,
)

router = APIRouter(prefix="/killswitch", tags=["Kill-Switch"])


# In-memory incident store (replace with database in production)
_incidents: dict[UUID, IncidentDetail] = {}
_active_killswitches: dict[UUID, UUID] = {}  # persona_id -> incident_id


@router.post(
    "/{persona_id}/trigger",
    response_model=KillSwitchTriggerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Trigger kill-switch",
    description="Trigger the kill-switch for a specific persona to immediately halt operations.",
    responses={
        201: {"description": "Kill-switch triggered successfully"},
        400: {"model": ErrorResponse, "description": "Kill-switch already active"},
        409: {"model": ErrorResponse, "description": "Conflict - persona in recovery"},
    },
)
async def trigger_killswitch(
    persona_id: UUID,
    request: KillSwitchTriggerRequest,
) -> KillSwitchTriggerResponse:
    """Trigger kill-switch for a persona."""
    # Check if kill-switch already active
    if persona_id in _active_killswitches:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Kill-switch already active for persona {persona_id}",
        )

    incident_id = uuid4()
    now = datetime.utcnow()

    # Create incident
    incident = IncidentDetail(
        id=incident_id,
        persona_id=persona_id,
        trigger_type=request.trigger_type,
        severity=request.severity,
        status=KillSwitchStatus.TRIGGERED,
        triggered_at=now,
        reason=request.reason,
        affected_operations=["generation", "memory_access", "external_communication"],
        cascade_targets=[],
        timeline=[
            {
                "timestamp": now.isoformat(),
                "event": "kill_switch_triggered",
                "trigger_type": request.trigger_type.value,
                "severity": request.severity.value,
            }
        ],
    )

    _incidents[incident_id] = incident
    _active_killswitches[persona_id] = incident_id

    # Update incident status to active
    incident.status = KillSwitchStatus.ACTIVE

    # Calculate estimated recovery time based on severity
    recovery_times = {
        KillSwitchSeverity.LOW: 60,
        KillSwitchSeverity.MEDIUM: 300,
        KillSwitchSeverity.HIGH: 900,
        KillSwitchSeverity.CRITICAL: 3600,
        KillSwitchSeverity.EMERGENCY: 86400,
    }

    return KillSwitchTriggerResponse(
        incident_id=incident_id,
        persona_id=persona_id,
        status=KillSwitchStatus.ACTIVE,
        triggered_at=now,
        trigger_type=request.trigger_type,
        severity=request.severity,
        affected_operations=incident.affected_operations,
        cascade_targets=incident.cascade_targets,
        estimated_recovery_time=recovery_times.get(request.severity, 300),
    )


@router.get(
    "/{persona_id}/status",
    response_model=KillSwitchStatusResponse,
    summary="Get kill-switch status",
    description="Retrieve the current kill-switch status for a persona.",
    responses={
        200: {"description": "Kill-switch status"},
    },
)
async def get_killswitch_status(persona_id: UUID) -> KillSwitchStatusResponse:
    """Get kill-switch status for a persona."""
    if persona_id not in _active_killswitches:
        return KillSwitchStatusResponse(
            persona_id=persona_id,
            active=False,
            status=KillSwitchStatus.RECOVERED,
            recovery_available=False,
            recovery_strategies=[],
        )

    incident_id = _active_killswitches[persona_id]
    incident = _incidents[incident_id]

    # Determine available recovery strategies
    strategies = [
        RecoveryStrategy.MANUAL,
        RecoveryStrategy.INCREMENTAL,
    ]

    if incident.severity in [KillSwitchSeverity.LOW, KillSwitchSeverity.MEDIUM]:
        strategies.append(RecoveryStrategy.AUTOMATIC)

    if incident.severity == KillSwitchSeverity.HIGH:
        strategies.append(RecoveryStrategy.CHECKPOINT)

    return KillSwitchStatusResponse(
        persona_id=persona_id,
        active=True,
        status=incident.status,
        incident_id=incident_id,
        triggered_at=incident.triggered_at,
        trigger_type=incident.trigger_type,
        severity=incident.severity,
        reason=incident.reason,
        recovery_available=incident.status == KillSwitchStatus.ACTIVE,
        recovery_strategies=strategies,
    )


@router.post(
    "/{persona_id}/recover",
    response_model=RecoveryResponse,
    summary="Recover from kill-switch",
    description="Initiate recovery process to restore persona operations after kill-switch.",
    responses={
        200: {"description": "Recovery initiated successfully"},
        400: {"model": ErrorResponse, "description": "No active kill-switch"},
        404: {"model": ErrorResponse, "description": "Persona or incident not found"},
    },
)
async def recover_from_killswitch(
    persona_id: UUID,
    request: RecoveryRequest,
) -> RecoveryResponse:
    """Recover persona from kill-switch."""
    if persona_id not in _active_killswitches:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No active kill-switch for persona {persona_id}",
        )

    incident_id = _active_killswitches[persona_id]
    incident = _incidents[incident_id]

    # Simulate validation steps
    validation_results = {}
    for step in request.validation_steps or ["state_check", "memory_integrity", "ethics_clear"]:
        validation_results[step] = True  # Simulated success

    # Auto-validate if enabled
    if request.auto_validate:
        validation_results["auto_validation"] = True

    # Update incident
    incident.status = KillSwitchStatus.RECOVERED
    incident.recovered_at = datetime.utcnow()
    incident.recovery_strategy = request.strategy
    incident.timeline.append({
        "timestamp": datetime.utcnow().isoformat(),
        "event": "recovery_completed",
        "strategy": request.strategy.value,
    })

    # Remove from active kill-switches
    del _active_killswitches[persona_id]

    return RecoveryResponse(
        persona_id=persona_id,
        incident_id=incident_id,
        success=True,
        status=KillSwitchStatus.RECOVERED,
        strategy=request.strategy,
        validation_results=validation_results,
        warnings=[],
        rollback_available=True,
    )


@router.get(
    "/incidents",
    response_model=IncidentListResponse,
    summary="List incidents",
    description="Retrieve a paginated list of kill-switch incidents.",
)
async def list_incidents(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    persona_id: Optional[UUID] = Query(None, description="Filter by persona ID"),
    severity: Optional[KillSwitchSeverity] = Query(None, description="Filter by severity"),
    status: Optional[KillSwitchStatus] = Query(None, description="Filter by status"),
) -> IncidentListResponse:
    """List all kill-switch incidents."""
    # Apply filters
    filtered = list(_incidents.values())

    if persona_id:
        filtered = [i for i in filtered if i.persona_id == persona_id]

    if severity:
        filtered = [i for i in filtered if i.severity == severity]

    if status:
        filtered = [i for i in filtered if i.status == status]

    # Sort by trigger date (newest first)
    filtered.sort(key=lambda i: i.triggered_at, reverse=True)

    # Paginate
    total = len(filtered)
    start = (page - 1) * page_size
    end = start + page_size
    items = filtered[start:end]

    # Create summaries
    summaries = [
        IncidentSummary(
            id=i.id,
            persona_id=i.persona_id,
            trigger_type=i.trigger_type,
            severity=i.severity,
            status=i.status,
            triggered_at=i.triggered_at,
            recovered_at=i.recovered_at,
            duration_seconds=(
                int((i.recovered_at - i.triggered_at).total_seconds())
                if i.recovered_at else None
            ),
        )
        for i in items
    ]

    return IncidentListResponse.create(
        items=summaries,
        total=total,
        page=page,
        page_size=page_size,
    )
