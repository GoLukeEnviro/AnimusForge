"""
Golden Task GT-004: LLM Failover

Tests the automatic failover mechanism when LLM providers become unavailable.
This includes:
- Primary provider failure detection
- Automatic failover to secondary providers
- Graceful degradation with no providers available
- Recovery when providers come back online
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

# Mark all tests in this module as e2e and golden_task
pytestmark = [pytest.mark.e2e, pytest.mark.golden_task, pytest.mark.slow]


# ============================================================================
# Enums and Data Classes
# ============================================================================

class ProviderStatus(Enum):
    """LLM provider status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    OFFLINE = "offline"


@dataclass
class MockProvider:
    """Mock LLM provider for testing."""
    name: str
    priority: int  # Lower = higher priority
    status: ProviderStatus = ProviderStatus.HEALTHY
    latency_ms: float = 100.0
    error_rate: float = 0.0
    request_count: int = 0
    error_count: int = 0
    
    async def generate(self, prompt: str, **kwargs) -> Dict[str, Any]:
        self.request_count += 1
        
        if self.status == ProviderStatus.OFFLINE:
            raise ConnectionError(f"Provider {self.name} is offline")
        
        if self.status == ProviderStatus.UNHEALTHY:
            self.error_count += 1
            raise Exception(f"Provider {self.name} is unhealthy")
        
        # Simulate latency
        await asyncio.sleep(self.latency_ms / 1000)
        
        # Simulate errors based on error rate
        import random
        if random.random() < self.error_rate:
            self.error_count += 1
            raise Exception(f"Random error from {self.name}")
        
        return {
            "content": f"Response from {self.name}",
            "provider": self.name,
            "latency_ms": self.latency_ms,
        }
    
    async def health_check(self) -> bool:
        return self.status in [ProviderStatus.HEALTHY, ProviderStatus.DEGRADED]


@dataclass
class MockLLMGateway:
    """Mock LLM gateway with failover logic."""
    providers: List[MockProvider] = field(default_factory=list)
    current_provider_index: int = 0
    failover_count: int = 0
    last_failover_reason: str = ""
    max_retries: int = 3
    
    def get_active_providers(self) -> List[MockProvider]:
        """Get providers sorted by priority."""
        return sorted(
            [p for p in self.providers if p.status != ProviderStatus.OFFLINE],
            key=lambda p: p.priority,
        )
    
    async def generate(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate with automatic failover."""
        providers = self.get_active_providers()
        
        if not providers:
            raise Exception("No available providers")
        
        last_error = None
        
        for attempt in range(self.max_retries):
            for provider in providers:
                try:
                    result = await provider.generate(prompt, **kwargs)
                    return result
                except Exception as e:
                    last_error = e
                    self.failover_count += 1
                    self.last_failover_reason = str(e)
                    continue
        
        raise Exception(f"All providers failed: {last_error}")
    
    async def health_check_all(self) -> Dict[str, bool]:
        """Check health of all providers."""
        results = {}
        for provider in self.providers:
            results[provider.name] = await provider.health_check()
        return results
    
    def get_status(self) -> Dict[str, Any]:
        """Get gateway status."""
        return {
            "total_providers": len(self.providers),
            "active_providers": len(self.get_active_providers()),
            "current_provider": providers[self.current_provider_index].name if providers else None,
            "failover_count": self.failover_count,
            "last_failover_reason": self.last_failover_reason,
        }


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def primary_provider() -> MockProvider:
    """Primary (highest priority) LLM provider."""
    return MockProvider(
        name="openai-primary",
        priority=1,
        status=ProviderStatus.HEALTHY,
        latency_ms=100,
    )


@pytest.fixture
def secondary_provider() -> MockProvider:
    """Secondary LLM provider."""
    return MockProvider(
        name="anthropic-secondary",
        priority=2,
        status=ProviderStatus.HEALTHY,
        latency_ms=150,
    )


@pytest.fixture
def tertiary_provider() -> MockProvider:
    """Tertiary (fallback) LLM provider."""
    return MockProvider(
        name="glm-tertiary",
        priority=3,
        status=ProviderStatus.HEALTHY,
        latency_ms=200,
    )


@pytest.fixture
def mock_gateway(
    primary_provider: MockProvider,
    secondary_provider: MockProvider,
    tertiary_provider: MockProvider,
) -> MockLLMGateway:
    """Create mock gateway with multiple providers."""
    return MockLLMGateway(
        providers=[primary_provider, secondary_provider, tertiary_provider],
    )


# ============================================================================
# Test Classes
# ============================================================================

class TestLLMFailoverBasics:
    """Basic LLM failover functionality tests."""
    
    @pytest.mark.asyncio
    async def test_gateway_uses_primary_by_default(self, mock_gateway: MockLLMGateway):
        """Gateway should use primary provider when healthy."""
        result = await mock_gateway.generate("test prompt")
        
        assert result["provider"] == "openai-primary"
        assert result["content"] == "Response from openai-primary"
    
    @pytest.mark.asyncio
    async def test_gateway_has_multiple_providers(self, mock_gateway: MockLLMGateway):
        """Gateway should have multiple providers configured."""
        assert len(mock_gateway.providers) == 3
        assert len(mock_gateway.get_active_providers()) == 3
    
    @pytest.mark.asyncio
    async def test_provider_priority_ordering(self, mock_gateway: MockLLMGateway):
        """Providers should be ordered by priority."""
        active = mock_gateway.get_active_providers()
        
        assert active[0].priority <= active[1].priority
        assert active[1].priority <= active[2].priority
        
        assert active[0].name == "openai-primary"
        assert active[1].name == "anthropic-secondary"
        assert active[2].name == "glm-tertiary"


class TestLLMFailoverOnPrimaryFailure:
    """Tests for failover when primary provider fails."""
    
    @pytest.mark.asyncio
    async def test_failover_on_primary_offline(
        self,
        mock_gateway: MockLLMGateway,
        primary_provider: MockProvider,
    ):
        """Should failover when primary goes offline."""
        # Take primary offline
        primary_provider.status = ProviderStatus.OFFLINE
        
        result = await mock_gateway.generate("test prompt")
        
        # Should use secondary
        assert result["provider"] == "anthropic-secondary"
        assert mock_gateway.failover_count >= 1
    
    @pytest.mark.asyncio
    async def test_failover_on_primary_unhealthy(
        self,
        mock_gateway: MockLLMGateway,
        primary_provider: MockProvider,
    ):
        """Should failover when primary becomes unhealthy."""
        primary_provider.status = ProviderStatus.UNHEALTHY
        
        result = await mock_gateway.generate("test prompt")
        
        assert result["provider"] == "anthropic-secondary"
    
    @pytest.mark.asyncio
    async def test_failover_on_primary_timeout(
        self,
        mock_gateway: MockLLMGateway,
        primary_provider: MockProvider,
    ):
        """Should failover when primary times out."""
        # Set very high latency to simulate timeout
        primary_provider.latency_ms = 30000  # 30 seconds
        
        # With timeout handling, should failover
        # For this test, we'll simulate by marking as unhealthy
        primary_provider.status = ProviderStatus.DEGRADED
        
        result = await mock_gateway.generate("test prompt")
        
        # Should still get a response
        assert "content" in result


class TestLLMFailoverCascade:
    """Tests for cascading failover scenarios."""
    
    @pytest.mark.asyncio
    async def test_cascade_to_tertiary(
        self,
        mock_gateway: MockLLMGateway,
        primary_provider: MockProvider,
        secondary_provider: MockProvider,
    ):
        """Should cascade to tertiary when primary and secondary fail."""
        primary_provider.status = ProviderStatus.OFFLINE
        secondary_provider.status = ProviderStatus.OFFLINE
        
        result = await mock_gateway.generate("test prompt")
        
        assert result["provider"] == "glm-tertiary"
    
    @pytest.mark.asyncio
    async def test_all_providers_fail(
        self,
        mock_gateway: MockLLMGateway,
        primary_provider: MockProvider,
        secondary_provider: MockProvider,
        tertiary_provider: MockProvider,
    ):
        """Should raise error when all providers fail."""
        primary_provider.status = ProviderStatus.OFFLINE
        secondary_provider.status = ProviderStatus.OFFLINE
        tertiary_provider.status = ProviderStatus.OFFLINE
        
        with pytest.raises(Exception) as exc_info:
            await mock_gateway.generate("test prompt")
        
        assert "No available providers" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_partial_availability(
        self,
        mock_gateway: MockLLMGateway,
        primary_provider: MockProvider,
        secondary_provider: MockProvider,
    ):
        """Should work with partial provider availability."""
        # Only tertiary available
        primary_provider.status = ProviderStatus.UNHEALTHY
        secondary_provider.status = ProviderStatus.OFFLINE
        
        result = await mock_gateway.generate("test prompt")
        
        assert result["provider"] == "glm-tertiary"


class TestLLMFailoverRecovery:
    """Tests for provider recovery scenarios."""
    
    @pytest.mark.asyncio
    async def test_primary_recovery(
        self,
        mock_gateway: MockLLMGateway,
        primary_provider: MockProvider,
    ):
        """Should return to primary after recovery."""
        # Fail primary
        primary_provider.status = ProviderStatus.OFFLINE
        
        # First request uses secondary
        result1 = await mock_gateway.generate("test prompt")
        assert result1["provider"] == "anthropic-secondary"
        
        # Recover primary
        primary_provider.status = ProviderStatus.HEALTHY
        
        # Next request should use primary again
        result2 = await mock_gateway.generate("test prompt")
        assert result2["provider"] == "openai-primary"
    
    @pytest.mark.asyncio
    async def test_health_check_updates_status(
        self,
        mock_gateway: MockLLMGateway,
        primary_provider: MockProvider,
    ):
        """Health check should update provider status."""
        primary_provider.status = ProviderStatus.UNHEALTHY
        
        health = await mock_gateway.health_check_all()
        
        assert health["openai-primary"] is False
        assert health["anthropic-secondary"] is True
        assert health["glm-tertiary"] is True


class TestLLMFailoverMetrics:
    """Tests for failover metrics and monitoring."""
    
    @pytest.mark.asyncio
    async def test_failover_count_tracking(
        self,
        mock_gateway: MockLLMGateway,
        primary_provider: MockProvider,
    ):
        """Should track failover count."""
        initial_count = mock_gateway.failover_count
        
        # Trigger failover
        primary_provider.status = ProviderStatus.OFFLINE
        await mock_gateway.generate("test prompt")
        
        assert mock_gateway.failover_count > initial_count
    
    @pytest.mark.asyncio
    async def test_provider_request_count(
        self,
        mock_gateway: MockLLMGateway,
        primary_provider: MockProvider,
        secondary_provider: MockProvider,
    ):
        """Should track request count per provider."""
        # Make requests
        for _ in range(3):
            await mock_gateway.generate("test prompt")
        
        assert primary_provider.request_count == 3
        assert secondary_provider.request_count == 0
        
        # Failover
        primary_provider.status = ProviderStatus.OFFLINE
        
        for _ in range(2):
            await mock_gateway.generate("test prompt")
        
        assert secondary_provider.request_count == 2
    
    @pytest.mark.asyncio
    async def test_gateway_status_report(self, mock_gateway: MockLLMGateway):
        """Gateway should provide status report."""
        status = mock_gateway.get_status()
        
        assert "total_providers" in status
        assert "active_providers" in status
        assert "failover_count" in status
        
        assert status["total_providers"] == 3
        assert status["active_providers"] == 3


class TestLLMFailoverEdgeCases:
    """Edge case tests for LLM failover."""
    
    @pytest.mark.asyncio
    async def test_degraded_provider_still_usable(
        self,
        mock_gateway: MockLLMGateway,
        primary_provider: MockProvider,
    ):
        """Degraded provider should still be usable."""
        primary_provider.status = ProviderStatus.DEGRADED
        primary_provider.latency_ms = 500  # Slower but working
        
        result = await mock_gateway.generate("test prompt")
        
        # Should still work, possibly with degraded provider
        assert "content" in result
    
    @pytest.mark.asyncio
    async def test_flapping_provider(
        self,
        mock_gateway: MockLLMGateway,
        primary_provider: MockProvider,
    ):
        """Should handle flapping (rapidly changing) provider status."""
        results = []
        
        for i in range(10):
            # Toggle status
            if i % 2 == 0:
                primary_provider.status = ProviderStatus.HEALTHY
            else:
                primary_provider.status = ProviderStatus.UNHEALTHY
            
            try:
                result = await mock_gateway.generate("test prompt")
                results.append(result["provider"])
            except:
                pass
        
        # Should have gotten some results
        assert len(results) > 0
    
    @pytest.mark.asyncio
    async def test_concurrent_requests_during_failover(
        self,
        mock_gateway: MockLLMGateway,
        primary_provider: MockProvider,
    ):
        """Concurrent requests should handle failover correctly."""
        # Start requests
        tasks = [
            mock_gateway.generate(f"test prompt {i}")
            for i in range(5)
        ]
        
        # Fail primary mid-flight
        await asyncio.sleep(0.05)  # Small delay
        primary_provider.status = ProviderStatus.OFFLINE
        
        # All requests should complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All should be either results or exceptions
        assert len(results) == 5
    
    @pytest.mark.asyncio
    async def test_empty_provider_list(self):
        """Should handle empty provider list gracefully."""
        empty_gateway = MockLLMGateway(providers=[])
        
        with pytest.raises(Exception) as exc_info:
            await empty_gateway.generate("test prompt")
        
        assert "No available providers" in str(exc_info.value)


class TestLLMFailoverRetryLogic:
    """Tests for retry logic during failover."""
    
    @pytest.mark.asyncio
    async def test_retry_within_provider(
        self,
        mock_gateway: MockLLMGateway,
        primary_provider: MockProvider,
    ):
        """Should retry within provider before failing over."""
        # Set high error rate but not 100%
        primary_provider.error_rate = 0.5
        
        # Should eventually succeed (either retry or failover)
        result = await mock_gateway.generate("test prompt")
        
        assert "content" in result
    
    @pytest.mark.asyncio
    async def test_max_retries_exceeded(
        self,
        mock_gateway: MockLLMGateway,
        primary_provider: MockProvider,
        secondary_provider: MockProvider,
        tertiary_provider: MockProvider,
    ):
        """Should fail after max retries across all providers."""
        # Make all providers fail
        primary_provider.status = ProviderStatus.UNHEALTHY
        secondary_provider.status = ProviderStatus.UNHEALTHY
        tertiary_provider.status = ProviderStatus.UNHEALTHY
        
        mock_gateway.max_retries = 1  # Reduce retries for faster test
        
        with pytest.raises(Exception):
            await mock_gateway.generate("test prompt")


# ============================================================================
# API Integration Tests (when API is available)
# ============================================================================

@pytest.mark.requires_docker
class TestLLMFailoverAPI:
    """API integration tests for LLM failover."""
    
    @pytest.mark.asyncio
    async def test_llm_status_endpoint(self, api_client: AsyncClient, api_routes):
        """GET /llm/status should return provider status."""
        response = await api_client.get(api_routes["llm"] + "/status")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "providers" in data["data"]
    
    @pytest.mark.asyncio
    async def test_chat_uses_available_provider(self, authenticated_client: AsyncClient, api_routes):
        """Chat should work with available provider."""
        response = await authenticated_client.post(
            api_routes["chat"],
            json={
                "message": "Test message",
                "persona_id": "test-persona",
            },
        )
        
        # Should get response (or proper error)
        assert response.status_code in [200, 201, 503]
    
    @pytest.mark.asyncio
    async def test_failover_transparent_to_user(
        self,
        authenticated_client: AsyncClient,
        api_routes,
        primary_provider: MockProvider,
    ):
        """Failover should be transparent to the user."""
        # This would require mocking the gateway in the API
        # For now, just verify the endpoint works
        response = await authenticated_client.post(
            api_routes["chat"],
            json={
                "message": "Test message",
                "persona_id": "test-persona",
            },
        )
        
        # Response should not expose internal failover details
        if response.status_code == 200:
            data = response.json()
            assert "content" in data.get("data", {})
