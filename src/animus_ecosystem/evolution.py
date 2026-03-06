"""
AnimusForge Evolution Engine

Self-evolving persona trait mutation system with proposal/approval workflow,
rollback capability, rate limiting, and comprehensive analytics.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import logging
import math
from collections import defaultdict

from pydantic import BaseModel, Field, field_validator, model_validator


logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS
# ============================================================================

class EvolutionTrigger(str, Enum):
    """Triggers that can initiate persona evolution."""
    PERFORMANCE = "performance"
    FEEDBACK = "feedback"
    ADAPTATION = "adaptation"
    LEARNING = "learning"
    MANUAL = "manual"


class EvolutionStatus(str, Enum):
    """Status of an evolution proposal."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    ROLLED_BACK = "rolled_back"
    EXPIRED = "expired"


# ============================================================================
# MODELS
# ============================================================================

class TraitMutation(BaseModel):
    """Represents a single trait mutation in an evolution proposal."""
    trait_name: str = Field(..., min_length=1, max_length=100, description="Name of the trait to mutate")
    old_value: Any = Field(..., description="Current value of the trait")
    new_value: Any = Field(..., description="Proposed new value for the trait")
    reason: str = Field(..., min_length=1, description="Reason for this mutation")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score for this mutation (0-1)")

    @field_validator('trait_name')
    @classmethod
    def validate_trait_name(cls, v: str) -> str:
        return v.strip().lower().replace(' ', '_')

    @field_validator('reason')
    @classmethod
    def validate_reason(cls, v: str) -> str:
        return v.strip()

    def calculate_impact_score(self) -> float:
        """Calculate impact score based on value change magnitude."""
        if isinstance(self.old_value, (int, float)) and isinstance(self.new_value, (int, float)):
            if self.old_value == 0:
                return abs(self.new_value) if self.new_value != 0 else 0.0
            return abs((self.new_value - self.old_value) / self.old_value)
        elif isinstance(self.old_value, str) and isinstance(self.new_value, str):
            # String similarity impact (simple length-based)
            len_diff = abs(len(self.new_value) - len(self.old_value))
            max_len = max(len(self.old_value), len(self.new_value), 1)
            return len_diff / max_len
        elif type(self.old_value) != type(self.new_value):
            # Type change is significant
            return 1.0
        return 0.5  # Default moderate impact for unknown types


class EvolutionProposal(BaseModel):
    """Represents a complete evolution proposal for a persona."""
    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique proposal identifier")
    persona_id: str = Field(..., min_length=1, description="ID of the persona to evolve")
    trigger: EvolutionTrigger = Field(..., description="What triggered this evolution")
    mutations: List[TraitMutation] = Field(..., min_length=1, description="List of trait mutations")
    rationale: str = Field(..., min_length=1, description="Overall rationale for this proposal")
    predicted_impact: Dict[str, float] = Field(default_factory=dict, description="Predicted impact scores")
    status: EvolutionStatus = Field(default=EvolutionStatus.PENDING, description="Current status")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp")
    applied_at: Optional[datetime] = Field(default=None, description="When proposal was applied")
    approved_by: Optional[str] = Field(default=None, description="Who approved this proposal")
    rejected_reason: Optional[str] = Field(default=None, description="Reason for rejection if rejected")
    rolled_back_at: Optional[datetime] = Field(default=None, description="When proposal was rolled back")
    rollback_reason: Optional[str] = Field(default=None, description="Reason for rollback")
    expires_at: Optional[datetime] = Field(default=None, description="Proposal expiration time")

    @field_validator('mutations')
    @classmethod
    def validate_mutations(cls, v: List[TraitMutation]) -> List[TraitMutation]:
        if not v:
            raise ValueError("At least one mutation is required")
        return v

    @field_validator('rationale')
    @classmethod
    def validate_rationale(cls, v: str) -> str:
        return v.strip()

    @model_validator(mode='after')
    def set_default_expiry(self) -> 'EvolutionProposal':
        if self.expires_at is None:
            self.expires_at = self.created_at + timedelta(hours=24)
        return self

    def is_expired(self) -> bool:
        """Check if this proposal has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def is_pending(self) -> bool:
        """Check if proposal is still pending."""
        return self.status == EvolutionStatus.PENDING and not self.is_expired()

    def get_average_confidence(self) -> float:
        """Get average confidence across all mutations."""
        if not self.mutations:
            return 0.0
        return sum(m.confidence for m in self.mutations) / len(self.mutations)

    def get_total_impact_score(self) -> float:
        """Get total impact score for all mutations."""
        return sum(m.calculate_impact_score() for m in self.mutations)


class EvolutionMetrics(BaseModel):
    """Metrics tracking evolution engine performance."""
    total_proposals: int = Field(default=0, ge=0, description="Total number of proposals")
    approved: int = Field(default=0, ge=0, description="Number of approved proposals")
    rejected: int = Field(default=0, ge=0, description="Number of rejected proposals")
    applied: int = Field(default=0, ge=0, description="Number of applied proposals")
    rolled_back: int = Field(default=0, ge=0, description="Number of rolled back proposals")
    avg_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Average confidence score")
    top_mutated_traits: List[str] = Field(default_factory=list, description="Most frequently mutated traits")
    trigger_counts: Dict[str, int] = Field(default_factory=dict, description="Count by trigger type")
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Rate of successful applications")
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def calculate_success_rate(self) -> float:
        """Calculate the success rate of applied proposals."""
        if self.applied == 0:
            return 0.0
        return (self.applied - self.rolled_back) / self.applied


class EvolutionConfig(BaseModel):
    """Configuration for the evolution engine."""
    min_confidence_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum confidence required for auto-approval"
    )
    max_mutations_per_day: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Maximum mutations allowed per persona per day"
    )
    require_approval: bool = Field(
        default=True,
        description="Whether proposals require manual approval"
    )
    rollback_enabled: bool = Field(
        default=True,
        description="Whether rollback is enabled"
    )
    trait_bounds: Dict[str, Tuple[float, float]] = Field(
        default_factory=dict,
        description="Allowed bounds for trait values"
    )
    proposal_expiry_hours: int = Field(
        default=24,
        ge=1,
        le=168,
        description="Hours before a pending proposal expires"
    )
    auto_apply_high_confidence: bool = Field(
        default=False,
        description="Auto-apply proposals with very high confidence"
    )
    high_confidence_threshold: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="Threshold for auto-applying proposals"
    )
    max_rollback_time_hours: int = Field(
        default=48,
        ge=1,
        description="Maximum time after application that rollback is allowed"
    )

    @field_validator('trait_bounds')
    @classmethod
    def validate_trait_bounds(cls, v: Dict[str, Tuple[float, float]]) -> Dict[str, Tuple[float, float]]:
        for trait, bounds in v.items():
            if len(bounds) != 2:
                raise ValueError(f"Trait bounds for {trait} must be a tuple of (min, max)")
            if bounds[0] > bounds[1]:
                raise ValueError(f"Min bound cannot be greater than max for trait {trait}")
        return v


class EvolutionHistory(BaseModel):
    """Evolution history for a specific persona."""
    persona_id: str
    proposals: List[EvolutionProposal] = Field(default_factory=list)
    total_mutations: int = Field(default=0)
    last_evolution: Optional[datetime] = None

    def add_proposal(self, proposal: EvolutionProposal) -> None:
        self.proposals.append(proposal)
        self.total_mutations += len(proposal.mutations)
        if proposal.applied_at:
            self.last_evolution = proposal.applied_at


# ============================================================================
# EXCEPTIONS
# ============================================================================

class EvolutionError(Exception):
    """Base exception for evolution engine errors."""
    pass


class ProposalNotFoundError(EvolutionError):
    """Raised when a proposal is not found."""
    pass


class ProposalNotPendingError(EvolutionError):
    """Raised when trying to approve/reject a non-pending proposal."""
    pass


class ProposalExpiredError(EvolutionError):
    """Raised when trying to act on an expired proposal."""
    pass


class RateLimitExceededError(EvolutionError):
    """Raised when daily mutation limit is exceeded."""
    pass


class MutationValidationError(EvolutionError):
    """Raised when a mutation validation fails."""
    pass


class RollbackNotEnabledError(EvolutionError):
    """Raised when trying to rollback but rollback is disabled."""
    pass


class RollbackTimeExceededError(EvolutionError):
    """Raised when rollback time window has passed."""
    pass


# ============================================================================
# EVOLUTION ENGINE
# ============================================================================

class EvolutionEngine:
    """
    Core evolution engine managing persona trait mutations.

    Features:
    - Proposal/Approval workflow
    - Confidence-based validation
    - Rate limiting
    - Rollback capability
    - Trait bounds validation
    """

    def __init__(self, config: Optional[EvolutionConfig] = None):
        self.config = config or EvolutionConfig()
        self._proposals: Dict[str, EvolutionProposal] = {}
        self._persona_history: Dict[str, EvolutionHistory] = {}
        self._daily_mutations: Dict[str, List[datetime]] = defaultdict(list)
        self._metrics = EvolutionMetrics()
        self._trait_mutation_counts: Dict[str, int] = defaultdict(int)
        logger.info(f"EvolutionEngine initialized with config: {self.config}")

    @property
    def metrics(self) -> EvolutionMetrics:
        """Get current evolution metrics."""
        return self._metrics

    @property
    def config(self) -> EvolutionConfig:
        """Get current configuration."""
        return self._config

    @config.setter
    def config(self, value: EvolutionConfig) -> None:
        self._config = value

    # ------------------------------------------------------------------------
    # Proposal Creation
    # ------------------------------------------------------------------------

    async def propose_evolution(
        self,
        persona_id: str,
        trigger: EvolutionTrigger,
        mutations: List[TraitMutation],
        rationale: str,
        predicted_impact: Optional[Dict[str, float]] = None
    ) -> EvolutionProposal:
        """
        Create a new evolution proposal.

        Args:
            persona_id: ID of the persona to evolve
            trigger: What triggered this evolution
            mutations: List of trait mutations
            rationale: Explanation for the evolution
            predicted_impact: Optional predicted impact scores

        Returns:
            The created EvolutionProposal

        Raises:
            RateLimitExceededError: If daily mutation limit exceeded
            MutationValidationError: If any mutation fails validation
        """
        # Check rate limit
        await self._check_rate_limit(persona_id)

        # Validate all mutations
        for mutation in mutations:
            if not self.validate_mutation(mutation):
                raise MutationValidationError(
                    f"Mutation for trait {mutation.trait_name} failed validation"
                )

        # Create proposal
        proposal = EvolutionProposal(
            persona_id=persona_id,
            trigger=trigger,
            mutations=mutations,
            rationale=rationale,
            predicted_impact=predicted_impact or {}
        )

        # Store proposal
        self._proposals[proposal.id] = proposal
        
        # Track daily mutations for rate limiting
        self._daily_mutations[persona_id].append(datetime.now(timezone.utc))

        # Update history
        if persona_id not in self._persona_history:
            self._persona_history[persona_id] = EvolutionHistory(persona_id=persona_id)
        self._persona_history[persona_id].add_proposal(proposal)

        # Update metrics
        self._metrics.total_proposals += 1
        self._update_trigger_counts(trigger)

        # Track trait mutation counts
        for mutation in mutations:
            self._trait_mutation_counts[mutation.trait_name] += 1

        logger.info(f"Created evolution proposal {proposal.id} for persona {persona_id}")

        # Check for auto-approval
        if self.config.auto_apply_high_confidence:
            if proposal.get_average_confidence() >= self.config.high_confidence_threshold:
                logger.info(f"Auto-applying high confidence proposal {proposal.id}")
                await self.approve_proposal(proposal.id, auto=True)
                await self.apply_proposal(proposal.id)

        return proposal

    async def _check_rate_limit(self, persona_id: str) -> None:
        """Check if persona has exceeded daily mutation limit."""
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Clean old entries
        self._daily_mutations[persona_id] = [
            dt for dt in self._daily_mutations[persona_id]
            if dt >= today_start
        ]

        # Check limit
        if len(self._daily_mutations[persona_id]) >= self.config.max_mutations_per_day:
            raise RateLimitExceededError(
                f"Persona {persona_id} has exceeded daily mutation limit of "
                f"{self.config.max_mutations_per_day}"
            )

    def _update_trigger_counts(self, trigger: EvolutionTrigger) -> None:
        """Update trigger count in metrics."""
        trigger_key = trigger.value
        self._metrics.trigger_counts[trigger_key] =             self._metrics.trigger_counts.get(trigger_key, 0) + 1

    # ------------------------------------------------------------------------
    # Approval Workflow
    # ------------------------------------------------------------------------

    async def approve_proposal(
        self,
        proposal_id: str,
        approver: Optional[str] = None,
        auto: bool = False
    ) -> bool:
        """
        Approve a pending evolution proposal.

        Args:
            proposal_id: ID of the proposal to approve
            approver: Optional ID of the approver
            auto: Whether this is an automatic approval

        Returns:
            True if approved successfully

        Raises:
            ProposalNotFoundError: If proposal not found
            ProposalNotPendingError: If proposal is not pending
            ProposalExpiredError: If proposal has expired
        """
        proposal = self._get_proposal(proposal_id)

        if not proposal.is_pending():
            if proposal.is_expired():
                proposal.status = EvolutionStatus.EXPIRED
                raise ProposalExpiredError(f"Proposal {proposal_id} has expired")
            raise ProposalNotPendingError(
                f"Proposal {proposal_id} is not pending (status: {proposal.status})"
            )

        proposal.status = EvolutionStatus.APPROVED
        proposal.approved_by = approver or ("system" if auto else None)
        self._metrics.approved += 1

        logger.info(f"Approved proposal {proposal_id} by {proposal.approved_by}")
        return True

    async def reject_proposal(
        self,
        proposal_id: str,
        reason: str
    ) -> bool:
        """
        Reject a pending evolution proposal.

        Args:
            proposal_id: ID of the proposal to reject
            reason: Reason for rejection

        Returns:
            True if rejected successfully

        Raises:
            ProposalNotFoundError: If proposal not found
            ProposalNotPendingError: If proposal is not pending
        """
        proposal = self._get_proposal(proposal_id)

        if not proposal.is_pending():
            raise ProposalNotPendingError(
                f"Proposal {proposal_id} is not pending (status: {proposal.status})"
            )

        proposal.status = EvolutionStatus.REJECTED
        proposal.rejected_reason = reason
        self._metrics.rejected += 1

        logger.info(f"Rejected proposal {proposal_id}: {reason}")
        return True

    # ------------------------------------------------------------------------
    # Application & Rollback
    # ------------------------------------------------------------------------

    async def apply_proposal(self, proposal_id: str) -> bool:
        """
        Apply an approved evolution proposal.

        Args:
            proposal_id: ID of the proposal to apply

        Returns:
            True if applied successfully

        Raises:
            ProposalNotFoundError: If proposal not found
            ValueError: If proposal is not approved
        """
        proposal = self._get_proposal(proposal_id)

        if proposal.status != EvolutionStatus.APPROVED:
            raise ValueError(
                f"Cannot apply proposal with status {proposal.status}. "
                f"Proposal must be approved first."
            )

        proposal.status = EvolutionStatus.APPLIED
        proposal.applied_at = datetime.now(timezone.utc)
        
        persona_id = proposal.persona_id

        # Update metrics
        self._metrics.applied += 1
        self._update_metrics_confidence()
        self._update_top_mutated_traits()

        # Update persona history
        if persona_id in self._persona_history:
            self._persona_history[persona_id].last_evolution = proposal.applied_at

        logger.info(f"Applied proposal {proposal_id} for persona {persona_id}")
        return True

    async def rollback_proposal(
        self,
        proposal_id: str,
        reason: Optional[str] = None
    ) -> bool:
        """
        Rollback an applied evolution proposal.

        Args:
            proposal_id: ID of the proposal to rollback
            reason: Optional reason for rollback

        Returns:
            True if rolled back successfully

        Raises:
            ProposalNotFoundError: If proposal not found
            RollbackNotEnabledError: If rollback is disabled
            RollbackTimeExceededError: If rollback time window has passed
            ValueError: If proposal is not applied
        """
        if not self.config.rollback_enabled:
            raise RollbackNotEnabledError("Rollback is disabled in configuration")

        proposal = self._get_proposal(proposal_id)

        if proposal.status != EvolutionStatus.APPLIED:
            raise ValueError(
                f"Cannot rollback proposal with status {proposal.status}. "
                f"Proposal must be applied first."
            )

        # Check rollback time window
        if proposal.applied_at:
            time_since_apply = datetime.now(timezone.utc) - proposal.applied_at
            if time_since_apply > timedelta(hours=self.config.max_rollback_time_hours):
                raise RollbackTimeExceededError(
                    f"Rollback time window of {self.config.max_rollback_time_hours} hours exceeded"
                )

        proposal.status = EvolutionStatus.ROLLED_BACK
        proposal.rolled_back_at = datetime.now(timezone.utc)
        proposal.rollback_reason = reason

        # Update metrics
        self._metrics.rolled_back += 1
        self._metrics.success_rate = self._metrics.calculate_success_rate()

        logger.info(f"Rolled back proposal {proposal_id}: {reason}")
        return True

    # ------------------------------------------------------------------------
    # Query Methods
    # ------------------------------------------------------------------------

    async def get_pending_proposals(
        self,
        persona_id: Optional[str] = None
    ) -> List[EvolutionProposal]:
        """
        Get all pending proposals, optionally filtered by persona.

        Args:
            persona_id: Optional persona ID to filter by

        Returns:
            List of pending proposals
        """
        pending = [
            p for p in self._proposals.values()
            if p.is_pending()
        ]

        if persona_id:
            pending = [p for p in pending if p.persona_id == persona_id]

        return sorted(pending, key=lambda p: p.created_at, reverse=True)

    async def get_persona_evolution_history(
        self,
        persona_id: str
    ) -> List[EvolutionProposal]:
        """
        Get evolution history for a specific persona.

        Args:
            persona_id: ID of the persona

        Returns:
            List of proposals for the persona
        """
        if persona_id in self._persona_history:
            return self._persona_history[persona_id].proposals
        return []

    def get_proposal(self, proposal_id: str) -> Optional[EvolutionProposal]:
        """
        Get a specific proposal by ID.

        Args:
            proposal_id: ID of the proposal

        Returns:
            The proposal or None if not found
        """
        return self._proposals.get(proposal_id)

    def _get_proposal(self, proposal_id: str) -> EvolutionProposal:
        """Get proposal or raise error if not found."""
        if proposal_id not in self._proposals:
            raise ProposalNotFoundError(f"Proposal {proposal_id} not found")
        return self._proposals[proposal_id]

    # ------------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------------

    def validate_mutation(self, mutation: TraitMutation) -> bool:
        """
        Validate a trait mutation against configuration.

        Args:
            mutation: The mutation to validate

        Returns:
            True if valid, False otherwise
        """
        # Check confidence threshold
        if mutation.confidence < self.config.min_confidence_threshold:
            logger.warning(
                f"Mutation confidence {mutation.confidence} below threshold "
                f"{self.config.min_confidence_threshold}"
            )
            return False

        # Check trait bounds if defined
        if mutation.trait_name in self.config.trait_bounds:
            bounds = self.config.trait_bounds[mutation.trait_name]
            if isinstance(mutation.new_value, (int, float)):
                if not (bounds[0] <= mutation.new_value <= bounds[1]):
                    logger.warning(
                        f"Mutation value {mutation.new_value} outside bounds "
                        f"{bounds} for trait {mutation.trait_name}"
                    )
                    return False

        return True

    # ------------------------------------------------------------------------
    # Metrics Updates
    # ------------------------------------------------------------------------

    def _update_metrics_confidence(self) -> None:
        """Update average confidence in metrics."""
        applied_proposals = [
            p for p in self._proposals.values()
            if p.status in (EvolutionStatus.APPLIED, EvolutionStatus.ROLLED_BACK)
        ]

        if applied_proposals:
            total_confidence = sum(p.get_average_confidence() for p in applied_proposals)
            self._metrics.avg_confidence = total_confidence / len(applied_proposals)

        self._metrics.success_rate = self._metrics.calculate_success_rate()
        self._metrics.last_updated = datetime.now(timezone.utc)

    def _update_top_mutated_traits(self, limit: int = 10) -> None:
        """Update top mutated traits in metrics."""
        sorted_traits = sorted(
            self._trait_mutation_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )
        self._metrics.top_mutated_traits = [t[0] for t in sorted_traits[:limit]]

    # ------------------------------------------------------------------------
    # Utility Methods
    # ------------------------------------------------------------------------

    def get_all_proposals(self) -> List[EvolutionProposal]:
        """Get all proposals."""
        return list(self._proposals.values())

    def clear_expired_proposals(self) -> int:
        """Clear all expired proposals and return count."""
        expired_ids = [
            pid for pid, p in self._proposals.items()
            if p.is_expired() and p.status == EvolutionStatus.PENDING
        ]

        for pid in expired_ids:
            self._proposals[pid].status = EvolutionStatus.EXPIRED

        if expired_ids:
            logger.info(f"Cleared {len(expired_ids)} expired proposals")

        return len(expired_ids)

    def get_persona_history(self, persona_id: str) -> Optional[EvolutionHistory]:
        """Get full history for a persona."""
        return self._persona_history.get(persona_id)


# ============================================================================
# EVOLUTION GATEWAY
# ============================================================================

class EvolutionGateway:
    """
    High-level gateway for persona evolution operations.

    Provides:
    - Performance-based evolution analysis
    - Automatic beneficial evolution detection
    - Evolution analytics and insights
    """

    def __init__(self, engine: Optional[EvolutionEngine] = None):
        self.engine = engine or EvolutionEngine()

    async def analyze_and_propose(
        self,
        persona_id: str,
        performance_data: Dict[str, Any],
        current_traits: Optional[Dict[str, Any]] = None
    ) -> Optional[EvolutionProposal]:
        """
        Analyze performance data and propose evolution if beneficial.

        Args:
            persona_id: ID of the persona to analyze
            performance_data: Performance metrics and indicators
            current_traits: Current trait values (for computing mutations)

        Returns:
            EvolutionProposal if beneficial evolution detected, None otherwise
        """
        mutations: List[TraitMutation] = []
        rationale_parts = []
        trigger = EvolutionTrigger.PERFORMANCE

        # Analyze performance metrics
        if "response_time" in performance_data:
            rt = performance_data["response_time"]
            if rt > 2.0:
                if current_traits and "patience" in current_traits:
                    mutations.append(TraitMutation(
                        trait_name="patience",
                        old_value=current_traits["patience"],
                        new_value=min(current_traits["patience"] + 0.1, 1.0),
                        reason="High response time requires increased patience",
                        confidence=0.85
                    ))
                    rationale_parts.append("Response time optimization")

        if "error_rate" in performance_data:
            er = performance_data["error_rate"]
            if er > 0.05:
                if current_traits and "caution" in current_traits:
                    mutations.append(TraitMutation(
                        trait_name="caution",
                        old_value=current_traits["caution"],
                        new_value=min(current_traits["caution"] + 0.15, 1.0),
                        reason="High error rate requires increased caution",
                        confidence=0.9
                    ))
                    rationale_parts.append("Error rate mitigation")

        if "user_satisfaction" in performance_data:
            us = performance_data["user_satisfaction"]
            if us < 0.7:
                if current_traits and "empathy" in current_traits:
                    mutations.append(TraitMutation(
                        trait_name="empathy",
                        old_value=current_traits["empathy"],
                        new_value=min(current_traits["empathy"] + 0.1, 1.0),
                        reason="Low satisfaction requires increased empathy",
                        confidence=0.8
                    ))
                    rationale_parts.append("User satisfaction improvement")

        # Check for adaptation signals
        if "adaptation_signals" in performance_data:
            signals = performance_data["adaptation_signals"]
            if signals:
                trigger = EvolutionTrigger.ADAPTATION
                rationale_parts.append("Adaptation signals detected")

        # Check for learning progress
        if "learning_progress" in performance_data:
            lp = performance_data["learning_progress"]
            if lp > 0.8:
                if current_traits and "curiosity" in current_traits:
                    mutations.append(TraitMutation(
                        trait_name="curiosity",
                        old_value=current_traits["curiosity"],
                        new_value=min(current_traits["curiosity"] + 0.05, 1.0),
                        reason="High learning progress encourages curiosity",
                        confidence=0.75
                    ))
                    trigger = EvolutionTrigger.LEARNING
                    rationale_parts.append("Learning progress reward")

        # If no mutations generated, return None
        if not mutations:
            return None

        # Create proposal
        rationale = "; ".join(rationale_parts) if rationale_parts else "Performance optimization"

        predicted_impact = {
            "performance_improvement": sum(m.confidence for m in mutations) / len(mutations),
            "stability_impact": 0.1 * len(mutations),
            "user_experience_impact": 0.2 if any(m.trait_name == "empathy" for m in mutations) else 0.0
        }

        return await self.engine.propose_evolution(
            persona_id=persona_id,
            trigger=trigger,
            mutations=mutations,
            rationale=rationale,
            predicted_impact=predicted_impact
        )

    async def auto_evolve_if_beneficial(
        self,
        persona_id: str,
        performance_data: Dict[str, Any],
        current_traits: Optional[Dict[str, Any]] = None,
        auto_apply: bool = False
    ) -> bool:
        """
        Automatically propose and optionally apply evolution if beneficial.

        Args:
            persona_id: ID of the persona
            performance_data: Performance metrics
            current_traits: Current trait values
            auto_apply: Whether to auto-apply if approved

        Returns:
            True if evolution was proposed and possibly applied
        """
        proposal = await self.analyze_and_propose(
            persona_id, performance_data, current_traits
        )

        if proposal is None:
            return False

        # Check if should auto-apply
        if auto_apply and not self.engine.config.require_approval:
            await self.engine.approve_proposal(proposal.id, auto=True)
            await self.engine.apply_proposal(proposal.id)
            return True

        return True

    async def get_evolution_analytics(self) -> Dict[str, Any]:
        """
        Get comprehensive evolution analytics.

        Returns:
            Dictionary containing evolution analytics and insights
        """
        metrics = self.engine.metrics

        # Calculate additional analytics
        total_proposals = metrics.total_proposals
        approval_rate = (
            metrics.approved / total_proposals if total_proposals > 0 else 0.0
        )
        application_rate = (
            metrics.applied / metrics.approved if metrics.approved > 0 else 0.0
        )

        # Get trigger distribution
        trigger_distribution = dict(metrics.trigger_counts)

        # Get recent proposals
        recent_proposals = sorted(
            self.engine.get_all_proposals(),
            key=lambda p: p.created_at,
            reverse=True
        )[:10]

        analytics = {
            "overview": {
                "total_proposals": total_proposals,
                "approved": metrics.approved,
                "rejected": metrics.rejected,
                "applied": metrics.applied,
                "rolled_back": metrics.rolled_back,
                "approval_rate": approval_rate,
                "application_rate": application_rate,
                "success_rate": metrics.success_rate
            },
            "confidence": {
                "average": metrics.avg_confidence,
                "min_threshold": self.engine.config.min_confidence_threshold,
                "high_threshold": self.engine.config.high_confidence_threshold
            },
            "traits": {
                "top_mutated": metrics.top_mutated_traits,
                "trait_bounds": self.engine.config.trait_bounds
            },
            "triggers": {
                "distribution": trigger_distribution,
                "most_common": max(
                    trigger_distribution.items(),
                    key=lambda x: x[1]
                )[0] if trigger_distribution else None
            },
            "configuration": {
                "require_approval": self.engine.config.require_approval,
                "rollback_enabled": self.engine.config.rollback_enabled,
                "max_mutations_per_day": self.engine.config.max_mutations_per_day,
                "auto_apply_high_confidence": self.engine.config.auto_apply_high_confidence
            },
            "recent_activity": [
                {
                    "id": p.id,
                    "persona_id": p.persona_id,
                    "trigger": p.trigger.value,
                    "status": p.status.value,
                    "created_at": p.created_at.isoformat(),
                    "mutations_count": len(p.mutations)
                }
                for p in recent_proposals
            ],
            "last_updated": metrics.last_updated.isoformat()
        }

        return analytics

    async def get_persona_evolution_summary(
        self,
        persona_id: str
    ) -> Dict[str, Any]:
        """
        Get evolution summary for a specific persona.

        Args:
            persona_id: ID of the persona

        Returns:
            Evolution summary for the persona
        """
        history = self.engine.get_persona_history(persona_id)

        if history is None:
            return {
                "persona_id": persona_id,
                "exists": False,
                "message": "No evolution history found for this persona"
            }

        proposals_by_status = defaultdict(list)
        for proposal in history.proposals:
            proposals_by_status[proposal.status.value].append(proposal)

        return {
            "persona_id": persona_id,
            "exists": True,
            "total_proposals": len(history.proposals),
            "total_mutations": history.total_mutations,
            "last_evolution": history.last_evolution.isoformat() if history.last_evolution else None,
            "proposals_by_status": {
                status: len(proposals)
                for status, proposals in proposals_by_status.items()
            },
            "recent_proposals": [
                {
                    "id": p.id,
                    "trigger": p.trigger.value,
                    "status": p.status.value,
                    "mutations_count": len(p.mutations),
                    "created_at": p.created_at.isoformat()
                }
                for p in sorted(history.proposals, key=lambda x: x.created_at, reverse=True)[:5]
            ]
        }


# ============================================================================
# MODULE EXPORTS
# ============================================================================

__all__ = [
    # Enums
    "EvolutionTrigger",
    "EvolutionStatus",
    # Models
    "TraitMutation",
    "EvolutionProposal",
    "EvolutionMetrics",
    "EvolutionConfig",
    "EvolutionHistory",
    # Exceptions
    "EvolutionError",
    "ProposalNotFoundError",
    "ProposalNotPendingError",
    "ProposalExpiredError",
    "RateLimitExceededError",
    "MutationValidationError",
    "RollbackNotEnabledError",
    "RollbackTimeExceededError",
    # Classes
    "EvolutionEngine",
    "EvolutionGateway",
]
