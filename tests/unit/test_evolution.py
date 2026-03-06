"""
Comprehensive Unit Tests for AnimusForge Evolution Engine

Tests cover:
- EvolutionTrigger and EvolutionStatus enums
- TraitMutation model and validation
- EvolutionProposal model and workflow
- EvolutionMetrics and EvolutionConfig
- EvolutionEngine: propose, approve, reject, apply, rollback
- EvolutionGateway: analytics, auto-evolution
- Rate limiting, validation, error handling
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio

from pydantic import ValidationError

from animus_ecosystem.evolution import (
    # Enums
    EvolutionTrigger,
    EvolutionStatus,
    # Models
    TraitMutation,
    EvolutionProposal,
    EvolutionMetrics,
    EvolutionConfig,
    EvolutionHistory,
    # Exceptions
    EvolutionError,
    ProposalNotFoundError,
    ProposalNotPendingError,
    ProposalExpiredError,
    RateLimitExceededError,
    MutationValidationError,
    RollbackNotEnabledError,
    RollbackTimeExceededError,
    # Classes
    EvolutionEngine,
    EvolutionGateway,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def sample_mutation():
    """Sample trait mutation for testing."""
    return TraitMutation(
        trait_name="patience",
        old_value=0.5,
        new_value=0.7,
        reason="Test mutation",
        confidence=0.85
    )


@pytest.fixture
def sample_mutation_low_confidence():
    """Sample mutation with low confidence."""
    return TraitMutation(
        trait_name="caution",
        old_value=0.3,
        new_value=0.5,
        reason="Low confidence mutation",
        confidence=0.5
    )


@pytest.fixture
def sample_proposal(sample_mutation):
    """Sample evolution proposal for testing."""
    return EvolutionProposal(
        persona_id="persona-123",
        trigger=EvolutionTrigger.PERFORMANCE,
        mutations=[sample_mutation],
        rationale="Test proposal",
        predicted_impact={"performance": 0.2}
    )


@pytest.fixture
def evolution_config():
    """Sample evolution config for testing."""
    return EvolutionConfig(
        min_confidence_threshold=0.7,
        max_mutations_per_day=5,
        require_approval=True,
        rollback_enabled=True,
        trait_bounds={"patience": (0.0, 1.0), "caution": (0.0, 1.0)}
    )


@pytest.fixture
async def evolution_engine(evolution_config):
    """Evolution engine instance for testing."""
    return EvolutionEngine(config=evolution_config)


@pytest.fixture
async def evolution_gateway(evolution_engine):
    """Evolution gateway instance for testing."""
    return EvolutionGateway(engine=evolution_engine)


# ============================================================================
# ENUM TESTS
# ============================================================================

class TestEvolutionTrigger:
    """Tests for EvolutionTrigger enum."""

    def test_trigger_values(self):
        assert EvolutionTrigger.PERFORMANCE.value == "performance"
        assert EvolutionTrigger.FEEDBACK.value == "feedback"
        assert EvolutionTrigger.ADAPTATION.value == "adaptation"
        assert EvolutionTrigger.LEARNING.value == "learning"
        assert EvolutionTrigger.MANUAL.value == "manual"

    def test_trigger_count(self):
        assert len(EvolutionTrigger) == 5

    def test_trigger_from_string(self):
        assert EvolutionTrigger("performance") == EvolutionTrigger.PERFORMANCE
        assert EvolutionTrigger("feedback") == EvolutionTrigger.FEEDBACK


class TestEvolutionStatus:
    """Tests for EvolutionStatus enum."""

    def test_status_values(self):
        assert EvolutionStatus.PENDING.value == "pending"
        assert EvolutionStatus.APPROVED.value == "approved"
        assert EvolutionStatus.REJECTED.value == "rejected"
        assert EvolutionStatus.APPLIED.value == "applied"
        assert EvolutionStatus.ROLLED_BACK.value == "rolled_back"
        assert EvolutionStatus.EXPIRED.value == "expired"

    def test_status_count(self):
        assert len(EvolutionStatus) == 6


# ============================================================================
# TRAIT MUTATION TESTS
# ============================================================================

class TestTraitMutation:
    """Tests for TraitMutation model."""

    def test_create_mutation(self):
        mutation = TraitMutation(
            trait_name="patience",
            old_value=0.5,
            new_value=0.7,
            reason="Test mutation",
            confidence=0.85
        )
        assert mutation.trait_name == "patience"
        assert mutation.old_value == 0.5
        assert mutation.new_value == 0.7
        assert mutation.reason == "Test mutation"
        assert mutation.confidence == 0.85

    def test_trait_name_normalization(self):
        mutation = TraitMutation(
            trait_name="  Patience Level  ",
            old_value=0.5,
            new_value=0.7,
            reason="Test",
            confidence=0.8
        )
        assert mutation.trait_name == "patience_level"

    def test_reason_stripping(self):
        mutation = TraitMutation(
            trait_name="test",
            old_value=0.5,
            new_value=0.7,
            reason="  Test reason  ",
            confidence=0.8
        )
        assert mutation.reason == "Test reason"

    def test_confidence_bounds_valid(self):
        mutation = TraitMutation(
            trait_name="test",
            old_value=0,
            new_value=1,
            reason="Test",
            confidence=0.0
        )
        assert mutation.confidence == 0.0

        mutation = TraitMutation(
            trait_name="test",
            old_value=0,
            new_value=1,
            reason="Test",
            confidence=1.0
        )
        assert mutation.confidence == 1.0

    def test_confidence_bounds_invalid_low(self):
        with pytest.raises(ValidationError):
            TraitMutation(
                trait_name="test",
                old_value=0,
                new_value=1,
                reason="Test",
                confidence=-0.1
            )

    def test_confidence_bounds_invalid_high(self):
        with pytest.raises(ValidationError):
            TraitMutation(
                trait_name="test",
                old_value=0,
                new_value=1,
                reason="Test",
                confidence=1.1
            )

    def test_empty_trait_name(self):
        with pytest.raises(ValidationError):
            TraitMutation(
                trait_name="",
                old_value=0,
                new_value=1,
                reason="Test",
                confidence=0.8
            )

    def test_empty_reason(self):
        with pytest.raises(ValidationError):
            TraitMutation(
                trait_name="test",
                old_value=0,
                new_value=1,
                reason="",
                confidence=0.8
            )

    def test_calculate_impact_score_numeric(self):
        mutation = TraitMutation(
            trait_name="test",
            old_value=0.5,
            new_value=0.7,
            reason="Test",
            confidence=0.8
        )
        impact = mutation.calculate_impact_score()
        assert impact == pytest.approx(0.4, rel=0.01)

    def test_calculate_impact_score_zero_old_value(self):
        mutation = TraitMutation(
            trait_name="test",
            old_value=0,
            new_value=0.5,
            reason="Test",
            confidence=0.8
        )
        impact = mutation.calculate_impact_score()
        assert impact == 0.5

    def test_calculate_impact_score_both_zero(self):
        mutation = TraitMutation(
            trait_name="test",
            old_value=0,
            new_value=0,
            reason="Test",
            confidence=0.8
        )
        impact = mutation.calculate_impact_score()
        assert impact == 0.0

    def test_calculate_impact_score_string(self):
        mutation = TraitMutation(
            trait_name="test",
            old_value="hello",
            new_value="hello world",
            reason="Test",
            confidence=0.8
        )
        impact = mutation.calculate_impact_score()
        assert 0.0 <= impact <= 1.0

    def test_calculate_impact_score_type_change(self):
        mutation = TraitMutation(
            trait_name="test",
            old_value=0.5,
            new_value="different type",
            reason="Test",
            confidence=0.8
        )
        impact = mutation.calculate_impact_score()
        assert impact == 1.0


# ============================================================================
# EVOLUTION PROPOSAL TESTS
# ============================================================================

class TestEvolutionProposal:
    """Tests for EvolutionProposal model."""

    def test_create_proposal(self, sample_mutation):
        proposal = EvolutionProposal(
            persona_id="persona-123",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test proposal"
        )
        assert proposal.persona_id == "persona-123"
        assert proposal.trigger == EvolutionTrigger.PERFORMANCE
        assert len(proposal.mutations) == 1
        assert proposal.status == EvolutionStatus.PENDING
        assert proposal.id is not None
        assert proposal.created_at is not None

    def test_proposal_default_expiry(self, sample_mutation):
        proposal = EvolutionProposal(
            persona_id="persona-123",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test"
        )
        assert proposal.expires_at is not None
        assert proposal.expires_at > proposal.created_at

    def test_proposal_custom_expiry(self, sample_mutation):
        custom_expiry = datetime.now(timezone.utc) + timedelta(hours=48)
        proposal = EvolutionProposal(
            persona_id="persona-123",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test",
            expires_at=custom_expiry
        )
        assert proposal.expires_at == custom_expiry

    def test_proposal_empty_mutations(self):
        with pytest.raises(ValidationError):
            EvolutionProposal(
                persona_id="persona-123",
                trigger=EvolutionTrigger.PERFORMANCE,
                mutations=[],
                rationale="Test"
            )

    def test_proposal_rationale_stripping(self, sample_mutation):
        proposal = EvolutionProposal(
            persona_id="persona-123",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="  Test rationale  "
        )
        assert proposal.rationale == "Test rationale"

    def test_is_expired_false(self, sample_mutation):
        proposal = EvolutionProposal(
            persona_id="persona-123",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test"
        )
        assert not proposal.is_expired()

    def test_is_expired_true(self, sample_mutation):
        proposal = EvolutionProposal(
            persona_id="persona-123",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1)
        )
        assert proposal.is_expired()

    def test_is_pending_true(self, sample_mutation):
        proposal = EvolutionProposal(
            persona_id="persona-123",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test"
        )
        assert proposal.is_pending()

    def test_is_pending_false_when_approved(self, sample_mutation):
        proposal = EvolutionProposal(
            persona_id="persona-123",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test",
            status=EvolutionStatus.APPROVED
        )
        assert not proposal.is_pending()

    def test_is_pending_false_when_expired(self, sample_mutation):
        proposal = EvolutionProposal(
            persona_id="persona-123",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1)
        )
        assert not proposal.is_pending()

    def test_get_average_confidence(self, sample_mutation):
        mutation2 = TraitMutation(
            trait_name="caution",
            old_value=0.3,
            new_value=0.5,
            reason="Test",
            confidence=0.9
        )
        proposal = EvolutionProposal(
            persona_id="persona-123",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation, mutation2],
            rationale="Test"
        )
        avg = proposal.get_average_confidence()
        assert avg == pytest.approx(0.875, rel=0.01)

    def test_get_average_confidence_empty_mutations(self):
        # This should not happen due to validation, but testing edge case
        proposal = EvolutionProposal(
            persona_id="persona-123",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[TraitMutation(
                trait_name="test",
                old_value=0,
                new_value=1,
                reason="Test",
                confidence=0.8
            )],
            rationale="Test"
        )
        assert proposal.get_average_confidence() == 0.8

    def test_get_total_impact_score(self, sample_mutation):
        mutation2 = TraitMutation(
            trait_name="caution",
            old_value=0.3,
            new_value=0.6,
            reason="Test",
            confidence=0.9
        )
        proposal = EvolutionProposal(
            persona_id="persona-123",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation, mutation2],
            rationale="Test"
        )
        total = proposal.get_total_impact_score()
        assert total >= 0


# ============================================================================
# EVOLUTION METRICS TESTS
# ============================================================================

class TestEvolutionMetrics:
    """Tests for EvolutionMetrics model."""

    def test_create_metrics_defaults(self):
        metrics = EvolutionMetrics()
        assert metrics.total_proposals == 0
        assert metrics.approved == 0
        assert metrics.rejected == 0
        assert metrics.applied == 0
        assert metrics.rolled_back == 0
        assert metrics.avg_confidence == 0.0
        assert metrics.top_mutated_traits == []

    def test_calculate_success_rate_no_applied(self):
        metrics = EvolutionMetrics()
        assert metrics.calculate_success_rate() == 0.0

    def test_calculate_success_rate_with_applied(self):
        metrics = EvolutionMetrics(applied=10, rolled_back=2)
        assert metrics.calculate_success_rate() == pytest.approx(0.8, rel=0.01)

    def test_calculate_success_rate_all_rolled_back(self):
        metrics = EvolutionMetrics(applied=5, rolled_back=5)
        assert metrics.calculate_success_rate() == 0.0


# ============================================================================
# EVOLUTION CONFIG TESTS
# ============================================================================

class TestEvolutionConfig:
    """Tests for EvolutionConfig model."""

    def test_create_config_defaults(self):
        config = EvolutionConfig()
        assert config.min_confidence_threshold == 0.7
        assert config.max_mutations_per_day == 5
        assert config.require_approval is True
        assert config.rollback_enabled is True
        assert config.trait_bounds == {}

    def test_custom_config(self):
        config = EvolutionConfig(
            min_confidence_threshold=0.8,
            max_mutations_per_day=10,
            require_approval=False,
            rollback_enabled=False
        )
        assert config.min_confidence_threshold == 0.8
        assert config.max_mutations_per_day == 10
        assert config.require_approval is False
        assert config.rollback_enabled is False

    def test_trait_bounds_validation_valid(self):
        config = EvolutionConfig(
            trait_bounds={"patience": (0.0, 1.0), "caution": (0.0, 0.8)}
        )
        assert "patience" in config.trait_bounds
        assert "caution" in config.trait_bounds

    def test_trait_bounds_validation_invalid_min_max(self):
        with pytest.raises(ValidationError):
            EvolutionConfig(trait_bounds={"patience": (1.0, 0.0)})

    def test_confidence_threshold_bounds(self):
        config = EvolutionConfig(min_confidence_threshold=0.0)
        assert config.min_confidence_threshold == 0.0

        config = EvolutionConfig(min_confidence_threshold=1.0)
        assert config.min_confidence_threshold == 1.0

    def test_confidence_threshold_invalid(self):
        with pytest.raises(ValidationError):
            EvolutionConfig(min_confidence_threshold=1.5)

    def test_max_mutations_per_day_bounds(self):
        config = EvolutionConfig(max_mutations_per_day=1)
        assert config.max_mutations_per_day == 1

        config = EvolutionConfig(max_mutations_per_day=100)
        assert config.max_mutations_per_day == 100

    def test_max_mutations_per_day_invalid(self):
        with pytest.raises(ValidationError):
            EvolutionConfig(max_mutations_per_day=0)


# ============================================================================
# EVOLUTION HISTORY TESTS
# ============================================================================

class TestEvolutionHistory:
    """Tests for EvolutionHistory model."""

    def test_create_history(self):
        history = EvolutionHistory(persona_id="persona-123")
        assert history.persona_id == "persona-123"
        assert history.proposals == []
        assert history.total_mutations == 0
        assert history.last_evolution is None

    def test_add_proposal(self, sample_proposal):
        history = EvolutionHistory(persona_id="persona-123")
        history.add_proposal(sample_proposal)
        assert len(history.proposals) == 1
        assert history.total_mutations == len(sample_proposal.mutations)


# ============================================================================
# EVOLUTION ENGINE TESTS
# ============================================================================

class TestEvolutionEngine:
    """Tests for EvolutionEngine class."""

    @pytest.mark.asyncio
    async def test_engine_initialization(self, evolution_config):
        engine = EvolutionEngine(config=evolution_config)
        assert engine.config == evolution_config
        assert engine.metrics is not None

    @pytest.mark.asyncio
    async def test_engine_default_config(self):
        engine = EvolutionEngine()
        assert engine.config is not None
        assert isinstance(engine.config, EvolutionConfig)

    @pytest.mark.asyncio
    async def test_propose_evolution(self, evolution_engine, sample_mutation):
        proposal = await evolution_engine.propose_evolution(
            persona_id="persona-123",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test proposal"
        )
        assert proposal.id is not None
        assert proposal.persona_id == "persona-123"
        assert proposal.status == EvolutionStatus.PENDING
        assert evolution_engine.metrics.total_proposals == 1

    @pytest.mark.asyncio
    async def test_propose_evolution_with_predicted_impact(self, evolution_engine, sample_mutation):
        proposal = await evolution_engine.propose_evolution(
            persona_id="persona-123",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test proposal",
            predicted_impact={"performance": 0.2}
        )
        assert proposal.predicted_impact == {"performance": 0.2}

    @pytest.mark.asyncio
    async def test_propose_evolution_low_confidence_rejected(self, evolution_engine, sample_mutation_low_confidence):
        with pytest.raises(MutationValidationError):
            await evolution_engine.propose_evolution(
                persona_id="persona-123",
                trigger=EvolutionTrigger.PERFORMANCE,
                mutations=[sample_mutation_low_confidence],
                rationale="Test proposal"
            )

    @pytest.mark.asyncio
    async def test_propose_evolution_out_of_bounds(self, evolution_engine):
        mutation = TraitMutation(
            trait_name="patience",
            old_value=0.5,
            new_value=1.5,  # Out of bounds (0.0, 1.0)
            reason="Test",
            confidence=0.8
        )
        with pytest.raises(MutationValidationError):
            await evolution_engine.propose_evolution(
                persona_id="persona-123",
                trigger=EvolutionTrigger.PERFORMANCE,
                mutations=[mutation],
                rationale="Test proposal"
            )

    @pytest.mark.asyncio
    async def test_approve_proposal(self, evolution_engine, sample_mutation):
        proposal = await evolution_engine.propose_evolution(
            persona_id="persona-123",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test proposal"
        )

        result = await evolution_engine.approve_proposal(proposal.id, approver="admin")
        assert result is True

        updated = evolution_engine.get_proposal(proposal.id)
        assert updated.status == EvolutionStatus.APPROVED
        assert updated.approved_by == "admin"

    @pytest.mark.asyncio
    async def test_approve_nonexistent_proposal(self, evolution_engine):
        with pytest.raises(ProposalNotFoundError):
            await evolution_engine.approve_proposal("nonexistent-id")

    @pytest.mark.asyncio
    async def test_approve_non_pending_proposal(self, evolution_engine, sample_mutation):
        proposal = await evolution_engine.propose_evolution(
            persona_id="persona-123",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test proposal"
        )
        await evolution_engine.approve_proposal(proposal.id)

        with pytest.raises(ProposalNotPendingError):
            await evolution_engine.approve_proposal(proposal.id)

    @pytest.mark.asyncio
    async def test_approve_expired_proposal(self, evolution_engine, sample_mutation):
        proposal = EvolutionProposal(
            persona_id="persona-123",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1)
        )
        evolution_engine._proposals[proposal.id] = proposal

        with pytest.raises(ProposalExpiredError):
            await evolution_engine.approve_proposal(proposal.id)

    @pytest.mark.asyncio
    async def test_reject_proposal(self, evolution_engine, sample_mutation):
        proposal = await evolution_engine.propose_evolution(
            persona_id="persona-123",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test proposal"
        )

        result = await evolution_engine.reject_proposal(proposal.id, "Not beneficial")
        assert result is True

        updated = evolution_engine.get_proposal(proposal.id)
        assert updated.status == EvolutionStatus.REJECTED
        assert updated.rejected_reason == "Not beneficial"

    @pytest.mark.asyncio
    async def test_reject_nonexistent_proposal(self, evolution_engine):
        with pytest.raises(ProposalNotFoundError):
            await evolution_engine.reject_proposal("nonexistent-id", "Reason")

    @pytest.mark.asyncio
    async def test_reject_non_pending_proposal(self, evolution_engine, sample_mutation):
        proposal = await evolution_engine.propose_evolution(
            persona_id="persona-123",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test proposal"
        )
        await evolution_engine.approve_proposal(proposal.id)

        with pytest.raises(ProposalNotPendingError):
            await evolution_engine.reject_proposal(proposal.id, "Too late")

    @pytest.mark.asyncio
    async def test_apply_proposal(self, evolution_engine, sample_mutation):
        proposal = await evolution_engine.propose_evolution(
            persona_id="persona-123",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test proposal"
        )
        await evolution_engine.approve_proposal(proposal.id)

        result = await evolution_engine.apply_proposal(proposal.id)
        assert result is True

        updated = evolution_engine.get_proposal(proposal.id)
        assert updated.status == EvolutionStatus.APPLIED
        assert updated.applied_at is not None

    @pytest.mark.asyncio
    async def test_apply_non_approved_proposal(self, evolution_engine, sample_mutation):
        proposal = await evolution_engine.propose_evolution(
            persona_id="persona-123",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test proposal"
        )

        with pytest.raises(ValueError):
            await evolution_engine.apply_proposal(proposal.id)

    @pytest.mark.asyncio
    async def test_apply_nonexistent_proposal(self, evolution_engine):
        with pytest.raises(ProposalNotFoundError):
            await evolution_engine.apply_proposal("nonexistent-id")

    @pytest.mark.asyncio
    async def test_rollback_proposal(self, evolution_engine, sample_mutation):
        proposal = await evolution_engine.propose_evolution(
            persona_id="persona-123",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test proposal"
        )
        await evolution_engine.approve_proposal(proposal.id)
        await evolution_engine.apply_proposal(proposal.id)

        result = await evolution_engine.rollback_proposal(proposal.id, "Issues detected")
        assert result is True

        updated = evolution_engine.get_proposal(proposal.id)
        assert updated.status == EvolutionStatus.ROLLED_BACK
        assert updated.rolled_back_at is not None
        assert updated.rollback_reason == "Issues detected"

    @pytest.mark.asyncio
    async def test_rollback_disabled(self, sample_mutation):
        config = EvolutionConfig(rollback_enabled=False)
        engine = EvolutionEngine(config=config)

        proposal = await engine.propose_evolution(
            persona_id="persona-123",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test proposal"
        )
        await engine.approve_proposal(proposal.id)
        await engine.apply_proposal(proposal.id)

        with pytest.raises(RollbackNotEnabledError):
            await engine.rollback_proposal(proposal.id)

    @pytest.mark.asyncio
    async def test_rollback_non_applied_proposal(self, evolution_engine, sample_mutation):
        proposal = await evolution_engine.propose_evolution(
            persona_id="persona-123",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test proposal"
        )

        with pytest.raises(ValueError):
            await evolution_engine.rollback_proposal(proposal.id)

    @pytest.mark.asyncio
    async def test_get_pending_proposals(self, evolution_engine, sample_mutation):
        # Create multiple proposals
        proposal1 = await evolution_engine.propose_evolution(
            persona_id="persona-1",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test 1"
        )
        proposal2 = await evolution_engine.propose_evolution(
            persona_id="persona-2",
            trigger=EvolutionTrigger.FEEDBACK,
            mutations=[sample_mutation],
            rationale="Test 2"
        )

        # Approve one
        await evolution_engine.approve_proposal(proposal1.id)

        pending = await evolution_engine.get_pending_proposals()
        assert len(pending) == 1
        assert pending[0].id == proposal2.id

    @pytest.mark.asyncio
    async def test_get_pending_proposals_by_persona(self, evolution_engine, sample_mutation):
        proposal1 = await evolution_engine.propose_evolution(
            persona_id="persona-1",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test 1"
        )
        await evolution_engine.propose_evolution(
            persona_id="persona-2",
            trigger=EvolutionTrigger.FEEDBACK,
            mutations=[sample_mutation],
            rationale="Test 2"
        )

        pending = await evolution_engine.get_pending_proposals(persona_id="persona-1")
        assert len(pending) == 1
        assert pending[0].id == proposal1.id

    @pytest.mark.asyncio
    async def test_get_persona_evolution_history(self, evolution_engine, sample_mutation):
        await evolution_engine.propose_evolution(
            persona_id="persona-1",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test 1"
        )
        await evolution_engine.propose_evolution(
            persona_id="persona-1",
            trigger=EvolutionTrigger.FEEDBACK,
            mutations=[sample_mutation],
            rationale="Test 2"
        )

        history = await evolution_engine.get_persona_evolution_history("persona-1")
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_get_persona_evolution_history_empty(self, evolution_engine):
        history = await evolution_engine.get_persona_evolution_history("nonexistent")
        assert history == []

    @pytest.mark.asyncio
    async def test_rate_limiting(self, evolution_config, sample_mutation):
        config = EvolutionConfig(max_mutations_per_day=2)
        engine = EvolutionEngine(config=config)

        # Create max allowed proposals
        for i in range(2):
            await engine.propose_evolution(
                persona_id="persona-1",
                trigger=EvolutionTrigger.PERFORMANCE,
                mutations=[sample_mutation],
                rationale=f"Test {i}"
            )

        # Try to create one more - should fail
        with pytest.raises(RateLimitExceededError):
            await engine.propose_evolution(
                persona_id="persona-1",
                trigger=EvolutionTrigger.PERFORMANCE,
                mutations=[sample_mutation],
                rationale="Should fail"
            )

    @pytest.mark.asyncio
    async def test_rate_limiting_different_personas(self, evolution_config, sample_mutation):
        config = EvolutionConfig(max_mutations_per_day=1)
        engine = EvolutionEngine(config=config)

        # Each persona should have its own limit
        await engine.propose_evolution(
            persona_id="persona-1",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test 1"
        )
        await engine.propose_evolution(
            persona_id="persona-2",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test 2"
        )

        # Now persona-1 should be at limit
        with pytest.raises(RateLimitExceededError):
            await engine.propose_evolution(
                persona_id="persona-1",
                trigger=EvolutionTrigger.PERFORMANCE,
                mutations=[sample_mutation],
                rationale="Should fail"
            )

    def test_validate_mutation_valid(self, evolution_engine, sample_mutation):
        assert evolution_engine.validate_mutation(sample_mutation) is True

    def test_validate_mutation_low_confidence(self, evolution_engine):
        mutation = TraitMutation(
            trait_name="test",
            old_value=0.5,
            new_value=0.7,
            reason="Test",
            confidence=0.5  # Below threshold of 0.7
        )
        assert evolution_engine.validate_mutation(mutation) is False

    def test_validate_mutation_out_of_bounds(self, evolution_engine):
        mutation = TraitMutation(
            trait_name="patience",  # Bounds are (0.0, 1.0)
            old_value=0.5,
            new_value=1.5,  # Out of bounds
            reason="Test",
            confidence=0.8
        )
        assert evolution_engine.validate_mutation(mutation) is False

    @pytest.mark.asyncio
    async def test_metrics_update_on_proposal(self, evolution_engine, sample_mutation):
        await evolution_engine.propose_evolution(
            persona_id="persona-1",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test"
        )

        assert evolution_engine.metrics.total_proposals == 1
        assert "performance" in evolution_engine.metrics.trigger_counts

    @pytest.mark.asyncio
    async def test_metrics_update_on_approval(self, evolution_engine, sample_mutation):
        proposal = await evolution_engine.propose_evolution(
            persona_id="persona-1",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test"
        )
        await evolution_engine.approve_proposal(proposal.id)

        assert evolution_engine.metrics.approved == 1

    @pytest.mark.asyncio
    async def test_metrics_update_on_rejection(self, evolution_engine, sample_mutation):
        proposal = await evolution_engine.propose_evolution(
            persona_id="persona-1",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test"
        )
        await evolution_engine.reject_proposal(proposal.id, "Reason")

        assert evolution_engine.metrics.rejected == 1

    @pytest.mark.asyncio
    async def test_metrics_update_on_apply(self, evolution_engine, sample_mutation):
        proposal = await evolution_engine.propose_evolution(
            persona_id="persona-1",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test"
        )
        await evolution_engine.approve_proposal(proposal.id)
        await evolution_engine.apply_proposal(proposal.id)

        assert evolution_engine.metrics.applied == 1

    @pytest.mark.asyncio
    async def test_metrics_update_on_rollback(self, evolution_engine, sample_mutation):
        proposal = await evolution_engine.propose_evolution(
            persona_id="persona-1",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test"
        )
        await evolution_engine.approve_proposal(proposal.id)
        await evolution_engine.apply_proposal(proposal.id)
        await evolution_engine.rollback_proposal(proposal.id)

        assert evolution_engine.metrics.rolled_back == 1

    def test_get_all_proposals(self, evolution_engine, sample_mutation):
        # Sync test - need to create proposals first
        proposal = EvolutionProposal(
            persona_id="persona-1",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test"
        )
        evolution_engine._proposals[proposal.id] = proposal

        all_proposals = evolution_engine.get_all_proposals()
        assert len(all_proposals) == 1

    def test_clear_expired_proposals(self, evolution_engine, sample_mutation):
        # Create expired proposal
        expired = EvolutionProposal(
            persona_id="persona-1",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1)
        )
        evolution_engine._proposals[expired.id] = expired

        count = evolution_engine.clear_expired_proposals()
        assert count == 1
        assert evolution_engine._proposals[expired.id].status == EvolutionStatus.EXPIRED

    @pytest.mark.asyncio
    async def test_auto_apply_high_confidence(self, sample_mutation):
        config = EvolutionConfig(
            auto_apply_high_confidence=True,
            high_confidence_threshold=0.8,
            require_approval=False
        )
        engine = EvolutionEngine(config=config)

        high_conf_mutation = TraitMutation(
            trait_name="test",
            old_value=0.5,
            new_value=0.7,
            reason="Test",
            confidence=0.95
        )

        proposal = await engine.propose_evolution(
            persona_id="persona-1",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[high_conf_mutation],
            rationale="Test"
        )

        # Should be auto-applied
        assert proposal.status == EvolutionStatus.APPLIED


# ============================================================================
# EVOLUTION GATEWAY TESTS
# ============================================================================

class TestEvolutionGateway:
    """Tests for EvolutionGateway class."""

    @pytest.mark.asyncio
    async def test_gateway_initialization(self):
        gateway = EvolutionGateway()
        assert gateway.engine is not None

    @pytest.mark.asyncio
    async def test_gateway_with_custom_engine(self, evolution_engine):
        gateway = EvolutionGateway(engine=evolution_engine)
        assert gateway.engine == evolution_engine

    @pytest.mark.asyncio
    async def test_analyze_and_propose_with_high_response_time(self, evolution_gateway):
        performance_data = {
            "response_time": 3.0,
            "error_rate": 0.01,
            "user_satisfaction": 0.8
        }
        current_traits = {"patience": 0.5}

        proposal = await evolution_gateway.analyze_and_propose(
            persona_id="persona-1",
            performance_data=performance_data,
            current_traits=current_traits
        )

        assert proposal is not None
        assert any(m.trait_name == "patience" for m in proposal.mutations)

    @pytest.mark.asyncio
    async def test_analyze_and_propose_with_high_error_rate(self, evolution_gateway):
        performance_data = {
            "response_time": 0.5,
            "error_rate": 0.1,
            "user_satisfaction": 0.8
        }
        current_traits = {"caution": 0.3}

        proposal = await evolution_gateway.analyze_and_propose(
            persona_id="persona-1",
            performance_data=performance_data,
            current_traits=current_traits
        )

        assert proposal is not None
        assert any(m.trait_name == "caution" for m in proposal.mutations)

    @pytest.mark.asyncio
    async def test_analyze_and_propose_with_low_satisfaction(self, evolution_gateway):
        performance_data = {
            "response_time": 0.5,
            "error_rate": 0.01,
            "user_satisfaction": 0.5
        }
        current_traits = {"empathy": 0.5}

        proposal = await evolution_gateway.analyze_and_propose(
            persona_id="persona-1",
            performance_data=performance_data,
            current_traits=current_traits
        )

        assert proposal is not None
        assert any(m.trait_name == "empathy" for m in proposal.mutations)

    @pytest.mark.asyncio
    async def test_analyze_and_propose_with_learning_progress(self, evolution_gateway):
        performance_data = {
            "response_time": 0.5,
            "error_rate": 0.01,
            "user_satisfaction": 0.8,
            "learning_progress": 0.9
        }
        current_traits = {"curiosity": 0.5}

        proposal = await evolution_gateway.analyze_and_propose(
            persona_id="persona-1",
            performance_data=performance_data,
            current_traits=current_traits
        )

        assert proposal is not None
        assert proposal.trigger == EvolutionTrigger.LEARNING

    @pytest.mark.asyncio
    async def test_analyze_and_propose_with_adaptation_signals(self):
        """Test analyze_and_propose with adaptation signals."""
        engine = EvolutionEngine()
        gateway = EvolutionGateway(engine=engine)
        
        # Provide data that triggers mutations + adaptation signals
        performance_data = {
            "response_time": 3.0,  # High - triggers patience mutation
            "error_rate": 0.01,
            "user_satisfaction": 0.8,
            "adaptation_signals": ["signal1", "signal2"]
        }
        current_traits = {"patience": 0.5}
        
        proposal = await gateway.analyze_and_propose(
            persona_id="persona-adaptation-test",
            performance_data=performance_data,
            current_traits=current_traits
        )
        
        assert proposal is not None
        assert proposal.trigger == EvolutionTrigger.ADAPTATION

    @pytest.mark.asyncio
    async def test_analyze_and_propose_no_mutations_needed(self, evolution_gateway):
        performance_data = {
            "response_time": 0.5,
            "error_rate": 0.01,
            "user_satisfaction": 0.9
        }
        current_traits = {}

        proposal = await evolution_gateway.analyze_and_propose(
            persona_id="persona-1",
            performance_data=performance_data,
            current_traits=current_traits
        )

        assert proposal is None

    @pytest.mark.asyncio
    async def test_auto_evolve_if_beneficial_with_auto_apply(self, evolution_gateway):
        # Configure for auto-apply
        evolution_gateway.engine.config.require_approval = False

        performance_data = {
            "response_time": 3.0
        }
        current_traits = {"patience": 0.5}

        result = await evolution_gateway.auto_evolve_if_beneficial(
            persona_id="persona-1",
            performance_data=performance_data,
            current_traits=current_traits,
            auto_apply=True
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_auto_evolve_if_beneficial_without_auto_apply(self, evolution_gateway):
        performance_data = {
            "response_time": 3.0
        }
        current_traits = {"patience": 0.5}

        result = await evolution_gateway.auto_evolve_if_beneficial(
            persona_id="persona-1",
            performance_data=performance_data,
            current_traits=current_traits,
            auto_apply=False
        )

        assert result is True
        # Check that proposal is pending (not applied)
        pending = await evolution_gateway.engine.get_pending_proposals()
        assert len(pending) == 1

    @pytest.mark.asyncio
    async def test_auto_evolve_if_not_beneficial(self, evolution_gateway):
        performance_data = {
            "response_time": 0.5,
            "error_rate": 0.01,
            "user_satisfaction": 0.9
        }

        result = await evolution_gateway.auto_evolve_if_beneficial(
            persona_id="persona-1",
            performance_data=performance_data,
            current_traits={},
            auto_apply=True
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_get_evolution_analytics(self, evolution_gateway, sample_mutation):
        # Create some proposals
        await evolution_gateway.engine.propose_evolution(
            persona_id="persona-1",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test"
        )

        analytics = await evolution_gateway.get_evolution_analytics()

        assert "overview" in analytics
        assert "confidence" in analytics
        assert "traits" in analytics
        assert "triggers" in analytics
        assert "configuration" in analytics
        assert "recent_activity" in analytics

        assert analytics["overview"]["total_proposals"] == 1

    @pytest.mark.asyncio
    async def test_get_evolution_analytics_empty(self, evolution_gateway):
        analytics = await evolution_gateway.get_evolution_analytics()

        assert analytics["overview"]["total_proposals"] == 0
        assert analytics["overview"]["approval_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_get_persona_evolution_summary(self, evolution_gateway, sample_mutation):
        # Create proposals for a persona
        await evolution_gateway.engine.propose_evolution(
            persona_id="persona-1",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test"
        )

        summary = await evolution_gateway.get_persona_evolution_summary("persona-1")

        assert summary["exists"] is True
        assert summary["total_proposals"] == 1
        assert "recent_proposals" in summary

    @pytest.mark.asyncio
    async def test_get_persona_evolution_summary_nonexistent(self, evolution_gateway):
        summary = await evolution_gateway.get_persona_evolution_summary("nonexistent")

        assert summary["exists"] is False
        assert "No evolution history found" in summary["message"]


# ============================================================================
# EXCEPTION TESTS
# ============================================================================

class TestEvolutionExceptions:
    """Tests for evolution exceptions."""

    def test_evolution_error(self):
        error = EvolutionError("Test error")
        assert str(error) == "Test error"

    def test_proposal_not_found_error(self):
        error = ProposalNotFoundError("Proposal not found")
        assert isinstance(error, EvolutionError)

    def test_proposal_not_pending_error(self):
        error = ProposalNotPendingError("Not pending")
        assert isinstance(error, EvolutionError)

    def test_proposal_expired_error(self):
        error = ProposalExpiredError("Expired")
        assert isinstance(error, EvolutionError)

    def test_rate_limit_exceeded_error(self):
        error = RateLimitExceededError("Rate limit exceeded")
        assert isinstance(error, EvolutionError)

    def test_mutation_validation_error(self):
        error = MutationValidationError("Validation failed")
        assert isinstance(error, EvolutionError)

    def test_rollback_not_enabled_error(self):
        error = RollbackNotEnabledError("Rollback disabled")
        assert isinstance(error, EvolutionError)

    def test_rollback_time_exceeded_error(self):
        error = RollbackTimeExceededError("Time exceeded")
        assert isinstance(error, EvolutionError)


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestEvolutionIntegration:
    """Integration tests for the evolution system."""

    @pytest.mark.asyncio
    async def test_full_proposal_workflow(self, evolution_engine, sample_mutation):
        """Test complete workflow: propose -> approve -> apply -> rollback."""
        # Create proposal
        proposal = await evolution_engine.propose_evolution(
            persona_id="persona-1",
            trigger=EvolutionTrigger.PERFORMANCE,
            mutations=[sample_mutation],
            rationale="Test workflow"
        )
        assert proposal.status == EvolutionStatus.PENDING

        # Approve
        await evolution_engine.approve_proposal(proposal.id, approver="admin")
        proposal = evolution_engine.get_proposal(proposal.id)
        assert proposal.status == EvolutionStatus.APPROVED

        # Apply
        await evolution_engine.apply_proposal(proposal.id)
        proposal = evolution_engine.get_proposal(proposal.id)
        assert proposal.status == EvolutionStatus.APPLIED
        assert proposal.applied_at is not None

        # Rollback
        await evolution_engine.rollback_proposal(proposal.id, "Issues found")
        proposal = evolution_engine.get_proposal(proposal.id)
        assert proposal.status == EvolutionStatus.ROLLED_BACK
        assert proposal.rolled_back_at is not None

    @pytest.mark.asyncio
    async def test_rejection_workflow(self, evolution_engine, sample_mutation):
        """Test rejection workflow: propose -> reject."""
        proposal = await evolution_engine.propose_evolution(
            persona_id="persona-1",
            trigger=EvolutionTrigger.FEEDBACK,
            mutations=[sample_mutation],
            rationale="Test rejection"
        )

        await evolution_engine.reject_proposal(proposal.id, "Not beneficial")
        proposal = evolution_engine.get_proposal(proposal.id)
        assert proposal.status == EvolutionStatus.REJECTED
        assert proposal.rejected_reason == "Not beneficial"

    @pytest.mark.asyncio
    async def test_gateway_analyze_approve_apply_workflow(self, evolution_gateway):
        """Test gateway-driven evolution workflow."""
        performance_data = {
            "response_time": 3.5,
            "error_rate": 0.1,
            "user_satisfaction": 0.5
        }
        current_traits = {
            "patience": 0.5,
            "caution": 0.3,
            "empathy": 0.5
        }

        # Analyze and propose
        proposal = await evolution_gateway.analyze_and_propose(
            persona_id="persona-1",
            performance_data=performance_data,
            current_traits=current_traits
        )
        assert proposal is not None

        # Approve
        await evolution_gateway.engine.approve_proposal(proposal.id)

        # Apply
        await evolution_gateway.engine.apply_proposal(proposal.id)

        # Check analytics
        analytics = await evolution_gateway.get_evolution_analytics()
        assert analytics["overview"]["applied"] == 1

    @pytest.mark.asyncio
    async def test_multiple_personas_evolution(self, evolution_engine, sample_mutation):
        """Test evolution for multiple personas."""
        # Create proposals for multiple personas
        for i in range(3):
            await evolution_engine.propose_evolution(
                persona_id=f"persona-{i}",
                trigger=EvolutionTrigger.PERFORMANCE,
                mutations=[sample_mutation],
                rationale=f"Test {i}"
            )

        # Check each persona has history
        for i in range(3):
            history = await evolution_engine.get_persona_evolution_history(f"persona-{i}")
            assert len(history) == 1

    @pytest.mark.asyncio
    async def test_metrics_consistency(self, evolution_engine, sample_mutation):
        """Test that metrics remain consistent through operations."""
        # Create and process multiple proposals
        proposal_ids = []
        for i in range(5):
            proposal = await evolution_engine.propose_evolution(
                persona_id=f"persona-{i % 2}",  # Two personas
                trigger=EvolutionTrigger.PERFORMANCE,
                mutations=[sample_mutation],
                rationale=f"Test {i}"
            )
            proposal_ids.append(proposal.id)

        # Approve some
        for pid in proposal_ids[:3]:
            await evolution_engine.approve_proposal(pid)

        # Reject one
        await evolution_engine.reject_proposal(proposal_ids[3], "Rejected")

        # Apply approved ones
        for pid in proposal_ids[:3]:
            await evolution_engine.apply_proposal(pid)

        # Rollback one
        await evolution_engine.rollback_proposal(proposal_ids[0])

        # Check metrics
        metrics = evolution_engine.metrics
        assert metrics.total_proposals == 5
        assert metrics.approved == 3
        assert metrics.rejected == 1
        assert metrics.applied == 3
        assert metrics.rolled_back == 1

    @pytest.mark.asyncio
    async def test_top_mutated_traits_tracking(self):
        """Test that top mutated traits are tracked correctly."""
        # Configure higher rate limit for this test
        config = EvolutionConfig(max_mutations_per_day=10, require_approval=False)
        evolution_engine = EvolutionEngine(config=config)
        
        # Create mutations for different traits
        traits = ["patience", "caution", "patience", "empathy", "patience", "caution"]
        
        for i, trait in enumerate(traits):
            mutation = TraitMutation(
                trait_name=trait,
                old_value=0.5,
                new_value=0.7,
                reason="Test",
                confidence=0.8
            )
            proposal = await evolution_engine.propose_evolution(
                persona_id=f"persona-traits-{i}",
                trigger=EvolutionTrigger.PERFORMANCE,
                mutations=[mutation],
                rationale="Test"
            )
            # Apply to update metrics
            await evolution_engine.approve_proposal(proposal.id)
            await evolution_engine.apply_proposal(proposal.id)
        
        top_traits = evolution_engine.metrics.top_mutated_traits
        assert len(top_traits) > 0
        # Patience should be most common (3 times)
        assert top_traits[0] == "patience"


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
