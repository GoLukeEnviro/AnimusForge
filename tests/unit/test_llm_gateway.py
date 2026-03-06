"""Comprehensive tests for LLM Gateway - Targeting 85%+ coverage."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from animus_resilience.llm_gateway import (
    CircuitBreaker,
    CircuitState,
    RetryConfig,
    LatencyTracker,
    CostTracker,
    LLMResponse,
    LLMProvider,
    OpenAIProvider,
    AnthropicProvider,
    OllamaProvider,
    ProviderError,
    GatewayConfig,
    LLMGateway,
    create_gateway,
)


# ============== CircuitBreaker Tests ==============

class TestCircuitBreaker:
    """Test circuit breaker state transitions."""
    
    def test_initial_state_is_closed(self):
        """Circuit breaker starts in CLOSED state."""
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.is_available is True
    
    @pytest.mark.asyncio
    async def test_opens_after_threshold_failures(self):
        """Circuit opens after reaching failure threshold."""
        cb = CircuitBreaker(failure_threshold=3)
        
        for _ in range(3):
            await cb.record_failure()
        
        assert cb.state == CircuitState.OPEN
        assert cb.is_available is False
    
    @pytest.mark.asyncio
    async def test_closes_after_success_threshold_in_half_open(self):
        """Circuit closes after enough successes in HALF_OPEN state."""
        cb = CircuitBreaker(failure_threshold=2, success_threshold=2, timeout_seconds=0.1)
        
        # Open the circuit
        await cb.record_failure()
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN
        
        # Wait for timeout to transition to HALF_OPEN
        await asyncio.sleep(0.15)
        assert cb.is_available is True  # Triggers HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN
        
        # Record successes to close
        await cb.record_success()
        await cb.record_success()
        assert cb.state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_back_to_open_on_failure_in_half_open(self):
        """Circuit returns to OPEN on failure during HALF_OPEN."""
        cb = CircuitBreaker(failure_threshold=2, timeout_seconds=0.1)
        
        await cb.record_failure()
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN
        
        await asyncio.sleep(0.15)
        cb.is_available  # Trigger transition
        
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN
    
    @pytest.mark.asyncio
    async def test_success_resets_failure_count(self):
        """Success resets the failure counter."""
        cb = CircuitBreaker(failure_threshold=5)
        
        await cb.record_failure()
        await cb.record_failure()
        assert cb._failure_count == 2
        
        await cb.record_success()
        assert cb._failure_count == 0


# ============== RetryConfig Tests ==============

class TestRetryConfig:
    """Test retry configuration and backoff."""
    
    def test_initial_delay(self):
        """First retry uses base delay."""
        config = RetryConfig(base_delay_ms=100)
        delay = config.get_delay(0)
        assert delay == 0.1  # 100ms = 0.1s
    
    def test_exponential_backoff(self):
        """Delay increases exponentially."""
        config = RetryConfig(base_delay_ms=100, exponential_base=2)
        assert config.get_delay(0) == 0.1
        assert config.get_delay(1) == 0.2
        assert config.get_delay(2) == 0.4
    
    def test_max_delay_cap(self):
        """Delay is capped at max_delay."""
        config = RetryConfig(base_delay_ms=100, max_delay_ms=500)
        delay = config.get_delay(10)  # Would be 102.4s without cap
        assert delay == 0.5  # Capped at 500ms


# ============== LatencyTracker Tests ==============

class TestLatencyTracker:
    """Test latency tracking and statistics."""
    
    @pytest.mark.asyncio
    async def test_record_latency(self):
        """Latency is recorded correctly."""
        tracker = LatencyTracker()
        await tracker.record(100.0)
        await tracker.record(200.0)
        
        assert len(tracker._latencies) == 2
    
    @pytest.mark.asyncio
    async def test_window_size_limit(self):
        """Only last N latencies are kept."""
        tracker = LatencyTracker(window_size=3)
        
        for i in range(5):
            await tracker.record(float(i))
        
        assert len(tracker._latencies) == 3
        assert tracker._latencies == [2.0, 3.0, 4.0]
    
    @pytest.mark.asyncio
    async def test_average_latency(self):
        """Average latency calculation."""
        tracker = LatencyTracker()
        await tracker.record(100.0)
        await tracker.record(200.0)
        await tracker.record(300.0)
        
        assert tracker.get_average_latency() == 200.0
    
    def test_empty_tracker_returns_inf(self):
        """Empty tracker returns infinity."""
        tracker = LatencyTracker()
        assert tracker.get_average_latency() == float("inf")
    
    @pytest.mark.asyncio
    async def test_percentile_calculation(self):
        """Percentile calculation works correctly."""
        tracker = LatencyTracker()
        for i in range(1, 11):  # 1 to 10
            await tracker.record(float(i))
        
        p50 = tracker.get_percentile(50)
        p95 = tracker.get_percentile(95)
        
        assert 5 <= p50 <= 6
        assert p95 == 10


# ============== CostTracker Tests ==============

class TestCostTracker:
    """Test cost tracking and alerts."""
    
    @pytest.mark.asyncio
    async def test_record_cost(self):
        """Cost is recorded correctly."""
        tracker = CostTracker(budget_limit=100)
        await tracker.record_cost("openai", 5.0)
        await tracker.record_cost("anthropic", 3.0)
        
        costs = tracker.get_costs()
        assert costs["total_cost"] == 8.0
        assert costs["by_provider"]["openai"] == 5.0
        assert costs["by_provider"]["anthropic"] == 3.0
    
    @pytest.mark.asyncio
    async def test_cost_alert_trigger(self):
        """Alert triggers at threshold."""
        tracker = CostTracker(budget_limit=100, alert_threshold=0.8)
        alert_triggered = []
        
        async def alert_callback(cost, percent):
            alert_triggered.append((cost, percent))
        
        tracker.register_alert_callback(alert_callback)
        await tracker.record_cost("openai", 80.0)  # 80% of 100
        
        assert len(alert_triggered) == 1
        assert alert_triggered[0][0] == 80.0
        assert alert_triggered[0][1] == 80.0
    
    @pytest.mark.asyncio
    async def test_usage_percent_calculation(self):
        """Usage percentage is correct."""
        tracker = CostTracker(budget_limit=200)
        await tracker.record_cost("openai", 50.0)
        
        costs = tracker.get_costs()
        assert costs["usage_percent"] == 25.0


# ============== LLMResponse Tests ==============

class TestLLMResponse:
    """Test LLM response model."""
    
    def test_response_creation(self):
        """Response can be created with all fields."""
        response = LLMResponse(
            content="Hello",
            provider="openai",
            model="gpt-4",
            latency_ms=150.5,
            tokens_used=100,
            cost=0.01,
            metadata={"id": "123"}
        )
        
        assert response.content == "Hello"
        assert response.provider == "openai"
        assert response.model == "gpt-4"
        assert response.latency_ms == 150.5
    
    def test_response_is_frozen(self):
        """Response is immutable."""
        response = LLMResponse(
            content="Test",
            provider="test",
            model="test",
            latency_ms=100
        )
        
        with pytest.raises(Exception):
            response.content = "Changed"


# ============== Provider Tests ==============

class TestOpenAIProvider:
    """Test OpenAI provider."""
    
    def test_provider_initialization(self):
        """Provider initializes correctly."""
        provider = OpenAIProvider(api_key="test-key")
        assert provider.name == "openai"
        assert provider.default_model == "gpt-4o-mini"
        assert len(provider.models) > 0
    
    def test_supports_model(self):
        """Model support check works."""
        provider = OpenAIProvider(api_key="test-key")
        assert provider.supports_model("gpt-4") is True
        assert provider.supports_model("unknown-model") is False
    
    def test_estimate_cost(self):
        """Cost estimation works."""
        provider = OpenAIProvider(api_key="test-key")
        cost = provider.estimate_cost(1000, "gpt-4")
        assert cost == 0.03  # $0.03 per 1K tokens
    
    @pytest.mark.asyncio
    async def test_generate_success(self):
        """Successful generation returns response."""
        provider = OpenAIProvider(api_key="test-key")
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test response"}}],
            "usage": {"total_tokens": 50},
            "id": "resp-123"
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(provider, '_get_client') as mock_client:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_http
            
            response = await provider.generate("Hello")
            
            assert response.content == "Test response"
            assert response.provider == "openai"
            assert response.tokens_used == 50
    
    @pytest.mark.asyncio
    async def test_close_client(self):
        """Client closes properly."""
        provider = OpenAIProvider(api_key="test-key")
        provider._client = AsyncMock()
        provider._client.is_closed = False
        provider._client.aclose = AsyncMock()
        
        await provider.close()
        provider._client.aclose.assert_called_once()


class TestAnthropicProvider:
    """Test Anthropic provider."""
    
    def test_provider_initialization(self):
        """Provider initializes correctly."""
        provider = AnthropicProvider(api_key="test-key")
        assert provider.name == "anthropic"
        assert provider.default_model == "claude-3-5-sonnet-20241022"
    
    def test_estimate_cost(self):
        """Cost estimation works."""
        provider = AnthropicProvider(api_key="test-key")
        cost = provider.estimate_cost(1000, "claude-3-opus-20240229")
        assert cost == 0.015
    
    @pytest.mark.asyncio
    async def test_generate_success(self):
        """Successful generation returns response."""
        provider = AnthropicProvider(api_key="test-key")
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "content": [{"text": "Claude response"}],
            "usage": {"input_tokens": 30, "output_tokens": 20},
            "id": "msg-123"
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(provider, '_get_client') as mock_client:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_http
            
            response = await provider.generate("Hello")
            
            assert response.content == "Claude response"
            assert response.tokens_used == 50


class TestOllamaProvider:
    """Test Ollama provider."""
    
    def test_provider_initialization(self):
        """Provider initializes correctly."""
        provider = OllamaProvider(base_url="http://localhost:11434")
        assert provider.name == "ollama"
        assert provider.default_model == "llama3.1"
    
    def test_estimate_cost_is_zero(self):
        """Local inference has no cost."""
        provider = OllamaProvider()
        cost = provider.estimate_cost(1000, "llama3")
        assert cost == 0.0
    
    @pytest.mark.asyncio
    async def test_generate_success(self):
        """Successful generation returns response."""
        provider = OllamaProvider()
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": "Ollama response",
            "eval_count": 50,
            "prompt_eval_count": 30,
            "total_duration": 1000000000
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(provider, '_get_client') as mock_client:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_http
            
            response = await provider.generate("Hello")
            
            assert response.content == "Ollama response"
            assert response.tokens_used == 80
            assert response.cost == 0.0


# ============== LLMGateway Tests ==============

class TestLLMGateway:
    """Test LLM Gateway orchestration."""
    
    def test_gateway_initialization(self):
        """Gateway initializes with providers."""
        gateway = LLMGateway(
            openai_api_key="test-openai",
            anthropic_api_key="test-anthropic",
        )
        
        assert "openai" in gateway._providers
        assert "anthropic" in gateway._providers
        assert "ollama" in gateway._providers
    
    def test_add_provider(self):
        """Provider can be added."""
        gateway = LLMGateway()
        provider = OpenAIProvider(api_key="test")
        
        gateway.add_provider("custom", provider)
        
        assert "custom" in gateway._providers
    
    def test_remove_provider(self):
        """Provider can be removed."""
        gateway = LLMGateway()
        gateway.add_provider("test", OpenAIProvider(api_key="test"))
        
        gateway.remove_provider("test")
        
        assert "test" not in gateway._providers
    
    @pytest.mark.asyncio
    async def test_get_available_provider_returns_lowest_latency(self):
        """Provider with lowest latency is selected."""
        gateway = LLMGateway()
        
        # Add mock providers with different latencies
        provider1 = OpenAIProvider(api_key="test")
        await provider1.latency_tracker.record(100.0)
        
        provider2 = AnthropicProvider(api_key="test")
        await provider2.latency_tracker.record(50.0)
        
        gateway.add_provider("slow", provider1)
        gateway.add_provider("fast", provider2)
        
        best = await gateway.get_available_provider()
        assert best == "fast"
    
    @pytest.mark.asyncio
    async def test_get_available_provider_raises_when_none_available(self):
        """Error raised when no providers available."""
        gateway = LLMGateway()
        gateway._providers.clear()
        
        with pytest.raises(ProviderError) as exc_info:
            await gateway.get_available_provider()
        
        assert "No available providers" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_generate_with_specific_provider(self):
        """Generation works with specific provider."""
        gateway = LLMGateway()
        
        mock_provider = MagicMock(spec=LLMProvider)
        mock_provider.circuit_breaker = CircuitBreaker()
        mock_provider.latency_tracker = LatencyTracker()
        mock_provider.generate = AsyncMock(return_value=LLMResponse(
            content="Test",
            provider="mock",
            model="test",
            latency_ms=100,
            tokens_used=10,
            cost=0.01
        ))
        
        gateway.add_provider("mock", mock_provider)
        
        response = await gateway.generate("Hello", provider="mock")
        
        assert response.content == "Test"
        mock_provider.generate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_generate_fails_over_on_error(self):
        """Gateway fails over to next provider on error."""
        gateway = LLMGateway()
        
        failing_provider = MagicMock(spec=LLMProvider)
        failing_provider.circuit_breaker = CircuitBreaker()
        failing_provider.latency_tracker = LatencyTracker()
        failing_provider.latency_tracker._latencies = [100]
        failing_provider.generate = AsyncMock(side_effect=Exception("Failed"))
        
        working_provider = MagicMock(spec=LLMProvider)
        working_provider.circuit_breaker = CircuitBreaker()
        working_provider.latency_tracker = LatencyTracker()
        working_provider.latency_tracker._latencies = [200]
        working_provider.generate = AsyncMock(return_value=LLMResponse(
            content="Success",
            provider="working",
            model="test",
            latency_ms=200
        ))
        
        gateway.add_provider("failing", failing_provider)
        gateway.add_provider("working", working_provider)
        
        # Clear ollama to use only our test providers
        gateway._providers = {
            "failing": failing_provider,
            "working": working_provider
        }
        gateway._circuit_breakers = {
            "failing": failing_provider.circuit_breaker,
            "working": working_provider.circuit_breaker
        }
        
        response = await gateway.generate("Test")
        
        assert response.content == "Success"
    
    @pytest.mark.asyncio
    async def test_generate_raises_when_all_providers_fail(self):
        """Error raised when all providers fail."""
        gateway = LLMGateway()
        gateway._providers.clear()
        
        failing_provider = MagicMock(spec=LLMProvider)
        failing_provider.circuit_breaker = CircuitBreaker()
        failing_provider.latency_tracker = LatencyTracker()
        failing_provider.generate = AsyncMock(side_effect=Exception("Failed"))
        
        gateway.add_provider("failing", failing_provider)
        
        with pytest.raises(ProviderError) as exc_info:
            await gateway.generate("Test")
        
        assert "All providers failed" in str(exc_info.value)
    
    def test_get_metrics(self):
        """Metrics are returned correctly."""
        gateway = LLMGateway(
            openai_api_key="test",
            anthropic_api_key="test"
        )
        
        metrics = gateway.get_metrics()
        
        assert "providers" in metrics
        assert "costs" in metrics
        assert "openai" in metrics["providers"]
        assert "anthropic" in metrics["providers"]
    
    @pytest.mark.asyncio
    async def test_cost_alert_registration(self):
        """Cost alert callback is registered."""
        gateway = LLMGateway()
        alerts = []
        
        async def alert_handler(cost, percent):
            alerts.append((cost, percent))
        
        gateway.register_cost_alert(alert_handler)
        
        await gateway._cost_tracker.record_cost("test", gateway.config.budget_limit * 0.8)
        
        assert len(alerts) == 1
    
    @pytest.mark.asyncio
    async def test_close_closes_all_providers(self):
        """Close method closes all provider connections."""
        gateway = LLMGateway()
        
        mock_provider = MagicMock()
        mock_provider.close = AsyncMock()
        gateway.add_provider("mock", mock_provider)
        
        await gateway.close()
        
        mock_provider.close.assert_called_once()


# ============== Factory Function Tests ==============

class TestCreateGateway:
    """Test gateway factory function."""
    
    def test_create_gateway_with_keys(self):
        """Gateway created with API keys."""
        gateway = create_gateway(
            openai_api_key="test-openai",
            anthropic_api_key="test-anthropic",
            budget_limit=50.0
        )
        
        assert gateway.config.budget_limit == 50.0
        assert "openai" in gateway._providers
        assert "anthropic" in gateway._providers
    
    def test_create_gateway_without_keys(self):
        """Gateway created without API keys (ollama only)."""
        gateway = create_gateway()
        
        assert "ollama" in gateway._providers
        assert "openai" not in gateway._providers
        assert "anthropic" not in gateway._providers


# ============== ProviderError Tests ==============

class TestProviderError:
    """Test provider error class."""
    
    def test_error_message_format(self):
        """Error message is formatted correctly."""
        error = ProviderError("openai", "API error")
        assert str(error) == "[openai] API error"
    
    def test_error_with_original(self):
        """Original error is preserved."""
        original = ValueError("Original error")
        error = ProviderError("anthropic", "Failed", original_error=original)
        
        assert error.provider == "anthropic"
        assert error.original_error == original


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
