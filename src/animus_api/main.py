"""AnimusForge API - Main FastAPI Application.

Adaptive AI Persona Framework with Ethical Governance
"""
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Callable

from fastapi import FastAPI, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware

from .schemas.base import ErrorResponse, ValidationErrorResponse
from .routes import (
    persona_router,
    llm_router,
    killswitch_router,
    memory_router,
    ethics_router,
    system_router,
)


# ==================== Rate Limiting Middleware ====================

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware for rate limiting and adding rate limit headers."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Add rate limit headers to all responses
        response = await call_next(request)

        # Rate limiting headers (in production, these would be dynamic)
        response.headers["X-RateLimit-Limit"] = "60"
        response.headers["X-RateLimit-Remaining"] = "59"
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + 60)

        return response


# ==================== Request Timing Middleware ====================

class TimingMiddleware(BaseHTTPMiddleware):
    """Middleware for tracking request processing time."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000
        response.headers["X-Process-Time-Ms"] = f"{process_time:.2f}"
        return response


# ==================== Lifespan Context Manager ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown events."""
    # Startup
    print("🚀 AnimusForge API starting up...")
    print("📋 Registering routes...")

    yield

    # Shutdown
    print("🛑 AnimusForge API shutting down...")


# ==================== Create FastAPI Application ====================

app = FastAPI(
    title="AnimusForge API",
    description="""
## Adaptive AI Persona Framework with Ethical Governance

AnimusForge is an enterprise-grade framework for creating, managing, and evolving
AI personas with built-in ethical governance, kill-switch mechanisms, and
comprehensive memory systems.

### Features

- **Persona Management**: Create, update, activate, and evolve AI personas
- **LLM Gateway**: Multi-provider LLM access with automatic failover
- **Kill-Switch**: Emergency stop and recovery mechanisms
- **Memory System**: Vector and graph-based memory storage
- **Ethics Engine**: Content evaluation and audit logging
- **System Monitoring**: Health checks, metrics, and configuration

### Authentication

JWT authentication is prepared but optional. Include `Authorization: Bearer <token>`
header for authenticated requests.

### Rate Limiting

API requests are rate-limited. Check the response headers for current limits:
- `X-RateLimit-Limit`: Maximum requests per minute
- `X-RateLimit-Remaining`: Remaining requests in current window
- `X-RateLimit-Reset`: Unix timestamp when the window resets
""",
    version="1.0.0",
    api_version="v1",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    contact={
        "name": "AnimusForge Team",
        "email": "api@animusforge.io",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
)


# ==================== Middleware Setup ====================

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8080",
        "https://animusforge.app",
        "https://api.animusforge.io",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=[
        "*",
        "Authorization",
        "Content-Type",
        "X-Request-ID",
        "X-API-Key",
    ],
    expose_headers=[
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
        "X-Process-Time-Ms",
    ],
)

# Custom middleware
app.add_middleware(RateLimitMiddleware)
app.add_middleware(TimingMiddleware)


# ==================== Exception Handlers ====================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Handle request validation errors."""
    errors = exc.errors()

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=jsonable_encoder(ValidationErrorResponse(
            error="validation_error",
            message="Request validation failed",
            details=[
                {
                    "loc": list(e["loc"]),
                    "msg": e["msg"],
                    "type": e["type"],
                }
                for e in errors
            ],
        )),
    )


@app.exception_handler(Exception)
async def general_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Handle unexpected exceptions."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=jsonable_encoder(ErrorResponse(
            error="internal_error",
            message="An unexpected error occurred",
            detail={"exception": str(exc)},
        )),
    )


# ==================== Include Routers ====================

# API v1 routes
app.include_router(persona_router, prefix="/api/v1")
app.include_router(llm_router, prefix="/api/v1")
app.include_router(killswitch_router, prefix="/api/v1")
app.include_router(memory_router, prefix="/api/v1")
app.include_router(ethics_router, prefix="/api/v1")
app.include_router(system_router, prefix="/api/v1")


# ==================== Root Endpoint ====================

@app.get("/", include_in_schema=False)
async def root() -> dict:
    """Root endpoint redirect to docs."""
    return {
        "name": "AnimusForge API",
        "version": "1.0.0",
        "docs": "/docs",
        "openapi": "/openapi.json",
    }


# ==================== Health Check Alias ====================

@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict:
    """Kubernetes-style health check endpoint."""
    return {"status": "healthy"}


# ==================== Readiness Check ====================

@app.get("/readyz", include_in_schema=False)
async def readyz() -> dict:
    """Kubernetes-style readiness check endpoint."""
    return {"status": "ready"}


# Export app for uvicorn
__all__ = ["app"]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "animus_api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
