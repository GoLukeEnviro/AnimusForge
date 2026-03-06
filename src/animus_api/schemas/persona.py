"""Persona management schemas."""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from .base import BaseSchema, PaginatedResponse, TimestampMixin, UUIDMixin


class PersonaStatus(str, Enum):
    """Persona status enumeration."""
    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    EVOLVING = "evolving"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class PersonaArchetype(str, Enum):
    """Persona archetype enumeration."""
    ANALYST = "analyst"
    CREATOR = "creator"
    MANAGER = "manager"
    ADVISOR = "advisor"
    EXECUTOR = "executor"
    RESEARCHER = "researcher"
    DIPLOMAT = "diplomat"
    GUARDIAN = "guardian"


class EmotionalState(str, Enum):
    """Emotional state enumeration."""
    NEUTRAL = "neutral"
    CURIOUS = "curious"
    FOCUSED = "focused"
    CAUTIOUS = "cautious"
    CONFIDENT = "confident"
    EMPATHETIC = "empathetic"
    ANALYTICAL = "analytical"
    CREATIVE = "creative"


class PersonalityTrait(BaseSchema):
    """Personality trait definition."""
    name: str = Field(description="Trait name")
    value: float = Field(ge=0.0, le=1.0, description="Trait value (0-1)")
    description: Optional[str] = Field(default=None, description="Trait description")


class CognitivePattern(BaseSchema):
    """Cognitive pattern definition."""
    pattern_type: str = Field(description="Pattern type")
    strength: float = Field(ge=0.0, le=1.0, description="Pattern strength")
    triggers: List[str] = Field(default_factory=list, description="Pattern triggers")


class PersonaConfig(BaseSchema):
    """Persona configuration."""
    max_tokens: int = Field(default=4096, ge=1, description="Maximum tokens per response")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Response temperature")
    top_p: float = Field(default=0.9, ge=0.0, le=1.0, description="Top-p sampling")
    frequency_penalty: float = Field(default=0.0, ge=-2.0, le=2.0, description="Frequency penalty")
    presence_penalty: float = Field(default=0.0, ge=-2.0, le=2.0, description="Presence penalty")
    response_format: str = Field(default="text", description="Response format")
    system_prompt: Optional[str] = Field(default=None, description="Custom system prompt")


class PersonaCreate(BaseSchema):
    """Schema for creating a new persona."""
    name: str = Field(min_length=1, max_length=100, description="Persona name")
    description: Optional[str] = Field(default=None, max_length=2000, description="Persona description")
    archetype: PersonaArchetype = Field(description="Persona archetype")
    traits: List[PersonalityTrait] = Field(default_factory=list, description="Personality traits")
    cognitive_patterns: List[CognitivePattern] = Field(default_factory=list, description="Cognitive patterns")
    config: PersonaConfig = Field(default_factory=PersonaConfig, description="Persona configuration")
    capabilities: List[str] = Field(default_factory=list, description="Enabled capabilities")
    restrictions: List[str] = Field(default_factory=list, description="Applied restrictions")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    tags: List[str] = Field(default_factory=list, description="Tags for organization")


class PersonaUpdate(BaseSchema):
    """Schema for updating a persona."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=100, description="Persona name")
    description: Optional[str] = Field(default=None, max_length=2000, description="Persona description")
    archetype: Optional[PersonaArchetype] = Field(default=None, description="Persona archetype")
    traits: Optional[List[PersonalityTrait]] = Field(default=None, description="Personality traits")
    cognitive_patterns: Optional[List[CognitivePattern]] = Field(default=None, description="Cognitive patterns")
    config: Optional[PersonaConfig] = Field(default=None, description="Persona configuration")
    capabilities: Optional[List[str]] = Field(default=None, description="Enabled capabilities")
    restrictions: Optional[List[str]] = Field(default=None, description="Applied restrictions")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")
    tags: Optional[List[str]] = Field(default=None, description="Tags for organization")


class PersonaState(BaseSchema):
    """Current persona state."""
    status: PersonaStatus = Field(description="Current status")
    emotional_state: EmotionalState = Field(description="Current emotional state")
    active_context: Optional[str] = Field(default=None, description="Active context ID")
    last_interaction: Optional[datetime] = Field(default=None, description="Last interaction timestamp")
    interaction_count: int = Field(default=0, ge=0, description="Total interaction count")
    evolution_generation: int = Field(default=0, ge=0, description="Evolution generation")
    health_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Health score (0-1)")
    coherence_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Coherence score (0-1)")
    adaptation_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Adaptation rate")


class PersonaHealth(BaseSchema):
    """Persona health status."""
    persona_id: UUID = Field(description="Persona ID")
    healthy: bool = Field(description="Overall health status")
    health_score: float = Field(ge=0.0, le=1.0, description="Health score")
    components: Dict[str, float] = Field(description="Component health scores")
    issues: List[str] = Field(default_factory=list, description="Detected issues")
    recommendations: List[str] = Field(default_factory=list, description="Health recommendations")
    last_check: datetime = Field(default_factory=datetime.utcnow, description="Last health check")


class PersonaEvolutionRequest(BaseSchema):
    """Request to trigger persona evolution."""
    evolution_type: str = Field(default="adaptive", description="Evolution type")
    target_traits: Optional[List[str]] = Field(default=None, description="Target traits to evolve")
    intensity: float = Field(default=0.1, ge=0.01, le=1.0, description="Evolution intensity")
    preserve_core: bool = Field(default=True, description="Preserve core traits")
    constraints: Dict[str, Any] = Field(default_factory=dict, description="Evolution constraints")


class PersonaEvolutionResponse(BaseSchema):
    """Response after persona evolution."""
    persona_id: UUID = Field(description="Persona ID")
    evolution_id: UUID = Field(description="Evolution session ID")
    status: str = Field(description="Evolution status")
    changes: Dict[str, Any] = Field(description="Applied changes")
    previous_state: Dict[str, Any] = Field(description="Previous state snapshot")
    new_state: Dict[str, Any] = Field(description="New state snapshot")
    evolved_at: datetime = Field(default_factory=datetime.utcnow, description="Evolution timestamp")


class PersonaResponse(UUIDMixin, TimestampMixin):
    """Full persona response."""
    name: str = Field(description="Persona name")
    description: Optional[str] = Field(default=None, description="Persona description")
    archetype: PersonaArchetype = Field(description="Persona archetype")
    status: PersonaStatus = Field(default=PersonaStatus.DRAFT, description="Current status")
    traits: List[PersonalityTrait] = Field(default_factory=list, description="Personality traits")
    cognitive_patterns: List[CognitivePattern] = Field(default_factory=list, description="Cognitive patterns")
    config: PersonaConfig = Field(default_factory=PersonaConfig, description="Persona configuration")
    capabilities: List[str] = Field(default_factory=list, description="Enabled capabilities")
    restrictions: List[str] = Field(default_factory=list, description="Applied restrictions")
    state: PersonaState = Field(default_factory=PersonaState, description="Current state")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    tags: List[str] = Field(default_factory=list, description="Tags for organization")
    version: int = Field(default=1, ge=1, description="Persona version")


class PersonaSummary(BaseSchema):
    """Lightweight persona summary for listings."""
    id: UUID = Field(description="Persona ID")
    name: str = Field(description="Persona name")
    archetype: PersonaArchetype = Field(description="Persona archetype")
    status: PersonaStatus = Field(description="Current status")
    health_score: float = Field(description="Health score")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")


class PersonaListResponse(PaginatedResponse[PersonaSummary]):
    """Paginated persona list response."""
    pass
