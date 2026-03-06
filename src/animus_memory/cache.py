"""
AnimusForge Memory System - Cache Manager

Redis-backed cache with in-memory fallback for persona and memory caching.
Supports LRU eviction, tag-based invalidation, and circuit breaker pattern.
"""

from collections import OrderedDict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union
import asyncio
import json
import logging
import sys
import time

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict

# Import CircuitBreaker from base module
from animus_memory.base import CircuitBreaker, CircuitState

logger = logging.getLogger(__name__)


class CacheBackend(str, Enum):
    """Available cache backend types."""
    REDIS = "redis"
    MEMORY = "memory"


class CacheEntry(BaseModel):
    """Single cache entry with metadata and tag support."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        arbitrary_types_allowed=True
    )

    key: str = Field(..., min_length=1, description="Cache key")
    value: Any = Field(..., description="Cached value")
    ttl: Optional[int] = Field(default=None, ge=0, description="Time-to-live in seconds, None = no expiry")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tags: Set[str] = Field(default_factory=set, description="Tags for group invalidation")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    size_bytes: int = Field(default=0, ge=0, description="Estimated size in bytes")

    def is_expired(self) -> bool:
        """Check if entry has expired based on TTL."""
        if self.ttl is None:
            return False
        elapsed = (datetime.now(timezone.utc) - self.created_at).total_seconds()
        return elapsed >= self.ttl

    def remaining_ttl(self) -> Optional[int]:
        """Get remaining TTL in seconds, None if no expiry."""
        if self.ttl is None:
            return None
        elapsed = (datetime.now(timezone.utc) - self.created_at).total_seconds()
        return max(0, int(self.ttl - elapsed))


class CacheStats(BaseModel):
    """Cache statistics for monitoring."""

    model_config = ConfigDict(
        validate_assignment=True,
        arbitrary_types_allowed=True
    )

    hits: int = Field(default=0, ge=0, description="Cache hits")
    misses: int = Field(default=0, ge=0, description="Cache misses")
    total_requests: int = Field(default=0, ge=0, description="Total requests")
    hit_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Hit rate 0-1")
    keys_count: int = Field(default=0, ge=0, description="Number of cached keys")
    memory_usage: int = Field(default=0, ge=0, description="Memory usage in bytes")
    evictions: int = Field(default=0, ge=0, description="Number of evictions")
    backend: CacheBackend = Field(default=CacheBackend.MEMORY, description="Active backend")

    def record_hit(self) -> None:
        """Record a cache hit."""
        self.hits += 1
        self.total_requests += 1
        self._update_hit_rate()

    def record_miss(self) -> None:
        """Record a cache miss."""
        self.misses += 1
        self.total_requests += 1
        self._update_hit_rate()

    def _update_hit_rate(self) -> None:
        """Update hit rate based on current stats."""
        if self.total_requests > 0:
            self.hit_rate = self.hits / self.total_requests


class CacheConfig(BaseModel):
    """Configuration for CacheManager."""

    model_config = ConfigDict(str_strip_whitespace=True)

    backend: CacheBackend = Field(default=CacheBackend.MEMORY, description="Cache backend type")
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")
    default_ttl: int = Field(default=3600, ge=0, description="Default TTL in seconds (1 hour)")
    max_memory: int = Field(default=100 * 1024 * 1024, ge=0, description="Max memory in bytes (100MB)")
    eviction_policy: str = Field(default="lru", description="Eviction policy: lru, lfu, fifo")
    key_prefix: str = Field(default="animus:", description="Key prefix for namespacing")
    circuit_failure_threshold: int = Field(default=5, ge=1, description="Circuit breaker failure threshold")
    circuit_timeout_seconds: float = Field(default=60.0, ge=1.0, description="Circuit breaker timeout")

    @field_validator('eviction_policy')
    @classmethod
    def validate_eviction_policy(cls, v: str) -> str:
        allowed = {'lru', 'lfu', 'fifo'}
        if v.lower() not in allowed:
            raise ValueError(f'eviction_policy must be one of {allowed}')
        return v.lower()


class CacheManager:
    """
    Async cache manager with Redis backend and in-memory fallback.

    Features:
    - Redis primary backend with automatic fallback
    - In-memory LRU cache for fallback/testing
    - Tag-based invalidation
    - Circuit breaker for fault tolerance
    - Statistics tracking
    """

    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig()
        self._client: Optional[Any] = None  # Redis client
        self._memory_cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._tag_index: Dict[str, Set[str]] = {}  # tag -> set of keys
        self._access_counts: Dict[str, int] = {}  # For LFU tracking
        self._lock = asyncio.Lock()
        self._stats = CacheStats(backend=self.config.backend)
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=self.config.circuit_failure_threshold,
            timeout_seconds=self.config.circuit_timeout_seconds
        )
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize cache backend, attempt Redis connection."""
        if self._initialized:
            return True

        if self.config.backend == CacheBackend.REDIS:
            try:
                import redis.asyncio as redis
                self._client = redis.from_url(
                    self.config.redis_url,
                    encoding="utf-8",
                    decode_responses=True
                )
                # Test connection
                await self._client.ping()
                self._stats.backend = CacheBackend.REDIS
                logger.info(f"CacheManager: Connected to Redis at {self.config.redis_url}")
            except Exception as e:
                logger.warning(f"CacheManager: Redis connection failed, falling back to memory: {e}")
                self._client = None
                self._stats.backend = CacheBackend.MEMORY
                self._circuit_breaker.record_failure()

        self._initialized = True
        return True

    async def close(self) -> None:
        """Close connections."""
        if self._client:
            await self._client.close()
            self._client = None
        self._initialized = False

    def _make_key(self, key: str) -> str:
        """Create namespaced key."""
        return f"{self.config.key_prefix}{key}"

    def _estimate_size(self, value: Any) -> int:
        """Estimate memory size of value in bytes."""
        try:
            return len(json.dumps(value, default=str))
        except (TypeError, ValueError):
            return sys.getsizeof(value)

    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        await self.initialize()
        full_key = self._make_key(key)

        async with self._lock:
            # Try Redis first if available
            if self._client and self._circuit_breaker.can_execute():
                try:
                    value = await self._client.get(full_key)
                    if value is not None:
                        self._stats.record_hit()
                        self._circuit_breaker.record_success()
                        return json.loads(value)
                    self._stats.record_miss()
                    return None
                except Exception as e:
                    logger.debug(f"CacheManager: Redis get failed: {e}")
                    self._circuit_breaker.record_failure()

            # Fallback to memory cache
            if full_key in self._memory_cache:
                entry = self._memory_cache[full_key]
                if entry.is_expired():
                    await self._remove_entry(full_key)
                    self._stats.record_miss()
                    return None

                # Update access tracking for LRU/LFU
                self._access_counts[full_key] = self._access_counts.get(full_key, 0) + 1
                if self.config.eviction_policy == "lru":
                    # Move to end for LRU
                    self._memory_cache.move_to_end(full_key)

                self._stats.record_hit()
                return entry.value

            self._stats.record_miss()
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        tags: Optional[Set[str]] = None
    ) -> bool:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (uses default if None)
            tags: Tags for group invalidation

        Returns:
            True if successful
        """
        await self.initialize()
        full_key = self._make_key(key)
        effective_ttl = ttl if ttl is not None else self.config.default_ttl
        tags = tags or set()

        # Create entry
        entry = CacheEntry(
            key=full_key,
            value=value,
            ttl=effective_ttl,
            tags=tags,
            size_bytes=self._estimate_size(value)
        )

        async with self._lock:
            # Try Redis first
            if self._client and self._circuit_breaker.can_execute():
                try:
                    serialized = json.dumps(value, default=str)
                    if effective_ttl:
                        await self._client.setex(full_key, effective_ttl, serialized)
                    else:
                        await self._client.set(full_key, serialized)

                    # Store tags in Redis set
                    for tag in tags:
                        await self._client.sadd(self._make_key(f"tag:{tag}"), full_key)

                    self._circuit_breaker.record_success()
                    return True
                except Exception as e:
                    logger.debug(f"CacheManager: Redis set failed: {e}")
                    self._circuit_breaker.record_failure()

            # Fallback to memory cache
            # Check memory limit and evict if needed
            await self._ensure_memory_capacity(entry.size_bytes)

            # Remove old entry if exists
            if full_key in self._memory_cache:
                await self._remove_entry(full_key)

            # Store entry
            self._memory_cache[full_key] = entry
            self._access_counts[full_key] = 1

            # Update tag index
            for tag in tags:
                if tag not in self._tag_index:
                    self._tag_index[tag] = set()
                self._tag_index[tag].add(full_key)

            self._update_memory_stats()
            return True

    async def delete(self, key: str) -> bool:
        """
        Delete key from cache.

        Args:
            key: Cache key

        Returns:
            True if key was deleted
        """
        await self.initialize()
        full_key = self._make_key(key)

        async with self._lock:
            deleted = False

            # Try Redis
            if self._client and self._circuit_breaker.can_execute():
                try:
                    result = await self._client.delete(full_key)
                    deleted = result > 0
                    self._circuit_breaker.record_success()
                except Exception as e:
                    logger.debug(f"CacheManager: Redis delete failed: {e}")
                    self._circuit_breaker.record_failure()

            # Also remove from memory cache
            if full_key in self._memory_cache:
                await self._remove_entry(full_key)
                deleted = True

            return deleted

    async def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.

        Args:
            key: Cache key

        Returns:
            True if key exists and is not expired
        """
        await self.initialize()
        full_key = self._make_key(key)

        async with self._lock:
            # Try Redis
            if self._client and self._circuit_breaker.can_execute():
                try:
                    exists = await self._client.exists(full_key) > 0
                    self._circuit_breaker.record_success()
                    return exists
                except Exception as e:
                    logger.debug(f"CacheManager: Redis exists failed: {e}")
                    self._circuit_breaker.record_failure()

            # Check memory cache
            if full_key in self._memory_cache:
                entry = self._memory_cache[full_key]
                if not entry.is_expired():
                    return True
                await self._remove_entry(full_key)

            return False

    async def clear(self) -> int:
        """
        Clear all cache entries.

        Returns:
            Number of keys cleared
        """
        await self.initialize()

        async with self._lock:
            count = len(self._memory_cache)

            # Clear Redis keys with prefix
            if self._client and self._circuit_breaker.can_execute():
                try:
                    pattern = f"{self.config.key_prefix}*"
                    keys = []
                    async for key in self._client.scan_iter(match=pattern):
                        keys.append(key)
                    if keys:
                        await self._client.delete(*keys)
                    self._circuit_breaker.record_success()
                except Exception as e:
                    logger.debug(f"CacheManager: Redis clear failed: {e}")
                    self._circuit_breaker.record_failure()

            # Clear memory cache
            self._memory_cache.clear()
            self._tag_index.clear()
            self._access_counts.clear()
            self._update_memory_stats()

            return count

    async def get_by_tag(self, tag: str) -> List[CacheEntry]:
        """
        Get all entries with a specific tag.

        Args:
            tag: Tag to search for

        Returns:
            List of matching cache entries
        """
        await self.initialize()
        entries: List[CacheEntry] = []

        async with self._lock:
            # Try Redis
            if self._client and self._circuit_breaker.can_execute():
                try:
                    tag_key = self._make_key(f"tag:{tag}")
                    keys = await self._client.smembers(tag_key)
                    for key in keys:
                        value = await self._client.get(key)
                        if value:
                            entries.append(CacheEntry(
                                key=key,
                                value=json.loads(value),
                                tags={tag}
                            ))
                    self._circuit_breaker.record_success()
                    return entries
                except Exception as e:
                    logger.debug(f"CacheManager: Redis get_by_tag failed: {e}")
                    self._circuit_breaker.record_failure()

            # Memory cache lookup
            if tag in self._tag_index:
                for key in self._tag_index[tag]:
                    if key in self._memory_cache:
                        entry = self._memory_cache[key]
                        if not entry.is_expired():
                            entries.append(entry)

        return entries

    async def invalidate_tag(self, tag: str) -> int:
        """
        Invalidate all entries with a specific tag.

        Args:
            tag: Tag to invalidate

        Returns:
            Number of keys invalidated
        """
        await self.initialize()
        count = 0

        async with self._lock:
            # Try Redis
            if self._client and self._circuit_breaker.can_execute():
                try:
                    tag_key = self._make_key(f"tag:{tag}")
                    keys = await self._client.smembers(tag_key)
                    if keys:
                        await self._client.delete(*keys)
                        count = len(keys)
                    await self._client.delete(tag_key)
                    self._circuit_breaker.record_success()
                except Exception as e:
                    logger.debug(f"CacheManager: Redis invalidate_tag failed: {e}")
                    self._circuit_breaker.record_failure()

            # Memory cache invalidation
            if tag in self._tag_index:
                keys_to_remove = list(self._tag_index[tag])
                for key in keys_to_remove:
                    if key in self._memory_cache:
                        del self._memory_cache[key]
                        self._access_counts.pop(key, None)
                        count += 1
                del self._tag_index[tag]

            self._update_memory_stats()

        return count

    async def get_stats(self) -> CacheStats:
        """
        Get cache statistics.

        Returns:
            Current cache statistics
        """
        async with self._lock:
            self._update_memory_stats()
            return self._stats.model_copy()

    async def set_many(self, items: Dict[str, Any], ttl: Optional[int] = None) -> int:
        """
        Set multiple values at once.

        Args:
            items: Dictionary of key-value pairs
            ttl: Time-to-live for all items

        Returns:
            Number of items set
        """
        count = 0
        for key, value in items.items():
            if await self.set(key, value, ttl=ttl):
                count += 1
        return count

    async def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """
        Get multiple values at once.

        Args:
            keys: List of cache keys

        Returns:
            Dictionary of found key-value pairs
        """
        result = {}
        for key in keys:
            value = await self.get(key)
            if value is not None:
                result[key] = value
        return result

    async def touch(self, key: str, ttl: int) -> bool:
        """
        Update TTL for a key.

        Args:
            key: Cache key
            ttl: New TTL in seconds

        Returns:
            True if successful
        """
        await self.initialize()
        full_key = self._make_key(key)

        async with self._lock:
            # Try Redis
            if self._client and self._circuit_breaker.can_execute():
                try:
                    result = await self._client.expire(full_key, ttl)
                    self._circuit_breaker.record_success()
                    return result
                except Exception as e:
                    logger.debug(f"CacheManager: Redis touch failed: {e}")
                    self._circuit_breaker.record_failure()

            # Memory cache
            if full_key in self._memory_cache:
                entry = self._memory_cache[full_key]
                entry.ttl = ttl
                entry.created_at = datetime.now(timezone.utc)
                return True

            return False

    async def _remove_entry(self, full_key: str) -> None:
        """Remove entry from all indexes."""
        if full_key in self._memory_cache:
            entry = self._memory_cache[full_key]
            # Remove from tag indexes
            for tag in entry.tags:
                if tag in self._tag_index:
                    self._tag_index[tag].discard(full_key)
                    if not self._tag_index[tag]:
                        del self._tag_index[tag]
            del self._memory_cache[full_key]
            self._access_counts.pop(full_key, None)

    async def _ensure_memory_capacity(self, additional_bytes: int) -> None:
        """Ensure memory capacity by evicting entries if needed."""
        current_usage = sum(e.size_bytes for e in self._memory_cache.values())
        target_usage = current_usage + additional_bytes

        while target_usage > self.config.max_memory and self._memory_cache:
            await self._evict_one()
            current_usage = sum(e.size_bytes for e in self._memory_cache.values())
            target_usage = current_usage + additional_bytes

    async def _evict_one(self) -> Optional[str]:
        """Evict one entry based on eviction policy."""
        if not self._memory_cache:
            return None

        key_to_evict: Optional[str] = None

        if self.config.eviction_policy == "lru":
            # First item in OrderedDict is least recently used
            key_to_evict = next(iter(self._memory_cache))
        elif self.config.eviction_policy == "lfu":
            # Find least frequently used
            min_access = float("inf")
            for key in self._memory_cache:
                access_count = self._access_counts.get(key, 0)
                if access_count < min_access:
                    min_access = access_count
                    key_to_evict = key
        else:  # fifo
            # First item inserted ( OrderedDict maintains insertion order for new keys)
            key_to_evict = next(iter(self._memory_cache))

        if key_to_evict:
            await self._remove_entry(key_to_evict)
            self._stats.evictions += 1

        return key_to_evict

    def _update_memory_stats(self) -> None:
        """Update memory usage statistics."""
        self._stats.keys_count = len(self._memory_cache)
        self._stats.memory_usage = sum(e.size_bytes for e in self._memory_cache.values())


class CacheGateway:
    """
    High-level cache gateway for persona and memory caching.

    Provides domain-specific caching operations with circuit breaker protection.
    """

    def __init__(self, manager: Optional[CacheManager] = None, config: Optional[CacheConfig] = None):
        self.manager = manager or CacheManager(config)
        # Circuit breaker specifically for gateway operations
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=3,
            timeout_seconds=30.0
        )

    async def initialize(self) -> bool:
        """Initialize the underlying cache manager."""
        return await self.manager.initialize()

    async def close(self) -> None:
        """Close the underlying cache manager."""
        await self.manager.close()

    async def cache_persona(self, persona_id: str, data: Dict[str, Any], ttl: int = 300) -> bool:
        """
        Cache persona data.

        Args:
            persona_id: Persona identifier
            data: Persona data to cache
            ttl: Time-to-live in seconds (default 5 minutes)

        Returns:
            True if successful
        """
        key = f"persona:{persona_id}"
        tags = {"persona", f"persona:{persona_id}"}
        return await self.manager.set(key, data, ttl=ttl, tags=tags)

    async def get_cached_persona(self, persona_id: str) -> Optional[Dict[str, Any]]:
        """
        Get cached persona data.

        Args:
            persona_id: Persona identifier

        Returns:
            Cached persona data or None
        """
        key = f"persona:{persona_id}"
        return await self.manager.get(key)

    async def cache_memory(self, memory_id: str, data: Dict[str, Any], ttl: int = 600) -> bool:
        """
        Cache memory data.

        Args:
            memory_id: Memory identifier
            data: Memory data to cache
            ttl: Time-to-live in seconds (default 10 minutes)

        Returns:
            True if successful
        """
        key = f"memory:{memory_id}"
        tags = {"memory", f"memory:{memory_id}"}
        # Add persona tag if available
        if "persona_id" in data:
            tags.add(f"persona:{data["persona_id"]}")
        return await self.manager.set(key, data, ttl=ttl, tags=tags)

    async def get_cached_memory(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """
        Get cached memory data.

        Args:
            memory_id: Memory identifier

        Returns:
            Cached memory data or None
        """
        key = f"memory:{memory_id}"
        return await self.manager.get(key)

    async def invalidate_persona(self, persona_id: str) -> int:
        """
        Invalidate all cached data for a persona.

        Args:
            persona_id: Persona identifier

        Returns:
            Number of keys invalidated
        """
        # Delete direct persona cache
        count = 0
        if await self.manager.delete(f"persona:{persona_id}"):
            count += 1

        # Invalidate by tag
        count += await self.manager.invalidate_tag(f"persona:{persona_id}")

        return count

    async def invalidate_memory(self, memory_id: str) -> int:
        """
        Invalidate cached memory data.

        Args:
            memory_id: Memory identifier

        Returns:
            Number of keys invalidated
        """
        count = 0
        if await self.manager.delete(f"memory:{memory_id}"):
            count += 1

        count += await self.manager.invalidate_tag(f"memory:{memory_id}")

        return count

    async def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        return await self.manager.get_stats()

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on cache.

        Returns:
            Health status dictionary
        """
        stats = await self.get_stats()
        return {
            "status": "healthy" if stats.hit_rate >= 0.5 or stats.total_requests < 10 else "degraded",
            "backend": stats.backend.value,
            "hit_rate": round(stats.hit_rate, 2),
            "keys_count": stats.keys_count,
            "memory_usage_mb": round(stats.memory_usage / (1024 * 1024), 2),
            "evictions": stats.evictions,
            "circuit_breaker_state": self.manager._circuit_breaker.state.value
        }
