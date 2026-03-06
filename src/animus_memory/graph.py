"""
AnimusForge Memory System - Graph Store Implementation

Async graph store with Neo4j backend, in-memory fallback, circuit breaker pattern,
and knowledge graph operations for the AnimusForge cognitive architecture.
"""

import asyncio
import logging
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict

try:  # pragma: no cover
    from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
    from neo4j.exceptions import ServiceUnavailable, AuthError
    NEO4J_AVAILABLE = True
except ImportError:  # pragma: no cover
    NEO4J_AVAILABLE = False
    AsyncGraphDatabase = None
    AsyncDriver = None
    AsyncSession = None
    ServiceUnavailable = Exception
    AuthError = Exception

from enum import Enum
from .base import CircuitBreaker, CircuitState

logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS
# ============================================================================

class NodeType(str, Enum):
    """Node type classification for graph entities."""
    PERSONA = "persona"
    MEMORY = "memory"
    CONCEPT = "concept"
    EVENT = "event"
    ENTITY = "entity"


from enum import Enum


class RelationType(str, Enum):
    """Relationship types for graph edges."""
    REMEMBERS = "remembers"
    KNOWS = "knows"
    EXPERIENCED = "experienced"
    RELATED_TO = "related_to"
    CAUSED_BY = "caused_by"
    PART_OF = "part_of"
    SIMILAR_TO = "similar_to"


# ============================================================================
# MODELS
# ============================================================================

class GraphNode(BaseModel):
    """Represents a node in the knowledge graph."""
    
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        arbitrary_types_allowed=True
    )
    
    id: str = Field(default_factory=lambda: str(uuid4()))
    node_type: NodeType = Field(..., description="Type of graph node")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Node properties")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    @field_validator('properties')
    @classmethod
    def validate_properties(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure properties is a valid dict."""
        if not isinstance(v, dict):
            raise ValueError('properties must be a dictionary')
        return v


class GraphEdge(BaseModel):
    """Represents an edge/relationship in the knowledge graph."""
    
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        arbitrary_types_allowed=True
    )
    
    id: str = Field(default_factory=lambda: str(uuid4()))
    source_id: str = Field(..., min_length=1, description="Source node ID")
    target_id: str = Field(..., min_length=1, description="Target node ID")
    relation_type: RelationType = Field(..., description="Type of relationship")
    weight: float = Field(default=1.0, ge=0.0, le=10.0, description="Edge weight")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Edge properties")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    @model_validator(mode='after')
    def validate_source_target_different(self) -> 'GraphEdge':
        """Ensure source and target are different nodes."""
        if self.source_id == self.target_id:
            raise ValueError('source_id and target_id must be different')
        return self


class GraphPath(BaseModel):
    """Represents a path through the graph."""
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    nodes: List[GraphNode] = Field(default_factory=list, description="Nodes in the path")
    edges: List[GraphEdge] = Field(default_factory=list, description="Edges in the path")
    total_weight: float = Field(default=0.0, ge=0.0, description="Total path weight")
    
    @model_validator(mode='after')
    def validate_path_consistency(self) -> 'GraphPath':
        """Validate path has consistent nodes and edges."""
        if len(self.nodes) > 0 and len(self.edges) > 0:
            expected_edges = len(self.nodes) - 1
            if len(self.edges) != expected_edges:
                raise ValueError(f'Path with {len(self.nodes)} nodes should have {expected_edges} edges, got {len(self.edges)}')
        return self
    
    @property
    def length(self) -> int:
        """Number of hops in the path."""
        return len(self.edges)
    
    @property
    def is_valid(self) -> bool:
        """Check if path is valid (connected sequence)."""
        if len(self.nodes) < 2:
            return True
        
        for i, edge in enumerate(self.edges):
            if i < len(self.nodes) - 1:
                if edge.source_id != self.nodes[i].id or edge.target_id != self.nodes[i + 1].id:
                    return False
        return True


class GraphStoreConfig(BaseModel):
    """Configuration for Neo4j graph store."""
    
    model_config = ConfigDict(str_strip_whitespace=True)
    
    uri: str = Field(default="bolt://localhost:7687", description="Neo4j connection URI")
    username: str = Field(default="neo4j", description="Neo4j username")
    password: str = Field(..., min_length=1, description="Neo4j password")
    database: str = Field(default="neo4j", description="Database name")
    max_connection_lifetime: int = Field(default=3600, ge=60, description="Max connection lifetime in seconds")
    max_connection_pool_size: int = Field(default=50, ge=1, description="Max connection pool size")
    connection_timeout: float = Field(default=30.0, ge=1.0, description="Connection timeout in seconds")
    in_memory: bool = Field(default=False, description="Use in-memory mode for testing")


class GraphStats(BaseModel):
    """Statistics about graph storage."""
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    total_nodes: int = Field(default=0, ge=0)
    total_edges: int = Field(default=0, ge=0)
    persona_nodes: int = Field(default=0, ge=0)
    memory_nodes: int = Field(default=0, ge=0)
    concept_nodes: int = Field(default=0, ge=0)
    event_nodes: int = Field(default=0, ge=0)
    entity_nodes: int = Field(default=0, ge=0)
    avg_connections_per_node: float = Field(default=0.0, ge=0.0)


# ============================================================================
# CIRCUIT BREAKER DECORATOR
# ============================================================================

def circuit_protected(func):
    """Decorator to protect methods with circuit breaker."""
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        if not self._circuit_breaker.can_execute():
            raise ConnectionError(
                f"Circuit breaker is OPEN - graph store unavailable. "
                f"Failures: {self._circuit_breaker.failure_count}"
            )
        
        try:
            result = await func(self, *args, **kwargs)
            self._circuit_breaker.record_success()
            return result
        except Exception as e:
            self._circuit_breaker.record_failure()
            logger.error(f"GraphStore operation failed: {e}")
            raise
    
    return wrapper


# ============================================================================
# IN-MEMORY GRAPH STORE
# ============================================================================

class InMemoryGraphStore:
    """
    In-memory graph store for testing and development.
    Implements basic graph operations without external dependencies.
    """
    
    def __init__(self, config: GraphStoreConfig):
        self.config = config
        self._nodes: Dict[str, GraphNode] = {}
        self._edges: Dict[str, GraphEdge] = {}
        self._outgoing: Dict[str, List[str]] = {}  # node_id -> outgoing edge ids
        self._incoming: Dict[str, List[str]] = {}  # node_id -> incoming edge ids
        self._node_type_index: Dict[NodeType, Set[str]] = {t: set() for t in NodeType}
    
    async def create_node(self, node: GraphNode) -> str:
        """Store a node."""
        self._nodes[node.id] = node
        if node.id not in self._outgoing:
            self._outgoing[node.id] = []
        if node.id not in self._incoming:
            self._incoming[node.id] = []
        self._node_type_index[node.node_type].add(node.id)
        return node.id
    
    async def create_edge(self, edge: GraphEdge) -> str:
        """Store an edge."""
        # Verify nodes exist
        if edge.source_id not in self._nodes:
            raise ValueError(f"Source node {edge.source_id} does not exist")
        if edge.target_id not in self._nodes:
            raise ValueError(f"Target node {edge.target_id} does not exist")
        
        self._edges[edge.id] = edge
        self._outgoing[edge.source_id].append(edge.id)
        self._incoming[edge.target_id].append(edge.id)
        return edge.id
    
    async def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Retrieve a node by ID."""
        return self._nodes.get(node_id)
    
    async def get_edge(self, edge_id: str) -> Optional[GraphEdge]:
        """Retrieve an edge by ID."""
        return self._edges.get(edge_id)
    
    async def get_neighbors(
        self,
        node_id: str,
        relation_type: Optional[RelationType] = None,
        direction: str = "both"
    ) -> List[GraphNode]:
        """Get neighboring nodes."""
        if node_id not in self._nodes:
            return []
        
        neighbor_ids: Set[str] = set()
        
        if direction in ("out", "both"):
            for edge_id in self._outgoing.get(node_id, []):
                edge = self._edges.get(edge_id)
                if edge and (relation_type is None or edge.relation_type == relation_type):
                    neighbor_ids.add(edge.target_id)
        
        if direction in ("in", "both"):
            for edge_id in self._incoming.get(node_id, []):
                edge = self._edges.get(edge_id)
                if edge and (relation_type is None or edge.relation_type == relation_type):
                    neighbor_ids.add(edge.source_id)
        
        return [self._nodes[nid] for nid in neighbor_ids if nid in self._nodes]
    
    async def find_shortest_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5
    ) -> Optional[GraphPath]:
        """Find shortest path using BFS."""
        if source_id not in self._nodes or target_id not in self._nodes:
            return None
        
        if source_id == target_id:
            return GraphPath(nodes=[self._nodes[source_id]], edges=[], total_weight=0.0)
        
        # BFS for shortest path
        visited: Set[str] = {source_id}
        queue: List[Tuple[str, List[str], List[str], float]] = [(source_id, [source_id], [], 0.0)]
        
        while queue:
            current_id, path_ids, edge_ids, weight = queue.pop(0)
            
            if len(path_ids) > max_depth:
                continue
            
            for edge_id in self._outgoing.get(current_id, []):
                edge = self._edges.get(edge_id)
                if not edge:
                    continue
                
                next_id = edge.target_id
                if next_id in visited:
                    continue
                
                new_path = path_ids + [next_id]
                new_edges = edge_ids + [edge_id]
                new_weight = weight + edge.weight
                
                if next_id == target_id:
                    nodes = [self._nodes[nid] for nid in new_path if nid in self._nodes]
                    edges = [self._edges[eid] for eid in new_edges if eid in self._edges]
                    return GraphPath(nodes=nodes, edges=edges, total_weight=new_weight)
                
                visited.add(next_id)
                queue.append((next_id, new_path, new_edges, new_weight))
        
        return None
    
    async def delete_node(self, node_id: str) -> bool:
        """Delete a node and all its edges."""
        if node_id not in self._nodes:
            return False
        
        node = self._nodes[node_id]
        
        # Remove all edges
        edge_ids_to_remove = self._outgoing.get(node_id, []) + self._incoming.get(node_id, [])
        for edge_id in edge_ids_to_remove:
            if edge_id in self._edges:
                edge = self._edges[edge_id]
                # Update other node's indices
                if edge.source_id in self._outgoing and edge_id in self._outgoing[edge.source_id]:
                    self._outgoing[edge.source_id].remove(edge_id)
                if edge.target_id in self._incoming and edge_id in self._incoming[edge.target_id]:
                    self._incoming[edge.target_id].remove(edge_id)
                del self._edges[edge_id]
        
        # Remove node
        del self._nodes[node_id]
        self._outgoing.pop(node_id, None)
        self._incoming.pop(node_id, None)
        self._node_type_index[node.node_type].discard(node_id)
        
        return True
    
    async def delete_edge(self, edge_id: str) -> bool:
        """Delete an edge."""
        if edge_id not in self._edges:
            return False
        
        edge = self._edges[edge_id]
        
        if edge_id in self._outgoing.get(edge.source_id, []):
            self._outgoing[edge.source_id].remove(edge_id)
        if edge_id in self._incoming.get(edge.target_id, []):
            self._incoming[edge.target_id].remove(edge_id)
        
        del self._edges[edge_id]
        return True
    
    async def traverse(
        self,
        start_id: str,
        max_depth: int = 3,
        relation_types: Optional[List[RelationType]] = None
    ) -> List[GraphNode]:
        """Traverse graph from start node using BFS."""
        if start_id not in self._nodes:
            return []
        
        visited: Set[str] = {start_id}
        result: List[GraphNode] = [self._nodes[start_id]]
        queue: List[Tuple[str, int]] = [(start_id, 0)]
        
        while queue:
            current_id, depth = queue.pop(0)
            
            if depth >= max_depth:
                continue
            
            for edge_id in self._outgoing.get(current_id, []):
                edge = self._edges.get(edge_id)
                if not edge:
                    continue
                
                if relation_types and edge.relation_type not in relation_types:
                    continue
                
                next_id = edge.target_id
                if next_id not in visited:
                    visited.add(next_id)
                    if next_id in self._nodes:
                        result.append(self._nodes[next_id])
                    queue.append((next_id, depth + 1))
        
        return result
    
    async def get_nodes_by_type(self, node_type: NodeType) -> List[GraphNode]:
        """Get all nodes of a specific type."""
        return [self._nodes[nid] for nid in self._node_type_index[node_type] if nid in self._nodes]
    
    async def count(self) -> Tuple[int, int]:
        """Count nodes and edges."""
        return len(self._nodes), len(self._edges)
    
    async def clear(self) -> None:
        """Clear all data."""
        self._nodes.clear()
        self._edges.clear()
        self._outgoing.clear()
        self._incoming.clear()
        for t in NodeType:
            self._node_type_index[t] = set()


# ============================================================================
# NEO4J GRAPH STORE
# ============================================================================

class GraphStore:
    """
    Async graph store with Neo4j backend and in-memory fallback.
    
    Features:
    - Knowledge graph operations
    - Path finding algorithms
    - Circuit breaker for fault tolerance
    - In-memory fallback for testing
    """
    
    def __init__(
        self,
        config: GraphStoreConfig,
        circuit_breaker: Optional[CircuitBreaker] = None
    ):
        self.config = config
        self._circuit_breaker = circuit_breaker or CircuitBreaker(
            failure_threshold=5,
            timeout_seconds=60.0
        )
        self._driver: Optional[Any] = None
        self._in_memory_store: Optional[InMemoryGraphStore] = None
        self._initialized = False
        
        # Use in-memory mode if configured or Neo4j unavailable
        if config.in_memory or not NEO4J_AVAILABLE:
            self._in_memory_store = InMemoryGraphStore(config)
            logger.info("Using in-memory graph store")
    
    async def initialize(self) -> None:
        """Initialize the graph store connection."""
        if self._initialized:
            return
        
        if self._in_memory_store:
            self._initialized = True
            return
        
        # Neo4j initialization  # pragma: no cover
        try:  # pragma: no cover
            self._driver = AsyncGraphDatabase.driver(
                self.config.uri,
                auth=(self.config.username, self.config.password),
                max_connection_lifetime=self.config.max_connection_lifetime,
                max_connection_pool_size=self.config.max_connection_pool_size,
                connection_timeout=self.config.connection_timeout
            )
            
            # Verify connection
            await self._driver.verify_connectivity()
            self._initialized = True
            logger.info(f"GraphStore initialized with Neo4j at {self.config.uri}")
            
        except Exception as e:  # pragma: no cover
            logger.warning(f"Failed to connect to Neo4j, falling back to in-memory: {e}")
            self._in_memory_store = InMemoryGraphStore(self.config)
            self._initialized = True
    
    @circuit_protected
    async def create_node(self, node: GraphNode) -> str:
        """
        Create a node in the graph.
        
        Args:
            node: GraphNode to create
            
        Returns:
            The ID of the created node
        """
        await self.initialize()
        
        if self._in_memory_store:
            return await self._in_memory_store.create_node(node)
        
        # Neo4j creation  # pragma: no cover
        try:  # pragma: no cover
            async with self._driver.session(database=self.config.database) as session:
                query = f"""
                CREATE (n:{node.node_type.value} {{
                    id: $id,
                    created_at: datetime($created_at),
                    updated_at: datetime($updated_at)
                }})
                SET n += $properties
                RETURN n.id as id
                """
                
                result = await session.run(
                    query,
                    id=node.id,
                    created_at=node.created_at.isoformat(),
                    updated_at=node.updated_at.isoformat(),
                    properties=node.properties
                )
                
                record = await result.single()
                return record["id"] if record else node.id
                
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to create node: {e}")
            raise
    
    @circuit_protected
    async def create_edge(self, edge: GraphEdge) -> str:
        """
        Create an edge/relationship in the graph.
        
        Args:
            edge: GraphEdge to create
            
        Returns:
            The ID of the created edge
        """
        await self.initialize()
        
        if self._in_memory_store:
            return await self._in_memory_store.create_edge(edge)
        
        # Neo4j edge creation  # pragma: no cover
        try:  # pragma: no cover
            async with self._driver.session(database=self.config.database) as session:
                query = f"""
                MATCH (source {{id: $source_id}})
                MATCH (target {{id: $target_id}})
                CREATE (source)-[r:{edge.relation_type.value} {{
                    id: $id,
                    weight: $weight,
                    created_at: datetime($created_at)
                }}]->(target)
                SET r += $properties
                RETURN r.id as id
                """
                
                result = await session.run(
                    query,
                    id=edge.id,
                    source_id=edge.source_id,
                    target_id=edge.target_id,
                    weight=edge.weight,
                    created_at=edge.created_at.isoformat(),
                    properties=edge.properties
                )
                
                record = await result.single()
                return record["id"] if record else edge.id
                
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to create edge: {e}")
            raise
    
    @circuit_protected
    async def get_node(self, node_id: str) -> Optional[GraphNode]:
        """
        Retrieve a node by ID.
        
        Args:
            node_id: The node ID
            
        Returns:
            GraphNode if found, None otherwise
        """
        await self.initialize()
        
        if self._in_memory_store:
            return await self._in_memory_store.get_node(node_id)
        
        # Neo4j retrieval  # pragma: no cover
        try:  # pragma: no cover
            async with self._driver.session(database=self.config.database) as session:
                query = """
                MATCH (n {id: $id})
                RETURN n, labels(n) as labels
                """
                
                result = await session.run(query, id=node_id)
                record = await result.single()
                
                if record:
                    return self._record_to_node(record)
                return None
                
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to get node {node_id}: {e}")
            raise
    
    @circuit_protected
    async def get_neighbors(
        self,
        node_id: str,
        relation_type: Optional[RelationType] = None,
        direction: str = "both"
    ) -> List[GraphNode]:
        """
        Get neighboring nodes.
        
        Args:
            node_id: The node ID
            relation_type: Optional relation type filter
            direction: "in", "out", or "both"
            
        Returns:
            List of neighboring GraphNode objects
        """
        await self.initialize()
        
        if self._in_memory_store:
            return await self._in_memory_store.get_neighbors(node_id, relation_type, direction)
        
        # Neo4j neighbors  # pragma: no cover
        try:  # pragma: no cover
            async with self._driver.session(database=self.config.database) as session:
                rel_filter = f":{relation_type.value}" if relation_type else ""
                
                if direction == "out":
                    pattern = f"(n)-[r{rel_filter}]->(neighbor)"
                elif direction == "in":
                    pattern = f"(n)<-[r{rel_filter}]-(neighbor)"
                else:
                    pattern = f"(n)-[r{rel_filter}]-(neighbor)"
                
                query = f"""
                MATCH {pattern}
                WHERE n.id = $id
                RETURN DISTINCT neighbor, labels(neighbor) as labels
                """
                
                result = await session.run(query, id=node_id)
                records = await result.data()
                
                return [self._record_to_node({"n": r["neighbor"], "labels": r["labels"]}) for r in records]
                
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to get neighbors: {e}")
            raise
    
    @circuit_protected
    async def find_shortest_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5
    ) -> Optional[GraphPath]:
        """
        Find the shortest path between two nodes.
        
        Args:
            source_id: Source node ID
            target_id: Target node ID
            max_depth: Maximum path length
            
        Returns:
            GraphPath if found, None otherwise
        """
        await self.initialize()
        
        if self._in_memory_store:
            return await self._in_memory_store.find_shortest_path(source_id, target_id, max_depth)
        
        # Neo4j shortest path  # pragma: no cover
        try:  # pragma: no cover
            async with self._driver.session(database=self.config.database) as session:
                query = """
                MATCH (source {id: $source_id}), (target {id: $target_id})
                CALL apoc.algo.dijkstra(source, target, '', 'weight', 1.0, $max_depth) 
                YIELD path, weight
                RETURN path, weight
                LIMIT 1
                """
                
                result = await session.run(
                    query,
                    source_id=source_id,
                    target_id=target_id,
                    max_depth=max_depth
                )
                record = await result.single()
                
                if record:
                    return self._record_to_path(record)
                
                # Fallback to built-in if APOC not available
                query = """
                MATCH (source {id: $source_id}), (target {id: $target_id})
                MATCH path = shortestPath((source)-[*..{max_depth}]-(target))
                RETURN path
                LIMIT 1
                """
                
                result = await session.run(
                    query,
                    source_id=source_id,
                    target_id=target_id
                )
                record = await result.single()
                
                if record:
                    return self._record_to_path_simple(record)
                
                return None
                
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to find shortest path: {e}")
            raise
    
    @circuit_protected
    async def delete_node(self, node_id: str) -> bool:
        """
        Delete a node and all its relationships.
        
        Args:
            node_id: The node ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        await self.initialize()
        
        if self._in_memory_store:
            return await self._in_memory_store.delete_node(node_id)
        
        # Neo4j deletion  # pragma: no cover
        try:  # pragma: no cover
            async with self._driver.session(database=self.config.database) as session:
                query = """
                MATCH (n {id: $id})
                DETACH DELETE n
                RETURN count(n) as deleted
                """
                
                result = await session.run(query, id=node_id)
                record = await result.single()
                
                return record["deleted"] > 0 if record else False
                
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to delete node {node_id}: {e}")
            raise
    
    @circuit_protected
    async def delete_edge(self, edge_id: str) -> bool:
        """
        Delete an edge.
        
        Args:
            edge_id: The edge ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        await self.initialize()
        
        if self._in_memory_store:
            return await self._in_memory_store.delete_edge(edge_id)
        
        # Neo4j edge deletion  # pragma: no cover
        try:  # pragma: no cover
            async with self._driver.session(database=self.config.database) as session:
                query = """
                MATCH ()-[r {id: $id}]-()
                DELETE r
                RETURN count(r) as deleted
                """
                
                result = await session.run(query, id=edge_id)
                record = await result.single()
                
                return record["deleted"] > 0 if record else False
                
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to delete edge {edge_id}: {e}")
            raise
    
    @circuit_protected
    async def traverse(
        self,
        start_id: str,
        max_depth: int = 3,
        relation_types: Optional[List[RelationType]] = None
    ) -> List[GraphNode]:
        """
        Traverse graph from start node.
        
        Args:
            start_id: Starting node ID
            max_depth: Maximum traversal depth
            relation_types: Optional list of relation types to follow
            
        Returns:
            List of GraphNode objects in traversal order
        """
        await self.initialize()
        
        if self._in_memory_store:
            return await self._in_memory_store.traverse(start_id, max_depth, relation_types)
        
        # Neo4j traversal  # pragma: no cover
        try:  # pragma: no cover
            async with self._driver.session(database=self.config.database) as session:
                rel_filter = ""
                if relation_types:
                    rel_filter = ":" + "|".join(rt.value for rt in relation_types)
                
                query = f"""
                MATCH path = (start {{id: $id}})-[r{rel_filter}*1..{max_depth}]-(node)
                RETURN DISTINCT node, labels(node) as labels
                """
                
                result = await session.run(query, id=start_id)
                records = await result.data()
                
                nodes = [self._record_to_node({"n": r["node"], "labels": r["labels"]}) for r in records]
                
                # Include start node
                start_node = await self.get_node(start_id)
                if start_node:
                    nodes.insert(0, start_node)
                
                return nodes
                
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to traverse: {e}")
            raise
    
    async def get_stats(self) -> GraphStats:
        """Get statistics about the graph."""
        await self.initialize()
        
        if self._in_memory_store:
            total_nodes, total_edges = await self._in_memory_store.count()
            
            stats = GraphStats(
                total_nodes=total_nodes,
                total_edges=total_edges
            )
            
            for node_type in NodeType:
                nodes = await self._in_memory_store.get_nodes_by_type(node_type)
                if node_type == NodeType.PERSONA:
                    stats.persona_nodes = len(nodes)
                elif node_type == NodeType.MEMORY:
                    stats.memory_nodes = len(nodes)
                elif node_type == NodeType.CONCEPT:
                    stats.concept_nodes = len(nodes)
                elif node_type == NodeType.EVENT:
                    stats.event_nodes = len(nodes)
                elif node_type == NodeType.ENTITY:
                    stats.entity_nodes = len(nodes)
            
            if total_nodes > 0:
                stats.avg_connections_per_node = (total_edges * 2) / total_nodes
            
            return stats
        
        # Neo4j stats  # pragma: no cover
        try:  # pragma: no cover
            async with self._driver.session(database=self.config.database) as session:
                # Count nodes by type
                stats = GraphStats()
                
                for node_type in NodeType:
                    query = f"""
                    MATCH (n:{node_type.value})
                    RETURN count(n) as count
                    """
                    result = await session.run(query)
                    record = await result.single()
                    count = record["count"] if record else 0
                    
                    if node_type == NodeType.PERSONA:
                        stats.persona_nodes = count
                    elif node_type == NodeType.MEMORY:
                        stats.memory_nodes = count
                    elif node_type == NodeType.CONCEPT:
                        stats.concept_nodes = count
                    elif node_type == NodeType.EVENT:
                        stats.event_nodes = count
                    elif node_type == NodeType.ENTITY:
                        stats.entity_nodes = count
                
                stats.total_nodes = (
                    stats.persona_nodes + stats.memory_nodes + 
                    stats.concept_nodes + stats.event_nodes + stats.entity_nodes
                )
                
                # Count edges
                edge_query = "MATCH ()-[r]->() RETURN count(r) as count"
                result = await session.run(edge_query)
                record = await result.single()
                stats.total_edges = record["count"] if record else 0
                
                if stats.total_nodes > 0:
                    stats.avg_connections_per_node = (stats.total_edges * 2) / stats.total_nodes
                
                return stats
                
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to get stats: {e}")
            raise
    
    def _record_to_node(self, record: Dict[str, Any]) -> GraphNode:
        """Convert Neo4j record to GraphNode."""
        node_data = record.get("n", record.get("neighbor"))
        labels = record.get("labels", [])
        
        # Determine node type from labels
        node_type = NodeType.ENTITY  # Default
        for label in labels:
            try:
                node_type = NodeType(label.lower())
                break
            except ValueError:
                pass
        
        properties = dict(node_data) if node_data else {}
        
        # Extract known fields
        node_id = properties.pop("id", str(uuid4()))
        created_at = properties.pop("created_at", datetime.now(timezone.utc))
        updated_at = properties.pop("updated_at", datetime.now(timezone.utc))
        
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        
        return GraphNode(
            id=node_id,
            node_type=node_type,
            properties=properties,
            created_at=created_at,
            updated_at=updated_at
        )
    
    def _record_to_path(self, record: Dict[str, Any]) -> GraphPath:  # pragma: no cover
        """Convert Neo4j path record to GraphPath."""
        path = record.get("path")
        weight = record.get("weight", 0.0)
        
        nodes = []
        edges = []
        
        if path:
            for node in path.nodes:
                node_obj = self._record_to_node({"n": node, "labels": list(node.labels)})
                nodes.append(node_obj)
            
            for rel in path.relationships:
                edge = GraphEdge(
                    id=rel.get("id", str(uuid4())),
                    source_id=rel.start_node.get("id", ""),
                    target_id=rel.end_node.get("id", ""),
                    relation_type=RelationType(type(rel).__name__.lower()),
                    weight=rel.get("weight", 1.0),
                    properties={k: v for k, v in rel.items() if k not in ["id", "weight"]}
                )
                edges.append(edge)
        
        return GraphPath(nodes=nodes, edges=edges, total_weight=weight)
    
    def _record_to_path_simple(self, record: Dict[str, Any]) -> GraphPath:  # pragma: no cover
        """Convert simple Neo4j path record to GraphPath."""
        path = record.get("path")
        
        nodes = []
        edges = []
        total_weight = 0.0
        
        if path:
            for node in path.nodes:
                node_obj = self._record_to_node({"n": node, "labels": list(node.labels)})
                nodes.append(node_obj)
            
            for rel in path.relationships:
                weight = rel.get("weight", 1.0)
                edge = GraphEdge(
                    id=rel.get("id", str(uuid4())),
                    source_id=rel.start_node.get("id", ""),
                    target_id=rel.end_node.get("id", ""),
                    relation_type=RelationType(type(rel).__name__.lower()),
                    weight=weight,
                    properties={k: v for k, v in rel.items() if k not in ["id", "weight"]}
                )
                edges.append(edge)
                total_weight += weight
        
        return GraphPath(nodes=nodes, edges=edges, total_weight=total_weight)
    
    async def close(self) -> None:
        """Close the connection."""
        if self._driver:  # pragma: no cover
            await self._driver.close()


# ============================================================================
# GRAPH GATEWAY
# ============================================================================

class GraphGatewayConfig(BaseModel):
    """Configuration for GraphGateway."""
    
    model_config = ConfigDict(str_strip_whitespace=True)
    
    store_config: GraphStoreConfig = Field(default_factory=lambda: GraphStoreConfig(password="default"))
    max_path_depth: int = Field(default=5, ge=1, le=10, description="Maximum path depth for queries")
    default_traversal_depth: int = Field(default=3, ge=1, le=5, description="Default traversal depth")
    similarity_threshold: float = Field(default=0.5, ge=0.0, le=1.0, description="Similarity threshold")


class GraphGateway:
    """
    High-level gateway for graph operations with circuit breaker protection.
    
    Provides a stable API for knowledge graph operations with:
    - Concept relationship management
    - Knowledge graph retrieval
    - Circuit breaker protection
    - Statistics and monitoring
    """
    
    def __init__(
        self,
        config: Optional[GraphGatewayConfig] = None
    ):
        self.config = config or GraphGatewayConfig()
        self._store = GraphStore(
            self.config.store_config,
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
        logger.info("GraphGateway initialized")
    
    async def create_persona_node(self, persona_id: str, properties: Optional[Dict[str, Any]] = None) -> str:
        """
        Create a persona node.
        
        Args:
            persona_id: Persona ID
            properties: Optional node properties
            
        Returns:
            Node ID
        """
        await self.initialize()
        
        node = GraphNode(
            id=persona_id,
            node_type=NodeType.PERSONA,
            properties=properties or {}
        )
        return await self._store.create_node(node)
    
    async def create_memory_node(
        self,
        memory_id: str,
        persona_id: str,
        content: str,
        properties: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a memory node and link to persona.
        
        Args:
            memory_id: Memory ID
            persona_id: Owner persona ID
            content: Memory content
            properties: Optional node properties
            
        Returns:
            Node ID
        """
        await self.initialize()
        
        # Create memory node
        node = GraphNode(
            id=memory_id,
            node_type=NodeType.MEMORY,
            properties={"content": content, **(properties or {})}
        )
        await self._store.create_node(node)
        
        # Link to persona
        edge = GraphEdge(
            source_id=persona_id,
            target_id=memory_id,
            relation_type=RelationType.REMEMBERS
        )
        await self._store.create_edge(edge)
        
        return memory_id
    
    async def connect_concepts(
        self,
        persona_id: str,
        concept_a: str,
        concept_b: str,
        weight: float = 1.0
    ) -> str:
        """
        Connect two concepts in the knowledge graph.
        
        Args:
            persona_id: Owner persona ID
            concept_a: First concept
            concept_b: Second concept
            weight: Connection weight
            
        Returns:
            Edge ID
        """
        await self.initialize()
        
        # Create concept nodes if they don't exist
        for concept in [concept_a, concept_b]:
            existing = await self._store.get_node(concept)
            if not existing:
                node = GraphNode(
                    id=concept,
                    node_type=NodeType.CONCEPT,
                    properties={"name": concept}
                )
                await self._store.create_node(node)
                
                # Link to persona
                edge = GraphEdge(
                    source_id=persona_id,
                    target_id=concept,
                    relation_type=RelationType.KNOWS
                )
                await self._store.create_edge(edge)
        
        # Create concept-to-concept edge
        edge = GraphEdge(
            source_id=concept_a,
            target_id=concept_b,
            relation_type=RelationType.RELATED_TO,
            weight=weight
        )
        return await self._store.create_edge(edge)
    
    async def find_related_memories(
        self,
        persona_id: str,
        memory_id: str,
        max_depth: int = 2
    ) -> List[GraphNode]:
        """
        Find memories related to a given memory.
        
        Args:
            persona_id: Owner persona ID
            memory_id: Starting memory ID
            max_depth: Maximum traversal depth
            
        Returns:
            List of related memory nodes
        """
        await self.initialize()
        
        # Traverse from memory through RELATED_TO edges
        nodes = await self._store.traverse(
            memory_id,
            max_depth=max_depth,
            relation_types=[RelationType.RELATED_TO, RelationType.CAUSED_BY, RelationType.PART_OF]
        )
        
        # Filter to only memory nodes
        return [n for n in nodes if n.node_type == NodeType.MEMORY]
    
    async def get_persona_knowledge_graph(self, persona_id: str) -> Dict[str, Any]:
        """
        Get the complete knowledge graph for a persona.
        
        Args:
            persona_id: Persona ID
            
        Returns:
            Dictionary with nodes and edges
        """
        await self.initialize()
        
        # Traverse from persona node
        nodes = await self._store.traverse(
            persona_id,
            max_depth=self.config.default_traversal_depth
        )
        
        # Get all edges between these nodes
        node_ids = {n.id for n in nodes}
        edges = []
        
        for node in nodes:
            neighbors = await self._store.get_neighbors(node.id)
            for neighbor in neighbors:
                if neighbor.id in node_ids:
                    # Create edge representation
                    edges.append({
                        "source": node.id,
                        "target": neighbor.id,
                        "type": "connected"
                    })
        
        return {
            "persona_id": persona_id,
            "nodes": [
                {
                    "id": n.id,
                    "type": n.node_type.value,
                    "properties": n.properties
                }
                for n in nodes
            ],
            "edges": edges,
            "stats": {
                "node_count": len(nodes),
                "edge_count": len(edges)
            }
        }
    
    async def add_experience(
        self,
        persona_id: str,
        event_id: str,
        event_type: str,
        description: str,
        related_concepts: Optional[List[str]] = None
    ) -> str:
        """
        Add an experience/event to the knowledge graph.
        
        Args:
            persona_id: Persona ID
            event_id: Event ID
            event_type: Type of event
            description: Event description
            related_concepts: Optional list of related concept IDs
            
        Returns:
            Event node ID
        """
        await self.initialize()
        
        # Create event node
        node = GraphNode(
            id=event_id,
            node_type=NodeType.EVENT,
            properties={
                "event_type": event_type,
                "description": description
            }
        )
        await self._store.create_node(node)
        
        # Link to persona
        edge = GraphEdge(
            source_id=persona_id,
            target_id=event_id,
            relation_type=RelationType.EXPERIENCED
        )
        await self._store.create_edge(edge)
        
        # Link to related concepts (create them if they don't exist)
        if related_concepts:
            for concept_id in related_concepts:
                # Check if concept exists, create if not
                existing = await self._store.get_node(concept_id)
                if not existing:
                    concept_node = GraphNode(
                        id=concept_id,
                        node_type=NodeType.CONCEPT,
                        properties={"name": concept_id}
                    )
                    await self._store.create_node(concept_node)
                
                edge = GraphEdge(
                    source_id=event_id,
                    target_id=concept_id,
                    relation_type=RelationType.RELATED_TO
                )
                await self._store.create_edge(edge)
        
        return event_id
    
    async def find_path_between_concepts(
        self,
        concept_a: str,
        concept_b: str
    ) -> Optional[GraphPath]:
        """
        Find the shortest path between two concepts.
        
        Args:
            concept_a: First concept ID
            concept_b: Second concept ID
            
        Returns:
            GraphPath if found, None otherwise
        """
        await self.initialize()
        return await self._store.find_shortest_path(
            concept_a,
            concept_b,
            max_depth=self.config.max_path_depth
        )
    
    async def get_concept_cluster(self, concept_id: str, depth: int = 2) -> List[GraphNode]:
        """
        Get all concepts in a cluster around a concept.
        
        Args:
            concept_id: Center concept ID
            depth: Traversal depth
            
        Returns:
            List of related concept nodes
        """
        await self.initialize()
        
        nodes = await self._store.traverse(
            concept_id,
            max_depth=depth,
            relation_types=[RelationType.RELATED_TO, RelationType.SIMILAR_TO]
        )
        
        return [n for n in nodes if n.node_type == NodeType.CONCEPT]
    
    async def delete_persona_graph(self, persona_id: str) -> bool:
        """
        Delete all nodes and edges associated with a persona.
        
        Args:
            persona_id: Persona ID
            
        Returns:
            True if deleted
        """
        await self.initialize()
        
        # Get all nodes connected to persona
        nodes = await self._store.traverse(persona_id, max_depth=10)
        
        # Delete each node (this also deletes edges)
        for node in nodes:
            if node.id != persona_id:  # Delete persona last
                await self._store.delete_node(node.id)
        
        # Delete persona node
        return await self._store.delete_node(persona_id)
    
    async def get_stats(self) -> GraphStats:
        """Get graph statistics."""
        await self.initialize()
        return await self._store.get_stats()
    
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
