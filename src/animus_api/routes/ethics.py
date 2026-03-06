"""Ethics and Safety API Routes."""
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, status

from ..schemas.base import ErrorResponse, PaginatedResponse
from ..schemas.ethics import (
    AuditCreateRequest,
    AuditEntry,
    AuditListResponse,
    ContentType,
    EthicsCategory,
    EthicsEvaluateRequest,
    EthicsEvaluateResponse,
    EthicsReportRequest,
    EthicsReportResponse,
    EthicsStatistics,
    EvaluationAction,
    CategoryScore,
    ViolationEntry,
    ViolationListResponse,
    ViolationSeverity,
)

router = APIRouter(prefix="/ethics", tags=["Ethics"])


# In-memory stores (replace with database in production)
_evaluations: dict[UUID, EthicsEvaluateResponse] = {}
_audits: dict[UUID, AuditEntry] = {}
_violations: dict[UUID, ViolationEntry] = {}


@router.post(
    "/evaluate",
    response_model=EthicsEvaluateResponse,
    summary="Evaluate content",
    description="Evaluate content for ethics compliance across multiple categories.",
    responses={
        200: {"description": "Evaluation completed"},
        400: {"model": ErrorResponse, "description": "Invalid evaluation request"},
    },
)
async def evaluate_content(request: EthicsEvaluateRequest) -> EthicsEvaluateResponse:
    """Evaluate content for ethics compliance."""
    import time
    import random

    evaluation_id = uuid4()
    now = datetime.utcnow()

    # Categories to evaluate
    categories = request.categories or list(EthicsCategory)

    # Simulate category scoring (replace with actual ethics evaluation in production)
    category_scores = []
    violations = []
    warnings = []

    for category in categories:
        # Simulate score based on content analysis
        score = random.uniform(0.7, 1.0)
        passed = score >= (0.8 if request.strict_mode else 0.6)

        explanation = None
        if request.include_explanation:
            if not passed:
                explanation = f"Content may not fully comply with {category.value} guidelines"
            else:
                explanation = f"Content complies with {category.value} standards"

        category_scores.append(CategoryScore(
            category=category,
            score=score,
            passed=passed,
            explanation=explanation,
        ))

        if not passed:
            violations.append(f"{category.value}_violation")

    # Calculate overall score
    overall_score = sum(cs.score for cs in category_scores) / len(category_scores)
    compliant = overall_score >= (0.8 if request.strict_mode else 0.7)

    # Determine action
    if compliant:
        action = EvaluationAction.ALLOW
    elif overall_score >= 0.5:
        action = EvaluationAction.WARN
    elif overall_score >= 0.3:
        action = EvaluationAction.MODIFY
    else:
        action = EvaluationAction.BLOCK

    # Generate recommendations
    recommendations = []
    if not compliant:
        recommendations.append("Review content for potential ethics violations")
        if overall_score < 0.5:
            recommendations.append("Consider content revision before use")

    response = EthicsEvaluateResponse(
        id=evaluation_id,
        persona_id=request.persona_id,
        compliant=compliant,
        overall_score=overall_score,
        action=action,
        category_scores=category_scores,
        violations=violations,
        warnings=warnings,
        recommendations=recommendations,
        confidence=random.uniform(0.85, 0.99),
        evaluated_at=now,
    )

    _evaluations[evaluation_id] = response

    return response


@router.post(
    "/audit",
    response_model=AuditEntry,
    status_code=status.HTTP_201_CREATED,
    summary="Create audit entry",
    description="Create an audit entry for tracking ethics-related actions.",
    responses={
        201: {"description": "Audit entry created"},
        400: {"model": ErrorResponse, "description": "Invalid audit data"},
    },
)
async def create_audit_entry(request: AuditCreateRequest) -> AuditEntry:
    """Create an audit entry."""
    audit_id = uuid4()
    now = datetime.utcnow()

    entry = AuditEntry(
        id=audit_id,
        persona_id=request.persona_id,
        action=request.action,
        category=request.category,
        details=request.details,
        outcome=request.outcome,
        risk_level=request.risk_level,
        reviewed=False,
        reviewer=None,
        review_notes=None,
        created_at=now,
    )

    _audits[audit_id] = entry

    return entry


@router.get(
    "/audit",
    response_model=AuditListResponse,
    summary="List audits",
    description="Retrieve a paginated list of audit entries.",
)
async def list_audits(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    persona_id: Optional[UUID] = Query(None, description="Filter by persona ID"),
    category: Optional[EthicsCategory] = Query(None, description="Filter by category"),
    reviewed: Optional[bool] = Query(None, description="Filter by reviewed status"),
    start_date: Optional[datetime] = Query(None, description="Filter from date"),
    end_date: Optional[datetime] = Query(None, description="Filter to date"),
) -> AuditListResponse:
    """List audit entries."""
    # Apply filters
    filtered = list(_audits.values())

    if persona_id:
        filtered = [a for a in filtered if a.persona_id == persona_id]

    if category:
        filtered = [a for a in filtered if a.category == category]

    if reviewed is not None:
        filtered = [a for a in filtered if a.reviewed == reviewed]

    if start_date:
        filtered = [a for a in filtered if a.created_at >= start_date]

    if end_date:
        filtered = [a for a in filtered if a.created_at <= end_date]

    # Sort by creation date (newest first)
    filtered.sort(key=lambda a: a.created_at, reverse=True)

    # Paginate
    total = len(filtered)
    start = (page - 1) * page_size
    end = start + page_size
    items = filtered[start:end]

    return AuditListResponse.create(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/violations",
    response_model=ViolationListResponse,
    summary="List violations",
    description="Retrieve a paginated list of ethics violations.",
)
async def list_violations(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    persona_id: Optional[UUID] = Query(None, description="Filter by persona ID"),
    category: Optional[EthicsCategory] = Query(None, description="Filter by category"),
    severity: Optional[ViolationSeverity] = Query(None, description="Filter by severity"),
    resolved: Optional[bool] = Query(None, description="Filter by resolved status"),
) -> ViolationListResponse:
    """List ethics violations."""
    # Apply filters
    filtered = list(_violations.values())

    if persona_id:
        filtered = [v for v in filtered if v.persona_id == persona_id]

    if category:
        filtered = [v for v in filtered if v.category == category]

    if severity:
        filtered = [v for v in filtered if v.severity == severity]

    if resolved is not None:
        filtered = [v for v in filtered if v.resolved == resolved]

    # Sort by creation date (newest first)
    filtered.sort(key=lambda v: v.created_at, reverse=True)

    # Paginate
    total = len(filtered)
    start = (page - 1) * page_size
    end = start + page_size
    items = filtered[start:end]

    return ViolationListResponse.create(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/report",
    response_model=EthicsReportResponse,
    summary="Generate report",
    description="Generate a comprehensive ethics report.",
    responses={
        200: {"description": "Report generated successfully"},
    },
)
async def generate_report(request: EthicsReportRequest) -> EthicsReportResponse:
    """Generate an ethics report."""
    import random

    report_id = uuid4()
    now = datetime.utcnow()

    # Determine report period
    start_date = request.start_date or (now - timedelta(days=30))
    end_date = request.end_date or now

    # Filter audits and violations
    audits = [
        a for a in _audits.values()
        if start_date <= a.created_at <= end_date
        and (request.persona_id is None or a.persona_id == request.persona_id)
    ]

    violations = [
        v for v in _violations.values()
        if start_date <= v.created_at <= end_date
        and (request.persona_id is None or v.persona_id == request.persona_id)
    ]

    evaluations = [
        e for e in _evaluations.values()
        if start_date <= e.evaluated_at <= end_date
        and (request.persona_id is None or e.persona_id == request.persona_id)
    ]

    # Calculate statistics
    total_evaluations = len(evaluations)
    compliant_count = sum(1 for e in evaluations if e.compliant)
    violation_count = len(violations)
    avg_score = sum(e.overall_score for e in evaluations) / len(evaluations) if evaluations else 1.0

    # Category scores
    category_scores = {}
    for cat in EthicsCategory:
        cat_evals = [e for e in evaluations if any(cs.category == cat for cs in e.category_scores)]
        if cat_evals:
            cat_scores = [cs.score for e in cat_evals for cs in e.category_scores if cs.category == cat]
            category_scores[cat.value] = sum(cat_scores) / len(cat_scores)
        else:
            category_scores[cat.value] = 1.0

    # Severity distribution
    severity_dist = {}
    for sev in ViolationSeverity:
        severity_dist[sev.value] = sum(1 for v in violations if v.severity == sev)

    statistics = EthicsStatistics(
        total_evaluations=total_evaluations,
        compliant_count=compliant_count,
        violation_count=violation_count,
        avg_compliance_score=avg_score,
        category_scores=category_scores,
        severity_distribution=severity_dist,
        trend_data=[],
    )

    # Generate recommendations
    recommendations = []
    if avg_score < 0.8:
        recommendations.append("Overall compliance score below target. Review ethics guidelines.")
    if violation_count > 10:
        recommendations.append("High violation count. Consider additional safeguards.")

    return EthicsReportResponse(
        report_id=report_id,
        persona_id=request.persona_id,
        generated_at=now,
        period_start=start_date,
        period_end=end_date,
        statistics=statistics,
        violations=violations if request.include_violations else [],
        audits=audits if request.include_audits else [],
        recommendations=recommendations,
        format=request.format,
    )
