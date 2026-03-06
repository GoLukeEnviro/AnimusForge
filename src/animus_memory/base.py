"""
AnimusForge Memory System - Base Models

Pydantic v2 models for memory management including episodic, semantic, and procedural memory types.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


class MemoryType(str, Enum):
    """Memory type classification based on cognitive science models."""
    EPISODIC = "episodic"      # Events, experiences, personal narratives
    SEMANTIC = "semantic"       # Facts, knowledge, concepts
    PROCEDURAL = "procedural"   # Skills, procedures, how-to knowledge


class MemoryEntry(BaseModel):
    """Single memory entry with embedding support and decay tracking."""
    
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        arbitrary_types_allowed=True
    )
    
    id: str = Field(default_factory=lambda: str(uuid4()))
    persona_id: str = Field(..., min_length=1, description="Owner persona ID")
    memory_type: MemoryType = Field(..., description="Type of memory")
    content: str = Field(..., min_length=1, description="Memory content text")
    embedding: Optional[List[float]] = Field(default=None, description="Vector embedding")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    importance: float = Field(default=0.5, ge=0.0, le=1.0, description="Memory importance 0-1")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    access_count: int = Field(default=0, ge=0, description="Number of times accessed")
    decay_rate: float = Field(default=0.1, ge=0.0, le=1.0, description="Decay rate per time unit")
    
    @field_validator('embedding')
    @classmethod
    def validate_embedding(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        if v is not None and len(v) == 0:
            raise ValueError('Embedding must not be empty list')
        return v
    
    def apply_decay(self, time_elapsed_seconds: float) -> float:
        """
        Apply exponential decay to memory importance.
        
        Formula: importance *= exp(-decay_rate * time_elapsed)
        
        Args:
            time_elapsed_seconds: Time elapsed since last access in seconds
            
        Returns:
            New decayed importance value
        """
        import math
        # Convert seconds to hours for more reasonable decay rates
        time_elapsed_hours = time_elapsed_seconds / 3600.0
        decay_factor = math.exp(-self.decay_rate * time_elapsed_hours)
        self.importance = max(0.0, min(1.0, self.importance * decay_factor))
        return self.importance
    
    def record_access(self) -> None:
        """Record a memory access, updating stats."""
        self.last_accessed = datetime.now(timezone.utc)
        self.access_count += 1
        # Boost importance slightly on access
        self.importance = min(1.0, self.importance + 0.05)


class SearchResult(BaseModel):
    """Search result with relevance scoring."""
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    entry: MemoryEntry = Field(..., description="The memory entry")
    score: float = Field(..., ge=0.0, le=1.0, description="Relevance score 0-1")
    distance: float = Field(..., ge=0.0, description="Vector distance (lower = more similar)")


class VectorStoreConfig(BaseModel):
    """Configuration for Qdrant vector store."""
    
    model_config = ConfigDict(str_strip_whitespace=True)
    
    collection_name: str = Field(default="animus_memories", min_length=1)
    embedding_dim: int = Field(default=1536, ge=1, description="Embedding dimension (OpenAI ada-002 default)")
    distance_metric: str = Field(default="cosine", description="Distance metric for similarity")
    host: str = Field(default="localhost")
    port: int = Field(default=6333, ge=1, le=65535)
    grpc_port: int = Field(default=6334, ge=1, le=65535)
    prefer_grpc: bool = Field(default=False)
    api_key: Optional[str] = Field(default=None)
    timeout: float = Field(default=30.0, ge=1.0)
    in_memory: bool = Field(default=False, description="Use in-memory mode for testing")
    
    @field_validator('distance_metric')
    @classmethod
    def validate_distance_metric(cls, v: str) -> str:
        allowed = {'cosine', 'euclidean', 'dot'}
        if v.lower() not in allowed:
            raise ValueError(f'distance_metric must be one of {allowed}')
        return v.lower()


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


class CircuitBreaker(BaseModel):
    """Circuit breaker for fault tolerance."""
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    state: CircuitState = Field(default=CircuitState.CLOSED)
    failure_count: int = Field(default=0, ge=0)
    success_count: int = Field(default=0, ge=0)
    failure_threshold: int = Field(default=5, ge=1)
    success_threshold: int = Field(default=3, ge=1)
    timeout_seconds: float = Field(default=60.0, ge=1.0)
    last_failure_time: Optional[datetime] = Field(default=None)
    
    def record_failure(self) -> None:
        """Record a failure and potentially open circuit."""
        self.failure_count += 1
        self.success_count = 0
        self.last_failure_time = datetime.now(timezone.utc)
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
    
    def record_success(self) -> None:
        """Record a success and potentially close circuit."""
        self.success_count += 1
        self.failure_count = 0
        
        if self.state == CircuitState.HALF_OPEN:
            if self.success_count >= self.success_threshold:
                self.state = CircuitState.CLOSED
                self.success_count = 0
    
    def can_execute(self) -> bool:
        """Check if execution is allowed."""
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            if self.last_failure_time is None:
                return False
            elapsed = (datetime.now(timezone.utc) - self.last_failure_time).total_seconds()
            if elapsed >= self.timeout_seconds:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        
        # HALF_OPEN allows limited testing
        return True
    
    def reset(self) -> None:
        """Reset circuit breaker to initial state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None


class VectorGatewayConfig(BaseModel):
    """Configuration for VectorGateway."""
    
    model_config = ConfigDict(str_strip_whitespace=True)
    
    store_config: VectorStoreConfig = Field(default_factory=VectorStoreConfig)
    enable_decay: bool = Field(default=True)
    decay_interval_hours: float = Field(default=24.0, ge=1.0)
    min_importance_threshold: float = Field(default=0.1, ge=0.0, le=1.0)
    max_retries: int = Field(default=3, ge=1)
    retry_delay_seconds: float = Field(default=1.0, ge=0.1)


class MemoryStats(BaseModel):
    """Statistics about memory storage."""
    
    total_memories: int = Field(default=0, ge=0)
    episodic_count: int = Field(default=0, ge=0)
    semantic_count: int = Field(default=0, ge=0)
    procedural_count: int = Field(default=0, ge=0)
    avg_importance: float = Field(default=0.0, ge=0.0, le=1.0)
    total_access_count: int = Field(default=0, ge=0)
    collection_size_bytes: int = Field(default=0, ge=0)
