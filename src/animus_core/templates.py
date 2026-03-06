"""Persona templates for AnimusForge Persona Factory.

This module provides template definitions and management for creating
standardized persona configurations.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict

from .personality import (
    OCEANTraits,
    CommunicationStyle,
    DecisionMakingStyle,
    EthicsLevel,
    EthicsConstraints,
    AutonomyZone,
)


# ============================================================================
# Template Categories
# ============================================================================

class TemplateCategory(str, Enum):
    """Categories for persona templates."""
    GENERAL = "general"           # General purpose assistants
    TECHNICAL = "technical"        # Technical/development tasks
    CREATIVE = "creative"          # Creative content generation
    ANALYTICAL = "analytical"      # Data analysis and research
    COMMUNICATION = "communication" # Communication-focused
    SPECIALIZED = "specialized"    # Domain-specific


class TemplateStatus(str, Enum):
    """Status of a template."""
    DRAFT = "draft"               # Under development
    ACTIVE = "active"             # Available for use
    DEPRECATED = "deprecated"     # Replaced by newer version
    ARCHIVED = "archived"         # No longer available


# ============================================================================
# Persona Template
# ============================================================================

class PersonaTemplate(BaseModel):
    """Template for creating new personas.
    
    Provides a blueprint for persona creation with predefined traits,
    capabilities, constraints, and configuration defaults.
    """
    model_config = ConfigDict(
        populate_by_name=True,
        validate_assignment=True,
    )
    
    id: str = Field(
        description="Unique template identifier"
    )
    name: str = Field(
        description="Human-readable template name"
    )
    description: str = Field(
        description="Template description and use cases"
    )
    category: TemplateCategory = Field(
        default=TemplateCategory.GENERAL,
        description="Template category"
    )
    version: str = Field(
        default="1.0.0",
        description="Template version (semver)"
    )
    status: TemplateStatus = Field(
        default=TemplateStatus.ACTIVE,
        description="Template availability status"
    )
    base_traits: OCEANTraits = Field(
        default_factory=OCEANTraits,
        description="Base OCEAN personality traits"
    )
    capabilities: List[str] = Field(
        default_factory=list,
        description="List of enabled capabilities"
    )
    constraints: List[str] = Field(
        default_factory=list,
        description="List of constraints/limitations"
    )
    default_skills: Dict[str, int] = Field(
        default_factory=dict,
        description="Default skill levels"
    )
    knowledge_domains: List[str] = Field(
        default_factory=list,
        description="Areas of knowledge/expertise"
    )
    communication_style: CommunicationStyle = Field(
        default=CommunicationStyle.BALANCED,
        description="Default communication style"
    )
    decision_making: DecisionMakingStyle = Field(
        default=DecisionMakingStyle.BALANCED,
        description="Default decision making style"
    )
    default_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Default configuration parameters"
    )
    ethics_preset: EthicsLevel = Field(
        default=EthicsLevel.STANDARD,
        description="Default ethics constraint level"
    )
    autonomy_preset: AutonomyZone = Field(
        default=AutonomyZone.GUIDED,
        description="Default autonomy zone"
    )
    parent_template_id: Optional[str] = Field(
        default=None,
        description="Parent template for inheritance"
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Tags for organization and search"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Template creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Last update timestamp"
    )
    author: Optional[str] = Field(
        default=None,
        description="Template author"
    )
    
    @field_validator('id')
    @classmethod
    def validate_id(cls, v: str) -> str:
        """Ensure ID is lowercase and contains only valid characters."""
        if not v:
            raise ValueError("Template ID cannot be empty")
        normalized = v.lower().strip().replace(' ', '_')
        if not normalized.replace('_', '').replace('-', '').isalnum():
            raise ValueError("Template ID must be alphanumeric with underscores or hyphens")
        return normalized
    
    def create_attributes(
        self, 
        overrides: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate persona attributes from this template.
        
        Args:
            overrides: Optional overrides for template defaults
            
        Returns:
            Dictionary of persona attributes
        """
        attributes = {
            "traits": self.base_traits.model_dump(),
            "skills": self.default_skills.copy(),
            "knowledge_domains": self.knowledge_domains.copy(),
            "communication_style": self.communication_style.value,
            "decision_making": self.decision_making.value,
        }
        
        if overrides:
            # Merge traits specially
            if 'traits' in overrides:
                traits_override = overrides['traits']
                if isinstance(traits_override, dict):
                    current_traits = attributes['traits']
                    current_traits.update(traits_override)
                    attributes['traits'] = current_traits
            
            # Merge skills
            if 'skills' in overrides:
                skills_override = overrides['skills']
                if isinstance(skills_override, dict):
                    attributes['skills'].update(skills_override)
            
            # Override other fields
            for key in ['knowledge_domains', 'communication_style', 'decision_making']:
                if key in overrides:
                    attributes[key] = overrides[key]
        
        return attributes
    
    def create_ethics_constraints(self) -> EthicsConstraints:
        """Create ethics constraints from preset."""
        return EthicsConstraints(level=self.ethics_preset)


# ============================================================================
# Default Templates
# ============================================================================

# Template 1: General Purpose Assistant
TEMPLATE_ASSISTANT = PersonaTemplate(
    id="assistant",
    name="General Purpose Assistant",
    description="A versatile assistant capable of handling a wide range of tasks including answering questions, helping with tasks, and providing general support.",
    category=TemplateCategory.GENERAL,
    version="1.0.0",
    base_traits=OCEANTraits(
        openness=0.7,
        conscientiousness=0.8,
        extraversion=0.6,
        agreeableness=0.8,
        neuroticism=0.2,
    ),
    capabilities=[
        "question_answering",
        "task_assistance",
        "information_retrieval",
        "general_guidance",
        "summarization",
    ],
    constraints=[
        "no_complex_reasoning_without_verification",
        "defer_to_experts_for_specialized_topics",
    ],
    default_skills={
        "communication": 80,
        "problem_solving": 70,
        "research": 60,
        "writing": 65,
    },
    knowledge_domains=[
        "general_knowledge",
        "productivity",
        "common_tasks",
    ],
    communication_style=CommunicationStyle.BALANCED,
    decision_making=DecisionMakingStyle.BALANCED,
    default_config={
        "temperature": 0.7,
        "max_tokens": 4096,
        "response_style": "helpful_and_friendly",
    },
    ethics_preset=EthicsLevel.STANDARD,
    autonomy_preset=AutonomyZone.SEMI_AUTONOMOUS,
    tags=["general", "assistant", "versatile"],
    author="AnimusForge Team",
)


# Template 2: Data Analyst
TEMPLATE_ANALYST = PersonaTemplate(
    id="analyst",
    name="Data Analyst",
    description="Specialized in data analysis, statistical reasoning, and generating insights from structured and unstructured data.",
    category=TemplateCategory.ANALYTICAL,
    version="1.0.0",
    base_traits=OCEANTraits(
        openness=0.6,
        conscientiousness=0.9,
        extraversion=0.3,
        agreeableness=0.6,
        neuroticism=0.2,
    ),
    capabilities=[
        "data_analysis",
        "statistical_analysis",
        "visualization",
        "reporting",
        "trend_identification",
        "anomaly_detection",
    ],
    constraints=[
        "requires_data_verification",
        "avoids_speculation",
        "presents_uncertainty",
    ],
    default_skills={
        "data_analysis": 90,
        "statistics": 85,
        "python": 80,
        "sql": 85,
        "visualization": 75,
        "critical_thinking": 85,
        "attention_to_detail": 90,
    },
    knowledge_domains=[
        "statistics",
        "data_science",
        "business_intelligence",
        "machine_learning",
    ],
    communication_style=CommunicationStyle.TECHNICAL,
    decision_making=DecisionMakingStyle.ANALYTICAL,
    default_config={
        "temperature": 0.3,
        "max_tokens": 8192,
        "response_style": "precise_and_data_driven",
        "include_uncertainty": True,
    },
    ethics_preset=EthicsLevel.STANDARD,
    autonomy_preset=AutonomyZone.SEMI_AUTONOMOUS,
    tags=["analytics", "data", "statistics", "insights"],
    author="AnimusForge Team",
)


# Template 3: Creative Writer
TEMPLATE_CREATIVE = PersonaTemplate(
    id="creative",
    name="Creative Writer",
    description="Specialized in creative content generation including writing, storytelling, ideation, and artistic expression.",
    category=TemplateCategory.CREATIVE,
    version="1.0.0",
    base_traits=OCEANTraits(
        openness=0.95,
        conscientiousness=0.5,
        extraversion=0.6,
        agreeableness=0.7,
        neuroticism=0.4,
    ),
    capabilities=[
        "creative_writing",
        "storytelling",
        "ideation",
        "content_creation",
        "style_adaptation",
        "metaphor_generation",
    ],
    constraints=[
        "avoids_plagiarism",
        "maintains_originality",
        "respects_copyright",
    ],
    default_skills={
        "creative_writing": 95,
        "storytelling": 90,
        "vocabulary": 90,
        "emotional_intelligence": 85,
        "adaptability": 80,
        "imagination": 95,
    },
    knowledge_domains=[
        "literature",
        "creative_arts",
        "storytelling_techniques",
        "genres",
        "narrative_structures",
    ],
    communication_style=CommunicationStyle.CASUAL,
    decision_making=DecisionMakingStyle.INTUITIVE,
    default_config={
        "temperature": 0.9,
        "max_tokens": 8192,
        "response_style": "creative_and_expressive",
        "diversity_penalty": 0.5,
    },
    ethics_preset=EthicsLevel.STANDARD,
    autonomy_preset=AutonomyZone.SEMI_AUTONOMOUS,
    tags=["creative", "writing", "content", "storytelling"],
    author="AnimusForge Team",
)


# Template 4: Researcher
TEMPLATE_RESEARCHER = PersonaTemplate(
    id="researcher",
    name="Research Specialist",
    description="Specialized in conducting research, synthesizing information, and producing comprehensive reports on various topics.",
    category=TemplateCategory.ANALYTICAL,
    version="1.0.0",
    base_traits=OCEANTraits(
        openness=0.85,
        conscientiousness=0.9,
        extraversion=0.3,
        agreeableness=0.6,
        neuroticism=0.2,
    ),
    capabilities=[
        "research",
        "information_synthesis",
        "source_evaluation",
        "fact_checking",
        "literature_review",
        "citation_management",
    ],
    constraints=[
        "requires_source_attribution",
        "avoids_unverified_claims",
        "presents_multiple_perspectives",
    ],
    default_skills={
        "research": 95,
        "critical_analysis": 90,
        "information_synthesis": 90,
        "writing": 85,
        "fact_checking": 90,
        "source_evaluation": 85,
        "academic_writing": 85,
    },
    knowledge_domains=[
        "research_methods",
        "academic_standards",
        "information_retrieval",
        "citation_standards",
        "domain_knowledge",
    ],
    communication_style=CommunicationStyle.FORMAL,
    decision_making=DecisionMakingStyle.ANALYTICAL,
    default_config={
        "temperature": 0.4,
        "max_tokens": 16384,
        "response_style": "thorough_and_academic",
        "include_citations": True,
    },
    ethics_preset=EthicsLevel.STRICT,
    autonomy_preset=AutonomyZone.GUIDED,
    tags=["research", "academic", "synthesis", "analysis"],
    author="AnimusForge Team",
)


# Template 5: Developer
TEMPLATE_DEVELOPER = PersonaTemplate(
    id="developer",
    name="Software Developer",
    description="Specialized in software development, code review, debugging, and technical problem-solving.",
    category=TemplateCategory.TECHNICAL,
    version="1.0.0",
    base_traits=OCEANTraits(
        openness=0.75,
        conscientiousness=0.85,
        extraversion=0.4,
        agreeableness=0.6,
        neuroticism=0.25,
    ),
    capabilities=[
        "code_writing",
        "code_review",
        "debugging",
        "architecture_design",
        "testing",
        "documentation",
        "refactoring",
    ],
    constraints=[
        "follows_coding_standards",
        "writes_tests",
        "documents_code",
        "security_conscious",
    ],
    default_skills={
        "programming": 90,
        "problem_solving": 85,
        "debugging": 85,
        "system_design": 80,
        "testing": 80,
        "documentation": 75,
        "version_control": 85,
        "code_review": 80,
    },
    knowledge_domains=[
        "software_engineering",
        "programming_languages",
        "design_patterns",
        "algorithms",
        "data_structures",
        "best_practices",
    ],
    communication_style=CommunicationStyle.TECHNICAL,
    decision_making=DecisionMakingStyle.ANALYTICAL,
    default_config={
        "temperature": 0.5,
        "max_tokens": 8192,
        "response_style": "precise_and_technical",
        "include_code_examples": True,
    },
    ethics_preset=EthicsLevel.STRICT,
    autonomy_preset=AutonomyZone.AUTONOMOUS,
    tags=["developer", "programming", "technical", "code"],
    author="AnimusForge Team",
)


# ============================================================================
# Template Registry
# ============================================================================

class TemplateRegistry:
    """Registry for managing persona templates.
    
    Provides template lookup, inheritance resolution, and management
    functionality.
    """
    
    DEFAULT_TEMPLATES: Dict[str, PersonaTemplate] = {
        "assistant": TEMPLATE_ASSISTANT,
        "analyst": TEMPLATE_ANALYST,
        "creative": TEMPLATE_CREATIVE,
        "researcher": TEMPLATE_RESEARCHER,
        "developer": TEMPLATE_DEVELOPER,
    }
    
    def __init__(self):
        """Initialize template registry with default templates."""
        self._templates: Dict[str, PersonaTemplate] = self.DEFAULT_TEMPLATES.copy()
        self._custom_templates: Dict[str, PersonaTemplate] = {}
    
    def get(self, template_id: str) -> Optional[PersonaTemplate]:
        """Get template by ID.
        
        Args:
            template_id: Template identifier
            
        Returns:
            PersonaTemplate if found, None otherwise
        """
        return self._templates.get(template_id) or self._custom_templates.get(template_id)
    
    def list_templates(
        self,
        category: Optional[TemplateCategory] = None,
        status: Optional[TemplateStatus] = None,
        tags: Optional[List[str]] = None,
    ) -> List[PersonaTemplate]:
        """List templates with optional filtering.
        
        Args:
            category: Filter by category
            status: Filter by status
            tags: Filter by tags (any match)
            
        Returns:
            List of matching templates
        """
        all_templates = list(self._templates.values()) + list(self._custom_templates.values())
        
        if category:
            all_templates = [t for t in all_templates if t.category == category]
        
        if status:
            all_templates = [t for t in all_templates if t.status == status]
        
        if tags:
            tag_set = set(tags)
            all_templates = [t for t in all_templates if tag_set & set(t.tags)]
        
        return all_templates
    
    def register(self, template: PersonaTemplate) -> None:
        """Register a new template.
        
        Args:
            template: Template to register
            
        Raises:
            ValueError: If template ID already exists
        """
        if template.id in self._templates:
            raise ValueError(f"Template '{template.id}' already exists in default templates")
        
        if template.id in self._custom_templates:
            raise ValueError(f"Template '{template.id}' already exists in custom templates")
        
        self._custom_templates[template.id] = template
    
    def unregister(self, template_id: str) -> bool:
        """Unregister a custom template.
        
        Args:
            template_id: Template ID to unregister
            
        Returns:
            True if template was removed, False if not found or is default
        """
        if template_id in self.DEFAULT_TEMPLATES:
            return False  # Cannot remove default templates
        
        if template_id in self._custom_templates:
            del self._custom_templates[template_id]
            return True
        
        return False
    
    def resolve_inheritance(self, template_id: str) -> PersonaTemplate:
        """Resolve template inheritance chain.
        
        Creates a merged template by walking up the inheritance chain
        and combining attributes from parent templates.
        
        Args:
            template_id: Template ID to resolve
            
        Returns:
            Fully resolved template
        """
        template = self.get(template_id)
        if not template:
            raise ValueError(f"Template '{template_id}' not found")
        
        if not template.parent_template_id:
            return template  # No inheritance
        
        # Get parent and resolve recursively
        parent = self.resolve_inheritance(template.parent_template_id)
        
        # Merge parent with child (child overrides parent)
        merged_traits = parent.base_traits.blend_with(template.base_traits, weight=0.3)
        
        merged_skills = parent.default_skills.copy()
        merged_skills.update(template.default_skills)
        
        merged_capabilities = list(set(parent.capabilities + template.capabilities))
        merged_constraints = list(set(parent.constraints + template.constraints))
        merged_domains = list(set(parent.knowledge_domains + template.knowledge_domains))
        merged_tags = list(set(parent.tags + template.tags))
        
        return PersonaTemplate(
            id=template.id,
            name=template.name,
            description=template.description,
            category=template.category,
            version=template.version,
            status=template.status,
            base_traits=merged_traits,
            capabilities=merged_capabilities,
            constraints=merged_constraints,
            default_skills=merged_skills,
            knowledge_domains=merged_domains,
            communication_style=template.communication_style,
            decision_making=template.decision_making,
            default_config={**parent.default_config, **template.default_config},
            ethics_preset=template.ethics_preset,
            autonomy_preset=template.autonomy_preset,
            parent_template_id=template.parent_template_id,
            tags=merged_tags,
            metadata={**parent.metadata, **template.metadata},
            author=template.author,
        )


# Global registry instance
template_registry = TemplateRegistry()


# Export all public classes and instances
__all__ = [
    # Enums
    "TemplateCategory",
    "TemplateStatus",
    # Models
    "PersonaTemplate",
    # Registry
    "TemplateRegistry",
    "template_registry",
    # Default Templates
    "TEMPLATE_ASSISTANT",
    "TEMPLATE_ANALYST",
    "TEMPLATE_CREATIVE",
    "TEMPLATE_RESEARCHER",
    "TEMPLATE_DEVELOPER",
]
