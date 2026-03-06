"""
AnimusForge Ecosystem Module

Contains evolution engine, health monitoring, and ecological management
for self-evolving digital personas.
"""

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
