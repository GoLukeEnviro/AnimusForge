"""AnimusStage - Agentic Loop Engine Module.

This module implements the PERCEIVE → THINK → ACT → LEARN cognitive architecture
for autonomous AI agents with full audit trail and kill-switch integration.
"""

from animus_stage.loop import (
    # Enums
    LoopPhase,
    LoopStatus,
    ObservationType,
    DecisionType,
    ActionType,
    InsightType,
    
    # Models
    MemoryReference,
    Observation,
    Decision,
    PlannedAction,
    ActionResult,
    Insight,
    
    # Phase Results
    PerceiveResult,
    ThinkResult,
    ActResult,
    LearnResult,
    
    # Context & Result
    LoopContext,
    LoopResult,
    
    # Gateways & Types
    MemoryGateway,
    InMemoryGateway,
    Persona,
    PersonaTraits,
    EthicsConstraint,
    SandboxExecutor,
    DefaultSandboxExecutor,
    
    # Engine
    AgenticLoop,
    
    # Factory
    create_agentic_loop,
)

__all__ = [
    # Enums
    "LoopPhase",
    "LoopStatus",
    "ObservationType",
    "DecisionType",
    "ActionType",
    "InsightType",
    
    # Models
    "MemoryReference",
    "Observation",
    "Decision",
    "PlannedAction",
    "ActionResult",
    "Insight",
    
    # Phase Results
    "PerceiveResult",
    "ThinkResult",
    "ActResult",
    "LearnResult",
    
    # Context & Result
    "LoopContext",
    "LoopResult",
    
    # Gateways & Types
    "MemoryGateway",
    "InMemoryGateway",
    "Persona",
    "PersonaTraits",
    "EthicsConstraint",
    "SandboxExecutor",
    "DefaultSandboxExecutor",
    
    # Engine
    "AgenticLoop",
    
    # Factory
    "create_agentic_loop",
]

__version__ = "1.0.0"
