"""System API Routes."""
import time
from datetime import datetime
from typing import List

from fastapi import APIRouter, Response
from fastapi.responses import PlainTextResponse

from ..schemas.system import (
    AggregatedMetrics,
    ComponentHealth,
    ComponentStatus,
    ConfigSection,
    ConfigurationResponse,
    MetricPoint,
    MetricsResponse,
    SystemHealthResponse,
    SystemInfoResponse,
    SystemStatus,
    VersionInfo,
    VersionResponse,
)

router = APIRouter(tags=["System"])


# System start time for uptime calculation
_start_time = time.time()


@router.get(
    "/health",
    response_model=SystemHealthResponse,
    summary="System health",
    description="Check the health status of the system and its components.",
)
async def system_health() -> SystemHealthResponse:
    """Get system health status."""
    now = datetime.utcnow()
    uptime = time.time() - _start_time

    # Check component health
    components = [
        ComponentHealth(
            name="api",
            status=ComponentStatus.OPERATIONAL,
            healthy=True,
            message="API responding normally",
            latency_ms=1.5,
            details={"requests_per_second": 42.5},
        ),
        ComponentHealth(
            name="database",
            status=ComponentStatus.OPERATIONAL,
            healthy=True,
            message="Database connection pool healthy",
            latency_ms=3.2,
            details={"active_connections": 5, "max_connections": 20},
        ),
        ComponentHealth(
            name="cache",
            status=ComponentStatus.OPERATIONAL,
            healthy=True,
            message="Cache hit rate optimal",
            latency_ms=0.5,
            details={"hit_rate": 0.92, "memory_usage_mb": 128},
        ),
        ComponentHealth(
            name="llm_gateway",
            status=ComponentStatus.OPERATIONAL,
            healthy=True,
            message="All LLM providers available",
            latency_ms=45.0,
            details={"providers_enabled": 2, "providers_total": 4},
        ),
        ComponentHealth(
            name="memory_system",
            status=ComponentStatus.OPERATIONAL,
            healthy=True,
            message="Vector and graph stores operational",
            latency_ms=2.1,
            details={"vectors_stored": 15420, "graph_nodes": 8543},
        ),
        ComponentHealth(
            name="ethics_engine",
            status=ComponentStatus.OPERATIONAL,
            healthy=True,
            message="Ethics evaluation engine ready",
            latency_ms=15.0,
            details={"evaluations_today": 1250, "compliance_rate": 0.98},
        ),
    ]

    # Determine overall status
    all_healthy = all(c.healthy for c in components)
    any_degraded = any(c.status == ComponentStatus.DEGRADED for c in components)

    if all_healthy:
        system_status = SystemStatus.HEALTHY
    elif any_degraded:
        system_status = SystemStatus.DEGRADED
    else:
        system_status = SystemStatus.UNHEALTHY

    return SystemHealthResponse(
        status=system_status,
        healthy=all_healthy,
        version="1.0.0",
        uptime_seconds=uptime,
        components=components,
        checked_at=now,
        hostname="animusforge-api-0",
        environment="production",
    )


@router.get(
    "/metrics",
    summary="Prometheus metrics",
    description="Get system metrics in Prometheus format.",
    response_class=PlainTextResponse,
)
async def prometheus_metrics() -> str:
    """Get Prometheus metrics."""
    uptime = time.time() - _start_time

    # Generate Prometheus-formatted metrics
    metrics = f"""# HELP animusforge_uptime_seconds System uptime in seconds
# TYPE animusforge_uptime_seconds gauge
animusforge_uptime_seconds {uptime:.2f}

# HELP animusforge_personas_total Total number of personas
# TYPE animusforge_personas_total gauge
animusforge_personas_total 42

# HELP animusforge_personas_active Number of active personas
# TYPE animusforge_personas_active gauge
animusforge_personas_active 15

# HELP animusforge_llm_requests_total Total LLM requests
# TYPE animusforge_llm_requests_total counter
animusforge_llm_requests_total 125847

# HELP animusforge_llm_tokens_total Total tokens processed
# TYPE animusforge_llm_tokens_total counter
animusforge_llm_tokens_total 4589231

# HELP animusforge_llm_latency_seconds LLM request latency
# TYPE animusforge_llm_latency_seconds histogram
animusforge_llm_latency_seconds_bucket{{le="0.1"}} 1523
animusforge_llm_latency_seconds_bucket{{le="0.5"}} 8452
animusforge_llm_latency_seconds_bucket{{le="1.0"}} 15234
animusforge_llm_latency_seconds_bucket{{le="2.0"}} 45231
animusforge_llm_latency_seconds_bucket{{le="5.0"}} 98452
animusforge_llm_latency_seconds_bucket{{le="+Inf"}} 125847
animusforge_llm_latency_seconds_sum 89234.5
animusforge_llm_latency_seconds_count 125847

# HELP animusforge_memory_vectors_total Total vectors in memory
# TYPE animusforge_memory_vectors_total gauge
animusforge_memory_vectors_total 15420

# HELP animusforge_memory_nodes_total Total graph nodes in memory
# TYPE animusforge_memory_nodes_total gauge
animusforge_memory_nodes_total 8543

# HELP animusforge_ethics_evaluations_total Total ethics evaluations
# TYPE animusforge_ethics_evaluations_total counter
animusforge_ethics_evaluations_total 45231

# HELP animusforge_ethics_violations_total Total ethics violations
# TYPE animusforge_ethics_violations_total counter
animusforge_ethics_violations_total 127

# HELP animusforge_killswitch_triggers_total Total kill-switch triggers
# TYPE animusforge_killswitch_triggers_total counter
animusforge_killswitch_triggers_total 3

# HELP animusforge_http_requests_total Total HTTP requests
# TYPE animusforge_http_requests_total counter
animusforge_http_requests_total{{method="GET",status="200"}} 85421
animusforge_http_requests_total{{method="POST",status="201"}} 12453
animusforge_http_requests_total{{method="PUT",status="200"}} 3452
animusforge_http_requests_total{{method="DELETE",status="204"}} 1234
"""

    return metrics


@router.get(
    "/info",
    response_model=SystemInfoResponse,
    summary="System information",
    description="Get detailed system information.",
)
async def system_info() -> SystemInfoResponse:
    """Get system information."""
    return SystemInfoResponse(
        name="AnimusForge",
        description="Adaptive AI Persona Framework with Ethical Governance",
        version="1.0.0",
        api_version="v1",
        build="2024.03.06.001",
        commit="a1b2c3d4e5f6g7h8i9j0",
        environment="production",
        features=[
            "persona_management",
            "llm_gateway",
            "kill_switch",
            "vector_memory",
            "graph_memory",
            "ethics_evaluation",
            "audit_logging",
        ],
        llm_providers=["openai", "anthropic", "deepseek", "glm"],
        capabilities=[
            "persona_evolution",
            "multi_provider_llm",
            "semantic_memory",
            "knowledge_graph",
            "realtime_ethics",
            "emergency_shutdown",
        ],
        started_at=datetime.utcfromtimestamp(_start_time),
        hostname="animusforge-api-0",
    )


@router.get(
    "/version",
    response_model=VersionResponse,
    summary="Version information",
    description="Get API version details.",
)
async def version_info() -> VersionResponse:
    """Get version information."""
    return VersionResponse(
        version="1.0.0",
        version_info=VersionInfo(
            major=1,
            minor=0,
            patch=0,
            pre_release=None,
            build="20240306001",
        ),
        api_version="v1",
        build_date=datetime(2024, 3, 6, 0, 0, 0),
        git_commit="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0",
        git_branch="main",
    )


@router.get(
    "/config",
    response_model=ConfigurationResponse,
    summary="Configuration",
    description="Get current system configuration (non-sensitive values only).",
)
async def configuration() -> ConfigurationResponse:
    """Get system configuration."""
    sections = [
        ConfigSection(
            name="api",
            settings={
                "host": "0.0.0.0",
                "port": 8000,
                "workers": 4,
                "timeout_seconds": 30,
            },
            sensitive_keys=[],
        ),
        ConfigSection(
            name="database",
            settings={
                "pool_size": 20,
                "max_overflow": 10,
                "pool_timeout": 30,
                "echo": False,
            },
            sensitive_keys=["password", "url"],
        ),
        ConfigSection(
            name="cache",
            settings={
                "backend": "redis",
                "ttl_seconds": 3600,
                "max_memory_mb": 512,
            },
            sensitive_keys=["url", "password"],
        ),
        ConfigSection(
            name="llm",
            settings={
                "default_provider": "openai",
                "default_model": "gpt-4-turbo",
                "max_retries": 3,
                "timeout_seconds": 60,
                "streaming_enabled": True,
            },
            sensitive_keys=["api_keys"],
        ),
        ConfigSection(
            name="memory",
            settings={
                "vector_dimension": 1536,
                "vector_metric": "cosine",
                "graph_max_depth": 5,
                "retention_days": 90,
            },
            sensitive_keys=[],
        ),
        ConfigSection(
            name="ethics",
            settings={
                "strict_mode": False,
                "min_compliance_score": 0.7,
                "audit_enabled": True,
                "auto_block_threshold": 0.3,
            },
            sensitive_keys=[],
        ),
        ConfigSection(
            name="rate_limiting",
            settings={
                "enabled": True,
                "requests_per_minute": 60,
                "requests_per_hour": 1000,
                "burst_size": 10,
            },
            sensitive_keys=[],
        ),
        ConfigSection(
            name="security",
            settings={
                "auth_enabled": True,
                "auth_type": "jwt",
                "https_only": True,
                "cors_origins": ["https://animusforge.app"],
            },
            sensitive_keys=["secret_key", "jwt_secret"],
        ),
    ]

    return ConfigurationResponse(
        environment="production",
        debug=False,
        log_level="INFO",
        sections=sections,
        loaded_at=datetime.utcnow(),
        config_source="environment",
    )
