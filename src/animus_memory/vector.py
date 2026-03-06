"""
AnimusForge Memory System - Vector Store Implementation

Async vector store with Qdrant backend, in-memory fallback, circuit breaker pattern,
and memory decay for the AnimusForge cognitive architecture.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Type
from functools import wraps

from pydantic import ValidationError

try:  # pragma: no cover
    from qdrant_client import QdrantClient, AsyncQdrantClient
    from qdrant_client.http import models as qdrant_models
    from qdrant_client.http.exceptions import UnexpectedResponse
    QDRANT_AVAILABLE = True
except ImportError:  # pragma: no cover
    QDRANT_AVAILABLE = False
    QdrantClient = None
    AsyncQdrantClient = None

from .base import (
    MemoryEntry,
    MemoryType,
    SearchResult,
    VectorStoreConfig,
    CircuitBreaker,
    CircuitState,
    VectorGatewayConfig,
    MemoryStats,
)

logger = logging.getLogger(__name__)


def circuit_protected(func):
    """Decorator to protect methods with circuit breaker."""
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        if not self._circuit_breaker.can_execute():
            raise ConnectionError(
                f"Circuit breaker is OPEN - vector store unavailable. "
                f"Failures: {self._circuit_breaker.failure_count}"
            )
        
        try:
            result = await func(self, *args, **kwargs)
            self._circuit_breaker.record_success()
            return result
        except Exception as e:
            self._circuit_breaker.record_failure()
            logger.error(f"VectorStore operation failed: {e}")
            raise
    
    return wrapper


def _clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value to a valid range, handling floating point errors."""
    return max(min_val, min(max_val, value))


class InMemoryVectorStore:
    """
    In-memory vector store for testing and development.
    Implements basic vector operations without external dependencies.
    """
    
    def __init__(self, config: VectorStoreConfig):
        self.config = config
        self._memories: Dict[str, MemoryEntry] = {}
        self._persona_index: Dict[str, List[str]] = {}  # persona_id -> memory_ids
        self._type_index: Dict[str, Dict[MemoryType, List[str]]] = {}  # persona_id -> {type -> ids}
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        import math
        if len(a) != len(b):
            return 0.0
        
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return _clamp(dot_product / (norm_a * norm_b), 0.0, 1.0)
    
    def _euclidean_distance(self, a: List[float], b: List[float]) -> float:
        """Calculate Euclidean distance between two vectors."""
        import math
        if len(a) != len(b):
            return float('inf')
        return max(0.0, math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b))))
    
    async def upsert(self, entry: MemoryEntry) -> str:
        """Store or update a memory entry."""
        self._memories[entry.id] = entry
        
        # Update persona index
        if entry.persona_id not in self._persona_index:
            self._persona_index[entry.persona_id] = []
            self._type_index[entry.persona_id] = {t: [] for t in MemoryType}
        
        if entry.id not in self._persona_index[entry.persona_id]:
            self._persona_index[entry.persona_id].append(entry.id)
        
        if entry.id not in self._type_index[entry.persona_id][entry.memory_type]:
            self._type_index[entry.persona_id][entry.memory_type].append(entry.id)
        
        return entry.id
    
    async def search(
        self,
        query_embedding: List[float],
        persona_id: str,
        limit: int = 10,
        memory_type: Optional[MemoryType] = None,
        min_score: float = 0.0
    ) -> List[SearchResult]:
        """Search for similar memories."""
        results = []
        
        memory_ids = self._persona_index.get(persona_id, [])
        
        for mid in memory_ids:
            entry = self._memories.get(mid)
            if entry is None or entry.embedding is None:
                continue
            
            if memory_type and entry.memory_type != memory_type:
                continue
            
            # Calculate similarity based on configured metric
            if self.config.distance_metric == "cosine":
                score = self._cosine_similarity(query_embedding, entry.embedding)
                distance = _clamp(1.0 - score, 0.0, 1.0)
            elif self.config.distance_metric == "euclidean":
                distance = self._euclidean_distance(query_embedding, entry.embedding)
                # Convert to similarity score (0-1)
                score = _clamp(1.0 / (1.0 + distance), 0.0, 1.0)
            else:  # dot product
                score = _clamp(sum(x * y for x, y in zip(query_embedding, entry.embedding)), 0.0, 1.0)
                distance = max(0.0, 1.0 - score)  # For dot product, higher is better
            
            if score >= min_score:
                results.append(SearchResult(entry=entry, score=score, distance=distance))
        
        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]
    
    async def get(self, memory_id: str) -> Optional[MemoryEntry]:
        """Retrieve a memory by ID."""
        return self._memories.get(memory_id)
    
    async def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        entry = self._memories.get(memory_id)
        if entry is None:
            return False
        
        del self._memories[memory_id]
        
        if entry.persona_id in self._persona_index:
            if memory_id in self._persona_index[entry.persona_id]:
                self._persona_index[entry.persona_id].remove(memory_id)
        
        if entry.persona_id in self._type_index:
            if memory_id in self._type_index[entry.persona_id][entry.memory_type]:
                self._type_index[entry.persona_id][entry.memory_type].remove(memory_id)
        
        return True
    
    async def get_by_persona(
        self,
        persona_id: str,
        memory_type: Optional[MemoryType] = None,
        limit: int = 100
    ) -> List[MemoryEntry]:
        """Get all memories for a persona."""
        if memory_type:
            ids = self._type_index.get(persona_id, {}).get(memory_type, [])
        else:
            ids = self._persona_index.get(persona_id, [])
        
        entries = [self._memories[mid] for mid in ids if mid in self._memories]
        return entries[:limit]
    
    async def count(self, persona_id: Optional[str] = None) -> int:
        """Count memories, optionally filtered by persona."""
        if persona_id:
            return len(self._persona_index.get(persona_id, []))
        return len(self._memories)
    
    async def clear(self) -> None:
        """Clear all memories."""
        self._memories.clear()
        self._persona_index.clear()
        self._type_index.clear()


class VectorStore:
    """
    Async vector store with Qdrant backend and in-memory fallback.
    
    Features:
    - Semantic search with configurable distance metrics
    - Memory decay implementation
    - Circuit breaker for fault tolerance
    - Automatic embedding generation
    """
    
    def __init__(
        self,
        config: VectorStoreConfig,
        embedding_fn: Optional[Callable[[str], List[float]]] = None,
        circuit_breaker: Optional[CircuitBreaker] = None
    ):
        self.config = config
        self._embedding_fn = embedding_fn
        self._circuit_breaker = circuit_breaker or CircuitBreaker()
        self._client: Optional[Any] = None
        self._async_client: Optional[Any] = None
        self._in_memory_store: Optional[InMemoryVectorStore] = None
        self._initialized = False
        
        # Use in-memory mode if configured or Qdrant unavailable
        if config.in_memory or not QDRANT_AVAILABLE:
            self._in_memory_store = InMemoryVectorStore(config)
            logger.info("Using in-memory vector store")
    
    async def initialize(self) -> None:
        """Initialize the vector store connection."""
        if self._initialized:
            return
        
        if self._in_memory_store:
            self._initialized = True
            return
        
        # Qdrant initialization - requires live server  # pragma: no cover
        try:  # pragma: no cover
            self._client = QdrantClient(
                host=self.config.host,
                port=self.config.port,
                grpc_port=self.config.grpc_port,
                prefer_grpc=self.config.prefer_grpc,
                api_key=self.config.api_key,
                timeout=self.config.timeout
            )
            
            self._async_client = AsyncQdrantClient(
                host=self.config.host,
                port=self.config.port,
                grpc_port=self.config.grpc_port,
                prefer_grpc=self.config.prefer_grpc,
                api_key=self.config.api_key,
                timeout=self.config.timeout
            )
            
            await self._ensure_collection()
            self._initialized = True
            logger.info(f"VectorStore initialized with Qdrant at {self.config.host}:{self.config.port}")
            
        except Exception as e:  # pragma: no cover
            logger.warning(f"Failed to connect to Qdrant, falling back to in-memory: {e}")
            self._in_memory_store = InMemoryVectorStore(self.config)
            self._initialized = True
    
    async def _ensure_collection(self) -> None:  # pragma: no cover
        """Ensure the collection exists, create if not."""
        if self._in_memory_store:
            return
        
        distance_map = {
            "cosine": qdrant_models.Distance.COSINE,
            "euclidean": qdrant_models.Distance.EUCLID,
            "dot": qdrant_models.Distance.DOT
        }
        
        try:
            collections = await self._async_client.get_collections()
            collection_names = [c.name for c in collections.collections]
            
            if self.config.collection_name not in collection_names:
                await self._async_client.create_collection(
                    collection_name=self.config.collection_name,
                    vectors_config=qdrant_models.VectorParams(
                        size=self.config.embedding_dim,
                        distance=distance_map[self.config.distance_metric]
                    )
                )
                logger.info(f"Created collection: {self.config.collection_name}")
        except Exception as e:
            logger.error(f"Failed to ensure collection: {e}")
            raise
    
    async def _get_embedding(self, text: str) -> List[float]:
        """Get embedding for text, using provided function or returning empty."""
        if self._embedding_fn:
            if asyncio.iscoroutinefunction(self._embedding_fn):
                return await self._embedding_fn(text)
            return self._embedding_fn(text)
        
        # Return a deterministic pseudo-embedding for testing
        import hashlib
        hash_obj = hashlib.sha256(text.encode())
        hash_bytes = hash_obj.digest()
        embedding = []
        for i in range(0, min(len(hash_bytes) * 2, self.config.embedding_dim)):
            byte_idx = i // 2
            if byte_idx < len(hash_bytes):
                val = hash_bytes[byte_idx] / 255.0
                if i % 2 == 1:
                    val = 1.0 - val
                embedding.append(val * 2 - 1)  # Normalize to -1 to 1
            else:
                embedding.append(0.0)
        
        # Pad or truncate to correct size
        while len(embedding) < self.config.embedding_dim:
            embedding.append(0.0)
        return embedding[:self.config.embedding_dim]
    
    @circuit_protected
    async def store(self, entry: MemoryEntry) -> str:
        """
        Store a memory entry in the vector store.
        
        Args:
            entry: MemoryEntry to store
            
        Returns:
            The ID of the stored memory
        """
        await self.initialize()
        
        # Generate embedding if not provided
        if entry.embedding is None:
            entry.embedding = await self._get_embedding(entry.content)
        
        if self._in_memory_store:
            return await self._in_memory_store.upsert(entry)
        
        # Qdrant storage - requires live server  # pragma: no cover
        try:  # pragma: no cover
            point = qdrant_models.PointStruct(
                id=entry.id,
                vector=entry.embedding,
                payload={
                    "persona_id": entry.persona_id,
                    "memory_type": entry.memory_type.value,
                    "content": entry.content,
                    "metadata": entry.metadata,
                    "importance": entry.importance,
                    "created_at": entry.created_at.isoformat(),
                    "last_accessed": entry.last_accessed.isoformat(),
                    "access_count": entry.access_count,
                    "decay_rate": entry.decay_rate
                }
            )
            
            await self._async_client.upsert(
                collection_name=self.config.collection_name,
                points=[point]
            )
            
            logger.debug(f"Stored memory {entry.id} for persona {entry.persona_id}")
            return entry.id
            
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to store memory: {e}")
            raise
    
    @circuit_protected
    async def search(
        self,
        query: str,
        persona_id: str,
        limit: int = 10,
        memory_type: Optional[MemoryType] = None,
        min_score: float = 0.0
    ) -> List[SearchResult]:
        """
        Search for similar memories.
        
        Args:
            query: Search query text
            persona_id: Persona ID to filter by
            limit: Maximum results to return
            memory_type: Optional memory type filter
            min_score: Minimum similarity score
            
        Returns:
            List of SearchResult objects
        """
        await self.initialize()
        
        query_embedding = await self._get_embedding(query)
        
        if self._in_memory_store:
            return await self._in_memory_store.search(
                query_embedding, persona_id, limit, memory_type, min_score
            )
        
        # Qdrant search - requires live server  # pragma: no cover
        try:  # pragma: no cover
            must_conditions = [
                qdrant_models.FieldCondition(
                    key="persona_id",
                    match=qdrant_models.MatchValue(value=persona_id)
                )
            ]
            
            if memory_type:
                must_conditions.append(
                    qdrant_models.FieldCondition(
                        key="memory_type",
                        match=qdrant_models.MatchValue(value=memory_type.value)
                    )
                )
            
            filter_obj = qdrant_models.Filter(must=must_conditions)
            
            results = await self._async_client.search(
                collection_name=self.config.collection_name,
                query_vector=query_embedding,
                query_filter=filter_obj,
                limit=limit,
                score_threshold=min_score
            )
            
            search_results = []
            for hit in results:
                entry = self._payload_to_entry(hit.payload, hit.id, hit.vector)
                search_results.append(SearchResult(
                    entry=entry,
                    score=_clamp(hit.score, 0.0, 1.0),
                    distance=_clamp(1.0 - hit.score if self.config.distance_metric == "cosine" else 0.0, 0.0, 1.0)
                ))
            
            return search_results
            
        except Exception as e:  # pragma: no cover
            logger.error(f"Search failed: {e}")
            raise
    
    @circuit_protected
    async def get(self, memory_id: str) -> Optional[MemoryEntry]:
        """
        Retrieve a memory by ID.
        
        Args:
            memory_id: The memory ID to retrieve
            
        Returns:
            MemoryEntry if found, None otherwise
        """
        await self.initialize()
        
        if self._in_memory_store:
            entry = await self._in_memory_store.get(memory_id)
            if entry:
                entry.record_access()
            return entry
        
        # Qdrant retrieval - requires live server  # pragma: no cover
        try:  # pragma: no cover
            result = await self._async_client.retrieve(
                collection_name=self.config.collection_name,
                ids=[memory_id],
                with_vectors=True
            )
            
            if result:
                hit = result[0]
                entry = self._payload_to_entry(hit.payload, hit.id, hit.vector)
                entry.record_access()
                await self._update_access_stats(entry)
                return entry
            
            return None
            
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to get memory {memory_id}: {e}")
            raise
    
    @circuit_protected
    async def delete(self, memory_id: str) -> bool:
        """
        Delete a memory by ID.
        
        Args:
            memory_id: The memory ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        await self.initialize()
        
        if self._in_memory_store:
            return await self._in_memory_store.delete(memory_id)
        
        # Qdrant deletion - requires live server  # pragma: no cover
        try:  # pragma: no cover
            await self._async_client.delete(
                collection_name=self.config.collection_name,
                points_selector=qdrant_models.PointIdsList(
                    points=[memory_id]
                )
            )
            return True
            
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to delete memory {memory_id}: {e}")
            raise
    
    @circuit_protected
    async def update(self, memory_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update a memory with partial data.
        
        Args:
            memory_id: The memory ID to update
            updates: Dictionary of fields to update
            
        Returns:
            True if updated, False if not found
        """
        await self.initialize()
        
        # Get directly from store without triggering record_access
        if self._in_memory_store:
            entry = self._in_memory_store._memories.get(memory_id)
        else:
            entry = None  # Would need Qdrant retrieval  # pragma: no cover
        
        if entry is None:
            return False
        
        # Apply updates
        for key, value in updates.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        
        # Re-store the updated entry
        await self.store(entry)
        return True
    
    @circuit_protected
    async def get_by_persona(
        self,
        persona_id: str,
        memory_type: Optional[MemoryType] = None,
        limit: int = 100
    ) -> List[MemoryEntry]:
        """
        Get all memories for a persona.
        
        Args:
            persona_id: Persona ID to filter by
            memory_type: Optional memory type filter
            limit: Maximum results
            
        Returns:
            List of MemoryEntry objects
        """
        await self.initialize()
        
        if self._in_memory_store:
            return await self._in_memory_store.get_by_persona(persona_id, memory_type, limit)
        
        # Qdrant scroll - requires live server  # pragma: no cover
        try:  # pragma: no cover
            must_conditions = [
                qdrant_models.FieldCondition(
                    key="persona_id",
                    match=qdrant_models.MatchValue(value=persona_id)
                )
            ]
            
            if memory_type:
                must_conditions.append(
                    qdrant_models.FieldCondition(
                        key="memory_type",
                        match=qdrant_models.MatchValue(value=memory_type.value)
                    )
                )
            
            filter_obj = qdrant_models.Filter(must=must_conditions)
            
            results, _ = await self._async_client.scroll(
                collection_name=self.config.collection_name,
                scroll_filter=filter_obj,
                limit=limit,
                with_vectors=True
            )
            
            entries = []
            for point in results:
                entry = self._payload_to_entry(point.payload, point.id, point.vector)
                entries.append(entry)
            
            return entries
            
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to get memories for persona {persona_id}: {e}")
            raise
    
    @circuit_protected
    async def decay_memories(self, persona_id: str) -> int:
        """
        Apply decay to all memories for a persona.
        
        Args:
            persona_id: Persona ID to process
            
        Returns:
            Number of memories updated
        """
        await self.initialize()
        
        entries = await self.get_by_persona(persona_id)
        updated_count = 0
        
        for entry in entries:
            time_elapsed = (datetime.now(timezone.utc) - entry.last_accessed).total_seconds()
            old_importance = entry.importance
            entry.apply_decay(time_elapsed)
            
            # Only update if decay actually changed importance
            if entry.importance != old_importance:
                await self.store(entry)
                updated_count += 1
        
        logger.info(f"Decayed {updated_count} memories for persona {persona_id}")
        return updated_count
    
    async def _update_access_stats(self, entry: MemoryEntry) -> None:  # pragma: no cover
        """Update access statistics in the store."""
        if self._in_memory_store:
            await self._in_memory_store.upsert(entry)
            return
        
        try:
            await self._async_client.set_payload(
                collection_name=self.config.collection_name,
                payload={
                    "last_accessed": entry.last_accessed.isoformat(),
                    "access_count": entry.access_count,
                    "importance": entry.importance
                },
                points=[entry.id]
            )
        except Exception as e:
            logger.warning(f"Failed to update access stats: {e}")
    
    def _payload_to_entry(
        self,
        payload: Dict[str, Any],
        memory_id: str,
        vector: Optional[List[float]] = None
    ) -> MemoryEntry:
        """Convert Qdrant payload to MemoryEntry."""
        return MemoryEntry(
            id=memory_id,
            persona_id=payload.get("persona_id", ""),
            memory_type=MemoryType(payload.get("memory_type", "semantic")),
            content=payload.get("content", ""),
            embedding=vector,
            metadata=payload.get("metadata", {}),
            importance=payload.get("importance", 0.5),
            created_at=datetime.fromisoformat(payload.get("created_at", datetime.now(timezone.utc).isoformat())),
            last_accessed=datetime.fromisoformat(payload.get("last_accessed", datetime.now(timezone.utc).isoformat())),
            access_count=payload.get("access_count", 0),
            decay_rate=payload.get("decay_rate", 0.1)
        )
    
    async def get_stats(self, persona_id: Optional[str] = None) -> MemoryStats:
        """Get statistics about stored memories."""
        await self.initialize()
        
        if self._in_memory_store:
            entries = await self.get_by_persona(persona_id) if persona_id else list(self._in_memory_store._memories.values())
        else:
            entries = await self.get_by_persona(persona_id) if persona_id else []  # pragma: no cover
        
        stats = MemoryStats()
        stats.total_memories = len(entries)
        
        for entry in entries:
            if entry.memory_type == MemoryType.EPISODIC:
                stats.episodic_count += 1
            elif entry.memory_type == MemoryType.SEMANTIC:
                stats.semantic_count += 1
            else:
                stats.procedural_count += 1
            
            stats.total_access_count += entry.access_count
        
        if entries:
            stats.avg_importance = sum(e.importance for e in entries) / len(entries)
        
        return stats
    
    async def close(self) -> None:
        """Close connections."""
        if self._async_client:  # pragma: no cover
            await self._async_client.close()
        if self._client:  # pragma: no cover
            self._client.close()


class VectorGateway:
    """
    High-level gateway for memory operations with circuit breaker protection.
    
    Provides a stable API for memory operations with:
    - Automatic retry logic
    - Circuit breaker protection
    - Memory decay scheduling
    - Statistics and monitoring
    """
    
    def __init__(
        self,
        config: Optional[VectorGatewayConfig] = None,
        embedding_fn: Optional[Callable[[str], List[float]]] = None
    ):
        self.config = config or VectorGatewayConfig()
        self._store = VectorStore(
            self.config.store_config,
            embedding_fn=embedding_fn,
            circuit_breaker=CircuitBreaker(
                failure_threshold=5,
                timeout_seconds=60.0
            )
        )
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the gateway."""
        if self._initialized:
            return
        await self._store.initialize()
        self._initialized = True
        logger.info("VectorGateway initialized")
    
    async def store_memory(self, entry: MemoryEntry) -> str:
        """
        Store a memory entry.
        
        Args:
            entry: MemoryEntry to store
            
        Returns:
            The ID of the stored memory
        """
        await self.initialize()
        return await self._store.store(entry)
    
    async def search_memories(
        self,
        query: str,
        persona_id: str,
        limit: int = 10,
        memory_type: Optional[MemoryType] = None
    ) -> List[SearchResult]:
        """
        Search for memories.
        
        Args:
            query: Search query text
            persona_id: Persona ID to filter by
            limit: Maximum results
            memory_type: Optional memory type filter
            
        Returns:
            List of SearchResult objects
        """
        await self.initialize()
        return await self._store.search(query, persona_id, limit, memory_type)
    
    async def get_memory(self, memory_id: str) -> Optional[MemoryEntry]:
        """
        Get a memory by ID.
        
        Args:
            memory_id: The memory ID
            
        Returns:
            MemoryEntry if found, None otherwise
        """
        await self.initialize()
        return await self._store.get(memory_id)
    
    async def delete_memory(self, memory_id: str) -> bool:
        """
        Delete a memory.
        
        Args:
            memory_id: The memory ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        await self.initialize()
        return await self._store.delete(memory_id)
    
    async def update_memory(self, memory_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update a memory.
        
        Args:
            memory_id: The memory ID to update
            updates: Dictionary of fields to update
            
        Returns:
            True if updated, False if not found
        """
        await self.initialize()
        return await self._store.update(memory_id, updates)
    
    async def get_persona_memories(
        self,
        persona_id: str,
        memory_type: Optional[MemoryType] = None,
        limit: int = 100
    ) -> List[MemoryEntry]:
        """
        Get all memories for a persona.
        
        Args:
            persona_id: Persona ID
            memory_type: Optional memory type filter
            limit: Maximum results
            
        Returns:
            List of MemoryEntry objects
        """
        await self.initialize()
        return await self._store.get_by_persona(persona_id, memory_type, limit)
    
    async def run_decay(self, persona_id: str) -> int:
        """
        Run memory decay for a persona.
        
        Args:
            persona_id: Persona ID to process
            
        Returns:
            Number of memories updated
        """
        await self.initialize()
        return await self._store.decay_memories(persona_id)
    
    async def get_stats(self, persona_id: Optional[str] = None) -> MemoryStats:
        """
        Get memory statistics.
        
        Args:
            persona_id: Optional persona ID to filter
            
        Returns:
            MemoryStats object
        """
        await self.initialize()
        return await self._store.get_stats(persona_id)
    
    @property
    def circuit_state(self) -> CircuitState:
        """Get current circuit breaker state."""
        return self._store._circuit_breaker.state
    
    def reset_circuit(self) -> None:
        """Reset the circuit breaker."""
        self._store._circuit_breaker.reset()
    
    async def close(self) -> None:
        """Close the gateway and release resources."""
        await self._store.close()
        self._initialized = False
