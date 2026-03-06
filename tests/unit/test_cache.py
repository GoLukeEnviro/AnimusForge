"""
Unit tests for Cache Manager module.

Tests for CacheBackend, CacheEntry, CacheStats, CacheConfig, CacheManager, and CacheGateway.
Achieves 85%+ coverage with async tests, edge cases, and integration scenarios.
"""

import asyncio
import json
import pytest
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Set
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import ValidationError

from animus_memory.cache import (
    CacheBackend,
    CacheEntry,
    CacheStats,
    CacheConfig,
    CacheManager,
    CacheGateway,
)


# ============================================
# Fixtures
# ============================================

@pytest.fixture
def basic_config() -> CacheConfig:
    """Create basic cache configuration."""
    return CacheConfig(
        backend=CacheBackend.MEMORY,
        default_ttl=3600,
        max_memory=1024 * 1024,  # 1MB
        eviction_policy="lru"
    )


@pytest.fixture
async def cache_manager(basic_config: CacheConfig) -> CacheManager:
    """Create initialized cache manager."""
    manager = CacheManager(basic_config)
    await manager.initialize()
    yield manager
    await manager.close()


@pytest.fixture
async def cache_gateway(cache_manager: CacheManager) -> CacheGateway:
    """Create cache gateway with initialized manager."""
    gateway = CacheGateway(manager=cache_manager)
    await gateway.initialize()
    yield gateway
    await gateway.close()


# ============================================
# CacheBackend Enum Tests
# ============================================

class TestCacheBackend:
    """Tests for CacheBackend enum."""

    def test_backend_values(self):
        """Test enum has correct values."""
        assert CacheBackend.REDIS.value == "redis"
        assert CacheBackend.MEMORY.value == "memory"

    def test_backend_from_string(self):
        """Test creating backend from string."""
        assert CacheBackend("redis") == CacheBackend.REDIS
        assert CacheBackend("memory") == CacheBackend.MEMORY

    def test_backend_string_representation(self):
        """Test string representation."""
        assert str(CacheBackend.REDIS) == "CacheBackend.REDIS"
        assert CacheBackend.REDIS.value == "redis"


# ============================================
# CacheEntry Model Tests
# ============================================

class TestCacheEntry:
    """Tests for CacheEntry model."""

    def test_create_entry_minimal(self):
        """Test creating entry with minimal fields."""
        entry = CacheEntry(key="test_key", value="test_value")
        assert entry.key == "test_key"
        assert entry.value == "test_value"
        assert entry.ttl is None
        assert entry.tags == set()
        assert entry.metadata == {}
        assert isinstance(entry.created_at, datetime)

    def test_create_entry_full(self):
        """Test creating entry with all fields."""
        now = datetime.now(timezone.utc)
        tags = {"tag1", "tag2"}
        metadata = {"meta": "data"}

        entry = CacheEntry(
            key="test_key",
            value={"complex": "data"},
            ttl=300,
            created_at=now,
            tags=tags,
            metadata=metadata,
            size_bytes=100
        )

        assert entry.key == "test_key"
        assert entry.value == {"complex": "data"}
        assert entry.ttl == 300
        assert entry.created_at == now
        assert entry.tags == tags
        assert entry.metadata == metadata
        assert entry.size_bytes == 100

    def test_is_expired_no_ttl(self):
        """Test expiration check with no TTL."""
        entry = CacheEntry(key="key", value="value", ttl=None)
        assert not entry.is_expired()

    def test_is_expired_not_expired(self):
        """Test expiration check when not expired."""
        entry = CacheEntry(
            key="key",
            value="value",
            ttl=3600,
            created_at=datetime.now(timezone.utc)
        )
        assert not entry.is_expired()

    def test_is_expired_expired(self):
        """Test expiration check when expired."""
        entry = CacheEntry(
            key="key",
            value="value",
            ttl=1,
            created_at=datetime.now(timezone.utc) - timedelta(seconds=2)
        )
        assert entry.is_expired()

    def test_remaining_ttl_no_ttl(self):
        """Test remaining TTL calculation with no TTL."""
        entry = CacheEntry(key="key", value="value", ttl=None)
        assert entry.remaining_ttl() is None

    def test_remaining_ttl_positive(self):
        """Test remaining TTL calculation when time remains."""
        entry = CacheEntry(
            key="key",
            value="value",
            ttl=300,
            created_at=datetime.now(timezone.utc)
        )
        remaining = entry.remaining_ttl()
        assert remaining is not None
        assert 295 <= remaining <= 300  # Account for test execution time

    def test_remaining_ttl_zero(self):
        """Test remaining TTL when expired."""
        entry = CacheEntry(
            key="key",
            value="value",
            ttl=1,
            created_at=datetime.now(timezone.utc) - timedelta(seconds=10)
        )
        assert entry.remaining_ttl() == 0

    def test_entry_with_empty_key_raises(self):
        """Test that empty key raises validation error."""
        with pytest.raises(ValidationError):
            CacheEntry(key="", value="value")

    def test_entry_with_negative_ttl_raises(self):
        """Test that negative TTL raises validation error."""
        with pytest.raises(ValidationError):
            CacheEntry(key="key", value="value", ttl=-1)

    def test_entry_with_negative_size_raises(self):
        """Test that negative size raises validation error."""
        with pytest.raises(ValidationError):
            CacheEntry(key="key", value="value", size_bytes=-1)


# ============================================
# CacheStats Model Tests
# ============================================

class TestCacheStats:
    """Tests for CacheStats model."""

    def test_create_stats_default(self):
        """Test creating stats with defaults."""
        stats = CacheStats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.total_requests == 0
        assert stats.hit_rate == 0.0
        assert stats.keys_count == 0
        assert stats.memory_usage == 0
        assert stats.evictions == 0
        assert stats.backend == CacheBackend.MEMORY

    def test_record_hit(self):
        """Test recording a hit."""
        stats = CacheStats()
        stats.record_hit()
        assert stats.hits == 1
        assert stats.misses == 0
        assert stats.total_requests == 1
        assert stats.hit_rate == 1.0

    def test_record_miss(self):
        """Test recording a miss."""
        stats = CacheStats()
        stats.record_miss()
        assert stats.hits == 0
        assert stats.misses == 1
        assert stats.total_requests == 1
        assert stats.hit_rate == 0.0

    def test_hit_rate_calculation(self):
        """Test hit rate calculation with multiple requests."""
        stats = CacheStats()
        stats.record_hit()
        stats.record_hit()
        stats.record_miss()
        assert stats.hits == 2
        assert stats.misses == 1
        assert stats.total_requests == 3
        assert abs(stats.hit_rate - 0.6666666666666666) < 0.0001

    def test_stats_with_all_fields(self):
        """Test creating stats with all fields."""
        stats = CacheStats(
            hits=100,
            misses=50,
            total_requests=150,
            hit_rate=0.66,
            keys_count=25,
            memory_usage=1024,
            evictions=5,
            backend=CacheBackend.REDIS
        )
        assert stats.hits == 100
        assert stats.misses == 50
        assert stats.total_requests == 150
        assert stats.hit_rate == 0.66
        assert stats.keys_count == 25
        assert stats.memory_usage == 1024
        assert stats.evictions == 5
        assert stats.backend == CacheBackend.REDIS


# ============================================
# CacheConfig Model Tests
# ============================================

class TestCacheConfig:
    """Tests for CacheConfig model."""

    def test_create_config_default(self):
        """Test creating config with defaults."""
        config = CacheConfig()
        assert config.backend == CacheBackend.MEMORY
        assert config.redis_url == "redis://localhost:6379/0"
        assert config.default_ttl == 3600
        assert config.max_memory == 100 * 1024 * 1024
        assert config.eviction_policy == "lru"
        assert config.key_prefix == "animus:"

    def test_create_config_custom(self):
        """Test creating config with custom values."""
        config = CacheConfig(
            backend=CacheBackend.REDIS,
            redis_url="redis://custom:6380/1",
            default_ttl=7200,
            max_memory=200 * 1024 * 1024,
            eviction_policy="lfu",
            key_prefix="custom:"
        )
        assert config.backend == CacheBackend.REDIS
        assert config.redis_url == "redis://custom:6380/1"
        assert config.default_ttl == 7200
        assert config.max_memory == 200 * 1024 * 1024
        assert config.eviction_policy == "lfu"
        assert config.key_prefix == "custom:"

    def test_eviction_policy_validation(self):
        """Test eviction policy validation."""
        # Valid policies
        for policy in ["lru", "lfu", "fifo", "LRU", "LFU", "FIFO"]:
            config = CacheConfig(eviction_policy=policy)
            assert config.eviction_policy == policy.lower()

        # Invalid policy
        with pytest.raises(ValidationError):
            CacheConfig(eviction_policy="invalid")

    def test_negative_default_ttl_raises(self):
        """Test that negative default TTL raises error."""
        with pytest.raises(ValidationError):
            CacheConfig(default_ttl=-1)

    def test_negative_max_memory_raises(self):
        """Test that negative max memory raises error."""
        with pytest.raises(ValidationError):
            CacheConfig(max_memory=-1)


# ============================================
# CacheManager Tests
# ============================================

class TestCacheManager:
    """Tests for CacheManager class."""

    @pytest.mark.asyncio
    async def test_initialize_memory_backend(self, basic_config: CacheConfig):
        """Test initialization with memory backend."""
        manager = CacheManager(basic_config)
        assert not manager._initialized

        result = await manager.initialize()
        assert result is True
        assert manager._initialized is True

        await manager.close()
        assert manager._initialized is False

    @pytest.mark.asyncio
    async def test_set_and_get(self, cache_manager: CacheManager):
        """Test basic set and get operations."""
        # Set value
        result = await cache_manager.set("test_key", "test_value")
        assert result is True

        # Get value
        value = await cache_manager.get("test_key")
        assert value == "test_value"

    @pytest.mark.asyncio
    async def test_set_with_ttl(self, cache_manager: CacheManager):
        """Test setting value with TTL."""
        result = await cache_manager.set("ttl_key", "ttl_value", ttl=1)
        assert result is True

        # Value should exist immediately
        value = await cache_manager.get("ttl_key")
        assert value == "ttl_value"

        # Wait for expiry
        await asyncio.sleep(1.1)

        # Value should be expired
        value = await cache_manager.get("ttl_key")
        assert value is None

    @pytest.mark.asyncio
    async def test_set_with_tags(self, cache_manager: CacheManager):
        """Test setting value with tags."""
        tags = {"tag1", "tag2"}
        result = await cache_manager.set("tagged_key", "value", tags=tags)
        assert result is True

        # Check tag index
        assert "tag1" in cache_manager._tag_index
        assert "tag2" in cache_manager._tag_index

    @pytest.mark.asyncio
    async def test_get_nonexistent_key(self, cache_manager: CacheManager):
        """Test getting nonexistent key."""
        value = await cache_manager.get("nonexistent")
        assert value is None

    @pytest.mark.asyncio
    async def test_delete_existing_key(self, cache_manager: CacheManager):
        """Test deleting existing key."""
        await cache_manager.set("delete_me", "value")
        result = await cache_manager.delete("delete_me")
        assert result is True

        value = await cache_manager.get("delete_me")
        assert value is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_key(self, cache_manager: CacheManager):
        """Test deleting nonexistent key."""
        result = await cache_manager.delete("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_exists_true(self, cache_manager: CacheManager):
        """Test exists returns true for existing key."""
        await cache_manager.set("exists_key", "value")
        result = await cache_manager.exists("exists_key")
        assert result is True

    @pytest.mark.asyncio
    async def test_exists_false(self, cache_manager: CacheManager):
        """Test exists returns false for nonexistent key."""
        result = await cache_manager.exists("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_exists_expired(self, cache_manager: CacheManager):
        """Test exists returns false for expired key."""
        await cache_manager.set("expired_key", "value", ttl=1)
        await asyncio.sleep(1.1)
        result = await cache_manager.exists("expired_key")
        assert result is False

    @pytest.mark.asyncio
    async def test_clear(self, cache_manager: CacheManager):
        """Test clearing all cache entries."""
        await cache_manager.set("key1", "value1")
        await cache_manager.set("key2", "value2")
        await cache_manager.set("key3", "value3")

        count = await cache_manager.clear()
        assert count >= 3

        assert await cache_manager.get("key1") is None
        assert await cache_manager.get("key2") is None
        assert await cache_manager.get("key3") is None

    @pytest.mark.asyncio
    async def test_get_by_tag(self, cache_manager: CacheManager):
        """Test getting entries by tag."""
        await cache_manager.set("key1", "value1", tags={"shared"})
        await cache_manager.set("key2", "value2", tags={"shared"})
        await cache_manager.set("key3", "value3", tags={"other"})

        entries = await cache_manager.get_by_tag("shared")
        assert len(entries) == 2
        values = [e.value for e in entries]
        assert "value1" in values
        assert "value2" in values

    @pytest.mark.asyncio
    async def test_invalidate_tag(self, cache_manager: CacheManager):
        """Test invalidating entries by tag."""
        await cache_manager.set("key1", "value1", tags={"shared"})
        await cache_manager.set("key2", "value2", tags={"shared"})
        await cache_manager.set("key3", "value3", tags={"other"})

        count = await cache_manager.invalidate_tag("shared")
        assert count == 2

        assert await cache_manager.get("key1") is None
        assert await cache_manager.get("key2") is None
        assert await cache_manager.get("key3") == "value3"

    @pytest.mark.asyncio
    async def test_get_stats(self, cache_manager: CacheManager):
        """Test getting cache statistics."""
        await cache_manager.set("key1", "value1")
        await cache_manager.get("key1")  # hit
        await cache_manager.get("nonexistent")  # miss

        stats = await cache_manager.get_stats()
        assert stats.hits == 1
        assert stats.misses == 1
        assert stats.total_requests == 2
        assert stats.keys_count >= 1

    @pytest.mark.asyncio
    async def test_set_many(self, cache_manager: CacheManager):
        """Test setting multiple values."""
        items = {"key1": "value1", "key2": "value2", "key3": "value3"}
        count = await cache_manager.set_many(items)
        assert count == 3

        assert await cache_manager.get("key1") == "value1"
        assert await cache_manager.get("key2") == "value2"
        assert await cache_manager.get("key3") == "value3"

    @pytest.mark.asyncio
    async def test_get_many(self, cache_manager: CacheManager):
        """Test getting multiple values."""
        await cache_manager.set("key1", "value1")
        await cache_manager.set("key2", "value2")

        result = await cache_manager.get_many(["key1", "key2", "nonexistent"])
        assert result == {"key1": "value1", "key2": "value2"}

    @pytest.mark.asyncio
    async def test_touch_existing_key(self, cache_manager: CacheManager):
        """Test touching existing key to update TTL."""
        await cache_manager.set("touch_key", "value", ttl=10)

        result = await cache_manager.touch("touch_key", 300)
        assert result is True

        # Entry should have new TTL
        entry = cache_manager._memory_cache.get(cache_manager._make_key("touch_key"))
        assert entry is not None
        assert entry.ttl == 300

    @pytest.mark.asyncio
    async def test_touch_nonexistent_key(self, cache_manager: CacheManager):
        """Test touching nonexistent key."""
        result = await cache_manager.touch("nonexistent", 300)
        assert result is False

    @pytest.mark.asyncio
    async def test_complex_value_types(self, cache_manager: CacheManager):
        """Test caching complex value types."""
        # Dict
        await cache_manager.set("dict_key", {"nested": {"data": 123}})
        assert await cache_manager.get("dict_key") == {"nested": {"data": 123}}

        # List
        await cache_manager.set("list_key", [1, 2, 3, 4])
        assert await cache_manager.get("list_key") == [1, 2, 3, 4]

        # Boolean
        await cache_manager.set("bool_key", True)
        assert await cache_manager.get("bool_key") is True

        # None
        await cache_manager.set("none_key", None)
        assert await cache_manager.get("none_key") is None


# ============================================
# Eviction Policy Tests
# ============================================

class TestEvictionPolicies:
    """Tests for different eviction policies."""

    @pytest.mark.asyncio
    async def test_lru_eviction(self):
        """Test LRU eviction policy."""
        config = CacheConfig(
            backend=CacheBackend.MEMORY,
            max_memory=500,  # Very small to trigger eviction
            eviction_policy="lru"
        )
        manager = CacheManager(config)
        await manager.initialize()

        try:
            # Add entries that will exceed memory
            await manager.set("key1", "a" * 200)
            await manager.set("key2", "b" * 200)

            # Access key1 to make it recently used
            await manager.get("key1")

            # Add key3, should evict key2 (LRU)
            await manager.set("key3", "c" * 200)

            # key1 should still exist (recently accessed)
            assert await manager.get("key1") is not None
            # key2 should be evicted
            assert await manager.get("key2") is None

            stats = await manager.get_stats()
            assert stats.evictions >= 1
        finally:
            await manager.close()

    @pytest.mark.asyncio
    async def test_lfu_eviction(self):
        """Test LFU eviction policy."""
        config = CacheConfig(
            backend=CacheBackend.MEMORY,
            max_memory=500,
            eviction_policy="lfu"
        )
        manager = CacheManager(config)
        await manager.initialize()

        try:
            await manager.set("key1", "a" * 150)
            await manager.set("key2", "b" * 150)

            # Access key1 multiple times
            for _ in range(5):
                await manager.get("key1")

            # Access key2 only once
            await manager.get("key2")

            # Add key3, should evict key2 (LFU)
            await manager.set("key3", "c" * 200)

            # key1 should still exist (frequently accessed)
            assert await manager.get("key1") is not None
            # key2 should be evicted (less frequently accessed)
            assert await manager.get("key2") is None
        finally:
            await manager.close()

    @pytest.mark.asyncio
    async def test_fifo_eviction(self):
        """Test FIFO eviction policy."""
        config = CacheConfig(
            backend=CacheBackend.MEMORY,
            max_memory=500,
            eviction_policy="fifo"
        )
        manager = CacheManager(config)
        await manager.initialize()

        try:
            await manager.set("key1", "a" * 200)
            await manager.set("key2", "b" * 200)

            # Access key1 (shouldn't matter for FIFO)
            await manager.get("key1")

            # Add key3, should evict key1 (first in)
            await manager.set("key3", "c" * 200)

            # key1 should be evicted (first in)
            assert await manager.get("key1") is None
            # key2 should still exist
            assert await manager.get("key2") is not None
        finally:
            await manager.close()


# ============================================
# Circuit Breaker Tests
# ============================================

class TestCacheCircuitBreaker:
    """Tests for circuit breaker integration."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_state_on_init(self, cache_manager: CacheManager):
        """Test circuit breaker starts closed."""
        assert cache_manager._circuit_breaker.state.value == "closed"

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_on_failures(self):
        """Test circuit breaker opens after threshold failures."""
        config = CacheConfig(
            backend=CacheBackend.REDIS,
            redis_url="redis://nonexistent:6379/0",
            circuit_failure_threshold=2
        )
        manager = CacheManager(config)

        # Mock Redis client that fails
        with patch.object(manager, '_client', None):
            # Simulate failures
            manager._circuit_breaker.record_failure()
            manager._circuit_breaker.record_failure()

            assert manager._circuit_breaker.state.value == "open"

    @pytest.mark.asyncio
    async def test_fallback_to_memory_on_redis_failure(self):
        """Test fallback to memory cache when Redis unavailable."""
        config = CacheConfig(
            backend=CacheBackend.REDIS,
            redis_url="redis://nonexistent:6379/0"
        )
        manager = CacheManager(config)
        await manager.initialize()

        try:
            # Should fall back to memory backend
            assert manager._stats.backend == CacheBackend.MEMORY

            # Operations should still work
            await manager.set("test", "value")
            assert await manager.get("test") == "value"
        finally:
            await manager.close()


# ============================================
# CacheGateway Tests
# ============================================

class TestCacheGateway:
    """Tests for CacheGateway class."""

    @pytest.mark.asyncio
    async def test_cache_persona(self, cache_gateway: CacheGateway):
        """Test caching persona data."""
        persona_data = {"name": "Test", "traits": ["friendly", "helpful"]}
        result = await cache_gateway.cache_persona("persona_123", persona_data)
        assert result is True

    @pytest.mark.asyncio
    async def test_get_cached_persona(self, cache_gateway: CacheGateway):
        """Test retrieving cached persona."""
        persona_data = {"name": "Test", "traits": ["friendly"]}
        await cache_gateway.cache_persona("persona_456", persona_data)

        cached = await cache_gateway.get_cached_persona("persona_456")
        assert cached == persona_data

    @pytest.mark.asyncio
    async def test_get_cached_persona_not_found(self, cache_gateway: CacheGateway):
        """Test retrieving nonexistent persona."""
        cached = await cache_gateway.get_cached_persona("nonexistent")
        assert cached is None

    @pytest.mark.asyncio
    async def test_cache_memory(self, cache_gateway: CacheGateway):
        """Test caching memory data."""
        memory_data = {"content": "Test memory", "importance": 0.8}
        result = await cache_gateway.cache_memory("memory_789", memory_data)
        assert result is True

    @pytest.mark.asyncio
    async def test_get_cached_memory(self, cache_gateway: CacheGateway):
        """Test retrieving cached memory."""
        memory_data = {"content": "Test memory"}
        await cache_gateway.cache_memory("memory_101", memory_data)

        cached = await cache_gateway.get_cached_memory("memory_101")
        assert cached == memory_data

    @pytest.mark.asyncio
    async def test_cache_memory_with_persona_tag(self, cache_gateway: CacheGateway):
        """Test memory caching includes persona tag."""
        memory_data = {"content": "Test", "persona_id": "persona_xyz"}
        await cache_gateway.cache_memory("memory_202", memory_data)

        # Check that persona tag was added
        full_key = cache_gateway.manager._make_key("memory:memory_202")
        entry = cache_gateway.manager._memory_cache.get(full_key)
        assert "persona:persona_xyz" in entry.tags

    @pytest.mark.asyncio
    async def test_invalidate_persona(self, cache_gateway: CacheGateway):
        """Test invalidating persona cache."""
        await cache_gateway.cache_persona("persona_inval", {"name": "Test"})

        count = await cache_gateway.invalidate_persona("persona_inval")
        assert count >= 1

        cached = await cache_gateway.get_cached_persona("persona_inval")
        assert cached is None

    @pytest.mark.asyncio
    async def test_invalidate_memory(self, cache_gateway: CacheGateway):
        """Test invalidating memory cache."""
        await cache_gateway.cache_memory("memory_inval", {"content": "Test"})

        count = await cache_gateway.invalidate_memory("memory_inval")
        assert count >= 1

        cached = await cache_gateway.get_cached_memory("memory_inval")
        assert cached is None

    @pytest.mark.asyncio
    async def test_get_stats(self, cache_gateway: CacheGateway):
        """Test getting stats through gateway."""
        stats = await cache_gateway.get_stats()
        assert isinstance(stats, CacheStats)

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, cache_gateway: CacheGateway):
        """Test health check returns healthy status."""
        # Add some hits
        await cache_gateway.cache_persona("test", {"name": "Test"})
        await cache_gateway.get_cached_persona("test")

        health = await cache_gateway.health_check()
        assert health["status"] in ["healthy", "degraded"]
        assert health["backend"] == "memory"
        assert "hit_rate" in health
        assert "keys_count" in health
        assert "memory_usage_mb" in health
        assert "circuit_breaker_state" in health

    @pytest.mark.asyncio
    async def test_health_check_degraded(self, cache_gateway: CacheGateway):
        """Test health check returns degraded with low hit rate."""
        # Generate many misses
        for i in range(20):
            await cache_gateway.get_cached_persona(f"nonexistent_{i}")

        health = await cache_gateway.health_check()
        # With low hit rate and many requests, should be degraded
        assert health["status"] == "degraded"


# ============================================
# Edge Cases and Integration Tests
# ============================================

class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    @pytest.mark.asyncio
    async def test_large_value(self, cache_manager: CacheManager):
        """Test caching large value."""
        large_data = "x" * 50000
        result = await cache_manager.set("large_key", large_data)
        assert result is True

        cached = await cache_manager.get("large_key")
        assert cached == large_data

    @pytest.mark.asyncio
    async def test_special_characters_in_key(self, cache_manager: CacheManager):
        """Test keys with special characters."""
        key = "key:with:special:chars:123"
        await cache_manager.set(key, "value")
        assert await cache_manager.get(key) == "value"

    @pytest.mark.asyncio
    async def test_unicode_value(self, cache_manager: CacheManager):
        """Test unicode values."""
        unicode_data = {"emoji": "😀🎉", "chinese": "中文", "arabic": "العربية"}
        await cache_manager.set("unicode_key", unicode_data)
        assert await cache_manager.get("unicode_key") == unicode_data

    @pytest.mark.asyncio
    async def test_empty_tags(self, cache_manager: CacheManager):
        """Test setting value with empty tags set."""
        result = await cache_manager.set("no_tags", "value", tags=set())
        assert result is True

    @pytest.mark.asyncio
    async def test_overwrite_existing_key(self, cache_manager: CacheManager):
        """Test overwriting existing key."""
        await cache_manager.set("overwrite", "original")
        await cache_manager.set("overwrite", "updated")

        assert await cache_manager.get("overwrite") == "updated"

    @pytest.mark.asyncio
    async def test_concurrent_access(self, cache_manager: CacheManager):
        """Test concurrent access to cache."""
        async def set_get(key: str, value: str):
            await cache_manager.set(key, value)
            return await cache_manager.get(key)

        tasks = [
            set_get(f"concurrent_{i}", f"value_{i}")
            for i in range(10)
        ]

        results = await asyncio.gather(*tasks)

        for i, result in enumerate(results):
            assert result == f"value_{i}"

    @pytest.mark.asyncio
    async def test_zero_ttl(self, cache_manager: CacheManager):
        """Test setting with zero TTL."""
        await cache_manager.set("zero_ttl", "value", ttl=0)
        # With TTL=0, entry is immediately expired
        result = await cache_manager.get("zero_ttl")
        # Should return None since it's expired
        assert result is None

    @pytest.mark.asyncio
    async def test_tag_cleanup_on_delete(self, cache_manager: CacheManager):
        """Test that tags are cleaned up when entry is deleted."""
        await cache_manager.set("key1", "value1", tags={"tag1"})
        await cache_manager.set("key2", "value2", tags={"tag1"})

        # Delete key1
        await cache_manager.delete("key1")

        # Tag1 should still have key2
        assert "tag1" in cache_manager._tag_index
        full_key2 = cache_manager._make_key("key2")
        assert full_key2 in cache_manager._tag_index["tag1"]

        # Delete key2
        await cache_manager.delete("key2")

        # Tag1 should be removed when empty
        assert "tag1" not in cache_manager._tag_index

    @pytest.mark.asyncio
    async def test_reinitialize(self, cache_manager: CacheManager):
        """Test reinitializing cache manager."""
        await cache_manager.set("key", "value")

        # Initialize again
        result = await cache_manager.initialize()
        assert result is True

        # Data should still be there
        assert await cache_manager.get("key") == "value"


# ============================================
# Key Prefix Tests
# ============================================

class TestKeyPrefix:
    """Tests for key prefix functionality."""

    @pytest.mark.asyncio
    async def test_default_prefix(self, cache_manager: CacheManager):
        """Test default key prefix is applied."""
        await cache_manager.set("test_key", "value")

        # Check internal storage has prefix
        full_key = cache_manager._make_key("test_key")
        assert full_key.startswith("animus:")

    @pytest.mark.asyncio
    async def test_custom_prefix(self):
        """Test custom key prefix."""
        config = CacheConfig(key_prefix="custom:")
        manager = CacheManager(config)
        await manager.initialize()

        try:
            await manager.set("key", "value")
            full_key = manager._make_key("key")
            assert full_key == "custom:key"
        finally:
            await manager.close()


# ============================================
# Statistics Edge Cases
# ============================================

class TestStatsEdgeCases:
    """Tests for statistics edge cases."""

    @pytest.mark.asyncio
    async def test_stats_after_clear(self, cache_manager: CacheManager):
        """Test stats are updated after clear."""
        await cache_manager.set("key1", "value1")
        await cache_manager.set("key2", "value2")

        await cache_manager.clear()

        stats = await cache_manager.get_stats()
        assert stats.keys_count == 0
        assert stats.memory_usage == 0

    @pytest.mark.asyncio
    async def test_hit_rate_no_requests(self):
        """Test hit rate with no requests."""
        stats = CacheStats()
        assert stats.hit_rate == 0.0


# ============================================
# Redis Mock Tests
# ============================================

class TestRedisIntegration:
    """Tests with mocked Redis for integration coverage."""

    @pytest.mark.asyncio
    async def test_redis_set_success(self):
        """Test successful Redis set operation."""
        config = CacheConfig(backend=CacheBackend.REDIS)
        manager = CacheManager(config)

        # Mock Redis client
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.get = AsyncMock(return_value=json.dumps("test_value"))

        with patch("redis.asyncio.from_url", return_value=mock_redis):
            await manager.initialize()
            assert manager._client is not None

            await manager.set("test_key", "test_value")
            value = await manager.get("test_key")
            assert value == "test_value"

        await manager.close()

    @pytest.mark.asyncio
    async def test_redis_delete_success(self):
        """Test successful Redis delete operation."""
        config = CacheConfig(backend=CacheBackend.REDIS)
        manager = CacheManager(config)

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.delete = AsyncMock(return_value=1)

        with patch("redis.asyncio.from_url", return_value=mock_redis):
            await manager.initialize()
            result = await manager.delete("test_key")
            assert result is True

        await manager.close()

    @pytest.mark.asyncio
    async def test_redis_exists_success(self):
        """Test successful Redis exists operation."""
        config = CacheConfig(backend=CacheBackend.REDIS)
        manager = CacheManager(config)

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.exists = AsyncMock(return_value=1)

        with patch("redis.asyncio.from_url", return_value=mock_redis):
            await manager.initialize()
            result = await manager.exists("test_key")
            assert result is True

        await manager.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
