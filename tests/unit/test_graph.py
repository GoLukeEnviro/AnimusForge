"""
Unit tests for AnimusForge Graph Store Implementation

Comprehensive tests covering NodeType, RelationType, GraphNode, GraphEdge,
GraphPath, GraphStoreConfig, InMemoryGraphStore, GraphStore, and GraphGateway.
"""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List, Optional

from pydantic import ValidationError

from animus_memory.graph import (
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
    circuit_protected,
)
from animus_memory.base import CircuitBreaker, CircuitState


# ============================================================================
# ENUM TESTS
# ============================================================================

class TestNodeType:
    """Tests for NodeType enum."""
    
    def test_node_type_values(self):
        """Test all NodeType values are correct."""
        assert NodeType.PERSONA.value == "persona"
        assert NodeType.MEMORY.value == "memory"
        assert NodeType.CONCEPT.value == "concept"
        assert NodeType.EVENT.value == "event"
        assert NodeType.ENTITY.value == "entity"
    
    def test_node_type_count(self):
        """Test that we have 5 node types."""
        assert len(NodeType) == 5
    
    def test_node_type_string_conversion(self):
        """Test string conversion of NodeType."""
        assert NodeType.PERSONA.value == "persona"
        assert NodeType.MEMORY.value == "memory"
    
    def test_node_type_from_string(self):
        """Test creating NodeType from string."""
        assert NodeType("concept") == NodeType.CONCEPT
        assert NodeType("event") == NodeType.EVENT


class TestRelationType:
    """Tests for RelationType enum."""
    
    def test_relation_type_values(self):
        """Test all RelationType values are correct."""
        assert RelationType.REMEMBERS.value == "remembers"
        assert RelationType.KNOWS.value == "knows"
        assert RelationType.EXPERIENCED.value == "experienced"
        assert RelationType.RELATED_TO.value == "related_to"
        assert RelationType.CAUSED_BY.value == "caused_by"
        assert RelationType.PART_OF.value == "part_of"
        assert RelationType.SIMILAR_TO.value == "similar_to"
    
    def test_relation_type_count(self):
        """Test that we have 7 relation types."""
        assert len(RelationType) == 7
    
    def test_relation_type_from_string(self):
        """Test creating RelationType from string."""
        assert RelationType("remembers") == RelationType.REMEMBERS
        assert RelationType("caused_by") == RelationType.CAUSED_BY


# ============================================================================
# MODEL TESTS
# ============================================================================

class TestGraphNode:
    """Tests for GraphNode model."""
    
    def test_create_graph_node_minimal(self):
        """Test creating GraphNode with minimal fields."""
        node = GraphNode(node_type=NodeType.CONCEPT)
        
        assert node.id is not None
        assert node.node_type == NodeType.CONCEPT
        assert node.properties == {}
        assert isinstance(node.created_at, datetime)
        assert isinstance(node.updated_at, datetime)
    
    def test_create_graph_node_full(self):
        """Test creating GraphNode with all fields."""
        props = {"name": "test", "value": 42}
        node = GraphNode(
            id="custom-id",
            node_type=NodeType.MEMORY,
            properties=props
        )
        
        assert node.id == "custom-id"
        assert node.node_type == NodeType.MEMORY
        assert node.properties == props
    
    def test_graph_node_auto_timestamps(self):
        """Test that timestamps are auto-generated."""
        before = datetime.now(timezone.utc)
        node = GraphNode(node_type=NodeType.ENTITY)
        after = datetime.now(timezone.utc)
        
        assert before <= node.created_at <= after
        assert before <= node.updated_at <= after
    
    def test_graph_node_properties_validation(self):
        """Test that properties must be a dict."""
        node = GraphNode(node_type=NodeType.EVENT, properties={})
        assert node.properties == {}
        
        # Should work with complex properties
        props = {"list": [1, 2, 3], "nested": {"a": "b"}}
        node = GraphNode(node_type=NodeType.EVENT, properties=props)
        assert node.properties == props


class TestGraphEdge:
    """Tests for GraphEdge model."""
    
    def test_create_graph_edge_minimal(self):
        """Test creating GraphEdge with minimal fields."""
        edge = GraphEdge(
            source_id="source-1",
            target_id="target-1",
            relation_type=RelationType.RELATED_TO
        )
        
        assert edge.id is not None
        assert edge.source_id == "source-1"
        assert edge.target_id == "target-1"
        assert edge.relation_type == RelationType.RELATED_TO
        assert edge.weight == 1.0
        assert edge.properties == {}
    
    def test_create_graph_edge_with_weight(self):
        """Test creating GraphEdge with custom weight."""
        edge = GraphEdge(
            source_id="s",
            target_id="t",
            relation_type=RelationType.SIMILAR_TO,
            weight=5.5
        )
        
        assert edge.weight == 5.5
    
    def test_graph_edge_weight_validation(self):
        """Test edge weight must be between 0 and 10."""
        # Valid weights
        edge = GraphEdge(source_id="s", target_id="t", relation_type=RelationType.KNOWS, weight=0.0)
        assert edge.weight == 0.0
        
        edge = GraphEdge(source_id="s", target_id="t", relation_type=RelationType.KNOWS, weight=10.0)
        assert edge.weight == 10.0
        
        # Invalid weights
        with pytest.raises(ValidationError):
            GraphEdge(source_id="s", target_id="t", relation_type=RelationType.KNOWS, weight=-1.0)
        
        with pytest.raises(ValidationError):
            GraphEdge(source_id="s", target_id="t", relation_type=RelationType.KNOWS, weight=11.0)
    
    def test_graph_edge_source_target_different(self):
        """Test that source and target must be different."""
        with pytest.raises(ValidationError, match="source_id and target_id must be different"):
            GraphEdge(
                source_id="same",
                target_id="same",
                relation_type=RelationType.RELATED_TO
            )
    
    def test_graph_edge_empty_ids_validation(self):
        """Test that source and target IDs cannot be empty."""
        with pytest.raises(ValidationError):
            GraphEdge(source_id="", target_id="t", relation_type=RelationType.KNOWS)
        
        with pytest.raises(ValidationError):
            GraphEdge(source_id="s", target_id="", relation_type=RelationType.KNOWS)


class TestGraphPath:
    """Tests for GraphPath model."""
    
    def test_create_empty_path(self):
        """Test creating an empty path."""
        path = GraphPath()
        
        assert path.nodes == []
        assert path.edges == []
        assert path.total_weight == 0.0
        assert path.length == 0
        assert path.is_valid
    
    def test_create_single_node_path(self):
        """Test path with single node."""
        node = GraphNode(id="n1", node_type=NodeType.CONCEPT)
        path = GraphPath(nodes=[node], edges=[])
        
        assert len(path.nodes) == 1
        assert path.length == 0
        assert path.is_valid
    
    def test_create_valid_path(self):
        """Test creating a valid path with nodes and edges."""
        n1 = GraphNode(id="n1", node_type=NodeType.CONCEPT)
        n2 = GraphNode(id="n2", node_type=NodeType.CONCEPT)
        n3 = GraphNode(id="n3", node_type=NodeType.CONCEPT)
        
        e1 = GraphEdge(source_id="n1", target_id="n2", relation_type=RelationType.RELATED_TO)
        e2 = GraphEdge(source_id="n2", target_id="n3", relation_type=RelationType.RELATED_TO)
        
        path = GraphPath(nodes=[n1, n2, n3], edges=[e1, e2], total_weight=2.5)
        
        assert len(path.nodes) == 3
        assert path.length == 2
        assert path.total_weight == 2.5
    
    def test_path_validation_inconsistent_edges(self):
        """Test that path validates edge count."""
        n1 = GraphNode(id="n1", node_type=NodeType.CONCEPT)
        n2 = GraphNode(id="n2", node_type=NodeType.CONCEPT)
        
        # 2 nodes should have 1 edge - GraphPath with 0 edges and 2 nodes is valid
        # (validation only triggers when edges > 0 and doesn't match nodes-1)
        path = GraphPath(nodes=[n1, n2], edges=[])
        assert len(path.nodes) == 2
        assert len(path.edges) == 0
        
        # 2 nodes should have 1 edge, not 2
        e1 = GraphEdge(source_id="n1", target_id="n2", relation_type=RelationType.RELATED_TO)
        e2 = GraphEdge(source_id="n1", target_id="n2", relation_type=RelationType.RELATED_TO)
        
        with pytest.raises(ValidationError):
            GraphPath(nodes=[n1, n2], edges=[e1, e2])
    
    def test_path_is_valid_check(self):
        """Test path validity check."""
        n1 = GraphNode(id="n1", node_type=NodeType.CONCEPT)
        n2 = GraphNode(id="n2", node_type=NodeType.CONCEPT)
        e1 = GraphEdge(source_id="n1", target_id="n2", relation_type=RelationType.RELATED_TO)
        
        path = GraphPath(nodes=[n1, n2], edges=[e1])
        assert path.is_valid
        
        # Invalid path - edge doesn't connect properly
        e_wrong = GraphEdge(source_id="wrong", target_id="n2", relation_type=RelationType.RELATED_TO)
        path_invalid = GraphPath(nodes=[n1, n2], edges=[e_wrong])
        assert not path_invalid.is_valid


class TestGraphStoreConfig:
    """Tests for GraphStoreConfig model."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = GraphStoreConfig(password="test")
        
        assert config.uri == "bolt://localhost:7687"
        assert config.username == "neo4j"
        assert config.password == "test"
        assert config.database == "neo4j"
        assert config.max_connection_lifetime == 3600
        assert config.max_connection_pool_size == 50
        assert config.connection_timeout == 30.0
        assert config.in_memory == False
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = GraphStoreConfig(
            uri="bolt://custom:7687",
            username="custom_user",
            password="secret",
            database="test_db",
            in_memory=True
        )
        
        assert config.uri == "bolt://custom:7687"
        assert config.username == "custom_user"
        assert config.database == "test_db"
        assert config.in_memory == True
    
    def test_config_validation(self):
        """Test configuration validation."""
        # Password is required
        with pytest.raises(ValidationError):
            GraphStoreConfig()
        
        # Pool size must be >= 1
        with pytest.raises(ValidationError):
            GraphStoreConfig(password="test", max_connection_pool_size=0)
        
        # Timeout must be >= 1.0
        with pytest.raises(ValidationError):
            GraphStoreConfig(password="test", connection_timeout=0.5)


class TestGraphStats:
    """Tests for GraphStats model."""
    
    def test_default_stats(self):
        """Test default stats values."""
        stats = GraphStats()
        
        assert stats.total_nodes == 0
        assert stats.total_edges == 0
        assert stats.persona_nodes == 0
        assert stats.memory_nodes == 0
        assert stats.concept_nodes == 0
        assert stats.event_nodes == 0
        assert stats.entity_nodes == 0
        assert stats.avg_connections_per_node == 0.0
    
    def test_stats_with_values(self):
        """Test stats with custom values."""
        stats = GraphStats(
            total_nodes=100,
            total_edges=250,
            persona_nodes=10,
            memory_nodes=40,
            concept_nodes=30,
            event_nodes=15,
            entity_nodes=5,
            avg_connections_per_node=5.0
        )
        
        assert stats.total_nodes == 100
        assert stats.total_edges == 250
        assert stats.avg_connections_per_node == 5.0


# ============================================================================
# IN-MEMORY GRAPH STORE TESTS
# ============================================================================

class TestInMemoryGraphStore:
    """Tests for InMemoryGraphStore."""
    
    @pytest.fixture
    def store(self):
        """Create an in-memory store."""
        config = GraphStoreConfig(password="test", in_memory=True)
        return InMemoryGraphStore(config)
    
    @pytest.mark.asyncio
    async def test_create_and_get_node(self, store):
        """Test creating and retrieving a node."""
        node = GraphNode(id="test-node", node_type=NodeType.CONCEPT, properties={"name": "test"})
        
        node_id = await store.create_node(node)
        assert node_id == "test-node"
        
        retrieved = await store.get_node("test-node")
        assert retrieved is not None
        assert retrieved.id == "test-node"
        assert retrieved.node_type == NodeType.CONCEPT
        assert retrieved.properties == {"name": "test"}
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_node(self, store):
        """Test retrieving a non-existent node."""
        result = await store.get_node("nonexistent")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_create_edge(self, store):
        """Test creating an edge between nodes."""
        n1 = GraphNode(id="n1", node_type=NodeType.CONCEPT)
        n2 = GraphNode(id="n2", node_type=NodeType.CONCEPT)
        
        await store.create_node(n1)
        await store.create_node(n2)
        
        edge = GraphEdge(source_id="n1", target_id="n2", relation_type=RelationType.RELATED_TO)
        edge_id = await store.create_edge(edge)
        
        assert edge_id is not None
        
        retrieved = await store.get_edge(edge_id)
        assert retrieved is not None
        assert retrieved.source_id == "n1"
        assert retrieved.target_id == "n2"
    
    @pytest.mark.asyncio
    async def test_create_edge_nonexistent_node(self, store):
        """Test creating edge with non-existent node fails."""
        edge = GraphEdge(source_id="nonexistent", target_id="n2", relation_type=RelationType.RELATED_TO)
        
        with pytest.raises(ValueError, match="Source node .* does not exist"):
            await store.create_edge(edge)
    
    @pytest.mark.asyncio
    async def test_get_neighbors(self, store):
        """Test getting neighboring nodes."""
        # Create nodes
        n1 = GraphNode(id="center", node_type=NodeType.CONCEPT)
        n2 = GraphNode(id="neighbor1", node_type=NodeType.CONCEPT)
        n3 = GraphNode(id="neighbor2", node_type=NodeType.CONCEPT)
        
        await store.create_node(n1)
        await store.create_node(n2)
        await store.create_node(n3)
        
        # Create edges
        await store.create_edge(GraphEdge(source_id="center", target_id="neighbor1", relation_type=RelationType.RELATED_TO))
        await store.create_edge(GraphEdge(source_id="neighbor2", target_id="center", relation_type=RelationType.RELATED_TO))
        await store.create_edge(GraphEdge(source_id="center", target_id="neighbor2", relation_type=RelationType.KNOWS))
        
        # Get all neighbors
        neighbors = await store.get_neighbors("center")
        assert len(neighbors) == 2
        neighbor_ids = {n.id for n in neighbors}
        assert "neighbor1" in neighbor_ids
        assert "neighbor2" in neighbor_ids
    
    @pytest.mark.asyncio
    async def test_get_neighbors_filtered_by_type(self, store):
        """Test getting neighbors filtered by relation type."""
        n1 = GraphNode(id="center", node_type=NodeType.CONCEPT)
        n2 = GraphNode(id="related", node_type=NodeType.CONCEPT)
        n3 = GraphNode(id="known", node_type=NodeType.CONCEPT)
        
        await store.create_node(n1)
        await store.create_node(n2)
        await store.create_node(n3)
        
        await store.create_edge(GraphEdge(source_id="center", target_id="related", relation_type=RelationType.RELATED_TO))
        await store.create_edge(GraphEdge(source_id="center", target_id="known", relation_type=RelationType.KNOWS))
        
        # Filter by RELATED_TO
        neighbors = await store.get_neighbors("center", relation_type=RelationType.RELATED_TO)
        assert len(neighbors) == 1
        assert neighbors[0].id == "related"
        
        # Filter by KNOWS
        neighbors = await store.get_neighbors("center", relation_type=RelationType.KNOWS)
        assert len(neighbors) == 1
        assert neighbors[0].id == "known"
    
    @pytest.mark.asyncio
    async def test_get_neighbors_direction(self, store):
        """Test getting neighbors by direction."""
        n1 = GraphNode(id="center", node_type=NodeType.CONCEPT)
        n2 = GraphNode(id="outgoing", node_type=NodeType.CONCEPT)
        n3 = GraphNode(id="incoming", node_type=NodeType.CONCEPT)
        
        await store.create_node(n1)
        await store.create_node(n2)
        await store.create_node(n3)
        
        await store.create_edge(GraphEdge(source_id="center", target_id="outgoing", relation_type=RelationType.RELATED_TO))
        await store.create_edge(GraphEdge(source_id="incoming", target_id="center", relation_type=RelationType.RELATED_TO))
        
        # Outgoing only
        neighbors = await store.get_neighbors("center", direction="out")
        assert len(neighbors) == 1
        assert neighbors[0].id == "outgoing"
        
        # Incoming only
        neighbors = await store.get_neighbors("center", direction="in")
        assert len(neighbors) == 1
        assert neighbors[0].id == "incoming"
    
    @pytest.mark.asyncio
    async def test_find_shortest_path_direct(self, store):
        """Test finding direct path between nodes."""
        n1 = GraphNode(id="start", node_type=NodeType.CONCEPT)
        n2 = GraphNode(id="end", node_type=NodeType.CONCEPT)
        
        await store.create_node(n1)
        await store.create_node(n2)
        
        edge = GraphEdge(source_id="start", target_id="end", relation_type=RelationType.RELATED_TO, weight=2.0)
        await store.create_edge(edge)
        
        path = await store.find_shortest_path("start", "end")
        
        assert path is not None
        assert len(path.nodes) == 2
        assert len(path.edges) == 1
        assert path.total_weight == 2.0
    
    @pytest.mark.asyncio
    async def test_find_shortest_path_multi_hop(self, store):
        """Test finding multi-hop path."""
        # Create chain: start -> mid -> end
        n1 = GraphNode(id="start", node_type=NodeType.CONCEPT)
        n2 = GraphNode(id="mid", node_type=NodeType.CONCEPT)
        n3 = GraphNode(id="end", node_type=NodeType.CONCEPT)
        
        await store.create_node(n1)
        await store.create_node(n2)
        await store.create_node(n3)
        
        await store.create_edge(GraphEdge(source_id="start", target_id="mid", relation_type=RelationType.RELATED_TO, weight=1.0))
        await store.create_edge(GraphEdge(source_id="mid", target_id="end", relation_type=RelationType.RELATED_TO, weight=1.0))
        
        path = await store.find_shortest_path("start", "end")
        
        assert path is not None
        assert len(path.nodes) == 3
        assert path.length == 2
        assert path.total_weight == 2.0
    
    @pytest.mark.asyncio
    async def test_find_shortest_path_no_path(self, store):
        """Test when no path exists."""
        n1 = GraphNode(id="isolated1", node_type=NodeType.CONCEPT)
        n2 = GraphNode(id="isolated2", node_type=NodeType.CONCEPT)
        
        await store.create_node(n1)
        await store.create_node(n2)
        
        path = await store.find_shortest_path("isolated1", "isolated2")
        assert path is None
    
    @pytest.mark.asyncio
    async def test_find_shortest_path_same_node(self, store):
        """Test path from node to itself."""
        n1 = GraphNode(id="self", node_type=NodeType.CONCEPT)
        await store.create_node(n1)
        
        path = await store.find_shortest_path("self", "self")
        
        assert path is not None
        assert len(path.nodes) == 1
        assert path.length == 0
        assert path.total_weight == 0.0
    
    @pytest.mark.asyncio
    async def test_delete_node(self, store):
        """Test deleting a node."""
        n1 = GraphNode(id="to-delete", node_type=NodeType.CONCEPT)
        await store.create_node(n1)
        
        # Verify exists
        retrieved = await store.get_node("to-delete")
        assert retrieved is not None
        
        # Delete
        result = await store.delete_node("to-delete")
        assert result == True
        
        # Verify deleted
        retrieved = await store.get_node("to-delete")
        assert retrieved is None
    
    @pytest.mark.asyncio
    async def test_delete_node_with_edges(self, store):
        """Test deleting a node removes its edges."""
        n1 = GraphNode(id="n1", node_type=NodeType.CONCEPT)
        n2 = GraphNode(id="n2", node_type=NodeType.CONCEPT)
        n3 = GraphNode(id="n3", node_type=NodeType.CONCEPT)
        
        await store.create_node(n1)
        await store.create_node(n2)
        await store.create_node(n3)
        
        edge = GraphEdge(source_id="n1", target_id="n2", relation_type=RelationType.RELATED_TO)
        edge_id = await store.create_edge(edge)
        
        # Delete n1
        await store.delete_node("n1")
        
        # Edge should be gone
        retrieved_edge = await store.get_edge(edge_id)
        assert retrieved_edge is None
    
    @pytest.mark.asyncio
    async def test_delete_nonexistent_node(self, store):
        """Test deleting non-existent node returns False."""
        result = await store.delete_node("nonexistent")
        assert result == False
    
    @pytest.mark.asyncio
    async def test_delete_edge(self, store):
        """Test deleting an edge."""
        n1 = GraphNode(id="n1", node_type=NodeType.CONCEPT)
        n2 = GraphNode(id="n2", node_type=NodeType.CONCEPT)
        
        await store.create_node(n1)
        await store.create_node(n2)
        
        edge = GraphEdge(id="edge-1", source_id="n1", target_id="n2", relation_type=RelationType.RELATED_TO)
        await store.create_edge(edge)
        
        result = await store.delete_edge("edge-1")
        assert result == True
        
        retrieved = await store.get_edge("edge-1")
        assert retrieved is None
    
    @pytest.mark.asyncio
    async def test_traverse_bfs(self, store):
        """Test BFS traversal."""
        # Create a small graph
        #     n2
        #    /
        # n1 -- n3
        #    \
        #     n4
        
        nodes = [
            GraphNode(id=f"n{i}", node_type=NodeType.CONCEPT)
            for i in range(1, 5)
        ]
        
        for n in nodes:
            await store.create_node(n)
        
        await store.create_edge(GraphEdge(source_id="n1", target_id="n2", relation_type=RelationType.RELATED_TO))
        await store.create_edge(GraphEdge(source_id="n1", target_id="n3", relation_type=RelationType.RELATED_TO))
        await store.create_edge(GraphEdge(source_id="n1", target_id="n4", relation_type=RelationType.RELATED_TO))
        
        traversed = await store.traverse("n1", max_depth=1)
        
        assert len(traversed) == 4  # n1 + 3 neighbors
        node_ids = {n.id for n in traversed}
        assert "n1" in node_ids
    
    @pytest.mark.asyncio
    async def test_traverse_with_relation_filter(self, store):
        """Test traversal with relation type filter."""
        n1 = GraphNode(id="start", node_type=NodeType.CONCEPT)
        n2 = GraphNode(id="related", node_type=NodeType.CONCEPT)
        n3 = GraphNode(id="known", node_type=NodeType.CONCEPT)
        
        await store.create_node(n1)
        await store.create_node(n2)
        await store.create_node(n3)
        
        await store.create_edge(GraphEdge(source_id="start", target_id="related", relation_type=RelationType.RELATED_TO))
        await store.create_edge(GraphEdge(source_id="start", target_id="known", relation_type=RelationType.KNOWS))
        
        # Only traverse RELATED_TO
        traversed = await store.traverse("start", max_depth=1, relation_types=[RelationType.RELATED_TO])
        
        assert len(traversed) == 2  # start + related
        node_ids = {n.id for n in traversed}
        assert "known" not in node_ids
    
    @pytest.mark.asyncio
    async def test_get_nodes_by_type(self, store):
        """Test getting nodes by type."""
        concepts = [GraphNode(id=f"c{i}", node_type=NodeType.CONCEPT) for i in range(3)]
        memories = [GraphNode(id=f"m{i}", node_type=NodeType.MEMORY) for i in range(2)]
        
        for n in concepts + memories:
            await store.create_node(n)
        
        concept_nodes = await store.get_nodes_by_type(NodeType.CONCEPT)
        assert len(concept_nodes) == 3
        
        memory_nodes = await store.get_nodes_by_type(NodeType.MEMORY)
        assert len(memory_nodes) == 2
        
        event_nodes = await store.get_nodes_by_type(NodeType.EVENT)
        assert len(event_nodes) == 0
    
    @pytest.mark.asyncio
    async def test_count(self, store):
        """Test counting nodes and edges."""
        n1 = GraphNode(id="n1", node_type=NodeType.CONCEPT)
        n2 = GraphNode(id="n2", node_type=NodeType.CONCEPT)
        
        await store.create_node(n1)
        await store.create_node(n2)
        await store.create_edge(GraphEdge(source_id="n1", target_id="n2", relation_type=RelationType.RELATED_TO))
        
        node_count, edge_count = await store.count()
        assert node_count == 2
        assert edge_count == 1
    
    @pytest.mark.asyncio
    async def test_clear(self, store):
        """Test clearing all data."""
        n1 = GraphNode(id="n1", node_type=NodeType.CONCEPT)
        n2 = GraphNode(id="n2", node_type=NodeType.CONCEPT)
        
        await store.create_node(n1)
        await store.create_node(n2)
        await store.create_edge(GraphEdge(source_id="n1", target_id="n2", relation_type=RelationType.RELATED_TO))
        
        await store.clear()
        
        node_count, edge_count = await store.count()
        assert node_count == 0
        assert edge_count == 0


# ============================================================================
# GRAPH STORE TESTS
# ============================================================================

class TestGraphStore:
    """Tests for GraphStore class."""
    
    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return GraphStoreConfig(password="test", in_memory=True)
    
    @pytest.fixture
    def store(self, config):
        """Create a graph store."""
        return GraphStore(config)
    
    @pytest.mark.asyncio
    async def test_initialize(self, store):
        """Test store initialization."""
        await store.initialize()
        assert store._initialized == True
    
    @pytest.mark.asyncio
    async def test_create_node(self, store):
        """Test creating a node."""
        node = GraphNode(id="test", node_type=NodeType.CONCEPT)
        node_id = await store.create_node(node)
        
        assert node_id == "test"
    
    @pytest.mark.asyncio
    async def test_get_node(self, store):
        """Test retrieving a node."""
        node = GraphNode(id="test", node_type=NodeType.MEMORY, properties={"content": "test content"})
        await store.create_node(node)
        
        retrieved = await store.get_node("test")
        assert retrieved is not None
        assert retrieved.id == "test"
        assert retrieved.node_type == NodeType.MEMORY
        assert retrieved.properties["content"] == "test content"
    
    @pytest.mark.asyncio
    async def test_create_and_get_edge(self, store):
        """Test creating and retrieving an edge."""
        n1 = GraphNode(id="s", node_type=NodeType.CONCEPT)
        n2 = GraphNode(id="t", node_type=NodeType.CONCEPT)
        
        await store.create_node(n1)
        await store.create_node(n2)
        
        edge = GraphEdge(source_id="s", target_id="t", relation_type=RelationType.RELATED_TO, weight=3.0)
        edge_id = await store.create_edge(edge)
        
        assert edge_id is not None
    
    @pytest.mark.asyncio
    async def test_get_neighbors(self, store):
        """Test getting neighbors."""
        n1 = GraphNode(id="center", node_type=NodeType.CONCEPT)
        n2 = GraphNode(id="neighbor", node_type=NodeType.CONCEPT)
        
        await store.create_node(n1)
        await store.create_node(n2)
        await store.create_edge(GraphEdge(source_id="center", target_id="neighbor", relation_type=RelationType.RELATED_TO))
        
        neighbors = await store.get_neighbors("center")
        assert len(neighbors) == 1
        assert neighbors[0].id == "neighbor"
    
    @pytest.mark.asyncio
    async def test_find_shortest_path(self, store):
        """Test shortest path finding."""
        n1 = GraphNode(id="a", node_type=NodeType.CONCEPT)
        n2 = GraphNode(id="b", node_type=NodeType.CONCEPT)
        
        await store.create_node(n1)
        await store.create_node(n2)
        await store.create_edge(GraphEdge(source_id="a", target_id="b", relation_type=RelationType.RELATED_TO))
        
        path = await store.find_shortest_path("a", "b")
        
        assert path is not None
        assert len(path.nodes) == 2
    
    @pytest.mark.asyncio
    async def test_delete_node(self, store):
        """Test deleting a node."""
        node = GraphNode(id="delete-me", node_type=NodeType.EVENT)
        await store.create_node(node)
        
        result = await store.delete_node("delete-me")
        assert result == True
        
        retrieved = await store.get_node("delete-me")
        assert retrieved is None
    
    @pytest.mark.asyncio
    async def test_traverse(self, store):
        """Test graph traversal."""
        nodes = [GraphNode(id=f"n{i}", node_type=NodeType.CONCEPT) for i in range(3)]
        for n in nodes:
            await store.create_node(n)
        
        await store.create_edge(GraphEdge(source_id="n0", target_id="n1", relation_type=RelationType.RELATED_TO))
        await store.create_edge(GraphEdge(source_id="n1", target_id="n2", relation_type=RelationType.RELATED_TO))
        
        traversed = await store.traverse("n0", max_depth=2)
        assert len(traversed) == 3
    
    @pytest.mark.asyncio
    async def test_get_stats(self, store):
        """Test getting statistics."""
        n1 = GraphNode(id="p1", node_type=NodeType.PERSONA)
        n2 = GraphNode(id="m1", node_type=NodeType.MEMORY)
        n3 = GraphNode(id="c1", node_type=NodeType.CONCEPT)
        
        await store.create_node(n1)
        await store.create_node(n2)
        await store.create_node(n3)
        
        stats = await store.get_stats()
        
        assert stats.total_nodes == 3
        assert stats.persona_nodes == 1
        assert stats.memory_nodes == 1
        assert stats.concept_nodes == 1
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_protection(self, config):
        """Test circuit breaker protection."""
        cb = CircuitBreaker(failure_threshold=2)
        store = GraphStore(config, circuit_breaker=cb)
        
        # Manually open circuit
        cb.record_failure()
        cb.record_failure()
        
        assert cb.state == CircuitState.OPEN
        
        # Should fail with circuit open
        with pytest.raises(ConnectionError, match="Circuit breaker is OPEN"):
            await store.create_node(GraphNode(node_type=NodeType.CONCEPT))
    
    @pytest.mark.asyncio
    async def test_close(self, store):
        """Test closing the store."""
        await store.initialize()
        await store.close()  # Should not raise


# ============================================================================
# GRAPH GATEWAY TESTS
# ============================================================================

class TestGraphGateway:
    """Tests for GraphGateway class."""
    
    @pytest.fixture
    def gateway_config(self):
        """Create gateway configuration."""
        return GraphGatewayConfig(
            store_config=GraphStoreConfig(password="test", in_memory=True)
        )
    
    @pytest.fixture
    def gateway(self, gateway_config):
        """Create a graph gateway."""
        return GraphGateway(gateway_config)
    
    @pytest.mark.asyncio
    async def test_initialize(self, gateway):
        """Test gateway initialization."""
        await gateway.initialize()
        assert gateway._initialized == True
    
    @pytest.mark.asyncio
    async def test_create_persona_node(self, gateway):
        """Test creating a persona node."""
        node_id = await gateway.create_persona_node("persona-1", {"name": "Test"})
        assert node_id == "persona-1"
    
    @pytest.mark.asyncio
    async def test_create_memory_node(self, gateway):
        """Test creating a memory node linked to persona."""
        await gateway.create_persona_node("persona-1")
        
        memory_id = await gateway.create_memory_node(
            "memory-1",
            "persona-1",
            "Test memory content"
        )
        
        assert memory_id == "memory-1"
        
        # Verify link exists
        neighbors = await gateway._store.get_neighbors("persona-1")
        neighbor_ids = [n.id for n in neighbors]
        assert "memory-1" in neighbor_ids
    
    @pytest.mark.asyncio
    async def test_connect_concepts(self, gateway):
        """Test connecting two concepts."""
        await gateway.create_persona_node("p1")
        
        edge_id = await gateway.connect_concepts("p1", "concept-a", "concept-b", weight=2.5)
        assert edge_id is not None
        
        # Both concepts should exist
        ca = await gateway._store.get_node("concept-a")
        cb = await gateway._store.get_node("concept-b")
        
        assert ca is not None
        assert cb is not None
        assert ca.node_type == NodeType.CONCEPT
    
    @pytest.mark.asyncio
    async def test_find_related_memories(self, gateway):
        """Test finding related memories."""
        await gateway.create_persona_node("p1")
        await gateway.create_memory_node("m1", "p1", "Memory 1")
        await gateway.create_memory_node("m2", "p1", "Memory 2")
        
        # Connect memories
        await gateway._store.create_edge(
            GraphEdge(source_id="m1", target_id="m2", relation_type=RelationType.RELATED_TO)
        )
        
        related = await gateway.find_related_memories("p1", "m1")
        assert len(related) >= 1
    
    @pytest.mark.asyncio
    async def test_get_persona_knowledge_graph(self, gateway):
        """Test getting complete knowledge graph."""
        await gateway.create_persona_node("p1")
        await gateway.create_memory_node("m1", "p1", "Memory")
        await gateway.connect_concepts("p1", "c1", "c2")
        
        kg = await gateway.get_persona_knowledge_graph("p1")
        
        assert kg["persona_id"] == "p1"
        assert len(kg["nodes"]) >= 2
        assert "stats" in kg
        assert kg["stats"]["node_count"] >= 2
    
    @pytest.mark.asyncio
    async def test_add_experience(self, gateway):
        """Test adding an experience."""
        await gateway.create_persona_node("p1")
        
        event_id = await gateway.add_experience(
            "p1",
            "event-1",
            "learning",
            "Learned about graphs",
            related_concepts=["graph-theory"]
        )
        
        assert event_id == "event-1"
        
        # Verify event node
        event = await gateway._store.get_node("event-1")
        assert event is not None
        assert event.node_type == NodeType.EVENT
        assert event.properties["event_type"] == "learning"
    
    @pytest.mark.asyncio
    async def test_find_path_between_concepts(self, gateway):
        """Test finding path between concepts."""
        await gateway.create_persona_node("p1")
        await gateway.connect_concepts("p1", "a", "b")
        await gateway.connect_concepts("p1", "b", "c")
        
        path = await gateway.find_path_between_concepts("a", "c")
        
        assert path is not None
        assert len(path.nodes) == 3
    
    @pytest.mark.asyncio
    async def test_get_concept_cluster(self, gateway):
        """Test getting concept cluster."""
        await gateway.create_persona_node("p1")
        await gateway.connect_concepts("p1", "center", "c1")
        await gateway.connect_concepts("p1", "center", "c2")
        await gateway.connect_concepts("p1", "center", "c3")
        
        cluster = await gateway.get_concept_cluster("center", depth=1)
        
        assert len(cluster) >= 1
        # All should be concepts
        for node in cluster:
            assert node.node_type == NodeType.CONCEPT
    
    @pytest.mark.asyncio
    async def test_delete_persona_graph(self, gateway):
        """Test deleting entire persona graph."""
        await gateway.create_persona_node("p1")
        await gateway.create_memory_node("m1", "p1", "Memory")
        await gateway.connect_concepts("p1", "c1", "c2")
        
        result = await gateway.delete_persona_graph("p1")
        assert result == True
        
        # Verify deleted
        p1 = await gateway._store.get_node("p1")
        assert p1 is None
    
    @pytest.mark.asyncio
    async def test_get_stats(self, gateway):
        """Test getting gateway stats."""
        await gateway.create_persona_node("p1")
        await gateway.create_memory_node("m1", "p1", "Memory")
        
        stats = await gateway.get_stats()
        
        assert stats.total_nodes >= 2
    
    def test_circuit_state_property(self, gateway):
        """Test circuit state property."""
        assert gateway.circuit_state == CircuitState.CLOSED
    
    def test_reset_circuit(self, gateway):
        """Test resetting circuit breaker."""
        gateway._store._circuit_breaker.record_failure()
        gateway._store._circuit_breaker.record_failure()
        gateway._store._circuit_breaker.record_failure()
        gateway._store._circuit_breaker.record_failure()
        gateway._store._circuit_breaker.record_failure()
        
        gateway.reset_circuit()
        assert gateway.circuit_state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_close(self, gateway):
        """Test closing gateway."""
        await gateway.initialize()
        await gateway.close()
        assert gateway._initialized == False


class TestGraphGatewayConfig:
    """Tests for GraphGatewayConfig."""
    
    def test_default_config(self):
        """Test default gateway config."""
        config = GraphGatewayConfig()
        
        assert config.max_path_depth == 5
        assert config.default_traversal_depth == 3
        assert config.similarity_threshold == 0.5
    
    def test_custom_config(self):
        """Test custom gateway config."""
        config = GraphGatewayConfig(
            max_path_depth=10,
            default_traversal_depth=5,
            similarity_threshold=0.8
        )
        
        assert config.max_path_depth == 10
        assert config.default_traversal_depth == 5
        assert config.similarity_threshold == 0.8
    
    def test_config_validation(self):
        """Test config validation."""
        # max_path_depth bounds
        with pytest.raises(ValidationError):
            GraphGatewayConfig(max_path_depth=0)
        
        with pytest.raises(ValidationError):
            GraphGatewayConfig(max_path_depth=11)


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestGraphIntegration:
    """Integration tests for graph operations."""
    
    @pytest.fixture
    async def setup_graph(self):
        """Setup a complete graph for testing."""
        config = GraphGatewayConfig(
            store_config=GraphStoreConfig(password="test", in_memory=True)
        )
        gateway = GraphGateway(config)
        
        # Create persona
        await gateway.create_persona_node("user-1", {"name": "Test User"})
        
        # Create memories
        await gateway.create_memory_node("mem-1", "user-1", "Learned Python")
        await gateway.create_memory_node("mem-2", "user-1", "Learned FastAPI")
        await gateway.create_memory_node("mem-3", "user-1", "Built REST API")
        
        # Create concepts
        await gateway.connect_concepts("user-1", "python", "programming")
        await gateway.connect_concepts("user-1", "fastapi", "python", weight=2.0)
        await gateway.connect_concepts("user-1", "fastapi", "web-framework")
        await gateway.connect_concepts("user-1", "rest-api", "web-framework")
        
        # Add experience
        await gateway.add_experience(
            "user-1",
            "exp-1",
            "project",
            "Completed first API project",
            related_concepts=["python", "fastapi", "rest-api"]
        )
        
        return gateway
    
    @pytest.mark.asyncio
    async def test_full_knowledge_graph_workflow(self, setup_graph):
        """Test complete knowledge graph workflow."""
        gateway = setup_graph
        
        # Get knowledge graph
        kg = await gateway.get_persona_knowledge_graph("user-1")
        
        assert kg["persona_id"] == "user-1"
        assert len(kg["nodes"]) >= 5  # persona + memories + concepts
        assert kg["stats"]["node_count"] >= 5
    
    @pytest.mark.asyncio
    async def test_concept_path_finding(self, setup_graph):
        """Test finding paths between concepts."""
        gateway = setup_graph
        
        # Find path from python to rest-api
        path = await gateway.find_path_between_concepts("python", "rest-api")
        
        # Path might exist through fastapi -> web-framework -> rest-api
        if path:
            assert len(path.nodes) >= 2
            assert path.nodes[0].id == "python"
            assert path.nodes[-1].id == "rest-api"
    
    @pytest.mark.asyncio
    async def test_concept_cluster_retrieval(self, setup_graph):
        """Test retrieving concept clusters."""
        gateway = setup_graph
        
        cluster = await gateway.get_concept_cluster("python", depth=2)
        
        # Should include related concepts
        assert len(cluster) >= 1
        concept_ids = {n.id for n in cluster}
        assert "python" in concept_ids
    
    @pytest.mark.asyncio
    async def test_stats_accuracy(self, setup_graph):
        """Test statistics accuracy."""
        gateway = setup_graph
        
        stats = await gateway.get_stats()
        
        assert stats.persona_nodes == 1
        assert stats.memory_nodes == 3
        assert stats.concept_nodes >= 4  # python, programming, fastapi, web-framework, rest-api
        assert stats.event_nodes == 1
        assert stats.total_edges >= 5


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    @pytest.fixture
    def store(self):
        """Create an in-memory store."""
        config = GraphStoreConfig(password="test", in_memory=True)
        return GraphStore(config)
    
    @pytest.mark.asyncio
    async def test_get_neighbors_of_nonexistent_node(self, store):
        """Test getting neighbors of non-existent node."""
        neighbors = await store.get_neighbors("nonexistent")
        assert neighbors == []
    
    @pytest.mark.asyncio
    async def test_traverse_from_nonexistent_node(self, store):
        """Test traversal from non-existent node."""
        nodes = await store.traverse("nonexistent")
        assert nodes == []
    
    @pytest.mark.asyncio
    async def test_path_between_nonexistent_nodes(self, store):
        """Test path finding between non-existent nodes."""
        path = await store.find_shortest_path("nonexistent1", "nonexistent2")
        assert path is None
    
    @pytest.mark.asyncio
    async def test_path_exceeding_max_depth(self, store):
        """Test path finding with depth limit."""
        # Create a chain of 5 nodes
        nodes = [GraphNode(id=f"n{i}", node_type=NodeType.CONCEPT) for i in range(5)]
        for n in nodes:
            await store.create_node(n)
        
        for i in range(4):
            await store.create_edge(
                GraphEdge(source_id=f"n{i}", target_id=f"n{i+1}", relation_type=RelationType.RELATED_TO)
            )
        
        # Should find path with max_depth=5
        path = await store.find_shortest_path("n0", "n4", max_depth=5)
        assert path is not None
        
        # Should not find with max_depth=3
        path = await store.find_shortest_path("n0", "n4", max_depth=3)
        assert path is None
    
    @pytest.mark.asyncio
    async def test_cyclic_graph_traversal(self, store):
        """Test traversal in cyclic graph doesn't loop infinitely."""
        n1 = GraphNode(id="a", node_type=NodeType.CONCEPT)
        n2 = GraphNode(id="b", node_type=NodeType.CONCEPT)
        n3 = GraphNode(id="c", node_type=NodeType.CONCEPT)
        
        await store.create_node(n1)
        await store.create_node(n2)
        await store.create_node(n3)
        
        # Create cycle: a -> b -> c -> a
        await store.create_edge(GraphEdge(source_id="a", target_id="b", relation_type=RelationType.RELATED_TO))
        await store.create_edge(GraphEdge(source_id="b", target_id="c", relation_type=RelationType.RELATED_TO))
        await store.create_edge(GraphEdge(source_id="c", target_id="a", relation_type=RelationType.RELATED_TO))
        
        # Should complete without infinite loop
        nodes = await store.traverse("a", max_depth=10)
        assert len(nodes) == 3  # Each node visited once
    
    @pytest.mark.asyncio
    async def test_empty_properties(self, store):
        """Test nodes and edges with empty properties."""
        node = GraphNode(id="empty", node_type=NodeType.ENTITY, properties={})
        await store.create_node(node)
        
        retrieved = await store.get_node("empty")
        assert retrieved is not None
        assert retrieved.properties == {}
    
    @pytest.mark.asyncio
    async def test_complex_properties(self, store):
        """Test nodes with complex nested properties."""
        props = {
            "string": "value",
            "number": 42,
            "float": 3.14,
            "bool": True,
            "list": [1, 2, 3],
            "nested": {
                "deep": {
                    "value": "found"
                }
            }
        }
        
        node = GraphNode(id="complex", node_type=NodeType.ENTITY, properties=props)
        await store.create_node(node)
        
        retrieved = await store.get_node("complex")
        assert retrieved is not None
        assert retrieved.properties == props


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
