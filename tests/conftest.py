"""
Pytest Configuration and Common Fixtures for AnimusForge Test Suite

This module provides:
- Async event loop configuration
- Mock fixtures for LLM providers
- Test database fixtures
- API test client
- Cleanup mechanisms
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import AsyncGenerator, Generator, Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass, field
from datetime import datetime
import json
import tempfile
import shutil

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


# ============================================================================
# Event Loop Configuration
# ============================================================================

@pytest.fixture(scope="session")
def event_loop_policy():
    """Configure event loop policy for async tests."""
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="session")
def event_loop(event_loop_policy):
    """Create session-scoped event loop for async tests."""
    loop = event_loop_policy.new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Configuration Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def test_config() -> Dict[str, Any]:
    """Provide test configuration."""
    return {
        "testing": True,
        "debug": True,
        "database": {
            "url": "sqlite+aiosqlite:///:memory:",
            "echo": False,
        },
        "llm": {
            "default_provider": "mock",
            "providers": {
                "mock": {
                    "api_key": "test-key",
                    "model": "test-model",
                    "base_url": "https://mock.local",
                },
                "openai": {
                    "api_key": "test-openai-key",
                    "model": "gpt-4",
                },
                "anthropic": {
                    "api_key": "test-anthropic-key",
                    "model": "claude-3",
                },
            },
        },
        "ethics": {
            "strict_mode": True,
            "violation_threshold": 3,
        },
        "kill_switch": {
            "instability_threshold": 0.7,
            "check_interval": 1.0,
            "cooldown_period": 30.0,
        },
        "memory": {
            "max_entries": 1000,
            "retention_days": 30,
        },
    }


@pytest.fixture(scope="session")
def temp_test_dir() -> Generator[Path, None, None]:
    """Create temporary directory for test artifacts."""
    temp_dir = Path(tempfile.mkdtemp(prefix="animus_test_"))
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


# ============================================================================
# Mock LLM Fixtures
# ============================================================================

@dataclass
class MockLLMResponse:
    """Mock LLM response structure."""
    content: str
    role: str = "assistant"
    finish_reason: str = "stop"
    usage: Dict[str, int] = field(default_factory=lambda: {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30})
    model: str = "mock-model"
    latency_ms: float = 100.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@pytest.fixture
def mock_llm_response() -> MockLLMResponse:
    """Provide a basic mock LLM response."""
    return MockLLMResponse(
        content="This is a mock LLM response for testing purposes.",
        role="assistant",
        metadata={"test": True}
    )


@pytest.fixture
def mock_llm_responses() -> List[MockLLMResponse]:
    """Provide a list of mock LLM responses for conversation tests."""
    return [
        MockLLMResponse(content="First response in conversation."),
        MockLLMResponse(content="Second response in conversation."),
        MockLLMResponse(content="Third response in conversation."),
    ]


@pytest.fixture
def mock_llm_provider():
    """Create mock LLM provider with configurable behavior."""
    provider = MagicMock()
    provider.generate = AsyncMock(return_value=MockLLMResponse(content="Mock response"))
    provider.generate_stream = AsyncMock()
    provider.is_healthy = AsyncMock(return_value=True)
    provider.get_metrics = MagicMock(return_value={
        "total_requests": 0,
        "failed_requests": 0,
        "avg_latency_ms": 0.0,
    })
    provider.name = "mock-provider"
    provider.model = "mock-model"
    return provider


@pytest.fixture
def mock_llm_gateway(mock_llm_provider):
    """Create mock LLM gateway with failover support."""
    from unittest.mock import create_autospec
    
    gateway = MagicMock()
    gateway.providers = [mock_llm_provider]
    gateway.primary_provider = mock_llm_provider
    gateway.generate = AsyncMock(return_value=MockLLMResponse(content="Gateway response"))
    gateway.check_health = AsyncMock(return_value=True)
    gateway.failover = AsyncMock(return_value=True)
    gateway.get_provider_status = MagicMock(return_value={
        "mock-provider": {"healthy": True, "latency_ms": 50}
    })
    return gateway


@pytest.fixture
def mock_failing_llm_provider():
    """Create mock LLM provider that simulates failures."""
    provider = MagicMock()
    provider.generate = AsyncMock(side_effect=Exception("LLM API Error"))
    provider.is_healthy = AsyncMock(return_value=False)
    provider.name = "failing-provider"
    return provider


# ============================================================================
# Persona Fixtures
# ============================================================================

@dataclass
class TestPersona:
    """Test persona structure."""
    id: str
    name: str
    description: str
    traits: Dict[str, Any]
    memory_context: List[str]
    ethics_constraints: List[str]
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)


@pytest.fixture
def sample_persona() -> TestPersona:
    """Provide a sample persona for testing."""
    return TestPersona(
        id="persona-001",
        name="Test Assistant",
        description="A test persona for unit testing",
        traits={
            "helpfulness": 0.9,
            "creativity": 0.7,
            "caution": 0.8,
        },
        memory_context=["User prefers concise answers", "Domain: software development"],
        ethics_constraints=["no_harm", "be_truthful", "respect_privacy"],
    )


@pytest.fixture
def sample_personas() -> List[TestPersona]:
    """Provide multiple personas for testing persona management."""
    return [
        TestPersona(
            id="persona-dev",
            name="Developer Assistant",
            description="Software development expert",
            traits={"technical": 0.95, "precision": 0.9},
            memory_context=["Expert in Python and TypeScript"],
            ethics_constraints=["secure_coding", "no_malware"],
        ),
        TestPersona(
            id="persona-creative",
            name="Creative Writer",
            description="Creative writing assistant",
            traits={"creativity": 0.95, "imagination": 0.9},
            memory_context=["Specializes in fiction and poetry"],
            ethics_constraints=["original_content", "attribution"],
        ),
        TestPersona(
            id="persona-analyst",
            name="Data Analyst",
            description="Data analysis expert",
            traits={"analytical": 0.95, "detail_oriented": 0.9},
            memory_context=["Expert in SQL and Python pandas"],
            ethics_constraints=["data_privacy", "accurate_reporting"],
        ),
    ]


# ============================================================================
# Memory Fixtures
# ============================================================================

@dataclass
class TestMemoryEntry:
    """Test memory entry structure."""
    id: str
    content: str
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    accessed_at: datetime = field(default_factory=datetime.utcnow)
    access_count: int = 0
    importance: float = 0.5


@pytest.fixture
def sample_memory_entry() -> TestMemoryEntry:
    """Provide a sample memory entry for testing."""
    return TestMemoryEntry(
        id="mem-001",
        content="User asked about Python async programming",
        embedding=[0.1] * 1536,  # Mock embedding
        metadata={"topic": "programming", "language": "python"},
        importance=0.8,
    )


@pytest.fixture
def sample_memory_entries() -> List[TestMemoryEntry]:
    """Provide multiple memory entries for testing memory retrieval."""
    return [
        TestMemoryEntry(
            id="mem-001",
            content="User prefers dark mode in IDE",
            metadata={"preference": "ui"},
            importance=0.6,
        ),
        TestMemoryEntry(
            id="mem-002",
            content="User is working on a FastAPI project",
            metadata={"project": "current"},
            importance=0.9,
        ),
        TestMemoryEntry(
            id="mem-003",
            content="User asked about pytest fixtures yesterday",
            metadata={"topic": "testing"},
            importance=0.7,
        ),
        TestMemoryEntry(
            id="mem-004",
            content="User has experience with Docker and Kubernetes",
            metadata={"skills": "devops"},
            importance=0.5,
        ),
    ]


@pytest.fixture
def mock_memory_store(sample_memory_entries):
    """Create mock memory store with test data."""
    store = MagicMock()
    store.entries = {e.id: e for e in sample_memory_entries}
    
    async def mock_search(query: str, limit: int = 5):
        return sample_memory_entries[:limit]
    
    async def mock_add(entry):
        store.entries[entry.id] = entry
        return entry.id
    
    async def mock_get(entry_id: str):
        return store.entries.get(entry_id)
    
    store.search = AsyncMock(side_effect=mock_search)
    store.add = AsyncMock(side_effect=mock_add)
    store.get = AsyncMock(side_effect=mock_get)
    store.delete = AsyncMock()
    store.clear = AsyncMock()
    store.count = MagicMock(return_value=len(sample_memory_entries))
    
    return store


# ============================================================================
# API Test Client Fixtures
# ============================================================================

@pytest.fixture
async def api_client():
    """Create async HTTP client for API testing."""
    try:
        from animus_api.main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    except ImportError:
        # Fallback for when app is not fully configured
        async with AsyncClient() as client:
            yield client


@pytest.fixture
def api_client_sync():
    """Create sync HTTP client for simpler tests."""
    from httpx import Client
    with Client(base_url="http://test") as client:
        yield client


# ============================================================================
# Kill Switch Fixtures
# ============================================================================

@pytest.fixture
def kill_switch_config() -> Dict[str, Any]:
    """Provide kill switch configuration for testing."""
    return {
        "instability_threshold": 0.7,
        "check_interval": 0.1,  # Fast for tests
        "cooldown_period": 1.0,  # Short for tests
        "max_violations": 5,
        "metrics_window": 10,
    }


@pytest.fixture
def mock_kill_switch(kill_switch_config):
    """Create mock kill switch for testing."""
    kill_switch = MagicMock()
    kill_switch.is_active = True
    kill_switch.is_triggered = False
    kill_switch.violation_count = 0
    kill_switch.config = kill_switch_config
    
    async def mock_check():
        return not kill_switch.is_triggered
    
    async def mock_trigger(reason: str):
        kill_switch.is_triggered = True
        kill_switch.trigger_reason = reason
    
    async def mock_reset():
        kill_switch.is_triggered = False
        kill_switch.violation_count = 0
    
    kill_switch.check = AsyncMock(side_effect=mock_check)
    kill_switch.trigger = AsyncMock(side_effect=mock_trigger)
    kill_switch.reset = AsyncMock(side_effect=mock_reset)
    kill_switch.record_violation = MagicMock()
    
    return kill_switch


# ============================================================================
# Ethics Fixtures
# ============================================================================

@pytest.fixture
def ethics_config() -> Dict[str, Any]:
    """Provide ethics configuration for testing."""
    return {
        "strict_mode": True,
        "violation_threshold": 3,
        "enabled_checks": [
            "harmful_content",
            "privacy_violation",
            "misinformation",
            "illegal_activities",
        ],
    }


@pytest.fixture
def sample_ethics_violations() -> List[Dict[str, Any]]:
    """Provide sample ethics violations for testing."""
    return [
        {
            "type": "harmful_content",
            "severity": "high",
            "description": "Content could cause harm",
            "context": "Generated response contained unsafe instructions",
        },
        {
            "type": "privacy_violation",
            "severity": "medium",
            "description": "Potential PII exposure",
            "context": "Response contained what appears to be personal data",
        },
    ]


# ============================================================================
# Cleanup Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def cleanup_after_test():
    """Automatically cleanup after each test."""
    yield
    # Reset any global state
    # This runs after every test
    

@pytest.fixture(scope="session", autouse=True)
def cleanup_session():
    """Session-level cleanup."""
    yield
    # Final cleanup after all tests
    

# ============================================================================
# Test Data Factories
# ============================================================================

class TestDataFactory:
    """Factory for creating test data instances."""
    
    @staticmethod
    def create_persona(**kwargs) -> TestPersona:
        defaults = {
            "id": f"persona-{uuid.uuid4().hex[:8]}",
            "name": "Test Persona",
            "description": "Auto-generated test persona",
            "traits": {},
            "memory_context": [],
            "ethics_constraints": [],
        }
        defaults.update(kwargs)
        return TestPersona(**defaults)
    
    @staticmethod
    def create_memory_entry(**kwargs) -> TestMemoryEntry:
        defaults = {
            "id": f"mem-{uuid.uuid4().hex[:8]}",
            "content": "Test memory content",
            "metadata": {},
            "importance": 0.5,
        }
        defaults.update(kwargs)
        return TestMemoryEntry(**defaults)
    
    @staticmethod
    def create_llm_response(**kwargs) -> MockLLMResponse:
        defaults = {
            "content": "Generated response",
            "role": "assistant",
        }
        defaults.update(kwargs)
        return MockLLMResponse(**defaults)


@pytest.fixture
def test_data_factory() -> TestDataFactory:
    """Provide test data factory."""
    return TestDataFactory()


# ============================================================================
# Markers and Skip Conditions
# ============================================================================

def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "e2e: mark test as an end-to-end test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "requires_docker: mark test as requiring Docker"
    )
    config.addinivalue_line(
        "markers", "requires_llm: mark test as requiring real LLM API"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection based on markers and options."""
    # Skip docker tests if docker not available
    skip_docker = pytest.mark.skip(reason="Docker not available")
    skip_llm = pytest.mark.skip(reason="LLM API keys not set")
    
    for item in items:
        if "requires_docker" in item.keywords:
            # Check if docker is available
            try:
                import docker
                docker.from_env()
            except Exception:
                item.add_marker(skip_docker)
        
        if "requires_llm" in item.keywords:
            # Check if API keys are set
            if not os.environ.get("OPENAI_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
                item.add_marker(skip_llm)


# Import uuid for factory
import uuid
