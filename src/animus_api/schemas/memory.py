"""Memory system schemas for vector and graph storage."""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field

from .base import BaseSchema, PaginatedResponse, UUIDMixin


class MemoryType(str, Enum):
    """Memory type enumeration."""
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    WORKING = "working"
    LONG_TERM = "long_term"


class VectorMetric(str, Enum):
    """Vector similarity metric."""
    COSINE = "cosine"
    EUCLIDEAN = "euclidean"
    DOT_PRODUCT = "dot_product"
    MANHATTAN = "manhattan"


class NodeType(str, Enum):
    """Graph node type."""
    ENTITY = "entity"
    CONCEPT = "concept"
    EVENT = "event"
    PERSONA = "persona"
    INTERACTION = "interaction"
    KNOWLEDGE = "knowledge"
    SKILL = "skill"
    CONTEXT = "context"


class RelationshipType(str, Enum):
    """Graph relationship type."""
    RELATES_TO = "relates_to"
    DERIVED_FROM = "derived_from"
    DEPENDS_ON = "depends_on"
    CAUSED_BY = "caused_by"
    FOLLOWS = "follows"
    PRECEDES = "precedes"
    CONTAINS = "contains"
    REFERENCES = "references"
    SIMILAR_TO = "similar_to"
    CONTRADICTS = "contradicts"
    SUPPORTS = "supports"


# ==================== Vector Memory Schemas ====================

class VectorStoreRequest(BaseSchema):
    """Request to store a vector."""
    persona_id: UUID = Field(description="Persona ID")
    content: str = Field(min_length=1, description="Content to store")
    memory_type: MemoryType = Field(default=MemoryType.SEMANTIC, description="Memory type")
    embedding: Optional[List[float]] = Field(default=None, description="Pre-computed embedding")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Vector metadata")
    tags: List[str] = Field(default_factory=list, description="Tags for retrieval")
    importance: float = Field(default=0.5, ge=0.0, le=1.0, description="Importance score")
    ttl_seconds: Optional[int] = Field(default=None, description="Time-to-live in seconds")


class VectorStoreResponse(BaseSchema):
    """Response after storing a vector."""
    id: UUID = Field(description="Vector ID")
    persona_id: UUID = Field(description="Persona ID")
    stored: bool = Field(description="Storage success")
    dimension: int = Field(description="Embedding dimension")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Storage timestamp")
    expires_at: Optional[datetime] = Field(default=None, description="Expiration timestamp")


class VectorSearchRequest(BaseSchema):
    """Request to search vectors."""
    persona_id: UUID = Field(description="Persona ID")
    query: str = Field(min_length=1, description="Search query")
    query_embedding: Optional[List[float]] = Field(default=None, description="Pre-computed query embedding")
    memory_types: Optional[List[MemoryType]] = Field(default=None, description="Filter by memory types")
    tags: Optional[List[str]] = Field(default=None, description="Filter by tags")
    metric: VectorMetric = Field(default=VectorMetric.COSINE, description="Similarity metric")
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results")
    min_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Minimum similarity score")
    include_content: bool = Field(default=True, description="Include content in results")
    include_metadata: bool = Field(default=True, description="Include metadata in results")


class VectorSearchResult(BaseSchema):
    """Single vector search result."""
    id: UUID = Field(description="Vector ID")
    score: float = Field(description="Similarity score")
    content: Optional[str] = Field(default=None, description="Vector content")
    memory_type: MemoryType = Field(description="Memory type")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Vector metadata")
    tags: List[str] = Field(default_factory=list, description="Tags")
    created_at: datetime = Field(description="Creation timestamp")


class VectorSearchResponse(BaseSchema):
    """Response for vector search."""
    results: List[VectorSearchResult] = Field(description="Search results")
    total: int = Field(description="Total matching vectors")
    query_time_ms: float = Field(description="Query time in milliseconds")
    persona_id: UUID = Field(description="Persona ID")


# ==================== Graph Memory Schemas ====================

class GraphNodeCreate(BaseSchema):
    """Request to create a graph node."""
    persona_id: UUID = Field(description="Persona ID")
    node_type: NodeType = Field(description="Node type")
    name: str = Field(min_length=1, max_length=200, description="Node name")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Node properties")
    content: Optional[str] = Field(default=None, description="Node content")
    embedding: Optional[List[float]] = Field(default=None, description="Node embedding")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score")
    source: Optional[str] = Field(default=None, description="Source of information")


class GraphNodeResponse(UUIDMixin):
    """Graph node response."""
    persona_id: UUID = Field(description="Persona ID")
    node_type: NodeType = Field(description="Node type")
    name: str = Field(description="Node name")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Node properties")
    content: Optional[str] = Field(default=None, description="Node content")
    confidence: float = Field(description="Confidence score")
    source: Optional[str] = Field(default=None, description="Source")
    edge_count: int = Field(default=0, description="Number of connected edges")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Update timestamp")


class GraphRelationshipCreate(BaseSchema):
    """Request to create a graph relationship."""
    persona_id: UUID = Field(description="Persona ID")
    source_id: UUID = Field(description="Source node ID")
    target_id: UUID = Field(description="Target node ID")
    relationship_type: RelationshipType = Field(description="Relationship type")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Relationship properties")
    weight: float = Field(default=1.0, ge=0.0, le=1.0, description="Relationship weight")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score")
    bidirectional: bool = Field(default=False, description="Create bidirectional relationship")


class GraphRelationshipResponse(UUIDMixin):
    """Graph relationship response."""
    persona_id: UUID = Field(description="Persona ID")
    source_id: UUID = Field(description="Source node ID")
    target_id: UUID = Field(description="Target node ID")
    relationship_type: RelationshipType = Field(description="Relationship type")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Relationship properties")
    weight: float = Field(description="Relationship weight")
    confidence: float = Field(description="Confidence score")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")


class GraphQueryRequest(BaseSchema):
    """Request to query the graph."""
    persona_id: UUID = Field(description="Persona ID")
    query_type: str = Field(description="Query type: cypher, traverse, pattern, neighbors")
    query: str = Field(min_length=1, description="Query string or pattern")
    start_node: Optional[UUID] = Field(default=None, description="Start node for traversal")
    max_depth: int = Field(default=3, ge=1, le=10, description="Maximum traversal depth")
    limit: int = Field(default=100, ge=1, le=1000, description="Result limit")
    node_types: Optional[List[NodeType]] = Field(default=None, description="Filter node types")
    relationship_types: Optional[List[RelationshipType]] = Field(default=None, description="Filter relationship types")
    include_properties: bool = Field(default=True, description="Include node/edge properties")


class GraphQueryNode(BaseSchema):
    """Node in query result."""
    id: UUID = Field(description="Node ID")
    node_type: NodeType = Field(description="Node type")
    name: str = Field(description="Node name")
    properties: Optional[Dict[str, Any]] = Field(default=None, description="Node properties")


class GraphQueryEdge(BaseSchema):
    """Edge in query result."""
    id: UUID = Field(description="Edge ID")
    source: UUID = Field(description="Source node ID")
    target: UUID = Field(description="Target node ID")
    relationship_type: RelationshipType = Field(description="Relationship type")
    properties: Optional[Dict[str, Any]] = Field(default=None, description="Edge properties")


class GraphQueryResponse(BaseSchema):
    """Response for graph query."""
    nodes: List[GraphQueryNode] = Field(description="Matching nodes")
    edges: List[GraphQueryEdge] = Field(description="Matching edges")
    total_nodes: int = Field(description="Total matching nodes")
    total_edges: int = Field(description="Total matching edges")
    query_time_ms: float = Field(description="Query time in milliseconds")
    persona_id: UUID = Field(description="Persona ID")
