"""LLM Gateway API Routes."""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, status

from ..schemas.base import ErrorResponse
from ..schemas.llm import (
    ChatMessage,
    GenerationFinishReason,
    GenerationRequest,
    GenerationResponse,
    LLMProvider,
    MessageRole,
    ProviderDisableResponse,
    ProviderEnableRequest,
    ProviderEnableResponse,
    ProviderInfo,
    ProviderListResponse,
    ProviderModel,
    ProviderStatus,
    ProviderStatusResponse,
    TokenUsage,
)

router = APIRouter(prefix="/llm", tags=["LLM Gateway"])


# In-memory provider store (replace with database in production)
_providers: dict[LLMProvider, ProviderInfo] = {
    LLMProvider.OPENAI: ProviderInfo(
        name=LLMProvider.OPENAI,
        display_name="OpenAI",
        status=ProviderStatus.ENABLED,
        models=[
            ProviderModel(
                name="gpt-4",
                display_name="GPT-4",
                context_window=8192,
                max_output_tokens=4096,
                supports_streaming=True,
                supports_functions=True,
                supports_vision=False,
                pricing_input=0.03,
                pricing_output=0.06,
            ),
            ProviderModel(
                name="gpt-4-turbo",
                display_name="GPT-4 Turbo",
                context_window=128000,
                max_output_tokens=4096,
                supports_streaming=True,
                supports_functions=True,
                supports_vision=True,
                pricing_input=0.01,
                pricing_output=0.03,
            ),
        ],
        default_model="gpt-4-turbo",
        capabilities=["chat", "completion", "function_calling", "vision"],
        rate_limit_rpm=500,
        rate_limit_tpm=90000,
    ),
    LLMProvider.ANTHROPIC: ProviderInfo(
        name=LLMProvider.ANTHROPIC,
        display_name="Anthropic",
        status=ProviderStatus.ENABLED,
        models=[
            ProviderModel(
                name="claude-3-opus",
                display_name="Claude 3 Opus",
                context_window=200000,
                max_output_tokens=4096,
                supports_streaming=True,
                supports_functions=True,
                supports_vision=True,
                pricing_input=0.015,
                pricing_output=0.075,
            ),
        ],
        default_model="claude-3-opus",
        capabilities=["chat", "completion", "vision"],
        rate_limit_rpm=60,
        rate_limit_tpm=40000,
    ),
    LLMProvider.DEEPSEEK: ProviderInfo(
        name=LLMProvider.DEEPSEEK,
        display_name="DeepSeek",
        status=ProviderStatus.DISABLED,
        models=[
            ProviderModel(
                name="deepseek-chat",
                display_name="DeepSeek Chat",
                context_window=32000,
                max_output_tokens=4096,
                supports_streaming=True,
                supports_functions=False,
                supports_vision=False,
                pricing_input=0.0001,
                pricing_output=0.0002,
            ),
        ],
        default_model="deepseek-chat",
        capabilities=["chat", "completion"],
        rate_limit_rpm=60,
        rate_limit_tpm=40000,
    ),
    LLMProvider.GLM: ProviderInfo(
        name=LLMProvider.GLM,
        display_name="GLM (Zhipu AI)",
        status=ProviderStatus.DISABLED,
        models=[
            ProviderModel(
                name="glm-4",
                display_name="GLM-4",
                context_window=128000,
                max_output_tokens=4096,
                supports_streaming=True,
                supports_functions=True,
                supports_vision=False,
                pricing_input=0.001,
                pricing_output=0.001,
            ),
        ],
        default_model="glm-4",
        capabilities=["chat", "completion", "function_calling"],
        rate_limit_rpm=60,
        rate_limit_tpm=60000,
    ),
}

# Provider statistics
_provider_stats: dict[LLMProvider, dict] = {
    provider: {
        "total_requests": 0,
        "successful_requests": 0,
        "failed_requests": 0,
        "last_success": None,
        "last_error": None,
    }
    for provider in _providers
}


@router.post(
    "/generate",
    response_model=GenerationResponse,
    summary="Generate text",
    description="Generate text using the LLM gateway with automatic provider selection.",
    responses={
        200: {"description": "Text generated successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        503: {"model": ErrorResponse, "description": "No providers available"},
    },
)
async def generate_text(request: GenerationRequest) -> GenerationResponse:
    """Generate text using configured LLM providers."""
    import time

    start_time = time.time()

    # Select provider
    provider = request.provider
    if provider is None:
        # Auto-select first enabled provider
        for p, info in _providers.items():
            if info.status == ProviderStatus.ENABLED:
                provider = p
                break

    if provider is None or provider not in _providers:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No LLM providers available",
        )

    provider_info = _providers[provider]
    if provider_info.status != ProviderStatus.ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Provider {provider} is not enabled",
        )

    # Select model
    model = request.model or provider_info.default_model

    # Update stats
    _provider_stats[provider]["total_requests"] += 1

    # Simulate generation (replace with actual LLM call in production)
    latency_ms = (time.time() - start_time) * 1000

    # Build response content
    content = f"[Generated response for {len(request.messages)} messages using {model}]"

    # Calculate token usage (simulated)
    prompt_tokens = sum(len(m.content.split()) for m in request.messages)
    completion_tokens = len(content.split())

    _provider_stats[provider]["successful_requests"] += 1
    _provider_stats[provider]["last_success"] = datetime.utcnow()

    return GenerationResponse(
        id=uuid4(),
        content=content,
        role=MessageRole.ASSISTANT,
        model=model,
        provider=provider,
        finish_reason=GenerationFinishReason.STOP,
        usage=TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
        latency_ms=latency_ms,
        persona_id=request.persona_id,
        metadata={
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        },
    )


@router.get(
    "/providers",
    response_model=ProviderListResponse,
    summary="List LLM providers",
    description="Retrieve a list of all configured LLM providers.",
)
async def list_providers() -> ProviderListResponse:
    """List all LLM providers."""
    providers = list(_providers.values())
    enabled_count = sum(1 for p in providers if p.status == ProviderStatus.ENABLED)

    return ProviderListResponse(
        providers=providers,
        total=len(providers),
        enabled_count=enabled_count,
    )


@router.get(
    "/providers/{provider_name}/status",
    response_model=ProviderStatusResponse,
    summary="Get provider status",
    description="Retrieve the status and health of a specific LLM provider.",
    responses={
        200: {"description": "Provider status"},
        404: {"model": ErrorResponse, "description": "Provider not found"},
    },
)
async def get_provider_status(provider_name: LLMProvider) -> ProviderStatusResponse:
    """Get status of a specific provider."""
    if provider_name not in _providers:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider {provider_name} not found",
        )

    provider = _providers[provider_name]
    stats = _provider_stats[provider_name]

    total = stats["total_requests"]
    successful = stats["successful_requests"]
    success_rate = successful / total if total > 0 else 1.0

    return ProviderStatusResponse(
        provider=provider_name,
        status=provider.status,
        healthy=provider.status == ProviderStatus.ENABLED,
        latency_ms=45.5,  # Simulated
        last_success=stats["last_success"],
        last_error=stats["last_error"],
        total_requests=total,
        success_rate=success_rate,
        quota_used=0,
        quota_limit=provider.rate_limit_tpm,
        models_available=len(provider.models),
    )


@router.post(
    "/providers/{provider_name}/enable",
    response_model=ProviderEnableResponse,
    summary="Enable provider",
    description="Enable an LLM provider for use.",
    responses={
        200: {"description": "Provider enabled successfully"},
        404: {"model": ErrorResponse, "description": "Provider not found"},
        400: {"model": ErrorResponse, "description": "Provider already enabled"},
    },
)
async def enable_provider(
    provider_name: LLMProvider,
    request: ProviderEnableRequest,
) -> ProviderEnableResponse:
    """Enable an LLM provider."""
    if provider_name not in _providers:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider {provider_name} not found",
        )

    provider = _providers[provider_name]

    if provider.status == ProviderStatus.ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider {provider_name} is already enabled",
        )

    # Update provider
    provider.status = ProviderStatus.ENABLED
    if request.default_model:
        provider.default_model = request.default_model

    return ProviderEnableResponse(
        provider=provider_name,
        status=ProviderStatus.ENABLED,
        message=f"Provider {provider_name} enabled successfully",
    )


@router.post(
    "/providers/{provider_name}/disable",
    response_model=ProviderDisableResponse,
    summary="Disable provider",
    description="Disable an LLM provider.",
    responses={
        200: {"description": "Provider disabled successfully"},
        404: {"model": ErrorResponse, "description": "Provider not found"},
        400: {"model": ErrorResponse, "description": "Provider already disabled"},
    },
)
async def disable_provider(
    provider_name: LLMProvider,
) -> ProviderDisableResponse:
    """Disable an LLM provider."""
    if provider_name not in _providers:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider {provider_name} not found",
        )

    provider = _providers[provider_name]

    if provider.status == ProviderStatus.DISABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider {provider_name} is already disabled",
        )

    # Update provider
    provider.status = ProviderStatus.DISABLED

    return ProviderDisableResponse(
        provider=provider_name,
        status=ProviderStatus.DISABLED,
        message=f"Provider {provider_name} disabled successfully",
    )
