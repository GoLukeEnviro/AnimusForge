"""
AnimusForge Container-based Sandbox System
Tool Execution with Autonomy Zone Isolation

SPRINT1-003 Implementation
ADR-011: Tool Sandbox Architecture
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from pydantic import BaseModel, Field, ConfigDict, field_validator

if TYPE_CHECKING:
    import docker
    from docker.models.containers import Container

logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS
# ============================================================================

class AutonomyZone(str, Enum):
    """Autonomy zones defining execution restrictions.
    
    Hierarchy: SAFE < MODERATE < RESTRICTED < FORBIDDEN
    
    - SAFE: Normal operations, no restrictions
    - MODERATE: Restricted tools, resource limits, limited network
    - RESTRICTED: Dangerous tools, strict limits, no network, isolated
    - FORBIDDEN: No execution allowed
    """
    SAFE = "safe"
    MODERATE = "moderate"
    RESTRICTED = "restricted"
    FORBIDDEN = "forbidden"

    def __str__(self) -> str:
        return self.value

    @property
    def allows_network(self) -> bool:
        """Check if this zone allows network access."""
        return self in (AutonomyZone.SAFE, AutonomyZone.MODERATE)

    @property
    def allows_execution(self) -> bool:
        """Check if this zone allows any execution."""
        return self != AutonomyZone.FORBIDDEN


class ExecutionStatus(str, Enum):
    """Status of a sandbox execution."""
    SUCCESS = "success"
    TIMEOUT = "timeout"
    ERROR = "error"
    KILLED = "killed"
    FORBIDDEN = "forbidden"
    RESOURCE_EXCEEDED = "resource_exceeded"

    def __str__(self) -> str:
        return self.value


class ContainerRuntime(str, Enum):
    """Supported container runtimes."""
    DOCKER = "docker"
    GVISOR = "gvisor"
    KATA = "kata"

    def __str__(self) -> str:
        return self.value


# ============================================================================
# CONFIGURATION MODELS
# ============================================================================

# Zone presets for default configurations
ZONE_PRESETS: Dict[AutonomyZone, Dict[str, Any]] = {
    AutonomyZone.SAFE: {
        "cpu_limit": 2.0,
        "memory_limit_mb": 1024,
        "disk_limit_mb": 5120,
        "network_enabled": True,
        "timeout_seconds": 300,
    },
    AutonomyZone.MODERATE: {
        "cpu_limit": 1.0,
        "memory_limit_mb": 512,
        "disk_limit_mb": 1024,
        "network_enabled": True,
        "timeout_seconds": 120,
    },
    AutonomyZone.RESTRICTED: {
        "cpu_limit": 0.5,
        "memory_limit_mb": 256,
        "disk_limit_mb": 256,
        "network_enabled": False,
        "timeout_seconds": 60,
    },
    AutonomyZone.FORBIDDEN: {
        "cpu_limit": 0.0,
        "memory_limit_mb": 0,
        "disk_limit_mb": 0,
        "network_enabled": False,
        "timeout_seconds": 0,
    },
}


class SandboxConfig(BaseModel):
    """Configuration for sandbox execution environment.
    
    Defines resource limits, network access, timeout, and allowed tools
    based on the autonomy zone.
    """
    model_config = ConfigDict(
        frozen=True,
        use_enum_values=False,
        json_encoders={datetime: lambda v: v.isoformat()},
    )

    autonomy_zone: AutonomyZone = Field(
        default=AutonomyZone.SAFE,
        description="Autonomy zone for execution restrictions",
    )
    cpu_limit: float = Field(
        default=2.0,
        ge=0.0,
        le=16.0,
        description="CPU limit in cores",
    )
    memory_limit_mb: int = Field(
        default=1024,
        ge=0,
        le=32768,
        description="Memory limit in megabytes",
    )
    disk_limit_mb: int = Field(
        default=5120,
        ge=0,
        le=102400,
        description="Disk limit in megabytes",
    )
    network_enabled: bool = Field(
        default=True,
        description="Whether network access is allowed",
    )
    timeout_seconds: int = Field(
        default=300,
        ge=0,
        le=3600,
        description="Execution timeout in seconds",
    )
    allowed_tools: List[str] = Field(
        default_factory=list,
        description="List of allowed tool names",
    )
    container_runtime: ContainerRuntime = Field(
        default=ContainerRuntime.DOCKER,
        description="Container runtime to use",
    )
    image_name: str = Field(
        default="python:3.12-slim",
        description="Docker image for execution",
    )
    workdir: str = Field(
        default="/sandbox",
        description="Working directory inside container",
    )
    enable_audit_logging: bool = Field(
        default=True,
        description="Enable audit logging for executions",
    )
    max_output_size_kb: int = Field(
        default=1024,
        ge=1,
        le=10240,
        description="Maximum output size in kilobytes",
    )

    @field_validator("allowed_tools", mode="before")
    @classmethod
    def validate_allowed_tools(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return list(v)

    @classmethod
    def from_zone(cls, zone: AutonomyZone, **overrides: Any) -> "SandboxConfig":
        """Create config from zone preset with optional overrides."""
        preset = ZONE_PRESETS.get(zone, ZONE_PRESETS[AutonomyZone.SAFE]).copy()
        preset["autonomy_zone"] = zone
        preset.update(overrides)
        return cls(**preset)


class ExecutionResult(BaseModel):
    """Result of a sandbox execution."""
    model_config = ConfigDict(
        frozen=True,
        use_enum_values=True,
        json_encoders={datetime: lambda v: v.isoformat()},
    )

    execution_id: str = Field(description="Unique execution identifier")
    status: ExecutionStatus = Field(description="Execution status")
    stdout: str = Field(default="", description="Standard output")
    stderr: str = Field(default="", description="Standard error")
    exit_code: Optional[int] = Field(default=None, description="Process exit code")
    duration_ms: float = Field(default=0.0, description="Execution duration in milliseconds")
    container_id: Optional[str] = Field(default=None, description="Container identifier")
    autonomy_zone: AutonomyZone = Field(description="Autonomy zone used")
    tool_name: Optional[str] = Field(default=None, description="Tool name if tool execution")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Execution timestamp",
    )
    resource_usage: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Resource usage statistics",
    )
    error_message: Optional[str] = Field(default=None, description="Error message if failed")


class ToolResult(BaseModel):
    """Result of a tool execution in sandbox."""
    model_config = ConfigDict(frozen=True)

    tool_name: str = Field(description="Tool name")
    success: bool = Field(description="Whether execution succeeded")
    result: Any = Field(default=None, description="Tool result data")
    error: Optional[str] = Field(default=None, description="Error message")
    execution_id: str = Field(description="Execution identifier")
    duration_ms: float = Field(default=0.0, description="Execution duration")
    autonomy_zone: AutonomyZone = Field(description="Autonomy zone used")


# ============================================================================
# TOOL DEFINITION
# ============================================================================

@dataclass
class ToolDefinition:
    """Definition of an executable tool.
    
    Attributes:
        name: Unique tool identifier
        description: Human-readable description
        autonomy_zone: Required minimum autonomy zone
        parameters: JSON Schema for parameters
        timeout: Execution timeout in seconds
        rate_limit: Maximum executions per minute
        validator: Optional validation function for parameters
        validator_code: Optional validation code string (for serialization)
    """
    name: str
    description: str
    autonomy_zone: AutonomyZone
    parameters: Dict[str, Any] = field(default_factory=dict)
    timeout: int = 60
    rate_limit: int = 60  # per minute
    validator: Optional[Callable[[Dict[str, Any]], bool]] = None
    validator_code: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.parameters:
            self.parameters = {"type": "object", "properties": {}}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "autonomy_zone": self.autonomy_zone.value,
            "parameters": self.parameters,
            "timeout": self.timeout,
            "rate_limit": self.rate_limit,
            "validator_code": self.validator_code,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolDefinition":
        """Create from dictionary."""
        data["autonomy_zone"] = AutonomyZone(data["autonomy_zone"])
        return cls(**data)


# ============================================================================
# TOOL REGISTRY
# ============================================================================

class ToolRegistry:
    """Registry for managing tool definitions.
    
    Thread-safe registry that stores tool definitions and provides
    validation, lookup, and enumeration capabilities.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}
        self._rate_trackers: Dict[str, List[float]] = {}
        self._lock = asyncio.Lock()

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool definition.
        
        Args:
            tool: Tool definition to register
            
        Raises:
            ValueError: If tool with same name already exists
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool
        self._rate_trackers[tool.name] = []
        logger.info(f"Registered tool: {tool.name} (zone: {tool.autonomy_zone})")

    def unregister(self, tool_name: str) -> bool:
        """Unregister a tool.
        
        Args:
            tool_name: Name of tool to unregister
            
        Returns:
            True if tool was unregistered, False if not found
        """
        if tool_name in self._tools:
            del self._tools[tool_name]
            del self._rate_trackers[tool_name]
            logger.info(f"Unregistered tool: {tool_name}")
            return True
        return False

    def get(self, tool_name: str) -> Optional[ToolDefinition]:
        """Get tool definition by name.
        
        Args:
            tool_name: Tool name to look up
            
        Returns:
            Tool definition or None if not found
        """
        return self._tools.get(tool_name)

    def list_tools(self, zone: Optional[AutonomyZone] = None) -> List[ToolDefinition]:
        """List all registered tools, optionally filtered by zone.
        
        Args:
            zone: Optional zone filter
            
        Returns:
            List of tool definitions
        """
        tools = list(self._tools.values())
        if zone:
            tools = [t for t in tools if t.autonomy_zone == zone]
        return tools

    def validate(self, tool_name: str, params: Dict[str, Any]) -> bool:
        """Validate parameters against tool definition.
        
        Args:
            tool_name: Tool name
            params: Parameters to validate
            
        Returns:
            True if valid, False otherwise
        """
        tool = self.get(tool_name)
        if not tool:
            logger.warning(f"Tool not found: {tool_name}")
            return False

        # Run custom validator if present
        if tool.validator:
            try:
                return tool.validator(params)
            except Exception as e:
                logger.error(f"Validator error for {tool_name}: {e}")
                return False

        return True

    async def check_rate_limit(self, tool_name: str) -> bool:
        """Check if tool execution is within rate limit.
        
        Args:
            tool_name: Tool name
            
        Returns:
            True if within limit, False if exceeded
        """
        tool = self.get(tool_name)
        if not tool:
            return False

        async with self._lock:
            now = time.time()
            tracker = self._rate_trackers.get(tool_name, [])
            
            # Remove timestamps older than 1 minute
            tracker[:] = [ts for ts in tracker if now - ts < 60]
            
            if len(tracker) >= tool.rate_limit:
                logger.warning(f"Rate limit exceeded for tool: {tool_name}")
                return False
            
            tracker.append(now)
            return True

    def get_zone_for_tool(self, tool_name: str) -> Optional[AutonomyZone]:
        """Get required autonomy zone for a tool.
        
        Args:
            tool_name: Tool name
            
        Returns:
            Required zone or None if tool not found
        """
        tool = self.get(tool_name)
        return tool.autonomy_zone if tool else None

    def is_tool_allowed_in_zone(
        self, tool_name: str, zone: AutonomyZone
    ) -> bool:
        """Check if tool is allowed in given autonomy zone.
        
        Args:
            tool_name: Tool name
            zone: Autonomy zone to check
            
        Returns:
            True if allowed, False otherwise
        """
        tool = self.get(tool_name)
        if not tool:
            return False

        # Zone hierarchy: SAFE < MODERATE < RESTRICTED < FORBIDDEN
        zone_order = [
            AutonomyZone.SAFE,
            AutonomyZone.MODERATE,
            AutonomyZone.RESTRICTED,
            AutonomyZone.FORBIDDEN,
        ]
        
        tool_zone_index = zone_order.index(tool.autonomy_zone)
        current_zone_index = zone_order.index(zone)
        
        # Tool is allowed if current zone is at least as restrictive as tool's zone
        return current_zone_index >= tool_zone_index


# ============================================================================
# SANDBOX EXECUTOR
# ============================================================================

class SandboxExecutor:
    """Container-based sandbox executor for tool and code execution.
    
    Provides isolated execution environments with resource limits,
    network isolation, and timeout handling.
    """

    def __init__(
        self,
        config: Optional[SandboxConfig] = None,
        container_client: Optional["docker.DockerClient"] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ) -> None:
        self.config = config or SandboxConfig()
        self._container_client = container_client
        self._tool_registry = tool_registry or ToolRegistry()
        self._active_containers: Dict[str, "Container"] = {}
        self._initialized = False

    @property
    def container_client(self) -> "docker.DockerClient":
        """Lazy-loaded Docker client."""
        if self._container_client is None:
            import docker
            self._container_client = docker.from_env()
        return self._container_client

    @property
    def tool_registry(self) -> ToolRegistry:
        """Tool registry instance."""
        return self._tool_registry

    async def initialize(self) -> None:
        """Initialize the sandbox executor.
        
        Ensures Docker is available and pulls required images.
        """
        if self._initialized:
            return

        try:
            # Verify Docker is available
            await asyncio.to_thread(self.container_client.ping)
            logger.info("Docker connection established")

            # Pull required image
            await asyncio.to_thread(
                self.container_client.images.pull,
                self.config.image_name
            )
            logger.info(f"Pulled image: {self.config.image_name}")

            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize sandbox: {e}")
            raise

    async def health_check(self) -> bool:
        """Check if sandbox executor is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            await asyncio.to_thread(self.container_client.ping)
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def _build_container_config(
        self,
        command: List[str],
        workdir: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        mounts: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Build container configuration.
        
        Args:
            command: Command to execute
            workdir: Working directory
            env: Environment variables
            mounts: Volume mounts
            
        Returns:
            Container configuration dict
        """
        config: Dict[str, Any] = {
            "image": self.config.image_name,
            "command": command,
            "working_dir": workdir or self.config.workdir,
            "detach": True,
            "remove": False,
            "environment": env or {},
            "network_disabled": not self.config.network_enabled,
        }

        # Resource limits
        if self.config.cpu_limit > 0:
            config["cpu_quota"] = int(self.config.cpu_limit * 100000)
            config["cpu_period"] = 100000

        if self.config.memory_limit_mb > 0:
            config["mem_limit"] = f"{self.config.memory_limit_mb}m"
            config["memswap_limit"] = f"{self.config.memory_limit_mb}m"

        # PIDs limit
        config["pids_limit"] = 256

        # Security options
        config["security_opt"] = ["no-new-privileges"]
        config["cap_drop"] = ["ALL"]

        # Volume mounts
        if mounts:
            config["volumes"] = {}
            for mount in mounts:
                config["volumes"][mount["host"]] = {
                    "bind": mount["container"],
                    "mode": mount.get("mode", "ro"),
                }

        return config

    async def execute(
        self,
        code: str,
        language: str = "python",
        timeout_override: Optional[int] = None,
    ) -> ExecutionResult:
        """Execute code in sandbox container.
        
        Args:
            code: Code to execute
            language: Programming language (python, javascript, etc.)
            timeout_override: Override timeout in seconds
            
        Returns:
            Execution result
        """
        # Check if execution is allowed
        if not self.config.autonomy_zone.allows_execution:
            return ExecutionResult(
                execution_id=str(uuid.uuid4()),
                status=ExecutionStatus.FORBIDDEN,
                autonomy_zone=self.config.autonomy_zone,
                error_message=f"Execution forbidden in zone: {self.config.autonomy_zone}",
            )

        execution_id = str(uuid.uuid4())
        timeout = timeout_override or self.config.timeout_seconds
        start_time = time.monotonic()

        # Build command based on language
        if language == "python":
            command = ["python", "-c", code]
        elif language == "javascript" or language == "nodejs":
            command = ["node", "-e", code]
        elif language == "bash":
            command = ["/bin/bash", "-c", code]
        else:
            return ExecutionResult(
                execution_id=execution_id,
                status=ExecutionStatus.ERROR,
                autonomy_zone=self.config.autonomy_zone,
                error_message=f"Unsupported language: {language}",
            )

        container = None
        container_id = None

        try:
            # Ensure initialized
            await self.initialize()

            # Build container config
            container_config = self._build_container_config(command)

            # Create container
            container = await asyncio.to_thread(
                self.container_client.containers.create,
                **container_config
            )
            container_id = container.id
            self._active_containers[execution_id] = container

            # Audit logging
            if self.config.enable_audit_logging:
                logger.info(
                    f"[{execution_id}] Starting execution: language={language}, "
                    f"zone={self.config.autonomy_zone}, timeout={timeout}s"
                )

            # Start container
            await asyncio.to_thread(container.start)

            # Wait for completion with timeout
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(container.wait),
                    timeout=timeout,
                )
                exit_code = result.get("StatusCode", -1)
            except asyncio.TimeoutError:
                # Kill container on timeout
                await asyncio.to_thread(container.kill)
                exit_code = -1
                status = ExecutionStatus.TIMEOUT
                logger.warning(f"[{execution_id}] Execution timed out after {timeout}s")

            # Get logs
            stdout = await asyncio.to_thread(
                lambda: container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
            )
            stderr = await asyncio.to_thread(
                lambda: container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
            )

            # Truncate output if needed
            max_output = self.config.max_output_size_kb * 1024
            if len(stdout) > max_output:
                stdout = stdout[:max_output] + "\n... [truncated]"
            if len(stderr) > max_output:
                stderr = stderr[:max_output] + "\n... [truncated]"

            duration_ms = (time.monotonic() - start_time) * 1000

            # Determine status
            if "status" not in locals():
                if exit_code == 0:
                    status = ExecutionStatus.SUCCESS
                else:
                    status = ExecutionStatus.ERROR

            # Get resource usage
            try:
                stats = await asyncio.to_thread(container.stats, stream=False)
                resource_usage = {
                    "cpu_percent": self._calculate_cpu_percent(stats),
                    "memory_mb": stats.get("memory_stats", {}).get("usage", 0) / (1024 * 1024),
                }
            except Exception:
                resource_usage = None

            # Audit logging
            if self.config.enable_audit_logging:
                logger.info(
                    f"[{execution_id}] Execution completed: status={status}, "
                    f"duration={duration_ms:.2f}ms, exit_code={exit_code}"
                )

            return ExecutionResult(
                execution_id=execution_id,
                status=status,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                duration_ms=duration_ms,
                container_id=container_id,
                autonomy_zone=self.config.autonomy_zone,
                resource_usage=resource_usage,
            )

        except Exception as e:
            logger.error(f"[{execution_id}] Execution error: {e}")
            return ExecutionResult(
                execution_id=execution_id,
                status=ExecutionStatus.ERROR,
                autonomy_zone=self.config.autonomy_zone,
                container_id=container_id,
                duration_ms=(time.monotonic() - start_time) * 1000,
                error_message=str(e),
            )

        finally:
            # Cleanup container
            if container:
                try:
                    await asyncio.to_thread(container.remove, force=True)
                except Exception as e:
                    logger.warning(f"[{execution_id}] Container cleanup error: {e}")
                self._active_containers.pop(execution_id, None)

    async def execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        config_override: Optional[SandboxConfig] = None,
    ) -> ToolResult:
        """Execute a registered tool in sandbox.
        
        Args:
            tool_name: Name of tool to execute
            params: Tool parameters
            config_override: Override sandbox config
            
        Returns:
            Tool execution result
        """
        config = config_override or self.config
        execution_id = str(uuid.uuid4())
        start_time = time.monotonic()

        # Get tool definition
        tool = self._tool_registry.get(tool_name)
        if not tool:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Tool not found: {tool_name}",
                execution_id=execution_id,
                autonomy_zone=config.autonomy_zone,
            )

        # Check if tool is allowed in current zone
        if not self._tool_registry.is_tool_allowed_in_zone(
            tool_name, config.autonomy_zone
        ):
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Tool '{tool_name}' not allowed in zone: {config.autonomy_zone}",
                execution_id=execution_id,
                autonomy_zone=config.autonomy_zone,
            )

        # Check rate limit
        if not await self._tool_registry.check_rate_limit(tool_name):
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Rate limit exceeded for tool: {tool_name}",
                execution_id=execution_id,
                autonomy_zone=config.autonomy_zone,
            )

        # Validate parameters
        if not self._tool_registry.validate(tool_name, params):
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Invalid parameters for tool: {tool_name}",
                execution_id=execution_id,
                autonomy_zone=config.autonomy_zone,
            )

        # Build tool execution code
        tool_code = self._build_tool_execution_code(tool, params)

        # Execute with tool-specific timeout
        result = await self.execute(
            code=tool_code,
            timeout_override=min(tool.timeout, config.timeout_seconds),
        )

        duration_ms = (time.monotonic() - start_time) * 1000

        # Parse result
        if result.status == ExecutionStatus.SUCCESS:
            try:
                output = json.loads(result.stdout.strip()) if result.stdout.strip() else {}
            except json.JSONDecodeError:
                output = {"raw_output": result.stdout}

            return ToolResult(
                tool_name=tool_name,
                success=True,
                result=output,
                execution_id=result.execution_id,
                duration_ms=duration_ms,
                autonomy_zone=config.autonomy_zone,
            )
        else:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=result.error_message or result.stderr or f"Status: {result.status}",
                execution_id=result.execution_id,
                duration_ms=duration_ms,
                autonomy_zone=config.autonomy_zone,
            )

    def _build_tool_execution_code(
        self,
        tool: ToolDefinition,
        params: Dict[str, Any],
    ) -> str:
        """Build Python code for tool execution.
        
        Args:
            tool: Tool definition
            params: Tool parameters
            
        Returns:
            Python code string
        """
        params_json = json.dumps(params)
        return f'''
import json
import sys

# Tool: {tool.name}
# Description: {tool.description}

tool_params = json.loads("""{params_json}"")

# Placeholder for actual tool implementation
# In production, this would be replaced with real tool logic
result = {{"status": "executed", "tool": "{tool.name}", "params": tool_params}}

print(json.dumps(result))
'''.strip()

    def _calculate_cpu_percent(self, stats: Dict[str, Any]) -> float:
        """Calculate CPU percentage from container stats.
        
        Args:
            stats: Container stats dictionary
            
        Returns:
            CPU percentage
        """
        try:
            cpu_stats = stats.get("cpu_stats", {})
            precpu_stats = stats.get("precpu_stats", {})
            
            cpu_delta = (
                cpu_stats.get("cpu_usage", {}).get("total_usage", 0)
                - precpu_stats.get("cpu_usage", {}).get("total_usage", 0)
            )
            system_delta = (
                cpu_stats.get("system_cpu_usage", 0)
                - precpu_stats.get("system_cpu_usage", 0)
            )
            
            if system_delta > 0 and cpu_delta > 0:
                cpu_count = len(cpu_stats.get("cpu_usage", {}).get("percpu_usage", [1]))
                return (cpu_delta / system_delta) * cpu_count * 100.0
        except Exception:
            pass
        return 0.0

    async def cleanup(self) -> None:
        """Cleanup all active containers and resources."""
        logger.info(f"Cleaning up {len(self._active_containers)} active containers")
        
        for execution_id, container in list(self._active_containers.items()):
            try:
                await asyncio.to_thread(container.remove, force=True)
                logger.debug(f"Removed container for execution: {execution_id}")
            except Exception as e:
                logger.warning(f"Failed to remove container {execution_id}: {e}")
        
        self._active_containers.clear()

    async def __aenter__(self) -> "SandboxExecutor":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.cleanup()


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

async def execute_in_sandbox(
    code: str,
    zone: AutonomyZone = AutonomyZone.SAFE,
    language: str = "python",
    **config_overrides: Any,
) -> ExecutionResult:
    """Convenience function for one-off sandbox execution.
    
    Args:
        code: Code to execute
        zone: Autonomy zone
        language: Programming language
        **config_overrides: Additional config overrides
        
    Returns:
        Execution result
    """
    # Check FORBIDDEN zone first - no need to create executor
    if zone == AutonomyZone.FORBIDDEN:
        return ExecutionResult(
            execution_id=str(uuid.uuid4()),
            status=ExecutionStatus.FORBIDDEN,
            autonomy_zone=AutonomyZone.FORBIDDEN,
            error_message=f"Execution forbidden in zone: {AutonomyZone.FORBIDDEN}",
        )
    
    config = SandboxConfig.from_zone(zone, **config_overrides)
    async with SandboxExecutor(config=config) as executor:
        return await executor.execute(code, language=language)


# ============================================================================
# BUILT-IN TOOLS
# ============================================================================

def create_default_tool_registry() -> ToolRegistry:
    """Create registry with default built-in tools.
    
    Returns:
        Configured ToolRegistry with safe built-in tools
    """
    registry = ToolRegistry()
    
    # Safe tools
    registry.register(ToolDefinition(
        name="echo",
        description="Echo input back as output",
        autonomy_zone=AutonomyZone.SAFE,
        parameters={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message to echo"},
            },
            "required": ["message"],
        },
        timeout=5,
        rate_limit=100,
    ))
    
    registry.register(ToolDefinition(
        name="calculate",
        description="Perform mathematical calculations",
        autonomy_zone=AutonomyZone.SAFE,
        parameters={
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "Math expression to evaluate"},
            },
            "required": ["expression"],
        },
        timeout=10,
        rate_limit=60,
    ))
    
    # Moderate tools
    registry.register(ToolDefinition(
        name="http_request",
        description="Make HTTP requests to external URLs",
        autonomy_zone=AutonomyZone.MODERATE,
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "format": "uri"},
                "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"]},
                "headers": {"type": "object"},
                "body": {"type": "string"},
            },
            "required": ["url"],
        },
        timeout=30,
        rate_limit=10,
    ))
    
    # Restricted tools
    registry.register(ToolDefinition(
        name="file_write",
        description="Write content to sandbox filesystem",
        autonomy_zone=AutonomyZone.RESTRICTED,
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
        timeout=30,
        rate_limit=10,
    ))
    
    registry.register(ToolDefinition(
        name="shell_exec",
        description="Execute shell commands (dangerous)",
        autonomy_zone=AutonomyZone.RESTRICTED,
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
            },
            "required": ["command"],
        },
        timeout=60,
        rate_limit=5,
    ))
    
    return registry


# ============================================================================
# MODULE EXPORTS
# ============================================================================

__all__ = [
    # Enums
    "AutonomyZone",
    "ExecutionStatus",
    "ContainerRuntime",
    # Models
    "SandboxConfig",
    "ExecutionResult",
    "ToolResult",
    # Classes
    "ToolDefinition",
    "ToolRegistry",
    "SandboxExecutor",
    # Functions
    "execute_in_sandbox",
    "create_default_tool_registry",
    # Constants
    "ZONE_PRESETS",
]
