"""
API Fixtures for AnimusForge Test Suite

Provides API test clients, mock responses, and request/response fixtures.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
import json

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport, Response


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class MockAPIResponse:
    """Mock API response structure."""
    status_code: int
    content: Dict[str, Any]
    headers: Dict[str, str] = field(default_factory=dict)
    
    def json(self) -> Dict[str, Any]:
        return self.content


@dataclass
class APIRequest:
    """API request structure."""
    method: str
    path: str
    headers: Dict[str, str] = field(default_factory=dict)
    params: Dict[str, str] = field(default_factory=dict)
    json_body: Optional[Dict[str, Any]] = None
    
    def to_kwargs(self) -> Dict[str, Any]:
        kwargs = {"headers": self.headers, "params": self.params}
        if self.json_body:
            kwargs["json"] = self.json_body
        return kwargs


# ============================================================================
# API Client Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def api_client():
    """Create async HTTP client for API testing."""
    try:
        from animus_api.main import app
        
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            timeout=30.0,
        ) as client:
            yield client
    except ImportError:
        # Fallback for when app is not fully configured
        async with AsyncClient(base_url="http://test", timeout=30.0) as client:
            yield client


@pytest.fixture
def api_client_sync():
    """Create sync HTTP client for simpler tests."""
    from httpx import Client
    with Client(base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def authenticated_client(api_client: AsyncClient):
    """API client with authentication headers."""
    api_client.headers.update({
        "Authorization": "Bearer test-api-key",
        "X-Request-ID": "test-request-001",
    })
    yield api_client


# ============================================================================
# Mock Response Fixtures
# ============================================================================

@pytest.fixture
def success_response() -> MockAPIResponse:
    """Standard success response."""
    return MockAPIResponse(
        status_code=200,
        content={
            "status": "success",
            "data": {},
            "message": "Operation completed successfully",
        },
        headers={"Content-Type": "application/json"},
    )


@pytest.fixture
def created_response() -> MockAPIResponse:
    """Resource created response."""
    return MockAPIResponse(
        status_code=201,
        content={
            "status": "success",
            "data": {"id": "resource-001"},
            "message": "Resource created successfully",
        },
        headers={"Content-Type": "application/json"},
    )


@pytest.fixture
def bad_request_response() -> MockAPIResponse:
    """Bad request error response."""
    return MockAPIResponse(
        status_code=400,
        content={
            "status": "error",
            "error": {
                "code": "BAD_REQUEST",
                "message": "Invalid request parameters",
                "details": [{"field": "name", "message": "Name is required"}],
            },
        },
    )


@pytest.fixture
def unauthorized_response() -> MockAPIResponse:
    """Unauthorized error response."""
    return MockAPIResponse(
        status_code=401,
        content={
            "status": "error",
            "error": {
                "code": "UNAUTHORIZED",
                "message": "Authentication required",
            },
        },
    )


@pytest.fixture
def forbidden_response() -> MockAPIResponse:
    """Forbidden error response."""
    return MockAPIResponse(
        status_code=403,
        content={
            "status": "error",
            "error": {
                "code": "FORBIDDEN",
                "message": "Access denied",
            },
        },
    )


@pytest.fixture
def not_found_response() -> MockAPIResponse:
    """Not found error response."""
    return MockAPIResponse(
        status_code=404,
        content={
            "status": "error",
            "error": {
                "code": "NOT_FOUND",
                "message": "Resource not found",
            },
        },
    )


@pytest.fixture
def server_error_response() -> MockAPIResponse:
    """Internal server error response."""
    return MockAPIResponse(
        status_code=500,
        content={
            "status": "error",
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
            },
        },
    )


@pytest.fixture
def rate_limited_response() -> MockAPIResponse:
    """Rate limited response."""
    return MockAPIResponse(
        status_code=429,
        content={
            "status": "error",
            "error": {
                "code": "RATE_LIMITED",
                "message": "Too many requests",
                "retry_after": 60,
            },
        },
        headers={"Retry-After": "60"},
    )


# ============================================================================
# API Request Fixtures
# ============================================================================

@pytest.fixture
def sample_chat_request() -> Dict[str, Any]:
    """Sample chat request payload."""
    return {
        "message": "Hello, how can I implement async in Python?",
        "persona_id": "persona-dev-001",
        "session_id": "session-001",
        "context": {
            "source": "test",
        },
    }


@pytest.fixture
def sample_stream_request() -> Dict[str, Any]:
    """Sample streaming request payload."""
    return {
        "message": "Explain Python generators",
        "persona_id": "persona-dev-001",
        "stream": True,
    }


@pytest.fixture
def sample_persona_create_request() -> Dict[str, Any]:
    """Sample persona creation request."""
    return {
        "name": "New Test Persona",
        "description": "A newly created test persona",
        "persona_type": "assistant",
        "traits": [
            {"name": "helpfulness", "value": 0.9},
            {"name": "creativity", "value": 0.7},
        ],
        "ethics_constraints": [
            {"name": "no_harm", "severity": "critical"},
        ],
    }


@pytest.fixture
def sample_memory_store_request() -> Dict[str, Any]:
    """Sample memory store request."""
    return {
        "content": "User prefers dark mode in IDE",
        "metadata": {
            "category": "preference",
        },
        "importance": 0.7,
        "tags": ["preference", "ui"],
    }


# ============================================================================
# API Response Payloads
# ============================================================================

@pytest.fixture
def chat_response_payload() -> Dict[str, Any]:
    """Sample chat response payload."""
    return {
        "status": "success",
        "data": {
            "response": "Python async is implemented using the asyncio library...",
            "persona_id": "persona-dev-001",
            "session_id": "session-001",
            "message_id": "msg-001",
            "metadata": {
                "model": "gpt-4",
                "provider": "openai",
                "latency_ms": 250,
                "tokens_used": 150,
            },
        },
    }


@pytest.fixture
def persona_list_response() -> Dict[str, Any]:
    """Sample persona list response."""
    return {
        "status": "success",
        "data": {
            "personas": [
                {
                    "id": "persona-dev-001",
                    "name": "Developer Assistant",
                    "status": "active",
                },
                {
                    "id": "persona-creative-001",
                    "name": "Creative Writer",
                    "status": "active",
                },
            ],
            "total": 2,
            "page": 1,
            "page_size": 20,
        },
    }


@pytest.fixture
def health_check_response() -> Dict[str, Any]:
    """Health check response payload."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            "api": {"status": "healthy"},
            "llm_gateway": {"status": "healthy", "providers": 3},
            "memory": {"status": "healthy", "entries": 100},
            "kill_switch": {"status": "healthy", "triggered": False},
        },
    }


@pytest.fixture
def kill_switch_status_response() -> Dict[str, Any]:
    """Kill switch status response."""
    return {
        "status": "success",
        "data": {
            "is_active": True,
            "is_triggered": False,
            "violation_count": 0,
            "last_check": datetime.utcnow().isoformat(),
            "config": {
                "instability_threshold": 0.7,
                "check_interval": 1.0,
            },
        },
    }


@pytest.fixture
def ethics_check_response() -> Dict[str, Any]:
    """Ethics check response."""
    return {
        "status": "success",
        "data": {
            "passed": True,
            "violations": [],
            "checks_performed": ["harmful_content", "privacy_violation", "misinformation"],
        },
    }


@pytest.fixture
def ethics_violation_response() -> Dict[str, Any]:
    """Ethics violation detected response."""
    return {
        "status": "error",
        "error": {
            "code": "ETHICS_VIOLATION",
            "message": "Content blocked by ethics filter",
            "violations": [
                {
                    "type": "harmful_content",
                    "severity": "high",
                    "description": "Content could cause harm",
                }
            ],
        },
    }


# ============================================================================
# Mock HTTP Client
# ============================================================================

@pytest.fixture
def mock_http_client():
    """Create mock HTTP client with configurable responses."""
    client = MagicMock(spec=AsyncClient)
    
    async def mock_get(url: str, **kwargs) -> Response:
        return Response(
            status_code=200,
            json={"status": "success", "data": {}},
        )
    
    async def mock_post(url: str, **kwargs) -> Response:
        return Response(
            status_code=201,
            json={"status": "success", "data": {"id": "new-resource"}},
        )
    
    async def mock_put(url: str, **kwargs) -> Response:
        return Response(
            status_code=200,
            json={"status": "success", "data": {}},
        )
    
    async def mock_delete(url: str, **kwargs) -> Response:
        return Response(status_code=204)
    
    client.get = AsyncMock(side_effect=mock_get)
    client.post = AsyncMock(side_effect=mock_post)
    client.put = AsyncMock(side_effect=mock_put)
    client.delete = AsyncMock(side_effect=mock_delete)
    
    return client


# ============================================================================
# API Test Helpers
# ============================================================================

@pytest.fixture
def api_test_helper():
    """Helper for API testing assertions."""
    
    class APITestHelper:
        @staticmethod
        def assert_success_response(response: Response, expected_data: Dict = None):
            assert response.status_code in [200, 201], f"Expected success, got {response.status_code}"
            data = response.json()
            assert data.get("status") == "success", f"Expected success status, got {data.get('status')}"
            if expected_data:
                assert "data" in data
                for key, value in expected_data.items():
                    assert data["data"].get(key) == value
        
        @staticmethod
        def assert_error_response(response: Response, expected_code: str = None):
            assert response.status_code >= 400, f"Expected error, got {response.status_code}"
            data = response.json()
            assert data.get("status") == "error", f"Expected error status, got {data.get('status')}"
            if expected_code:
                assert data.get("error", {}).get("code") == expected_code
        
        @staticmethod
        def assert_validation_error(response: Response, field: str = None):
            APITestHelper.assert_error_response(response, "VALIDATION_ERROR")
            if field:
                data = response.json()
                details = data.get("error", {}).get("details", [])
                assert any(d.get("field") == field for d in details), f"Field {field} not in validation errors"
    
    return APITestHelper()


# ============================================================================
# Route Testing Fixtures
# ============================================================================

@pytest.fixture
def api_routes():
    """API route definitions for testing."""
    return {
        "health": "/api/v1/health",
        "chat": "/api/v1/chat",
        "chat_stream": "/api/v1/chat/stream",
        "personas": "/api/v1/personas",
        "persona_detail": "/api/v1/personas/{persona_id}",
        "memory": "/api/v1/memory",
        "memory_search": "/api/v1/memory/search",
        "kill_switch": "/api/v1/kill-switch",
        "ethics_check": "/api/v1/ethics/check",
        "system_status": "/api/v1/system/status",
    }


@pytest.fixture
def pagination_params() -> Dict[str, Any]:
    """Standard pagination parameters."""
    return {
        "page": 1,
        "page_size": 20,
        "sort_by": "created_at",
        "sort_order": "desc",
    }


@pytest.fixture
def filter_params() -> Dict[str, Any]:
    """Standard filter parameters."""
    return {
        "status": "active",
        "search": "",
        "tags": [],
    }
