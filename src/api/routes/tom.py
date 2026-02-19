"""TOM (Target Operating Model) management routes.

Provides CRUD operations for target operating models, gap analysis results,
best practices, and benchmarks.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import (
    AuditAction,
    AuditLog,
    Benchmark,
    BestPractice,
    Engagement,
    GapAnalysisResult,
    TargetOperatingModel,
    TOMDimension,
    TOMGapType,
    User,
)
from src.api.deps import get_session
from src.core.permissions import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tom", tags=["tom"])


# -- Request/Response Schemas ------------------------------------------------


class TOMCreate(BaseModel):
    """Schema for creating a target operating model."""

    engagement_id: UUID
    name: str = Field(..., min_length=1, max_length=512)
    dimensions: dict[str, Any] | None = None
    maturity_targets: dict[str, Any] | None = None


class TOMUpdate(BaseModel):
    """Schema for updating a TOM (PATCH)."""

    name: str | None = Field(None, min_length=1, max_length=512)
    dimensions: dict[str, Any] | None = None
    maturity_targets: dict[str, Any] | None = None


class TOMResponse(BaseModel):
    """Schema for TOM responses."""

    model_config = {"from_attributes": True}

    id: UUID
    engagement_id: UUID
    name: str
    dimensions: dict[str, Any] | None
    maturity_targets: dict[str, Any] | None
    created_at: Any
    updated_at: Any


class TOMList(BaseModel):
    """Schema for listing TOMs."""

    items: list[TOMResponse]
    total: int


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


# -- Helpers ------------------------------------------------------------------


async def _log_audit(
    session: AsyncSession,
    engagement_id: UUID,
    action: AuditAction,
    details: str | None = None,
) -> None:
    audit = AuditLog(engagement_id=engagement_id, action=action, actor="system", details=details)
    session.add(audit)


async def _verify_engagement(session: AsyncSession, engagement_id: UUID) -> None:
    result = await session.execute(select(Engagement).where(Engagement.id == engagement_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Engagement {engagement_id} not found")


# -- TOM Routes ---------------------------------------------------------------


@router.post("/models", response_model=TOMResponse, status_code=status.HTTP_201_CREATED)
async def create_tom(
    payload: TOMCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> TargetOperatingModel:
    """Create a new target operating model."""
    await _verify_engagement(session, payload.engagement_id)
    tom = TargetOperatingModel(
        engagement_id=payload.engagement_id,
        name=payload.name,
        dimensions=payload.dimensions,
        maturity_targets=payload.maturity_targets,
    )
    session.add(tom)
    await session.flush()
    await _log_audit(session, payload.engagement_id, AuditAction.TOM_CREATED, json.dumps({"name": payload.name}))
    await session.commit()
    await session.refresh(tom)
    return tom


@router.get("/models", response_model=TOMList)
async def list_toms(
    engagement_id: UUID,
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """List target operating models for an engagement."""
    query = select(TargetOperatingModel).where(TargetOperatingModel.engagement_id == engagement_id)
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
    return {"items": toms, "total": total}


@router.get("/models/{tom_id}", response_model=TOMResponse)
async def get_tom(
    tom_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> TargetOperatingModel:
    """Get a specific TOM by ID."""
    result = await session.execute(select(TargetOperatingModel).where(TargetOperatingModel.id == tom_id))
    tom = result.scalar_one_or_none()
    if not tom:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"TOM {tom_id} not found")
    return tom


@router.patch("/models/{tom_id}", response_model=TOMResponse)
async def update_tom(
    tom_id: UUID,
    payload: TOMUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> TargetOperatingModel:
    """Update a TOM (partial update)."""
    result = await session.execute(select(TargetOperatingModel).where(TargetOperatingModel.id == tom_id))
    tom = result.scalar_one_or_none()
    if not tom:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"TOM {tom_id} not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field_name, value in update_data.items():
        setattr(tom, field_name, value)

    await session.commit()
    await session.refresh(tom)
    return tom


# -- Gap Analysis Routes ------------------------------------------------------


@router.post("/gaps", response_model=GapResponse, status_code=status.HTTP_201_CREATED)
async def create_gap(
    payload: GapCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> GapAnalysisResult:
    """Create a gap analysis result."""
    await _verify_engagement(session, payload.engagement_id)
    gap = GapAnalysisResult(
        engagement_id=payload.engagement_id,
        tom_id=payload.tom_id,
        gap_type=payload.gap_type,
        dimension=payload.dimension,
        severity=payload.severity,
        confidence=payload.confidence,
        rationale=payload.rationale,
        recommendation=payload.recommendation,
    )
    session.add(gap)
    await session.flush()
    await _log_audit(
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
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """List gap analysis results for an engagement."""
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

    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    gaps = list(result.scalars().all())
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0
    return {"items": gaps, "total": total}


# -- Best Practices Routes ----------------------------------------------------


class BestPracticeList(BaseModel):
    """Schema for listing best practices."""

    items: list[BestPracticeResponse]
    total: int


class BenchmarkList(BaseModel):
    """Schema for listing benchmarks."""

    items: list[BenchmarkResponse]
    total: int


@router.post("/best-practices", response_model=BestPracticeResponse, status_code=status.HTTP_201_CREATED)
async def create_best_practice(
    payload: BestPracticeCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
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
    limit: int = 50,
    offset: int = 0,
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
    user: User = Depends(require_permission("engagement:read")),
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
    limit: int = 50,
    offset: int = 0,
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


@router.post("/seed", status_code=status.HTTP_201_CREATED)
async def seed_best_practices_and_benchmarks(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
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


@router.post("/alignment/{engagement_id}/{tom_id}")
async def run_alignment(
    engagement_id: UUID,
    tom_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
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


@router.get("/alignment/{engagement_id}/maturity")
async def get_maturity_scores(
    engagement_id: UUID,
    request: Request,
    user: User = Depends(require_permission("engagement:read")),
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
        scores[dim] = engine._assess_dimension_maturity(dim, stats)

    return {"engagement_id": str(engagement_id), "maturity_scores": scores}


@router.post("/alignment/{engagement_id}/prioritize")
async def prioritize_gaps(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
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


@router.post("/conformance/check")
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


@router.get("/conformance/{engagement_id}/summary")
async def get_conformance_summary(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
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


@router.post("/roadmap/{engagement_id}/{tom_id}")
async def generate_roadmap(
    engagement_id: UUID,
    tom_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
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


@router.get("/roadmap/{engagement_id}")
async def get_roadmap_summary(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
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
