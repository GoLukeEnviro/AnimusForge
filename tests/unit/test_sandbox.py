"""
Unit tests for AnimusForge Sandbox System
SPRINT1-003 Implementation Tests

Tests cover:
- AutonomyZone enum and restrictions
- SandboxConfig validation and presets
- ToolDefinition and ToolRegistry
- SandboxExecutor with mocked Docker
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from animus_tools.sandbox import (
    AutonomyZone,
    ContainerRuntime,
    ExecutionStatus,
    ExecutionResult,
    SandboxConfig,
    SandboxExecutor,
    ToolDefinition,
    ToolRegistry,
    ToolResult,
    ZONE_PRESETS,
    create_default_tool_registry,
    execute_in_sandbox,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_docker_client():
    """Create a mock Docker client."""
    client = MagicMock()
    client.ping = MagicMock(return_value=True)
    client.images.pull = MagicMock()
    
    # Mock container
    mock_container = MagicMock()
    mock_container.id = "test-container-id-123"
    mock_container.start = MagicMock()
    mock_container.wait = MagicMock(return_value={"StatusCode": 0})
    mock_container.kill = MagicMock()
    mock_container.remove = MagicMock()
    mock_container.logs = MagicMock(return_value=b'{"status": "success"}')
    mock_container.stats = MagicMock(return_value={
        "cpu_stats": {"cpu_usage": {"total_usage": 1000000, "percpu_usage": [500000]}},
        "precpu_stats": {"cpu_usage": {"total_usage": 0}, "system_cpu_usage": 0},
        "system_cpu_usage": 1000000,
        "memory_stats": {"usage": 1048576}  # 1 MB
    })
    
    # Mock containers collection
    client.containers.create = MagicMock(return_value=mock_container)
    client.containers.get = MagicMock(return_value=mock_container)
    
    return client, mock_container


@pytest.fixture
def tool_registry():
    """Create a tool registry with test tools."""
    registry = ToolRegistry()
    
    registry.register(ToolDefinition(
        name="test_tool_safe",
        description="A safe test tool",
        autonomy_zone=AutonomyZone.SAFE,
        parameters={
            "type": "object",
            "properties": {
                "input": {"type": "string"},
            },
            "required": ["input"],
        },
        timeout=10,
        rate_limit=60,
    ))
    
    registry.register(ToolDefinition(
        name="test_tool_moderate",
        description="A moderate test tool",
        autonomy_zone=AutonomyZone.MODERATE,
        parameters={"type": "object"},
        timeout=30,
        rate_limit=10,
    ))
    
    registry.register(ToolDefinition(
        name="test_tool_restricted",
        description="A restricted test tool",
        autonomy_zone=AutonomyZone.RESTRICTED,
        parameters={"type": "object"},
        timeout=60,
        rate_limit=5,
    ))
    
    return registry


@pytest.fixture
def sandbox_config():
    """Create a default sandbox config."""
    return SandboxConfig(
        autonomy_zone=AutonomyZone.SAFE,
        cpu_limit=2.0,
        memory_limit_mb=1024,
        disk_limit_mb=5120,
        network_enabled=True,
        timeout_seconds=300,
    )


# ============================================================================
# AUTONOMY ZONE TESTS
# ============================================================================

class TestAutonomyZone:
    """Tests for AutonomyZone enum."""
    
    def test_zone_values(self):
        """Test that all zone values are correct."""
        assert AutonomyZone.SAFE.value == "safe"
        assert AutonomyZone.MODERATE.value == "moderate"
        assert AutonomyZone.RESTRICTED.value == "restricted"
        assert AutonomyZone.FORBIDDEN.value == "forbidden"
    
    def test_zone_allows_network(self):
        """Test network access per zone."""
        assert AutonomyZone.SAFE.allows_network is True
        assert AutonomyZone.MODERATE.allows_network is True
        assert AutonomyZone.RESTRICTED.allows_network is False
        assert AutonomyZone.FORBIDDEN.allows_network is False
    
    def test_zone_allows_execution(self):
        """Test execution permission per zone."""
        assert AutonomyZone.SAFE.allows_execution is True
        assert AutonomyZone.MODERATE.allows_execution is True
        assert AutonomyZone.RESTRICTED.allows_execution is True
        assert AutonomyZone.FORBIDDEN.allows_execution is False
    
    def test_zone_string_representation(self):
        """Test string representation of zones."""
        assert str(AutonomyZone.SAFE) == "safe"
        assert str(AutonomyZone.MODERATE) == "moderate"


# ============================================================================
# SANDBOX CONFIG TESTS
# ============================================================================

class TestSandboxConfig:
    """Tests for SandboxConfig model."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = SandboxConfig()
        assert config.autonomy_zone == AutonomyZone.SAFE
        assert config.cpu_limit == 2.0
        assert config.memory_limit_mb == 1024
        assert config.network_enabled is True
        assert config.timeout_seconds == 300
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = SandboxConfig(
            autonomy_zone=AutonomyZone.RESTRICTED,
            cpu_limit=0.5,
            memory_limit_mb=256,
            network_enabled=False,
            timeout_seconds=60,
        )
        assert config.autonomy_zone == AutonomyZone.RESTRICTED
        assert config.cpu_limit == 0.5
        assert config.memory_limit_mb == 256
        assert config.network_enabled is False
    
    def test_from_zone_safe(self):
        """Test config creation from SAFE zone preset."""
        config = SandboxConfig.from_zone(AutonomyZone.SAFE)
        assert config.autonomy_zone == AutonomyZone.SAFE
        assert config.network_enabled is True
        assert config.timeout_seconds == 300
    
    def test_from_zone_moderate(self):
        """Test config creation from MODERATE zone preset."""
        config = SandboxConfig.from_zone(AutonomyZone.MODERATE)
        assert config.autonomy_zone == AutonomyZone.MODERATE
        assert config.cpu_limit == 1.0
        assert config.memory_limit_mb == 512
    
    def test_from_zone_restricted(self):
        """Test config creation from RESTRICTED zone preset."""
        config = SandboxConfig.from_zone(AutonomyZone.RESTRICTED)
        assert config.autonomy_zone == AutonomyZone.RESTRICTED
        assert config.network_enabled is False
        assert config.timeout_seconds == 60
    
    def test_from_zone_forbidden(self):
        """Test config creation from FORBIDDEN zone preset."""
        config = SandboxConfig.from_zone(AutonomyZone.FORBIDDEN)
        assert config.autonomy_zone == AutonomyZone.FORBIDDEN
        assert config.cpu_limit == 0.0
        assert config.memory_limit_mb == 0
    
    def test_from_zone_with_overrides(self):
        """Test config creation with overrides."""
        config = SandboxConfig.from_zone(
            AutonomyZone.SAFE,
            cpu_limit=4.0,
            timeout_seconds=600,
        )
        assert config.cpu_limit == 4.0
        assert config.timeout_seconds == 600
        assert config.autonomy_zone == AutonomyZone.SAFE
    
    def test_allowed_tools_validator(self):
        """Test allowed_tools validator converts string to list."""
        config = SandboxConfig(allowed_tools="tool1")
        assert config.allowed_tools == ["tool1"]
    
    def test_allowed_tools_none_becomes_empty_list(self):
        """Test that None allowed_tools becomes empty list."""
        config = SandboxConfig(allowed_tools=None)
        assert config.allowed_tools == []
    
    def test_cpu_limit_validation(self):
        """Test CPU limit bounds validation."""
        with pytest.raises(ValidationError):
            SandboxConfig(cpu_limit=-1.0)
        with pytest.raises(ValidationError):
            SandboxConfig(cpu_limit=20.0)
    
    def test_memory_limit_validation(self):
        """Test memory limit bounds validation."""
        with pytest.raises(ValidationError):
            SandboxConfig(memory_limit_mb=-100)
    
    def test_frozen_config(self):
        """Test that config is immutable (frozen)."""
        config = SandboxConfig()
        with pytest.raises(ValidationError):
            config.cpu_limit = 4.0


class TestZonePresets:
    """Tests for zone preset constants."""
    
    def test_all_zones_have_presets(self):
        """Test that all zones have defined presets."""
        for zone in AutonomyZone:
            assert zone in ZONE_PRESETS
    
    def test_preset_structure(self):
        """Test that presets have all required fields."""
        required_fields = [
            "cpu_limit", "memory_limit_mb", "disk_limit_mb",
            "network_enabled", "timeout_seconds",
        ]
        for zone, preset in ZONE_PRESETS.items():
            for field in required_fields:
                assert field in preset, f"Missing {field} in {zone} preset"


# ============================================================================
# TOOL DEFINITION TESTS
# ============================================================================

class TestToolDefinition:
    """Tests for ToolDefinition dataclass."""
    
    def test_basic_tool_definition(self):
        """Test basic tool definition creation."""
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            autonomy_zone=AutonomyZone.SAFE,
        )
        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert tool.autonomy_zone == AutonomyZone.SAFE
        assert tool.timeout == 60
        assert tool.rate_limit == 60
    
    def test_default_parameters(self):
        """Test that empty parameters get default schema."""
        tool = ToolDefinition(
            name="test",
            description="Test",
            autonomy_zone=AutonomyZone.SAFE,
        )
        assert tool.parameters == {"type": "object", "properties": {}}
    
    def test_custom_parameters(self):
        """Test custom parameter schema."""
        params = {
            "type": "object",
            "properties": {
                "url": {"type": "string", "format": "uri"},
            },
            "required": ["url"],
        }
        tool = ToolDefinition(
            name="http_get",
            description="HTTP GET request",
            autonomy_zone=AutonomyZone.MODERATE,
            parameters=params,
        )
        assert tool.parameters == params
    
    def test_validator_function(self):
        """Test custom validator function."""
        def validate_params(params: Dict[str, Any]) -> bool:
            return "url" in params and params["url"].startswith("https://")
        
        tool = ToolDefinition(
            name="secure_http",
            description="Secure HTTP only",
            autonomy_zone=AutonomyZone.SAFE,
            validator=validate_params,
        )
        
        assert tool.validator({"url": "https://example.com"}) is True
        assert tool.validator({"url": "http://example.com"}) is False
    
    def test_to_dict(self):
        """Test serialization to dictionary."""
        tool = ToolDefinition(
            name="test",
            description="Test tool",
            autonomy_zone=AutonomyZone.SAFE,
            timeout=30,
            rate_limit=10,
        )
        data = tool.to_dict()
        
        assert data["name"] == "test"
        assert data["description"] == "Test tool"
        assert data["autonomy_zone"] == "safe"
        assert data["timeout"] == 30
    
    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "name": "test",
            "description": "Test tool",
            "autonomy_zone": "moderate",
            "parameters": {},
            "timeout": 45,
            "rate_limit": 20,
        }
        tool = ToolDefinition.from_dict(data)
        
        assert tool.name == "test"
        assert tool.autonomy_zone == AutonomyZone.MODERATE
        assert tool.timeout == 45


# ============================================================================
# TOOL REGISTRY TESTS
# ============================================================================

class TestToolRegistry:
    """Tests for ToolRegistry class."""
    
    def test_register_tool(self, tool_registry):
        """Test tool registration."""
        assert tool_registry.get("test_tool_safe") is not None
        assert tool_registry.get("nonexistent") is None
    
    def test_duplicate_registration_raises(self):
        """Test that duplicate registration raises error."""
        registry = ToolRegistry()
        tool = ToolDefinition(
            name="duplicate",
            description="Test",
            autonomy_zone=AutonomyZone.SAFE,
        )
        registry.register(tool)
        
        with pytest.raises(ValueError, match="already registered"):
            registry.register(tool)
    
    def test_unregister_tool(self, tool_registry):
        """Test tool unregistration."""
        assert tool_registry.unregister("test_tool_safe") is True
        assert tool_registry.get("test_tool_safe") is None
        assert tool_registry.unregister("nonexistent") is False
    
    def test_list_tools(self, tool_registry):
        """Test listing all tools."""
        tools = tool_registry.list_tools()
        assert len(tools) == 3
    
    def test_list_tools_by_zone(self, tool_registry):
        """Test filtering tools by zone."""
        safe_tools = tool_registry.list_tools(zone=AutonomyZone.SAFE)
        assert len(safe_tools) == 1
        assert safe_tools[0].name == "test_tool_safe"
    
    def test_validate_params_no_validator(self, tool_registry):
        """Test validation without custom validator."""
        assert tool_registry.validate("test_tool_safe", {"input": "test"}) is True
        assert tool_registry.validate("nonexistent", {}) is False
    
    def test_validate_params_with_validator(self):
        """Test validation with custom validator."""
        registry = ToolRegistry()
        
        def validator(params: Dict[str, Any]) -> bool:
            return "value" in params and params["value"] > 0
        
        registry.register(ToolDefinition(
            name="validated_tool",
            description="Has validator",
            autonomy_zone=AutonomyZone.SAFE,
            validator=validator,
        ))
        
        assert registry.validate("validated_tool", {"value": 10}) is True
        assert registry.validate("validated_tool", {"value": -1}) is False
    
    def test_get_zone_for_tool(self, tool_registry):
        """Test getting zone for a tool."""
        zone = tool_registry.get_zone_for_tool("test_tool_moderate")
        assert zone == AutonomyZone.MODERATE
        assert tool_registry.get_zone_for_tool("nonexistent") is None
    
    def test_is_tool_allowed_in_zone(self, tool_registry):
        """Test tool permission in zones.
        
        SAFE tools can run in all zones (SAFE, MODERATE, RESTRICTED)
        MODERATE tools can run in MODERATE, RESTRICTED
        RESTRICTED tools can only run in RESTRICTED
        """
        # SAFE tool
        assert tool_registry.is_tool_allowed_in_zone("test_tool_safe", AutonomyZone.SAFE)
        assert tool_registry.is_tool_allowed_in_zone("test_tool_safe", AutonomyZone.MODERATE)
        assert tool_registry.is_tool_allowed_in_zone("test_tool_safe", AutonomyZone.RESTRICTED)
        
        # MODERATE tool
        assert not tool_registry.is_tool_allowed_in_zone("test_tool_moderate", AutonomyZone.SAFE)
        assert tool_registry.is_tool_allowed_in_zone("test_tool_moderate", AutonomyZone.MODERATE)
        assert tool_registry.is_tool_allowed_in_zone("test_tool_moderate", AutonomyZone.RESTRICTED)
        
        # RESTRICTED tool
        assert not tool_registry.is_tool_allowed_in_zone("test_tool_restricted", AutonomyZone.SAFE)
        assert not tool_registry.is_tool_allowed_in_zone("test_tool_restricted", AutonomyZone.MODERATE)
        assert tool_registry.is_tool_allowed_in_zone("test_tool_restricted", AutonomyZone.RESTRICTED)
    
    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Test rate limiting functionality."""
        registry = ToolRegistry()
        registry.register(ToolDefinition(
            name="limited_tool",
            description="Rate limited",
            autonomy_zone=AutonomyZone.SAFE,
            rate_limit=3,
        ))
        
        # Should allow 3 calls
        for _ in range(3):
            assert await registry.check_rate_limit("limited_tool")
        
        # 4th call should be denied
        assert not await registry.check_rate_limit("limited_tool")
    
    @pytest.mark.asyncio
    async def test_rate_limit_reset(self):
        """Test that rate limit resets after time window."""
        registry = ToolRegistry()
        registry.register(ToolDefinition(
            name="limited_tool",
            description="Rate limited",
            autonomy_zone=AutonomyZone.SAFE,
            rate_limit=2,
        ))
        
        # Use up the limit
        await registry.check_rate_limit("limited_tool")
        await registry.check_rate_limit("limited_tool")
        assert not await registry.check_rate_limit("limited_tool")
        
        # Manually clear old timestamps (simulate time passing)
        registry._rate_trackers["limited_tool"] = []
        
        # Should allow again
        assert await registry.check_rate_limit("limited_tool")


# ============================================================================
# EXECUTION RESULT TESTS
# ============================================================================

class TestExecutionResult:
    """Tests for ExecutionResult model."""
    
    def test_success_result(self):
        """Test successful execution result."""
        result = ExecutionResult(
            execution_id="test-123",
            status=ExecutionStatus.SUCCESS,
            stdout="Hello, World!",
            stderr="",
            exit_code=0,
            duration_ms=150.5,
            autonomy_zone=AutonomyZone.SAFE,
        )
        
        assert result.status == ExecutionStatus.SUCCESS
        assert result.stdout == "Hello, World!"
        assert result.exit_code == 0
    
    def test_timeout_result(self):
        """Test timeout execution result."""
        result = ExecutionResult(
            execution_id="test-456",
            status=ExecutionStatus.TIMEOUT,
            autonomy_zone=AutonomyZone.MODERATE,
            duration_ms=30000,
        )
        
        assert result.status == ExecutionStatus.TIMEOUT
        assert result.exit_code is None
    
    def test_forbidden_result(self):
        """Test forbidden execution result."""
        result = ExecutionResult(
            execution_id="test-789",
            status=ExecutionStatus.FORBIDDEN,
            autonomy_zone=AutonomyZone.FORBIDDEN,
            error_message="Execution not allowed",
        )
        
        assert result.status == ExecutionStatus.FORBIDDEN
    
    def test_result_is_frozen(self):
        """Test that result is immutable."""
        result = ExecutionResult(
            execution_id="test",
            status=ExecutionStatus.SUCCESS,
            autonomy_zone=AutonomyZone.SAFE,
        )
        
        with pytest.raises(ValidationError):
            result.status = ExecutionStatus.ERROR


class TestToolResult:
    """Tests for ToolResult model."""
    
    def test_successful_tool_result(self):
        """Test successful tool execution result."""
        result = ToolResult(
            tool_name="echo",
            success=True,
            result={"output": "test"},
            execution_id="exec-123",
            duration_ms=50.0,
            autonomy_zone=AutonomyZone.SAFE,
        )
        
        assert result.success is True
        assert result.result == {"output": "test"}
        assert result.error is None
    
    def test_failed_tool_result(self):
        """Test failed tool execution result."""
        result = ToolResult(
            tool_name="fail_tool",
            success=False,
            error="Something went wrong",
            execution_id="exec-456",
            autonomy_zone=AutonomyZone.MODERATE,
        )
        
        assert result.success is False
        assert result.error == "Something went wrong"


# ============================================================================
# SANDBOX EXECUTOR TESTS
# ============================================================================

class TestSandboxExecutor:
    """Tests for SandboxExecutor class."""
    
    def test_init_default_config(self):
        """Test executor initialization with defaults."""
        executor = SandboxExecutor()
        assert executor.config is not None
        assert executor.config.autonomy_zone == AutonomyZone.SAFE
    
    def test_init_custom_config(self, sandbox_config):
        """Test executor initialization with custom config."""
        executor = SandboxExecutor(config=sandbox_config)
        assert executor.config == sandbox_config
    
    def test_init_with_mocked_docker(self, mock_docker_client):
        """Test executor with mocked Docker client."""
        client, _ = mock_docker_client
        executor = SandboxExecutor(container_client=client)
        assert executor.container_client == client
    
    @pytest.mark.asyncio
    async def test_health_check_success(self, mock_docker_client):
        """Test health check when Docker is available."""
        client, _ = mock_docker_client
        executor = SandboxExecutor(container_client=client)
        
        healthy = await executor.health_check()
        assert healthy is True
        client.ping.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test health check when Docker is unavailable."""
        client = MagicMock()
        client.ping.side_effect = Exception("Docker unavailable")
        
        executor = SandboxExecutor(container_client=client)
        healthy = await executor.health_check()
        
        assert healthy is False
    
    @pytest.mark.asyncio
    async def test_execute_forbidden_zone(self):
        """Test execution in FORBIDDEN zone returns forbidden result."""
        config = SandboxConfig.from_zone(AutonomyZone.FORBIDDEN)
        executor = SandboxExecutor(config=config)
        
        result = await executor.execute("print('hello')")
        
        assert result.status == ExecutionStatus.FORBIDDEN
        assert "forbidden" in result.error_message.lower()
    
    @pytest.mark.asyncio
    async def test_execute_unsupported_language(self, mock_docker_client, sandbox_config):
        """Test execution with unsupported language."""
        client, _ = mock_docker_client
        executor = SandboxExecutor(config=sandbox_config, container_client=client)
        
        result = await executor.execute("code", language="unsupported")
        
        assert result.status == ExecutionStatus.ERROR
        assert "Unsupported language" in result.error_message
    
    @pytest.mark.asyncio
    async def test_execute_python_success(self, mock_docker_client, sandbox_config):
        """Test successful Python code execution."""
        client, container = mock_docker_client
        container.logs = MagicMock(side_effect=[
            b'{"result": 42}',  # stdout
            b'',  # stderr
        ])
        
        executor = SandboxExecutor(config=sandbox_config, container_client=client)
        result = await executor.execute("print(json.dumps({'result': 42}))")
        
        assert result.status == ExecutionStatus.SUCCESS
        assert result.exit_code == 0
        assert result.autonomy_zone == AutonomyZone.SAFE
        
        # Verify container was created and started
        client.containers.create.assert_called_once()
        container.start.assert_called_once()
        container.remove.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_with_timeout(self, mock_docker_client, sandbox_config):
        """Test execution timeout handling."""
        client, container = mock_docker_client
        
        # Make wait hang, then we'll timeout
        async def slow_wait():
            await asyncio.sleep(10)
            return {"StatusCode": 0}
        
        # Use sync mock that will be cancelled
        container.wait = MagicMock(side_effect=lambda: time.sleep(10))
        
        config = SandboxConfig.from_zone(AutonomyZone.SAFE, timeout_seconds=1)
        executor = SandboxExecutor(config=config, container_client=client)
        
        result = await executor.execute("while True: pass")
        
        assert result.status == ExecutionStatus.TIMEOUT
        container.kill.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_cleanup_on_error(self, mock_docker_client, sandbox_config):
        """Test that container is cleaned up even on error."""
        client, container = mock_docker_client
        container.start.side_effect = Exception("Start failed")
        
        executor = SandboxExecutor(config=sandbox_config, container_client=client)
        result = await executor.execute("print('test')")
        
        assert result.status == ExecutionStatus.ERROR
        container.remove.assert_called_once_with(force=True)
    
    @pytest.mark.asyncio
    async def test_context_manager(self, mock_docker_client, sandbox_config):
        """Test async context manager usage."""
        client, _ = mock_docker_client
        
        async with SandboxExecutor(config=sandbox_config, container_client=client) as executor:
            assert executor._initialized is True
        
        # After context exit, containers should be cleaned
        assert len(executor._active_containers) == 0
    
    def test_build_container_config(self, sandbox_config, mock_docker_client):
        """Test container configuration building."""
        client, _ = mock_docker_client
        executor = SandboxExecutor(config=sandbox_config, container_client=client)
        
        config = executor._build_container_config(
            command=["python", "-c", "print('test')"],
            env={"TEST": "value"},
        )
        
        assert config["image"] == sandbox_config.image_name
        assert config["command"] == ["python", "-c", "print('test')"]
        assert config["detach"] is True
        assert config["network_disabled"] is False
        assert "cpu_quota" in config
        assert "mem_limit" in config
        assert config["security_opt"] == ["no-new-privileges"]
        assert config["cap_drop"] == ["ALL"]
    
    def test_build_container_config_network_disabled(self, mock_docker_client):
        """Test container config with network disabled."""
        client, _ = mock_docker_client
        config = SandboxConfig.from_zone(AutonomyZone.RESTRICTED)
        executor = SandboxExecutor(config=config, container_client=client)
        
        container_config = executor._build_container_config(["echo", "test"])
        
        assert container_config["network_disabled"] is True
    
    @pytest.mark.asyncio
    async def test_execute_tool_not_found(self, sandbox_config, mock_docker_client):
        """Test tool execution when tool not found."""
        client, _ = mock_docker_client
        executor = SandboxExecutor(config=sandbox_config, container_client=client)
        
        result = await executor.execute_tool("nonexistent_tool", {})
        
        assert result.success is False
        assert "not found" in result.error
    
    @pytest.mark.asyncio
    async def test_execute_tool_zone_denied(self, mock_docker_client):
        """Test tool execution denied due to zone."""
        client, _ = mock_docker_client
        registry = create_default_tool_registry()
        
        # Try to run restricted tool in safe zone
        config = SandboxConfig.from_zone(AutonomyZone.SAFE)
        executor = SandboxExecutor(
            config=config,
            container_client=client,
            tool_registry=registry,
        )
        
        result = await executor.execute_tool("shell_exec", {"command": "ls"})
        
        assert result.success is False
        assert "not allowed" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_cleanup(self, mock_docker_client, sandbox_config):
        """Test explicit cleanup."""
        client, container = mock_docker_client
        executor = SandboxExecutor(config=sandbox_config, container_client=client)
        
        # Add a fake active container
        executor._active_containers["test-id"] = container
        
        await executor.cleanup()
        
        container.remove.assert_called_once_with(force=True)
        assert len(executor._active_containers) == 0


# ============================================================================
# DEFAULT TOOL REGISTRY TESTS
# ============================================================================

class TestDefaultToolRegistry:
    """Tests for default tool registry creation."""
    
    def test_create_default_registry(self):
        """Test creation of default tool registry."""
        registry = create_default_tool_registry()
        
        assert isinstance(registry, ToolRegistry)
        assert registry.get("echo") is not None
        assert registry.get("calculate") is not None
        assert registry.get("http_request") is not None
        assert registry.get("file_write") is not None
        assert registry.get("shell_exec") is not None
    
    def test_default_tool_zones(self):
        """Test that default tools have correct zones."""
        registry = create_default_tool_registry()
        
        assert registry.get_zone_for_tool("echo") == AutonomyZone.SAFE
        assert registry.get_zone_for_tool("calculate") == AutonomyZone.SAFE
        assert registry.get_zone_for_tool("http_request") == AutonomyZone.MODERATE
        assert registry.get_zone_for_tool("file_write") == AutonomyZone.RESTRICTED
        assert registry.get_zone_for_tool("shell_exec") == AutonomyZone.RESTRICTED


# ============================================================================
# CONVENIENCE FUNCTION TESTS
# ============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""
    
    @pytest.mark.asyncio
    async def test_execute_in_sandbox_forbidden(self):
        """Test convenience function with forbidden zone returns immediately."""
        # FORBIDDEN zone should return immediately without needing Docker
        result = await execute_in_sandbox(
            "print('test')",
            zone=AutonomyZone.FORBIDDEN,
        )
        
        assert result.status == ExecutionStatus.FORBIDDEN
    
    @pytest.mark.asyncio
    async def test_execute_in_sandbox_with_mocked_docker(self, mock_docker_client):
        """Test convenience function with mocked Docker."""
        client, container = mock_docker_client
        container.logs = MagicMock(return_value=b'test output')
        
        with patch('animus_tools.sandbox.SandboxExecutor') as MockExecutor:
            mock_executor = MagicMock()
            mock_executor.__aenter__ = AsyncMock(return_value=mock_executor)
            mock_executor.__aexit__ = AsyncMock(return_value=None)
            mock_executor.execute = AsyncMock(return_value=ExecutionResult(
                execution_id="test-123",
                status=ExecutionStatus.SUCCESS,
                stdout="test output",
                autonomy_zone=AutonomyZone.SAFE,
            ))
            MockExecutor.return_value = mock_executor
            
            result = await execute_in_sandbox("print('test')", zone=AutonomyZone.SAFE)
            
            assert result.status == ExecutionStatus.SUCCESS


# ============================================================================
# EXECUTION STATUS TESTS
# ============================================================================

class TestExecutionStatus:
    """Tests for ExecutionStatus enum."""
    
    def test_status_values(self):
        """Test all status values."""
        assert ExecutionStatus.SUCCESS.value == "success"
        assert ExecutionStatus.TIMEOUT.value == "timeout"
        assert ExecutionStatus.ERROR.value == "error"
        assert ExecutionStatus.KILLED.value == "killed"
        assert ExecutionStatus.FORBIDDEN.value == "forbidden"
        assert ExecutionStatus.RESOURCE_EXCEEDED.value == "resource_exceeded"


# ============================================================================
# CONTAINER RUNTIME TESTS
# ============================================================================

class TestContainerRuntime:
    """Tests for ContainerRuntime enum."""
    
    def test_runtime_values(self):
        """Test all runtime values."""
        assert ContainerRuntime.DOCKER.value == "docker"
        assert ContainerRuntime.GVISOR.value == "gvisor"
        assert ContainerRuntime.KATA.value == "kata"


# ============================================================================
# INTEGRATION-STYLE TESTS
# ============================================================================

class TestSandboxIntegration:
    """Integration-style tests with mocked Docker."""
    
    @pytest.mark.asyncio
    async def test_full_execution_flow(self, mock_docker_client):
        """Test full execution flow from config to result."""
        client, container = mock_docker_client
        container.logs = MagicMock(return_value=b'{"output": "Hello"}')
        
        config = SandboxConfig.from_zone(AutonomyZone.SAFE)
        registry = create_default_tool_registry()
        
        async with SandboxExecutor(
            config=config,
            container_client=client,
            tool_registry=registry,
        ) as executor:
            # Execute code
            code_result = await executor.execute("print('Hello')")
            assert code_result.status == ExecutionStatus.SUCCESS
            
            # Execute tool (echo is a SAFE tool, should work in SAFE zone)
            tool_result = await executor.execute_tool("echo", {"message": "test"})
            # Tool should succeed with mocked Docker
            assert tool_result.success is True
    
    @pytest.mark.asyncio
    async def test_zone_progression_restrictions(self, mock_docker_client):
        """Test that tools respect zone hierarchy."""
        client, _ = mock_docker_client
        registry = create_default_tool_registry()
        
        zones = [
            AutonomyZone.SAFE,
            AutonomyZone.MODERATE,
            AutonomyZone.RESTRICTED,
        ]
        
        for zone in zones:
            config = SandboxConfig.from_zone(zone)
            executor = SandboxExecutor(
                config=config,
                container_client=client,
                tool_registry=registry,
            )
            
            # Try to execute shell_exec
            result = await executor.execute_tool("shell_exec", {"command": "ls"})
            
            if zone == AutonomyZone.RESTRICTED:
                # Should succeed (mocked)
                pass
            else:
                # Should be denied
                assert result.success is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
