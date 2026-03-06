"""Memory System API Routes."""
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, status

from ..schemas.base import ErrorResponse
from ..schemas.memory import (
    GraphNodeCreate,
    GraphNodeResponse,
    GraphQueryEdge,
    GraphQueryNode,
    GraphQueryRequest,
    GraphQueryResponse,
    GraphRelationshipCreate,
    GraphRelationshipResponse,
    MemoryType,
    NodeType,
    RelationshipType,
    VectorMetric,
    VectorSearchRequest,
    VectorSearchResponse,
    VectorSearchResult,
    VectorStoreRequest,
    VectorStoreResponse,
)

router = APIRouter(prefix="/memory", tags=["Memory"])


# ==================== Vector Memory Store ====================

# In-memory vector store (replace with actual vector DB in production)
_vector_store: dict[UUID, dict] = {}


@router.post(
    "/vector/store",
    response_model=VectorStoreResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Store vector",
    description="Store a vector embedding with associated content and metadata.",
    responses={
        201: {"description": "Vector stored successfully"},
        400: {"model": ErrorResponse, "description": "Invalid vector data"},
    },
)
async def store_vector(request: VectorStoreRequest) -> VectorStoreResponse:
    """Store a vector in memory."""
    vector_id = uuid4()
    now = datetime.utcnow()

    # Determine embedding dimension
    dimension = len(request.embedding) if request.embedding else 1536  # Default to OpenAI dimension

    # Calculate expiration
    expires_at = None
    if request.ttl_seconds:
        expires_at = now + timedelta(seconds=request.ttl_seconds)

    # Store vector data
    _vector_store[vector_id] = {
        "persona_id": request.persona_id,
        "content": request.content,
        "embedding": request.embedding or [],
        "memory_type": request.memory_type,
        "metadata": request.metadata,
        "tags": request.tags,
        "importance": request.importance,
        "dimension": dimension,
        "created_at": now,
        "expires_at": expires_at,
    }

    return VectorStoreResponse(
        id=vector_id,
        persona_id=request.persona_id,
        stored=True,
        dimension=dimension,
        created_at=now,
        expires_at=expires_at,
    )


@router.post(
    "/vector/search",
    response_model=VectorSearchResponse,
    summary="Search vectors",
    description="Search for similar vectors using semantic similarity.",
    responses={
        200: {"description": "Search completed successfully"},
        400: {"model": ErrorResponse, "description": "Invalid search parameters"},
    },
)
async def search_vectors(request: VectorSearchRequest) -> VectorSearchResponse:
    """Search vectors by similarity."""
    import time
    import random

    start_time = time.time()

    # Filter by persona_id
    candidates = [
        (vid, data) for vid, data in _vector_store.items()
        if data["persona_id"] == request.persona_id
    ]

    # Filter by memory types if specified
    if request.memory_types:
        candidates = [
            (vid, data) for vid, data in candidates
            if data["memory_type"] in request.memory_types
        ]

    # Filter by tags if specified
    if request.tags:
        candidates = [
            (vid, data) for vid, data in candidates
            if any(tag in data["tags"] for tag in request.tags)
        ]

    # Simulate similarity scoring (replace with actual vector similarity in production)
    results = []
    for vid, data in candidates:
        # Simulated score based on importance
        score = data["importance"] * random.uniform(0.7, 1.0)

        if score >= request.min_score:
            results.append(VectorSearchResult(
                id=vid,
                score=score,
                content=data["content"] if request.include_content else None,
                memory_type=data["memory_type"],
                metadata=data["metadata"] if request.include_metadata else None,
                tags=data["tags"],
                created_at=data["created_at"],
            ))

    # Sort by score and limit
    results.sort(key=lambda r: r.score, reverse=True)
    results = results[:request.top_k]

    query_time_ms = (time.time() - start_time) * 1000

    return VectorSearchResponse(
        results=results,
        total=len(candidates),
        query_time_ms=query_time_ms,
        persona_id=request.persona_id,
    )


# ==================== Graph Memory Store ====================

# In-memory graph store (replace with Neo4j or similar in production)
_graph_nodes: dict[UUID, dict] = {}
_graph_edges: dict[UUID, dict] = {}


@router.post(
    "/graph/node",
    response_model=GraphNodeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create graph node",
    description="Create a new node in the knowledge graph.",
    responses={
        201: {"description": "Node created successfully"},
        400: {"model": ErrorResponse, "description": "Invalid node data"},
    },
)
async def create_graph_node(request: GraphNodeCreate) -> GraphNodeResponse:
    """Create a node in the knowledge graph."""
    node_id = uuid4()
    now = datetime.utcnow()

    _graph_nodes[node_id] = {
        "persona_id": request.persona_id,
        "node_type": request.node_type,
        "name": request.name,
        "properties": request.properties,
        "content": request.content,
        "embedding": request.embedding,
        "confidence": request.confidence,
        "source": request.source,
        "edge_count": 0,
        "created_at": now,
        "updated_at": now,
    }

    return GraphNodeResponse(
        id=node_id,
        persona_id=request.persona_id,
        node_type=request.node_type,
        name=request.name,
        properties=request.properties,
        content=request.content,
        confidence=request.confidence,
        source=request.source,
        edge_count=0,
        created_at=now,
        updated_at=now,
    )


@router.get(
    "/graph/node/{node_id}",
    response_model=GraphNodeResponse,
    summary="Get graph node",
    description="Retrieve a specific node from the knowledge graph.",
    responses={
        200: {"description": "Node retrieved successfully"},
        404: {"model": ErrorResponse, "description": "Node not found"},
    },
)
async def get_graph_node(node_id: UUID) -> GraphNodeResponse:
    """Get a specific graph node."""
    if node_id not in _graph_nodes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node {node_id} not found",
        )

    data = _graph_nodes[node_id]
    return GraphNodeResponse(id=node_id, **data)


@router.post(
    "/graph/relationship",
    response_model=GraphRelationshipResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create graph relationship",
    description="Create a relationship between two nodes in the knowledge graph.",
    responses={
        201: {"description": "Relationship created successfully"},
        400: {"model": ErrorResponse, "description": "Invalid relationship data"},
        404: {"model": ErrorResponse, "description": "Source or target node not found"},
    },
)
async def create_graph_relationship(
    request: GraphRelationshipCreate,
) -> GraphRelationshipResponse:
    """Create a relationship in the knowledge graph."""
    # Verify nodes exist
    if request.source_id not in _graph_nodes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source node {request.source_id} not found",
        )

    if request.target_id not in _graph_nodes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target node {request.target_id} not found",
        )

    edge_id = uuid4()
    now = datetime.utcnow()

    # Store edge
    _graph_edges[edge_id] = {
        "persona_id": request.persona_id,
        "source_id": request.source_id,
        "target_id": request.target_id,
        "relationship_type": request.relationship_type,
        "properties": request.properties,
        "weight": request.weight,
        "confidence": request.confidence,
        "created_at": now,
    }

    # Update node edge counts
    _graph_nodes[request.source_id]["edge_count"] += 1
    _graph_nodes[request.target_id]["edge_count"] += 1

    # Create bidirectional edge if requested
    if request.bidirectional:
        reverse_edge_id = uuid4()
        _graph_edges[reverse_edge_id] = {
            "persona_id": request.persona_id,
            "source_id": request.target_id,
            "target_id": request.source_id,
            "relationship_type": request.relationship_type,
            "properties": request.properties,
            "weight": request.weight,
            "confidence": request.confidence,
            "created_at": now,
        }

    return GraphRelationshipResponse(
        id=edge_id,
        persona_id=request.persona_id,
        source_id=request.source_id,
        target_id=request.target_id,
        relationship_type=request.relationship_type,
        properties=request.properties,
        weight=request.weight,
        confidence=request.confidence,
        created_at=now,
    )


@router.get(
    "/graph/query",
    response_model=GraphQueryResponse,
    summary="Query graph",
    description="Execute a query against the knowledge graph.",
)
async def query_graph(
    persona_id: UUID = Query(..., description="Persona ID"),
    query_type: str = Query("traverse", description="Query type: cypher, traverse, pattern, neighbors"),
    query: str = Query(..., description="Query string or pattern"),
    start_node: Optional[UUID] = Query(None, description="Start node for traversal"),
    max_depth: int = Query(3, ge=1, le=10, description="Maximum traversal depth"),
    limit: int = Query(100, ge=1, le=1000, description="Result limit"),
    include_properties: bool = Query(True, description="Include node/edge properties"),
) -> GraphQueryResponse:
    """Query the knowledge graph."""
    import time

    start_time = time.time()

    # Filter nodes by persona
    persona_nodes = {
        nid: data for nid, data in _graph_nodes.items()
        if data["persona_id"] == persona_id
    }

    persona_edges = {
        eid: data for eid, data in _graph_edges.items()
        if data["persona_id"] == persona_id
    }

    # Build response nodes
    nodes = []
    for nid, data in persona_nodes.items():
        nodes.append(GraphQueryNode(
            id=nid,
            node_type=data["node_type"],
            name=data["name"],
            properties=data["properties"] if include_properties else None,
        ))
        if len(nodes) >= limit:
            break

    # Build response edges
    edges = []
    for eid, data in persona_edges.items():
        edges.append(GraphQueryEdge(
            id=eid,
            source=data["source_id"],
            target=data["target_id"],
            relationship_type=data["relationship_type"],
            properties=data["properties"] if include_properties else None,
        ))
        if len(edges) >= limit:
            break

    query_time_ms = (time.time() - start_time) * 1000

    return GraphQueryResponse(
        nodes=nodes,
        edges=edges,
        total_nodes=len(persona_nodes),
        total_edges=len(persona_edges),
        query_time_ms=query_time_ms,
        persona_id=persona_id,
    )
