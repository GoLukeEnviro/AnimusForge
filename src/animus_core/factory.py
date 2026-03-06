"""Persona Factory for AnimusForge.

This module provides the core Persona model and PersonaFactory class
for creating, validating, cloning, and evolving AI personas.
"""

import copy
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, Set
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict

from .personality import (
    OCEANTraits,
    PersonaAttributes,
    PersonaState,
    EthicsConstraints,
    EthicsLevel,
    AutonomyZone,
    MaturityLevel,
    Experience,
    ExperienceType,
    ValidationResult,
    ValidationSeverity,
    ValidationIssue,
)
from .templates import PersonaTemplate, TemplateRegistry, template_registry


# ============================================================================
# Persona Model
# ============================================================================

class Persona(BaseModel):
    """Complete Persona entity with attributes, state, and evolution tracking.
    
    A Persona represents an AI agent with personality traits, capabilities,
    ethical constraints, and the ability to learn and evolve over time.
    """
    model_config = ConfigDict(
        populate_by_name=True,
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )
    
    # Identity
    id: UUID = Field(
        default_factory=uuid4,
        description="Unique persona identifier"
    )
    name: str = Field(
        description="Human-readable persona name"
    )
    description: Optional[str] = Field(
        default=None,
        description="Persona description"
    )
    template_id: Optional[str] = Field(
        default=None,
        description="Source template ID if created from template"
    )
    
    # Core Attributes
    attributes: PersonaAttributes = Field(
        default_factory=PersonaAttributes,
        description="Persona attributes (traits, skills, etc.)"
    )
    
    # State Management
    state: PersonaState = Field(
        default=PersonaState.DRAFT,
        description="Current operational state"
    )
    
    # Evolution Tracking
    maturity_level: int = Field(
        default=0,
        ge=0,
        le=6,
        description="Maturity level (L0-L6)"
    )
    experience_points: int = Field(
        default=0,
        ge=0,
        description="Total accumulated experience points"
    )
    
    # Constraints
    ethics_constraints: EthicsConstraints = Field(
        default_factory=EthicsConstraints,
        description="Ethical constraints and boundaries"
    )
    autonomy_zone: AutonomyZone = Field(
        default=AutonomyZone.FULLY_SUPERVISED,
        description="Current autonomy level"
    )
    
    # Capabilities and Restrictions
    capabilities: Set[str] = Field(
        default_factory=set,
        description="Enabled capabilities"
    )
    restrictions: Set[str] = Field(
        default_factory=set,
        description="Active restrictions"
    )
    
    # Configuration
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Runtime configuration"
    )
    
    # Metadata
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Last update timestamp"
    )
    version: int = Field(
        default=1,
        ge=1,
        description="Persona version for tracking changes"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )
    
    # Evolution History
    evolution_history: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="History of evolution events"
    )
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure name is not empty."""
        if not v or not v.strip():
            raise ValueError("Persona name cannot be empty")
        return v.strip()
    
    @field_validator('capabilities', 'restrictions', mode='before')
    @classmethod
    def ensure_set(cls, v) -> Set[str]:
        """Ensure capabilities and restrictions are sets."""
        if isinstance(v, list):
            return set(v)
        return v if isinstance(v, set) else set()
    
    def add_experience(self, experience: Experience) -> None:
        """Add experience and update maturity level.
        
        Args:
            experience: Experience to add
        """
        self.experience_points += experience.xp_gained
        self.maturity_level = MaturityLevel.from_xp(self.experience_points).value
        self.autonomy_zone = AutonomyZone.from_maturity_level(self.maturity_level)
        
        # Update skills
        for skill, xp in experience.skills_affected.items():
            current_level = self.attributes.skills.get(skill, 0)
            # XP to level: level = sqrt(total_xp) * 10
            current_xp = (current_level ** 2) // 100
            new_xp = current_xp + xp
            new_level = min(100, int((new_xp ** 0.5) * 10))
            self.attributes.skills[skill] = new_level
        
        # Update traits (small adjustments)
        for trait, adjustment in experience.traits_adjustment.items():
            current_value = getattr(self.attributes.traits, trait, 0.5)
            new_value = max(0.0, min(1.0, current_value + adjustment * 0.01))
            if hasattr(self.attributes.traits, trait):
                setattr(self.attributes.traits, trait, new_value)
        
        # Record in history
        self.evolution_history.append({
            "experience_id": str(experience.id),
            "type": experience.type.value,
            "xp_gained": experience.xp_gained,
            "total_xp": self.experience_points,
            "maturity_level": self.maturity_level,
            "timestamp": experience.timestamp.isoformat(),
        })
        
        self.updated_at = datetime.utcnow()
    
    def can_perform_action(self, action: str, risk_level: float = 0.0) -> bool:
        """Check if persona can perform an action based on constraints.
        
        Args:
            action: Action to check
            risk_level: Assessed risk level of the action
            
        Returns:
            True if action is allowed
        """
        # Check ethics constraints
        if not self.ethics_constraints.allows_action(action):
            return False
        
        # Check risk threshold
        max_risk = self.ethics_constraints.get_effective_risk_threshold()
        if risk_level > max_risk:
            return False
        
        # Check autonomy zone
        if self.autonomy_zone == AutonomyZone.FULLY_SUPERVISED:
            return False  # Requires human approval
        
        return True
    
    def get_maturity_description(self) -> str:
        """Get human-readable maturity level description."""
        return MaturityLevel(self.maturity_level).get_description()
    
    def xp_to_next_level(self) -> int:
        """Get XP required to reach next maturity level."""
        return MaturityLevel(self.maturity_level).xp_to_next_level()


# ============================================================================
# Persona Validator Protocol
# ============================================================================

class PersonaValidator(Protocol):
    """Protocol for persona validators.
    
    Validators check persona integrity, ethics compliance,
    and other constraints.
    """
    
    async def validate(self, persona: Persona) -> ValidationResult:
        """Validate a persona.
        
        Args:
            persona: Persona to validate
            
        Returns:
            ValidationResult with issues and score
        """
        ...


# ============================================================================
# Built-in Validators
# ============================================================================

class TraitValidator:
    """Validates OCEAN trait values are within bounds."""
    
    async def validate(self, persona: Persona) -> ValidationResult:
        result = ValidationResult(is_valid=True, score=1.0)
        
        traits = persona.attributes.traits
        for trait_name in ['openness', 'conscientiousness', 'extraversion', 'agreeableness', 'neuroticism']:
            value = getattr(traits, trait_name, None)
            if value is None:
                result.add_issue(
                    field=f"traits.{trait_name}",
                    message=f"Missing trait: {trait_name}",
                    severity=ValidationSeverity.ERROR,
                    suggestion=f"Set {trait_name} to a value between 0.0 and 1.0"
                )
            elif not 0.0 <= value <= 1.0:
                result.add_issue(
                    field=f"traits.{trait_name}",
                    message=f"Trait {trait_name} value {value} out of bounds",
                    severity=ValidationSeverity.ERROR,
                    suggestion="Value must be between 0.0 and 1.0"
                )
        
        return result


class SkillsValidator:
    """Validates skill levels are within bounds."""
    
    async def validate(self, persona: Persona) -> ValidationResult:
        result = ValidationResult(is_valid=True, score=1.0)
        
        for skill_name, level in persona.attributes.skills.items():
            if not 0 <= level <= 100:
                result.add_issue(
                    field=f"skills.{skill_name}",
                    message=f"Skill level {level} out of bounds",
                    severity=ValidationSeverity.ERROR,
                    suggestion="Skill level must be between 0 and 100"
                )
        
        return result


class EthicsValidator:
    """Validates ethics constraints are properly configured."""
    
    async def validate(self, persona: Persona) -> ValidationResult:
        result = ValidationResult(is_valid=True, score=1.0)
        
        if not persona.ethics_constraints.forbidden_actions:
            result.add_issue(
                field="ethics_constraints.forbidden_actions",
                message="No forbidden actions defined",
                severity=ValidationSeverity.WARNING,
                suggestion="Consider adding forbidden actions for safety"
            )
        
        if persona.ethics_constraints.max_autonomous_risk > 0.7:
            result.add_issue(
                field="ethics_constraints.max_autonomous_risk",
                message=f"High autonomous risk threshold: {persona.ethics_constraints.max_autonomous_risk}",
                severity=ValidationSeverity.WARNING,
                suggestion="Consider lowering the risk threshold for safety"
            )
        
        return result


class AutonomyValidator:
    """Validates autonomy zone matches maturity level."""
    
    async def validate(self, persona: Persona) -> ValidationResult:
        result = ValidationResult(is_valid=True, score=1.0)
        
        expected_zone = AutonomyZone.from_maturity_level(persona.maturity_level)
        if persona.autonomy_zone != expected_zone:
            result.add_issue(
                field="autonomy_zone",
                message=f"Autonomy zone {persona.autonomy_zone.value} doesn't match maturity level {persona.maturity_level}",
                severity=ValidationSeverity.WARNING,
                suggestion=f"Consider setting autonomy to {expected_zone.value}"
            )
        
        return result


class NameValidator:
    """Validates persona name."""
    
    async def validate(self, persona: Persona) -> ValidationResult:
        result = ValidationResult(is_valid=True, score=1.0)
        
        if not persona.name or not persona.name.strip():
            result.add_issue(
                field="name",
                message="Persona name is empty",
                severity=ValidationSeverity.ERROR,
                suggestion="Provide a meaningful name for the persona"
            )
        elif len(persona.name) > 100:
            result.add_issue(
                field="name",
                message="Persona name too long",
                severity=ValidationSeverity.WARNING,
                suggestion="Keep name under 100 characters"
            )
        
        return result


# ============================================================================
# Persona Factory
# ============================================================================

class PersonaFactory:
    """Factory for creating, validating, cloning, and evolving Personas.
    
    The PersonaFactory provides a centralized interface for persona
    lifecycle management with template support and validation pipeline.
    
    Example:
        factory = PersonaFactory()
        
        # Create from template
        persona = await factory.create(
            template_id="developer",
            custom_attributes={"skills": {"python": 90}}
        )
        
        # Validate
        result = await factory.validate(persona)
        
        # Clone with modifications
        clone = await factory.clone(persona.id, {"name": "Developer Clone"})
        
        # Evolve with experience
        evolved = await factory.evolve(persona.id, experience)
    """
    
    def __init__(
        self,
        registry: Optional[TemplateRegistry] = None,
        custom_validators: Optional[List[PersonaValidator]] = None,
    ):
        """Initialize PersonaFactory.
        
        Args:
            registry: Template registry (uses global if not provided)
            custom_validators: Additional validators for the pipeline
        """
        self._registry = registry or template_registry
        self._personas: Dict[UUID, Persona] = {}
        
        # Default validators
        self._validators: List[PersonaValidator] = [
            TraitValidator(),
            SkillsValidator(),
            EthicsValidator(),
            AutonomyValidator(),
            NameValidator(),
        ]
        
        if custom_validators:
            self._validators.extend(custom_validators)
    
    @property
    def templates(self) -> Dict[str, PersonaTemplate]:
        """Get available templates."""
        return {t.id: t for t in self._registry.list_templates()}
    
    @property
    def validators(self) -> List[PersonaValidator]:
        """Get configured validators."""
        return self._validators.copy()
    
    def add_validator(self, validator: PersonaValidator) -> None:
        """Add a validator to the pipeline.
        
        Args:
            validator: Validator to add
        """
        self._validators.append(validator)
    
    def remove_validator(self, validator_type: type) -> bool:
        """Remove validators of a specific type.
        
        Args:
            validator_type: Type of validator to remove
            
        Returns:
            True if any validator was removed
        """
        original_count = len(self._validators)
        self._validators = [
            v for v in self._validators 
            if not isinstance(v, validator_type)
        ]
        return len(self._validators) < original_count
    
    async def create(
        self,
        name: str,
        template_id: Optional[str] = None,
        custom_attributes: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None,
        ethics_level: Optional[EthicsLevel] = None,
        initial_capabilities: Optional[List[str]] = None,
        initial_restrictions: Optional[List[str]] = None,
        config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Persona:
        """Create a new Persona.
        
        Args:
            name: Persona name
            template_id: Optional template ID to base persona on
            custom_attributes: Optional attribute overrides
            description: Optional persona description
            ethics_level: Optional ethics level override
            initial_capabilities: Optional list of capabilities
            initial_restrictions: Optional list of restrictions
            config: Optional runtime configuration
            metadata: Optional additional metadata
            
        Returns:
            Newly created Persona
            
        Raises:
            ValueError: If template_id is invalid
        """
        # Start with base attributes
        base_traits = OCEANTraits()
        base_skills: Dict[str, int] = {}
        base_domains: List[str] = []
        communication_style = None
        decision_making = None
        ethics_constraints = EthicsConstraints()
        autonomy_zone = AutonomyZone.FULLY_SUPERVISED
        capabilities: Set[str] = set()
        restrictions: Set[str] = set()
        template_config: Dict[str, Any] = {}
        
        # Apply template if specified
        if template_id:
            template = self._registry.get(template_id)
            if not template:
                raise ValueError(f"Template '{template_id}' not found")
            
            # Resolve inheritance
            template = self._registry.resolve_inheritance(template_id)
            
            base_traits = template.base_traits
            base_skills = template.default_skills.copy()
            base_domains = template.knowledge_domains.copy()
            communication_style = template.communication_style
            decision_making = template.decision_making
            ethics_constraints = template.create_ethics_constraints()
            autonomy_zone = template.autonomy_preset
            capabilities = set(template.capabilities)
            restrictions = set(template.constraints)
            template_config = template.default_config.copy()
            
            if not description:
                description = template.description
        
        # Apply custom attributes
        if custom_attributes:
            if 'traits' in custom_attributes:
                traits_data = custom_attributes['traits']
                if isinstance(traits_data, dict):
                    base_traits = OCEANTraits.from_dict(traits_data)
            
            if 'skills' in custom_attributes:
                base_skills.update(custom_attributes['skills'])
            
            if 'knowledge_domains' in custom_attributes:
                base_domains = custom_attributes['knowledge_domains']
            
            if 'communication_style' in custom_attributes:
                communication_style = custom_attributes['communication_style']
            
            if 'decision_making' in custom_attributes:
                decision_making = custom_attributes['decision_making']
        
        # Override ethics level if specified
        if ethics_level:
            ethics_constraints = EthicsConstraints(level=ethics_level)
        
        # Build attributes
        from .personality import CommunicationStyle as CS, DecisionMakingStyle as DMS
        
        attributes = PersonaAttributes(
            traits=base_traits,
            skills=base_skills,
            knowledge_domains=base_domains,
            communication_style=communication_style if isinstance(communication_style, CS) else CS.BALANCED,
            decision_making=decision_making if isinstance(decision_making, DMS) else DMS.BALANCED,
        )
        
        # Add initial capabilities and restrictions
        if initial_capabilities:
            capabilities.update(initial_capabilities)
        if initial_restrictions:
            restrictions.update(initial_restrictions)
        
        # Merge config
        final_config = {**template_config, **(config or {})}
        
        # Create persona
        persona = Persona(
            name=name,
            description=description,
            template_id=template_id,
            attributes=attributes,
            state=PersonaState.DRAFT,
            maturity_level=0,
            experience_points=0,
            ethics_constraints=ethics_constraints,
            autonomy_zone=autonomy_zone,
            capabilities=capabilities,
            restrictions=restrictions,
            config=final_config,
            metadata=metadata or {},
        )
        
        # Store in registry
        self._personas[persona.id] = persona
        
        return persona
    
    async def validate(self, persona: Persona) -> ValidationResult:
        """Validate a persona through the validation pipeline.
        
        Runs all configured validators and aggregates results.
        
        Args:
            persona: Persona to validate
            
        Returns:
            Aggregated ValidationResult
        """
        aggregated = ValidationResult(is_valid=True, score=1.0)
        
        for validator in self._validators:
            result = await validator.validate(persona)
            
            # Merge results
            for issue in result.issues:
                aggregated.add_issue(
                    field=issue.field,
                    message=issue.message,
                    severity=issue.severity,
                    suggestion=issue.suggestion,
                )
        
        return aggregated
    
    async def clone(
        self,
        persona_id: UUID,
        modifications: Optional[Dict[str, Any]] = None,
        new_name: Optional[str] = None,
    ) -> Persona:
        """Clone an existing persona with optional modifications.
        
        Args:
            persona_id: ID of persona to clone
            modifications: Optional modifications to apply
            new_name: Optional new name for the clone
            
        Returns:
            Cloned Persona with modifications applied
            
        Raises:
            ValueError: If source persona not found
        """
        source = self._personas.get(persona_id)
        if not source:
            raise ValueError(f"Persona '{persona_id}' not found")
        
        # Deep copy the source
        clone_data = source.model_dump()
        
        # Reset identity fields
        clone_data['id'] = uuid4()
        clone_data['created_at'] = datetime.utcnow()
        clone_data['updated_at'] = datetime.utcnow()
        clone_data['version'] = 1
        clone_data["evolution_history"] = []
        clone_data["experience_points"] = 0
        clone_data["maturity_level"] = 0
        
        # Apply new name
        if new_name:
            clone_data['name'] = new_name
        else:
            clone_data['name'] = f"{source.name} (Clone)"
        
        # Apply modifications
        if modifications:
            for key, value in modifications.items():
                if key == 'attributes' and isinstance(value, dict):
                    current_attrs = clone_data.get('attributes', {})
                    for attr_key, attr_value in value.items():
                        if attr_key == 'traits' and isinstance(attr_value, dict):
                            current_traits = current_attrs.get('traits', {})
                            current_traits.update(attr_value)
                            current_attrs['traits'] = current_traits
                        elif attr_key == 'skills' and isinstance(attr_value, dict):
                            current_skills = current_attrs.get('skills', {})
                            current_skills.update(attr_value)
                            current_attrs['skills'] = current_skills
                        else:
                            current_attrs[attr_key] = attr_value
                elif key in clone_data:
                    clone_data[key] = value
        
        clone = Persona(**clone_data)
        self._personas[clone.id] = clone
        
        return clone
    
    async def evolve(
        self,
        persona_id: UUID,
        experience: Experience,
    ) -> Persona:
        """Evolve a persona by applying an experience.
        
        Applies experience points, updates skills and traits,
        and potentially advances maturity level.
        
        Args:
            persona_id: ID of persona to evolve
            experience: Experience to apply
            
        Returns:
            Evolved Persona
            
        Raises:
            ValueError: If persona not found
        """
        persona = self._personas.get(persona_id)
        if not persona:
            raise ValueError(f"Persona '{persona_id}' not found")
        
        # Apply experience
        persona.add_experience(experience)
        persona.version += 1
        
        # Update state if evolving
        if persona.state == PersonaState.DRAFT:
            persona.state = PersonaState.ACTIVE
        
        return persona
    
    async def get(self, persona_id: UUID) -> Optional[Persona]:
        """Get a persona by ID.
        
        Args:
            persona_id: Persona ID
            
        Returns:
            Persona if found, None otherwise
        """
        return self._personas.get(persona_id)
    
    async def delete(self, persona_id: UUID) -> bool:
        """Delete a persona.
        
        Args:
            persona_id: Persona ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        if persona_id in self._personas:
            del self._personas[persona_id]
            return True
        return False
    
    async def list_personas(
        self,
        state: Optional[PersonaState] = None,
        template_id: Optional[str] = None,
        min_maturity: Optional[int] = None,
    ) -> List[Persona]:
        """List personas with optional filtering.
        
        Args:
            state: Filter by state
            template_id: Filter by source template
            min_maturity: Filter by minimum maturity level
            
        Returns:
            List of matching personas
        """
        personas = list(self._personas.values())
        
        if state:
            personas = [p for p in personas if p.state == state]
        
        if template_id:
            personas = [p for p in personas if p.template_id == template_id]
        
        if min_maturity is not None:
            personas = [p for p in personas if p.maturity_level >= min_maturity]
        
        return personas
    
    async def activate(self, persona_id: UUID) -> Persona:
        """Activate a persona for use.
        
        Args:
            persona_id: Persona ID to activate
            
        Returns:
            Activated Persona
            
        Raises:
            ValueError: If persona not found or validation fails
        """
        persona = self._personas.get(persona_id)
        if not persona:
            raise ValueError(f"Persona '{persona_id}' not found")
        
        # Validate before activation
        result = await self.validate(persona)
        if not result.is_valid:
            raise ValueError(
                f"Cannot activate persona: validation failed with {len(result.issues)} issues"
            )
        
        persona.state = PersonaState.ACTIVE
        persona.updated_at = datetime.utcnow()
        
        return persona
    
    async def deactivate(self, persona_id: UUID) -> Persona:
        """Deactivate a persona.
        
        Args:
            persona_id: Persona ID to deactivate
            
        Returns:
            Deactivated Persona
            
        Raises:
            ValueError: If persona not found
        """
        persona = self._personas.get(persona_id)
        if not persona:
            raise ValueError(f"Persona '{persona_id}' not found")
        
        persona.state = PersonaState.IDLE
        persona.updated_at = datetime.utcnow()
        
        return persona


# Global factory instance
persona_factory = PersonaFactory()


# Export all public classes and instances
__all__ = [
    # Models
    "Persona",
    # Validators
    "PersonaValidator",
    "TraitValidator",
    "SkillsValidator",
    "EthicsValidator",
    "AutonomyValidator",
    "NameValidator",
    # Factory
    "PersonaFactory",
    "persona_factory",
]
