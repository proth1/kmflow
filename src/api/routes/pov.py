"""POV (Process Point of View) API routes.

Provides endpoints for generating, retrieving, and inspecting
process models created by the LCD algorithm.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import (
    Contradiction,
    EvidenceGap,
    ProcessElement,
    ProcessModel,
    User,
)
from src.core.permissions import require_permission
from src.pov.generator import generate_pov

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

    # Track job as in-progress
    await _set_job(request, job_id, {"status": "running", "result": None, "error": None})

    job_status = "failed"
    try:
        result = await generate_pov(
            session=session,
            engagement_id=payload.engagement_id,
            scope=payload.scope,
            generated_by=payload.generated_by,
        )

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
            }
            job_status = "completed"
        else:
            job_data = {
                "status": "failed",
                "result": {
                    "model_id": str(result.process_model.id) if result.process_model else None,
                },
                "error": result.error,
            }

        await _set_job(request, job_id, job_data)

    except (ValueError, RuntimeError) as e:
        logger.exception("POV generation failed")
        await _set_job(request, job_id, {"status": "failed", "result": None, "error": str(e)})

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

    # Get all elements for this model
    result = await session.execute(select(ProcessElement).where(ProcessElement.model_id == model_uuid))
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

    result = await session.execute(select(EvidenceGap).where(EvidenceGap.model_id == model_uuid))
    gaps = list(result.scalars().all())

    return [_gap_to_response(g) for g in gaps]


@router.get("/{model_id}/contradictions", response_model=list[ContradictionResponse])
async def get_contradictions(
    model_id: str,
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

    result = await session.execute(select(Contradiction).where(Contradiction.model_id == model_uuid))
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
