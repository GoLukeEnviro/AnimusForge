"""
Memory Fixtures for AnimusForge Test Suite

Provides test data for memory systems, embeddings, and memory-related operations.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import uuid
import json

import pytest


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class TestMemoryEntry:
    """Test memory entry structure."""
    id: str
    content: str
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    accessed_at: datetime = field(default_factory=datetime.utcnow)
    access_count: int = 0
    importance: float = 0.5  # 0.0 to 1.0
    expires_at: Optional[datetime] = None
    tags: List[str] = field(default_factory=list)
    source: str = "user"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "accessed_at": self.accessed_at.isoformat(),
            "access_count": self.access_count,
            "importance": self.importance,
            "tags": self.tags,
            "source": self.source,
        }


@dataclass
class TestConversationMemory:
    """Test conversation memory structure."""
    id: str
    session_id: str
    messages: List[Dict[str, str]]
    summary: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "messages": self.messages,
            "summary": self.summary,
            "message_count": len(self.messages),
        }


@dataclass
class TestWorkingMemory:
    """Test working memory structure."""
    id: str
    context: Dict[str, Any]
    ttl_seconds: int = 3600
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.created_at + timedelta(seconds=self.ttl_seconds)


# ============================================================================
# Mock Embedding Generator
# ============================================================================

def generate_mock_embedding(dimensions: int = 1536, seed: int = 42) -> List[float]:
    """Generate deterministic mock embedding for testing."""
    import math
    # Generate deterministic values based on seed
    embedding = []
    for i in range(dimensions):
        value = math.sin(seed + i * 0.1) * 0.5 + math.cos(seed + i * 0.2) * 0.3
        embedding.append(round(value, 6))
    return embedding


# ============================================================================
# Basic Memory Entry Fixtures
# ============================================================================

@pytest.fixture
def sample_memory_entry() -> TestMemoryEntry:
    """Basic memory entry for testing."""
    return TestMemoryEntry(
        id="mem-test-001",
        content="User asked about Python async programming patterns",
        embedding=generate_mock_embedding(seed=1),
        metadata={
            "topic": "programming",
            "language": "python",
            "category": "technical",
        },
        importance=0.8,
        tags=["python", "async", "programming"],
    )


@pytest.fixture
def simple_memory_entry() -> TestMemoryEntry:
    """Simple memory entry without embedding."""
    return TestMemoryEntry(
        id="mem-simple-001",
        content="User prefers dark mode in IDE",
        metadata={"preference": "ui"},
        importance=0.6,
        tags=["preference", "ui"],
    )


@pytest.fixture
def important_memory_entry() -> TestMemoryEntry:
    """High-importance memory entry."""
    return TestMemoryEntry(
        id="mem-important-001",
        content="User is working on a critical project deadline next week",
        metadata={
            "type": "deadline",
            "priority": "critical",
        },
        importance=0.95,
        tags=["deadline", "project", "important"],
        access_count=10,
    )


@pytest.fixture
def expired_memory_entry() -> TestMemoryEntry:
    """Expired memory entry for testing cleanup."""
    return TestMemoryEntry(
        id="mem-expired-001",
        content="This memory has expired",
        metadata={"temporary": True},
        importance=0.3,
        expires_at=datetime.utcnow() - timedelta(days=1),
    )


# ============================================================================
# Multiple Memory Entries Fixtures
# ============================================================================

@pytest.fixture
def sample_memory_entries() -> List[TestMemoryEntry]:
    """Multiple memory entries for testing retrieval."""
    return [
        TestMemoryEntry(
            id="mem-001",
            content="User prefers dark mode in IDE",
            embedding=generate_mock_embedding(seed=1),
            metadata={"preference": "ui"},
            importance=0.6,
            tags=["preference"],
        ),
        TestMemoryEntry(
            id="mem-002",
            content="User is working on a FastAPI project",
            embedding=generate_mock_embedding(seed=2),
            metadata={"project": "current", "framework": "fastapi"},
            importance=0.9,
            tags=["project", "fastapi"],
        ),
        TestMemoryEntry(
            id="mem-003",
            content="User asked about pytest fixtures yesterday",
            embedding=generate_mock_embedding(seed=3),
            metadata={"topic": "testing"},
            importance=0.7,
            tags=["testing", "pytest"],
        ),
        TestMemoryEntry(
            id="mem-004",
            content="User has experience with Docker and Kubernetes",
            embedding=generate_mock_embedding(seed=4),
            metadata={"skills": "devops"},
            importance=0.5,
            tags=["skills", "devops"],
        ),
        TestMemoryEntry(
            id="mem-005",
            content="User's timezone is UTC-5",
            embedding=generate_mock_embedding(seed=5),
            metadata={"timezone": "UTC-5"},
            importance=0.4,
            tags=["preferences"],
        ),
    ]


@pytest.fixture
def technical_memory_entries() -> List[TestMemoryEntry]:
    """Technical domain memory entries."""
    return [
        TestMemoryEntry(
            id="mem-tech-001",
            content="User is building a microservices architecture",
            metadata={"domain": "architecture"},
            importance=0.85,
            tags=["microservices", "architecture"],
        ),
        TestMemoryEntry(
            id="mem-tech-002",
            content="User prefers PostgreSQL over MySQL",
            metadata={"database": "preference"},
            importance=0.5,
            tags=["database", "postgresql"],
        ),
        TestMemoryEntry(
            id="mem-tech-003",
            content="User is using Python 3.11 for the project",
            metadata={"language_version": "python"},
            importance=0.6,
            tags=["python", "version"],
        ),
    ]


@pytest.fixture
def large_memory_dataset() -> List[TestMemoryEntry]:
    """Large dataset for performance testing."""
    entries = []
    for i in range(100):
        entries.append(TestMemoryEntry(
            id=f"mem-bulk-{i:04d}",
            content=f"Test memory entry number {i} for bulk operations testing",
            embedding=generate_mock_embedding(seed=i),
            metadata={"index": i, "batch": "performance_test"},
            importance=0.3 + (i % 10) * 0.05,
            tags=["bulk", f"batch-{i // 10}"],
        ))
    return entries


# ============================================================================
# Conversation Memory Fixtures
# ============================================================================

@pytest.fixture
def sample_conversation() -> TestConversationMemory:
    """Sample conversation memory."""
    return TestConversationMemory(
        id="conv-001",
        session_id="session-test-001",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "How do I implement async in Python?"},
            {"role": "assistant", "content": "Python async is implemented using asyncio..."},
            {"role": "user", "content": "Can you show an example?"},
            {"role": "assistant", "content": "Here's an example using async/await..."},
        ],
        summary="Discussion about Python async programming",
        metadata={"topic": "python", "turns": 3},
    )


@pytest.fixture
def long_conversation() -> TestConversationMemory:
    """Long conversation for context testing."""
    messages = [{"role": "system", "content": "You are a helpful assistant."}]
    for i in range(20):
        messages.append({"role": "user", "content": f"Question {i+1}: Tell me about topic {i+1}"})
        messages.append({"role": "assistant", "content": f"Response {i+1}: Here's information about topic {i+1}..."})
    
    return TestConversationMemory(
        id="conv-long-001",
        session_id="session-long-001",
        messages=messages,
        summary="Long multi-turn conversation",
        metadata={"turns": 20},
    )


@pytest.fixture
def conversations_batch() -> List[TestConversationMemory]:
    """Multiple conversations for testing."""
    return [
        TestConversationMemory(
            id=f"conv-batch-{i:03d}",
            session_id=f"session-batch-{i:03d}",
            messages=[
                {"role": "user", "content": f"Question {i}"},
                {"role": "assistant", "content": f"Answer {i}"},
            ],
            metadata={"batch_index": i},
        )
        for i in range(10)
    ]


# ============================================================================
# Working Memory Fixtures
# ============================================================================

@pytest.fixture
def sample_working_memory() -> TestWorkingMemory:
    """Sample working memory for testing."""
    return TestWorkingMemory(
        id="wm-001",
        context={
            "current_task": "implementing_user_authentication",
            "active_files": ["auth.py", "models.py"],
            "last_command": "pytest tests/",
            "errors_encountered": 0,
        },
        ttl_seconds=1800,
    )


@pytest.fixture
def expired_working_memory() -> TestWorkingMemory:
    """Expired working memory for cleanup testing."""
    return TestWorkingMemory(
        id="wm-expired-001",
        context={"old_task": "completed"},
        ttl_seconds=0,
        created_at=datetime.utcnow() - timedelta(hours=2),
    )


# ============================================================================
# Memory Configuration Fixtures
# ============================================================================

@pytest.fixture
def memory_config() -> Dict[str, Any]:
    """Memory system configuration."""
    return {
        "max_entries": 10000,
        "retention_days": 30,
        "embedding_dimensions": 1536,
        "similarity_threshold": 0.7,
        "max_context_entries": 20,
        "importance_decay": 0.95,
        "cleanup_interval_hours": 24,
        "index_type": "faiss",
    }


@pytest.fixture
def memory_search_config() -> Dict[str, Any]:
    """Memory search configuration."""
    return {
        "default_limit": 5,
        "max_limit": 50,
        "min_similarity": 0.5,
        "rerank": True,
        "filters": {
            "importance_min": 0.0,
            "tags_any": [],
            "tags_all": [],
        },
    }


# ============================================================================
# Mock Memory Store Fixture
# ============================================================================

@pytest.fixture
def mock_memory_store(sample_memory_entries: List[TestMemoryEntry]):
    """Create mock memory store with test data."""
    from unittest.mock import AsyncMock, MagicMock
    
    store = MagicMock()
    store.entries = {e.id: e for e in sample_memory_entries}
    
    async def mock_search(query: str, limit: int = 5, **kwargs):
        # Simple mock: return first N entries
        return sample_memory_entries[:limit]
    
    async def mock_add(entry: TestMemoryEntry):
        store.entries[entry.id] = entry
        return entry.id
    
    async def mock_get(entry_id: str):
        return store.entries.get(entry_id)
    
    async def mock_delete(entry_id: str):
        if entry_id in store.entries:
            del store.entries[entry_id]
            return True
        return False
    
    async def mock_update(entry_id: str, updates: Dict[str, Any]):
        if entry_id in store.entries:
            entry = store.entries[entry_id]
            for key, value in updates.items():
                if hasattr(entry, key):
                    setattr(entry, key, value)
            entry.updated_at = datetime.utcnow()
            return entry
        return None
    
    store.search = AsyncMock(side_effect=mock_search)
    store.add = AsyncMock(side_effect=mock_add)
    store.get = AsyncMock(side_effect=mock_get)
    store.delete = AsyncMock(side_effect=mock_delete)
    store.update = AsyncMock(side_effect=mock_update)
    store.clear = AsyncMock()
    store.count = MagicMock(return_value=len(sample_memory_entries))
    
    return store


# ============================================================================
# Embedding Fixtures
# ============================================================================

@pytest.fixture
def mock_embedding():
    """Generate mock embedding vector."""
    return generate_mock_embedding()


@pytest.fixture
def mock_embeddings_batch():
    """Generate batch of mock embeddings."""
    return [generate_mock_embedding(seed=i) for i in range(10)]


@pytest.fixture
def similar_embeddings():
    """Generate similar embeddings for similarity testing."""
    base = generate_mock_embedding(seed=1)
    # Create variations with small noise
    similar = [
        [v + 0.01 * (i + 1) for v in base]
        for i in range(3)
    ]
    return [base] + similar


# ============================================================================
# Factory Functions
# ============================================================================

def create_memory_entry(
    content: str = "Test memory content",
    **kwargs
) -> TestMemoryEntry:
    """Factory function to create memory entries."""
    defaults = {
        "id": f"mem-{uuid.uuid4().hex[:8]}",
        "metadata": {},
        "importance": 0.5,
        "tags": [],
    }
    defaults.update(kwargs)
    return TestMemoryEntry(content=content, **defaults)


def create_conversation_memory(
    session_id: str = None,
    messages: List[Dict[str, str]] = None,
    **kwargs
) -> TestConversationMemory:
    """Factory function to create conversation memories."""
    defaults = {
        "id": f"conv-{uuid.uuid4().hex[:8]}",
        "session_id": session_id or f"session-{uuid.uuid4().hex[:8]}",
        "messages": messages or [],
        "metadata": {},
    }
    defaults.update(kwargs)
    return TestConversationMemory(**defaults)


@pytest.fixture
def memory_factory():
    """Provide factory for creating custom memory entries."""
    return create_memory_entry


@pytest.fixture
def conversation_factory():
    """Provide factory for creating custom conversations."""
    return create_conversation_memory
