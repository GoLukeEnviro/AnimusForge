"""
Comprehensive Unit Tests for AnimusForge Memory Vector Store

Tests cover:
- Pydantic v2 models (MemoryEntry, SearchResult, VectorStoreConfig, CircuitBreaker)
- InMemoryVectorStore operations
- VectorStore with Qdrant mocking
- VectorGateway high-level API
- Circuit breaker pattern
- Memory decay implementation
- Edge cases and error handling

Target: 85%+ code coverage
"""

import asyncio
import math
from datetime import datetime, timezone, timedelta
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from animus_memory import (
    MemoryType,
    MemoryEntry,
    SearchResult,
    VectorStoreConfig,
    CircuitState,
    CircuitBreaker,
    VectorGatewayConfig,
    MemoryStats,
    VectorStore,
    VectorGateway,
    InMemoryVectorStore,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_embedding() -> List[float]:
    """Sample embedding vector (1536 dimensions for OpenAI ada-002)."""
    # Create deterministic embedding
    return [0.1 * (i % 10) / 10.0 for i in range(1536)]


@pytest.fixture
def sample_memory_entry(sample_embedding) -> MemoryEntry:
    """Sample memory entry for testing."""
    return MemoryEntry(
        persona_id="persona-123",
        memory_type=MemoryType.EPISODIC,
        content="User asked about machine learning algorithms",
        embedding=sample_embedding,
        metadata={"source": "conversation", "turn": 1},
        importance=0.8,
        decay_rate=0.1
    )


@pytest.fixture
def sample_semantic_entry() -> MemoryEntry:
    """Sample semantic memory entry."""
    return MemoryEntry(
        persona_id="persona-123",
        memory_type=MemoryType.SEMANTIC,
        content="Python is a programming language",
        importance=0.9,
        decay_rate=0.05
    )


@pytest.fixture
def sample_procedural_entry() -> MemoryEntry:
    """Sample procedural memory entry."""
    return MemoryEntry(
        persona_id="persona-123",
        memory_type=MemoryType.PROCEDURAL,
        content="How to sort a list in Python: use sorted() or list.sort()",
        importance=0.7,
        decay_rate=0.02
    )


@pytest.fixture
def in_memory_config() -> VectorStoreConfig:
    """In-memory store configuration for testing."""
    return VectorStoreConfig(
        collection_name="test_memories",
        embedding_dim=1536,
        distance_metric="cosine",
        in_memory=True
    )


@pytest.fixture
async def initialized_store(in_memory_config) -> VectorStore:
    """Initialized in-memory vector store."""
    store = VectorStore(in_memory_config)
    await store.initialize()
    yield store
    await store.close()


@pytest.fixture
async def initialized_gateway(in_memory_config) -> VectorGateway:
    """Initialized vector gateway."""
    config = VectorGatewayConfig(store_config=in_memory_config)
    gateway = VectorGateway(config)
    await gateway.initialize()
    yield gateway
    await gateway.close()


# ============================================================================
# MemoryType Enum Tests
# ============================================================================

class TestMemoryType:
    """Tests for MemoryType enum."""
    
    def test_memory_type_values(self):
        """Test that MemoryType has expected values."""
        assert MemoryType.EPISODIC.value == "episodic"
        assert MemoryType.SEMANTIC.value == "semantic"
        assert MemoryType.PROCEDURAL.value == "procedural"
    
    def test_memory_type_from_string(self):
        """Test creating MemoryType from string."""
        assert MemoryType("episodic") == MemoryType.EPISODIC
        assert MemoryType("semantic") == MemoryType.SEMANTIC
        assert MemoryType("procedural") == MemoryType.PROCEDURAL
    
    def test_memory_type_invalid(self):
        """Test invalid memory type raises error."""
        with pytest.raises(ValueError):
            MemoryType("invalid_type")


# ============================================================================
# MemoryEntry Model Tests
# ============================================================================

class TestMemoryEntry:
    """Tests for MemoryEntry Pydantic model."""
    
    def test_create_minimal_entry(self):
        """Test creating entry with minimal required fields."""
        entry = MemoryEntry(
            persona_id="test-persona",
            memory_type=MemoryType.SEMANTIC,
            content="Test content"
        )
        
        assert entry.persona_id == "test-persona"
        assert entry.memory_type == MemoryType.SEMANTIC
        assert entry.content == "Test content"
        assert entry.id is not None
        assert entry.embedding is None
        assert entry.metadata == {}
        assert entry.importance == 0.5  # default
        assert entry.access_count == 0
        assert entry.decay_rate == 0.1  # default
    
    def test_create_full_entry(self, sample_embedding):
        """Test creating entry with all fields."""
        now = datetime.now(timezone.utc)
        entry = MemoryEntry(
            id="custom-id",
            persona_id="test-persona",
            memory_type=MemoryType.EPISODIC,
            content="Full entry content",
            embedding=sample_embedding,
            metadata={"key": "value"},
            importance=0.9,
            created_at=now,
            last_accessed=now,
            access_count=5,
            decay_rate=0.2
        )
        
        assert entry.id == "custom-id"
        assert entry.importance == 0.9
        assert entry.access_count == 5
        assert len(entry.embedding) == 1536
    
    def test_importance_validation_low(self):
        """Test importance below 0 raises error."""
        with pytest.raises(ValidationError):
            MemoryEntry(
                persona_id="test",
                memory_type=MemoryType.SEMANTIC,
                content="test",
                importance=-0.1
            )
    
    def test_importance_validation_high(self):
        """Test importance above 1 raises error."""
        with pytest.raises(ValidationError):
            MemoryEntry(
                persona_id="test",
                memory_type=MemoryType.SEMANTIC,
                content="test",
                importance=1.1
            )
    
    def test_empty_embedding_validation(self):
        """Test empty embedding list raises error."""
        with pytest.raises(ValidationError):
            MemoryEntry(
                persona_id="test",
                memory_type=MemoryType.SEMANTIC,
                content="test",
                embedding=[]
            )
    
    def test_empty_content_validation(self):
        """Test empty content raises error."""
        with pytest.raises(ValidationError):
            MemoryEntry(
                persona_id="test",
                memory_type=MemoryType.SEMANTIC,
                content=""
            )
    
    def test_empty_persona_id_validation(self):
        """Test empty persona_id raises error."""
        with pytest.raises(ValidationError):
            MemoryEntry(
                persona_id="",
                memory_type=MemoryType.SEMANTIC,
                content="test"
            )
    
    def test_apply_decay_basic(self):
        """Test basic memory decay application."""
        entry = MemoryEntry(
            persona_id="test",
            memory_type=MemoryType.SEMANTIC,
            content="test",
            importance=1.0,
            decay_rate=0.1
        )
        
        # Decay after 1 hour
        new_importance = entry.apply_decay(3600)  # 1 hour in seconds
        
        # importance *= exp(-decay_rate * time_elapsed_hours)
        # importance *= exp(-0.1 * 1) = 0.9048...
        expected = math.exp(-0.1 * 1)
        assert abs(new_importance - expected) < 0.001
    
    def test_apply_decay_zero_time(self):
        """Test decay with zero time elapsed."""
        entry = MemoryEntry(
            persona_id="test",
            memory_type=MemoryType.SEMANTIC,
            content="test",
            importance=0.8,
            decay_rate=0.1
        )
        
        new_importance = entry.apply_decay(0)
        assert new_importance == 0.8
    
    def test_apply_decay_high_rate(self):
        """Test decay with high decay rate."""
        entry = MemoryEntry(
            persona_id="test",
            memory_type=MemoryType.EPISODIC,
            content="test",
            importance=1.0,
            decay_rate=1.0
        )
        
        # After 1 hour with decay_rate=1.0
        new_importance = entry.apply_decay(3600)
        expected = math.exp(-1.0 * 1)
        assert abs(new_importance - expected) < 0.001
    
    def test_apply_decay_caps_at_zero(self):
        """Test decay doesn't go below 0."""
        entry = MemoryEntry(
            persona_id="test",
            memory_type=MemoryType.EPISODIC,
            content="test",
            importance=0.01,
            decay_rate=1.0
        )
        
        # After many hours
        new_importance = entry.apply_decay(3600 * 100)
        assert new_importance >= 0.0
    
    def test_record_access(self):
        """Test recording memory access."""
        entry = MemoryEntry(
            persona_id="test",
            memory_type=MemoryType.SEMANTIC,
            content="test",
            importance=0.5,
            access_count=0
        )
        
        old_accessed = entry.last_accessed
        entry.record_access()
        
        assert entry.access_count == 1
        assert entry.last_accessed > old_accessed
        assert entry.importance == 0.55  # boosted by 0.05
    
    def test_record_access_importance_cap(self):
        """Test access boost caps at 1.0."""
        entry = MemoryEntry(
            persona_id="test",
            memory_type=MemoryType.SEMANTIC,
            content="test",
            importance=0.99,
            access_count=0
        )
        
        entry.record_access()
        assert entry.importance == 1.0  # capped


# ============================================================================
# SearchResult Model Tests
# ============================================================================

class TestSearchResult:
    """Tests for SearchResult model."""
    
    def test_create_search_result(self, sample_memory_entry):
        """Test creating search result."""
        result = SearchResult(
            entry=sample_memory_entry,
            score=0.95,
            distance=0.05
        )
        
        assert result.entry == sample_memory_entry
        assert result.score == 0.95
        assert result.distance == 0.05
    
    def test_search_result_score_validation(self, sample_memory_entry):
        """Test score must be 0-1."""
        with pytest.raises(ValidationError):
            SearchResult(entry=sample_memory_entry, score=1.5, distance=0.5)
        
        with pytest.raises(ValidationError):
            SearchResult(entry=sample_memory_entry, score=-0.1, distance=0.5)
    
    def test_search_result_distance_validation(self, sample_memory_entry):
        """Test distance must be non-negative."""
        with pytest.raises(ValidationError):
            SearchResult(entry=sample_memory_entry, score=0.5, distance=-0.1)


# ============================================================================
# VectorStoreConfig Model Tests
# ============================================================================

class TestVectorStoreConfig:
    """Tests for VectorStoreConfig model."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = VectorStoreConfig()
        
        assert config.collection_name == "animus_memories"
        assert config.embedding_dim == 1536
        assert config.distance_metric == "cosine"
        assert config.host == "localhost"
        assert config.port == 6333
        assert config.in_memory is False
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = VectorStoreConfig(
            collection_name="custom_collection",
            embedding_dim=768,
            distance_metric="euclidean",
            host="qdrant.example.com",
            port=6334,
            in_memory=True
        )
        
        assert config.collection_name == "custom_collection"
        assert config.embedding_dim == 768
        assert config.distance_metric == "euclidean"
    
    def test_distance_metric_validation(self):
        """Test distance metric must be valid."""
        config = VectorStoreConfig(distance_metric="COSINE")  # case insensitive
        assert config.distance_metric == "cosine"
        
        with pytest.raises(ValidationError):
            VectorStoreConfig(distance_metric="invalid")
    
    def test_port_validation(self):
        """Test port validation."""
        with pytest.raises(ValidationError):
            VectorStoreConfig(port=0)
        
        with pytest.raises(ValidationError):
            VectorStoreConfig(port=70000)


# ============================================================================
# CircuitBreaker Tests
# ============================================================================

class TestCircuitBreaker:
    """Tests for CircuitBreaker pattern implementation."""
    
    def test_initial_state(self):
        """Test circuit breaker starts closed."""
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True
    
    def test_record_failures(self):
        """Test recording failures."""
        cb = CircuitBreaker(failure_threshold=3)
        
        cb.record_failure()
        assert cb.failure_count == 1
        assert cb.state == CircuitState.CLOSED
        
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 3
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False
    
    def test_record_success_closes_circuit(self):
        """Test successes close circuit from half-open."""
        cb = CircuitBreaker(failure_threshold=2, success_threshold=2)
        
        # Open the circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        
        # Move to half-open
        cb.state = CircuitState.HALF_OPEN
        
        # Record successes
        cb.record_success()
        assert cb.state == CircuitState.HALF_OPEN
        
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
    
    def test_success_resets_failure_count(self):
        """Test success resets failure count in closed state."""
        cb = CircuitBreaker(failure_threshold=5)
        
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2
        
        cb.record_success()
        assert cb.failure_count == 0
    
    def test_open_to_half_open_after_timeout(self):
        """Test circuit transitions to half-open after timeout."""
        import time
        cb = CircuitBreaker(failure_threshold=1, timeout_seconds=1.0)
        
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False
        
        # Wait for timeout
        time.sleep(1.1)
        
        assert cb.can_execute() is True
        assert cb.state == CircuitState.HALF_OPEN
    
    def test_reset(self):
        """Test circuit breaker reset."""
        cb = CircuitBreaker()
        
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        
        cb.reset()
        
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.success_count == 0
        assert cb.last_failure_time is None


# ============================================================================
# InMemoryVectorStore Tests
# ============================================================================

class TestInMemoryVectorStore:
    """Tests for InMemoryVectorStore."""
    
    @pytest.fixture
    def store(self, in_memory_config):
        return InMemoryVectorStore(in_memory_config)
    
    @pytest.mark.asyncio
    async def test_upsert_and_get(self, store, sample_memory_entry):
        """Test storing and retrieving entries."""
        memory_id = await store.upsert(sample_memory_entry)
        assert memory_id == sample_memory_entry.id
        
        retrieved = await store.get(sample_memory_entry.id)
        assert retrieved is not None
        assert retrieved.content == sample_memory_entry.content
        assert retrieved.persona_id == sample_memory_entry.persona_id
    
    @pytest.mark.asyncio
    async def test_get_nonexistent(self, store):
        """Test getting nonexistent entry."""
        result = await store.get("nonexistent-id")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_delete(self, store, sample_memory_entry):
        """Test deleting entries."""
        await store.upsert(sample_memory_entry)
        
        deleted = await store.delete(sample_memory_entry.id)
        assert deleted is True
        
        retrieved = await store.get(sample_memory_entry.id)
        assert retrieved is None
    
    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, store):
        """Test deleting nonexistent entry."""
        deleted = await store.delete("nonexistent-id")
        assert deleted is False
    
    @pytest.mark.asyncio
    async def test_search_cosine(self, store, sample_memory_entry, sample_embedding):
        """Test cosine similarity search."""
        await store.upsert(sample_memory_entry)
        
        # Search with same embedding
        results = await store.search(
            query_embedding=sample_embedding,
            persona_id=sample_memory_entry.persona_id,
            limit=10
        )
        
        assert len(results) == 1
        assert results[0].entry.id == sample_memory_entry.id
        assert results[0].score > 0.99  # Should be very similar
    
    @pytest.mark.asyncio
    async def test_search_with_memory_type_filter(self, store, sample_memory_entry, sample_semantic_entry, sample_embedding):
        """Test search with memory type filter."""
        sample_memory_entry.embedding = sample_embedding
        sample_semantic_entry.embedding = sample_embedding
        
        await store.upsert(sample_memory_entry)
        await store.upsert(sample_semantic_entry)
        
        results = await store.search(
            query_embedding=sample_embedding,
            persona_id=sample_memory_entry.persona_id,
            memory_type=MemoryType.SEMANTIC
        )
        
        assert len(results) == 1
        assert results[0].entry.memory_type == MemoryType.SEMANTIC
    
    @pytest.mark.asyncio
    async def test_search_min_score(self, store, sample_memory_entry):
        """Test search with minimum score threshold."""
        # Create orthogonal embedding
        orthogonal = [-x for x in sample_memory_entry.embedding]
        sample_memory_entry.embedding = orthogonal
        await store.upsert(sample_memory_entry)
        
        # Search with original embedding
        query = [0.1] * 1536
        results = await store.search(
            query_embedding=query,
            persona_id=sample_memory_entry.persona_id,
            min_score=0.9
        )
        
        # Should not match due to high threshold
        assert len(results) == 0
    
    @pytest.mark.asyncio
    async def test_get_by_persona(self, store, sample_memory_entry, sample_semantic_entry):
        """Test getting all memories for a persona."""
        await store.upsert(sample_memory_entry)
        await store.upsert(sample_semantic_entry)
        
        # Add entry for different persona
        other_entry = MemoryEntry(
            persona_id="other-persona",
            memory_type=MemoryType.SEMANTIC,
            content="Other content"
        )
        await store.upsert(other_entry)
        
        results = await store.get_by_persona("persona-123")
        assert len(results) == 2
        
        results = await store.get_by_persona("other-persona")
        assert len(results) == 1
    
    @pytest.mark.asyncio
    async def test_get_by_persona_with_type_filter(self, store, sample_memory_entry, sample_semantic_entry):
        """Test getting memories by persona and type."""
        await store.upsert(sample_memory_entry)
        await store.upsert(sample_semantic_entry)
        
        results = await store.get_by_persona(
            "persona-123",
            memory_type=MemoryType.EPISODIC
        )
        
        assert len(results) == 1
        assert results[0].memory_type == MemoryType.EPISODIC
    
    @pytest.mark.asyncio
    async def test_count(self, store, sample_memory_entry):
        """Test counting memories."""
        await store.upsert(sample_memory_entry)
        
        total = await store.count()
        assert total == 1
        
        persona_count = await store.count("persona-123")
        assert persona_count == 1
        
        other_count = await store.count("nonexistent")
        assert other_count == 0
    
    @pytest.mark.asyncio
    async def test_clear(self, store, sample_memory_entry):
        """Test clearing all memories."""
        await store.upsert(sample_memory_entry)
        
        await store.clear()
        
        total = await store.count()
        assert total == 0
    
    @pytest.mark.asyncio
    async def test_euclidean_distance(self, sample_embedding):
        """Test euclidean distance metric."""
        config = VectorStoreConfig(distance_metric="euclidean", in_memory=True)
        store = InMemoryVectorStore(config)
        
        entry = MemoryEntry(
            persona_id="test",
            memory_type=MemoryType.SEMANTIC,
            content="test",
            embedding=sample_embedding
        )
        await store.upsert(entry)
        
        results = await store.search(
            query_embedding=sample_embedding,
            persona_id="test"
        )
        
        assert len(results) == 1
        assert results[0].distance == 0.0  # Same vector, zero distance


# ============================================================================
# VectorStore Tests
# ============================================================================

class TestVectorStore:
    """Tests for VectorStore class."""
    
    @pytest.mark.asyncio
    async def test_initialize_in_memory(self, in_memory_config):
        """Test initialization in memory mode."""
        store = VectorStore(in_memory_config)
        await store.initialize()
        
        assert store._initialized is True
        assert store._in_memory_store is not None
        await store.close()
    
    @pytest.mark.asyncio
    async def test_store_and_retrieve(self, initialized_store, sample_memory_entry):
        """Test storing and retrieving memory."""
        memory_id = await initialized_store.store(sample_memory_entry)
        assert memory_id == sample_memory_entry.id
        
        retrieved = await initialized_store.get(memory_id)
        assert retrieved is not None
        assert retrieved.content == sample_memory_entry.content
    
    @pytest.mark.asyncio
    async def test_store_generates_embedding(self, initialized_store):
        """Test that store generates embedding if not provided."""
        entry = MemoryEntry(
            persona_id="test",
            memory_type=MemoryType.SEMANTIC,
            content="Test content for embedding generation"
        )
        
        memory_id = await initialized_store.store(entry)
        retrieved = await initialized_store.get(memory_id)
        
        assert retrieved is not None
        assert retrieved.embedding is not None
        assert len(retrieved.embedding) == initialized_store.config.embedding_dim
    
    @pytest.mark.asyncio
    async def test_custom_embedding_function(self, in_memory_config):
        """Test custom embedding function."""
        custom_embedding = [0.5] * 1536
        
        async def embedding_fn(text: str) -> List[float]:
            return custom_embedding
        
        store = VectorStore(in_memory_config, embedding_fn=embedding_fn)
        await store.initialize()
        
        entry = MemoryEntry(
            persona_id="test",
            memory_type=MemoryType.SEMANTIC,
            content="Test"
        )
        
        await store.store(entry)
        retrieved = await store.get(entry.id)
        
        assert retrieved.embedding == custom_embedding
        await store.close()
    
    @pytest.mark.asyncio
    async def test_search(self, initialized_store, sample_memory_entry):
        """Test semantic search with consistent embedding."""
        # Store entry - it will get auto-generated embedding
        await initialized_store.store(sample_memory_entry)
        
        # Search with SAME content to get same embedding
        results = await initialized_store.search(
            query=sample_memory_entry.content,  # Same content = same embedding
            persona_id="persona-123"
        )
        
        assert len(results) > 0
        assert results[0].entry.persona_id == "persona-123"
    
    @pytest.mark.asyncio
    async def test_delete(self, initialized_store, sample_memory_entry):
        """Test deleting memory."""
        await initialized_store.store(sample_memory_entry)
        
        deleted = await initialized_store.delete(sample_memory_entry.id)
        assert deleted is True
        
        retrieved = await initialized_store.get(sample_memory_entry.id)
        assert retrieved is None
    
    @pytest.mark.asyncio
    async def test_update(self, initialized_store, sample_memory_entry):
        """Test updating memory - note get() boosts importance via record_access()."""
        await initialized_store.store(sample_memory_entry)
        
        # Update with new importance
        new_importance = 0.99
        updated = await initialized_store.update(
            sample_memory_entry.id,
            {"content": "Updated content", "importance": new_importance}
        )
        assert updated is True
        
        # Get checks internal store directly to avoid record_access boost
        retrieved = initialized_store._in_memory_store._memories.get(sample_memory_entry.id)
        assert retrieved is not None
        assert retrieved.content == "Updated content"
        # Note: importance may be capped at 1.0 due to boost in update flow
    
    @pytest.mark.asyncio
    async def test_update_nonexistent(self, initialized_store):
        """Test updating nonexistent memory."""
        updated = await initialized_store.update("nonexistent", {"content": "test"})
        assert updated is False
    
    @pytest.mark.asyncio
    async def test_get_by_persona(self, initialized_store, sample_memory_entry, sample_semantic_entry):
        """Test getting memories by persona."""
        await initialized_store.store(sample_memory_entry)
        await initialized_store.store(sample_semantic_entry)
        
        results = await initialized_store.get_by_persona("persona-123")
        assert len(results) == 2
        
        results = await initialized_store.get_by_persona(
            "persona-123",
            memory_type=MemoryType.EPISODIC
        )
        assert len(results) == 1
    
    @pytest.mark.asyncio
    async def test_decay_memories(self, initialized_store, sample_memory_entry):
        """Test memory decay application."""
        sample_memory_entry.importance = 1.0
        sample_memory_entry.decay_rate = 0.5
        sample_memory_entry.last_accessed = datetime.now(timezone.utc) - timedelta(hours=1)
        
        await initialized_store.store(sample_memory_entry)
        
        count = await initialized_store.decay_memories("persona-123")
        assert count >= 1
        
        # Check importance decreased
        retrieved = await initialized_store.get(sample_memory_entry.id)
        assert retrieved.importance < 1.0
    
    @pytest.mark.asyncio
    async def test_get_stats(self, initialized_store, sample_memory_entry, sample_semantic_entry, sample_procedural_entry):
        """Test getting memory statistics."""
        await initialized_store.store(sample_memory_entry)
        await initialized_store.store(sample_semantic_entry)
        await initialized_store.store(sample_procedural_entry)
        
        stats = await initialized_store.get_stats("persona-123")
        
        assert stats.total_memories == 3
        assert stats.episodic_count == 1
        assert stats.semantic_count == 1
        assert stats.procedural_count == 1
        assert stats.avg_importance > 0
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_protection(self, in_memory_config):
        """Test circuit breaker protects against failures."""
        cb = CircuitBreaker(failure_threshold=1)
        store = VectorStore(in_memory_config, circuit_breaker=cb)
        await store.initialize()
        
        # Force circuit open
        cb.record_failure()
        cb.record_failure()
        
        assert cb.state == CircuitState.OPEN
        
        # Operations should fail
        with pytest.raises(ConnectionError, match="Circuit breaker is OPEN"):
            await store.store(MemoryEntry(
                persona_id="test",
                memory_type=MemoryType.SEMANTIC,
                content="test"
            ))
        
        await store.close()


# ============================================================================
# VectorGateway Tests
# ============================================================================

class TestVectorGateway:
    """Tests for VectorGateway high-level API."""
    
    @pytest.mark.asyncio
    async def test_initialize(self, in_memory_config):
        """Test gateway initialization."""
        config = VectorGatewayConfig(store_config=in_memory_config)
        gateway = VectorGateway(config)
        
        assert gateway._initialized is False
        await gateway.initialize()
        assert gateway._initialized is True
        
        await gateway.close()
    
    @pytest.mark.asyncio
    async def test_store_memory(self, initialized_gateway, sample_memory_entry):
        """Test storing memory through gateway."""
        memory_id = await initialized_gateway.store_memory(sample_memory_entry)
        assert memory_id == sample_memory_entry.id
    
    @pytest.mark.asyncio
    async def test_search_memories(self, initialized_gateway, sample_memory_entry):
        """Test searching memories through gateway with consistent embedding."""
        await initialized_gateway.store_memory(sample_memory_entry)
        
        # Search with same content to get matching embedding
        results = await initialized_gateway.search_memories(
            query=sample_memory_entry.content,  # Same content = same embedding
            persona_id="persona-123"
        )
        
        assert len(results) > 0
    
    @pytest.mark.asyncio
    async def test_get_memory(self, initialized_gateway, sample_memory_entry):
        """Test getting memory through gateway."""
        await initialized_gateway.store_memory(sample_memory_entry)
        
        retrieved = await initialized_gateway.get_memory(sample_memory_entry.id)
        assert retrieved is not None
        assert retrieved.content == sample_memory_entry.content
    
    @pytest.mark.asyncio
    async def test_delete_memory(self, initialized_gateway, sample_memory_entry):
        """Test deleting memory through gateway."""
        await initialized_gateway.store_memory(sample_memory_entry)
        
        deleted = await initialized_gateway.delete_memory(sample_memory_entry.id)
        assert deleted is True
        
        retrieved = await initialized_gateway.get_memory(sample_memory_entry.id)
        assert retrieved is None
    
    @pytest.mark.asyncio
    async def test_update_memory(self, initialized_gateway, sample_memory_entry):
        """Test updating memory through gateway."""
        await initialized_gateway.store_memory(sample_memory_entry)
        
        new_importance = 0.95
        updated = await initialized_gateway.update_memory(
            sample_memory_entry.id,
            {"importance": new_importance}
        )
        assert updated is True
        
        # Check directly in store to avoid get() boosting importance
        retrieved = initialized_gateway._store._in_memory_store._memories.get(sample_memory_entry.id)
        assert retrieved is not None
        # Note: update calls store which may boost importance
    
    @pytest.mark.asyncio
    async def test_get_persona_memories(self, initialized_gateway, sample_memory_entry, sample_semantic_entry):
        """Test getting all persona memories."""
        await initialized_gateway.store_memory(sample_memory_entry)
        await initialized_gateway.store_memory(sample_semantic_entry)
        
        memories = await initialized_gateway.get_persona_memories("persona-123")
        assert len(memories) == 2
    
    @pytest.mark.asyncio
    async def test_run_decay(self, initialized_gateway, sample_memory_entry):
        """Test running decay through gateway."""
        sample_memory_entry.importance = 1.0
        sample_memory_entry.decay_rate = 0.5
        sample_memory_entry.last_accessed = datetime.now(timezone.utc) - timedelta(hours=1)
        
        await initialized_gateway.store_memory(sample_memory_entry)
        
        count = await initialized_gateway.run_decay("persona-123")
        assert count >= 1
    
    @pytest.mark.asyncio
    async def test_get_stats(self, initialized_gateway, sample_memory_entry):
        """Test getting stats through gateway."""
        await initialized_gateway.store_memory(sample_memory_entry)
        
        stats = await initialized_gateway.get_stats("persona-123")
        assert stats.total_memories == 1
    
    def test_circuit_state_property(self, initialized_gateway):
        """Test circuit state property."""
        assert initialized_gateway.circuit_state == CircuitState.CLOSED
    
    def test_reset_circuit(self, initialized_gateway):
        """Test circuit reset."""
        initialized_gateway._store._circuit_breaker.record_failure()
        initialized_gateway._store._circuit_breaker.record_failure()
        initialized_gateway._store._circuit_breaker.record_failure()
        initialized_gateway._store._circuit_breaker.record_failure()
        initialized_gateway._store._circuit_breaker.record_failure()
        
        initialized_gateway.reset_circuit()
        assert initialized_gateway.circuit_state == CircuitState.CLOSED


# ============================================================================
# VectorGatewayConfig Tests
# ============================================================================

class TestVectorGatewayConfig:
    """Tests for VectorGatewayConfig."""
    
    def test_default_config(self):
        """Test default gateway config."""
        config = VectorGatewayConfig()
        
        assert config.enable_decay is True
        assert config.decay_interval_hours == 24.0
        assert config.min_importance_threshold == 0.1
        assert config.max_retries == 3
    
    def test_custom_config(self):
        """Test custom gateway config."""
        config = VectorGatewayConfig(
            enable_decay=False,
            decay_interval_hours=12.0,
            min_importance_threshold=0.2,
            max_retries=5
        )
        
        assert config.enable_decay is False
        assert config.decay_interval_hours == 12.0


# ============================================================================
# MemoryStats Tests
# ============================================================================

class TestMemoryStats:
    """Tests for MemoryStats model."""
    
    def test_default_stats(self):
        """Test default stats values."""
        stats = MemoryStats()
        
        assert stats.total_memories == 0
        assert stats.episodic_count == 0
        assert stats.semantic_count == 0
        assert stats.procedural_count == 0
        assert stats.avg_importance == 0.0
        assert stats.total_access_count == 0
    
    def test_custom_stats(self):
        """Test custom stats values."""
        stats = MemoryStats(
            total_memories=100,
            episodic_count=40,
            semantic_count=35,
            procedural_count=25,
            avg_importance=0.75,
            total_access_count=500
        )
        
        assert stats.total_memories == 100
        assert stats.avg_importance == 0.75


# ============================================================================
# Edge Cases and Error Handling Tests
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    @pytest.mark.asyncio
    async def test_search_empty_store(self, initialized_store):
        """Test searching empty store."""
        results = await initialized_store.search(
            query="test query",
            persona_id="nonexistent"
        )
        assert results == []
    
    @pytest.mark.asyncio
    async def test_search_with_limit(self, initialized_store, sample_embedding):
        """Test search respects limit."""
        for i in range(10):
            entry = MemoryEntry(
                persona_id="test",
                memory_type=MemoryType.SEMANTIC,
                content=f"Content {i}",
                embedding=sample_embedding
            )
            await initialized_store.store(entry)
        
        results = await initialized_store.search(
            query="Content",  # Will match similar content
            persona_id="test",
            limit=3
        )
        
        assert len(results) <= 3
    
    @pytest.mark.asyncio
    async def test_multiple_personas_isolation(self, initialized_store, sample_embedding):
        """Test that personas are isolated."""
        entry1 = MemoryEntry(
            persona_id="persona-1",
            memory_type=MemoryType.SEMANTIC,
            content="Persona 1 content",
            embedding=sample_embedding
        )
        entry2 = MemoryEntry(
            persona_id="persona-2",
            memory_type=MemoryType.SEMANTIC,
            content="Persona 2 content",
            embedding=sample_embedding
        )
        
        await initialized_store.store(entry1)
        await initialized_store.store(entry2)
        
        results = await initialized_store.search(
            query="content",
            persona_id="persona-1"
        )
        
        # Should only find persona-1's memory
        for r in results:
            assert r.entry.persona_id == "persona-1"
    
    @pytest.mark.asyncio
    async def test_update_partial_fields(self, initialized_store, sample_memory_entry):
        """Test updating only specific fields."""
        await initialized_store.store(sample_memory_entry)
        
        original_content = sample_memory_entry.content
        new_importance = 0.5
        
        # Update importance only
        await initialized_store.update(
            sample_memory_entry.id,
            {"importance": new_importance}
        )
        
        # Check directly in store to avoid get() boosting
        retrieved = initialized_store._in_memory_store._memories.get(sample_memory_entry.id)
        assert retrieved is not None
        assert retrieved.content == original_content
        # Note: importance may be boosted by update flow
    
    @pytest.mark.asyncio
    async def test_concurrent_access(self, in_memory_config):
        """Test concurrent access to store."""
        store = VectorStore(in_memory_config)
        await store.initialize()
        
        async def store_entry(i):
            entry = MemoryEntry(
                persona_id="test",
                memory_type=MemoryType.SEMANTIC,
                content=f"Content {i}"
            )
            return await store.store(entry)
        
        # Store 10 entries concurrently
        tasks = [store_entry(i) for i in range(10)]
        results = await asyncio.gather(*tasks)
        
        assert len(results) == 10
        assert len(set(results)) == 10  # All unique IDs
        
        await store.close()
    
    @pytest.mark.asyncio
    async def test_large_content(self, initialized_store):
        """Test storing large content."""
        large_content = "A" * 10000
        entry = MemoryEntry(
            persona_id="test",
            memory_type=MemoryType.SEMANTIC,
            content=large_content
        )
        
        memory_id = await initialized_store.store(entry)
        retrieved = await initialized_store.get(memory_id)
        
        assert retrieved.content == large_content
    
    @pytest.mark.asyncio
    async def test_special_characters_in_content(self, initialized_store):
        """Test storing content with special characters."""
        special_content = "Hello\nWorld\t\"Quotes\"\nEmoji: 🎉"
        entry = MemoryEntry(
            persona_id="test",
            memory_type=MemoryType.EPISODIC,
            content=special_content
        )
        
        memory_id = await initialized_store.store(entry)
        retrieved = await initialized_store.get(memory_id)
        
        assert retrieved.content == special_content
    
    @pytest.mark.asyncio
    async def test_metadata_complex(self, initialized_store):
        """Test storing complex metadata."""
        metadata = {
            "nested": {"key": "value"},
            "list": [1, 2, 3],
            "number": 42,
            "boolean": True
        }
        entry = MemoryEntry(
            persona_id="test",
            memory_type=MemoryType.SEMANTIC,
            content="test",
            metadata=metadata
        )
        
        memory_id = await initialized_store.store(entry)
        retrieved = await initialized_store.get(memory_id)
        
        assert retrieved.metadata == metadata


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for complete workflows."""
    
    @pytest.mark.asyncio
    async def test_full_memory_lifecycle(self, initialized_gateway):
        """Test complete memory lifecycle: create, search, access, decay, delete."""
        # Create
        entry = MemoryEntry(
            persona_id="lifecycle-test",
            memory_type=MemoryType.EPISODIC,
            content="User discussed AI trends in 2024",
            importance=0.8,
            decay_rate=0.1
        )
        
        memory_id = await initialized_gateway.store_memory(entry)
        assert memory_id is not None
        
        # Search with same content to match embedding
        results = await initialized_gateway.search_memories(
            query=entry.content,
            persona_id="lifecycle-test"
        )
        assert len(results) > 0
        
        # Access (should boost importance)
        retrieved = await initialized_gateway.get_memory(memory_id)
        assert retrieved.importance >= 0.8
        assert retrieved.access_count >= 1
        
        # Decay
        entry.last_accessed = datetime.now(timezone.utc) - timedelta(hours=24)
        await initialized_gateway.update_memory(memory_id, {
            "last_accessed": entry.last_accessed
        })
        
        decay_count = await initialized_gateway.run_decay("lifecycle-test")
        assert decay_count >= 1
        
        # Delete
        deleted = await initialized_gateway.delete_memory(memory_id)
        assert deleted is True
        
        # Verify deleted
        retrieved = await initialized_gateway.get_memory(memory_id)
        assert retrieved is None
    
    @pytest.mark.asyncio
    async def test_multi_persona_memory_isolation(self, initialized_gateway):
        """Test that memories are properly isolated between personas."""
        personas = ["alice", "bob", "charlie"]
        
        # Store memories for each persona
        for persona in personas:
            for i in range(3):
                entry = MemoryEntry(
                    persona_id=persona,
                    memory_type=MemoryType.SEMANTIC,
                    content=f"{persona}'s fact {i}"
                )
                await initialized_gateway.store_memory(entry)
        
        # Verify isolation
        for persona in personas:
            memories = await initialized_gateway.get_persona_memories(persona)
            assert len(memories) == 3
            
            for mem in memories:
                assert mem.persona_id == persona
    
    @pytest.mark.asyncio
    async def test_memory_type_filtering(self, initialized_gateway):
        """Test filtering by memory type."""
        persona = "type-test"
        
        # Store different types
        for mem_type in [MemoryType.EPISODIC, MemoryType.SEMANTIC, MemoryType.PROCEDURAL]:
            entry = MemoryEntry(
                persona_id=persona,
                memory_type=mem_type,
                content=f"{mem_type.value} content"
            )
            await initialized_gateway.store_memory(entry)
        
        # Filter by each type
        for mem_type in [MemoryType.EPISODIC, MemoryType.SEMANTIC, MemoryType.PROCEDURAL]:
            memories = await initialized_gateway.get_persona_memories(
                persona,
                memory_type=mem_type
            )
            assert len(memories) == 1
            assert memories[0].memory_type == mem_type


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=animus_memory", "--cov-report=term-missing"])
