"""POV (Process Point of View) API routes.

Provides endpoints for generating, retrieving, and inspecting
process models created by the LCD algorithm.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Literal

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.api.services.dark_room_backlog import DarkRoomBacklogService
from src.api.services.illumination_planner import IlluminationPlannerService
from src.core.audit import log_audit
from src.core.models import (
    AuditAction,
    BrightnessClassification,
    Contradiction,
    EngagementMember,
    EvidenceGap,
    EvidenceItem,
    IlluminationActionStatus,
    ProcessElement,
    ProcessModel,
    User,
    UserRole,
)
from src.core.permissions import require_permission
from src.pov.generator import generate_pov
from src.pov.orchestrator import TOTAL_STEPS, compute_version_diff
from src.semantic.graph import KnowledgeGraphService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pov", tags=["pov"])

# Job TTL in Redis: 24 hours
_JOB_TTL = 86400


async def _set_job(request: Request, job_id: str, data: dict[str, Any]) -> None:
    """Store a job record in Redis."""
    try:
        redis_client = request.app.state.redis_client
        await redis_client.setex(f"pov:job:{job_id}", _JOB_TTL, json.dumps(data))
    except aioredis.RedisError:
        logger.warning("Redis unavailable for job store, job %s status may be lost", job_id)


async def _get_job(request: Request, job_id: str) -> dict[str, Any] | None:
    """Retrieve a job record from Redis."""
    try:
        redis_client = request.app.state.redis_client
        raw = await redis_client.get(f"pov:job:{job_id}")
        if raw:
            return json.loads(raw)
    except aioredis.RedisError:
        logger.warning("Redis unavailable for job store lookup")
    return None


# -- Request/Response Schemas ------------------------------------------------


class POVGenerateRequest(BaseModel):
    """Request to trigger POV generation."""

    engagement_id: str = Field(..., description="Engagement UUID")
    scope: str = Field(default="all", description="Scope filter for evidence")
    generated_by: str = Field(default="lcd_algorithm", description="Generator identifier")


class POVGenerateResponse(BaseModel):
    """Response for POV generation trigger."""

    job_id: str
    status: str
    message: str


class ProcessModelResponse(BaseModel):
    """Response schema for a process model."""

    model_config = {"from_attributes": True}

    id: str
    engagement_id: str
    version: int
    scope: str
    status: str
    confidence_score: float
    bpmn_xml: str | None = None
    element_count: int
    evidence_count: int
    contradiction_count: int
    metadata_json: dict | None = None
    generated_at: Any | None = None
    generated_by: str


class ProcessElementResponse(BaseModel):
    """Response schema for a process element."""

    model_config = {"from_attributes": True}

    id: str
    model_id: str
    element_type: str
    name: str
    confidence_score: float
    triangulation_score: float
    corroboration_level: str
    evidence_count: int
    evidence_ids: list[str] | None = None
    metadata_json: dict | None = None


class ProcessElementList(BaseModel):
    """Paginated list of process elements."""

    items: list[ProcessElementResponse]
    total: int


class ContradictionResponse(BaseModel):
    """Response schema for a contradiction."""

    model_config = {"from_attributes": True}

    id: str
    model_id: str
    element_name: str
    field_name: str
    values: list[dict[str, str]] | None = None
    resolution_value: str | None = None
    resolution_reason: str | None = None
    evidence_ids: list[str] | None = None


class EvidenceGapResponse(BaseModel):
    """Response schema for an evidence gap."""

    model_config = {"from_attributes": True}

    id: str
    model_id: str
    gap_type: str
    description: str
    severity: str
    recommendation: str | None = None
    related_element_id: str | None = None


class ProcessElementDetailResponse(BaseModel):
    """Detailed response for a process element including brightness and grade."""

    id: str
    model_id: str
    element_type: str
    name: str
    confidence_score: float
    triangulation_score: float
    corroboration_level: str
    evidence_count: int
    evidence_ids: list[str] | None = None
    evidence_grade: str = "U"
    brightness_classification: str = "dark"
    mvc_threshold_passed: bool = False
    metadata_json: dict | None = None


class ElementEvidenceItem(BaseModel):
    """An evidence item linked to a process element."""

    id: str
    title: str
    category: str
    grade: str
    source: str | None = None
    created_at: str | None = None


class ElementEvidenceResponse(BaseModel):
    """Response for element-level evidence query."""

    element_id: str
    element_name: str
    evidence_items: list[ElementEvidenceItem]
    total: int


class EngagementBPMNResponse(BaseModel):
    """Response for engagement-scoped latest BPMN model."""

    engagement_id: str
    model_id: str
    version: int
    bpmn_xml: str
    confidence_score: float
    element_count: int
    elements: list[ProcessElementDetailResponse]


class DashboardKPIs(BaseModel):
    """Dashboard KPIs for an engagement's process model."""

    engagement_id: str
    model_version: int
    overall_confidence: float
    element_count: int
    brightness_distribution: dict[str, int]
    brightness_percentages: dict[str, float]
    evidence_coverage: float
    gap_count: int
    critical_gap_count: int


class EvidenceMapEntry(BaseModel):
    """An entry in the evidence-to-element mapping."""

    evidence_id: str
    element_names: list[str]
    element_ids: list[str]


class BPMNResponse(BaseModel):
    """Response containing BPMN XML and element confidence metadata."""

    model_id: str
    bpmn_xml: str
    element_confidences: dict[str, float] = {}


class JobStatusResponse(BaseModel):
    """Response for job status check."""

    job_id: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None


class ProgressResponse(BaseModel):
    """Response for POV generation progress tracking."""

    task_id: str
    status: str
    current_step: int
    step_name: str
    completion_percentage: int
    total_steps: int = TOTAL_STEPS
    completed_steps: list[dict[str, Any]] | None = None
    failed_step: dict[str, Any] | None = None
    total_duration_ms: int = 0


class VersionSummary(BaseModel):
    """Summary of a single POV version."""

    model_id: str
    version: int
    status: str
    confidence_score: float
    element_count: int
    generated_at: datetime | None = None


class VersionDiffResponse(BaseModel):
    """Version diff between two POV generations."""

    added_count: int = 0
    removed_count: int = 0
    changed_count: int = 0
    unchanged_count: int = 0
    added: list[str] = []
    removed: list[str] = []
    changed: list[str] = []


class VersionHistoryResponse(BaseModel):
    """Response for version history listing."""

    engagement_id: str
    versions: list[VersionSummary]
    total_versions: int
    diff: VersionDiffResponse | None = None


# -- Helpers ------------------------------------------------------------------


def _model_to_response(model: ProcessModel) -> dict[str, Any]:
    """Convert a ProcessModel ORM object to a response dict."""
    return {
        "id": str(model.id),
        "engagement_id": str(model.engagement_id),
        "version": model.version,
        "scope": model.scope,
        "status": str(model.status),
        "confidence_score": model.confidence_score,
        "bpmn_xml": model.bpmn_xml,
        "element_count": model.element_count,
        "evidence_count": model.evidence_count,
        "contradiction_count": model.contradiction_count,
        "metadata_json": model.metadata_json,
        "generated_at": model.generated_at,
        "generated_by": model.generated_by,
    }


def _element_to_response(elem: ProcessElement) -> dict[str, Any]:
    """Convert a ProcessElement ORM object to a response dict."""
    return {
        "id": str(elem.id),
        "model_id": str(elem.model_id),
        "element_type": str(elem.element_type),
        "name": elem.name,
        "confidence_score": elem.confidence_score,
        "triangulation_score": elem.triangulation_score,
        "corroboration_level": str(elem.corroboration_level),
        "evidence_count": elem.evidence_count,
        "evidence_ids": elem.evidence_ids,
        "metadata_json": elem.metadata_json,
    }


def _contradiction_to_response(c: Contradiction) -> dict[str, Any]:
    """Convert a Contradiction ORM object to a response dict."""
    return {
        "id": str(c.id),
        "model_id": str(c.model_id),
        "element_name": c.element_name,
        "field_name": c.field_name,
        "values": c.values,
        "resolution_value": c.resolution_value,
        "resolution_reason": c.resolution_reason,
        "evidence_ids": c.evidence_ids,
    }


def _gap_to_response(g: EvidenceGap) -> dict[str, Any]:
    """Convert an EvidenceGap ORM object to a response dict."""
    return {
        "id": str(g.id),
        "model_id": str(g.model_id),
        "gap_type": str(g.gap_type),
        "description": g.description,
        "severity": str(g.severity),
        "recommendation": g.recommendation,
        "related_element_id": str(g.related_element_id) if g.related_element_id else None,
    }


# -- Routes -------------------------------------------------------------------


@router.post("/generate", response_model=POVGenerateResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_pov_generation(
    payload: POVGenerateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("pov:generate")),
) -> dict[str, Any]:
    """Trigger POV generation for an engagement.

    Runs the LCD algorithm synchronously (MVP) and returns a job ID
    for tracking. In a future version, this would dispatch to a
    background task queue.
    """
    job_id = uuid.uuid4().hex

    # Track job as in-progress with initial progress
    await _set_job(
        request,
        job_id,
        {
            "status": "running",
            "result": None,
            "error": None,
            "progress": {
                "current_step": 0,
                "step_name": "Evidence Aggregation",
                "completion_percentage": 0,
                "total_steps": 8,
            },
        },
    )

    job_status = "failed"
    try:
        result = await generate_pov(
            session=session,
            engagement_id=payload.engagement_id,
            scope=payload.scope,
            generated_by=payload.generated_by,
        )

        try:
            eng_uuid = uuid.UUID(payload.engagement_id)
            await log_audit(
                session,
                eng_uuid,
                AuditAction.POV_GENERATED,
                f"POV generation scope={payload.scope}",
                actor=str(user.id),
            )
        except ValueError:
            pass  # engagement_id is not a valid UUID, skip audit

        await session.commit()

        job_data: dict[str, Any]
        if result.success and result.process_model:
            job_data = {
                "status": "completed",
                "result": {
                    "model_id": str(result.process_model.id),
                    "stats": result.stats,
                },
                "error": None,
                "progress": {
                    "current_step": 8,
                    "step_name": "Complete",
                    "completion_percentage": 100,
                    "total_steps": 8,
                },
            }
            job_status = "completed"
        else:
            job_data = {
                "status": "failed",
                "result": {
                    "model_id": str(result.process_model.id) if result.process_model else None,
                },
                "error": result.error,
                "progress": {
                    "current_step": 0,
                    "step_name": "Failed",
                    "completion_percentage": 0,
                    "total_steps": 8,
                },
            }

        await _set_job(request, job_id, job_data)

    except (ValueError, RuntimeError) as e:
        logger.exception("POV generation failed")
        await _set_job(
            request,
            job_id,
            {
                "status": "failed",
                "result": None,
                "error": str(e),
                "progress": {
                    "current_step": 0,
                    "step_name": "Failed",
                    "completion_percentage": 0,
                    "total_steps": 8,
                },
            },
        )

    return {
        "job_id": job_id,
        "status": job_status,
        "message": f"POV generation {'completed' if job_status == 'completed' else 'failed'}",
    }


@router.get("/job/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    request: Request,
    user: User = Depends(require_permission("pov:read")),
) -> dict[str, Any]:
    """Get the status of a POV generation job."""
    job = await _get_job(request, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    return {
        "job_id": job_id,
        "status": job["status"],
        "result": job.get("result"),
        "error": job.get("error"),
    }


@router.get("/job/{job_id}/progress", response_model=ProgressResponse)
async def get_job_progress(
    job_id: str,
    request: Request,
    user: User = Depends(require_permission("pov:read")),
) -> dict[str, Any]:
    """Get detailed progress for a POV generation task.

    Returns current step, step name, completion percentage, and per-step
    results for monitoring the 8-step LCD algorithm pipeline.
    """
    job = await _get_job(request, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    # Extract progress fields from stored job data (set by PovGenerationWorker)
    progress = job.get("progress", {})
    return {
        "task_id": job_id,
        "status": job.get("status", "unknown"),
        "current_step": progress.get("current_step", 0),
        "step_name": progress.get("step_name", ""),
        "completion_percentage": progress.get("completion_percentage", 0),
        "total_steps": progress.get("total_steps", 8),
        "completed_steps": progress.get("completed_steps"),
        "failed_step": progress.get("failed_step"),
        "total_duration_ms": progress.get("total_duration_ms", 0),
    }


@router.get("/engagement/{engagement_id}/versions", response_model=VersionHistoryResponse)
async def get_version_history(
    engagement_id: str,
    include_diff: bool = Query(default=False, description="Include diff between latest two versions"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("pov:read")),
) -> dict[str, Any]:
    """Get version history for an engagement's POV generations.

    Returns all POV versions ordered by version number descending.
    Optionally includes a diff between the latest two versions.
    """
    try:
        eng_uuid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid engagement ID format",
        ) from None

    await _check_engagement_member(session, user, eng_uuid)

    # Get all versions for this engagement ordered by version desc
    query = select(ProcessModel).where(ProcessModel.engagement_id == eng_uuid).order_by(ProcessModel.version.desc())
    result = await session.execute(query)
    models = list(result.scalars().all())

    versions = [
        {
            "model_id": str(m.id),
            "version": m.version,
            "status": str(m.status),
            "confidence_score": m.confidence_score,
            "element_count": m.element_count,
            "generated_at": m.generated_at,
        }
        for m in models
    ]

    response: dict[str, Any] = {
        "engagement_id": engagement_id,
        "versions": versions,
        "total_versions": len(versions),
        "diff": None,
    }

    # Optionally compute diff between latest two versions
    if include_diff and len(models) >= 2:
        latest = models[0]
        previous = models[1]

        # Get elements for both versions
        latest_elements = await _get_elements_for_model(session, latest.id)
        previous_elements = await _get_elements_for_model(session, previous.id)

        diff = compute_version_diff(previous_elements, latest_elements)
        response["diff"] = diff

    return response


async def _get_elements_for_model(
    session: AsyncSession,
    model_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Get elements for a model as simple dicts for version comparison."""
    result = await session.execute(select(ProcessElement).where(ProcessElement.model_id == model_id))
    return [
        {
            "name": e.name,
            "confidence_score": e.confidence_score,
        }
        for e in result.scalars().all()
    ]


@router.get("/{model_id}", response_model=ProcessModelResponse)
async def get_process_model(
    model_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("pov:read")),
) -> dict[str, Any]:
    """Get a process model by ID."""
    try:
        model_uuid = uuid.UUID(model_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid model ID format",
        ) from None

    result = await session.execute(select(ProcessModel).where(ProcessModel.id == model_uuid))
    model = result.scalar_one_or_none()

    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Process model {model_id} not found",
        )

    return _model_to_response(model)


@router.get("/{model_id}/elements", response_model=ProcessElementList)
async def get_process_elements(
    model_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("pov:read")),
) -> dict[str, Any]:
    """Get elements for a process model with pagination."""
    try:
        model_uuid = uuid.UUID(model_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid model ID format",
        ) from None

    # Verify model exists
    model_result = await session.execute(select(ProcessModel.id).where(ProcessModel.id == model_uuid))
    if not model_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Process model {model_id} not found",
        )

    # Get elements
    query = select(ProcessElement).where(ProcessElement.model_id == model_uuid).offset(offset).limit(limit)
    result = await session.execute(query)
    elements = list(result.scalars().all())

    # Get total count
    count_result = await session.execute(
        select(func.count()).select_from(ProcessElement).where(ProcessElement.model_id == model_uuid)
    )
    total = count_result.scalar() or 0

    return {
        "items": [_element_to_response(e) for e in elements],
        "total": total,
    }


@router.get("/{model_id}/evidence-map", response_model=list[EvidenceMapEntry])
async def get_evidence_map(
    model_id: str,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("pov:read")),
) -> list[dict[str, Any]]:
    """Get evidence-to-element mappings for a process model."""
    try:
        model_uuid = uuid.UUID(model_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid model ID format",
        ) from None

    # Get elements for this model with pagination
    query = select(ProcessElement).where(ProcessElement.model_id == model_uuid).limit(limit).offset(offset)
    result = await session.execute(query)
    elements = list(result.scalars().all())

    if not elements:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Process model {model_id} not found or has no elements",
        )

    # Build reverse mapping: evidence_id -> elements
    evidence_map: dict[str, dict[str, list[str]]] = {}
    for elem in elements:
        if elem.evidence_ids:
            for ev_id in elem.evidence_ids:
                if ev_id not in evidence_map:
                    evidence_map[ev_id] = {"names": [], "ids": []}
                evidence_map[ev_id]["names"].append(elem.name)
                evidence_map[ev_id]["ids"].append(str(elem.id))

    return [
        {
            "evidence_id": ev_id,
            "element_names": data["names"],
            "element_ids": data["ids"],
        }
        for ev_id, data in evidence_map.items()
    ]


@router.get("/{model_id}/gaps", response_model=list[EvidenceGapResponse])
async def get_evidence_gaps(
    model_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("pov:read")),
) -> list[dict[str, Any]]:
    """Get evidence gaps for a process model."""
    try:
        model_uuid = uuid.UUID(model_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid model ID format",
        ) from None

    query = select(EvidenceGap).where(EvidenceGap.model_id == model_uuid).limit(limit).offset(offset)
    result = await session.execute(query)
    gaps = list(result.scalars().all())

    return [_gap_to_response(g) for g in gaps]


@router.get("/{model_id}/contradictions", response_model=list[ContradictionResponse])
async def get_contradictions(
    model_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("pov:read")),
) -> list[dict[str, Any]]:
    """Get contradictions for a process model."""
    try:
        model_uuid = uuid.UUID(model_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid model ID format",
        ) from None

    query = select(Contradiction).where(Contradiction.model_id == model_uuid).limit(limit).offset(offset)
    result = await session.execute(query)
    contradictions = list(result.scalars().all())

    return [_contradiction_to_response(c) for c in contradictions]


@router.get("/{model_id}/bpmn", response_model=BPMNResponse)
async def get_bpmn_xml(
    model_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("pov:read")),
) -> dict[str, Any]:
    """Get BPMN XML for a process model with element confidence scores.

    Returns the BPMN XML string and a mapping of element names
    to their confidence scores for visualization overlays.
    """
    try:
        model_uuid = uuid.UUID(model_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid model ID format",
        ) from None

    result = await session.execute(select(ProcessModel).where(ProcessModel.id == model_uuid))
    model = result.scalar_one_or_none()

    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Process model {model_id} not found",
        )

    if not model.bpmn_xml:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Process model {model_id} has no BPMN XML",
        )

    # Get element confidence scores
    elements_result = await session.execute(select(ProcessElement).where(ProcessElement.model_id == model_uuid))
    elements = list(elements_result.scalars().all())

    element_confidences = {elem.name: elem.confidence_score for elem in elements}

    return {
        "model_id": str(model.id),
        "bpmn_xml": model.bpmn_xml,
        "element_confidences": element_confidences,
    }


# -- BPMN Viewer API endpoints (Story #338) ---------------------------------


def _element_to_detail_response(elem: ProcessElement) -> dict[str, Any]:
    """Convert a ProcessElement to a detailed response dict."""
    return {
        "id": str(elem.id),
        "model_id": str(elem.model_id),
        "element_type": str(elem.element_type),
        "name": elem.name,
        "confidence_score": elem.confidence_score,
        "triangulation_score": elem.triangulation_score,
        "corroboration_level": str(elem.corroboration_level),
        "evidence_count": elem.evidence_count,
        "evidence_ids": elem.evidence_ids,
        "evidence_grade": str(elem.evidence_grade),
        "brightness_classification": str(elem.brightness_classification),
        "mvc_threshold_passed": elem.mvc_threshold_passed,
        "metadata_json": elem.metadata_json,
    }


@router.get(
    "/engagement/{engagement_id}/latest-model",
    response_model=EngagementBPMNResponse,
)
async def get_latest_model_for_engagement(
    engagement_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("pov:read")),
) -> dict[str, Any]:
    """Get the latest process model with BPMN and elements for an engagement.

    Used by the BPMN.js viewer to load the process model for visualization.

    Args:
        engagement_id: The engagement UUID.
    """
    try:
        eng_uuid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid engagement ID format",
        ) from None

    await _check_engagement_member(session, user, eng_uuid)

    # Get latest model version
    model_result = await session.execute(
        select(ProcessModel)
        .where(ProcessModel.engagement_id == eng_uuid)
        .order_by(ProcessModel.version.desc())
        .limit(1)
    )
    model = model_result.scalar_one_or_none()

    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No process model found for engagement {engagement_id}",
        )

    if not model.bpmn_xml:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Latest process model has no BPMN XML",
        )

    # Get all elements for the model
    elements_result = await session.execute(select(ProcessElement).where(ProcessElement.model_id == model.id))
    elements = list(elements_result.scalars().all())

    return {
        "engagement_id": engagement_id,
        "model_id": str(model.id),
        "version": model.version,
        "bpmn_xml": model.bpmn_xml,
        "confidence_score": model.confidence_score,
        "element_count": model.element_count,
        "elements": [_element_to_detail_response(e) for e in elements],
    }


@router.get(
    "/elements/{element_id}/evidence",
    response_model=ElementEvidenceResponse,
)
async def get_element_evidence(
    element_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("pov:read")),
) -> dict[str, Any]:
    """Get evidence items linked to a specific process element.

    Returns all evidence items referenced by the element's evidence_ids.

    Args:
        element_id: The process element UUID.
    """
    try:
        elem_uuid = uuid.UUID(element_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid element ID format",
        ) from None

    # Fetch element
    elem_result = await session.execute(select(ProcessElement).where(ProcessElement.id == elem_uuid))
    element = elem_result.scalar_one_or_none()

    if not element:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Process element {element_id} not found",
        )

    # Verify engagement access via the element's parent model
    model_result = await session.execute(select(ProcessModel).where(ProcessModel.id == element.model_id))
    model = model_result.scalar_one_or_none()
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated process model not found",
        )
    await _check_engagement_member(session, user, model.engagement_id)

    # Fetch evidence items referenced by this element
    evidence_items: list[dict[str, Any]] = []
    if element.evidence_ids:
        evidence_uuids = []
        for eid in element.evidence_ids:
            try:
                evidence_uuids.append(uuid.UUID(str(eid)))
            except ValueError:
                continue

        if evidence_uuids:
            ev_result = await session.execute(select(EvidenceItem).where(EvidenceItem.id.in_(evidence_uuids)))
            for ev in ev_result.scalars().all():
                evidence_items.append(
                    {
                        "id": str(ev.id),
                        "title": ev.name,
                        "category": str(ev.category),
                        "grade": "N/A",
                        "source": ev.source_system,
                        "created_at": str(ev.created_at) if ev.created_at else None,
                    }
                )

    return {
        "element_id": str(element.id),
        "element_name": element.name,
        "evidence_items": evidence_items,
        "total": len(evidence_items),
    }


@router.get(
    "/engagement/{engagement_id}/dashboard",
    response_model=DashboardKPIs,
)
async def get_engagement_dashboard(
    engagement_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("pov:read")),
) -> dict[str, Any]:
    """Get dashboard KPIs for an engagement's process model.

    Returns confidence, brightness distribution, evidence coverage,
    and gap counts for the latest model version.

    Args:
        engagement_id: The engagement UUID.
    """
    try:
        eng_uuid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid engagement ID format",
        ) from None

    await _check_engagement_member(session, user, eng_uuid)

    # Get latest model
    model_result = await session.execute(
        select(ProcessModel)
        .where(ProcessModel.engagement_id == eng_uuid)
        .order_by(ProcessModel.version.desc())
        .limit(1)
    )
    model = model_result.scalar_one_or_none()

    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No process model found for engagement {engagement_id}",
        )

    # Get elements for brightness distribution
    elements_result = await session.execute(select(ProcessElement).where(ProcessElement.model_id == model.id))
    elements = list(elements_result.scalars().all())

    # Brightness distribution
    brightness_dist: dict[str, int] = {"bright": 0, "dim": 0, "dark": 0}
    for elem in elements:
        b = str(elem.brightness_classification)
        if b in brightness_dist:
            brightness_dist[b] += 1

    total_elements = len(elements) or 1
    brightness_pcts = {k: round(v / total_elements * 100, 1) for k, v in brightness_dist.items()}

    # Evidence coverage: elements with at least 1 evidence item
    with_evidence = sum(1 for e in elements if e.evidence_count > 0)
    evidence_coverage = round(with_evidence / total_elements * 100, 1)

    # Gap counts
    gap_result = await session.execute(
        select(func.count()).select_from(EvidenceGap).where(EvidenceGap.model_id == model.id)
    )
    gap_count = gap_result.scalar() or 0

    critical_gap_result = await session.execute(
        select(func.count())
        .select_from(EvidenceGap)
        .where(
            EvidenceGap.model_id == model.id,
            EvidenceGap.severity == "high",
        )
    )
    critical_gap_count = critical_gap_result.scalar() or 0

    return {
        "engagement_id": engagement_id,
        "model_version": model.version,
        "overall_confidence": model.confidence_score,
        "element_count": model.element_count,
        "brightness_distribution": brightness_dist,
        "brightness_percentages": brightness_pcts,
        "evidence_coverage": evidence_coverage,
        "gap_count": gap_count,
        "critical_gap_count": critical_gap_count,
    }


# -- Confidence Heatmap Schemas ----------------------------------------------


class ElementConfidenceEntry(BaseModel):
    """Confidence data for a single process element."""

    score: float
    brightness: str
    grade: str


class ConfidenceMapResponse(BaseModel):
    """Map of element_id to confidence data for heatmap rendering."""

    engagement_id: str
    model_version: int
    elements: dict[str, ElementConfidenceEntry]
    total_elements: int


class ConfidenceSummaryResponse(BaseModel):
    """Summary statistics of confidence distribution."""

    engagement_id: str
    model_version: int
    total_elements: int
    bright_count: int
    bright_percentage: float
    dim_count: int
    dim_percentage: float
    dark_count: int
    dark_percentage: float
    overall_confidence: float


# -- Confidence Heatmap Endpoints --------------------------------------------


@router.get(
    "/engagement/{engagement_id}/confidence",
    response_model=ConfidenceMapResponse,
)
async def get_confidence_map(
    engagement_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("pov:read")),
) -> dict[str, Any]:
    """Get per-element confidence data for heatmap rendering.

    Returns a map of element_id to {score, brightness, grade} for
    the latest model version.

    Args:
        engagement_id: The engagement UUID.
    """
    try:
        eng_uuid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid engagement ID format",
        ) from None

    await _check_engagement_member(session, user, eng_uuid)

    # Get latest model
    model_result = await session.execute(
        select(ProcessModel)
        .where(ProcessModel.engagement_id == eng_uuid)
        .order_by(ProcessModel.version.desc())
        .limit(1)
    )
    model = model_result.scalar_one_or_none()

    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No process model found for engagement {engagement_id}",
        )

    # Get all elements
    elements_result = await session.execute(select(ProcessElement).where(ProcessElement.model_id == model.id))
    elements = list(elements_result.scalars().all())

    elements_map: dict[str, dict[str, Any]] = {}
    for elem in elements:
        elements_map[str(elem.id)] = {
            "score": elem.confidence_score,
            "brightness": str(elem.brightness_classification),
            "grade": str(elem.evidence_grade),
        }

    return {
        "engagement_id": engagement_id,
        "model_version": model.version,
        "elements": elements_map,
        "total_elements": len(elements),
    }


@router.get(
    "/engagement/{engagement_id}/confidence/summary",
    response_model=ConfidenceSummaryResponse,
)
async def get_confidence_summary(
    engagement_id: str,
    output_format: str = Query(default="json", alias="format", pattern="^(json|csv)$"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("pov:read")),
) -> dict[str, Any] | Response:
    """Get summary statistics of confidence distribution for export.

    Returns counts and percentages for each brightness tier plus
    overall model confidence. Supports JSON and CSV formats.

    Args:
        engagement_id: The engagement UUID.
        output_format: Response format ('json' or 'csv').
    """
    try:
        eng_uuid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid engagement ID format",
        ) from None

    await _check_engagement_member(session, user, eng_uuid)

    # Get latest model
    model_result = await session.execute(
        select(ProcessModel)
        .where(ProcessModel.engagement_id == eng_uuid)
        .order_by(ProcessModel.version.desc())
        .limit(1)
    )
    model = model_result.scalar_one_or_none()

    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No process model found for engagement {engagement_id}",
        )

    # Get elements
    elements_result = await session.execute(select(ProcessElement).where(ProcessElement.model_id == model.id))
    elements = list(elements_result.scalars().all())

    total = len(elements) or 1
    bright = sum(1 for e in elements if e.brightness_classification == BrightnessClassification.BRIGHT)
    dim = sum(1 for e in elements if e.brightness_classification == BrightnessClassification.DIM)
    dark = sum(1 for e in elements if e.brightness_classification == BrightnessClassification.DARK)

    summary_data = {
        "engagement_id": engagement_id,
        "model_version": model.version,
        "total_elements": len(elements),
        "bright_count": bright,
        "bright_percentage": round(bright / total * 100, 1),
        "dim_count": dim,
        "dim_percentage": round(dim / total * 100, 1),
        "dark_count": dark,
        "dark_percentage": round(dark / total * 100, 1),
        "overall_confidence": model.confidence_score,
    }

    if output_format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Metric", "Value"])
        writer.writerow(["Engagement ID", engagement_id])
        writer.writerow(["Model Version", model.version])
        writer.writerow(["Total Elements", len(elements)])
        writer.writerow(["Bright Count", bright])
        writer.writerow(["Bright %", summary_data["bright_percentage"]])
        writer.writerow(["Dim Count", dim])
        writer.writerow(["Dim %", summary_data["dim_percentage"]])
        writer.writerow(["Dark Count", dark])
        writer.writerow(["Dark %", summary_data["dark_percentage"]])
        writer.writerow(["Overall Confidence", model.confidence_score])

        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="confidence-summary-{engagement_id}.csv"'},
        )

    return summary_data


# -- Evidence Mapping Schemas ------------------------------------------------


class ReverseElementEntry(BaseModel):
    """A process element that references a given evidence item."""

    element_id: str
    element_name: str
    element_type: str
    confidence_score: float
    brightness_classification: str


class ReverseEvidenceLookupResponse(BaseModel):
    """Process elements that reference a specific evidence item."""

    evidence_id: str
    elements: list[ReverseElementEntry]
    total: int


class DarkElementEntry(BaseModel):
    """A dark (unsupported) process element."""

    element_id: str
    element_name: str
    element_type: str
    confidence_score: float
    evidence_count: int
    suggested_actions: list[str]


class DarkElementsResponse(BaseModel):
    """List of process elements with no supporting evidence."""

    engagement_id: str
    model_version: int
    dark_elements: list[DarkElementEntry]
    total: int


# -- Evidence Mapping Endpoints ----------------------------------------------


@router.get(
    "/evidence/{evidence_id}/process-elements",
    response_model=ReverseEvidenceLookupResponse,
)
async def get_elements_for_evidence(
    evidence_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("pov:read")),
) -> dict[str, Any]:
    """Reverse lookup: get all process elements that reference a given evidence item.

    Used for highlighting linked elements when an evidence item is selected.

    Args:
        evidence_id: The evidence item UUID.
    """
    try:
        ev_uuid = uuid.UUID(evidence_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid evidence ID format",
        ) from None

    # Verify the evidence item exists and get its engagement for access control
    ev_result = await session.execute(select(EvidenceItem).where(EvidenceItem.id == ev_uuid))
    evidence = ev_result.scalar_one_or_none()
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence item {evidence_id} not found",
        )

    await _check_engagement_member(session, user, evidence.engagement_id)

    # Get the latest model for the engagement
    model_result = await session.execute(
        select(ProcessModel)
        .where(ProcessModel.engagement_id == evidence.engagement_id)
        .order_by(ProcessModel.version.desc())
        .limit(1)
    )
    model = model_result.scalar_one_or_none()

    matching_elements: list[dict[str, Any]] = []
    if model:
        # Get elements for this model and filter by evidence_id
        elements_result = await session.execute(
            select(ProcessElement).where(
                ProcessElement.model_id == model.id,
                ProcessElement.evidence_ids.isnot(None),
            )
        )
        for elem in elements_result.scalars().all():
            if elem.evidence_ids and str(ev_uuid) in [str(eid) for eid in elem.evidence_ids]:
                matching_elements.append(
                    {
                        "element_id": str(elem.id),
                        "element_name": elem.name,
                        "element_type": str(elem.element_type),
                        "confidence_score": elem.confidence_score,
                        "brightness_classification": str(elem.brightness_classification),
                    }
                )

    return {
        "evidence_id": evidence_id,
        "elements": matching_elements,
        "total": len(matching_elements),
    }


@router.get(
    "/engagement/{engagement_id}/dark-elements",
    response_model=DarkElementsResponse,
)
async def get_dark_elements(
    engagement_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("pov:read")),
) -> dict[str, Any]:
    """Get all unsupported (dark) process elements for an engagement.

    Returns elements with no evidence, along with suggested evidence
    acquisition actions.

    Args:
        engagement_id: The engagement UUID.
    """
    try:
        eng_uuid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid engagement ID format",
        ) from None

    await _check_engagement_member(session, user, eng_uuid)

    # Get latest model
    model_result = await session.execute(
        select(ProcessModel)
        .where(ProcessModel.engagement_id == eng_uuid)
        .order_by(ProcessModel.version.desc())
        .limit(1)
    )
    model = model_result.scalar_one_or_none()

    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No process model found for engagement {engagement_id}",
        )

    # Get dark elements (no evidence)
    elements_result = await session.execute(
        select(ProcessElement).where(
            ProcessElement.model_id == model.id,
            ProcessElement.evidence_count == 0,
        )
    )
    dark_elements = list(elements_result.scalars().all())

    dark_entries: list[dict[str, Any]] = []
    for elem in dark_elements:
        suggestions = _suggest_evidence_actions(str(elem.element_type), elem.name)
        dark_entries.append(
            {
                "element_id": str(elem.id),
                "element_name": elem.name,
                "element_type": str(elem.element_type),
                "confidence_score": elem.confidence_score,
                "evidence_count": elem.evidence_count,
                "suggested_actions": suggestions,
            }
        )

    return {
        "engagement_id": engagement_id,
        "model_version": model.version,
        "dark_elements": dark_entries,
        "total": len(dark_entries),
    }


def _suggest_evidence_actions(element_type: str, element_name: str) -> list[str]:
    """Generate suggested evidence acquisition actions for a dark element."""
    suggestions: list[str] = []

    if element_type == "activity":
        suggestions.append(f"Schedule SME interview about '{element_name}'")
        suggestions.append("Request process documentation or work instructions")
        suggestions.append("Review system logs for automated steps")
    elif element_type == "gateway":
        suggestions.append(f"Clarify decision criteria for '{element_name}'")
        suggestions.append("Request business rules documentation")
    elif element_type == "role":
        suggestions.append(f"Verify role assignment for '{element_name}'")
        suggestions.append("Request org chart or RACI matrix")
    elif element_type == "event":
        suggestions.append(f"Identify trigger conditions for '{element_name}'")
        suggestions.append("Review event logs or monitoring data")
    else:
        suggestions.append(f"Collect supporting evidence for '{element_name}'")
        suggestions.append("Schedule stakeholder interview")

    return suggestions


# -- Engagement Access Check -------------------------------------------------


async def _check_engagement_member(session: AsyncSession, user: User, engagement_id: uuid.UUID) -> None:
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


# -- Dark Room Backlog Schemas -----------------------------------------------


class MissingFormEntry(BaseModel):
    """A missing knowledge form entry in a dark segment."""

    form_number: int
    form_name: str
    recommended_probes: list[str]
    probe_type: str


class DarkSegmentEntry(BaseModel):
    """A single Dark Room backlog entry."""

    element_id: str
    element_name: str
    current_confidence: float
    brightness: str
    estimated_confidence_uplift: float
    missing_knowledge_forms: list[MissingFormEntry]
    missing_form_count: int
    covered_form_count: int


class DarkRoomResponse(BaseModel):
    """Response for the Dark Room backlog."""

    engagement_id: str
    dark_threshold: float
    total_count: int
    items: list[DarkSegmentEntry]


# -- Dark Room Backlog Route -------------------------------------------------


@router.get("/{model_id}/dark-room", response_model=DarkRoomResponse)
async def get_dark_room_backlog(
    model_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    dark_threshold: float = Query(default=0.4, ge=0.0, le=1.0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("pov:read")),
) -> dict[str, Any]:
    """Get the Dark Room backlog for a process model.

    Returns a prioritized list of all Dark segments ranked by estimated
    confidence uplift. Each entry shows missing knowledge forms and
    recommended probes for evidence acquisition.
    """
    try:
        model_uuid = uuid.UUID(model_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid model ID format",
        ) from None

    result = await session.execute(select(ProcessModel).where(ProcessModel.id == model_uuid))
    model = result.scalar_one_or_none()

    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Process model {model_id} not found",
        )

    await _check_engagement_member(session, user, model.engagement_id)

    graph_service = KnowledgeGraphService(request.app.state.neo4j_driver)
    backlog_service = DarkRoomBacklogService(graph_service, dark_threshold=dark_threshold)

    backlog = await backlog_service.get_dark_segments(
        engagement_id=str(model.engagement_id),
        limit=limit,
        offset=offset,
    )
    return backlog


# -- Illumination Plan Helpers -----------------------------------------------


async def _get_model_or_404(session: AsyncSession, model_id: str) -> ProcessModel:
    """Look up a process model by ID, raising 404 if not found."""
    try:
        model_uuid = uuid.UUID(model_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid model ID format",
        ) from None

    result = await session.execute(select(ProcessModel).where(ProcessModel.id == model_uuid))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Process model {model_id} not found",
        )
    return model


# -- Illumination Plan Schemas -----------------------------------------------


class IlluminationActionEntry(BaseModel):
    """A single illumination action."""

    id: str
    element_id: str
    element_name: str
    action_type: str
    target_knowledge_form: int
    target_form_name: str
    status: str
    linked_item_id: str | None = None


class IlluminationPlanResponse(BaseModel):
    """Response for creating an illumination plan."""

    engagement_id: str
    element_id: str
    actions_created: int
    actions: list[IlluminationActionEntry]


class IlluminationProgressResponse(BaseModel):
    """Response for illumination progress."""

    engagement_id: str
    element_id: str
    total_actions: int
    completed_actions: int
    pending_actions: int
    in_progress_actions: int
    all_complete: bool
    actions: list[dict]


class ActionStatusUpdateRequest(BaseModel):
    """Request to update an illumination action's status."""

    status: Literal["pending", "in_progress", "complete"]
    linked_item_id: str | None = None


class ActionStatusUpdateResponse(BaseModel):
    """Response after updating an action's status."""

    id: str
    element_id: str
    action_type: str
    target_knowledge_form: int
    status: str
    linked_item_id: str | None = None


class SegmentCompletionResponse(BaseModel):
    """Response for segment completion check."""

    element_id: str
    all_complete: bool
    total_actions: int
    completed_actions: int
    should_recalculate: bool


# -- Illumination Plan Routes ------------------------------------------------


@router.post(
    "/{model_id}/dark-room/{element_id}/illuminate",
    response_model=IlluminationPlanResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_illumination_plan(
    model_id: str,
    element_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("pov:read")),
) -> dict[str, Any]:
    """Create an illumination plan for a Dark segment.

    Generates acquisition actions based on missing knowledge forms.
    Each missing form maps to a shelf request, persona probe, or
    system extraction action.
    """
    model = await _get_model_or_404(session, model_id)
    await _check_engagement_member(session, user, model.engagement_id)

    # Idempotency: check for existing non-complete actions
    from src.core.models import IlluminationAction

    existing = await session.execute(
        select(IlluminationAction).where(
            IlluminationAction.engagement_id == model.engagement_id,
            IlluminationAction.element_id == element_id,
            IlluminationAction.status != IlluminationActionStatus.COMPLETE,
        )
    )
    if existing.scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Active illumination plan already exists for element {element_id}",
        )

    graph_service = KnowledgeGraphService(request.app.state.neo4j_driver)
    backlog_service = DarkRoomBacklogService(graph_service)

    # Get dark segments to find the element's missing forms
    backlog = await backlog_service.get_dark_segments(engagement_id=str(model.engagement_id), limit=500)
    target_item = next(
        (item for item in backlog["items"] if item["element_id"] == element_id),
        None,
    )
    if target_item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Element {element_id} not found in Dark Room backlog",
        )

    planner = IlluminationPlannerService(session)
    actions = await planner.create_illumination_plan(
        engagement_id=str(model.engagement_id),
        element_id=element_id,
        element_name=target_item["element_name"],
        missing_forms=target_item["missing_knowledge_forms"],
    )

    await log_audit(
        session,
        model.engagement_id,
        AuditAction.EPISTEMIC_PLAN_GENERATED,
        f"Created illumination plan with {len(actions)} actions for {element_id}",
        actor=str(user.id),
    )
    await session.commit()

    return {
        "engagement_id": str(model.engagement_id),
        "element_id": element_id,
        "actions_created": len(actions),
        "actions": actions,
    }


@router.get(
    "/{model_id}/dark-room/{element_id}/progress",
    response_model=IlluminationProgressResponse,
)
async def get_illumination_progress(
    model_id: str,
    element_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("pov:read")),
) -> dict[str, Any]:
    """Get illumination progress for a specific Dark segment.

    Returns total/completed/pending counts and per-action status.
    """
    model = await _get_model_or_404(session, model_id)
    await _check_engagement_member(session, user, model.engagement_id)

    planner = IlluminationPlannerService(session)
    progress = await planner.get_progress(
        engagement_id=str(model.engagement_id),
        element_id=element_id,
    )
    return progress


@router.patch(
    "/{model_id}/dark-room/actions/{action_id}",
    response_model=ActionStatusUpdateResponse,
)
async def update_action_status(
    model_id: str,
    action_id: str,
    payload: ActionStatusUpdateRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("pov:read")),
) -> dict[str, Any]:
    """Update the status of an illumination action.

    Transitions an action between pending, in_progress, and complete states.
    """
    model = await _get_model_or_404(session, model_id)
    await _check_engagement_member(session, user, model.engagement_id)

    try:
        new_status = IlluminationActionStatus(payload.status)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status: {payload.status}. Must be one of: pending, in_progress, complete",
        ) from None

    planner = IlluminationPlannerService(session)
    result = await planner.update_action_status(
        action_id=action_id,
        new_status=new_status,
        linked_item_id=payload.linked_item_id,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action {action_id} not found",
        )

    await session.commit()
    return result


@router.get(
    "/{model_id}/dark-room/{element_id}/completion",
    response_model=SegmentCompletionResponse,
)
async def check_segment_completion(
    model_id: str,
    element_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("pov:read")),
) -> dict[str, Any]:
    """Check if all illumination actions for a segment are complete.

    Returns completion status and whether confidence recalculation
    should be triggered.
    """
    model = await _get_model_or_404(session, model_id)
    await _check_engagement_member(session, user, model.engagement_id)

    planner = IlluminationPlannerService(session)
    completion = await planner.check_segment_completion(
        engagement_id=str(model.engagement_id),
        element_id=element_id,
    )
    return completion
