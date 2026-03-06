"""Persona Management API Routes."""
from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from ..schemas.base import ErrorResponse, PaginatedResponse
from ..schemas.persona import (
    PersonaCreate,
    PersonaEvolutionRequest,
    PersonaEvolutionResponse,
    PersonaHealth,
    PersonaListResponse,
    PersonaResponse,
    PersonaState,
    PersonaSummary,
    PersonaUpdate,
    PersonaStatus,
)

router = APIRouter(prefix="/personas", tags=["Persona Management"])


# In-memory store for demo (replace with database in production)
_personas_db: dict[UUID, PersonaResponse] = {}


@router.post(
    "",
    response_model=PersonaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new persona",
    description="Create a new AI persona with specified traits, archetype, and configuration.",
    responses={
        201: {"description": "Persona created successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request data"},
        409: {"model": ErrorResponse, "description": "Persona with this name already exists"},
    },
)
async def create_persona(persona: PersonaCreate) -> PersonaResponse:
    """Create a new AI persona."""
    # Check for duplicate name
    for existing in _personas_db.values():
        if existing.name == persona.name:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Persona with name '{persona.name}' already exists",
            )

    persona_id = uuid4()
    now = datetime.utcnow()

    response = PersonaResponse(
        id=persona_id,
        name=persona.name,
        description=persona.description,
        archetype=persona.archetype,
        status=PersonaStatus.DRAFT,
        traits=persona.traits,
        cognitive_patterns=persona.cognitive_patterns,
        config=persona.config,
        capabilities=persona.capabilities,
        restrictions=persona.restrictions,
        state=PersonaState(),
        metadata=persona.metadata,
        tags=persona.tags,
        version=1,
        created_at=now,
        updated_at=now,
    )

    _personas_db[persona_id] = response
    return response


@router.get(
    "",
    response_model=PersonaListResponse,
    summary="List all personas",
    description="Retrieve a paginated list of all personas with optional filtering.",
)
async def list_personas(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[PersonaStatus] = Query(None, description="Filter by status"),
    archetype: Optional[str] = Query(None, description="Filter by archetype"),
    search: Optional[str] = Query(None, description="Search in name and description"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
) -> PersonaListResponse:
    """List all personas with pagination and filtering."""
    # Apply filters
    filtered = list(_personas_db.values())

    if status:
        filtered = [p for p in filtered if p.status == status]

    if archetype:
        filtered = [p for p in filtered if p.archetype.value == archetype]

    if search:
        search_lower = search.lower()
        filtered = [
            p for p in filtered
            if search_lower in p.name.lower()
            or (p.description and search_lower in p.description.lower())
        ]

    if tag:
        filtered = [p for p in filtered if tag in p.tags]

    # Sort by creation date (newest first)
    filtered.sort(key=lambda p: p.created_at, reverse=True)

    # Paginate
    total = len(filtered)
    start = (page - 1) * page_size
    end = start + page_size
    items = filtered[start:end]

    # Create summaries
    summaries = [
        PersonaSummary(
            id=p.id,
            name=p.name,
            archetype=p.archetype,
            status=p.status,
            health_score=p.state.health_score,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in items
    ]

    return PersonaListResponse.create(
        items=summaries,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{persona_id}",
    response_model=PersonaResponse,
    summary="Get persona by ID",
    description="Retrieve detailed information about a specific persona.",
    responses={
        200: {"description": "Persona details"},
        404: {"model": ErrorResponse, "description": "Persona not found"},
    },
)
async def get_persona(persona_id: UUID) -> PersonaResponse:
    """Get a specific persona by ID."""
    if persona_id not in _personas_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona with ID {persona_id} not found",
        )
    return _personas_db[persona_id]


@router.put(
    "/{persona_id}",
    response_model=PersonaResponse,
    summary="Update persona",
    description="Update an existing persona's configuration and properties.",
    responses={
        200: {"description": "Persona updated successfully"},
        404: {"model": ErrorResponse, "description": "Persona not found"},
        400: {"model": ErrorResponse, "description": "Invalid update data"},
    },
)
async def update_persona(
    persona_id: UUID,
    update: PersonaUpdate,
) -> PersonaResponse:
    """Update an existing persona."""
    if persona_id not in _personas_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona with ID {persona_id} not found",
        )

    existing = _personas_db[persona_id]
    update_data = update.model_dump(exclude_unset=True)

    # Create updated persona
    updated_dict = existing.model_dump()
    updated_dict.update(update_data)
    updated_dict["updated_at"] = datetime.utcnow()
    updated_dict["version"] = existing.version + 1

    updated_persona = PersonaResponse(**updated_dict)
    _personas_db[persona_id] = updated_persona

    return updated_persona


@router.delete(
    "/{persona_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete persona",
    description="Permanently delete a persona.",
    responses={
        204: {"description": "Persona deleted successfully"},
        404: {"model": ErrorResponse, "description": "Persona not found"},
    },
)
async def delete_persona(persona_id: UUID) -> None:
    """Delete a persona."""
    if persona_id not in _personas_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona with ID {persona_id} not found",
        )

    del _personas_db[persona_id]


@router.post(
    "/{persona_id}/activate",
    response_model=PersonaResponse,
    summary="Activate persona",
    description="Activate a persona for production use.",
    responses={
        200: {"description": "Persona activated successfully"},
        404: {"model": ErrorResponse, "description": "Persona not found"},
        400: {"model": ErrorResponse, "description": "Cannot activate persona"},
    },
)
async def activate_persona(persona_id: UUID) -> PersonaResponse:
    """Activate a persona."""
    if persona_id not in _personas_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona with ID {persona_id} not found",
        )

    persona = _personas_db[persona_id]

    if persona.status == PersonaStatus.SUSPENDED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot activate a suspended persona",
        )

    updated_dict = persona.model_dump()
    updated_dict["status"] = PersonaStatus.ACTIVE
    updated_dict["updated_at"] = datetime.utcnow()
    updated_dict["state"]["status"] = PersonaStatus.ACTIVE

    updated_persona = PersonaResponse(**updated_dict)
    _personas_db[persona_id] = updated_persona

    return updated_persona


@router.post(
    "/{persona_id}/deactivate",
    response_model=PersonaResponse,
    summary="Deactivate persona",
    description="Deactivate a persona from production use.",
    responses={
        200: {"description": "Persona deactivated successfully"},
        404: {"model": ErrorResponse, "description": "Persona not found"},
    },
)
async def deactivate_persona(persona_id: UUID) -> PersonaResponse:
    """Deactivate a persona."""
    if persona_id not in _personas_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona with ID {persona_id} not found",
        )

    persona = _personas_db[persona_id]

    updated_dict = persona.model_dump()
    updated_dict["status"] = PersonaStatus.INACTIVE
    updated_dict["updated_at"] = datetime.utcnow()
    updated_dict["state"]["status"] = PersonaStatus.INACTIVE

    updated_persona = PersonaResponse(**updated_dict)
    _personas_db[persona_id] = updated_persona

    return updated_persona


@router.get(
    "/{persona_id}/state",
    response_model=PersonaState,
    summary="Get persona state",
    description="Retrieve the current state of a persona.",
    responses={
        200: {"description": "Persona state"},
        404: {"model": ErrorResponse, "description": "Persona not found"},
    },
)
async def get_persona_state(persona_id: UUID) -> PersonaState:
    """Get the current state of a persona."""
    if persona_id not in _personas_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona with ID {persona_id} not found",
        )

    return _personas_db[persona_id].state


@router.post(
    "/{persona_id}/evolve",
    response_model=PersonaEvolutionResponse,
    summary="Trigger persona evolution",
    description="Initiate an evolution process for the persona to adapt and improve.",
    responses={
        200: {"description": "Evolution triggered successfully"},
        404: {"model": ErrorResponse, "description": "Persona not found"},
        400: {"model": ErrorResponse, "description": "Evolution not possible"},
    },
)
async def evolve_persona(
    persona_id: UUID,
    request: PersonaEvolutionRequest,
) -> PersonaEvolutionResponse:
    """Trigger persona evolution."""
    if persona_id not in _personas_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona with ID {persona_id} not found",
        )

    persona = _personas_db[persona_id]

    if persona.status not in [PersonaStatus.ACTIVE, PersonaStatus.INACTIVE]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot evolve persona in {persona.status} status",
        )

    # Capture previous state
    previous_state = persona.state.model_dump()

    # Simulate evolution (in production, this would be AI-driven)
    evolution_id = uuid4()
    changes = {
        "evolution_type": request.evolution_type,
        "intensity": request.intensity,
        "traits_adjusted": request.target_traits or [],
    }

    # Update persona
    updated_dict = persona.model_dump()
    updated_dict["state"]["evolution_generation"] += 1
    updated_dict["updated_at"] = datetime.utcnow()

    new_state = updated_dict["state"]

    updated_persona = PersonaResponse(**updated_dict)
    _personas_db[persona_id] = updated_persona

    return PersonaEvolutionResponse(
        persona_id=persona_id,
        evolution_id=evolution_id,
        status="completed",
        changes=changes,
        previous_state=previous_state,
        new_state=new_state,
    )


@router.get(
    "/{persona_id}/health",
    response_model=PersonaHealth,
    summary="Get persona health",
    description="Check the health status of a persona.",
    responses={
        200: {"description": "Persona health status"},
        404: {"model": ErrorResponse, "description": "Persona not found"},
    },
)
async def get_persona_health(persona_id: UUID) -> PersonaHealth:
    """Check persona health status."""
    if persona_id not in _personas_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona with ID {persona_id} not found",
        )

    persona = _personas_db[persona_id]

    # Calculate component health scores
    components = {
        "coherence": persona.state.coherence_score,
        "stability": persona.state.health_score,
        "adaptation": persona.state.adaptation_rate,
        "interaction": min(1.0, persona.state.interaction_count / 100),
    }

    # Detect issues
    issues = []
    if persona.state.coherence_score < 0.7:
        issues.append("Low coherence score detected")
    if persona.state.health_score < 0.5:
        issues.append("Health score below threshold")

    # Generate recommendations
    recommendations = []
    if persona.state.interaction_count < 10:
        recommendations.append("Consider more training interactions")
    if persona.state.evolution_generation < 2:
        recommendations.append("Evolution process recommended")

    return PersonaHealth(
        persona_id=persona_id,
        healthy=persona.state.health_score > 0.7,
        health_score=persona.state.health_score,
        components=components,
        issues=issues,
        recommendations=recommendations,
    )
