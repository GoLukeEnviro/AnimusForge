"""LLM Gateway schemas."""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from .base import BaseSchema, PaginatedResponse, UUIDMixin


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    GLM = "glm"
    LOCAL = "local"
    CUSTOM = "custom"


class ProviderStatus(str, Enum):
    """Provider status enumeration."""
    ENABLED = "enabled"
    DISABLED = "disabled"
    DEGRADED = "degraded"
    ERROR = "error"
    MAINTENANCE = "maintenance"


class GenerationFinishReason(str, Enum):
    """Generation finish reason."""
    STOP = "stop"
    LENGTH = "length"
    CONTENT_FILTER = "content_filter"
    ERROR = "error"
    CANCELLED = "cancelled"


class MessageRole(str, Enum):
    """Message role in conversation."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"


class ChatMessage(BaseSchema):
    """Chat message."""
    role: MessageRole = Field(description="Message role")
    content: str = Field(description="Message content")
    name: Optional[str] = Field(default=None, description="Sender name (for function calls)")


class GenerationRequest(BaseSchema):
    """Text generation request."""
    messages: List[ChatMessage] = Field(min_length=1, description="Conversation messages")
    model: Optional[str] = Field(default=None, description="Model to use")
    provider: Optional[LLMProvider] = Field(default=None, description="Provider preference")
    persona_id: Optional[UUID] = Field(default=None, description="Persona context")
    max_tokens: int = Field(default=1024, ge=1, le=128000, description="Maximum tokens to generate")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature")
    top_p: float = Field(default=0.9, ge=0.0, le=1.0, description="Top-p sampling")
    stop_sequences: Optional[List[str]] = Field(default=None, description="Stop sequences")
    stream: bool = Field(default=False, description="Enable streaming")
    response_format: Optional[Dict[str, str]] = Field(default=None, description="Response format")
    tools: Optional[List[Dict[str, Any]]] = Field(default=None, description="Available tools")
    tool_choice: Optional[str] = Field(default=None, description="Tool selection strategy")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Request metadata")


class TokenUsage(BaseSchema):
    """Token usage statistics."""
    prompt_tokens: int = Field(ge=0, description="Prompt tokens used")
    completion_tokens: int = Field(ge=0, description="Completion tokens used")
    total_tokens: int = Field(ge=0, description="Total tokens used")


class GenerationResponse(BaseSchema):
    """Text generation response."""
    id: UUID = Field(description="Generation ID")
    content: str = Field(description="Generated content")
    role: MessageRole = Field(default=MessageRole.ASSISTANT, description="Response role")
    model: str = Field(description="Model used")
    provider: LLMProvider = Field(description="Provider used")
    finish_reason: GenerationFinishReason = Field(description="Finish reason")
    usage: TokenUsage = Field(description="Token usage")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Generation timestamp")
    latency_ms: float = Field(description="Generation latency in milliseconds")
    persona_id: Optional[UUID] = Field(default=None, description="Persona context used")
    safety_flags: List[str] = Field(default_factory=list, description="Safety flags raised")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Response metadata")


class ProviderModel(BaseSchema):
    """Provider model information."""
    name: str = Field(description="Model name")
    display_name: str = Field(description="Display name")
    context_window: int = Field(description="Context window size")
    max_output_tokens: int = Field(description="Maximum output tokens")
    supports_streaming: bool = Field(description="Supports streaming")
    supports_functions: bool = Field(description="Supports function calling")
    supports_vision: bool = Field(description="Supports vision")
    pricing_input: float = Field(description="Input price per 1K tokens")
    pricing_output: float = Field(description="Output price per 1K tokens")


class ProviderInfo(BaseSchema):
    """Provider information."""
    name: LLMProvider = Field(description="Provider name")
    display_name: str = Field(description="Display name")
    status: ProviderStatus = Field(description="Current status")
    models: List[ProviderModel] = Field(default_factory=list, description="Available models")
    default_model: Optional[str] = Field(default=None, description="Default model")
    capabilities: List[str] = Field(default_factory=list, description="Provider capabilities")
    rate_limit_rpm: int = Field(description="Rate limit requests per minute")
    rate_limit_tpm: int = Field(description="Rate limit tokens per minute")


class ProviderStatusResponse(BaseSchema):
    """Provider status response."""
    provider: LLMProvider = Field(description="Provider name")
    status: ProviderStatus = Field(description="Current status")
    healthy: bool = Field(description="Health status")
    latency_ms: Optional[float] = Field(default=None, description="API latency")
    last_success: Optional[datetime] = Field(default=None, description="Last successful request")
    last_error: Optional[str] = Field(default=None, description="Last error message")
    total_requests: int = Field(default=0, description="Total requests count")
    success_rate: float = Field(default=1.0, description="Success rate (0-1)")
    quota_used: int = Field(default=0, description="Quota used")
    quota_limit: Optional[int] = Field(default=None, description="Quota limit")
    models_available: int = Field(description="Number of available models")


class ProviderEnableRequest(BaseSchema):
    """Request to enable a provider."""
    api_key: Optional[str] = Field(default=None, description="API key (if required)")
    base_url: Optional[str] = Field(default=None, description="Custom base URL")
    default_model: Optional[str] = Field(default=None, description="Default model")
    config: Dict[str, Any] = Field(default_factory=dict, description="Provider configuration")


class ProviderEnableResponse(BaseSchema):
    """Response after enabling provider."""
    provider: LLMProvider = Field(description="Provider name")
    status: ProviderStatus = Field(description="New status")
    message: str = Field(description="Status message")
    enabled_at: datetime = Field(default_factory=datetime.utcnow, description="Enable timestamp")


class ProviderDisableResponse(BaseSchema):
    """Response after disabling provider."""
    provider: LLMProvider = Field(description="Provider name")
    status: ProviderStatus = Field(description="New status")
    message: str = Field(description="Status message")
    disabled_at: datetime = Field(default_factory=datetime.utcnow, description="Disable timestamp")


class ProviderListResponse(BaseSchema):
    """List of providers response."""
    providers: List[ProviderInfo] = Field(description="Provider list")
    total: int = Field(description="Total count")
    enabled_count: int = Field(description="Enabled providers count")
