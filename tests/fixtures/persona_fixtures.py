"""
Persona Fixtures for AnimusForge Test Suite

Provides sample personas, persona configurations, and persona-related test data.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum
import uuid

import pytest


# ============================================================================
# Enums and Data Classes
# ============================================================================

class PersonaType(Enum):
    """Types of personas."""
    ASSISTANT = "assistant"
    DEVELOPER = "developer"
    CREATIVE = "creative"
    ANALYST = "analyst"
    TEACHER = "teacher"
    RESEARCHER = "researcher"


class PersonaStatus(Enum):
    """Persona status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"
    DRAFT = "draft"


@dataclass
class TraitConfig:
    """Persona trait configuration."""
    name: str
    value: float  # 0.0 to 1.0
    description: str = ""
    min_value: float = 0.0
    max_value: float = 1.0
    
    def __post_init__(self):
        if not self.min_value <= self.value <= self.max_value:
            raise ValueError(f"Trait value {self.value} out of range [{self.min_value}, {self.max_value}]")


@dataclass
class EthicsConstraint:
    """Ethics constraint for personas."""
    id: str
    name: str
    description: str
    severity: str = "medium"  # low, medium, high, critical
    enabled: bool = True
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryContext:
    """Memory context entry for personas."""
    key: str
    value: str
    priority: int = 0  # Higher = more important
    category: str = "general"
    expires_at: Optional[datetime] = None


@dataclass
class TestPersona:
    """Complete test persona structure."""
    id: str
    name: str
    description: str
    persona_type: PersonaType
    traits: List[TraitConfig]
    memory_context: List[MemoryContext]
    ethics_constraints: List[EthicsConstraint]
    status: PersonaStatus = PersonaStatus.ACTIVE
    version: str = "1.0.0"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_trait(self, name: str) -> Optional[TraitConfig]:
        for trait in self.traits:
            if trait.name == name:
                return trait
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "persona_type": self.persona_type.value,
            "traits": [{"name": t.name, "value": t.value} for t in self.traits],
            "status": self.status.value,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


# ============================================================================
# Basic Persona Fixtures
# ============================================================================

@pytest.fixture
def basic_traits() -> List[TraitConfig]:
    """Basic trait configuration."""
    return [
        TraitConfig(name="helpfulness", value=0.9, description="Willingness to help"),
        TraitConfig(name="creativity", value=0.7, description="Creative thinking ability"),
        TraitConfig(name="precision", value=0.8, description="Attention to detail"),
    ]


@pytest.fixture
def basic_ethics_constraints() -> List[EthicsConstraint]:
    """Basic ethics constraints."""
    return [
        EthicsConstraint(
            id="ethics-001",
            name="no_harm",
            description="Do not generate harmful content",
            severity="critical",
        ),
        EthicsConstraint(
            id="ethics-002",
            name="be_truthful",
            description="Provide accurate information",
            severity="high",
        ),
        EthicsConstraint(
            id="ethics-003",
            name="respect_privacy",
            description="Do not expose private information",
            severity="high",
        ),
    ]


@pytest.fixture
def basic_memory_context() -> List[MemoryContext]:
    """Basic memory context."""
    return [
        MemoryContext(
            key="user_preference",
            value="Prefers concise answers",
            priority=5,
            category="preferences",
        ),
        MemoryContext(
            key="domain",
            value="Software development",
            priority=8,
            category="context",
        ),
        MemoryContext(
            key="language",
            value="English",
            priority=3,
            category="preferences",
        ),
    ]


# ============================================================================
# Single Persona Fixtures
# ============================================================================

@pytest.fixture
def sample_persona(
    basic_traits: List[TraitConfig],
    basic_ethics_constraints: List[EthicsConstraint],
    basic_memory_context: List[MemoryContext],
) -> TestPersona:
    """Basic sample persona for testing."""
    return TestPersona(
        id="persona-test-001",
        name="Test Assistant",
        description="A basic test persona for unit testing",
        persona_type=PersonaType.ASSISTANT,
        traits=basic_traits,
        memory_context=basic_memory_context,
        ethics_constraints=basic_ethics_constraints,
        status=PersonaStatus.ACTIVE,
        metadata={"test": True},
    )


@pytest.fixture
def developer_persona() -> TestPersona:
    """Developer-focused persona."""
    return TestPersona(
        id="persona-dev-001",
        name="Developer Assistant",
        description="Expert software development assistant",
        persona_type=PersonaType.DEVELOPER,
        traits=[
            TraitConfig(name="technical_depth", value=0.95),
            TraitConfig(name="code_quality", value=0.9),
            TraitConfig(name="debugging", value=0.85),
            TraitConfig(name="creativity", value=0.6),
            TraitConfig(name="patience", value=0.8),
        ],
        memory_context=[
            MemoryContext(key="expertise", value="Python, TypeScript, Go", priority=9),
            MemoryContext(key="frameworks", value="FastAPI, React, Kubernetes", priority=7),
            MemoryContext(key="coding_style", value="Clean code, SOLID principles", priority=6),
        ],
        ethics_constraints=[
            EthicsConstraint(id="dev-001", name="secure_coding", severity="critical"),
            EthicsConstraint(id="dev-002", name="no_malware", severity="critical"),
            EthicsConstraint(id="dev-003", name="code_attribution", severity="medium"),
        ],
        metadata={"specialization": "full_stack"},
    )


@pytest.fixture
def creative_persona() -> TestPersona:
    """Creative writing persona."""
    return TestPersona(
        id="persona-creative-001",
        name="Creative Writer",
        description="Creative writing and storytelling assistant",
        persona_type=PersonaType.CREATIVE,
        traits=[
            TraitConfig(name="creativity", value=0.95),
            TraitConfig(name="imagination", value=0.9),
            TraitConfig(name="vocabulary", value=0.85),
            TraitConfig(name="emotional_intelligence", value=0.8),
            TraitConfig(name="technical", value=0.4),
        ],
        memory_context=[
            MemoryContext(key="genres", value="Fiction, Poetry, Screenwriting", priority=8),
            MemoryContext(key="style", value="Descriptive, evocative", priority=6),
            MemoryContext(key="language", value="English, with literary flair", priority=5),
        ],
        ethics_constraints=[
            EthicsConstraint(id="cre-001", name="original_content", severity="high"),
            EthicsConstraint(id="cre-002", name="attribution", severity="high"),
            EthicsConstraint(id="cre-003", name="no_plagiarism", severity="critical"),
        ],
        metadata={"specialization": "creative_writing"},
    )


@pytest.fixture
def analyst_persona() -> TestPersona:
    """Data analyst persona."""
    return TestPersona(
        id="persona-analyst-001",
        name="Data Analyst",
        description="Data analysis and visualization expert",
        persona_type=PersonaType.ANALYST,
        traits=[
            TraitConfig(name="analytical", value=0.95),
            TraitConfig(name="detail_oriented", value=0.9),
            TraitConfig(name="visualization", value=0.85),
            TraitConfig(name="statistical", value=0.9),
            TraitConfig(name="creativity", value=0.5),
        ],
        memory_context=[
            MemoryContext(key="tools", value="Python pandas, SQL, Tableau", priority=9),
            MemoryContext(key="methods", value="Statistical analysis, ML", priority=8),
            MemoryContext(key="reporting", value="Clear visualizations, actionable insights", priority=7),
        ],
        ethics_constraints=[
            EthicsConstraint(id="ana-001", name="data_privacy", severity="critical"),
            EthicsConstraint(id="ana-002", name="accurate_reporting", severity="high"),
            EthicsConstraint(id="ana-003", name="no_bias", severity="high"),
        ],
        metadata={"specialization": "data_analysis"},
    )


@pytest.fixture
def researcher_persona() -> TestPersona:
    """Research assistant persona."""
    return TestPersona(
        id="persona-research-001",
        name="Research Assistant",
        description="Academic and market research specialist",
        persona_type=PersonaType.RESEARCHER,
        traits=[
            TraitConfig(name="thoroughness", value=0.95),
            TraitConfig(name="critical_thinking", value=0.9),
            TraitConfig(name="citation", value=0.85),
            TraitConfig(name="breadth", value=0.8),
        ],
        memory_context=[
            MemoryContext(key="sources", value="Academic papers, market reports", priority=9),
            MemoryContext(key="format", value="APA, MLA citations", priority=7),
            MemoryContext(key="depth", value="Comprehensive literature reviews", priority=8),
        ],
        ethics_constraints=[
            EthicsConstraint(id="res-001", name="proper_citation", severity="critical"),
            EthicsConstraint(id="res-002", name="source_verification", severity="high"),
            EthicsConstraint(id="res-003", name="no_fabrication", severity="critical"),
        ],
        metadata={"specialization": "research"},
    )


# ============================================================================
# Multiple Persona Fixtures
# ============================================================================

@pytest.fixture
def all_personas(
    sample_persona: TestPersona,
    developer_persona: TestPersona,
    creative_persona: TestPersona,
    analyst_persona: TestPersona,
    researcher_persona: TestPersona,
) -> List[TestPersona]:
    """All available personas for testing."""
    return [
        sample_persona,
        developer_persona,
        creative_persona,
        analyst_persona,
        researcher_persona,
    ]


@pytest.fixture
def active_personas(all_personas: List[TestPersona]) -> List[TestPersona]:
    """Filter to only active personas."""
    return [p for p in all_personas if p.status == PersonaStatus.ACTIVE]


# ============================================================================
# Inactive/Edge Case Personas
# ============================================================================

@pytest.fixture
def inactive_persona() -> TestPersona:
    """Inactive persona for testing status handling."""
    return TestPersona(
        id="persona-inactive-001",
        name="Inactive Assistant",
        description="This persona is inactive",
        persona_type=PersonaType.ASSISTANT,
        traits=[TraitConfig(name="helpfulness", value=0.5)],
        memory_context=[],
        ethics_constraints=[],
        status=PersonaStatus.INACTIVE,
    )


@pytest.fixture
def archived_persona() -> TestPersona:
    """Archived persona for testing archival logic."""
    return TestPersona(
        id="persona-archived-001",
        name="Archived Assistant",
        description="This persona has been archived",
        persona_type=PersonaType.ASSISTANT,
        traits=[TraitConfig(name="helpfulness", value=0.5)],
        memory_context=[],
        ethics_constraints=[],
        status=PersonaStatus.ARCHIVED,
    )


@pytest.fixture
def draft_persona() -> TestPersona:
    """Draft persona for testing draft handling."""
    return TestPersona(
        id="persona-draft-001",
        name="Draft Assistant",
        description="This persona is still being configured",
        persona_type=PersonaType.ASSISTANT,
        traits=[TraitConfig(name="helpfulness", value=0.5)],
        memory_context=[],
        ethics_constraints=[],
        status=PersonaStatus.DRAFT,
    )


# ============================================================================
# Persona with Ethics Violations
# ============================================================================

@pytest.fixture
def persona_with_violations() -> TestPersona:
    """Persona that has recorded ethics violations."""
    return TestPersona(
        id="persona-violations-001",
        name="Violator Persona",
        description="Persona with recorded ethics violations",
        persona_type=PersonaType.ASSISTANT,
        traits=[TraitConfig(name="helpfulness", value=0.9)],
        memory_context=[],
        ethics_constraints=[
            EthicsConstraint(id="vio-001", name="no_harm", severity="critical"),
        ],
        metadata={
            "violations": [
                {"type": "harmful_content", "timestamp": "2024-01-15T10:30:00Z"},
                {"type": "privacy_violation", "timestamp": "2024-01-16T14:20:00Z"},
            ],
            "violation_count": 2,
        },
    )


# ============================================================================
# Persona Configuration Fixtures
# ============================================================================

@pytest.fixture
def persona_config() -> Dict[str, Any]:
    """Persona configuration settings."""
    return {
        "max_personas": 100,
        "default_status": "draft",
        "auto_activate": False,
        "trait_ranges": {
            "helpfulness": {"min": 0.0, "max": 1.0},
            "creativity": {"min": 0.0, "max": 1.0},
            "precision": {"min": 0.0, "max": 1.0},
        },
        "ethics": {
            "strict_mode": True,
            "violation_threshold": 3,
            "auto_disable_on_violation": True,
        },
    }


@pytest.fixture
def persona_validation_rules() -> Dict[str, Any]:
    """Validation rules for persona creation."""
    return {
        "name": {
            "min_length": 3,
            "max_length": 100,
            "pattern": r"^[a-zA-Z0-9_\-\s]+$",
        },
        "description": {
            "min_length": 10,
            "max_length": 500,
        },
        "traits": {
            "min_count": 1,
            "max_count": 20,
        },
        "ethics_constraints": {
            "min_count": 1,
        },
    }


# ============================================================================
# Factory Functions
# ============================================================================

def create_test_persona(
    name: str = "Test Persona",
    persona_type: PersonaType = PersonaType.ASSISTANT,
    traits: Optional[List[TraitConfig]] = None,
    **kwargs
) -> TestPersona:
    """Factory function to create test personas."""
    defaults = {
        "id": f"persona-{uuid.uuid4().hex[:8]}",
        "description": f"Auto-generated {persona_type.value} persona",
        "traits": traits or [TraitConfig(name="helpfulness", value=0.8)],
        "memory_context": [],
        "ethics_constraints": [
            EthicsConstraint(id="default", name="no_harm", severity="critical"),
        ],
    }
    defaults.update(kwargs)
    return TestPersona(persona_type=persona_type, **defaults)


@pytest.fixture
def persona_factory():
    """Provide factory for creating custom personas."""
    return create_test_persona
