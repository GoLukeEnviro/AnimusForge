"""Ethics and safety schemas for content evaluation and auditing."""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from .base import BaseSchema, PaginatedResponse, UUIDMixin


class EthicsCategory(str, Enum):
    """Ethics category enumeration."""
    HARM = "harm"
    FAIRNESS = "fairness"
    PRIVACY = "privacy"
    TRANSPARENCY = "transparency"
    ACCOUNTABILITY = "accountability"
    BENEVOLENCE = "benevolence"
    AUTONOMY = "autonomy"
    TRUTHFULNESS = "truthfulness"


class ViolationSeverity(str, Enum):
    """Violation severity levels."""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ContentType(str, Enum):
    """Content type for evaluation."""
    TEXT = "text"
    CODE = "code"
    INTERACTION = "interaction"
    DECISION = "decision"
    OUTPUT = "output"
    BEHAVIOR = "behavior"


class EvaluationAction(str, Enum):
    """Recommended action from evaluation."""
    ALLOW = "allow"
    WARN = "warn"
    MODIFY = "modify"
    BLOCK = "block"
    ESCALATE = "escalate"


class EthicsEvaluateRequest(BaseSchema):
    """Request to evaluate content for ethics compliance."""
    persona_id: UUID = Field(description="Persona ID")
    content: str = Field(min_length=1, description="Content to evaluate")
    content_type: ContentType = Field(description="Content type")
    context: Dict[str, Any] = Field(default_factory=dict, description="Evaluation context")
    categories: Optional[List[EthicsCategory]] = Field(default=None, description="Specific categories to evaluate")
    strict_mode: bool = Field(default=False, description="Enable strict evaluation")
    include_explanation: bool = Field(default=True, description="Include explanations")


class CategoryScore(BaseSchema):
    """Score for a specific ethics category."""
    category: EthicsCategory = Field(description="Ethics category")
    score: float = Field(ge=0.0, le=1.0, description="Compliance score (0-1)")
    passed: bool = Field(description="Passed threshold")
    explanation: Optional[str] = Field(default=None, description="Score explanation")


class EthicsEvaluateResponse(BaseSchema):
    """Response from ethics evaluation."""
    id: UUID = Field(description="Evaluation ID")
    persona_id: UUID = Field(description="Persona ID")
    compliant: bool = Field(description="Overall compliance status")
    overall_score: float = Field(ge=0.0, le=1.0, description="Overall compliance score")
    action: EvaluationAction = Field(description="Recommended action")
    category_scores: List[CategoryScore] = Field(description="Per-category scores")
    violations: List[str] = Field(default_factory=list, description="Detected violations")
    warnings: List[str] = Field(default_factory=list, description="Warnings")
    recommendations: List[str] = Field(default_factory=list, description="Recommendations")
    confidence: float = Field(ge=0.0, le=1.0, description="Evaluation confidence")
    evaluated_at: datetime = Field(default_factory=datetime.utcnow, description="Evaluation timestamp")


class AuditCreateRequest(BaseSchema):
    """Request to create an audit entry."""
    persona_id: UUID = Field(description="Persona ID")
    action: str = Field(min_length=1, description="Audited action")
    category: EthicsCategory = Field(description="Ethics category")
    details: Dict[str, Any] = Field(default_factory=dict, description="Audit details")
    outcome: str = Field(description="Action outcome")
    risk_level: ViolationSeverity = Field(default=ViolationSeverity.LOW, description="Risk level")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class AuditEntry(UUIDMixin):
    """Audit entry response."""
    persona_id: UUID = Field(description="Persona ID")
    action: str = Field(description="Audited action")
    category: EthicsCategory = Field(description="Ethics category")
    details: Dict[str, Any] = Field(default_factory=dict, description="Audit details")
    outcome: str = Field(description="Action outcome")
    risk_level: ViolationSeverity = Field(description="Risk level")
    reviewed: bool = Field(default=False, description="Reviewed status")
    reviewer: Optional[str] = Field(default=None, description="Reviewer")
    review_notes: Optional[str] = Field(default=None, description="Review notes")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")


class AuditListResponse(PaginatedResponse[AuditEntry]):
    """Paginated audit list response."""
    pass


class ViolationEntry(BaseSchema):
    """Violation entry for tracking."""
    id: UUID = Field(description="Violation ID")
    persona_id: UUID = Field(description="Persona ID")
    category: EthicsCategory = Field(description="Ethics category")
    severity: ViolationSeverity = Field(description="Violation severity")
    description: str = Field(description="Violation description")
    content_snippet: Optional[str] = Field(default=None, description="Related content snippet")
    context: Dict[str, Any] = Field(default_factory=dict, description="Violation context")
    resolved: bool = Field(default=False, description="Resolution status")
    resolved_at: Optional[datetime] = Field(default=None, description="Resolution timestamp")
    resolution_notes: Optional[str] = Field(default=None, description="Resolution notes")
    created_at: datetime = Field(description="Detection timestamp")


class ViolationListResponse(PaginatedResponse[ViolationEntry]):
    """Paginated violation list response."""
    pass


class EthicsReportRequest(BaseSchema):
    """Request to generate ethics report."""
    persona_id: Optional[UUID] = Field(default=None, description="Specific persona ID")
    start_date: Optional[datetime] = Field(default=None, description="Report start date")
    end_date: Optional[datetime] = Field(default=None, description="Report end date")
    categories: Optional[List[EthicsCategory]] = Field(default=None, description="Filter categories")
    include_violations: bool = Field(default=True, description="Include violations")
    include_audits: bool = Field(default=True, description="Include audits")
    include_statistics: bool = Field(default=True, description="Include statistics")
    format: str = Field(default="json", description="Report format: json, pdf, html")


class EthicsStatistics(BaseSchema):
    """Ethics statistics for reporting."""
    total_evaluations: int = Field(description="Total evaluations")
    compliant_count: int = Field(description="Compliant evaluations")
    violation_count: int = Field(description="Total violations")
    avg_compliance_score: float = Field(description="Average compliance score")
    category_scores: Dict[str, float] = Field(description="Per-category average scores")
    severity_distribution: Dict[str, int] = Field(description="Violations by severity")
    trend_data: List[Dict[str, Any]] = Field(default_factory=list, description="Trend over time")


class EthicsReportResponse(BaseSchema):
    """Generated ethics report."""
    report_id: UUID = Field(description="Report ID")
    persona_id: Optional[UUID] = Field(default=None, description="Persona ID")
    generated_at: datetime = Field(default_factory=datetime.utcnow, description="Generation timestamp")
    period_start: datetime = Field(description="Report period start")
    period_end: datetime = Field(description="Report period end")
    statistics: EthicsStatistics = Field(description="Statistics summary")
    violations: List[ViolationEntry] = Field(default_factory=list, description="Violations")
    audits: List[AuditEntry] = Field(default_factory=list, description="Audit entries")
    recommendations: List[str] = Field(default_factory=list, description="Recommendations")
    format: str = Field(description="Report format")
