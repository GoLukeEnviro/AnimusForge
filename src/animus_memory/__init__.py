"""
AnimusForge Memory System

Comprehensive memory management with vector-based semantic memory,
graph-based knowledge storage, and Redis-backed caching.
"""

from .base import (
    MemoryType,
    MemoryEntry,
    SearchResult,
    VectorStoreConfig,
    CircuitBreaker,
    CircuitState,
    VectorGatewayConfig,
    MemoryStats,
)

from .vector import (
    VectorStore,
    VectorGateway,
    InMemoryVectorStore,
)

from .graph import (
    NodeType,
    RelationType,
    GraphNode,
    GraphEdge,
    GraphPath,
    GraphStoreConfig,
    GraphStats,
    GraphStore,
    GraphGateway,
    GraphGatewayConfig,
    InMemoryGraphStore,
)

from .cache import (
    CacheBackend,
    CacheEntry,
    CacheStats,
    CacheConfig,
    CacheManager,
    CacheGateway,
)

__all__ = [
    # Base
    "MemoryType",
    "MemoryEntry",
    "SearchResult",
    "VectorStoreConfig",
    "CircuitBreaker",
    "CircuitState",
    "VectorGatewayConfig",
    "MemoryStats",

    # Vector
    "VectorStore",
    "VectorGateway",
    "InMemoryVectorStore",

    # Graph
    "NodeType",
    "RelationType",
    "GraphNode",
    "GraphEdge",
    "GraphPath",
    "GraphStoreConfig",
    "GraphStats",
    "GraphStore",
    "GraphGateway",
    "GraphGatewayConfig",
    "InMemoryGraphStore",

    # Cache
    "CacheBackend",
    "CacheEntry",
    "CacheStats",
    "CacheConfig",
    "CacheManager",
    "CacheGateway",
]
