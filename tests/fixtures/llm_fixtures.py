"""
LLM Fixtures for AnimusForge Test Suite

Provides mock LLM responses, provider fixtures, and failover scenarios.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, AsyncGenerator, Callable
from unittest.mock import AsyncMock, MagicMock, patch
from enum import Enum
import time

import pytest
import pytest_asyncio


# ============================================================================
# Enums and Data Classes
# ============================================================================

class LLMProviderType(Enum):
    """Supported LLM provider types."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GLM = "glm"
    DEEPSEEK = "deepseek"
    MOCK = "mock"


class LLMStatus(Enum):
    """LLM provider status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    OFFLINE = "offline"


@dataclass
class MockLLMResponse:
    """Mock LLM response structure."""
    content: str
    role: str = "assistant"
    finish_reason: str = "stop"
    usage: Dict[str, int] = field(default_factory=lambda: {
        "prompt_tokens": 10, 
        "completion_tokens": 20, 
        "total_tokens": 30
    })
    model: str = "mock-model"
    provider: str = "mock"
    latency_ms: float = 100.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "role": self.role,
            "finish_reason": self.finish_reason,
            "usage": self.usage,
            "model": self.model,
            "provider": self.provider,
            "latency_ms": self.latency_ms,
            "metadata": self.metadata,
        }


@dataclass
class MockStreamChunk:
    """Mock streaming response chunk."""
    content: str
    delta: str
    finish_reason: Optional[str] = None
    index: int = 0


@dataclass
class MockLLMProviderConfig:
    """Mock provider configuration."""
    name: str
    provider_type: LLMProviderType
    model: str
    api_key: str = "test-api-key"
    base_url: str = "https://mock.local"
    is_primary: bool = False
    max_retries: int = 3
    timeout: float = 30.0
    rate_limit: int = 100


# ============================================================================
# Basic LLM Response Fixtures
# ============================================================================

@pytest.fixture
def basic_llm_response() -> MockLLMResponse:
    """Basic successful LLM response."""
    return MockLLMResponse(
        content="This is a basic mock LLM response for testing.",
        metadata={"test_type": "basic"}
    )


@pytest.fixture
def creative_llm_response() -> MockLLMResponse:
    """Creative/longer LLM response."""
    return MockLLMResponse(
        content="""# Creative Response

This is a more detailed response that includes:

1. Multiple paragraphs
2. Code examples
3. Detailed explanations

```python
def example():
    return "Hello, World!"
```

The response continues with more content to test handling of longer outputs.
""",
        usage={"prompt_tokens": 50, "completion_tokens": 150, "total_tokens": 200},
        metadata={"test_type": "creative", "style": "detailed"}
    )


@pytest.fixture
def concise_llm_response() -> MockLLMResponse:
    """Concise LLM response."""
    return MockLLMResponse(
        content="Brief response.",
        usage={"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
        metadata={"test_type": "concise"}
    )


@pytest.fixture
def streaming_chunks() -> List[MockStreamChunk]:
    """Mock streaming response chunks."""
    return [
        MockStreamChunk(content="", delta="Hello", index=0),
        MockStreamChunk(content="Hello", delta=",", index=1),
        MockStreamChunk(content="Hello,", delta=" world", index=2),
        MockStreamChunk(content="Hello, world", delta="!", index=3),
        MockStreamChunk(content="Hello, world!", delta="", finish_reason="stop", index=4),
    ]


# ============================================================================
# Provider-Specific Response Fixtures
# ============================================================================

@pytest.fixture
def openai_response() -> MockLLMResponse:
    """Mock OpenAI GPT-4 response."""
    return MockLLMResponse(
        content="OpenAI GPT-4 generated response.",
        model="gpt-4",
        provider="openai",
        usage={"prompt_tokens": 15, "completion_tokens": 25, "total_tokens": 40},
        metadata={"provider_specific": True}
    )


@pytest.fixture
def anthropic_response() -> MockLLMResponse:
    """Mock Anthropic Claude response."""
    return MockLLMResponse(
        content="Claude generated response with thoughtful analysis.",
        model="claude-3-opus",
        provider="anthropic",
        usage={"prompt_tokens": 20, "completion_tokens": 30, "total_tokens": 50},
        metadata={"provider_specific": True}
    )


@pytest.fixture
def glm_response() -> MockLLMResponse:
    """Mock GLM response."""
    return MockLLMResponse(
        content="GLM generated response.",
        model="glm-4",
        provider="glm",
        usage={"prompt_tokens": 12, "completion_tokens": 22, "total_tokens": 34},
        metadata={"provider_specific": True}
    )


@pytest.fixture
def deepseek_response() -> MockLLMResponse:
    """Mock DeepSeek response."""
    return MockLLMResponse(
        content="DeepSeek generated response.",
        model="deepseek-chat",
        provider="deepseek",
        usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        metadata={"provider_specific": True}
    )


# ============================================================================
# Conversation Fixtures
# ============================================================================

@pytest.fixture
def conversation_responses() -> List[MockLLMResponse]:
    """Series of responses for conversation testing."""
    return [
        MockLLMResponse(
            content="Hello! How can I help you today?",
            metadata={"turn": 1}
        ),
        MockLLMResponse(
            content="I understand you're asking about Python. Let me explain...",
            metadata={"turn": 2}
        ),
        MockLLMResponse(
            content="Is there anything else you'd like to know?",
            metadata={"turn": 3}
        ),
    ]


@pytest.fixture
def multi_turn_conversation() -> List[Dict[str, str]]:
    """Multi-turn conversation history."""
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is async programming?"},
        {"role": "assistant", "content": "Async programming allows concurrent execution..."},
        {"role": "user", "content": "Can you give an example?"},
        {"role": "assistant", "content": "Here's a Python example using asyncio..."},
    ]


# ============================================================================
# Error Response Fixtures
# ============================================================================

@pytest.fixture
def rate_limit_response() -> MockLLMResponse:
    """Rate limit error response."""
    return MockLLMResponse(
        content="",
        finish_reason="error",
        metadata={
            "error": "rate_limit_exceeded",
            "error_message": "Rate limit exceeded. Please retry after 60 seconds.",
            "retry_after": 60,
        }
    )


@pytest.fixture
def context_length_exceeded_response() -> MockLLMResponse:
    """Context length exceeded error."""
    return MockLLMResponse(
        content="",
        finish_reason="error",
        metadata={
            "error": "context_length_exceeded",
            "error_message": "Maximum context length exceeded.",
            "max_tokens": 4096,
            "requested_tokens": 5000,
        }
    )


@pytest.fixture
def content_filter_response() -> MockLLMResponse:
    """Content filter triggered response."""
    return MockLLMResponse(
        content="",
        finish_reason="content_filter",
        metadata={
            "error": "content_filter",
            "error_message": "Response blocked by content filter.",
            "filter_reason": "safety",
        }
    )


@pytest.fixture
def timeout_response() -> MockLLMResponse:
    """Timeout error response."""
    return MockLLMResponse(
        content="",
        finish_reason="error",
        metadata={
            "error": "timeout",
            "error_message": "Request timed out after 30 seconds.",
        }
    )


# ============================================================================
# Mock Provider Fixtures
# ============================================================================

@pytest.fixture
def mock_llm_provider(basic_llm_response: MockLLMResponse):
    """Create a basic mock LLM provider."""
    provider = MagicMock()
    provider.name = "mock-provider"
    provider.provider_type = LLMProviderType.MOCK
    provider.model = "mock-model"
    provider.status = LLMStatus.HEALTHY
    
    async def mock_generate(prompt: str, **kwargs) -> MockLLMResponse:
        return basic_llm_response
    
    async def mock_generate_stream(prompt: str, **kwargs) -> AsyncGenerator[MockStreamChunk, None]:
        for chunk in [
            MockStreamChunk(content="", delta="Test", index=0),
            MockStreamChunk(content="Test", delta=" response", index=1),
            MockStreamChunk(content="Test response", delta="", finish_reason="stop", index=2),
        ]:
            yield chunk
    
    async def mock_is_healthy() -> bool:
        return provider.status == LLMStatus.HEALTHY
    
    provider.generate = AsyncMock(side_effect=mock_generate)
    provider.generate_stream = AsyncMock(side_effect=mock_generate_stream)
    provider.is_healthy = AsyncMock(side_effect=mock_is_healthy)
    provider.get_metrics = MagicMock(return_value={
        "total_requests": 0,
        "successful_requests": 0,
        "failed_requests": 0,
        "avg_latency_ms": 0.0,
        "last_error": None,
    })
    
    return provider


@pytest.fixture
def mock_failing_provider():
    """Create a mock provider that fails."""
    provider = MagicMock()
    provider.name = "failing-provider"
    provider.status = LLMStatus.UNHEALTHY
    
    async def mock_generate_fail(prompt: str, **kwargs):
        raise ConnectionError("Provider is unavailable")
    
    provider.generate = AsyncMock(side_effect=mock_generate_fail)
    provider.is_healthy = AsyncMock(return_value=False)
    
    return provider


@pytest.fixture
def mock_slow_provider(basic_llm_response: MockLLMResponse):
    """Create a mock provider with slow responses."""
    provider = MagicMock()
    provider.name = "slow-provider"
    provider.status = LLMStatus.DEGRADED
    
    async def mock_generate_slow(prompt: str, **kwargs):
        await asyncio.sleep(5.0)  # Simulate slow response
        response = MockLLMResponse(
            content=basic_llm_response.content,
            latency_ms=5000.0,
        )
        return response
    
    provider.generate = AsyncMock(side_effect=mock_generate_slow)
    provider.is_healthy = AsyncMock(return_value=True)
    
    return provider


@pytest.fixture
def mock_rate_limited_provider(rate_limit_response: MockLLMResponse):
    """Create a mock provider that is rate limited."""
    provider = MagicMock()
    provider.name = "rate-limited-provider"
    provider.status = LLMStatus.DEGRADED
    
    call_count = 0
    
    async def mock_generate_rate_limited(prompt: str, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 3:
            return rate_limit_response
        return MockLLMResponse(content="Success after rate limit")
    
    provider.generate = AsyncMock(side_effect=mock_generate_rate_limited)
    provider.is_healthy = AsyncMock(return_value=True)
    
    return provider


# ============================================================================
# Provider Pool Fixtures
# ============================================================================

@pytest.fixture
def mock_provider_pool(
    mock_llm_provider,
    openai_response,
    anthropic_response,
):
    """Create a pool of mock providers for failover testing."""
    # Primary provider
    primary = MagicMock()
    primary.name = "primary-provider"
    primary.is_primary = True
    primary.status = LLMStatus.HEALTHY
    primary.generate = AsyncMock(return_value=openai_response)
    primary.is_healthy = AsyncMock(return_value=True)
    
    # Secondary provider
    secondary = MagicMock()
    secondary.name = "secondary-provider"
    secondary.is_primary = False
    secondary.status = LLMStatus.HEALTHY
    secondary.generate = AsyncMock(return_value=anthropic_response)
    secondary.is_healthy = AsyncMock(return_value=True)
    
    # Tertiary provider (fallback)
    tertiary = MagicMock()
    tertiary.name = "fallback-provider"
    tertiary.is_primary = False
    tertiary.status = LLMStatus.HEALTHY
    tertiary.generate = AsyncMock(return_value=MockLLMResponse(content="Fallback response"))
    tertiary.is_healthy = AsyncMock(return_value=True)
    
    return {
        "primary": primary,
        "secondary": secondary,
        "tertiary": tertiary,
        "all": [primary, secondary, tertiary],
    }


# ============================================================================
# LLM Gateway Fixtures
# ============================================================================

@pytest.fixture
def mock_llm_gateway(mock_provider_pool):
    """Create mock LLM gateway with provider pool."""
    gateway = MagicMock()
    gateway.providers = mock_provider_pool["all"]
    gateway.primary_provider = mock_provider_pool["primary"]
    gateway.current_provider_index = 0
    
    async def mock_generate(prompt: str, **kwargs):
        for provider in gateway.providers:
            if await provider.is_healthy():
                try:
                    return await provider.generate(prompt, **kwargs)
                except Exception:
                    continue
        raise Exception("All providers failed")
    
    async def mock_check_health():
        return any(p.status == LLMStatus.HEALTHY for p in gateway.providers)
    
    async def mock_failover():
        gateway.current_provider_index = (gateway.current_provider_index + 1) % len(gateway.providers)
        return gateway.providers[gateway.current_provider_index]
    
    gateway.generate = AsyncMock(side_effect=mock_generate)
    gateway.check_health = AsyncMock(side_effect=mock_check_health)
    gateway.failover = AsyncMock(side_effect=mock_failover)
    gateway.get_provider_status = MagicMock(return_value={
        p.name: {"status": p.status.value, "healthy": p.status == LLMStatus.HEALTHY}
        for p in gateway.providers
    })
    
    return gateway


# ============================================================================
# Helper Functions
# ============================================================================

def create_mock_response(
    content: str = "Mock response",
    **kwargs
) -> MockLLMResponse:
    """Factory function to create mock responses."""
    return MockLLMResponse(content=content, **kwargs)


def create_error_response(
    error_type: str,
    error_message: str,
    **kwargs
) -> MockLLMResponse:
    """Factory function to create error responses."""
    return MockLLMResponse(
        content="",
        finish_reason="error",
        metadata={
            "error": error_type,
            "error_message": error_message,
            **kwargs
        }
    )


@pytest.fixture
def llm_response_factory():
    """Provide factory for creating custom LLM responses."""
    return create_mock_response


@pytest.fixture
def llm_error_factory():
    """Provide factory for creating error responses."""
    return create_error_response
