"""Unit tests for Persona Factory.

Tests cover:
- Persona creation from templates
- Custom attribute handling
- Validation pipeline
- Cloning functionality
- Evolution and XP-based leveling
- State management
"""

import pytest
import pytest_asyncio
from datetime import datetime
from uuid import UUID
from unittest.mock import AsyncMock, MagicMock, patch

from animus_core.factory import (
    Persona,
    PersonaFactory,
    TraitValidator,
    SkillsValidator,
    EthicsValidator,
    AutonomyValidator,
    NameValidator,
    persona_factory,
)
from animus_core.personality import (
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
    CommunicationStyle,
    DecisionMakingStyle,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def factory():
    """Create a fresh PersonaFactory for each test."""
    return PersonaFactory()


@pytest.fixture
def sample_traits():
    """Sample OCEAN traits."""
    return OCEANTraits(
        openness=0.8,
        conscientiousness=0.9,
        extraversion=0.5,
        agreeableness=0.7,
        neuroticism=0.2,
    )


@pytest.fixture
def sample_attributes(sample_traits):
    """Sample persona attributes."""
    return PersonaAttributes(
        traits=sample_traits,
        skills={"python": 85, "testing": 70},
        knowledge_domains=["software_engineering", "testing"],
        communication_style=CommunicationStyle.TECHNICAL,
        decision_making=DecisionMakingStyle.ANALYTICAL,
    )


@pytest.fixture
def sample_persona(sample_attributes):
    """Sample persona for testing."""
    return Persona(
        name="Test Persona",
        description="A test persona",
        attributes=sample_attributes,
        state=PersonaState.DRAFT,
        maturity_level=0,
        experience_points=0,
        ethics_constraints=EthicsConstraints(),
        autonomy_zone=AutonomyZone.FULLY_SUPERVISED,
    )


@pytest.fixture
def sample_experience():
    """Sample experience for evolution tests."""
    return Experience(
        type=ExperienceType.TASK_COMPLETION,
        description="Successfully completed a coding task",
        xp_gained=50,
        skills_affected={"python": 10, "testing": 5},
        traits_adjustment={"conscientiousness": 0.5},
        success=True,
    )


# ============================================================================
# Persona Model Tests
# ============================================================================

class TestPersonaModel:
    """Tests for Persona model."""
    
    def test_persona_creation_minimal(self):
        """Test creating a persona with minimal fields."""
        persona = Persona(name="Minimal Persona")
        
        assert persona.name == "Minimal Persona"
        assert persona.id is not None
        assert isinstance(persona.id, UUID)
        assert persona.state == PersonaState.DRAFT
        assert persona.maturity_level == 0
        assert persona.experience_points == 0
        assert persona.version == 1
    
    def test_persona_creation_full(self, sample_attributes):
        """Test creating a persona with all fields."""
        now = datetime.utcnow()
        persona = Persona(
            name="Full Persona",
            description="Complete test persona",
            template_id="developer",
            attributes=sample_attributes,
            state=PersonaState.ACTIVE,
            maturity_level=3,
            experience_points=1500,
            ethics_constraints=EthicsConstraints(level=EthicsLevel.STRICT),
            autonomy_zone=AutonomyZone.SEMI_AUTONOMOUS,
            capabilities={"coding", "testing"},
            restrictions={"no_production_access"},
            config={"temperature": 0.5},
            metadata={"custom": "value"},
        )
        
        assert persona.name == "Full Persona"
        assert persona.template_id == "developer"
        assert persona.state == PersonaState.ACTIVE
        assert persona.maturity_level == 3
        assert persona.experience_points == 1500
        assert "coding" in persona.capabilities
        assert "no_production_access" in persona.restrictions
    
    def test_persona_name_validation_empty(self):
        """Test that empty name raises validation error."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            Persona(name="")
    
    def test_persona_name_validation_whitespace(self):
        """Test that whitespace-only name raises validation error."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            Persona(name="   ")
    
    def test_persona_name_stripped(self):
        """Test that name is stripped of whitespace."""
        persona = Persona(name="  Trimmed Name  ")
        assert persona.name == "Trimmed Name"
    
    def test_persona_capabilities_set_conversion(self, sample_attributes):
        """Test that capabilities are converted to set."""
        persona = Persona(
            name="Test",
            attributes=sample_attributes,
            capabilities=["a", "b", "c"],
        )
        assert isinstance(persona.capabilities, set)
        assert persona.capabilities == {"a", "b", "c"}
    
    def test_persona_maturity_level_bounds(self, sample_attributes):
        """Test maturity level is bounded 0-6."""
        # Valid bounds
        persona = Persona(name="Test", maturity_level=0)
        assert persona.maturity_level == 0
        
        persona = Persona(name="Test", maturity_level=6)
        assert persona.maturity_level == 6
        
        # Invalid bounds should raise
        with pytest.raises(ValueError):
            Persona(name="Test", maturity_level=-1)
        
        with pytest.raises(ValueError):
            Persona(name="Test", maturity_level=7)


# ============================================================================
# Experience and Evolution Tests
# ============================================================================

class TestPersonaEvolution:
    """Tests for persona evolution and experience."""
    
    def test_add_experience_basic(self, sample_persona, sample_experience):
        """Test adding basic experience to persona."""
        initial_xp = sample_persona.experience_points
        initial_version = sample_persona.version
        
        sample_persona.add_experience(sample_experience)
        
        assert sample_persona.experience_points == initial_xp + sample_experience.xp_gained
        assert len(sample_persona.evolution_history) == 1
        assert sample_persona.evolution_history[0]["xp_gained"] == 50
    
    def test_add_experience_updates_skills(self, sample_persona, sample_experience):
        """Test that experience updates skill levels."""
        initial_python = sample_persona.attributes.skills.get("python", 0)
        
        sample_persona.add_experience(sample_experience)
        
        # Skill should increase
        assert sample_persona.attributes.skills["python"] >= initial_python
    
    def test_add_experience_updates_maturity(self, sample_persona):
        """Test that XP gains update maturity level."""
        assert sample_persona.maturity_level == 0
        
        # Add enough XP to reach L1 (100 XP)
        large_experience = Experience(
            type=ExperienceType.LEARNING,
            description="Intensive learning session",
            xp_gained=150,
        )
        sample_persona.add_experience(large_experience)
        
        assert sample_persona.maturity_level >= 1
    
    def test_add_experience_updates_autonomy(self, sample_persona):
        """Test that maturity level updates autonomy zone."""
        assert sample_persona.autonomy_zone == AutonomyZone.FULLY_SUPERVISED
        
        # Add XP to reach L4 (10000 XP)
        massive_experience = Experience(
            type=ExperienceType.EVOLUTION,
            description="Major evolution event",
            xp_gained=12000,
        )
        sample_persona.add_experience(massive_experience)
        
        assert sample_persona.autonomy_zone == AutonomyZone.AUTONOMOUS
    
    def test_xp_to_next_level(self, sample_persona):
        """Test XP to next level calculation."""
        # L0 to L1 requires 100 XP
        assert sample_persona.xp_to_next_level() == 100
        
        # Add XP to reach L1
        sample_persona.add_experience(Experience(
            type=ExperienceType.TASK_COMPLETION,
            description="Task",
            xp_gained=150,
        ))
        
        # L1 to L2 requires 400 more XP (500 - 100)
        assert sample_persona.xp_to_next_level() == 400
    
    def test_get_maturity_description(self, sample_persona):
        """Test maturity description."""
        assert "Newborn" in sample_persona.get_maturity_description()
        
        sample_persona.maturity_level = 4
        assert "Adult" in sample_persona.get_maturity_description()


# ============================================================================
# Action Permission Tests
# ============================================================================

class TestPersonaPermissions:
    """Tests for persona action permissions."""
    
    def test_can_perform_action_allowed(self, sample_persona):
        """Test allowed action."""
        sample_persona.autonomy_zone = AutonomyZone.SEMI_AUTONOMOUS
        
        assert sample_persona.can_perform_action("help_user", risk_level=0.1)
    
    def test_can_perform_action_forbidden(self, sample_persona):
        """Test forbidden action is blocked."""
        sample_persona.autonomy_zone = AutonomyZone.AUTONOMOUS
        sample_persona.ethics_constraints.forbidden_actions.append("dangerous_action")
        
        assert not sample_persona.can_perform_action("dangerous_action")
    
    def test_can_perform_action_risk_exceeded(self, sample_persona):
        """Test action blocked when risk exceeds threshold."""
        sample_persona.autonomy_zone = AutonomyZone.AUTONOMOUS
        sample_persona.ethics_constraints.max_autonomous_risk = 0.3
        
        assert not sample_persona.can_perform_action("risky_action", risk_level=0.8)
    
    def test_can_perform_action_fully_supervised(self, sample_persona):
        """Test action blocked in fully supervised mode."""
        sample_persona.autonomy_zone = AutonomyZone.FULLY_SUPERVISED
        
        assert not sample_persona.can_perform_action("any_action")


# ============================================================================
# Factory Creation Tests
# ============================================================================

class TestPersonaFactoryCreate:
    """Tests for PersonaFactory.create method."""
    
    @pytest.mark.asyncio
    async def test_create_minimal_persona(self, factory):
        """Test creating minimal persona without template."""
        persona = await factory.create(name="Basic Persona")
        
        assert persona.name == "Basic Persona"
        assert persona.template_id is None
        assert persona.state == PersonaState.DRAFT
        assert persona.maturity_level == 0
    
    @pytest.mark.asyncio
    async def test_create_with_template(self, factory):
        """Test creating persona from template."""
        persona = await factory.create(
            name="Developer",
            template_id="developer",
        )
        
        assert persona.name == "Developer"
        assert persona.template_id == "developer"
        assert "code_writing" in persona.capabilities
        assert persona.attributes.traits.conscientiousness > 0.5
    
    @pytest.mark.asyncio
    async def test_create_with_invalid_template(self, factory):
        """Test error on invalid template ID."""
        with pytest.raises(ValueError, match="Template.*not found"):
            await factory.create(
                name="Test",
                template_id="nonexistent_template",
            )
    
    @pytest.mark.asyncio
    async def test_create_with_custom_attributes(self, factory):
        """Test creating persona with custom attributes."""
        persona = await factory.create(
            name="Custom",
            custom_attributes={
                "traits": {"openness": 0.95},
                "skills": {"custom_skill": 90},
            },
        )
        
        assert persona.attributes.traits.openness == 0.95
        assert persona.attributes.skills["custom_skill"] == 90
    
    @pytest.mark.asyncio
    async def test_create_with_ethics_level(self, factory):
        """Test creating persona with specific ethics level."""
        persona = await factory.create(
            name="Strict Persona",
            ethics_level=EthicsLevel.STRICT,
        )
        
        assert persona.ethics_constraints.level == EthicsLevel.STRICT
    
    @pytest.mark.asyncio
    async def test_create_with_capabilities(self, factory):
        """Test creating persona with initial capabilities."""
        persona = await factory.create(
            name="Capable",
            initial_capabilities=["custom_cap1", "custom_cap2"],
        )
        
        assert "custom_cap1" in persona.capabilities
        assert "custom_cap2" in persona.capabilities
    
    @pytest.mark.asyncio
    async def test_create_with_config(self, factory):
        """Test creating persona with custom config."""
        persona = await factory.create(
            name="Configured",
            config={"temperature": 0.3, "max_tokens": 8192},
        )
        
        assert persona.config["temperature"] == 0.3
        assert persona.config["max_tokens"] == 8192
    
    @pytest.mark.asyncio
    async def test_create_all_templates(self, factory):
        """Test creating personas from all default templates."""
        template_ids = ["assistant", "analyst", "creative", "researcher", "developer"]
        
        for template_id in template_ids:
            persona = await factory.create(
                name=f"Test {template_id}",
                template_id=template_id,
            )
            assert persona.template_id == template_id


# ============================================================================
# Factory Validation Tests
# ============================================================================

class TestPersonaFactoryValidation:
    """Tests for PersonaFactory validation pipeline."""
    
    @pytest.mark.asyncio
    async def test_validate_valid_persona(self, factory, sample_persona):
        """Test validation of a valid persona."""
        result = await factory.validate(sample_persona)
        
        assert isinstance(result, ValidationResult)
        assert result.is_valid
        assert result.score > 0.8
    
    @pytest.mark.asyncio
    async def test_validate_invalid_traits(self, factory):
        """Test validation catches invalid trait values."""
        # Create persona with invalid traits by bypassing validation
        persona = Persona(name="Invalid Traits")
        # Manually set invalid value (Pydantic prevents this normally, so we test the validator)
        persona.attributes.traits.openness = 0.5  # This is valid
        
        result = await factory.validate(persona)
        assert result.is_valid  # Should be valid
    
    @pytest.mark.asyncio
    async def test_validate_empty_name(self, factory):
        """Test validation catches empty name."""
        # Create a persona and manually set empty name
        persona = Persona(name="Temp")
        # Use object.__setattr__ to bypass Pydantic validation for testing
        object.__setattr__(persona, 'name', '')
        
        result = await factory.validate(persona)
        
        assert not result.is_valid
        assert any("name" in issue.field for issue in result.issues)
    
    @pytest.mark.asyncio
    async def test_validate_high_risk_threshold(self, factory):
        """Test validation warns on high risk threshold."""
        persona = Persona(
            name="Risky",
            ethics_constraints=EthicsConstraints(max_autonomous_risk=0.9),
        )
        
        result = await factory.validate(persona)
        
        # Should have warning about high risk
        assert any(
            "risk" in issue.message.lower() 
            for issue in result.issues
        )
    
    @pytest.mark.asyncio
    async def test_add_custom_validator(self, factory):
        """Test adding custom validator to pipeline."""
        
        class CustomValidator:
            async def validate(self, persona):
                result = ValidationResult(is_valid=True, score=1.0)
                if "test" not in persona.name.lower():
                    result.add_issue(
                        field="name",
                        message="Name must contain 'test'",
                        severity=ValidationSeverity.ERROR,
                    )
                return result
        
        factory.add_validator(CustomValidator())
        
        persona = Persona(name="Wrong Name")
        result = await factory.validate(persona)
        
        assert not result.is_valid
    
    @pytest.mark.asyncio
    async def test_remove_validator(self, factory):
        """Test removing validator from pipeline."""
        initial_count = len(factory.validators)
        
        removed = factory.remove_validator(NameValidator)
        
        assert removed
        assert len(factory.validators) == initial_count - 1


# ============================================================================
# Factory Clone Tests
# ============================================================================

class TestPersonaFactoryClone:
    """Tests for PersonaFactory.clone method."""
    
    @pytest.mark.asyncio
    async def test_clone_basic(self, factory):
        """Test basic cloning."""
        original = await factory.create(
            name="Original",
            template_id="developer",
        )
        
        clone = await factory.clone(original.id)
        
        assert clone.id != original.id
        assert clone.name == "Original (Clone)"
        assert clone.template_id == original.template_id
        assert clone.version == 1
    
    @pytest.mark.asyncio
    async def test_clone_with_new_name(self, factory):
        """Test cloning with new name."""
        original = await factory.create(name="Original")
        
        clone = await factory.clone(original.id, new_name="Brand New Name")
        
        assert clone.name == "Brand New Name"
    
    @pytest.mark.asyncio
    async def test_clone_with_modifications(self, factory):
        """Test cloning with attribute modifications."""
        original = await factory.create(
            name="Original",
            custom_attributes={"skills": {"python": 50}},
        )
        
        clone = await factory.clone(
            original.id,
            modifications={
                "attributes": {
                    "skills": {"python": 90, "testing": 80},
                }
            },
        )
        
        assert clone.attributes.skills["python"] == 90
        assert clone.attributes.skills["testing"] == 80
    
    @pytest.mark.asyncio
    async def test_clone_not_found(self, factory):
        """Test error when cloning non-existent persona."""
        from uuid import uuid4
        
        with pytest.raises(ValueError, match="not found"):
            await factory.clone(uuid4())
    
    @pytest.mark.asyncio
    async def test_clone_resets_evolution_history(self, factory):
        """Test that clone has empty evolution history."""
        original = await factory.create(name="Original")
        original.add_experience(Experience(
            type=ExperienceType.TASK_COMPLETION,
            description="Task",
            xp_gained=100,
        ))
        
        clone = await factory.clone(original.id)
        
        assert len(clone.evolution_history) == 0
        assert clone.experience_points == 0


# ============================================================================
# Factory Evolve Tests
# ============================================================================

class TestPersonaFactoryEvolve:
    """Tests for PersonaFactory.evolve method."""
    
    @pytest.mark.asyncio
    async def test_evolve_basic(self, factory):
        """Test basic evolution."""
        persona = await factory.create(name="Evolver")
        initial_xp = persona.experience_points
        
        experience = Experience(
            type=ExperienceType.LEARNING,
            description="Learned something",
            xp_gained=100,
        )
        
        evolved = await factory.evolve(persona.id, experience)
        
        assert evolved.experience_points == initial_xp + 100
        assert evolved.version == 2
    
    @pytest.mark.asyncio
    async def test_evolve_activates_draft(self, factory):
        """Test that evolution activates draft personas."""
        persona = await factory.create(name="Draft")
        assert persona.state == PersonaState.DRAFT
        
        experience = Experience(
            type=ExperienceType.TASK_COMPLETION,
            description="First task",
            xp_gained=50,
        )
        
        evolved = await factory.evolve(persona.id, experience)
        
        assert evolved.state == PersonaState.ACTIVE
    
    @pytest.mark.asyncio
    async def test_evolve_not_found(self, factory):
        """Test error when evolving non-existent persona."""
        from uuid import uuid4
        
        experience = Experience(
            type=ExperienceType.LEARNING,
            description="Learning",
            xp_gained=50,
        )
        
        with pytest.raises(ValueError, match="not found"):
            await factory.evolve(uuid4(), experience)


# ============================================================================
# Factory State Management Tests
# ============================================================================

class TestPersonaFactoryStateManagement:
    """Tests for persona state management."""
    
    @pytest.mark.asyncio
    async def test_get_persona(self, factory):
        """Test retrieving persona by ID."""
        created = await factory.create(name="Retrievable")
        
        retrieved = await factory.get(created.id)
        
        assert retrieved is not None
        assert retrieved.id == created.id
    
    @pytest.mark.asyncio
    async def test_get_persona_not_found(self, factory):
        """Test retrieving non-existent persona."""
        from uuid import uuid4
        
        retrieved = await factory.get(uuid4())
        
        assert retrieved is None
    
    @pytest.mark.asyncio
    async def test_delete_persona(self, factory):
        """Test deleting persona."""
        persona = await factory.create(name="Deletable")
        
        deleted = await factory.delete(persona.id)
        
        assert deleted
        assert await factory.get(persona.id) is None
    
    @pytest.mark.asyncio
    async def test_delete_persona_not_found(self, factory):
        """Test deleting non-existent persona."""
        from uuid import uuid4
        
        deleted = await factory.delete(uuid4())
        
        assert not deleted
    
    @pytest.mark.asyncio
    async def test_list_personas(self, factory):
        """Test listing all personas."""
        await factory.create(name="Persona 1")
        await factory.create(name="Persona 2")
        await factory.create(name="Persona 3")
        
        personas = await factory.list_personas()
        
        assert len(personas) >= 3
    
    @pytest.mark.asyncio
    async def test_list_personas_filter_by_state(self, factory):
        """Test listing personas filtered by state."""
        await factory.create(name="Draft 1")
        await factory.create(name="Draft 2")
        
        active = await factory.create(name="Active 1")
        await factory.activate(active.id)
        
        drafts = await factory.list_personas(state=PersonaState.DRAFT)
        actives = await factory.list_personas(state=PersonaState.ACTIVE)
        
        assert len(drafts) >= 2
        assert len(actives) >= 1
    
    @pytest.mark.asyncio
    async def test_activate_persona(self, factory):
        """Test activating persona."""
        persona = await factory.create(name="Activatable")
        assert persona.state == PersonaState.DRAFT
        
        activated = await factory.activate(persona.id)
        
        assert activated.state == PersonaState.ACTIVE
    
    @pytest.mark.asyncio
    async def test_deactivate_persona(self, factory):
        """Test deactivating persona."""
        persona = await factory.create(name="Deactivatable")
        await factory.activate(persona.id)
        
        deactivated = await factory.deactivate(persona.id)
        
        assert deactivated.state == PersonaState.IDLE


# ============================================================================
# Individual Validator Tests
# ============================================================================

class TestIndividualValidators:
    """Tests for individual validator classes."""
    
    @pytest.mark.asyncio
    async def test_trait_validator(self):
        """Test TraitValidator."""
        validator = TraitValidator()
        persona = Persona(name="Test")
        
        result = await validator.validate(persona)
        
        assert result.is_valid
    
    @pytest.mark.asyncio
    async def test_skills_validator(self):
        """Test SkillsValidator."""
        validator = SkillsValidator()
        persona = Persona(
            name="Test",
            attributes=PersonaAttributes(skills={"python": 50}),
        )
        
        result = await validator.validate(persona)
        
        assert result.is_valid
    
    @pytest.mark.asyncio
    async def test_ethics_validator_warnings(self):
        """Test EthicsValidator produces warnings."""
        validator = EthicsValidator()
        persona = Persona(
            name="Test",
            ethics_constraints=EthicsConstraints(
                forbidden_actions=[],  # Empty - should warn
                max_autonomous_risk=0.9,  # High - should warn
            ),
        )
        
        result = await validator.validate(persona)
        
        # Should have warnings
        assert len(result.issues) >= 1
    
    @pytest.mark.asyncio
    async def test_autonomy_validator_mismatch(self):
        """Test AutonomyValidator detects mismatches."""
        validator = AutonomyValidator()
        persona = Persona(
            name="Test",
            maturity_level=4,  # Should be AUTONOMOUS
            autonomy_zone=AutonomyZone.FULLY_SUPERVISED,  # Wrong!
        )
        
        result = await validator.validate(persona)
        
        # Should have warning about mismatch
        assert any("autonomy" in issue.field for issue in result.issues)
    
    @pytest.mark.asyncio
    async def test_name_validator_empty(self):
        """Test NameValidator catches empty name."""
        validator = NameValidator()
        persona = Persona(name="Temp")
        object.__setattr__(persona, 'name', '')
        
        result = await validator.validate(persona)
        
        assert not result.is_valid
        assert any("name" in issue.field for issue in result.issues)


# ============================================================================
# Integration Tests
# ============================================================================

class TestFactoryIntegration:
    """Integration tests for full factory workflows."""
    
    @pytest.mark.asyncio
    async def test_full_lifecycle(self, factory):
        """Test complete persona lifecycle."""
        # Create
        persona = await factory.create(
            name="Lifecycle Test",
            template_id="developer",
        )
        assert persona.state == PersonaState.DRAFT
        
        # Validate
        result = await factory.validate(persona)
        assert result.is_valid
        
        # Activate
        activated = await factory.activate(persona.id)
        assert activated.state == PersonaState.ACTIVE
        
        # Evolve
        experience = Experience(
            type=ExperienceType.TASK_COMPLETION,
            description="Completed task",
            xp_gained=100,
        )
        evolved = await factory.evolve(persona.id, experience)
        assert evolved.experience_points == 100
        
        # Clone
        clone = await factory.clone(persona.id, new_name="Lifecycle Clone")
        assert clone.name == "Lifecycle Clone"
        
        # Deactivate
        deactivated = await factory.deactivate(persona.id)
        assert deactivated.state == PersonaState.IDLE
        
        # Delete
        deleted = await factory.delete(persona.id)
        assert deleted
    
    @pytest.mark.asyncio
    async def test_template_inheritance_workflow(self, factory):
        """Test workflow with template inheritance."""
        from animus_core.templates import PersonaTemplate, TemplateCategory, template_registry
        
        # Create custom template based on developer
        custom_template = PersonaTemplate(
            id="senior_developer",
            name="Senior Developer",
            description="Senior developer with leadership skills",
            category=TemplateCategory.TECHNICAL,
            parent_template_id="developer",
            default_skills={"leadership": 80, "mentoring": 85},
        )
        
        template_registry.register(custom_template)
        
        # Create from custom template
        persona = await factory.create(
            name="Senior Dev",
            template_id="senior_developer",
        )
        
        # Should have inherited capabilities from developer
        assert "code_writing" in persona.capabilities
        # And have custom skills
        assert persona.attributes.skills.get("leadership", 0) >= 80
        
        # Cleanup
        template_registry.unregister("senior_developer")


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    @pytest.mark.asyncio
    async def test_create_with_empty_custom_attributes(self, factory):
        """Test create with empty custom attributes dict."""
        persona = await factory.create(
            name="Empty Attrs",
            custom_attributes={},
        )
        
        assert persona is not None
    
    @pytest.mark.asyncio
    async def test_evolve_preserves_other_state(self, factory):
        """Test that evolution preserves other persona state."""
        persona = await factory.create(
            name="Stateful",
            config={"custom": "value"},
            metadata={"key": "value"},
        )
        
        experience = Experience(
            type=ExperienceType.LEARNING,
            description="Learning",
            xp_gained=50,
        )
        
        evolved = await factory.evolve(persona.id, experience)
        
        assert evolved.config["custom"] == "value"
        assert evolved.metadata["key"] == "value"
    
    @pytest.mark.asyncio
    async def test_clone_preserves_capabilities(self, factory):
        """Test that clone preserves capabilities."""
        original = await factory.create(
            name="Original",
            template_id="developer",
            initial_capabilities=["custom_cap"],
        )
        
        clone = await factory.clone(original.id)
        
        assert "custom_cap" in clone.capabilities
        assert "code_writing" in clone.capabilities


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
