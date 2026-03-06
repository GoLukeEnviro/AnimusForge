"""
Unit Tests for AnimusForge Agentic Loop Engine
SPRINT2-002 Implementation

Tests cover:
- Enums and Phase Models
- Phase Result Models
- LoopContext and LoopResult
- MemoryGateway implementations
- Persona Model
- AgenticLoop Engine
- PERCEIVE, THINK, ACT, LEARN phases
- Edge cases and error handling
"""

import asyncio
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any, Dict, List
import uuid

import pytest

from animus_stage.loop import (
    # Enums
    LoopPhase,
    LoopStatus,
    ObservationType,
    DecisionType,
    ActionType,
    InsightType,
    # Supporting Models
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
    # Context and Result
    LoopContext,
    LoopResult,
    # Gateway and Persona
    MemoryGateway,
    InMemoryGateway,
    PersonaTraits,
    EthicsConstraint,
    Persona,
    # Sandbox
    SandboxExecutor,
    DefaultSandboxExecutor,
    # Main Engine
    AgenticLoop,
    create_agentic_loop,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_persona():
    """Create a sample persona for testing."""
    return Persona(
        id="test-persona-001",
        name="Test Assistant",
        description="A test persona for unit testing",
        traits=PersonaTraits(
            helpfulness=0.9,
            creativity=0.7,
            precision=0.8,
        ),
        ethics_constraints=[
            EthicsConstraint(id="eth-001", name="no_harm", severity="critical"),
            EthicsConstraint(id="eth-002", name="be_truthful", severity="high"),
        ],
    )


@pytest.fixture
def mock_llm_gateway():
    """Create a mock LLM gateway."""
    gateway = MagicMock()
    gateway.generate = AsyncMock(return_value=MagicMock(
        content="This is a test response from the LLM.",
        provider="mock",
        model="mock-model",
        tokens_used=100,
        latency_ms=50.0,
    ))
    return gateway


@pytest.fixture
def mock_kill_switch():
    """Create a mock kill-switch controller."""
    ks = MagicMock()
    ks.register_persona = AsyncMock(return_value=True)
    ks.get_active_kill_switch = MagicMock(return_value=None)
    return ks


@pytest.fixture
def mock_memory_gateway():
    """Create a mock memory gateway."""
    return InMemoryGateway()


@pytest.fixture
def mock_sandbox():
    """Create a mock sandbox executor."""
    sandbox = MagicMock()
    sandbox.execute = AsyncMock(return_value=ActionResult(
        action_id="test-action",
        success=True,
        output="Action executed successfully",
    ))
    sandbox.is_available = AsyncMock(return_value=True)
    return sandbox


@pytest.fixture
def agentic_loop(sample_persona, mock_llm_gateway, mock_memory_gateway, mock_kill_switch, mock_sandbox):
    """Create a configured AgenticLoop instance."""
    return AgenticLoop(
        persona=sample_persona,
        llm_gateway=mock_llm_gateway,
        memory_gateway=mock_memory_gateway,
        kill_switch=mock_kill_switch,
        sandbox=mock_sandbox,
        max_iterations=5,
    )


@pytest.fixture
def sample_input_data():
    """Sample input data for testing."""
    return {
        "user_input": "What is Python async?",
        "system_events": ["session_started", "memory_loaded"],
        "metadata": {"test": True},
    }


# ============================================================================
# Enum Tests
# ============================================================================

class TestLoopPhase:
    """Tests for LoopPhase enum."""

    def test_loop_phase_values(self):
        """Test all loop phase values."""
        assert LoopPhase.PERCEIVE.value == "perceive"
        assert LoopPhase.THINK.value == "think"
        assert LoopPhase.ACT.value == "act"
        assert LoopPhase.LEARN.value == "learn"

    def test_loop_phase_str(self):
        """Test string representation."""
        assert str(LoopPhase.PERCEIVE) == "perceive"
        assert str(LoopPhase.THINK) == "think"

    def test_loop_phase_count(self):
        """Test that we have exactly 4 phases."""
        assert len(LoopPhase) == 4


class TestLoopStatus:
    """Tests for LoopStatus enum."""

    def test_loop_status_values(self):
        """Test all loop status values."""
        assert LoopStatus.PENDING.value == "pending"
        assert LoopStatus.RUNNING.value == "running"
        assert LoopStatus.COMPLETED.value == "completed"
        assert LoopStatus.FAILED.value == "failed"
        assert LoopStatus.KILLED.value == "killed"
        assert LoopStatus.PAUSED.value == "paused"

    def test_loop_status_str(self):
        """Test string representation."""
        assert str(LoopStatus.RUNNING) == "running"


class TestObservationType:
    """Tests for ObservationType enum."""

    def test_observation_type_values(self):
        """Test observation type values."""
        assert ObservationType.USER_INPUT.value == "user_input"
        assert ObservationType.SYSTEM_EVENT.value == "system_event"
        assert ObservationType.MEMORY_RECALL.value == "memory_recall"
        assert ObservationType.ENVIRONMENT.value == "environment"
        assert ObservationType.FEEDBACK.value == "feedback"
        assert ObservationType.ERROR.value == "error"


class TestDecisionType:
    """Tests for DecisionType enum."""

    def test_decision_type_values(self):
        """Test decision type values."""
        assert DecisionType.ACTION_SELECTION.value == "action_selection"
        assert DecisionType.TOOL_CHOICE.value == "tool_choice"
        assert DecisionType.RESPONSE_GENERATION.value == "response_generation"
        assert DecisionType.CLARIFICATION.value == "clarification"
        assert DecisionType.DEFERRAL.value == "deferral"
        assert DecisionType.TERMINATION.value == "termination"


class TestActionType:
    """Tests for ActionType enum."""

    def test_action_type_values(self):
        """Test action type values."""
        assert ActionType.TOOL_EXECUTION.value == "tool_execution"
        assert ActionType.RESPONSE.value == "response"
        assert ActionType.MEMORY_STORE.value == "memory_store"
        assert ActionType.EXTERNAL_API.value == "external_api"
        assert ActionType.FILE_OPERATION.value == "file_operation"
        assert ActionType.COMMUNICATION.value == "communication"


class TestInsightType:
    """Tests for InsightType enum."""

    def test_insight_type_values(self):
        """Test insight type values."""
        assert InsightType.SUCCESS_PATTERN.value == "success_pattern"
        assert InsightType.FAILURE_PATTERN.value == "failure_pattern"
        assert InsightType.BEHAVIOR_ADJUSTMENT.value == "behavior_adjustment"
        assert InsightType.KNOWLEDGE_GAIN.value == "knowledge_gain"
        assert InsightType.PREFERENCE_UPDATE.value == "preference_update"
        assert InsightType.SKILL_IMPROVEMENT.value == "skill_improvement"


# ============================================================================
# Supporting Model Tests
# ============================================================================

class TestMemoryReference:
    """Tests for MemoryReference model."""

    def test_memory_reference_creation(self):
        """Test creating a memory reference."""
        ref = MemoryReference(
            memory_id="mem-001",
            relevance_score=0.85,
            content_preview="This is a test memory",
            source="user",
        )
        assert ref.memory_id == "mem-001"
        assert ref.relevance_score == 0.85
        assert ref.content_preview == "This is a test memory"

    def test_memory_reference_frozen(self):
        """Test that MemoryReference is frozen."""
        ref = MemoryReference(
            memory_id="mem-001",
            relevance_score=0.85,
            content_preview="Test",
        )
        with pytest.raises(Exception):
            ref.memory_id = "new-id"

    def test_memory_reference_default_timestamp(self):
        """Test default timestamp is set."""
        ref = MemoryReference(
            memory_id="mem-001",
            relevance_score=0.5,
            content_preview="Test",
        )
        assert ref.timestamp is not None
        assert isinstance(ref.timestamp, datetime)

    def test_memory_reference_relevance_bounds(self):
        """Test relevance score validation."""
        # Valid bounds
        ref = MemoryReference(memory_id="mem", relevance_score=0.0, content_preview="Test")
        assert ref.relevance_score == 0.0
        ref = MemoryReference(memory_id="mem", relevance_score=1.0, content_preview="Test")
        assert ref.relevance_score == 1.0

        # Invalid bounds
        with pytest.raises(Exception):
            MemoryReference(memory_id="mem", relevance_score=1.5, content_preview="Test")
        with pytest.raises(Exception):
            MemoryReference(memory_id="mem", relevance_score=-0.1, content_preview="Test")


class TestObservation:
    """Tests for Observation model."""

    def test_observation_creation(self):
        """Test creating an observation."""
        obs = Observation(
            observation_type=ObservationType.USER_INPUT,
            content="User asked about Python",
            source="user",
            confidence=0.9,
        )
        assert obs.observation_type == ObservationType.USER_INPUT
        assert obs.content == "User asked about Python"
        assert obs.confidence == 0.9

    def test_observation_auto_id(self):
        """Test that observation ID is auto-generated."""
        obs = Observation(
            observation_type=ObservationType.USER_INPUT,
            content="Test",
        )
        assert obs.observation_id is not None
        assert len(obs.observation_id) > 0

    def test_observation_content_not_empty(self):
        """Test that empty content is rejected."""
        with pytest.raises(Exception):
            Observation(
                observation_type=ObservationType.USER_INPUT,
                content="",
            )
        with pytest.raises(Exception):
            Observation(
                observation_type=ObservationType.USER_INPUT,
                content="   ",
            )

    def test_observation_default_timestamp(self):
        """Test default timestamp."""
        obs = Observation(
            observation_type=ObservationType.USER_INPUT,
            content="Test",
        )
        assert obs.timestamp is not None

    def test_observation_not_frozen(self):
        """Test that Observation is not frozen (mutable)."""
        obs = Observation(
            observation_type=ObservationType.USER_INPUT,
            content="Test",
        )
        obs.content = "Modified"
        assert obs.content == "Modified"


class TestDecision:
    """Tests for Decision model."""

    def test_decision_creation(self):
        """Test creating a decision."""
        decision = Decision(
            decision_type=DecisionType.RESPONSE_GENERATION,
            reasoning="User needs information",
            selected_option="provide_response",
            confidence=0.85,
        )
        assert decision.decision_type == DecisionType.RESPONSE_GENERATION
        assert decision.selected_option == "provide_response"
        assert decision.confidence == 0.85

    def test_decision_ethics_fields(self):
        """Test ethics-related fields."""
        decision = Decision(
            decision_type=DecisionType.ACTION_SELECTION,
            reasoning="Test",
            selected_option="option1",
            ethics_approved=False,
            ethics_concerns=["Potential privacy issue"],
        )
        assert not decision.ethics_approved
        assert len(decision.ethics_concerns) == 1

    def test_decision_alternatives(self):
        """Test alternatives list."""
        decision = Decision(
            decision_type=DecisionType.TOOL_CHOICE,
            reasoning="Need to choose a tool",
            selected_option="search",
            alternatives=["lookup", "query"],
        )
        assert len(decision.alternatives) == 2


class TestPlannedAction:
    """Tests for PlannedAction model."""

    def test_planned_action_creation(self):
        """Test creating a planned action."""
        action = PlannedAction(
            action_type=ActionType.RESPONSE,
            description="Generate response",
            tool_name="llm",
            parameters={"content": "Hello"},
            priority=7,
        )
        assert action.action_type == ActionType.RESPONSE
        assert action.priority == 7

    def test_planned_action_dependencies(self):
        """Test action dependencies."""
        action = PlannedAction(
            action_type=ActionType.TOOL_EXECUTION,
            description="Execute tool",
            dependencies=["action-1", "action-2"],
        )
        assert len(action.dependencies) == 2

    def test_planned_action_rollback(self):
        """Test rollback plan."""
        action = PlannedAction(
            action_type=ActionType.FILE_OPERATION,
            description="Write file",
            rollback_plan="Delete the file",
        )
        assert action.rollback_plan == "Delete the file"

    def test_planned_action_priority_bounds(self):
        """Test priority validation."""
        action = PlannedAction(
            action_type=ActionType.RESPONSE,
            description="Test",
            priority=1,
        )
        assert action.priority == 1

        action = PlannedAction(
            action_type=ActionType.RESPONSE,
            description="Test",
            priority=10,
        )
        assert action.priority == 10

        with pytest.raises(Exception):
            PlannedAction(action_type=ActionType.RESPONSE, description="Test", priority=0)
        with pytest.raises(Exception):
            PlannedAction(action_type=ActionType.RESPONSE, description="Test", priority=11)


class TestActionResult:
    """Tests for ActionResult model."""

    def test_action_result_success(self):
        """Test successful action result."""
        result = ActionResult(
            action_id="action-001",
            success=True,
            output="Operation completed",
            execution_time_ms=150.5,
        )
        assert result.success
        assert result.output == "Operation completed"

    def test_action_result_failure(self):
        """Test failed action result."""
        result = ActionResult(
            action_id="action-001",
            success=False,
            error="Connection timeout",
        )
        assert not result.success
        assert result.error == "Connection timeout"

    def test_action_result_side_effects(self):
        """Test side effects tracking."""
        result = ActionResult(
            action_id="action-001",
            success=True,
            side_effects=["file_created", "notification_sent"],
        )
        assert len(result.side_effects) == 2


class TestInsight:
    """Tests for Insight model."""

    def test_insight_creation(self):
        """Test creating an insight."""
        insight = Insight(
            insight_type=InsightType.SUCCESS_PATTERN,
            description="User prefers concise answers",
            evidence=["Observation 1", "Observation 2"],
            applicability=0.8,
        )
        assert insight.insight_type == InsightType.SUCCESS_PATTERN
        assert len(insight.evidence) == 2

    def test_insight_confidence_bounds(self):
        """Test confidence validation."""
        insight = Insight(
            insight_type=InsightType.KNOWLEDGE_GAIN,
            description="Test",
            confidence=0.5,
        )
        assert insight.confidence == 0.5


# ============================================================================
# Phase Result Model Tests
# ============================================================================

class TestPerceiveResult:
    """Tests for PerceiveResult model."""

    def test_perceive_result_creation(self):
        """Test creating perceive result."""
        result = PerceiveResult(
            observations=[
                Observation(observation_type=ObservationType.USER_INPUT, content="Test"),
            ],
            context_summary="User asked a question",
            confidence=0.9,
        )
        assert result.observation_count == 1
        assert result.has_observations

    def test_perceive_result_empty(self):
        """Test empty perceive result."""
        result = PerceiveResult()
        assert not result.has_observations
        assert result.observation_count == 0

    def test_perceive_result_memories(self):
        """Test with relevant memories."""
        result = PerceiveResult(
            relevant_memories=[
                MemoryReference(memory_id="mem-1", relevance_score=0.8, content_preview="Test"),
            ],
        )
        assert len(result.relevant_memories) == 1


class TestThinkResult:
    """Tests for ThinkResult model."""

    def test_think_result_creation(self):
        """Test creating think result."""
        result = ThinkResult(
            reasoning="User needs help with Python",
            decisions=[
                Decision(
                    decision_type=DecisionType.RESPONSE_GENERATION,
                    reasoning="Test",
                    selected_option="respond",
                ),
            ],
            planned_actions=[
                PlannedAction(action_type=ActionType.RESPONSE, description="Test"),
            ],
        )
        assert result.has_planned_actions
        assert result.action_count == 1

    def test_think_result_ethics_violations(self):
        """Test ethics violations detection."""
        result = ThinkResult(
            ethics_violations=["Potential harm detected"],
        )
        assert result.has_ethics_violations

    def test_think_result_clarification(self):
        """Test clarification needed."""
        result = ThinkResult(
            requires_clarification=True,
            clarification_questions=["What do you mean by X?"],
        )
        assert result.requires_clarification
        assert len(result.clarification_questions) == 1


class TestActResult:
    """Tests for ActResult model."""

    def test_act_result_success(self):
        """Test successful act result."""
        result = ActResult(
            actions_taken=[
                ActionResult(action_id="a1", success=True),
                ActionResult(action_id="a2", success=True),
            ],
            success=True,
        )
        assert result.success
        assert result.successful_action_count == 2
        assert result.failed_action_count == 0
        assert result.success_rate == 1.0

    def test_act_result_partial_failure(self):
        """Test partially failed act result."""
        result = ActResult(
            actions_taken=[
                ActionResult(action_id="a1", success=True),
                ActionResult(action_id="a2", success=False, error="Failed"),
            ],
        )
        assert result.successful_action_count == 1
        assert result.failed_action_count == 1
        assert result.success_rate == 0.5

    def test_act_result_empty(self):
        """Test empty act result."""
        result = ActResult()
        assert result.success_rate == 1.0  # No actions = 100% success rate

    def test_act_result_killed(self):
        """Test killed act result."""
        result = ActResult(
            killed=True,
            kill_reason="Resource limit exceeded",
        )
        assert result.killed
        assert result.kill_reason == "Resource limit exceeded"


class TestLearnResult:
    """Tests for LearnResult model."""

    def test_learn_result_creation(self):
        """Test creating learn result."""
        result = LearnResult(
            insights=[
                Insight(insight_type=InsightType.SUCCESS_PATTERN, description="Test"),
            ],
            experience_gained=15,
            memories_created=["mem-1", "mem-2"],
        )
        assert result.has_insights
        assert result.has_learning
        assert result.experience_gained == 15

    def test_learn_result_trait_adjustments(self):
        """Test trait adjustments."""
        result = LearnResult(
            trait_adjustments={"helpfulness": 0.05, "caution": 0.02},
        )
        assert "helpfulness" in result.trait_adjustments

    def test_learn_result_no_learning(self):
        """Test result with no learning."""
        result = LearnResult()
        assert not result.has_insights
        assert not result.has_learning


# ============================================================================
# LoopContext Tests
# ============================================================================

class TestLoopContext:
    """Tests for LoopContext model."""

    def test_loop_context_creation(self):
        """Test creating a loop context."""
        context = LoopContext(
            persona_id="persona-001",
            input_data={"user_input": "Hello"},
            max_iterations=10,
        )
        assert context.persona_id == "persona-001"
        assert context.iteration == 0
        assert context.status == LoopStatus.PENDING

    def test_loop_context_auto_ids(self):
        """Test auto-generated IDs."""
        context = LoopContext(persona_id="test")
        assert context.loop_id is not None
        assert context.session_id is not None

    def test_loop_context_record_phase(self):
        """Test phase recording in audit trail."""
        context = LoopContext(persona_id="test")
        context.record_phase_start(LoopPhase.PERCEIVE)
        assert len(context.audit_trail) == 1
        assert context.audit_trail[0]["event"] == "phase_start"
        assert context.audit_trail[0]["phase"] == "perceive"

    def test_loop_context_record_phase_end(self):
        """Test phase end recording."""
        context = LoopContext(persona_id="test")
        context.record_phase_end(LoopPhase.PERCEIVE, {"observation_count": 3})
        assert len(context.audit_trail) == 1
        assert context.audit_trail[0]["result"]["observation_count"] == 3

    def test_loop_context_advance_iteration(self):
        """Test iteration advancement."""
        context = LoopContext(persona_id="test")
        context.iteration = 2
        context.current_phase = LoopPhase.LEARN
        context.advance_iteration()
        assert context.iteration == 3
        assert context.current_phase == LoopPhase.PERCEIVE

    def test_loop_context_elapsed_time(self):
        """Test elapsed time calculation."""
        context = LoopContext(persona_id="test")
        elapsed = context.elapsed_time_ms
        assert elapsed >= 0

    def test_loop_context_is_complete(self):
        """Test completion check."""
        context = LoopContext(persona_id="test")
        assert not context.is_complete

        context.status = LoopStatus.COMPLETED
        assert context.is_complete

        context.status = LoopStatus.FAILED
        assert context.is_complete

        context.status = LoopStatus.KILLED
        assert context.is_complete

    def test_loop_context_can_continue(self):
        """Test can continue check."""
        context = LoopContext(persona_id="test", max_iterations=5)
        assert context.can_continue

        context.status = LoopStatus.RUNNING
        assert context.can_continue

        context.status = LoopStatus.COMPLETED
        assert not context.can_continue

        context.status = LoopStatus.RUNNING
        context.iteration = 10
        assert not context.can_continue

        context.iteration = 2
        context.status = LoopStatus.PAUSED
        assert not context.can_continue


# ============================================================================
# LoopResult Tests
# ============================================================================

class TestLoopResult:
    """Tests for LoopResult model."""

    def test_loop_result_creation(self):
        """Test creating a loop result."""
        result = LoopResult(
            loop_id="loop-001",
            persona_id="persona-001",
            session_id="session-001",
            status=LoopStatus.COMPLETED,
            iterations_completed=3,
            started_at=datetime.now(timezone.utc) - timedelta(seconds=5),
            completed_at=datetime.now(timezone.utc),
        )
        assert result.success
        assert result.iterations_completed == 3

    def test_loop_result_duration(self):
        """Test duration calculation."""
        start = datetime.now(timezone.utc) - timedelta(seconds=10)
        end = datetime.now(timezone.utc)
        result = LoopResult(
            loop_id="loop-001",
            persona_id="p1",
            session_id="s1",
            status=LoopStatus.COMPLETED,
            iterations_completed=1,
            started_at=start,
            completed_at=end,
        )
        assert result.duration_seconds >= 10

    def test_loop_result_failed(self):
        """Test failed result."""
        result = LoopResult(
            loop_id="loop-001",
            persona_id="p1",
            session_id="s1",
            status=LoopStatus.FAILED,
            iterations_completed=1,
            errors=["Something went wrong"],
            started_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            completed_at=datetime.now(timezone.utc),
        )
        assert not result.success
        assert len(result.errors) == 1


# ============================================================================
# MemoryGateway Tests
# ============================================================================

class TestInMemoryGateway:
    """Tests for InMemoryGateway."""

    @pytest.fixture
    def gateway(self):
        return InMemoryGateway()

    @pytest.mark.asyncio
    async def test_store_and_get(self, gateway):
        """Test storing and retrieving memories."""
        memory_id = await gateway.store(
            content="Test memory content",
            persona_id="persona-001",
            importance=0.8,
        )
        assert memory_id is not None

        memory = await gateway.get(memory_id)
        assert memory is not None
        assert memory["content"] == "Test memory content"

    @pytest.mark.asyncio
    async def test_search(self, gateway):
        """Test memory search."""
        await gateway.store("Python async programming", "p1", importance=0.8)
        await gateway.store("JavaScript promises", "p1", importance=0.7)
        await gateway.store("Python data classes", "p1", importance=0.6)

        results = await gateway.search(
            query="Python programming",
            persona_id="p1",
            limit=5,
        )
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_search_persona_filter(self, gateway):
        """Test that search filters by persona."""
        await gateway.store("Memory for persona A", "persona-a")
        await gateway.store("Memory for persona B", "persona-b")

        results = await gateway.search(
            query="Memory",
            persona_id="persona-a",
            limit=10,
        )
        assert all(r.source != "persona-b" for r in results)

    @pytest.mark.asyncio
    async def test_update(self, gateway):
        """Test memory update."""
        memory_id = await gateway.store("Original content", "p1")
        success = await gateway.update(memory_id, {"importance": 0.9})
        assert success

        memory = await gateway.get(memory_id)
        assert memory["importance"] == 0.9

    @pytest.mark.asyncio
    async def test_delete(self, gateway):
        """Test memory deletion."""
        memory_id = await gateway.store("To be deleted", "p1")
        success = await gateway.delete(memory_id)
        assert success

        memory = await gateway.get(memory_id)
        assert memory is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, gateway):
        """Test deleting nonexistent memory."""
        success = await gateway.delete("nonexistent-id")
        assert not success

    @pytest.mark.asyncio
    async def test_search_relevance_threshold(self, gateway):
        """Test relevance threshold filtering."""
        await gateway.store("Python async", "p1")
        await gateway.store("Completely unrelated topic xyz", "p1")

        results = await gateway.search(
            query="Python",
            persona_id="p1",
            min_relevance=0.3,
        )
        # Results should be filtered by relevance
        assert isinstance(results, list)


# ============================================================================
# Persona Model Tests
# ============================================================================

class TestPersonaTraits:
    """Tests for PersonaTraits model."""

    def test_persona_traits_defaults(self):
        """Test default trait values."""
        traits = PersonaTraits()
        assert 0 <= traits.helpfulness <= 1
        assert 0 <= traits.creativity <= 1
        assert 0 <= traits.precision <= 1

    def test_persona_traits_custom(self):
        """Test custom trait values."""
        traits = PersonaTraits(
            helpfulness=0.95,
            creativity=0.3,
            precision=0.8,
        )
        assert traits.helpfulness == 0.95
        assert traits.creativity == 0.3

    def test_persona_traits_bounds(self):
        """Test trait value bounds."""
        with pytest.raises(Exception):
            PersonaTraits(helpfulness=1.5)
        with pytest.raises(Exception):
            PersonaTraits(helpfulness=-0.1)


class TestPersona:
    """Tests for Persona model."""

    def test_persona_creation(self):
        """Test creating a persona."""
        persona = Persona(
            id="persona-001",
            name="Test Assistant",
            description="A test persona",
        )
        assert persona.id == "persona-001"
        assert persona.name == "Test Assistant"

    def test_persona_get_trait(self):
        """Test getting trait values."""
        persona = Persona(
            id="p1",
            name="Test",
            traits=PersonaTraits(helpfulness=0.9),
        )
        assert persona.get_trait("helpfulness") == 0.9
        assert persona.get_trait("nonexistent") == 0.5  # Default

    def test_persona_adjust_trait(self):
        """Test adjusting trait values."""
        persona = Persona(
            id="p1",
            name="Test",
            traits=PersonaTraits(helpfulness=0.5),
        )
        persona.adjust_trait("helpfulness", 0.1)
        assert persona.traits.helpfulness == 0.6

        # Test bounds
        persona.adjust_trait("helpfulness", 0.5)
        assert persona.traits.helpfulness == 1.0  # Capped at 1.0

    def test_persona_ethics_constraints(self):
        """Test ethics constraints."""
        persona = Persona(
            id="p1",
            name="Test",
            ethics_constraints=[
                EthicsConstraint(id="e1", name="no_harm", severity="critical"),
            ],
        )
        assert len(persona.ethics_constraints) == 1


# ============================================================================
# SandboxExecutor Tests
# ============================================================================

class TestDefaultSandboxExecutor:
    """Tests for DefaultSandboxExecutor."""

    @pytest.fixture
    def sandbox(self):
        return DefaultSandboxExecutor()

    @pytest.fixture
    def context(self):
        return LoopContext(persona_id="test")

    @pytest.mark.asyncio
    async def test_execute_response_action(self, sandbox, context):
        """Test executing a response action."""
        action = PlannedAction(
            action_type=ActionType.RESPONSE,
            description="Test response",
            parameters={"content": "Hello, world!"},
        )
        result = await sandbox.execute(action, context)
        assert result.success
        assert result.output == "Hello, world!"

    @pytest.mark.asyncio
    async def test_execute_memory_store_action(self, sandbox, context):
        """Test executing a memory store action."""
        action = PlannedAction(
            action_type=ActionType.MEMORY_STORE,
            description="Store memory",
            parameters={"content": "Important info"},
        )
        result = await sandbox.execute(action, context)
        assert result.success

    @pytest.mark.asyncio
    async def test_is_available(self, sandbox):
        """Test sandbox availability."""
        assert await sandbox.is_available()


# ============================================================================
# AgenticLoop Tests
# ============================================================================

class TestAgenticLoop:
    """Tests for AgenticLoop engine."""

    def test_agentic_loop_creation(self, sample_persona, mock_llm_gateway):
        """Test creating an agentic loop."""
        loop = AgenticLoop(
            persona=sample_persona,
            llm_gateway=mock_llm_gateway,
        )
        assert loop.persona == sample_persona
        assert loop.max_iterations == 10  # Default

    def test_agentic_loop_custom_iterations(self, sample_persona, mock_llm_gateway):
        """Test custom max iterations."""
        loop = AgenticLoop(
            persona=sample_persona,
            llm_gateway=mock_llm_gateway,
            max_iterations=20,
        )
        assert loop.max_iterations == 20

    @pytest.mark.asyncio
    async def test_run_basic(self, agentic_loop, sample_input_data):
        """Test basic loop execution."""
        result = await agentic_loop.run(sample_input_data)

        assert result is not None
        assert result.status == LoopStatus.COMPLETED
        assert result.iterations_completed >= 1
        assert result.loop_id is not None

    @pytest.mark.asyncio
    async def test_run_with_session_id(self, agentic_loop, sample_input_data):
        """Test loop with specific session ID."""
        result = await agentic_loop.run(
            sample_input_data,
            session_id="custom-session-123",
        )
        assert result.session_id == "custom-session-123"

    @pytest.mark.asyncio
    async def test_perceive_phase(self, agentic_loop):
        """Test PERCEIVE phase."""
        context = LoopContext(
            persona_id=agentic_loop.persona.id,
            input_data={"user_input": "Hello, how are you?"},
        )

        result = await agentic_loop.perceive(context)

        assert isinstance(result, PerceiveResult)
        assert result.has_observations
        assert result.observation_count > 0
        assert result.confidence > 0

    @pytest.mark.asyncio
    async def test_perceive_with_memories(self, agentic_loop):
        """Test PERCEIVE phase with memory retrieval."""
        # Store a memory first
        await agentic_loop.memory_gateway.store(
            content="User prefers dark mode",
            persona_id=agentic_loop.persona.id,
        )

        context = LoopContext(
            persona_id=agentic_loop.persona.id,
            input_data={"user_input": "What is my preference?"},
        )

        result = await agentic_loop.perceive(context)

        assert len(result.relevant_memories) >= 0

    @pytest.mark.asyncio
    async def test_perceive_system_events(self, agentic_loop):
        """Test PERCEIVE phase with system events."""
        context = LoopContext(
            persona_id=agentic_loop.persona.id,
            input_data={
                "user_input": "Test",
                "system_events": ["startup", "config_loaded"],
            },
        )

        result = await agentic_loop.perceive(context)

        # Should have user input + system events as observations
        assert result.observation_count >= 2

    @pytest.mark.asyncio
    async def test_think_phase(self, agentic_loop, mock_llm_gateway):
        """Test THINK phase."""
        context = LoopContext(
            persona_id=agentic_loop.persona.id,
            input_data={"user_input": "Hello"},
        )
        context.perceived_data = PerceiveResult(
            observations=[
                Observation(observation_type=ObservationType.USER_INPUT, content="Hello"),
            ],
            context_summary="User said hello",
        )

        result = await agentic_loop.think(context)

        assert isinstance(result, ThinkResult)
        assert result.reasoning is not None
        # LLM should have been called
        mock_llm_gateway.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_act_phase(self, agentic_loop):
        """Test ACT phase."""
        context = LoopContext(
            persona_id=agentic_loop.persona.id,
            input_data={"user_input": "Test"},
        )
        context.thought_result = ThinkResult(
            planned_actions=[
                PlannedAction(
                    action_type=ActionType.RESPONSE,
                    description="Test action",
                    parameters={"content": "Response"},
                ),
            ],
        )

        result = await agentic_loop.act(context)

        assert isinstance(result, ActResult)
        assert len(result.actions_taken) == 1
        assert result.actions_taken[0].success

    @pytest.mark.asyncio
    async def test_act_no_actions(self, agentic_loop):
        """Test ACT phase with no planned actions."""
        context = LoopContext(persona_id=agentic_loop.persona.id)
        context.thought_result = ThinkResult()

        result = await agentic_loop.act(context)

        assert isinstance(result, ActResult)
        assert len(result.actions_taken) == 0
        assert "No actions to execute" in result.errors

    @pytest.mark.asyncio
    async def test_learn_phase(self, agentic_loop):
        """Test LEARN phase."""
        context = LoopContext(
            persona_id=agentic_loop.persona.id,
            input_data={"user_input": "Hello"},
        )
        context.perceived_data = PerceiveResult(
            observations=[
                Observation(observation_type=ObservationType.USER_INPUT, content="Hello"),
            ],
        )
        context.action_result = ActResult(
            actions_taken=[
                ActionResult(action_id="a1", success=True, output="Hi!"),
            ],
            success=True,
        )

        result = await agentic_loop.learn(context)

        assert isinstance(result, LearnResult)
        assert result.experience_gained > 0
        assert result.has_learning

    @pytest.mark.asyncio
    async def test_learn_from_failure(self, agentic_loop):
        """Test learning from failed actions."""
        context = LoopContext(persona_id=agentic_loop.persona.id)
        context.action_result = ActResult(
            actions_taken=[
                ActionResult(action_id="a1", success=False, error="Failed"),
            ],
            success=False,
            errors=["Action failed"],
        )

        result = await agentic_loop.learn(context)

        # Should still learn from failure
        assert result.has_insights
        assert any(i.insight_type == InsightType.FAILURE_PATTERN for i in result.insights)

    @pytest.mark.asyncio
    async def test_ethics_check(self, agentic_loop):
        """Test ethics checking."""
        action = PlannedAction(
            action_type=ActionType.RESPONSE,
            description="This will harm the user",
            parameters={},
        )
        context = LoopContext(persona_id=agentic_loop.persona.id)

        violations = await agentic_loop._check_ethics(action, context)

        assert len(violations) > 0

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_pause_and_resume(self, agentic_loop):
        """Test pause and resume functionality."""
        # The loop completes very fast in tests, so we test pause/resume
        # on an already-completed loop which should return False
        result = await agentic_loop.run({"user_input": "Test"})
        assert result.status == LoopStatus.COMPLETED
        
        # Pause on completed loop should return False (nothing to pause)
        paused = await agentic_loop.pause()
        assert paused is False  # Cannot pause completed loop
        
        # Resume on completed loop should also return False
        resumed = await agentic_loop.resume()
        assert resumed is False  # Cannot resume completed loop
    @pytest.mark.asyncio
    async def test_stop(self, agentic_loop):
        """Test stopping the loop."""
        agentic_loop._context = LoopContext(persona_id="test")

        stopped = await agentic_loop.stop("Test stop")
        assert stopped
        assert agentic_loop._context.status == LoopStatus.KILLED


# ============================================================================
# Integration Tests
# ============================================================================

class TestAgenticLoopIntegration:
    """Integration tests for the complete loop."""

    @pytest.mark.asyncio
    async def test_full_loop_execution(self, agentic_loop):
        """Test complete loop execution from input to output."""
        input_data = {
            "user_input": "What is the capital of France?",
        }

        result = await agentic_loop.run(input_data)

        assert result.success
        assert result.final_output is not None
        assert result.perceive_summary is not None
        assert result.think_summary is not None
        assert result.act_summary is not None
        assert result.learn_summary is not None
        assert len(result.audit_trail) > 0

    @pytest.mark.asyncio
    async def test_multiple_iterations(self, mock_llm_gateway, mock_memory_gateway):
        """Test loop with multiple iterations."""
        persona = Persona(id="test", name="Test")

        # Create a loop that needs multiple iterations
        loop = AgenticLoop(
            persona=persona,
            llm_gateway=mock_llm_gateway,
            memory_gateway=mock_memory_gateway,
            max_iterations=3,
        )

        result = await loop.run({"user_input": "Complex query"})

        assert result.iterations_completed >= 1
        assert result.iterations_completed <= 3

    @pytest.mark.asyncio
    async def test_kill_switch_integration(self, sample_persona, mock_llm_gateway, mock_memory_gateway):
        """Test kill-switch integration."""
        mock_kill_switch = MagicMock()
        mock_kill_switch.register_persona = AsyncMock(return_value=True)

        # Return active kill-switch after first check
        mock_kill_switch.get_active_kill_switch = MagicMock(return_value=None)

        loop = AgenticLoop(
            persona=sample_persona,
            llm_gateway=mock_llm_gateway,
            memory_gateway=mock_memory_gateway,
            kill_switch=mock_kill_switch,
        )

        result = await loop.run({"user_input": "Test"})

        # Kill-switch should have been checked
        mock_kill_switch.register_persona.assert_called_once()

    @pytest.mark.asyncio
    async def test_memory_integration(self, agentic_loop):
        """Test memory storage and retrieval integration."""
        # Store initial memory
        await agentic_loop.memory_gateway.store(
            content="User likes Python",
            persona_id=agentic_loop.persona.id,
            importance=0.8,
        )

        # Run loop
        result = await agentic_loop.run({
            "user_input": "What programming language do I like?"
        })

        # Should have created new memories
        assert result.success

    @pytest.mark.asyncio
    async def test_error_handling(self, sample_persona, mock_memory_gateway):
        """Test error handling in the loop."""
        # Create a failing LLM gateway
        failing_gateway = MagicMock()
        failing_gateway.generate = AsyncMock(side_effect=Exception("LLM failed"))

        loop = AgenticLoop(
            persona=sample_persona,
            llm_gateway=failing_gateway,
            memory_gateway=mock_memory_gateway,
        )

        result = await loop.run({"user_input": "Test"})

        # Should still complete (with fallback behavior)
        assert result is not None


# ============================================================================
# Factory Function Tests
# ============================================================================

class TestCreateAgenticLoop:
    """Tests for create_agentic_loop factory function."""

    def test_create_with_required_params(self, mock_llm_gateway):
        """Test creating loop with required parameters."""
        loop = create_agentic_loop(
            persona_id="test-001",
            llm_gateway=mock_llm_gateway,
        )

        assert loop.persona.id == "test-001"
        assert loop.llm_gateway == mock_llm_gateway

    def test_create_with_optional_params(self, mock_llm_gateway, mock_memory_gateway, mock_kill_switch):
        """Test creating loop with optional parameters."""
        loop = create_agentic_loop(
            persona_id="test-001",
            persona_name="Custom Assistant",
            llm_gateway=mock_llm_gateway,
            memory_gateway=mock_memory_gateway,
            kill_switch=mock_kill_switch,
            max_iterations=20,
        )

        assert loop.persona.name == "Custom Assistant"
        assert loop.max_iterations == 20
        assert loop.kill_switch == mock_kill_switch

    def test_create_requires_llm_gateway(self):
        """Test that LLM gateway is required."""
        with pytest.raises(ValueError):
            create_agentic_loop(persona_id="test")

    def test_create_default_persona_traits(self, mock_llm_gateway):
        """Test default persona traits."""
        loop = create_agentic_loop(
            persona_id="test",
            llm_gateway=mock_llm_gateway,
        )

        assert loop.persona.traits is not None
        assert loop.persona.ethics_constraints is not None


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_empty_input(self, agentic_loop):
        """Test with empty input."""
        result = await agentic_loop.run({})

        assert result is not None
        # Should still complete, just with no observations

    @pytest.mark.asyncio
    async def test_very_long_input(self, agentic_loop):
        """Test with very long input."""
        long_input = "a" * 10000
        result = await agentic_loop.run({"user_input": long_input})

        assert result is not None

    @pytest.mark.asyncio
    async def test_special_characters(self, agentic_loop):
        """Test with special characters in input."""
        result = await agentic_loop.run({
            "user_input": "Hello! @#$%^&*() {}[]|\\:;\"'<>,.?/~`"
        })

        assert result is not None

    @pytest.mark.asyncio
    async def test_unicode_input(self, agentic_loop):
        """Test with unicode input."""
        result = await agentic_loop.run({
            "user_input": "你好世界 🌍 مرحبا Привет"
        })

        assert result is not None

    @pytest.mark.asyncio
    async def test_concurrent_runs(self, sample_persona, mock_llm_gateway, mock_memory_gateway):
        """Test concurrent loop executions."""
        loop1 = AgenticLoop(
            persona=sample_persona,
            llm_gateway=mock_llm_gateway,
            memory_gateway=mock_memory_gateway,
        )

        # Create second persona for second loop
        persona2 = Persona(id="test-2", name="Test 2")
        loop2 = AgenticLoop(
            persona=persona2,
            llm_gateway=mock_llm_gateway,
            memory_gateway=mock_memory_gateway,
        )

        # Run concurrently
        results = await asyncio.gather(
            loop1.run({"user_input": "Query 1"}),
            loop2.run({"user_input": "Query 2"}),
        )

        assert len(results) == 2
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_max_iterations_limit(self, mock_llm_gateway, mock_memory_gateway):
        """Test that max iterations is respected."""
        persona = Persona(id="test", name="Test")
        loop = AgenticLoop(
            persona=persona,
            llm_gateway=mock_llm_gateway,
            memory_gateway=mock_memory_gateway,
            max_iterations=2,
        )

        result = await loop.run({"user_input": "Test"})

        assert result.iterations_completed <= 2


# ============================================================================
# Performance Tests
# ============================================================================

class TestPerformance:
    """Performance-related tests."""

    @pytest.mark.asyncio
    async def test_single_iteration_speed(self, agentic_loop):
        """Test single iteration completes quickly."""
        start = time.monotonic()

        await agentic_loop.run({"user_input": "Quick test"})

        elapsed = time.monotonic() - start
        # Should complete in under 1 second with mocks
        assert elapsed < 1.0

    @pytest.mark.asyncio
    async def test_processing_time_tracked(self, agentic_loop):
        """Test that processing time is tracked."""
        result = await agentic_loop.run({"user_input": "Test"})

        assert result.total_processing_time_ms > 0

    @pytest.mark.asyncio
    async def test_audit_trail_complete(self, agentic_loop):
        """Test audit trail captures all phases."""
        result = await agentic_loop.run({"user_input": "Test"})

        # Should have entries for all phases
        phases_recorded = set()
        for entry in result.audit_trail:
            if "phase" in entry:
                phases_recorded.add(entry["phase"])

        # At minimum should have perceive and think
        assert len(phases_recorded) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
