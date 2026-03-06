"""AnimusForge Core Module.

This module provides the core functionality for persona management,
including the Persona Factory, Templates, and Personality models.
"""

# Personality models
from .personality import (
    OCEANTrait,
    OCEANTraits,
    DecisionMakingStyle,
    CommunicationStyle,
    Skill,
    SkillsRegistry,
    PersonaAttributes,
    EthicsLevel,
    EthicsConstraints,
    AutonomyZone,
    MaturityLevel,
    PersonaState,
    ExperienceType,
    Experience,
    ValidationSeverity,
    ValidationIssue,
    ValidationResult,
)

# Template models
from .templates import (
    TemplateCategory,
    TemplateStatus,
    PersonaTemplate,
    TemplateRegistry,
    template_registry,
    TEMPLATE_ASSISTANT,
    TEMPLATE_ANALYST,
    TEMPLATE_CREATIVE,
    TEMPLATE_RESEARCHER,
    TEMPLATE_DEVELOPER,
)

# Factory models
from .factory import (
    Persona,
    PersonaValidator,
    TraitValidator,
    SkillsValidator,
    EthicsValidator,
    AutonomyValidator,
    NameValidator,
    PersonaFactory,
    persona_factory,
)

__all__ = [
    # Personality
    "OCEANTrait",
    "OCEANTraits",
    "DecisionMakingStyle",
    "CommunicationStyle",
    "Skill",
    "SkillsRegistry",
    "PersonaAttributes",
    "EthicsLevel",
    "EthicsConstraints",
    "AutonomyZone",
    "MaturityLevel",
    "PersonaState",
    "ExperienceType",
    "Experience",
    "ValidationSeverity",
    "ValidationIssue",
    "ValidationResult",
    # Templates
    "TemplateCategory",
    "TemplateStatus",
    "PersonaTemplate",
    "TemplateRegistry",
    "template_registry",
    "TEMPLATE_ASSISTANT",
    "TEMPLATE_ANALYST",
    "TEMPLATE_CREATIVE",
    "TEMPLATE_RESEARCHER",
    "TEMPLATE_DEVELOPER",
    # Factory
    "Persona",
    "PersonaValidator",
    "TraitValidator",
    "SkillsValidator",
    "EthicsValidator",
    "AutonomyValidator",
    "NameValidator",
    "PersonaFactory",
    "persona_factory",
]
