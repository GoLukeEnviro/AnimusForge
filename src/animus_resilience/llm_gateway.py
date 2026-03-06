"""
AnimusForge LLM Gateway - Multi-Provider Resilience Layer

Production-ready LLM gateway with circuit breaker, retry logic,
latency-based routing, and cost management.
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Awaitable
import statistics

import httpx
from pydantic import BaseModel, Field, ConfigDict

# Configure logging
logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Failing, rejecting requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreaker:
    """
    Circuit Breaker pattern implementation.
    
    Protects against cascading failures by monitoring provider health.
    
    Attributes:
        failure_threshold: Number of failures before opening circuit
        success_threshold: Number of successes before closing circuit
        timeout_seconds: Time to wait before attempting recovery
    """
    failure_threshold: int = 5
    success_threshold: int = 3
    timeout_seconds: float = 30.0
    
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _success_count: int = field(default=0, init=False)
    _last_failure_time: Optional[float] = field(default=None, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    
    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        return self._state
    
    @property
    def is_available(self) -> bool:
        """Check if circuit allows requests."""
        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.OPEN:
            if self._last_failure_time is None:
                return False
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.timeout_seconds:
                self._state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker transitioning to HALF_OPEN")
                return True
            return False
        return True
    
    async def record_success(self) -> None:
        """Record successful request."""
        async with self._lock:
            self._failure_count = 0
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._success_count = 0
                    logger.info("Circuit breaker recovered - now CLOSED")
            elif self._state == CircuitState.OPEN:
                self._state = CircuitState.HALF_OPEN
                self._success_count = 1
    
    async def record_failure(self) -> None:
        """Record failed request."""
        async with self._lock:
            self._success_count = 0
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning("Circuit breaker recovery failed - back to OPEN")
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.error(
                    f"Circuit breaker opened after {self._failure_count} failures"
                )


@dataclass
class RetryConfig:
    """Retry configuration with exponential backoff."""
    max_attempts: int = 3
    base_delay_ms: float = 100.0
    max_delay_ms: float = 5000.0
    exponential_base: float = 2.0
    
    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt (0-indexed)."""
        delay_ms = self.base_delay_ms * (self.exponential_base ** attempt)
        return min(delay_ms, self.max_delay_ms) / 1000.0


@dataclass
class LatencyTracker:
    """Tracks provider latency for load balancing."""
    window_size: int = 10
    _latencies: List[float] = field(default_factory=list, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    
    async def record(self, latency_ms: float) -> None:
        """Record latency measurement."""
        async with self._lock:
            self._latencies.append(latency_ms)
            if len(self._latencies) > self.window_size:
                self._latencies.pop(0)
    
    def get_average_latency(self) -> float:
        """Get average latency in milliseconds."""
        if not self._latencies:
            return float("inf")
        return statistics.mean(self._latencies)
    
    def get_percentile(self, percentile: float = 95.0) -> float:
        """Get latency percentile in milliseconds."""
        if not self._latencies:
            return float("inf")
        sorted_latencies = sorted(self._latencies)
        index = int(len(sorted_latencies) * percentile / 100)
        return sorted_latencies[min(index, len(sorted_latencies) - 1)]


@dataclass
class CostTracker:
    """Tracks LLM costs and triggers alerts."""
    budget_limit: float = 100.0
    alert_threshold: float = 0.8
    _total_cost: float = field(default=0.0, init=False)
    _costs_by_provider: Dict[str, float] = field(default_factory=dict, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _alert_callbacks: List[Callable[[float, float], Awaitable[None]]] = field(
        default_factory=list, init=False
    )
    
    async def record_cost(self, provider: str, cost: float) -> None:
        """Record cost for a provider."""
        async with self._lock:
            self._total_cost += cost
            self._costs_by_provider[provider] = (
                self._costs_by_provider.get(provider, 0.0) + cost
            )
            
            if self._total_cost >= self.budget_limit * self.alert_threshold:
                await self._trigger_alert()
    
    async def _trigger_alert(self) -> None:
        """Trigger cost alert callbacks."""
        usage_percent = (self._total_cost / self.budget_limit) * 100
        logger.warning(
            f"Cost alert: {self._total_cost:.2f} USD ({usage_percent:.1f}% of budget)"
        )
        for callback in self._alert_callbacks:
            try:
                await callback(self._total_cost, usage_percent)
            except Exception as e:
                logger.error(f"Cost alert callback failed: {e}")
    
    def register_alert_callback(
        self, callback: Callable[[float, float], Awaitable[None]]
    ) -> None:
        """Register callback for cost alerts."""
        self._alert_callbacks.append(callback)
    
    def get_costs(self) -> Dict[str, Any]:
        """Get cost summary."""
        return {
            "total_cost": self._total_cost,
            "budget_limit": self.budget_limit,
            "usage_percent": (self._total_cost / self.budget_limit) * 100,
            "by_provider": dict(self._costs_by_provider),
        }


class LLMResponse(BaseModel):
    """Standardized LLM response."""
    model_config = ConfigDict(frozen=True)
    
    content: str
    provider: str
    model: str
    latency_ms: float
    tokens_used: int = 0
    cost: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    
    All provider implementations must inherit from this class
    and implement the generate method.
    """
    
    def __init__(
        self,
        name: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        models: Optional[List[str]] = None,
        default_model: Optional[str] = None,
    ) -> None:
        self.name = name
        self.api_key = api_key
        self.base_url = base_url
        self.models = models or []
        self.default_model = default_model or (models[0] if models else "default")
        self.latency_tracker = LatencyTracker()
        self.circuit_breaker = CircuitBreaker()
        
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Generate completion from the provider.
        
        Args:
            prompt: Input prompt for completion
            model: Model to use (provider-specific)
            **kwargs: Additional provider-specific parameters
            
        Returns:
            LLMResponse with generated content and metadata
            
        Raises:
            ProviderError: If generation fails
        """
        pass
    
    @abstractmethod
    def estimate_cost(self, tokens: int, model: str) -> float:
        """Estimate cost for token usage."""
        pass
    
    def supports_model(self, model: str) -> bool:
        """Check if provider supports given model."""
        return model in self.models or not self.models
    
    async def health_check(self) -> bool:
        """Check if provider is healthy."""
        return self.circuit_breaker.is_available


class OpenAIProvider(LLMProvider):
    """OpenAI provider implementation."""
    
    MODEL_COSTS = {
        "gpt-4-turbo-preview": 0.01 / 1000,
        "gpt-4": 0.03 / 1000,
        "gpt-3.5-turbo": 0.0005 / 1000,
        "gpt-4o": 0.0025 / 1000,
        "gpt-4o-mini": 0.00015 / 1000,
    }
    
    def __init__(self, api_key: str, **kwargs: Any) -> None:
        super().__init__(
            name="openai",
            api_key=api_key,
            models=list(self.MODEL_COSTS.keys()),
            default_model="gpt-4o-mini",
            **kwargs,
        )
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url="https://api.openai.com/v1",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=60.0,
            )
        return self._client
    
    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate completion using OpenAI API."""
        model = model or self.default_model
        start_time = time.monotonic()
        
        client = await self._get_client()
        
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if "temperature" in kwargs:
            payload["temperature"] = kwargs["temperature"]
        if "max_tokens" in kwargs:
            payload["max_tokens"] = kwargs["max_tokens"]
        
        response = await client.post("/chat/completions", json=payload)
        response.raise_for_status()
        
        data = response.json()
        latency_ms = (time.monotonic() - start_time) * 1000
        
        content = data["choices"][0]["message"]["content"]
        tokens = data.get("usage", {}).get("total_tokens", 0)
        cost = self.estimate_cost(tokens, model)
        
        await self.latency_tracker.record(latency_ms)
        
        return LLMResponse(
            content=content,
            provider=self.name,
            model=model,
            latency_ms=latency_ms,
            tokens_used=tokens,
            cost=cost,
            metadata={"response_id": data.get("id")},
        )
    
    def estimate_cost(self, tokens: int, model: str) -> float:
        """Estimate cost based on token usage."""
        rate = self.MODEL_COSTS.get(model, 0.01 / 1000)
        return tokens * rate
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider implementation."""
    
    MODEL_COSTS = {
        "claude-3-opus-20240229": 0.015 / 1000,
        "claude-3-sonnet-20240229": 0.003 / 1000,
        "claude-3-haiku-20240307": 0.00025 / 1000,
        "claude-3-5-sonnet-20241022": 0.003 / 1000,
    }
    
    def __init__(self, api_key: str, **kwargs: Any) -> None:
        super().__init__(
            name="anthropic",
            api_key=api_key,
            models=list(self.MODEL_COSTS.keys()),
            default_model="claude-3-5-sonnet-20241022",
            **kwargs,
        )
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url="https://api.anthropic.com/v1",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                timeout=60.0,
            )
        return self._client
    
    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate completion using Anthropic API."""
        model = model or self.default_model
        start_time = time.monotonic()
        
        client = await self._get_client()
        
        max_tokens = kwargs.pop("max_tokens", 4096)
        
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            **kwargs,
        }
        
        response = await client.post("/messages", json=payload)
        response.raise_for_status()
        
        data = response.json()
        latency_ms = (time.monotonic() - start_time) * 1000
        
        content = data["content"][0]["text"]
        tokens = data.get("usage", {}).get("input_tokens", 0) + data.get("usage", {}).get("output_tokens", 0)
        cost = self.estimate_cost(tokens, model)
        
        await self.latency_tracker.record(latency_ms)
        
        return LLMResponse(
            content=content,
            provider=self.name,
            model=model,
            latency_ms=latency_ms,
            tokens_used=tokens,
            cost=cost,
            metadata={"response_id": data.get("id")},
        )
    
    def estimate_cost(self, tokens: int, model: str) -> float:
        """Estimate cost based on token usage."""
        rate = self.MODEL_COSTS.get(model, 0.01 / 1000)
        return tokens * rate
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


class OllamaProvider(LLMProvider):
    """Ollama local provider implementation."""
    
    def __init__(self, base_url: str = "http://localhost:11434", **kwargs: Any) -> None:
        super().__init__(
            name="ollama",
            base_url=base_url,
            models=["llama3", "llama3.1", "mistral", "codellama", "deepseek-coder"],
            default_model="llama3.1",
            **kwargs,
        )
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=120.0,
            )
        return self._client
    
    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate completion using Ollama API."""
        model = model or self.default_model
        start_time = time.monotonic()
        
        client = await self._get_client()
        
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            **kwargs,
        }
        
        response = await client.post("/api/generate", json=payload)
        response.raise_for_status()
        
        data = response.json()
        latency_ms = (time.monotonic() - start_time) * 1000
        
        content = data.get("response", "")
        tokens = data.get("eval_count", 0) + data.get("prompt_eval_count", 0)
        
        await self.latency_tracker.record(latency_ms)
        
        return LLMResponse(
            content=content,
            provider=self.name,
            model=model,
            latency_ms=latency_ms,
            tokens_used=tokens,
            cost=0.0,
            metadata={
                "total_duration": data.get("total_duration"),
                "load_duration": data.get("load_duration"),
            },
        )
    
    def estimate_cost(self, tokens: int, model: str) -> float:
        """Local inference has no cost."""
        return 0.0
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


class ProviderError(Exception):
    """Error from LLM provider."""
    def __init__(self, provider: str, message: str, original_error: Optional[Exception] = None):
        self.provider = provider
        self.original_error = original_error
        super().__init__(f"[{provider}] {message}")


class GatewayConfig(BaseModel):
    """Gateway configuration."""
    model_config = ConfigDict(frozen=True)
    
    budget_limit: float = 100.0
    cost_alert_threshold: float = 0.8
    failover_timeout_seconds: float = 30.0
    preferred_providers: List[str] = Field(default_factory=list)
    max_retry_attempts: int = 3
    retry_base_delay_ms: float = 100.0
    retry_max_delay_ms: float = 5000.0


class LLMGateway:
    """
    Multi-Provider LLM Gateway with resilience patterns.
    
    Features:
    - Circuit breaker per provider
    - Retry with exponential backoff
    - Latency-based load balancing
    - Automatic failover
    - Cost tracking and alerts
    
    Usage:
        gateway = LLMGateway(config)
        gateway.add_provider("openai", openai_provider)
        gateway.add_provider("anthropic", anthropic_provider)
        
        response = await gateway.generate("Hello, world!")
    """
    
    def __init__(
        self,
        config: Optional[GatewayConfig] = None,
        openai_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        ollama_base_url: str = "http://localhost:11434",
    ) -> None:
        self.config = config or GatewayConfig()
        self._retry_config = RetryConfig(
            max_attempts=self.config.max_retry_attempts,
            base_delay_ms=self.config.retry_base_delay_ms,
            max_delay_ms=self.config.retry_max_delay_ms,
        )
        self._providers: Dict[str, LLMProvider] = {}
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._cost_tracker = CostTracker(
            budget_limit=self.config.budget_limit,
            alert_threshold=self.config.cost_alert_threshold,
        )
        self._lock = asyncio.Lock()
        
        if openai_api_key:
            self.add_provider("openai", OpenAIProvider(api_key=openai_api_key))
        if anthropic_api_key:
            self.add_provider("anthropic", AnthropicProvider(api_key=anthropic_api_key))
        self.add_provider("ollama", OllamaProvider(base_url=ollama_base_url))
    
    def add_provider(self, name: str, provider: LLMProvider) -> None:
        """
        Add a provider to the gateway.
        
        Args:
            name: Unique provider identifier
            provider: Provider instance
        """
        self._providers[name] = provider
        self._circuit_breakers[name] = provider.circuit_breaker
        logger.info(f"Added provider: {name}")
    
    def remove_provider(self, name: str) -> None:
        """Remove a provider from the gateway."""
        if name in self._providers:
            del self._providers[name]
            del self._circuit_breakers[name]
            logger.info(f"Removed provider: {name}")
    
    async def get_available_provider(self, model: Optional[str] = None) -> str:
        """
        Get the best available provider based on latency and health.
        
        Args:
            model: Optional model requirement
            
        Returns:
            Name of the best available provider
            
        Raises:
            ProviderError: If no providers are available
        """
        available = []
        
        for name, provider in self._providers.items():
            if model and not provider.supports_model(model):
                continue
            if not await provider.health_check():
                continue
            
            latency = provider.latency_tracker.get_average_latency()
            available.append((name, latency))
        
        if not available:
            raise ProviderError("gateway", "No available providers")
        
        available.sort(key=lambda x: x[1])
        
        if self.config.preferred_providers:
            for preferred in self.config.preferred_providers:
                for name, latency in available:
                    if name == preferred:
                        return name
        
        return available[0][0]
    
    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Generate completion with automatic failover.
        
        Args:
            prompt: Input prompt
            model: Model to use (optional)
            provider: Specific provider to use (optional)
            **kwargs: Additional parameters
            
        Returns:
            LLMResponse with generated content
            
        Raises:
            ProviderError: If all providers fail
        """
        if provider:
            providers_to_try = [provider]
        else:
            providers_to_try = await self._get_ordered_providers(model)
        
        last_error: Optional[Exception] = None
        
        for provider_name in providers_to_try:
            try:
                response = await self._generate_with_retry(
                    provider_name, prompt, model, **kwargs
                )
                return response
            except Exception as e:
                last_error = e
                logger.warning(f"Provider {provider_name} failed: {e}")
                await self._circuit_breakers[provider_name].record_failure()
        
        raise ProviderError(
            "gateway",
            "All providers failed",
            original_error=last_error,
        )
    
    async def _generate_with_retry(
        self,
        provider_name: str,
        prompt: str,
        model: Optional[str],
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate with retry logic."""
        provider = self._providers[provider_name]
        circuit = self._circuit_breakers[provider_name]
        
        if not circuit.is_available:
            raise ProviderError(provider_name, "Circuit breaker is open")
        
        last_error: Optional[Exception] = None
        
        for attempt in range(self._retry_config.max_attempts):
            try:
                response = await provider.generate(prompt, model, **kwargs)
                
                await circuit.record_success()
                await self._cost_tracker.record_cost(
                    provider_name, response.cost
                )
                
                return response
            except Exception as e:
                last_error = e
                
                if attempt < self._retry_config.max_attempts - 1:
                    delay = self._retry_config.get_delay(attempt)
                    logger.debug(
                        f"Retry {attempt + 1}/{self._retry_config.max_attempts} "
                        f"for {provider_name} after {delay:.2f}s"
                    )
                    await asyncio.sleep(delay)
        
        raise ProviderError(
            provider_name,
            f"Failed after {self._retry_config.max_attempts} attempts",
            original_error=last_error,
        )
    
    async def _get_ordered_providers(self, model: Optional[str] = None) -> List[str]:
        """Get providers ordered by latency."""
        providers = []
        
        for name, provider in self._providers.items():
            if model and not provider.supports_model(model):
                continue
            if not await provider.health_check():
                continue
            latency = provider.latency_tracker.get_average_latency()
            providers.append((name, latency))
        
        providers.sort(key=lambda x: x[1])
        return [p[0] for p in providers]
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get gateway metrics."""
        return {
            "providers": {
                name: {
                    "available": provider.circuit_breaker.is_available,
                    "state": provider.circuit_breaker.state.value,
                    "avg_latency_ms": provider.latency_tracker.get_average_latency(),
                    "p95_latency_ms": provider.latency_tracker.get_percentile(95),
                }
                for name, provider in self._providers.items()
            },
            "costs": self._cost_tracker.get_costs(),
        }
    
    def register_cost_alert(
        self, callback: Callable[[float, float], Awaitable[None]]
    ) -> None:
        """Register callback for cost alerts."""
        self._cost_tracker.register_alert_callback(callback)
    
    async def close(self) -> None:
        """Close all provider connections."""
        for provider in self._providers.values():
            if hasattr(provider, "close"):
                await provider.close()


def create_gateway(
    openai_api_key: Optional[str] = None,
    anthropic_api_key: Optional[str] = None,
    ollama_base_url: str = "http://localhost:11434",
    budget_limit: float = 100.0,
) -> LLMGateway:
    """
    Create configured LLM Gateway.
    
    Args:
        openai_api_key: OpenAI API key
        anthropic_api_key: Anthropic API key
        ollama_base_url: Ollama server URL
        budget_limit: Cost budget in USD
        
    Returns:
        Configured LLMGateway instance
    """
    config = GatewayConfig(budget_limit=budget_limit)
    return LLMGateway(
        config=config,
        openai_api_key=openai_api_key,
        anthropic_api_key=anthropic_api_key,
        ollama_base_url=ollama_base_url,
    )
