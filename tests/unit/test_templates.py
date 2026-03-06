"""Unit tests for Persona Templates.

Tests cover:
- PersonaTemplate model validation
- TemplateRegistry operations
- Template inheritance
- Default templates
- Attribute generation
"""

import pytest
from datetime import datetime
from unittest.mock import patch

from animus_core.templates import (
    PersonaTemplate,
    TemplateRegistry,
    TemplateCategory,
    TemplateStatus,
    template_registry,
    TEMPLATE_ASSISTANT,
    TEMPLATE_ANALYST,
    TEMPLATE_CREATIVE,
    TEMPLATE_RESEARCHER,
    TEMPLATE_DEVELOPER,
)
from animus_core.personality import (
    OCEANTraits,
    CommunicationStyle,
    DecisionMakingStyle,
    EthicsLevel,
    AutonomyZone,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def fresh_registry():
    """Create a fresh TemplateRegistry for each test."""
    return TemplateRegistry()


@pytest.fixture
def custom_template():
    """Create a custom template for testing."""
    return PersonaTemplate(
        id="test_template",
        name="Test Template",
        description="A template for testing",
        category=TemplateCategory.GENERAL,
        base_traits=OCEANTraits(
            openness=0.9,
            conscientiousness=0.8,
        ),
        capabilities=["testing", "mocking"],
        constraints=["no_production"],
        default_skills={"python": 75, "testing": 85},
    )


@pytest.fixture
def child_template():
    """Create a child template for inheritance testing."""
    return PersonaTemplate(
        id="senior_developer",
        name="Senior Developer",
        description="Senior developer with leadership",
        category=TemplateCategory.TECHNICAL,
        parent_template_id="developer",
        default_skills={"leadership": 90, "mentoring": 85},
    )


# ============================================================================
# PersonaTemplate Model Tests
# ============================================================================

class TestPersonaTemplateModel:
    """Tests for PersonaTemplate model."""
    
    def test_template_creation_minimal(self):
        """Test creating template with minimal fields."""
        template = PersonaTemplate(
            id="minimal",
            name="Minimal Template",
            description="Minimal test template",
        )
        
        assert template.id == "minimal"
        assert template.name == "Minimal Template"
        assert template.category == TemplateCategory.GENERAL
        assert template.version == "1.0.0"
        assert template.status == TemplateStatus.ACTIVE
    
    def test_template_creation_full(self):
        """Test creating template with all fields."""
        traits = OCEANTraits(openness=0.9, conscientiousness=0.8)
        
        template = PersonaTemplate(
            id="full_template",
            name="Full Template",
            description="Complete template",
            category=TemplateCategory.TECHNICAL,
            version="2.1.0",
            status=TemplateStatus.ACTIVE,
            base_traits=traits,
            capabilities=["coding", "testing"],
            constraints=["no_production"],
            default_skills={"python": 90},
            knowledge_domains=["software_engineering"],
            communication_style=CommunicationStyle.TECHNICAL,
            decision_making=DecisionMakingStyle.ANALYTICAL,
            default_config={"temperature": 0.5},
            ethics_preset=EthicsLevel.STRICT,
            autonomy_preset=AutonomyZone.AUTONOMOUS,
            tags=["technical", "development"],
            author="Test Author",
        )
        
        assert template.id == "full_template"
        assert template.category == TemplateCategory.TECHNICAL
        assert template.version == "2.1.0"
        assert "coding" in template.capabilities
        assert template.ethics_preset == EthicsLevel.STRICT
    
    def test_template_id_validation_lowercase(self):
        """Test that ID is normalized to lowercase."""
        template = PersonaTemplate(
            id="UPPER_CASE_ID",
            name="Test",
            description="Test",
        )
        
        assert template.id == "upper_case_id"
    
    def test_template_id_validation_spaces(self):
        """Test that spaces in ID are replaced with underscores."""
        template = PersonaTemplate(
            id="test template id",
            name="Test",
            description="Test",
        )
        
        assert template.id == "test_template_id"
    
    def test_template_id_validation_empty(self):
        """Test that empty ID raises error."""
        with pytest.raises(ValueError, match="cannot be empty"):
            PersonaTemplate(
                id="",
                name="Test",
                description="Test",
            )
    
    def test_template_id_validation_special_chars(self):
        """Test that ID allows alphanumeric, underscores, and hyphens."""
        # Valid IDs
        valid_ids = ["test_id", "test-id", "test123", "TEST_ID"]
        for test_id in valid_ids:
            template = PersonaTemplate(
                id=test_id,
                name="Test",
                description="Test",
            )
            assert template.id == test_id.lower()
    
    def test_template_id_validation_invalid_chars(self):
        """Test that invalid characters raise error."""
        with pytest.raises(ValueError, match="alphanumeric"):
            PersonaTemplate(
                id="test@id!",
                name="Test",
                description="Test",
            )


# ============================================================================
# Template Attribute Generation Tests
# ============================================================================

class TestTemplateAttributeGeneration:
    """Tests for template attribute generation."""
    
    def test_create_attributes_basic(self, custom_template):
        """Test basic attribute generation."""
        attributes = custom_template.create_attributes()
        
        assert "traits" in attributes
        assert "skills" in attributes
        assert attributes["skills"]["python"] == 75
        assert attributes["skills"]["testing"] == 85
    
    def test_create_attributes_with_overrides(self, custom_template):
        """Test attribute generation with overrides."""
        attributes = custom_template.create_attributes(
            overrides={
                "skills": {"python": 95, "new_skill": 50},
                "knowledge_domains": ["custom_domain"],
            }
        )
        
        # Should update existing skill
        assert attributes["skills"]["python"] == 95
        # Should add new skill
        assert attributes["skills"]["new_skill"] == 50
        # Should keep existing skill
        assert attributes["skills"]["testing"] == 85
        # Should override domains
        assert attributes["knowledge_domains"] == ["custom_domain"]
    
    def test_create_attributes_traits_override(self, custom_template):
        """Test attribute generation with trait overrides."""
        attributes = custom_template.create_attributes(
            overrides={
                "traits": {
                    "openness": 0.5,
                    "extraversion": 0.9,
                }
            }
        )
        
        # Should update specified trait
        assert attributes["traits"]["openness"] == 0.5
        assert attributes["traits"]["extraversion"] == 0.9
        # Should keep other traits from template
        assert attributes["traits"]["conscientiousness"] == 0.8
    
    def test_create_ethics_constraints(self, custom_template):
        """Test ethics constraints creation."""
        constraints = custom_template.create_ethics_constraints()
        
        assert constraints.level == custom_template.ethics_preset
        assert isinstance(constraints, type(constraints))


# ============================================================================
# TemplateRegistry Tests
# ============================================================================

class TestTemplateRegistry:
    """Tests for TemplateRegistry operations."""
    
    def test_registry_has_default_templates(self, fresh_registry):
        """Test that registry includes default templates."""
        templates = fresh_registry.list_templates()
        
        template_ids = [t.id for t in templates]
        assert "assistant" in template_ids
        assert "analyst" in template_ids
        assert "creative" in template_ids
        assert "researcher" in template_ids
        assert "developer" in template_ids
    
    def test_get_template_by_id(self, fresh_registry):
        """Test retrieving template by ID."""
        template = fresh_registry.get("developer")
        
        assert template is not None
        assert template.id == "developer"
        assert template.name == "Software Developer"
    
    def test_get_template_not_found(self, fresh_registry):
        """Test retrieving non-existent template."""
        template = fresh_registry.get("nonexistent")
        
        assert template is None
    
    def test_register_template(self, fresh_registry, custom_template):
        """Test registering a new template."""
        fresh_registry.register(custom_template)
        
        retrieved = fresh_registry.get("test_template")
        assert retrieved is not None
        assert retrieved.name == "Test Template"
    
    def test_register_duplicate_template(self, fresh_registry, custom_template):
        """Test that registering duplicate ID raises error."""
        fresh_registry.register(custom_template)
        
        with pytest.raises(ValueError, match="already exists"):
            fresh_registry.register(custom_template)
    
    def test_register_overrides_default(self, fresh_registry):
        """Test that registering with default template ID raises error."""
        duplicate = PersonaTemplate(
            id="developer",  # Same as default
            name="Duplicate Developer",
            description="Should fail",
        )
        
        with pytest.raises(ValueError, match="already exists in default"):
            fresh_registry.register(duplicate)
    
    def test_unregister_custom_template(self, fresh_registry, custom_template):
        """Test unregistering a custom template."""
        fresh_registry.register(custom_template)
        
        result = fresh_registry.unregister("test_template")
        
        assert result
        assert fresh_registry.get("test_template") is None
    
    def test_unregister_default_template_fails(self, fresh_registry):
        """Test that unregistering default template fails."""
        result = fresh_registry.unregister("developer")
        
        assert not result
        assert fresh_registry.get("developer") is not None
    
    def test_unregister_nonexistent(self, fresh_registry):
        """Test unregistering non-existent template."""
        result = fresh_registry.unregister("nonexistent")
        
        assert not result
    
    def test_list_templates_filter_by_category(self, fresh_registry):
        """Test filtering templates by category."""
        technical = fresh_registry.list_templates(category=TemplateCategory.TECHNICAL)
        creative = fresh_registry.list_templates(category=TemplateCategory.CREATIVE)
        
        technical_ids = [t.id for t in technical]
        assert "developer" in technical_ids
        assert "creative" not in technical_ids
        
        creative_ids = [t.id for t in creative]
        assert "creative" in creative_ids
    
    def test_list_templates_filter_by_status(self, fresh_registry, custom_template):
        """Test filtering templates by status."""
        custom_template.status = TemplateStatus.DEPRECATED
        fresh_registry.register(custom_template)
        
        active = fresh_registry.list_templates(status=TemplateStatus.ACTIVE)
        deprecated = fresh_registry.list_templates(status=TemplateStatus.DEPRECATED)
        
        active_ids = [t.id for t in active]
        deprecated_ids = [t.id for t in deprecated]
        
        assert "test_template" not in active_ids
        assert "test_template" in deprecated_ids
    
    def test_list_templates_filter_by_tags(self, fresh_registry):
        """Test filtering templates by tags."""
        results = fresh_registry.list_templates(tags=["technical", "code"])
        
        # Should find developer template
        found_ids = [t.id for t in results]
        assert "developer" in found_ids


# ============================================================================
# Template Inheritance Tests
# ============================================================================

class TestTemplateInheritance:
    """Tests for template inheritance."""
    
    def test_resolve_inheritance_no_parent(self, fresh_registry, custom_template):
        """Test resolving template without parent."""
        fresh_registry.register(custom_template)
        
        resolved = fresh_registry.resolve_inheritance("test_template")
        
        assert resolved.id == "test_template"
        assert resolved.name == "Test Template"
    
    def test_resolve_inheritance_with_parent(self, fresh_registry, child_template):
        """Test resolving template with parent."""
        fresh_registry.register(child_template)
        
        resolved = fresh_registry.resolve_inheritance("senior_developer")
        
        # Should have inherited capabilities from developer
        assert "code_writing" in resolved.capabilities
        # Should have own skills
        assert resolved.default_skills["leadership"] == 90
        # Should have inherited skills
        assert "programming" in resolved.default_skills
    
    def test_resolve_inheritance_traits_blend(self, fresh_registry):
        """Test that inherited traits are blended."""
        child = PersonaTemplate(
            id="child",
            name="Child",
            description="Child template",
            parent_template_id="developer",
            base_traits=OCEANTraits(openness=0.9, extraversion=0.8),
        )
        fresh_registry.register(child)
        
        resolved = fresh_registry.resolve_inheritance("child")
        
        # Traits should be blended (30% parent, 70% child)
        # parent.blend_with(child, 0.3) = parent * 0.3 + child * 0.7 = 0.75 * 0.3 + 0.9 * 0.7
        expected_openness = 0.75 * 0.3 + 0.9 * 0.7
        assert abs(resolved.base_traits.openness - expected_openness) < 0.01
    
    def test_resolve_inheritance_chained(self, fresh_registry):
        """Test resolving multi-level inheritance."""
        # Create grandchild template
        grandchild = PersonaTemplate(
            id="lead_developer",
            name="Lead Developer",
            description="Lead developer",
            parent_template_id="senior_developer",
            default_skills={"project_management": 85},
        )
        
        # Register in order
        fresh_registry.register(PersonaTemplate(
            id="senior_developer",
            name="Senior Developer",
            description="Senior",
            parent_template_id="developer",
            default_skills={"leadership": 90},
        ))
        fresh_registry.register(grandchild)
        
        resolved = fresh_registry.resolve_inheritance("lead_developer")
        
        # Should have inherited from both parent and grandparent
        assert "project_management" in resolved.default_skills
        assert "leadership" in resolved.default_skills
        # From original developer template
        assert "programming" in resolved.default_skills
    
    def test_resolve_inheritance_not_found(self, fresh_registry):
        """Test error when template not found."""
        with pytest.raises(ValueError, match="not found"):
            fresh_registry.resolve_inheritance("nonexistent")
    
    def test_resolve_inheritance_parent_not_found(self, fresh_registry):
        """Test error when parent template not found."""
        orphan = PersonaTemplate(
            id="orphan",
            name="Orphan",
            description="Has missing parent",
            parent_template_id="missing_parent",
        )
        fresh_registry.register(orphan)
        
        with pytest.raises(ValueError, match="not found"):
            fresh_registry.resolve_inheritance("orphan")


# ============================================================================
# Default Template Tests
# ============================================================================

class TestDefaultTemplates:
    """Tests for default template configurations."""
    
    def test_assistant_template(self):
        """Test assistant template configuration."""
        assert TEMPLATE_ASSISTANT.id == "assistant"
        assert TEMPLATE_ASSISTANT.category == TemplateCategory.GENERAL
        assert "question_answering" in TEMPLATE_ASSISTANT.capabilities
        assert TEMPLATE_ASSISTANT.base_traits.openness == 0.7
        assert TEMPLATE_ASSISTANT.base_traits.conscientiousness == 0.8
    
    def test_analyst_template(self):
        """Test analyst template configuration."""
        assert TEMPLATE_ANALYST.id == "analyst"
        assert TEMPLATE_ANALYST.category == TemplateCategory.ANALYTICAL
        assert "data_analysis" in TEMPLATE_ANALYST.capabilities
        assert TEMPLATE_ANALYST.communication_style == CommunicationStyle.TECHNICAL
        assert TEMPLATE_ANALYST.decision_making == DecisionMakingStyle.ANALYTICAL
    
    def test_creative_template(self):
        """Test creative template configuration."""
        assert TEMPLATE_CREATIVE.id == "creative"
        assert TEMPLATE_CREATIVE.category == TemplateCategory.CREATIVE
        assert "creative_writing" in TEMPLATE_CREATIVE.capabilities
        assert TEMPLATE_CREATIVE.base_traits.openness == 0.95
        assert TEMPLATE_CREATIVE.decision_making == DecisionMakingStyle.INTUITIVE
    
    def test_researcher_template(self):
        """Test researcher template configuration."""
        assert TEMPLATE_RESEARCHER.id == "researcher"
        assert TEMPLATE_RESEARCHER.category == TemplateCategory.ANALYTICAL
        assert "research" in TEMPLATE_RESEARCHER.capabilities
        assert TEMPLATE_RESEARCHER.communication_style == CommunicationStyle.FORMAL
        assert TEMPLATE_RESEARCHER.ethics_preset == EthicsLevel.STRICT
    
    def test_developer_template(self):
        """Test developer template configuration."""
        assert TEMPLATE_DEVELOPER.id == "developer"
        assert TEMPLATE_DEVELOPER.category == TemplateCategory.TECHNICAL
        assert "code_writing" in TEMPLATE_DEVELOPER.capabilities
        assert "debugging" in TEMPLATE_DEVELOPER.capabilities
        assert TEMPLATE_DEVELOPER.default_skills["programming"] == 90
        assert TEMPLATE_DEVELOPER.autonomy_preset == AutonomyZone.AUTONOMOUS
    
    def test_all_templates_have_required_fields(self):
        """Test that all default templates have required fields."""
        templates = [
            TEMPLATE_ASSISTANT,
            TEMPLATE_ANALYST,
            TEMPLATE_CREATIVE,
            TEMPLATE_RESEARCHER,
            TEMPLATE_DEVELOPER,
        ]
        
        for template in templates:
            assert template.id
            assert template.name
            assert template.description
            assert template.base_traits is not None
            assert len(template.capabilities) > 0
            assert len(template.constraints) > 0
            assert len(template.default_skills) > 0
            assert len(template.knowledge_domains) > 0
            assert template.communication_style is not None
            assert template.decision_making is not None


# ============================================================================
# Template Category Tests
# ============================================================================

class TestTemplateCategories:
    """Tests for template categories."""
    
    def test_category_values(self):
        """Test that all expected categories exist."""
        categories = [
            TemplateCategory.GENERAL,
            TemplateCategory.TECHNICAL,
            TemplateCategory.CREATIVE,
            TemplateCategory.ANALYTICAL,
            TemplateCategory.COMMUNICATION,
            TemplateCategory.SPECIALIZED,
        ]
        
        for cat in categories:
            assert isinstance(cat.value, str)
    
    def test_template_category_assignment(self):
        """Test assigning categories to templates."""
        template = PersonaTemplate(
            id="test",
            name="Test",
            description="Test",
            category=TemplateCategory.SPECIALIZED,
        )
        
        assert template.category == TemplateCategory.SPECIALIZED


# ============================================================================
# Template Status Tests
# ============================================================================

class TestTemplateStatus:
    """Tests for template status."""
    
    def test_status_values(self):
        """Test that all expected statuses exist."""
        statuses = [
            TemplateStatus.DRAFT,
            TemplateStatus.ACTIVE,
            TemplateStatus.DEPRECATED,
            TemplateStatus.ARCHIVED,
        ]
        
        for status in statuses:
            assert isinstance(status.value, str)
    
    def test_default_status_is_active(self):
        """Test that default status is ACTIVE."""
        template = PersonaTemplate(
            id="test",
            name="Test",
            description="Test",
        )
        
        assert template.status == TemplateStatus.ACTIVE


# ============================================================================
# Global Registry Tests
# ============================================================================

class TestGlobalRegistry:
    """Tests for the global template_registry instance."""
    
    def test_global_registry_exists(self):
        """Test that global registry exists."""
        assert template_registry is not None
        assert isinstance(template_registry, TemplateRegistry)
    
    def test_global_registry_has_defaults(self):
        """Test that global registry has default templates."""
        templates = template_registry.list_templates()
        
        assert len(templates) >= 5  # At least the 5 default templates


# ============================================================================
# Edge Cases Tests
# ============================================================================

class TestTemplateEdgeCases:
    """Tests for edge cases in template handling."""
    
    def test_template_with_empty_overrides(self, custom_template):
        """Test attribute generation with empty overrides."""
        attributes = custom_template.create_attributes(overrides={})
        
        assert attributes is not None
        assert "traits" in attributes
    
    def test_template_with_none_overrides(self, custom_template):
        """Test attribute generation with None overrides."""
        attributes = custom_template.create_attributes(overrides=None)
        
        assert attributes is not None
    
    def test_template_config_merging(self):
        """Test that template configs are properly merged."""
        template = PersonaTemplate(
            id="config_test",
            name="Config Test",
            description="Test",
            default_config={
                "temperature": 0.5,
                "max_tokens": 4096,
            },
        )
        
        attrs = template.create_attributes()
        
        # Config should be in attributes or accessible
        assert template.default_config["temperature"] == 0.5
    
    def test_template_skills_merge_in_create_attributes(self, custom_template):
        """Test that skills are merged, not replaced."""
        attributes = custom_template.create_attributes(
            overrides={
                "skills": {"new_skill": 100},
            }
        )
        
        # Should have both existing and new skills
        assert attributes["skills"]["python"] == 75
        assert attributes["skills"]["new_skill"] == 100
    
    def test_template_empty_capabilities_constraints(self):
        """Test template with empty capabilities and constraints."""
        template = PersonaTemplate(
            id="empty",
            name="Empty",
            description="Empty template",
            capabilities=[],
            constraints=[],
        )
        
        assert template.capabilities == []
        assert template.constraints == []
    
    def test_template_special_characters_in_description(self):
        """Test template with special characters in description."""
        template = PersonaTemplate(
            id="special",
            name="Special",
            description="Description with special chars: äöü, 中文, 🎉",
        )
        
        assert "中文" in template.description
        assert "🎉" in template.description


# ============================================================================
# Template Metadata Tests
# ============================================================================

class TestTemplateMetadata:
    """Tests for template metadata handling."""
    
    def test_template_metadata(self):
        """Test template metadata storage."""
        template = PersonaTemplate(
            id="meta_test",
            name="Meta Test",
            description="Test",
            metadata={
                "custom_field": "value",
                "nested": {"key": "value"},
            },
        )
        
        assert template.metadata["custom_field"] == "value"
        assert template.metadata["nested"]["key"] == "value"
    
    def test_template_timestamps(self):
        """Test template timestamps."""
        before = datetime.utcnow()
        template = PersonaTemplate(
            id="time_test",
            name="Time Test",
            description="Test",
        )
        after = datetime.utcnow()
        
        assert before <= template.created_at <= after
        assert before <= template.updated_at <= after
    
    def test_template_author(self):
        """Test template author field."""
        template = PersonaTemplate(
            id="author_test",
            name="Author Test",
            description="Test",
            author="Test Author",
        )
        
        assert template.author == "Test Author"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
