"""
AnimusForge Agentic Loop Engine
PERCEIVE → THINK → ACT → LEARN Cognitive Architecture

SPRINT2-002 Implementation
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar, TYPE_CHECKING
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

if TYPE_CHECKING:
    from animus_stage.kill_switch import (
        KillSwitchController,
        KillSwitchLevel,
        HealthStatus,
        TriggerSource,
    )
    from animus_resilience.llm_gateway import LLMGateway, LLMResponse

logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class LoopPhase(str, Enum):
    """Agentic loop phases following cognitive architecture."""
    PERCEIVE = "perceive"
    THINK = "think"
    ACT = "act"
    LEARN = "learn"

    def __str__(self) -> str:
        return self.value


class LoopStatus(str, Enum):
    """Status of loop execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"
    PAUSED = "paused"

    def __str__(self) -> str:
        return self.value


class ObservationType(str, Enum):
    """Types of observations in PERCEIVE phase."""
    USER_INPUT = "user_input"
    SYSTEM_EVENT = "system_event"
    MEMORY_RECALL = "memory_recall"
    ENVIRONMENT = "environment"
    FEEDBACK = "feedback"
    ERROR = "error"

    def __str__(self) -> str:
        return self.value


class DecisionType(str, Enum):
    """Types of decisions in THINK phase."""
    ACTION_SELECTION = "action_selection"
    TOOL_CHOICE = "tool_choice"
    RESPONSE_GENERATION = "response_generation"
    CLARIFICATION = "clarification"
    DEFERRAL = "deferral"
    TERMINATION = "termination"

    def __str__(self) -> str:
        return self.value


class ActionType(str, Enum):
    """Types of actions in ACT phase."""
    TOOL_EXECUTION = "tool_execution"
    RESPONSE = "response"
    MEMORY_STORE = "memory_store"
    EXTERNAL_API = "external_api"
    FILE_OPERATION = "file_operation"
    COMMUNICATION = "communication"

    def __str__(self) -> str:
        return self.value


class InsightType(str, Enum):
    """Types of insights in LEARN phase."""
    SUCCESS_PATTERN = "success_pattern"
    FAILURE_PATTERN = "failure_pattern"
    BEHAVIOR_ADJUSTMENT = "behavior_adjustment"
    KNOWLEDGE_GAIN = "knowledge_gain"
    PREFERENCE_UPDATE = "preference_update"
    SKILL_IMPROVEMENT = "skill_improvement"

    def __str__(self) -> str:
        return self.value


# ============================================================================
# Supporting Models
# ============================================================================

class MemoryReference(BaseModel):
    """Reference to a memory entry."""
    model_config = ConfigDict(frozen=True)

    memory_id: str = Field(..., description="Unique memory identifier")
    relevance_score: float = Field(ge=0.0, le=1.0, description="Relevance to current context")
    content_preview: str = Field(max_length=200, description="Preview of memory content")
    source: str = Field(default="unknown", description="Source of the memory")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Observation(BaseModel):
    """Single observation from PERCEIVE phase."""
    model_config = ConfigDict(frozen=False)

    observation_id: str = Field(default_factory=lambda: str(uuid4()))
    observation_type: ObservationType
    content: str = Field(..., description="The observed content")
    source: str = Field(default="system", description="Source of observation")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Observation content cannot be empty")
        return v


class Decision(BaseModel):
    """Decision made during THINK phase."""
    model_config = ConfigDict(frozen=False)

    decision_id: str = Field(default_factory=lambda: str(uuid4()))
    decision_type: DecisionType
    reasoning: str = Field(..., description="Reasoning behind the decision")
    selected_option: str = Field(..., description="The selected option")
    alternatives: List[str] = Field(default_factory=list, description="Alternative options considered")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    ethics_approved: bool = Field(default=True, description="Passed ethics check")
    ethics_concerns: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PlannedAction(BaseModel):
    """Action planned during THINK phase."""
    model_config = ConfigDict(frozen=False)

    action_id: str = Field(default_factory=lambda: str(uuid4()))
    action_type: ActionType
    description: str = Field(..., description="Description of the action")
    tool_name: Optional[str] = Field(None, description="Tool to execute if applicable")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    expected_outcome: str = Field(default="", description="Expected outcome")
    priority: int = Field(default=5, ge=1, le=10)
    dependencies: List[str] = Field(default_factory=list, description="IDs of dependent actions")
    rollback_plan: Optional[str] = Field(None, description="Rollback strategy if action fails")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ActionResult(BaseModel):
    """Result of an executed action."""
    model_config = ConfigDict(frozen=False)

    action_id: str
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    execution_time_ms: float = Field(default=0.0, ge=0.0)
    side_effects: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Insight(BaseModel):
    """Insight gained during LEARN phase."""
    model_config = ConfigDict(frozen=False)

    insight_id: str = Field(default_factory=lambda: str(uuid4()))
    insight_type: InsightType
    description: str = Field(..., description="Description of the insight")
    evidence: List[str] = Field(default_factory=list, description="Supporting evidence")
    applicability: float = Field(default=0.8, ge=0.0, le=1.0, description="How broadly applicable")
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================================
# Phase Result Models
# ============================================================================

class PerceiveResult(BaseModel):
    """Result of PERCEIVE phase."""
    model_config = ConfigDict(frozen=False)

    observations: List[Observation] = Field(default_factory=list)
    context_summary: str = Field(default="", description="Summary of perceived context")
    relevant_memories: List[MemoryReference] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    processing_time_ms: float = Field(default=0.0, ge=0.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def has_observations(self) -> bool:
        return len(self.observations) > 0

    @property
    def observation_count(self) -> int:
        return len(self.observations)


class ThinkResult(BaseModel):
    """Result of THINK phase."""
    model_config = ConfigDict(frozen=False)

    reasoning: str = Field(default="", description="Overall reasoning process")
    decisions: List[Decision] = Field(default_factory=list)
    planned_actions: List[PlannedAction] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    ethics_violations: List[str] = Field(default_factory=list)
    requires_clarification: bool = Field(default=False)
    clarification_questions: List[str] = Field(default_factory=list)
    processing_time_ms: float = Field(default=0.0, ge=0.0)
    llm_tokens_used: int = Field(default=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def has_planned_actions(self) -> bool:
        return len(self.planned_actions) > 0

    @property
    def action_count(self) -> int:
        return len(self.planned_actions)

    @property
    def has_ethics_violations(self) -> bool:
        return len(self.ethics_violations) > 0


class ActResult(BaseModel):
    """Result of ACT phase."""
    model_config = ConfigDict(frozen=False)

    actions_taken: List[ActionResult] = Field(default_factory=list)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    success: bool = Field(default=True)
    errors: List[str] = Field(default_factory=list)
    total_execution_time_ms: float = Field(default=0.0, ge=0.0)
    killed: bool = Field(default=False, description="Whether execution was killed")
    kill_reason: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def successful_action_count(self) -> int:
        return sum(1 for a in self.actions_taken if a.success)

    @property
    def failed_action_count(self) -> int:
        return sum(1 for a in self.actions_taken if not a.success)

    @property
    def success_rate(self) -> float:
        if not self.actions_taken:
            return 1.0
        return self.successful_action_count / len(self.actions_taken)


class LearnResult(BaseModel):
    """Result of LEARN phase."""
    model_config = ConfigDict(frozen=False)

    insights: List[Insight] = Field(default_factory=list)
    experience_gained: int = Field(default=0, ge=0, description="XP gained from this iteration")
    memories_created: List[str] = Field(default_factory=list, description="IDs of created memories")
    trait_adjustments: Dict[str, float] = Field(default_factory=dict, description="Persona trait adjustments")
    skill_improvements: Dict[str, float] = Field(default_factory=dict)
    feedback_summary: str = Field(default="")
    processing_time_ms: float = Field(default=0.0, ge=0.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def has_insights(self) -> bool:
        return len(self.insights) > 0

    @property
    def has_learning(self) -> bool:
        return (
            self.has_insights or
            self.experience_gained > 0 or
            len(self.memories_created) > 0 or
            len(self.trait_adjustments) > 0
        )


# ============================================================================
# Loop Context and Result
# ============================================================================

class LoopContext(BaseModel):
    """Context maintained throughout the agentic loop execution."""
    model_config = ConfigDict(frozen=False, arbitrary_types_allowed=True)

    loop_id: str = Field(default_factory=lambda: str(uuid4()))
    persona_id: str = Field(..., description="ID of the executing persona")
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    current_phase: LoopPhase = Field(default=LoopPhase.PERCEIVE)
    status: LoopStatus = Field(default=LoopStatus.PENDING)

    input_data: Dict[str, Any] = Field(default_factory=dict)
    perceived_data: Optional[PerceiveResult] = None
    thought_result: Optional[ThinkResult] = None
    action_result: Optional[ActResult] = None
    learning_result: Optional[LearnResult] = None

    iteration: int = Field(default=0, ge=0)
    max_iterations: int = Field(default=10, ge=1, le=100)

    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    last_phase_at: Optional[datetime] = None

    total_tokens_used: int = Field(default=0)
    total_processing_time_ms: float = Field(default=0.0)

    metadata: Dict[str, Any] = Field(default_factory=dict)
    audit_trail: List[Dict[str, Any]] = Field(default_factory=list)

    def record_phase_start(self, phase: LoopPhase) -> None:
        """Record the start of a phase in the audit trail."""
        self.current_phase = phase
        self.last_phase_at = datetime.now(timezone.utc)
        self.audit_trail.append({
            "event": "phase_start",
            "phase": phase.value,
            "iteration": self.iteration,
            "timestamp": self.last_phase_at.isoformat(),
        })

    def record_phase_end(self, phase: LoopPhase, result_summary: Dict[str, Any]) -> None:
        """Record the end of a phase in the audit trail."""
        self.audit_trail.append({
            "event": "phase_end",
            "phase": phase.value,
            "iteration": self.iteration,
            "result": result_summary,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def advance_iteration(self) -> None:
        """Advance to the next iteration."""
        self.iteration += 1
        self.current_phase = LoopPhase.PERCEIVE

    @property
    def elapsed_time_ms(self) -> float:
        """Calculate elapsed time in milliseconds."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds() * 1000
        return (datetime.now(timezone.utc) - self.started_at).total_seconds() * 1000

    @property
    def is_complete(self) -> bool:
        """Check if loop has completed all phases."""
        return self.status in (LoopStatus.COMPLETED, LoopStatus.FAILED, LoopStatus.KILLED)

    @property
    def can_continue(self) -> bool:
        """Check if loop can continue execution."""
        return (
            not self.is_complete and
            self.iteration < self.max_iterations and
            self.status != LoopStatus.PAUSED
        )


class LoopResult(BaseModel):
    """Final result of the agentic loop execution."""
    model_config = ConfigDict(frozen=False)

    loop_id: str
    persona_id: str
    session_id: str
    status: LoopStatus
    iterations_completed: int

    final_output: Optional[str] = None
    outputs: Dict[str, Any] = Field(default_factory=dict)

    perceive_summary: Optional[str] = None
    think_summary: Optional[str] = None
    act_summary: Optional[str] = None
    learn_summary: Optional[str] = None

    total_tokens_used: int = Field(default=0)
    total_processing_time_ms: float = Field(default=0.0)
    experience_gained: int = Field(default=0)

    errors: List[str] = Field(default_factory=list)
    audit_trail: List[Dict[str, Any]] = Field(default_factory=list)

    started_at: datetime
    completed_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status == LoopStatus.COMPLETED

    @property
    def duration_seconds(self) -> float:
        return (self.completed_at - self.started_at).total_seconds()


# ============================================================================
# Memory Gateway Interface
# ============================================================================

class MemoryGateway(ABC):
    """Abstract interface for memory operations in the agentic loop."""

    @abstractmethod
    async def search(
        self,
        query: str,
        persona_id: str,
        limit: int = 5,
        min_relevance: float = 0.5,
    ) -> List[MemoryReference]:
        """Search for relevant memories."""
        pass

    @abstractmethod
    async def store(
        self,
        content: str,
        persona_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        importance: float = 0.5,
    ) -> str:
        """Store a new memory and return its ID."""
        pass

    @abstractmethod
    async def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific memory by ID."""
        pass

    @abstractmethod
    async def update(
        self,
        memory_id: str,
        updates: Dict[str, Any],
    ) -> bool:
        """Update an existing memory."""
        pass

    @abstractmethod
    async def delete(self, memory_id: str) -> bool:
        """Delete a memory."""
        pass


class InMemoryGateway(MemoryGateway):
    """Simple in-memory implementation of MemoryGateway for testing."""

    def __init__(self):
        self._memories: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def search(
        self,
        query: str,
        persona_id: str,
        limit: int = 5,
        min_relevance: float = 0.5,
    ) -> List[MemoryReference]:
        """Simple keyword-based search."""
        results = []
        query_lower = query.lower()

        async with self._lock:
            for mem_id, mem in self._memories.items():
                if mem.get("persona_id") != persona_id:
                    continue
                content = mem.get("content", "")
                # Simple relevance scoring based on keyword overlap
                overlap = sum(1 for w in query_lower.split() if w in content.lower())
                relevance = min(overlap / max(len(query_lower.split()), 1), 1.0)

                if relevance >= min_relevance:
                    results.append(MemoryReference(
                        memory_id=mem_id,
                        relevance_score=relevance,
                        content_preview=content[:200],
                        source=mem.get("source", "unknown"),
                    ))

        results.sort(key=lambda x: x.relevance_score, reverse=True)
        return results[:limit]

    async def store(
        self,
        content: str,
        persona_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        importance: float = 0.5,
    ) -> str:
        """Store a memory."""
        memory_id = str(uuid4())
        async with self._lock:
            self._memories[memory_id] = {
                "id": memory_id,
                "content": content,
                "persona_id": persona_id,
                "metadata": metadata or {},
                "importance": importance,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        return memory_id

    async def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Get a memory by ID."""
        async with self._lock:
            return self._memories.get(memory_id)

    async def update(self, memory_id: str, updates: Dict[str, Any]) -> bool:
        """Update a memory."""
        async with self._lock:
            if memory_id not in self._memories:
                return False
            self._memories[memory_id].update(updates)
            return True

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory."""
        async with self._lock:
            if memory_id in self._memories:
                del self._memories[memory_id]
                return True
            return False


# ============================================================================
# Persona Model
# ============================================================================

class PersonaTraits(BaseModel):
    """Persona trait configuration."""
    model_config = ConfigDict(frozen=False)

    helpfulness: float = Field(default=0.8, ge=0.0, le=1.0)
    creativity: float = Field(default=0.7, ge=0.0, le=1.0)
    precision: float = Field(default=0.8, ge=0.0, le=1.0)
    patience: float = Field(default=0.7, ge=0.0, le=1.0)
    curiosity: float = Field(default=0.6, ge=0.0, le=1.0)
    caution: float = Field(default=0.5, ge=0.0, le=1.0)


class EthicsConstraint(BaseModel):
    """Ethics constraint definition."""
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    description: str = ""
    severity: str = "medium"  # low, medium, high, critical
    enabled: bool = True


class Persona(BaseModel):
    """Persona definition for the agentic loop."""
    model_config = ConfigDict(frozen=False, arbitrary_types_allowed=True)

    id: str
    name: str
    description: str = ""
    traits: PersonaTraits = Field(default_factory=PersonaTraits)
    ethics_constraints: List[EthicsConstraint] = Field(default_factory=list)
    capabilities: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def get_trait(self, name: str) -> float:
        """Get a trait value by name."""
        return getattr(self.traits, name, 0.5)

    def adjust_trait(self, name: str, delta: float) -> None:
        """Adjust a trait value."""
        current = self.get_trait(name)
        new_value = max(0.0, min(1.0, current + delta))
        if hasattr(self.traits, name):
            setattr(self.traits, name, new_value)
        self.updated_at = datetime.now(timezone.utc)


# ============================================================================
# Sandbox Executor Interface
# ============================================================================

class SandboxExecutor(ABC):
    """Abstract interface for sandboxed action execution."""

    @abstractmethod
    async def execute(
        self,
        action: PlannedAction,
        context: LoopContext,
    ) -> ActionResult:
        """Execute an action in the sandbox."""
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if sandbox is available."""
        pass


class DefaultSandboxExecutor(SandboxExecutor):
    """Default sandbox executor for basic actions."""

    async def execute(self, action: PlannedAction, context: LoopContext) -> ActionResult:
        """Execute an action with basic handling."""
        import time
        start = time.monotonic()

        try:
            # Basic action execution based on type
            if action.action_type == ActionType.RESPONSE:
                output = action.parameters.get("content", "")
            elif action.action_type == ActionType.MEMORY_STORE:
                output = f"Memory stored: {action.description}"
            else:
                output = f"Action executed: {action.description}"

            execution_time = (time.monotonic() - start) * 1000

            return ActionResult(
                action_id=action.action_id,
                success=True,
                output=output,
                execution_time_ms=execution_time,
            )
        except Exception as e:
            execution_time = (time.monotonic() - start) * 1000
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error=str(e),
                execution_time_ms=execution_time,
            )

    async def is_available(self) -> bool:
        return True


# ============================================================================
# Agentic Loop Engine
# ============================================================================

class AgenticLoop:
    """
    Main Agentic Loop Engine implementing PERCEIVE → THINK → ACT → LEARN.

    This is the core cognitive architecture that drives autonomous agent behavior.
    """

    def __init__(
        self,
        persona: Persona,
        llm_gateway: "LLMGateway",
        memory_gateway: Optional[MemoryGateway] = None,
        kill_switch: Optional["KillSwitchController"] = None,
        sandbox: Optional[SandboxExecutor] = None,
        max_iterations: int = 10,
        ethics_checker: Optional[Callable[[Dict[str, Any]], List[str]]] = None,
    ):
        self.persona = persona
        self.llm_gateway = llm_gateway
        self.memory_gateway = memory_gateway or InMemoryGateway()
        self.kill_switch = kill_switch
        self.sandbox = sandbox or DefaultSandboxExecutor()
        self.max_iterations = max_iterations
        self.ethics_checker = ethics_checker

        self._context: Optional[LoopContext] = None
        self._running = False

    async def run(
        self,
        input_data: Dict[str, Any],
        session_id: Optional[str] = None,
    ) -> LoopResult:
        """
        Execute the agentic loop with the given input.

        Args:
            input_data: Input data for the loop
            session_id: Optional session ID for continuity

        Returns:
            LoopResult with complete execution details
        """
        # Initialize context
        self._context = LoopContext(
            persona_id=self.persona.id,
            session_id=session_id or str(uuid4()),
            input_data=input_data,
            max_iterations=self.max_iterations,
            status=LoopStatus.RUNNING,
        )

        # Register with kill-switch if available
        if self.kill_switch:
            await self.kill_switch.register_persona(
                self.persona.id,
                initial_state={"loop_id": self._context.loop_id},
            )

        self._running = True

        try:
            # Main loop execution
            while self._context.can_continue:
                # Check kill-switch health before each iteration
                if self.kill_switch:
                    should_kill = await self._check_kill_switch()
                    if should_kill:
                        break

                # Execute all four phases
                await self._execute_iteration()

                # Check if we should continue
                if self._should_terminate():
                    break

                self._context.advance_iteration()

            # Finalize result
            self._context.status = LoopStatus.COMPLETED
            self._context.completed_at = datetime.now(timezone.utc)

        except Exception as e:
            logger.error(f"Loop execution failed: {e}\n{traceback.format_exc()}")
            self._context.status = LoopStatus.FAILED
            self._context.completed_at = datetime.now(timezone.utc)
            self._context.metadata["error"] = str(e)

        finally:
            self._running = False

        return self._build_result()

    async def _execute_iteration(self) -> None:
        """Execute a single iteration of all four phases."""
        # PERCEIVE
        self._context.record_phase_start(LoopPhase.PERCEIVE)
        self._context.perceived_data = await self.perceive(self._context)
        self._context.record_phase_end(
            LoopPhase.PERCEIVE,
            {"observation_count": self._context.perceived_data.observation_count},
        )
        self._context.total_processing_time_ms += self._context.perceived_data.processing_time_ms

        # THINK
        self._context.record_phase_start(LoopPhase.THINK)
        self._context.thought_result = await self.think(self._context)
        self._context.record_phase_end(
            LoopPhase.THINK,
            {"action_count": self._context.thought_result.action_count},
        )
        self._context.total_processing_time_ms += self._context.thought_result.processing_time_ms
        self._context.total_tokens_used += self._context.thought_result.llm_tokens_used

        # Check for ethics violations
        if self._context.thought_result.has_ethics_violations:
            logger.warning(f"Ethics violations detected: {self._context.thought_result.ethics_violations}")
            # Store violation in metadata
            self._context.metadata.setdefault("ethics_violations", []).extend(
                self._context.thought_result.ethics_violations
            )

        # ACT
        self._context.record_phase_start(LoopPhase.ACT)
        self._context.action_result = await self.act(self._context)
        self._context.record_phase_end(
            LoopPhase.ACT,
            {"success": self._context.action_result.success},
        )
        self._context.total_processing_time_ms += self._context.action_result.total_execution_time_ms

        # Check if killed during act phase
        if self._context.action_result.killed:
            self._context.status = LoopStatus.KILLED
            return

        # LEARN
        self._context.record_phase_start(LoopPhase.LEARN)
        self._context.learning_result = await self.learn(self._context)
        self._context.record_phase_end(
            LoopPhase.LEARN,
            {"experience_gained": self._context.learning_result.experience_gained},
        )
        self._context.total_processing_time_ms += self._context.learning_result.processing_time_ms

    async def perceive(self, context: LoopContext) -> PerceiveResult:
        """
        PERCEIVE phase: Gather and process input observations.

        - Input parsing and validation
        - Memory retrieval (semantic search)
        - Context building
        - Observation extraction
        """
        import time
        start = time.monotonic()

        observations: List[Observation] = []
        relevant_memories: List[MemoryReference] = []

        # 1. Parse user input
        user_input = context.input_data.get("user_input", "")
        if user_input:
            observations.append(Observation(
                observation_type=ObservationType.USER_INPUT,
                content=str(user_input),
                source="user",
                confidence=1.0,
            ))

        # 2. Parse system events
        system_events = context.input_data.get("system_events", [])
        for event in system_events:
            observations.append(Observation(
                observation_type=ObservationType.SYSTEM_EVENT,
                content=str(event),
                source="system",
                confidence=1.0,
            ))

        # 3. Retrieve relevant memories
        if user_input and self.memory_gateway:
            try:
                relevant_memories = await self.memory_gateway.search(
                    query=str(user_input),
                    persona_id=self.persona.id,
                    limit=5,
                    min_relevance=0.3,
                )

                for mem in relevant_memories:
                    observations.append(Observation(
                        observation_type=ObservationType.MEMORY_RECALL,
                        content=mem.content_preview,
                        source="memory",
                        confidence=mem.relevance_score,
                        metadata={"memory_id": mem.memory_id},
                    ))
            except Exception as e:
                logger.warning(f"Memory retrieval failed: {e}")

        # 4. Build context summary
        context_parts = []
        if user_input:
            context_parts.append(f"User input: {user_input[:200]}")
        if relevant_memories:
            context_parts.append(f"Retrieved {len(relevant_memories)} relevant memories")
        if system_events:
            context_parts.append(f"{len(system_events)} system events")

        context_summary = " | ".join(context_parts) if context_parts else "No input observed"

        # Calculate confidence based on observations
        confidence = 1.0 if observations else 0.0
        if relevant_memories:
            avg_relevance = sum(m.relevance_score for m in relevant_memories) / len(relevant_memories)
            confidence = (confidence + avg_relevance) / 2

        processing_time = (time.monotonic() - start) * 1000

        return PerceiveResult(
            observations=observations,
            context_summary=context_summary,
            relevant_memories=relevant_memories,
            confidence=confidence,
            processing_time_ms=processing_time,
        )

    async def think(self, context: LoopContext) -> ThinkResult:
        """
        THINK phase: Reason and plan actions.

        - LLM-based reasoning
        - Decision making
        - Action planning
        - Ethics check (pre-action)
        """
        import time
        start = time.monotonic()

        decisions: List[Decision] = []
        planned_actions: List[PlannedAction] = []
        ethics_violations: List[str] = []
        llm_tokens = 0
        reasoning = ""

        # Build prompt from perceived data
        if context.perceived_data:
            prompt = self._build_thinking_prompt(context)

            try:
                # Call LLM for reasoning
                response = await self.llm_gateway.generate(
                    prompt=prompt,
                    model=None,  # Use default
                    temperature=0.7,
                    max_tokens=2000,
                )
                reasoning = response.content
                llm_tokens = response.tokens_used

                # Parse LLM response into decisions and actions
                parsed = self._parse_llm_response(response.content)
                decisions = parsed.get("decisions", [])
                planned_actions = parsed.get("actions", [])

            except Exception as e:
                logger.error(f"LLM reasoning failed: {e}")
                reasoning = f"LLM reasoning failed: {e}"
                # Create fallback action
                planned_actions = [PlannedAction(
                    action_type=ActionType.RESPONSE,
                    description="Provide response based on observations",
                    parameters={"content": "I'm processing your request."},
                )]

        # Run ethics check on planned actions
        for action in planned_actions:
            violations = await self._check_ethics(action, context)
            if violations:
                ethics_violations.extend(violations)
                # Modify or remove violating actions
                action.metadata["ethics_violations"] = violations

        processing_time = (time.monotonic() - start) * 1000

        return ThinkResult(
            reasoning=reasoning,
            decisions=decisions,
            planned_actions=planned_actions,
            confidence=0.8 if planned_actions else 0.3,
            ethics_violations=ethics_violations,
            processing_time_ms=processing_time,
            llm_tokens_used=llm_tokens,
        )

    async def act(self, context: LoopContext) -> ActResult:
        """
        ACT phase: Execute planned actions.

        - Tool/Action execution via sandbox
        - Output generation
        - Error handling
        - Kill-switch monitoring
        """
        import time
        start = time.monotonic()

        actions_taken: List[ActionResult] = []
        outputs: Dict[str, Any] = {}
        errors: List[str] = []
        killed = False
        kill_reason = None

        if not context.thought_result or not context.thought_result.planned_actions:
            return ActResult(
                actions_taken=[],
                outputs={},
                success=True,
                errors=["No actions to execute"],
                total_execution_time_ms=(time.monotonic() - start) * 1000,
            )

        # Execute each planned action
        for action in context.thought_result.planned_actions:
            # Check kill-switch before each action
            if self.kill_switch:
                ks = self.kill_switch.get_active_kill_switch(self.persona.id)
                if ks:
                    killed = True
                    kill_reason = ks.reason
                    break

            # Check sandbox availability
            if not await self.sandbox.is_available():
                errors.append(f"Sandbox unavailable for action {action.action_id}")
                continue

            # Execute action
            try:
                result = await self.sandbox.execute(action, context)
                actions_taken.append(result)

                if result.success:
                    outputs[action.action_id] = result.output
                else:
                    errors.append(f"Action {action.action_id} failed: {result.error}")

            except Exception as e:
                error_msg = f"Action {action.action_id} exception: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
                actions_taken.append(ActionResult(
                    action_id=action.action_id,
                    success=False,
                    error=str(e),
                ))

        processing_time = (time.monotonic() - start) * 1000

        return ActResult(
            actions_taken=actions_taken,
            outputs=outputs,
            success=len(errors) == 0 and not killed,
            errors=errors,
            total_execution_time_ms=processing_time,
            killed=killed,
            kill_reason=kill_reason,
        )

    async def learn(self, context: LoopContext) -> LearnResult:
        """
        LEARN phase: Extract insights and update persona.

        - Experience extraction
        - Memory storage
        - XP calculation
        - Trait adjustments
        """
        import time
        start = time.monotonic()

        insights: List[Insight] = []
        memories_created: List[str] = []
        trait_adjustments: Dict[str, float] = {}
        experience_gained = 0

        # 1. Extract insights from the iteration
        if context.action_result:
            # Success-based learning
            if context.action_result.success:
                insights.append(Insight(
                    insight_type=InsightType.SUCCESS_PATTERN,
                    description="Successfully completed action sequence",
                    evidence=[a.output for a in context.action_result.actions_taken if a.output],
                    applicability=0.8,
                ))
                experience_gained += 10
            else:
                # Learn from failures
                for error in context.action_result.errors:
                    insights.append(Insight(
                        insight_type=InsightType.FAILURE_PATTERN,
                        description=f"Encountered error: {error}",
                        evidence=[error],
                        applicability=0.6,
                    ))
                experience_gained += 2  # Still learn from failures

        # 2. Store significant experiences as memories
        if context.perceived_data and context.perceived_data.has_observations:
            user_input = context.input_data.get("user_input", "")
            if user_input and context.action_result:
                try:
                    memory_content = f"User: {user_input[:100]} | Response: {str(context.action_result.outputs)[:200]}"
                    memory_id = await self.memory_gateway.store(
                        content=memory_content,
                        persona_id=self.persona.id,
                        importance=0.6 if context.action_result.success else 0.4,
                        metadata={
                            "loop_id": context.loop_id,
                            "iteration": context.iteration,
                            "success": context.action_result.success,
                        },
                    )
                    memories_created.append(memory_id)
                except Exception as e:
                    logger.warning(f"Failed to store memory: {e}")

        # 3. Adjust traits based on experience
        if context.thought_result and context.thought_result.has_ethics_violations:
            # Increase caution after ethics violations
            trait_adjustments["caution"] = 0.05
            self.persona.adjust_trait("caution", 0.05)

        if context.action_result and context.action_result.success_rate > 0.8:
            # Increase helpfulness after successful interactions
            trait_adjustments["helpfulness"] = 0.02
            self.persona.adjust_trait("helpfulness", 0.02)

        # 4. Store insights as memories
        for insight in insights:
            try:
                memory_id = await self.memory_gateway.store(
                    content=f"Insight: {insight.description}",
                    persona_id=self.persona.id,
                    importance=insight.applicability,
                    metadata={
                        "type": "insight",
                        "insight_type": insight.insight_type.value,
                    },
                )
                memories_created.append(memory_id)
            except Exception as e:
                logger.warning(f"Failed to store insight: {e}")

        processing_time = (time.monotonic() - start) * 1000

        return LearnResult(
            insights=insights,
            experience_gained=experience_gained,
            memories_created=memories_created,
            trait_adjustments=trait_adjustments,
            feedback_summary=f"Gained {experience_gained} XP from {len(insights)} insights",
            processing_time_ms=processing_time,
        )

    async def _check_kill_switch(self) -> bool:
        """Check if kill-switch has been triggered."""
        if not self.kill_switch:
            return False

        ks = self.kill_switch.get_active_kill_switch(self.persona.id)
        if ks:
            logger.warning(f"Kill-switch triggered: {ks.reason}")
            return True
        return False

    async def _check_ethics(self, action: PlannedAction, context: LoopContext) -> List[str]:
        """Check action against ethics constraints."""
        violations = []

        # Check built-in ethics constraints
        for constraint in self.persona.ethics_constraints:
            if not constraint.enabled:
                continue

            # Basic content checks
            action_text = f"{action.description} {action.parameters}".lower()

            # Check for harmful content
            if constraint.name == "no_harm":
                harmful_patterns = ["harm", "damage", "destroy", "attack"]
                if any(p in action_text for p in harmful_patterns):
                    violations.append(f"Potential harm detected: {constraint.name}")

            # Check for privacy violations
            elif constraint.name == "respect_privacy":
                privacy_patterns = ["password", "secret", "private", "credential"]
                if any(p in action_text for p in privacy_patterns):
                    violations.append(f"Privacy concern: {constraint.name}")

        # Use custom ethics checker if provided
        if self.ethics_checker:
            custom_violations = self.ethics_checker({
                "action": action.model_dump(),
                "context": context.model_dump(),
            })
            violations.extend(custom_violations)

        return violations

    def _build_thinking_prompt(self, context: LoopContext) -> str:
        """Build prompt for LLM reasoning."""
        parts = [
            f"You are {self.persona.name}, {self.persona.description}",
            f"\nTraits: helpfulness={self.persona.traits.helpfulness:.1f}, "
            f"creativity={self.persona.traits.creativity:.1f}, "
            f"precision={self.persona.traits.precision:.1f}",
        ]

        if context.perceived_data:
            parts.append(f"\nObservations: {context.perceived_data.context_summary}")
            for obs in context.perceived_data.observations[:3]:
                parts.append(f"- [{obs.observation_type.value}] {obs.content[:100]}")

        if context.perceived_data and context.perceived_data.relevant_memories:
            parts.append("\nRelevant memories:")
            for mem in context.perceived_data.relevant_memories[:3]:
                parts.append(f"- {mem.content_preview[:100]}")

        parts.append("\nBased on the above, decide what actions to take.")
        parts.append("Respond with your reasoning and planned actions.")

        return "\n".join(parts)

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response into decisions and actions."""
        decisions = []
        actions = []

        # Simple parsing: create a response action with the LLM output
        actions.append(PlannedAction(
            action_type=ActionType.RESPONSE,
            description="Generate response to user",
            parameters={"content": response},
            priority=5,
        ))

        # Create a decision record
        decisions.append(Decision(
            decision_type=DecisionType.RESPONSE_GENERATION,
            reasoning=response[:500],
            selected_option="provide_response",
            confidence=0.8,
        ))

        return {"decisions": decisions, "actions": actions}

    def _should_terminate(self) -> bool:
        """Check if loop should terminate after current iteration."""
        if not self._context:
            return True

        # Check if we have a clear completion signal
        if self._context.action_result:
            # Terminate if we've successfully responded
            if self._context.action_result.success:
                outputs = self._context.action_result.outputs
                if outputs and any("response" in str(k).lower() for k in outputs.keys()):
                    return True

        # Terminate if too many iterations
        if self._context.iteration >= self._context.max_iterations - 1:
            return True

        return False

    def _build_result(self) -> LoopResult:
        """Build final result from context."""
        if not self._context:
            raise RuntimeError("No context available to build result")

        # Extract summaries
        perceive_summary = None
        think_summary = None
        act_summary = None
        learn_summary = None

        if self._context.perceived_data:
            perceive_summary = self._context.perceived_data.context_summary

        if self._context.thought_result:
            think_summary = self._context.thought_result.reasoning[:500]

        if self._context.action_result:
            act_summary = f"Executed {len(self._context.action_result.actions_taken)} actions"

        if self._context.learning_result:
            learn_summary = self._context.learning_result.feedback_summary

        # Extract final output
        final_output = None
        if self._context.action_result and self._context.action_result.outputs:
            for key, value in self._context.action_result.outputs.items():
                if value:
                    final_output = str(value)
                    break

        # Get experience gained
        experience_gained = 0
        if self._context.learning_result:
            experience_gained = self._context.learning_result.experience_gained

        return LoopResult(
            loop_id=self._context.loop_id,
            persona_id=self._context.persona_id,
            session_id=self._context.session_id,
            status=self._context.status,
            iterations_completed=self._context.iteration + 1,
            final_output=final_output,
            outputs=self._context.action_result.outputs if self._context.action_result else {},
            perceive_summary=perceive_summary,
            think_summary=think_summary,
            act_summary=act_summary,
            learn_summary=learn_summary,
            total_tokens_used=self._context.total_tokens_used,
            total_processing_time_ms=self._context.total_processing_time_ms,
            experience_gained=experience_gained,
            errors=self._context.metadata.get("errors", []),
            audit_trail=self._context.audit_trail,
            started_at=self._context.started_at,
            completed_at=self._context.completed_at or datetime.now(timezone.utc),
            metadata=self._context.metadata,
        )

    async def pause(self) -> bool:
        """Pause the running loop."""
        if self._context and self._running:
            self._context.status = LoopStatus.PAUSED
            return True
        return False

    async def resume(self) -> bool:
        """Resume a paused loop."""
        if self._context and self._context.status == LoopStatus.PAUSED:
            self._context.status = LoopStatus.RUNNING
            return True
        return False

    async def stop(self, reason: str = "User requested") -> bool:
        """Stop the running loop."""
        if self._context:
            self._context.status = LoopStatus.KILLED
            self._context.metadata["stop_reason"] = reason
            self._running = False
            return True
        return False


# ============================================================================
# Factory Functions
# ============================================================================

def create_agentic_loop(
    persona_id: str,
    persona_name: str = "Assistant",
    llm_gateway: Optional["LLMGateway"] = None,
    memory_gateway: Optional[MemoryGateway] = None,
    kill_switch: Optional["KillSwitchController"] = None,
    max_iterations: int = 10,
) -> AgenticLoop:
    """
    Factory function to create an AgenticLoop with defaults.

    Args:
        persona_id: Unique persona identifier
        persona_name: Display name for the persona
        llm_gateway: LLM gateway instance (required for production)
        memory_gateway: Memory gateway instance (optional, uses in-memory default)
        kill_switch: Kill-switch controller (optional)
        max_iterations: Maximum loop iterations

    Returns:
        Configured AgenticLoop instance
    """
    persona = Persona(
        id=persona_id,
        name=persona_name,
        description=f"AI assistant {persona_name}",
        traits=PersonaTraits(),
        ethics_constraints=[
            EthicsConstraint(id="default-no-harm", name="no_harm", severity="critical"),
            EthicsConstraint(id="default-truthful", name="be_truthful", severity="high"),
        ],
    )

    if llm_gateway is None:
        raise ValueError("llm_gateway is required for AgenticLoop")

    return AgenticLoop(
        persona=persona,
        llm_gateway=llm_gateway,
        memory_gateway=memory_gateway,
        kill_switch=kill_switch,
        max_iterations=max_iterations,
    )
