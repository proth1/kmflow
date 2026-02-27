"""TOM (Target Operating Model) management routes.

Provides CRUD operations for target operating models, gap analysis results,
best practices, and benchmarks.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid as _uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.deps import get_session
from src.core.audit import log_audit
from src.core.models import (
    AlignmentRunStatus,
    AuditAction,
    Benchmark,
    BestPractice,
    Engagement,
    EngagementMember,
    GapAnalysisResult,
    MaturityScore,
    ProcessMaturity,
    ProcessModel,
    TargetOperatingModel,
    TOMAlignmentResult,
    TOMAlignmentRun,
    TOMDimension,
    TOMDimensionRecord,
    TOMGapType,
    TOMVersion,
    User,
    UserRole,
)
from src.core.permissions import require_engagement_access, require_permission
from src.tom.maturity_scorer import MaturityScoringService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tom", tags=["tom"])

# Background task references to prevent GC from cancelling them
_background_tasks: set[asyncio.Task[None]] = set()


async def _check_engagement_member(session: AsyncSession, user: User, engagement_id: UUID) -> None:
    """Verify user is a member of the engagement. Platform admins bypass."""
    if user.role == UserRole.PLATFORM_ADMIN:
        return
    result = await session.execute(
        select(EngagementMember).where(
            EngagementMember.engagement_id == engagement_id,
            EngagementMember.user_id == user.id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this engagement",
        )


# -- Request/Response Schemas ------------------------------------------------


class DimensionInput(BaseModel):
    """Schema for a single TOM dimension input."""

    dimension_type: TOMDimension
    maturity_target: int = Field(..., ge=1, le=5)
    description: str | None = None


class TOMCreate(BaseModel):
    """Schema for creating a target operating model."""

    engagement_id: UUID
    name: str = Field(..., min_length=1, max_length=512)
    dimensions: list[DimensionInput] | None = None
    maturity_targets: dict[str, Any] | None = None


class TOMUpdate(BaseModel):
    """Schema for updating a TOM (PATCH)."""

    name: str | None = Field(None, min_length=1, max_length=512)
    dimensions: list[DimensionInput] | None = None
    maturity_targets: dict[str, Any] | None = None


class DimensionResponse(BaseModel):
    """Schema for a TOM dimension in responses."""

    model_config = {"from_attributes": True}

    dimension_type: TOMDimension
    maturity_target: int
    description: str | None


class TOMResponse(BaseModel):
    """Schema for TOM responses."""

    model_config = {"from_attributes": True}

    id: UUID
    engagement_id: UUID
    name: str
    version: int
    dimensions: list[DimensionResponse] | None = None
    maturity_targets: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class TOMList(BaseModel):
    """Schema for listing TOMs."""

    items: list[TOMResponse]
    total: int


class TOMVersionResponse(BaseModel):
    """Schema for a TOM version history entry."""

    model_config = {"from_attributes": True}

    version_number: int
    snapshot: dict[str, Any]
    changed_by: str | None
    created_at: datetime


class TOMVersionList(BaseModel):
    """Schema for listing TOM versions."""

    tom_id: UUID
    current_version: int
    versions: list[TOMVersionResponse]


class GapCreate(BaseModel):
    """Schema for creating a gap analysis result."""

    engagement_id: UUID
    tom_id: UUID
    gap_type: TOMGapType
    dimension: TOMDimension
    severity: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str | None = None
    recommendation: str | None = None
    business_criticality: int | None = Field(None, ge=1, le=5)
    risk_exposure: int | None = Field(None, ge=1, le=5)
    regulatory_impact: int | None = Field(None, ge=1, le=5)
    remediation_cost: int | None = Field(None, ge=1, le=5)


class GapResponse(BaseModel):
    """Schema for gap analysis result responses."""

    model_config = {"from_attributes": True}

    id: UUID
    engagement_id: UUID
    tom_id: UUID
    gap_type: TOMGapType
    dimension: TOMDimension
    severity: float
    confidence: float
    rationale: str | None
    recommendation: str | None
    priority_score: float
    composite_score: float
    business_criticality: int | None
    risk_exposure: int | None
    regulatory_impact: int | None
    remediation_cost: int | None
    created_at: Any


class GapList(BaseModel):
    """Schema for listing gap results."""

    items: list[GapResponse]
    total: int


class BestPracticeCreate(BaseModel):
    """Schema for creating a best practice."""

    domain: str = Field(..., min_length=1, max_length=255)
    industry: str = Field(..., min_length=1, max_length=255)
    description: str
    source: str | None = None
    tom_dimension: TOMDimension


class BestPracticeResponse(BaseModel):
    """Schema for best practice responses."""

    model_config = {"from_attributes": True}

    id: UUID
    domain: str
    industry: str
    description: str
    source: str | None
    tom_dimension: TOMDimension
    created_at: Any


class BenchmarkCreate(BaseModel):
    """Schema for creating a benchmark."""

    metric_name: str = Field(..., min_length=1, max_length=255)
    industry: str = Field(..., min_length=1, max_length=255)
    p25: float
    p50: float
    p75: float
    p90: float
    source: str | None = None


class BenchmarkResponse(BaseModel):
    """Schema for benchmark responses."""

    model_config = {"from_attributes": True}

    id: UUID
    metric_name: str
    industry: str
    p25: float
    p50: float
    p75: float
    p90: float
    source: str | None
    created_at: Any


# -- TOM Routes ---------------------------------------------------------------


def _tom_to_response(tom: TargetOperatingModel) -> dict[str, Any]:
    """Convert TOM ORM instance to response dict with embedded dimensions."""
    dim_list = [
        {
            "dimension_type": dr.dimension_type,
            "maturity_target": dr.maturity_target,
            "description": dr.description,
        }
        for dr in (tom.dimension_records or [])
    ]
    return {
        "id": tom.id,
        "engagement_id": tom.engagement_id,
        "name": tom.name,
        "version": tom.version,
        "dimensions": dim_list if dim_list else None,
        "maturity_targets": tom.maturity_targets,
        "created_at": tom.created_at,
        "updated_at": tom.updated_at,
    }


def _snapshot_dimensions(tom: TargetOperatingModel) -> dict[str, Any]:
    """Create a JSON-serialisable snapshot of the TOM's current state."""
    return {
        "name": tom.name,
        "maturity_targets": tom.maturity_targets,
        "dimensions": [
            {
                "dimension_type": dr.dimension_type.value if hasattr(dr.dimension_type, "value") else str(dr.dimension_type),
                "maturity_target": dr.maturity_target,
                "description": dr.description,
            }
            for dr in (tom.dimension_records or [])
        ],
    }


@router.post("/models", response_model=TOMResponse, status_code=status.HTTP_201_CREATED)
async def create_tom(
    payload: TOMCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> dict[str, Any]:
    """Create a new target operating model."""
    await _check_engagement_member(session, user, payload.engagement_id)
    eng_result = await session.execute(select(Engagement).where(Engagement.id == payload.engagement_id))
    if not eng_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Engagement {payload.engagement_id} not found"
        )
    # Validate no duplicate dimension types
    if payload.dimensions:
        dim_types = [d.dimension_type for d in payload.dimensions]
        if len(dim_types) != len(set(dim_types)):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Duplicate dimension_type values are not allowed",
            )

    tom = TargetOperatingModel(
        engagement_id=payload.engagement_id,
        name=payload.name,
        version=1,
        maturity_targets=payload.maturity_targets,
    )
    session.add(tom)
    await session.flush()

    # Create structured dimension records
    if payload.dimensions:
        for dim_input in payload.dimensions:
            dim_record = TOMDimensionRecord(
                tom_id=tom.id,
                dimension_type=dim_input.dimension_type,
                maturity_target=dim_input.maturity_target,
                description=dim_input.description,
            )
            session.add(dim_record)

    await log_audit(session, payload.engagement_id, AuditAction.TOM_CREATED, json.dumps({"name": payload.name}))
    await session.commit()
    await session.refresh(tom, attribute_names=["dimension_records"])
    return _tom_to_response(tom)


@router.get("/models", response_model=TOMList)
async def list_toms(
    engagement_id: UUID,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """List target operating models for an engagement."""
    await _check_engagement_member(session, user, engagement_id)

    query = (
        select(TargetOperatingModel)
        .where(TargetOperatingModel.engagement_id == engagement_id)
        .options(selectinload(TargetOperatingModel.dimension_records))
    )
    count_query = (
        select(func.count())
        .select_from(TargetOperatingModel)
        .where(TargetOperatingModel.engagement_id == engagement_id)
    )
    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    toms = list(result.scalars().all())
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0
    return {"items": [_tom_to_response(t) for t in toms], "total": total}


@router.get("/models/{tom_id}", response_model=TOMResponse)
async def get_tom(
    tom_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Get a specific TOM by ID with embedded dimensions."""

    result = await session.execute(
        select(TargetOperatingModel)
        .where(TargetOperatingModel.id == tom_id)
        .options(selectinload(TargetOperatingModel.dimension_records))
    )
    tom = result.scalar_one_or_none()
    if not tom:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"TOM {tom_id} not found")
    await _check_engagement_member(session, user, tom.engagement_id)
    return _tom_to_response(tom)


@router.patch("/models/{tom_id}", response_model=TOMResponse)
async def update_tom(
    tom_id: UUID,
    payload: TOMUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> dict[str, Any]:
    """Update a TOM (partial update). Creates a version snapshot before applying changes."""

    result = await session.execute(
        select(TargetOperatingModel)
        .where(TargetOperatingModel.id == tom_id)
        .options(selectinload(TargetOperatingModel.dimension_records))
    )
    tom = result.scalar_one_or_none()
    if not tom:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"TOM {tom_id} not found")
    await _check_engagement_member(session, user, tom.engagement_id)

    # Snapshot current state before changes
    snapshot = _snapshot_dimensions(tom)
    version_record = TOMVersion(
        tom_id=tom.id,
        version_number=tom.version,
        snapshot=snapshot,
        changed_by=str(user.id) if user else None,
    )
    session.add(version_record)

    # Apply scalar updates (name, maturity_targets)
    update_data = payload.model_dump(exclude_unset=True, exclude={"dimensions"})
    for field_name, value in update_data.items():
        setattr(tom, field_name, value)

    # Apply dimension updates if provided
    if payload.dimensions is not None:
        # Update or create dimension records
        existing = {dr.dimension_type: dr for dr in tom.dimension_records}
        for dim_input in payload.dimensions:
            if dim_input.dimension_type in existing:
                existing[dim_input.dimension_type].maturity_target = dim_input.maturity_target
                existing[dim_input.dimension_type].description = dim_input.description
            else:
                dim_record = TOMDimensionRecord(
                    tom_id=tom.id,
                    dimension_type=dim_input.dimension_type,
                    maturity_target=dim_input.maturity_target,
                    description=dim_input.description,
                )
                session.add(dim_record)

    # Bump version atomically via SQL expression to prevent race conditions
    await session.execute(
        select(TargetOperatingModel)
        .where(TargetOperatingModel.id == tom.id)
        .with_for_update()
    )
    tom.version = TargetOperatingModel.version + 1  # type: ignore[assignment]  # SA SQL expression

    await session.commit()
    await session.refresh(tom, attribute_names=["dimension_records"])
    return _tom_to_response(tom)


# -- Version History Routes ----------------------------------------------------


@router.get("/models/{tom_id}/versions", response_model=TOMVersionList)
async def get_tom_versions(
    tom_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Get version history for a TOM."""
    result = await session.execute(select(TargetOperatingModel).where(TargetOperatingModel.id == tom_id))
    tom = result.scalar_one_or_none()
    if not tom:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"TOM {tom_id} not found")
    await _check_engagement_member(session, user, tom.engagement_id)

    versions_result = await session.execute(
        select(TOMVersion)
        .where(TOMVersion.tom_id == tom_id)
        .order_by(TOMVersion.version_number.asc())
    )
    versions = list(versions_result.scalars().all())

    return {
        "tom_id": tom.id,
        "current_version": tom.version,
        "versions": [
            {
                "version_number": v.version_number,
                "snapshot": v.snapshot,
                "changed_by": v.changed_by,
                "created_at": v.created_at,
            }
            for v in versions
        ],
    }


# -- Import/Export Routes -----------------------------------------------------


@router.get("/models/{tom_id}/export")
async def export_tom(
    tom_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Export a TOM as a portable JSON document."""

    result = await session.execute(
        select(TargetOperatingModel)
        .where(TargetOperatingModel.id == tom_id)
        .options(selectinload(TargetOperatingModel.dimension_records))
    )
    tom = result.scalar_one_or_none()
    if not tom:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"TOM {tom_id} not found")
    await _check_engagement_member(session, user, tom.engagement_id)

    return {
        "name": tom.name,
        "version": tom.version,
        "maturity_targets": tom.maturity_targets,
        "dimensions": [
            {
                "dimension_type": dr.dimension_type.value if hasattr(dr.dimension_type, "value") else str(dr.dimension_type),
                "maturity_target": dr.maturity_target,
                "description": dr.description,
            }
            for dr in (tom.dimension_records or [])
        ],
    }


class TOMImport(BaseModel):
    """Schema for importing a TOM."""

    engagement_id: UUID
    name: str = Field(..., min_length=1, max_length=512)
    dimensions: list[DimensionInput] | None = None
    maturity_targets: dict[str, Any] | None = None


@router.post("/models/import", response_model=TOMResponse, status_code=status.HTTP_201_CREATED)
async def import_tom(
    payload: TOMImport,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> dict[str, Any]:
    """Import a TOM from a portable JSON document."""
    await _check_engagement_member(session, user, payload.engagement_id)
    eng_result = await session.execute(select(Engagement).where(Engagement.id == payload.engagement_id))
    if not eng_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Engagement {payload.engagement_id} not found"
        )

    # Validate no duplicate dimension types
    if payload.dimensions:
        dim_types = [d.dimension_type for d in payload.dimensions]
        if len(dim_types) != len(set(dim_types)):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Duplicate dimension_type values are not allowed",
            )

    tom = TargetOperatingModel(
        engagement_id=payload.engagement_id,
        name=payload.name,
        version=1,
        maturity_targets=payload.maturity_targets,
    )
    session.add(tom)
    await session.flush()

    if payload.dimensions:
        for dim_input in payload.dimensions:
            dim_record = TOMDimensionRecord(
                tom_id=tom.id,
                dimension_type=dim_input.dimension_type,
                maturity_target=dim_input.maturity_target,
                description=dim_input.description,
            )
            session.add(dim_record)

    await log_audit(
        session, payload.engagement_id, AuditAction.TOM_CREATED,
        json.dumps({"name": payload.name, "source": "import"}),
    )
    await session.commit()
    await session.refresh(tom, attribute_names=["dimension_records"])
    return _tom_to_response(tom)


# -- Gap Analysis Routes ------------------------------------------------------


@router.post("/gaps", response_model=GapResponse, status_code=status.HTTP_201_CREATED)
async def create_gap(
    payload: GapCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> GapAnalysisResult:
    """Create a gap analysis result."""
    await _check_engagement_member(session, user, payload.engagement_id)
    eng_result = await session.execute(select(Engagement).where(Engagement.id == payload.engagement_id))
    if not eng_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Engagement {payload.engagement_id} not found"
        )
    gap = GapAnalysisResult(
        engagement_id=payload.engagement_id,
        tom_id=payload.tom_id,
        gap_type=payload.gap_type,
        dimension=payload.dimension,
        severity=payload.severity,
        confidence=payload.confidence,
        rationale=payload.rationale,
        recommendation=payload.recommendation,
        business_criticality=payload.business_criticality,
        risk_exposure=payload.risk_exposure,
        regulatory_impact=payload.regulatory_impact,
        remediation_cost=payload.remediation_cost,
    )
    session.add(gap)
    await session.flush()
    await log_audit(
        session,
        payload.engagement_id,
        AuditAction.GAP_ANALYSIS_RUN,
        json.dumps({"dimension": payload.dimension, "gap_type": payload.gap_type}),
    )
    await session.commit()
    await session.refresh(gap)
    return gap


@router.get("/gaps", response_model=GapList)
async def list_gaps(
    engagement_id: UUID,
    tom_id: UUID | None = None,
    dimension: TOMDimension | None = None,
    sort: str | None = Query(None, description="Sort order: 'priority' for composite_score desc"),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """List gap analysis results for an engagement.

    Use sort=priority to order by composite_score descending.
    """
    await _check_engagement_member(session, user, engagement_id)
    query = select(GapAnalysisResult).where(GapAnalysisResult.engagement_id == engagement_id)
    count_query = (
        select(func.count()).select_from(GapAnalysisResult).where(GapAnalysisResult.engagement_id == engagement_id)
    )

    if tom_id is not None:
        query = query.where(GapAnalysisResult.tom_id == tom_id)
        count_query = count_query.where(GapAnalysisResult.tom_id == tom_id)
    if dimension is not None:
        query = query.where(GapAnalysisResult.dimension == dimension)
        count_query = count_query.where(GapAnalysisResult.dimension == dimension)

    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0

    if sort == "priority":
        # Priority sort requires loading all gaps for Python-side sort
        # (composite_score is a computed property, not a DB column).
        # Cap at 1000 to prevent excessive memory usage.
        max_sort_rows = 1000
        result = await session.execute(query.limit(max_sort_rows))
        gaps = list(result.scalars().all())
        gaps.sort(key=lambda g: g.composite_score, reverse=True)
        gaps = gaps[offset : offset + limit]
    else:
        result = await session.execute(query.offset(offset).limit(limit))
        gaps = list(result.scalars().all())

    return {"items": gaps, "total": total}


# -- Gap Rationale Generation Routes (Story #352) ----------------------------


class RationaleResponse(BaseModel):
    """Response for a single gap rationale generation."""

    gap_id: UUID
    rationale: str
    recommendation: str


class BulkRationaleResponse(BaseModel):
    """Response for bulk rationale generation."""

    engagement_id: UUID
    gaps_processed: int
    results: list[RationaleResponse]


@router.post("/gaps/{gap_id}/generate-rationale", response_model=RationaleResponse)
async def generate_gap_rationale(
    gap_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> dict[str, Any]:
    """Generate LLM-powered rationale for a single gap."""
    from src.tom.rationale_generator import RationaleGeneratorService

    result = await session.execute(
        select(GapAnalysisResult).where(GapAnalysisResult.id == gap_id)
    )
    gap = result.scalar_one_or_none()
    if not gap:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Gap {gap_id} not found")

    await _check_engagement_member(session, user, gap.engagement_id)

    # Get TOM specification for context
    tom_spec = None
    if gap.tom_id:
        tom_result = await session.execute(
            select(TargetOperatingModel)
            .where(TargetOperatingModel.id == gap.tom_id)
            .options(selectinload(TargetOperatingModel.dimension_records))
        )
        tom = tom_result.scalar_one_or_none()
        if tom and tom.dimension_records:
            for dr in tom.dimension_records:
                if str(dr.dimension_type) == str(gap.dimension):
                    tom_spec = dr.description
                    break

    generator = RationaleGeneratorService()
    rationale_data = await generator.generate_rationale(gap, tom_spec)

    gap.rationale = rationale_data["rationale"]
    gap.recommendation = rationale_data["recommendation"]
    await session.commit()

    return {
        "gap_id": gap.id,
        "rationale": rationale_data["rationale"],
        "recommendation": rationale_data["recommendation"],
    }


@router.post(
    "/gaps/engagement/{engagement_id}/generate-rationales",
    response_model=BulkRationaleResponse,
)
async def generate_bulk_rationales(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Generate LLM-powered rationales for all gaps without rationale in an engagement."""
    from src.tom.rationale_generator import RationaleGeneratorService

    generator = RationaleGeneratorService()
    results = await generator.generate_bulk_rationales(session, str(engagement_id))
    await session.commit()

    return {
        "engagement_id": engagement_id,
        "gaps_processed": len(results),
        "results": [
            {
                "gap_id": r["gap_id"],
                "rationale": r["rationale"],
                "recommendation": r["recommendation"],
            }
            for r in results
        ],
    }


# -- Best Practices Routes ----------------------------------------------------


class BestPracticeList(BaseModel):
    """Schema for listing best practices."""

    items: list[BestPracticeResponse]
    total: int


class BenchmarkList(BaseModel):
    """Schema for listing benchmarks."""

    items: list[BenchmarkResponse]
    total: int


class SeedResponse(BaseModel):
    """Schema for seed operation response."""

    best_practices_seeded: int
    benchmarks_seeded: int


class AlignmentResponse(BaseModel):
    """Schema for alignment analysis response."""

    engagement_id: str
    tom_id: str
    overall_alignment: float
    maturity_scores: dict[str, float]
    gaps_detected: int
    gaps_persisted: int
    gaps: list[dict[str, Any]]


class MaturityScoresResponse(BaseModel):
    """Schema for maturity scores response."""

    engagement_id: str
    maturity_scores: dict[str, float]


class PrioritizedGapsResponse(BaseModel):
    """Schema for prioritized gaps response."""

    engagement_id: str
    gaps: list[dict[str, Any]]
    total: int


class ConformanceDeviationResponse(BaseModel):
    """Schema for a single conformance deviation."""

    element_name: str
    deviation_type: str
    severity: float
    description: str


class ConformanceCheckResponse(BaseModel):
    """Schema for conformance check response."""

    pov_model_id: str
    reference_model_id: str
    fitness_score: float
    matching_elements: int
    total_reference_elements: int
    deviations: list[ConformanceDeviationResponse]


class ConformanceModelSummary(BaseModel):
    """Schema for a model in the conformance summary."""

    id: str
    scope: str
    confidence_score: float
    element_count: int


class ConformanceSummaryResponse(BaseModel):
    """Schema for conformance summary response."""

    engagement_id: str
    completed_models: int
    models: list[ConformanceModelSummary]


class RoadmapPhaseResponse(BaseModel):
    """Schema for a roadmap phase."""

    phase_number: int
    name: str
    duration_months: int
    initiative_count: int
    initiatives: list[dict[str, Any]]


class RoadmapResponse(BaseModel):
    """Schema for roadmap generation response."""

    engagement_id: str
    tom_id: str
    total_initiatives: int
    estimated_duration_months: int
    phases: list[RoadmapPhaseResponse]


class RoadmapSummaryResponse(BaseModel):
    """Schema for roadmap summary response."""

    engagement_id: str
    total_gaps: int
    gaps_by_dimension: dict[str, int]


@router.post("/best-practices", response_model=BestPracticeResponse, status_code=status.HTTP_201_CREATED)
async def create_best_practice(
    payload: BestPracticeCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> BestPractice:
    """Create a best practice entry."""
    bp = BestPractice(
        domain=payload.domain,
        industry=payload.industry,
        description=payload.description,
        source=payload.source,
        tom_dimension=payload.tom_dimension,
    )
    session.add(bp)
    await session.commit()
    await session.refresh(bp)
    return bp


@router.get("/best-practices", response_model=BestPracticeList)
async def list_best_practices(
    industry: str | None = None,
    dimension: TOMDimension | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """List best practices with optional filters.

    Args:
        industry: Filter by industry name.
        dimension: Filter by TOM dimension.
        limit: Max results.
        offset: Pagination offset.
    """
    query = select(BestPractice)
    count_query = select(func.count()).select_from(BestPractice)

    if industry is not None:
        query = query.where(BestPractice.industry == industry)
        count_query = count_query.where(BestPractice.industry == industry)
    if dimension is not None:
        query = query.where(BestPractice.tom_dimension == dimension)
        count_query = count_query.where(BestPractice.tom_dimension == dimension)

    query = query.order_by(BestPractice.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(query)
    items = list(result.scalars().all())
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0
    return {"items": items, "total": total}


@router.get("/best-practices/{bp_id}", response_model=BestPracticeResponse)
async def get_best_practice(
    bp_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> BestPractice:
    """Get a single best practice by ID."""
    result = await session.execute(select(BestPractice).where(BestPractice.id == bp_id))
    bp = result.scalar_one_or_none()
    if not bp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Best practice {bp_id} not found")
    return bp


# -- Benchmark Routes ---------------------------------------------------------


@router.post("/benchmarks", response_model=BenchmarkResponse, status_code=status.HTTP_201_CREATED)
async def create_benchmark(
    payload: BenchmarkCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> Benchmark:
    """Create a benchmark entry."""
    bm = Benchmark(
        metric_name=payload.metric_name,
        industry=payload.industry,
        p25=payload.p25,
        p50=payload.p50,
        p75=payload.p75,
        p90=payload.p90,
        source=payload.source,
    )
    session.add(bm)
    await session.commit()
    await session.refresh(bm)
    return bm


@router.get("/benchmarks", response_model=BenchmarkList)
async def list_benchmarks(
    industry: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """List benchmarks with optional filters.

    Args:
        industry: Filter by industry name.
        limit: Max results.
        offset: Pagination offset.
    """
    query = select(Benchmark)
    count_query = select(func.count()).select_from(Benchmark)

    if industry is not None:
        query = query.where(Benchmark.industry == industry)
        count_query = count_query.where(Benchmark.industry == industry)

    query = query.order_by(Benchmark.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(query)
    items = list(result.scalars().all())
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0
    return {"items": items, "total": total}


@router.get("/benchmarks/{benchmark_id}", response_model=BenchmarkResponse)
async def get_benchmark(
    benchmark_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> Benchmark:
    """Get a single benchmark by ID."""
    result = await session.execute(select(Benchmark).where(Benchmark.id == benchmark_id))
    bm = result.scalar_one_or_none()
    if not bm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Benchmark {benchmark_id} not found")
    return bm


@router.post("/seed", response_model=SeedResponse, status_code=status.HTTP_201_CREATED)
async def seed_best_practices_and_benchmarks(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> dict[str, Any]:
    """Seed the database with standard best practices and benchmarks."""
    from src.data.seeds import get_benchmark_seeds, get_best_practice_seeds

    bp_seeds = get_best_practice_seeds()
    bm_seeds = get_benchmark_seeds()

    bp_count = 0
    for bp_data in bp_seeds:
        bp = BestPractice(**bp_data)
        session.add(bp)
        bp_count += 1

    bm_count = 0
    for bm_data in bm_seeds:
        bm = Benchmark(**bm_data)
        session.add(bm)
        bm_count += 1

    await session.commit()
    return {"best_practices_seeded": bp_count, "benchmarks_seeded": bm_count}


# -- Alignment Engine Routes (Story #30) --------------------------------------


@router.post("/alignment/{engagement_id}/{tom_id}", response_model=AlignmentResponse)
async def run_alignment(
    engagement_id: UUID,
    tom_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Run TOM alignment analysis for an engagement."""
    from src.semantic.graph import KnowledgeGraphService
    from src.tom.alignment import TOMAlignmentEngine

    driver = request.app.state.neo4j_driver
    graph_service = KnowledgeGraphService(driver)
    engine = TOMAlignmentEngine(graph_service)

    result = await engine.run_alignment(session, str(engagement_id), str(tom_id))

    # Persist gaps
    persisted = await engine.persist_gaps(session, result)
    await session.commit()

    return {
        "engagement_id": result.engagement_id,
        "tom_id": result.tom_id,
        "overall_alignment": result.overall_alignment,
        "maturity_scores": result.maturity_scores,
        "gaps_detected": len(result.gaps),
        "gaps_persisted": len(persisted),
        "gaps": result.gaps,
    }


@router.get("/alignment/{engagement_id}/maturity", response_model=MaturityScoresResponse)
async def get_maturity_scores(
    engagement_id: UUID,
    request: Request,
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get current maturity scores for an engagement."""
    from src.semantic.graph import KnowledgeGraphService
    from src.tom.alignment import TOMAlignmentEngine

    driver = request.app.state.neo4j_driver
    graph_service = KnowledgeGraphService(driver)
    engine = TOMAlignmentEngine(graph_service)

    stats = await graph_service.get_stats(str(engagement_id))
    from src.core.models import TOMDimension as TomDimension

    scores = {}
    for dim in TomDimension:
        scores[dim] = engine.assess_dimension_maturity(dim, stats)

    return {"engagement_id": str(engagement_id), "maturity_scores": scores}


@router.post("/alignment/{engagement_id}/prioritize", response_model=PrioritizedGapsResponse)
async def prioritize_gaps(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get prioritized gap list for an engagement."""
    from src.tom.alignment import TOMAlignmentEngine

    gap_query = select(GapAnalysisResult).where(GapAnalysisResult.engagement_id == engagement_id)
    gap_result = await session.execute(gap_query)
    gaps = list(gap_result.scalars().all())

    prioritized = []
    for gap in gaps:
        priority = TOMAlignmentEngine.calculate_priority(gap.severity, gap.confidence, str(gap.dimension))
        prioritized.append(
            {
                "gap_id": str(gap.id),
                "dimension": str(gap.dimension),
                "gap_type": str(gap.gap_type),
                "severity": gap.severity,
                "confidence": gap.confidence,
                "priority_score": priority,
                "recommendation": gap.recommendation,
            }
        )

    prioritized.sort(key=lambda x: float(x.get("priority_score", 0) or 0), reverse=True)  # type: ignore[arg-type]
    return {"engagement_id": str(engagement_id), "gaps": prioritized, "total": len(prioritized)}


# -- Conformance Routes (Story #32) -------------------------------------------


@router.post("/conformance/check", response_model=ConformanceCheckResponse)
async def check_conformance(
    pov_model_id: UUID,
    reference_model_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Check conformance between a POV model and reference model."""
    from src.tom.conformance import ConformanceCheckingEngine

    engine = ConformanceCheckingEngine()
    result = await engine.check_conformance(session, str(pov_model_id), str(reference_model_id))

    return {
        "pov_model_id": result.pov_model_id,
        "reference_model_id": result.reference_model_id,
        "fitness_score": result.fitness_score,
        "matching_elements": result.matching_elements,
        "total_reference_elements": result.total_reference_elements,
        "deviations": [
            {
                "element_name": d.element_name,
                "deviation_type": d.deviation_type,
                "severity": d.severity,
                "description": d.description,
            }
            for d in result.deviations
        ],
    }


@router.get("/conformance/{engagement_id}/summary", response_model=ConformanceSummaryResponse)
async def get_conformance_summary(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get conformance summary for all models in an engagement."""
    from src.core.models import ProcessModel, ProcessModelStatus

    result = await session.execute(
        select(ProcessModel)
        .where(ProcessModel.engagement_id == engagement_id)
        .where(ProcessModel.status == ProcessModelStatus.COMPLETED)
    )
    models = list(result.scalars().all())

    return {
        "engagement_id": str(engagement_id),
        "completed_models": len(models),
        "models": [
            {
                "id": str(m.id),
                "scope": m.scope,
                "confidence_score": m.confidence_score,
                "element_count": m.element_count,
            }
            for m in models
        ],
    }


# -- Roadmap Routes (Story #34) -----------------------------------------------


@router.post("/roadmap/{engagement_id}/{tom_id}", response_model=RoadmapResponse)
async def generate_roadmap(
    engagement_id: UUID,
    tom_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Generate a transformation roadmap."""
    from src.tom.roadmap import RoadmapGenerator

    generator = RoadmapGenerator()
    roadmap = await generator.generate_roadmap(session, str(engagement_id), str(tom_id))

    return {
        "engagement_id": roadmap.engagement_id,
        "tom_id": roadmap.tom_id,
        "total_initiatives": roadmap.total_initiatives,
        "estimated_duration_months": roadmap.estimated_duration_months,
        "phases": [
            {
                "phase_number": p.phase_number,
                "name": p.name,
                "duration_months": p.duration_months,
                "initiative_count": len(p.initiatives),
                "initiatives": p.initiatives,
            }
            for p in roadmap.phases
        ],
    }


@router.get("/roadmap/{engagement_id}", response_model=RoadmapSummaryResponse)
async def get_roadmap_summary(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get roadmap summary with gap counts per dimension."""
    gap_result = await session.execute(
        select(GapAnalysisResult).where(GapAnalysisResult.engagement_id == engagement_id)
    )
    gaps = list(gap_result.scalars().all())

    by_dimension: dict[str, int] = {}
    for gap in gaps:
        dim = str(gap.dimension)
        by_dimension[dim] = by_dimension.get(dim, 0) + 1

    return {
        "engagement_id": str(engagement_id),
        "total_gaps": len(gaps),
        "gaps_by_dimension": by_dimension,
    }


# -- Gap-Prioritized Roadmap Routes (Story #368) -----------------------------


class RoadmapRecommendationDetail(BaseModel):
    """A recommendation within a roadmap phase."""

    gap_id: str
    title: str
    dimension: str
    gap_type: str
    composite_score: float
    effort_weeks: float
    remediation_cost: int
    rationale_summary: str
    depends_on: list[str] = Field(default_factory=list)


class PrioritizedPhaseResponse(BaseModel):
    """A phase in the prioritized roadmap."""

    phase_number: int
    name: str
    duration_weeks_estimate: int
    recommendation_count: int
    recommendation_ids: list[str]
    recommendations: list[RoadmapRecommendationDetail]


class PrioritizedRoadmapResponse(BaseModel):
    """Full prioritized roadmap response."""

    model_config = {"from_attributes": True}

    id: UUID
    engagement_id: UUID
    status: str
    total_initiatives: int
    estimated_duration_weeks: int
    phases: list[PrioritizedPhaseResponse]
    generated_at: Any


class GenerateRoadmapResponse(BaseModel):
    """Response for roadmap generation."""

    roadmap_id: UUID
    engagement_id: UUID
    status: str
    total_initiatives: int
    estimated_duration_weeks: int
    phase_count: int


@router.post(
    "/roadmaps/{engagement_id}/generate",
    response_model=GenerateRoadmapResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_prioritized_roadmap(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Generate a prioritized transformation roadmap from gap analysis.

    Groups gaps into 3-4 phases based on composite_score and effort_estimate,
    resolves dependencies via topological sort, and persists the roadmap.
    """
    from src.tom.roadmap_generator import generate_roadmap as gen_roadmap

    # Verify engagement exists
    eng_result = await session.execute(select(Engagement).where(Engagement.id == engagement_id))
    if not eng_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Engagement {engagement_id} not found",
        )

    roadmap = await gen_roadmap(session, engagement_id)
    await session.commit()

    return {
        "roadmap_id": roadmap.id,
        "engagement_id": roadmap.engagement_id,
        "status": roadmap.status.value,
        "total_initiatives": roadmap.total_initiatives,
        "estimated_duration_weeks": roadmap.estimated_duration_weeks,
        "phase_count": len(roadmap.phases or []),
    }


@router.get("/roadmaps/{roadmap_id}", response_model=PrioritizedRoadmapResponse)
async def get_prioritized_roadmap(
    roadmap_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Retrieve a generated roadmap by ID (structured JSON)."""
    from src.core.models import TransformationRoadmapModel

    result = await session.execute(
        select(TransformationRoadmapModel).where(TransformationRoadmapModel.id == roadmap_id)
    )
    roadmap = result.scalar_one_or_none()
    if not roadmap:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Roadmap {roadmap_id} not found",
        )

    await _check_engagement_member(session, user, roadmap.engagement_id)

    return {
        "id": roadmap.id,
        "engagement_id": roadmap.engagement_id,
        "status": roadmap.status.value,
        "total_initiatives": roadmap.total_initiatives,
        "estimated_duration_weeks": roadmap.estimated_duration_weeks,
        "phases": roadmap.phases or [],
        "generated_at": roadmap.generated_at,
    }


@router.get("/roadmaps/{roadmap_id}/export")
async def export_roadmap(
    roadmap_id: UUID,
    export_format: str = Query(default="html", alias="format", description="Export format: html"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> Any:
    """Export a roadmap as client-ready HTML document."""
    from fastapi.responses import HTMLResponse

    from src.core.models import TransformationRoadmapModel
    from src.tom.roadmap_exporter import export_roadmap_html

    result = await session.execute(
        select(TransformationRoadmapModel).where(TransformationRoadmapModel.id == roadmap_id)
    )
    roadmap = result.scalar_one_or_none()
    if not roadmap:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Roadmap {roadmap_id} not found",
        )

    await _check_engagement_member(session, user, roadmap.engagement_id)

    # Fetch engagement name
    eng_result = await session.execute(select(Engagement).where(Engagement.id == roadmap.engagement_id))
    engagement = eng_result.scalar_one_or_none()
    eng_name = engagement.name if engagement else "Unknown Engagement"

    roadmap_data = {
        "phases": roadmap.phases or [],
        "total_initiatives": roadmap.total_initiatives,
        "estimated_duration_weeks": roadmap.estimated_duration_weeks,
        "generated_at": roadmap.generated_at.isoformat() if roadmap.generated_at else "",
    }

    if export_format != "html":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported export format: {export_format}. Supported: html",
        )

    html_content = export_roadmap_html(roadmap_data, eng_name)

    # Update exported_at
    from datetime import UTC, datetime

    roadmap.exported_at = datetime.now(UTC)
    await session.commit()

    return HTMLResponse(content=html_content)


# ---------------------------------------------------------------------------
# Maturity Scoring schemas
# ---------------------------------------------------------------------------


class MaturityComputeRequest(BaseModel):
    """Request body for computing maturity scores."""

    governance_map: dict[str, dict[str, Any]] | None = None


class MaturityScoreResponse(BaseModel):
    """Response for a single maturity score."""

    model_config = {"from_attributes": True}

    id: UUID
    process_model_id: UUID
    process_area_name: str
    maturity_level: ProcessMaturity
    level_number: int
    evidence_dimensions: dict[str, Any] | None
    recommendations: list[str] | None
    scored_at: datetime


class MaturityComputeResponse(BaseModel):
    """Response for a batch maturity computation."""

    engagement_id: UUID
    scores_computed: int
    scores: list[MaturityScoreResponse]


class MaturityHeatmapEntry(BaseModel):
    """A single entry in the maturity heatmap."""

    process_model_id: UUID
    process_area_name: str
    maturity_level: ProcessMaturity
    level_number: int


class MaturityHeatmapResponse(BaseModel):
    """Full maturity heatmap response."""

    engagement_id: UUID
    process_areas: list[MaturityHeatmapEntry]
    overall_engagement_maturity: float
    process_area_count: int


# -- Per-Activity Alignment Scoring Routes (Story #348) ----------------------


class AlignmentRunTriggerResponse(BaseModel):
    """Response for triggering an alignment scoring run."""

    run_id: UUID
    status: str
    message: str


class AlignmentResultEntry(BaseModel):
    """A single per-activity, per-dimension alignment result."""

    model_config = {"from_attributes": True}

    id: UUID
    activity_id: UUID
    dimension_type: TOMDimension
    gap_type: TOMGapType
    deviation_score: float
    alignment_evidence: dict[str, Any] | None


class AlignmentRunResultsResponse(BaseModel):
    """Paginated results for an alignment run."""

    run_id: UUID
    status: str
    items: list[AlignmentResultEntry]
    total: int


# ---------------------------------------------------------------------------
# Maturity Scoring routes
# ---------------------------------------------------------------------------


@router.post(
    "/engagements/{engagement_id}/maturity-scores/compute",
    response_model=MaturityComputeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def compute_maturity_scores(
    engagement_id: UUID,
    body: MaturityComputeRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Compute maturity scores for all process areas in an engagement.

    Evaluates evidence coverage, governance linkages, and metric
    availability to assign a CMMI-aligned maturity level (1-5).
    """
    # Verify engagement exists
    eng_result = await session.execute(select(Engagement).where(Engagement.id == engagement_id))
    engagement = eng_result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found")

    # Fetch all process models for this engagement
    pm_result = await session.execute(
        select(ProcessModel).where(ProcessModel.engagement_id == engagement_id)
    )
    process_models = list(pm_result.scalars().all())

    if not process_models:
        return {
            "engagement_id": engagement_id,
            "scores_computed": 0,
            "scores": [],
        }

    # Build process model dicts with form_coverage from metadata
    pm_dicts = []
    for pm in process_models:
        meta = pm.metadata_json or {}
        pm_dicts.append({
            "id": str(pm.id),
            "engagement_id": str(engagement_id),
            "scope": pm.scope,
            "form_coverage": meta.get("form_coverage", 0.0),
        })

    # Use governance_map from request body, or default to empty
    governance_map = body.governance_map or {}

    scorer = MaturityScoringService()
    score_results = await scorer.score_engagement(pm_dicts, governance_map)

    # Persist scores
    now = datetime.now(UTC)
    score_responses = []
    for sr in score_results:
        score_id = _uuid.uuid4()
        ms = MaturityScore(
            id=score_id,
            engagement_id=engagement_id,
            process_model_id=UUID(sr["process_model_id"]),
            maturity_level=sr["maturity_level"],
            level_number=sr["level_number"],
            evidence_dimensions=sr["evidence_dimensions"],
            recommendations=sr["recommendations"],
        )
        session.add(ms)

        # Find process area name
        pm_name = next(
            (p["scope"] for p in pm_dicts if p["id"] == sr["process_model_id"]),
            "Unknown",
        )
        score_responses.append({
            "id": score_id,
            "process_model_id": UUID(sr["process_model_id"]),
            "process_area_name": pm_name,
            "maturity_level": sr["maturity_level"],
            "level_number": sr["level_number"],
            "evidence_dimensions": sr["evidence_dimensions"],
            "recommendations": sr["recommendations"],
            "scored_at": now,
        })

    await session.commit()

    await log_audit(
        session, engagement_id, AuditAction.ENGAGEMENT_UPDATED,
        f"Computed maturity scores for {len(score_results)} process areas",
        actor=str(user.id),
    )

    return {
        "engagement_id": engagement_id,
        "scores_computed": len(score_results),
        "scores": score_responses,
    }


@router.get(
    "/engagements/{engagement_id}/maturity-heatmap",
    response_model=MaturityHeatmapResponse,
)
async def get_maturity_heatmap(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Return the maturity heatmap for all process areas in an engagement.

    Returns the most recent maturity score per process area, plus
    the overall engagement maturity as the average of all level numbers.
    """
    # Verify engagement exists
    eng_result = await session.execute(select(Engagement).where(Engagement.id == engagement_id))
    if not eng_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found")

    # Get latest maturity scores per process model using a subquery
    latest_scores_subq = (
        select(
            MaturityScore.process_model_id,
            func.max(MaturityScore.scored_at).label("latest_scored_at"),
        )
        .where(MaturityScore.engagement_id == engagement_id)
        .group_by(MaturityScore.process_model_id)
        .subquery()
    )

    score_result = await session.execute(
        select(MaturityScore)
        .join(
            latest_scores_subq,
            (MaturityScore.process_model_id == latest_scores_subq.c.process_model_id)
            & (MaturityScore.scored_at == latest_scores_subq.c.latest_scored_at),
        )
        .where(MaturityScore.engagement_id == engagement_id)
    )
    scores = list(score_result.scalars().all())

    if not scores:
        return {
            "engagement_id": engagement_id,
            "process_areas": [],
            "overall_engagement_maturity": 0.0,
            "process_area_count": 0,
        }

    # Fetch process model names
    pm_ids = [s.process_model_id for s in scores]
    pm_result = await session.execute(
        select(ProcessModel).where(ProcessModel.id.in_(pm_ids))
    )
    pm_map = {pm.id: pm.scope for pm in pm_result.scalars().all()}

    areas = []
    total_level = 0
    for s in scores:
        areas.append({
            "process_model_id": s.process_model_id,
            "process_area_name": pm_map.get(s.process_model_id, "Unknown"),
            "maturity_level": s.maturity_level,
            "level_number": s.level_number,
        })
        total_level += s.level_number

    overall = round(total_level / len(scores), 2) if scores else 0.0

    return {
        "engagement_id": engagement_id,
        "process_areas": areas,
        "overall_engagement_maturity": overall,
        "process_area_count": len(scores),
    }


# ---------------------------------------------------------------------------
# Alignment Scoring routes
# ---------------------------------------------------------------------------


@router.post(
    "/scoring/{engagement_id}/run",
    response_model=AlignmentRunTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_alignment_scoring(
    engagement_id: UUID,
    request: Request,
    tom_id: UUID = Query(..., description="TOM to score against"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Trigger asynchronous per-activity TOM alignment scoring.

    Creates a TOMAlignmentRun in PENDING status and kicks off background
    scoring. Returns the run_id immediately.
    """
    # Verify engagement exists
    eng_result = await session.execute(select(Engagement).where(Engagement.id == engagement_id))
    if not eng_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Engagement {engagement_id} not found")

    # Verify TOM exists and belongs to this engagement
    tom_result = await session.execute(
        select(TargetOperatingModel).where(
            TargetOperatingModel.id == tom_id,
            TargetOperatingModel.engagement_id == engagement_id,
        )
    )
    if not tom_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"TOM {tom_id} not found for this engagement")

    # Check for existing active run (prevent duplicates)
    existing_run_result = await session.execute(
        select(TOMAlignmentRun).where(
            TOMAlignmentRun.engagement_id == engagement_id,
            TOMAlignmentRun.tom_id == tom_id,
            TOMAlignmentRun.status.in_([AlignmentRunStatus.PENDING, AlignmentRunStatus.RUNNING]),
        )
    )
    if existing_run_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An alignment scoring run is already in progress for this engagement and TOM",
        )

    # Create alignment run record
    run = TOMAlignmentRun(engagement_id=engagement_id, tom_id=tom_id)
    session.add(run)
    await session.flush()
    run_id = run.id

    await log_audit(
        session,
        engagement_id,
        AuditAction.GAP_ANALYSIS_RUN,
        json.dumps({"tom_id": str(tom_id), "run_id": str(run_id)}),
    )
    await session.commit()

    # Launch async scoring with reference retention
    task = asyncio.create_task(
        _run_alignment_scoring_async(
            run_id=run_id,
            session_factory=request.app.state.db_session_factory,
            neo4j_driver=request.app.state.neo4j_driver,
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {
        "run_id": run_id,
        "status": AlignmentRunStatus.PENDING.value,
        "message": "Alignment scoring started",
    }


@router.get(
    "/scoring/runs/{run_id}/results",
    response_model=AlignmentRunResultsResponse,
)
async def get_alignment_run_results(
    run_id: UUID,
    limit: int = Query(50, ge=1, le=500, description="Items per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Retrieve paginated results for an alignment scoring run."""
    # Fetch the run
    run_result = await session.execute(
        select(TOMAlignmentRun).where(TOMAlignmentRun.id == run_id)
    )
    run = run_result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Alignment run {run_id} not found")

    await _check_engagement_member(session, user, run.engagement_id)

    # Count total results
    count_result = await session.execute(
        select(func.count()).select_from(TOMAlignmentResult).where(TOMAlignmentResult.run_id == run_id)
    )
    total = count_result.scalar() or 0

    # Fetch paginated results
    results_query = (
        select(TOMAlignmentResult)
        .where(TOMAlignmentResult.run_id == run_id)
        .order_by(TOMAlignmentResult.activity_id, TOMAlignmentResult.dimension_type)
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(results_query)
    items = list(result.scalars().all())

    return {
        "run_id": run_id,
        "status": run.status.value,
        "items": items,
        "total": total,
    }


async def _run_alignment_scoring_async(
    run_id: UUID,
    session_factory: Any,
    neo4j_driver: Any,
) -> None:
    """Background task to execute alignment scoring."""
    from src.semantic.graph import KnowledgeGraphService
    from src.tom.alignment_scoring import AlignmentScoringService

    try:
        async with session_factory() as session:
            # Re-fetch the run record within this session
            run_result = await session.execute(
                select(TOMAlignmentRun).where(TOMAlignmentRun.id == run_id)
            )
            run = run_result.scalar_one_or_none()
            if not run:
                logger.error("Alignment run %s not found in background task", run_id)
                return

            graph_service = KnowledgeGraphService(neo4j_driver)

            # Try to get embedding service (optional)
            embedding_service = None
            try:
                from src.rag.embeddings import EmbeddingService

                embedding_service = EmbeddingService()
            except Exception:
                logger.info("Embedding service not available, using graph-only scoring")

            scoring_service = AlignmentScoringService(
                graph_service=graph_service,
                embedding_service=embedding_service,
            )

            await scoring_service.run_scoring(session, run)
            await session.commit()

    except Exception:
        logger.exception("Background alignment scoring failed for run %s", run_id)
        try:
            async with session_factory() as session:
                run_result = await session.execute(
                    select(TOMAlignmentRun).where(TOMAlignmentRun.id == run_id)
                )
                run = run_result.scalar_one_or_none()
                if run and run.status != AlignmentRunStatus.FAILED:
                    run.status = AlignmentRunStatus.FAILED
                    run.completed_at = datetime.now(UTC)
                    run.error_message = "Background scoring task failed"
                    await session.commit()
        except Exception:
            logger.exception("Failed to update run %s status to FAILED", run_id)
