"""Base schemas for AnimusForge API."""
from datetime import datetime
from typing import Any, Generic, List, Optional, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


T = TypeVar("T")


class BaseSchema(BaseModel):
    """Base schema with common configuration."""
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        use_enum_values=True,
        json_encoders={datetime: lambda v: v.isoformat()},
    )


class UUIDMixin(BaseSchema):
    """Mixin for UUID-based entities."""
    id: UUID = Field(default_factory=uuid4, description="Unique identifier")


class TimestampMixin(BaseSchema):
    """Mixin for timestamp fields."""
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")


class PaginationParams(BaseSchema):
    """Pagination parameters."""
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")


class PaginatedResponse(BaseSchema, Generic[T]):
    """Paginated response wrapper."""
    items: List[T] = Field(default_factory=list, description="List of items")
    total: int = Field(description="Total number of items")
    page: int = Field(description="Current page")
    page_size: int = Field(description="Items per page")
    pages: int = Field(description="Total number of pages")
    has_next: bool = Field(description="Has next page")
    has_prev: bool = Field(description="Has previous page")

    @classmethod
    def create(cls, items: List[T], total: int, page: int, page_size: int) -> "PaginatedResponse[T]":
        pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
            has_next=page < pages,
            has_prev=page > 1,
        )


class ErrorResponse(BaseSchema):
    """Standard error response."""
    error: str = Field(description="Error type")
    message: str = Field(description="Error message")
    detail: Optional[dict[str, Any]] = Field(default=None, description="Additional error details")
    request_id: Optional[UUID] = Field(default=None, description="Request trace ID")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")


class ValidationErrorDetail(BaseSchema):
    """Validation error detail."""
    loc: List[str] = Field(description="Error location")
    msg: str = Field(description="Error message")
    type: str = Field(description="Error type")


class ValidationErrorResponse(BaseSchema):
    """Validation error response."""
    error: str = Field(default="validation_error", description="Error type")
    message: str = Field(default="Request validation failed", description="Error message")
    details: List[ValidationErrorDetail] = Field(description="Validation errors")
    request_id: Optional[UUID] = Field(default=None, description="Request trace ID")


class HealthStatus(BaseSchema):
    """Health check status."""
    status: str = Field(description="Health status: healthy, degraded, unhealthy")
    component: str = Field(description="Component name")
    message: Optional[str] = Field(default=None, description="Status message")
    latency_ms: Optional[float] = Field(default=None, description="Response latency in milliseconds")


class SuccessResponse(BaseSchema):
    """Generic success response."""
    success: bool = Field(default=True, description="Operation success")
    message: str = Field(description="Success message")
    data: Optional[dict[str, Any]] = Field(default=None, description="Response data")
