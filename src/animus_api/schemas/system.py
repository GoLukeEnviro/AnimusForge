"""System schemas for health, metrics, and configuration."""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from .base import BaseSchema, HealthStatus


class SystemStatus(str, Enum):
    """System status enumeration."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    MAINTENANCE = "maintenance"
    STARTING = "starting"
    STOPPING = "stopping"


class ComponentStatus(str, Enum):
    """Component status enumeration."""
    OPERATIONAL = "operational"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


# ==================== Health Schemas ====================

class ComponentHealth(BaseSchema):
    """Health status of a system component."""
    name: str = Field(description="Component name")
    status: ComponentStatus = Field(description="Component status")
    healthy: bool = Field(description="Health check result")
    message: Optional[str] = Field(default=None, description="Status message")
    latency_ms: Optional[float] = Field(default=None, description="Response latency")
    last_check: datetime = Field(default_factory=datetime.utcnow, description="Last check time")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional details")


class SystemHealthResponse(BaseSchema):
    """System health check response."""
    status: SystemStatus = Field(description="Overall system status")
    healthy: bool = Field(description="Overall health status")
    version: str = Field(description="System version")
    uptime_seconds: float = Field(description="System uptime in seconds")
    components: List[ComponentHealth] = Field(description="Component health statuses")
    checked_at: datetime = Field(default_factory=datetime.utcnow, description="Check timestamp")
    hostname: str = Field(description="Server hostname")
    environment: str = Field(description="Environment name")


# ==================== Metrics Schemas ====================

class MetricType(str, Enum):
    """Metric type enumeration."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


class MetricPoint(BaseSchema):
    """Single metric data point."""
    name: str = Field(description="Metric name")
    value: float = Field(description="Metric value")
    metric_type: MetricType = Field(description="Metric type")
    labels: Dict[str, str] = Field(default_factory=dict, description="Metric labels")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Metric timestamp")


class MetricsResponse(BaseSchema):
    """Prometheus metrics response."""
    metrics: List[MetricPoint] = Field(description="Metric data points")
    format: str = Field(default="prometheus", description="Metrics format")
    scrape_duration_ms: float = Field(description="Scrape duration")


class AggregatedMetrics(BaseSchema):
    """Aggregated system metrics."""
    persona_count: int = Field(description="Total personas")
    active_persona_count: int = Field(description="Active personas")
    total_interactions: int = Field(description="Total interactions")
    interactions_per_hour: float = Field(description="Interactions per hour")
    avg_response_time_ms: float = Field(description="Average response time")
    error_rate: float = Field(description="Error rate (0-1)")
    llm_requests_total: int = Field(description="Total LLM requests")
    llm_tokens_total: int = Field(description="Total tokens used")
    memory_vectors_total: int = Field(description="Total vectors stored")
    memory_nodes_total: int = Field(description="Total graph nodes")
    uptime_seconds: float = Field(description="System uptime")


# ==================== Info Schemas ====================

class SystemInfoResponse(BaseSchema):
    """System information response."""
    name: str = Field(description="System name")
    description: str = Field(description="System description")
    version: str = Field(description="System version")
    api_version: str = Field(description="API version")
    build: str = Field(description="Build identifier")
    commit: str = Field(description="Git commit hash")
    environment: str = Field(description="Environment name")
    features: List[str] = Field(description="Enabled features")
    llm_providers: List[str] = Field(description="Available LLM providers")
    capabilities: List[str] = Field(description="System capabilities")
    started_at: datetime = Field(description="System start time")
    hostname: str = Field(description="Server hostname")


class VersionInfo(BaseSchema):
    """Version information."""
    major: int = Field(description="Major version")
    minor: int = Field(description="Minor version")
    patch: int = Field(description="Patch version")
    pre_release: Optional[str] = Field(default=None, description="Pre-release identifier")
    build: Optional[str] = Field(default=None, description="Build metadata")

    def __str__(self) -> str:
        version = f"{self.major}.{self.minor}.{self.patch}"
        if self.pre_release:
            version += f"-{self.pre_release}"
        if self.build:
            version += f"+{self.build}"
        return version


class VersionResponse(BaseSchema):
    """Version endpoint response."""
    version: str = Field(description="Full version string")
    version_info: VersionInfo = Field(description="Version components")
    api_version: str = Field(description="API version")
    build_date: datetime = Field(description="Build date")
    git_commit: str = Field(description="Git commit hash")
    git_branch: str = Field(description="Git branch")


# ==================== Config Schemas ====================

class ConfigSection(BaseSchema):
    """Configuration section."""
    name: str = Field(description="Section name")
    settings: Dict[str, Any] = Field(description="Section settings")
    sensitive_keys: List[str] = Field(default_factory=list, description="Sensitive key names")


class ConfigurationResponse(BaseSchema):
    """Configuration response."""
    environment: str = Field(description="Environment name")
    debug: bool = Field(description="Debug mode")
    log_level: str = Field(description="Log level")
    sections: List[ConfigSection] = Field(description="Configuration sections")
    loaded_at: datetime = Field(default_factory=datetime.utcnow, description="Config load time")
    config_source: str = Field(description="Configuration source")


class RateLimitConfig(BaseSchema):
    """Rate limit configuration."""
    enabled: bool = Field(description="Rate limiting enabled")
    requests_per_minute: int = Field(description="Requests per minute limit")
    requests_per_hour: int = Field(description="Requests per hour limit")
    burst_size: int = Field(description="Burst size")


class SecurityConfig(BaseSchema):
    """Security configuration."""
    auth_enabled: bool = Field(description="Authentication enabled")
    auth_type: str = Field(description="Authentication type")
    cors_origins: List[str] = Field(description="Allowed CORS origins")
    cors_methods: List[str] = Field(description="Allowed CORS methods")
    https_only: bool = Field(description="HTTPS only")
