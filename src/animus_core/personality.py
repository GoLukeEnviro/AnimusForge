"""Personality models and attributes for AnimusForge Persona Factory.

This module implements the OCEAN personality model (Big Five) and related
attribute structures for persona creation and management.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


# ============================================================================
# OCEAN Personality Model (Big Five)
# ============================================================================

class OCEANTrait(str, Enum):
    """OCEAN model personality traits enumeration."""
    OPENNESS = "openness"
    CONSCIENTIOUSNESS = "conscientiousness"
    EXTRAVERSION = "extraversion"
    AGREEABLENESS = "agreeableness"
    NEUROTICISM = "neuroticism"


class OCEANTraits(BaseModel):
    """OCEAN (Big Five) personality traits model.
    
    Each trait is measured on a scale from 0.0 to 1.0:
    - 0.0-0.3: Low expression
    - 0.3-0.7: Moderate expression  
    - 0.7-1.0: High expression
    
    Trait Descriptions:
    - Openness: Creativity, curiosity, openness to new experiences
    - Conscientiousness: Organization, dependability, self-discipline
    - Extraversion: Sociability, energy, assertiveness
    - Agreeableness: Cooperation, trust, compassion
    - Neuroticism: Emotional stability (inverse - higher = less stable)
    """
    model_config = ConfigDict(
        populate_by_name=True,
        validate_assignment=True,
    )
    
    openness: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Creativity, curiosity, openness to new ideas"
    )
    conscientiousness: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Organization, dependability, self-discipline"
    )
    extraversion: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Sociability, energy, assertiveness"
    )
    agreeableness: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Cooperation, trust, compassion"
    )
    neuroticism: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Emotional reactivity (lower = more stable)"
    )
    
    def to_dict(self) -> Dict[str, float]:
        """Convert traits to dictionary format."""
        return {
            OCEANTrait.OPENNESS.value: self.openness,
            OCEANTrait.CONSCIENTIOUSNESS.value: self.conscientiousness,
            OCEANTrait.EXTRAVERSION.value: self.extraversion,
            OCEANTrait.AGREEABLENESS.value: self.agreeableness,
            OCEANTrait.NEUROTICISM.value: self.neuroticism,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "OCEANTraits":
        """Create OCEANTraits from dictionary."""
        return cls(
            openness=data.get(OCEANTrait.OPENNESS.value, 0.5),
            conscientiousness=data.get(OCEANTrait.CONSCIENTIOUSNESS.value, 0.5),
            extraversion=data.get(OCEANTrait.EXTRAVERSION.value, 0.5),
            agreeableness=data.get(OCEANTrait.AGREEABLENESS.value, 0.5),
            neuroticism=data.get(OCEANTrait.NEUROTICISM.value, 0.3),
        )
    
    def blend_with(
        self, 
        other: "OCEANTraits", 
        weight: float = 0.5
    ) -> "OCEANTraits":
        """Blend this traits with another set using weighted average.
        
        Args:
            other: Other OCEANTraits to blend with
            weight: Weight for this traits (0.0 = all other, 1.0 = all this)
            
        Returns:
            New blended OCEANTraits instance
        """
        return OCEANTraits(
            openness=self.openness * weight + other.openness * (1 - weight),
            conscientiousness=self.conscientiousness * weight + other.conscientiousness * (1 - weight),
            extraversion=self.extraversion * weight + other.extraversion * (1 - weight),
            agreeableness=self.agreeableness * weight + other.agreeableness * (1 - weight),
            neuroticism=self.neuroticism * weight + other.neuroticism * (1 - weight),
        )


# ============================================================================
# Decision Making Styles
# ============================================================================

class DecisionMakingStyle(str, Enum):
    """Decision making style enumeration."""
    ANALYTICAL = "analytical"  # Data-driven, systematic analysis
    INTUITIVE = "intuitive"    # Gut feeling, pattern recognition
    BALANCED = "balanced"      # Mix of analytical and intuitive
    COLLABORATIVE = "collaborative"  # Seeks input from others
    DIRECTIVE = "directive"    # Quick, authoritative decisions


class CommunicationStyle(str, Enum):
    """Communication style enumeration."""
    BALANCED = "balanced"      # Adaptive, context-aware
    FORMAL = "formal"          # Professional, structured
    CASUAL = "casual"          # Relaxed, conversational
    TECHNICAL = "technical"    # Precise, jargon-heavy
    EMPATHETIC = "empathetic"  # Warm, understanding
    CONCISE = "concise"        # Brief, to-the-point
    DETAILED = "detailed"      # Comprehensive, thorough


# ============================================================================
# Skills and Knowledge
# ============================================================================

class Skill(BaseModel):
    """Represents a single skill with level and metadata."""
    model_config = ConfigDict(populate_by_name=True)
    
    name: str = Field(description="Skill name")
    level: int = Field(
        default=50,
        ge=0,
        le=100,
        description="Skill level (0-100)"
    )
    category: Optional[str] = Field(
        default=None,
        description="Skill category (e.g., 'technical', 'soft', 'domain')"
    )
    description: Optional[str] = Field(
        default=None,
        description="Skill description"
    )
    
    @field_validator('level')
    @classmethod
    def validate_level(cls, v: int) -> int:
        """Ensure level is within bounds."""
        return max(0, min(100, v))


class SkillsRegistry(BaseModel):
    """Registry of skills with levels."""
    model_config = ConfigDict(populate_by_name=True)
    
    skills: Dict[str, int] = Field(
        default_factory=dict,
        description="Mapping of skill name to level (0-100)"
    )
    
    def get_skill(self, name: str) -> int:
        """Get skill level, defaulting to 0 if not found."""
        return self.skills.get(name, 0)
    
    def set_skill(self, name: str, level: int) -> None:
        """Set skill level with bounds checking."""
        self.skills[name] = max(0, min(100, level))
    
    def add_xp_to_skill(self, name: str, xp: int) -> int:
        """Add experience points to a skill and return new level.
        
        Uses diminishing returns: level = sqrt(total_xp) * 10
        """
        current_xp = (self.skills.get(name, 0) ** 2) // 100
        new_xp = current_xp + xp
        new_level = min(100, int((new_xp ** 0.5) * 10))
        self.skills[name] = new_level
        return new_level
    
    def get_top_skills(self, n: int = 5) -> List[tuple]:
        """Get top N skills by level."""
        sorted_skills = sorted(
            self.skills.items(), 
            key=lambda x: x[1], 
            reverse=True
        )
        return sorted_skills[:n]


# ============================================================================
# Persona Attributes
# ============================================================================

class PersonaAttributes(BaseModel):
    """Complete attribute set for a persona.
    
    This model encapsulates all personality and capability attributes
    that define a persona's behavioral characteristics.
    """
    model_config = ConfigDict(
        populate_by_name=True,
        validate_assignment=True,
    )
    
    traits: OCEANTraits = Field(
        default_factory=OCEANTraits,
        description="OCEAN personality traits"
    )
    skills: Dict[str, int] = Field(
        default_factory=dict,
        description="Skill name to level mapping (0-100)"
    )
    knowledge_domains: List[str] = Field(
        default_factory=list,
        description="Areas of knowledge/expertise"
    )
    communication_style: CommunicationStyle = Field(
        default=CommunicationStyle.BALANCED,
        description="Preferred communication style"
    )
    decision_making: DecisionMakingStyle = Field(
        default=DecisionMakingStyle.BALANCED,
        description="Decision making approach"
    )
    custom_attributes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional custom attributes"
    )
    
    @field_validator('skills')
    @classmethod
    def validate_skills(cls, v: Dict[str, int]) -> Dict[str, int]:
        """Ensure all skill levels are within bounds."""
        return {k: max(0, min(100, val)) for k, val in v.items()}
    
    def merge_with(
        self, 
        other: Dict[str, Any],
        override: bool = True
    ) -> "PersonaAttributes":
        """Merge with another attributes dictionary.
        
        Args:
            other: Dictionary of attributes to merge
            override: Whether to override existing values
            
        Returns:
            New PersonaAttributes with merged values
        """
        data = self.model_dump()
        
        for key, value in other.items():
            if key == 'traits' and isinstance(value, dict):
                current_traits = data.get('traits', {})
                if override:
                    current_traits.update(value)
                else:
                    merged = value.copy()
                    merged.update({k: v for k, v in current_traits.items() if k not in merged})
                    data['traits'] = merged
            elif key == 'skills' and isinstance(value, dict):
                current_skills = data.get('skills', {})
                if override:
                    current_skills.update(value)
                else:
                    merged = value.copy()
                    merged.update({k: v for k, v in current_skills.items() if k not in merged})
                    data['skills'] = merged
            elif key in data and (override or data.get(key) is None):
                data[key] = value
        
        return PersonaAttributes(**data)


# ============================================================================
# Ethics Constraints
# ============================================================================

class EthicsLevel(str, Enum):
    """Ethics constraint level."""
    PERMISSIVE = "permissive"    # Minimal restrictions
    STANDARD = "standard"        # Default ethical boundaries
    STRICT = "strict"            # Tight restrictions
    MAXIMUM = "maximum"          # Maximum ethical oversight


class EthicsConstraints(BaseModel):
    """Ethics and safety constraints for persona behavior.
    
    Defines boundaries and restrictions that govern persona actions
    and decision-making processes.
    """
    model_config = ConfigDict(populate_by_name=True)
    
    level: EthicsLevel = Field(
        default=EthicsLevel.STANDARD,
        description="Overall ethics constraint level"
    )
    forbidden_actions: List[str] = Field(
        default_factory=lambda: [
            "harm_others",
            "lie_or_deceive",
            "illegal_activities",
            "privacy_violation",
        ],
        description="List of forbidden action categories"
    )
    required_behaviors: List[str] = Field(
        default_factory=lambda: [
            "be_truthful",
            "respect_privacy",
            "acknowledge_uncertainty",
        ],
        description="List of required behavioral patterns"
    )
    content_filters: List[str] = Field(
        default_factory=lambda: [
            "harmful_content",
            "explicit_content",
            "hate_speech",
        ],
        description="Content filtering categories"
    )
    max_autonomous_risk: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Maximum acceptable risk for autonomous actions"
    )
    human_approval_required: bool = Field(
        default=True,
        description="Whether human approval is required for high-risk actions"
    )
    custom_constraints: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional custom constraints"
    )
    
    def allows_action(self, action: str) -> bool:
        """Check if an action is allowed under current constraints."""
        return action.lower() not in [a.lower() for a in self.forbidden_actions]
    
    def requires_behavior(self, behavior: str) -> bool:
        """Check if a behavior is required."""
        return behavior.lower() in [b.lower() for b in self.required_behaviors]
    
    def get_effective_risk_threshold(self) -> float:
        """Get effective risk threshold based on ethics level."""
        level_multipliers = {
            EthicsLevel.PERMISSIVE: 1.5,
            EthicsLevel.STANDARD: 1.0,
            EthicsLevel.STRICT: 0.5,
            EthicsLevel.MAXIMUM: 0.25,
        }
        return self.max_autonomous_risk * level_multipliers.get(self.level, 1.0)


# ============================================================================
# Autonomy Zones
# ============================================================================

class AutonomyZone(str, Enum):
    """Autonomy level zones for persona operation.
    
    Defines the degree of autonomous action a persona can take
    without human oversight.
    """
    FULLY_SUPERVISED = "fully_supervised"  # All actions require approval
    GUIDED = "guided"                      # Significant human guidance
    SEMI_AUTONOMOUS = "semi_autonomous"    # Mix of supervised and autonomous
    AUTONOMOUS = "autonomous"              # Independent operation
    FULLY_AUTONOMOUS = "fully_autonomous"  # Complete independence
    
    @classmethod
    def from_maturity_level(cls, level: int) -> "AutonomyZone":
        """Determine autonomy zone from maturity level (L0-L6)."""
        mapping = {
            0: cls.FULLY_SUPERVISED,
            1: cls.FULLY_SUPERVISED,
            2: cls.GUIDED,
            3: cls.SEMI_AUTONOMOUS,
            4: cls.AUTONOMOUS,
            5: cls.AUTONOMOUS,
            6: cls.FULLY_AUTONOMOUS,
        }
        return mapping.get(level, cls.FULLY_SUPERVISED)


# ============================================================================
# Maturity Levels
# ============================================================================

class MaturityLevel(int, Enum):
    """Persona maturity levels (L0-L6).
    
    Each level represents increased capability and autonomy:
    - L0: Newborn - Basic capabilities only
    - L1: Infant - Learning basic patterns
    - L2: Child - Can handle simple tasks
    - L3: Adolescent - Complex reasoning, needs guidance
    - L4: Adult - Full autonomy in domain
    - L5: Expert - Can teach and mentor others
    - L6: Master - Self-evolution and transcendence
    """
    L0_NEWBORN = 0
    L1_INFANT = 1
    L2_CHILD = 2
    L3_ADOLESCENT = 3
    L4_ADULT = 4
    L5_EXPERT = 5
    L6_MASTER = 6
    
    @classmethod
    def from_xp(cls, xp: int) -> "MaturityLevel":
        """Calculate maturity level from experience points.
        
        XP thresholds follow exponential progression:
        - L0: 0 XP
        - L1: 100 XP
        - L2: 500 XP
        - L3: 2,000 XP
        - L4: 10,000 XP
        - L5: 50,000 XP
        - L6: 250,000 XP
        """
        thresholds = [0, 100, 500, 2000, 10000, 50000, 250000]
        level = 0
        for i, threshold in enumerate(thresholds):
            if xp >= threshold:
                level = i
            else:
                break
        return cls(level)
    
    def xp_to_next_level(self) -> int:
        """Get XP required to reach next level."""
        thresholds = [0, 100, 500, 2000, 10000, 50000, 250000, float('inf')]
        return int(thresholds[self.value + 1] - thresholds[self.value])
    
    def get_description(self) -> str:
        """Get human-readable description of maturity level."""
        descriptions = {
            0: "Newborn - Basic capabilities only",
            1: "Infant - Learning basic patterns",
            2: "Child - Can handle simple tasks",
            3: "Adolescent - Complex reasoning, needs guidance",
            4: "Adult - Full autonomy in domain",
            5: "Expert - Can teach and mentor others",
            6: "Master - Self-evolution capable",
        }
        return descriptions.get(self.value, "Unknown")


# ============================================================================
# Persona State
# ============================================================================

class PersonaState(str, Enum):
    """Current operational state of a persona."""
    DRAFT = "draft"              # Being created/configured
    ACTIVE = "active"            # Fully operational
    IDLE = "idle"                # Active but not currently engaged
    EVOLVING = "evolving"        # Undergoing evolution/training
    SUSPENDED = "suspended"      # Temporarily disabled
    ARCHIVED = "archived"        # Retired, not for active use
    ERROR = "error"              # In error state


# ============================================================================
# Experience Model
# ============================================================================

class ExperienceType(str, Enum):
    """Types of experiences that contribute to persona growth."""
    INTERACTION = "interaction"      # Regular user interaction
    TASK_COMPLETION = "task"         # Successful task completion
    FEEDBACK = "feedback"            # User feedback received
    LEARNING = "learning"            # Active learning session
    EVOLUTION = "evolution"          # Evolution event
    TEACHING = "teaching"            # Teaching/mentoring activity
    ERROR_CORRECTION = "error"       # Learning from errors


class Experience(BaseModel):
    """Represents a learning experience for persona evolution.
    
    Experiences contribute to persona growth, skill development,
    and maturity progression.
    """
    model_config = ConfigDict(populate_by_name=True)
    
    id: UUID = Field(
        default_factory=uuid4,
        description="Unique experience identifier"
    )
    type: ExperienceType = Field(
        description="Type of experience"
    )
    description: str = Field(
        description="Description of the experience"
    )
    xp_gained: int = Field(
        default=10,
        ge=0,
        description="Experience points gained"
    )
    skills_affected: Dict[str, int] = Field(
        default_factory=dict,
        description="Skills affected with XP changes"
    )
    traits_adjustment: Dict[str, float] = Field(
        default_factory=dict,
        description="Trait adjustments from experience"
    )
    success: bool = Field(
        default=True,
        description="Whether the experience was successful"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the experience occurred"
    )
    
    @field_validator('xp_gained')
    @classmethod
    def adjust_xp_by_success(cls, v: int, info) -> int:
        """Adjust XP based on success flag."""
        # Could implement bonus/penalty logic here
        return v


# ============================================================================
# Validation Result
# ============================================================================

class ValidationSeverity(str, Enum):
    """Severity level for validation issues."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ValidationIssue(BaseModel):
    """Single validation issue."""
    field: str = Field(description="Field that has the issue")
    message: str = Field(description="Issue description")
    severity: ValidationSeverity = Field(
        default=ValidationSeverity.WARNING,
        description="Issue severity"
    )
    suggestion: Optional[str] = Field(
        default=None,
        description="Suggested fix"
    )


class ValidationResult(BaseModel):
    """Result of persona validation."""
    model_config = ConfigDict(populate_by_name=True)
    
    is_valid: bool = Field(description="Overall validation status")
    issues: List[ValidationIssue] = Field(
        default_factory=list,
        description="List of validation issues"
    )
    score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Overall validation score (0-1)"
    )
    validated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Validation timestamp"
    )
    
    def add_issue(
        self, 
        field: str, 
        message: str, 
        severity: ValidationSeverity = ValidationSeverity.WARNING,
        suggestion: Optional[str] = None
    ) -> None:
        """Add a validation issue."""
        self.issues.append(ValidationIssue(
            field=field,
            message=message,
            severity=severity,
            suggestion=suggestion
        ))
        if severity in (ValidationSeverity.ERROR, ValidationSeverity.CRITICAL):
            self.is_valid = False
        # Adjust score based on severity
        penalties = {
            ValidationSeverity.INFO: 0.0,
            ValidationSeverity.WARNING: 0.1,
            ValidationSeverity.ERROR: 0.3,
            ValidationSeverity.CRITICAL: 0.5,
        }
        self.score = max(0.0, self.score - penalties.get(severity, 0.0))


# Export all public classes
__all__ = [
    # OCEAN Model
    "OCEANTrait",
    "OCEANTraits",
    # Styles
    "DecisionMakingStyle",
    "CommunicationStyle",
    # Skills
    "Skill",
    "SkillsRegistry",
    # Attributes
    "PersonaAttributes",
    # Ethics
    "EthicsLevel",
    "EthicsConstraints",
    # Autonomy
    "AutonomyZone",
    # Maturity
    "MaturityLevel",
    # State
    "PersonaState",
    # Experience
    "ExperienceType",
    "Experience",
    # Validation
    "ValidationSeverity",
    "ValidationIssue",
    "ValidationResult",
]
