"""Conformance checking API routes.

Provides endpoints for uploading reference BPMN models,
running conformance checks, and retrieving results.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.conformance.bpmn_parser import parse_bpmn_xml
from src.conformance.checker import ConformanceChecker
from src.conformance.metrics import calculate_metrics
from src.core.models import (
    ConformanceResult,
    ProcessModel,
    ReferenceProcessModel,
    User,
)
from src.core.permissions import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/conformance", tags=["conformance"])


# -- Schemas ------------------------------------------------------------------


class ReferenceModelCreate(BaseModel):
    """Schema for uploading a reference BPMN model."""
    name: str = Field(..., min_length=1, max_length=512)
    industry: str = Field(..., min_length=1, max_length=255)
    process_area: str = Field(..., min_length=1, max_length=255)
    bpmn_xml: str = Field(..., min_length=10)


class ReferenceModelResponse(BaseModel):
    """Schema for reference model responses."""
    id: str
    name: str
    industry: str
    process_area: str
    created_at: str


class ReferenceModelList(BaseModel):
    """Schema for listing reference models."""
    items: list[ReferenceModelResponse]
    total: int


class ConformanceCheckRequest(BaseModel):
    """Schema for triggering a conformance check."""
    engagement_id: UUID
    reference_model_id: UUID
    pov_model_id: UUID | None = None
    observed_bpmn_xml: str | None = None  # Alternative to pov_model_id


class DeviationResponse(BaseModel):
    """Schema for a single deviation."""
    element_name: str
    deviation_type: str
    severity: str
    description: str


class ConformanceCheckResponse(BaseModel):
    """Schema for conformance check results."""
    id: str
    fitness_score: float
    precision_score: float
    f1_score: float
    matching_elements: int
    total_reference_elements: int
    total_observed_elements: int
    deviations: list[DeviationResponse]
    deviation_count: int
    high_severity_count: int


class ConformanceResultResponse(BaseModel):
    """Schema for stored conformance result."""
    id: str
    engagement_id: str
    reference_model_id: str
    fitness_score: float
    precision_score: float
    deviations: dict[str, Any] | None
    created_at: str


class ConformanceResultList(BaseModel):
    """Schema for listing conformance results."""
    items: list[ConformanceResultResponse]
    total: int


# -- Dependency ---------------------------------------------------------------


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        yield session


# -- Routes -------------------------------------------------------------------


@router.post("/reference-models", response_model=ReferenceModelResponse, status_code=status.HTTP_201_CREATED)
async def create_reference_model(
    payload: ReferenceModelCreate,
    user: User = Depends(require_permission("conformance:manage")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Upload a reference BPMN model for conformance checking."""
    # Validate that the BPMN XML is parseable
    graph = parse_bpmn_xml(payload.bpmn_xml)
    if not graph.elements:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid BPMN XML: no process elements found",
        )

    model = ReferenceProcessModel(
        name=payload.name,
        industry=payload.industry,
        process_area=payload.process_area,
        bpmn_xml=payload.bpmn_xml,
        graph_data={
            "element_count": len(graph.elements),
            "task_count": len(graph.tasks),
            "flow_count": len(graph.flows),
        },
    )
    session.add(model)
    await session.commit()
    await session.refresh(model)

    return {
        "id": str(model.id),
        "name": model.name,
        "industry": model.industry,
        "process_area": model.process_area,
        "created_at": model.created_at.isoformat() if model.created_at else "",
    }


@router.get("/reference-models", response_model=ReferenceModelList)
async def list_reference_models(
    industry: str | None = None,
    user: User = Depends(require_permission("conformance:check")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List available reference models."""
    query = select(ReferenceProcessModel)
    if industry:
        query = query.where(ReferenceProcessModel.industry == industry)

    result = await session.execute(query)
    models = result.scalars().all()

    return {
        "items": [
            {
                "id": str(m.id),
                "name": m.name,
                "industry": m.industry,
                "process_area": m.process_area,
                "created_at": m.created_at.isoformat() if m.created_at else "",
            }
            for m in models
        ],
        "total": len(list(models)),
    }


@router.post("/check", response_model=ConformanceCheckResponse)
async def run_conformance_check(
    payload: ConformanceCheckRequest,
    user: User = Depends(require_permission("conformance:check")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Run a conformance check between observed and reference models."""
    # Get reference model
    ref_result = await session.execute(
        select(ReferenceProcessModel).where(
            ReferenceProcessModel.id == payload.reference_model_id
        )
    )
    ref_model = ref_result.scalar_one_or_none()
    if not ref_model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reference model {payload.reference_model_id} not found",
        )

    # Get observed BPMN XML
    observed_xml = payload.observed_bpmn_xml
    if not observed_xml and payload.pov_model_id:
        pov_result = await session.execute(
            select(ProcessModel).where(ProcessModel.id == payload.pov_model_id)
        )
        pov_model = pov_result.scalar_one_or_none()
        if not pov_model or not pov_model.bpmn_xml:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"POV model {payload.pov_model_id} not found or has no BPMN XML",
            )
        observed_xml = pov_model.bpmn_xml

    if not observed_xml:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either pov_model_id or observed_bpmn_xml must be provided",
        )

    # Run conformance check
    checker = ConformanceChecker()
    check_result = checker.check_from_xml(ref_model.bpmn_xml, observed_xml)
    metrics = calculate_metrics(check_result)

    # Persist result
    db_result = ConformanceResult(
        engagement_id=payload.engagement_id,
        reference_model_id=payload.reference_model_id,
        pov_model_id=payload.pov_model_id,
        fitness_score=check_result.fitness_score,
        precision_score=check_result.precision_score,
        deviations={
            "items": [
                {
                    "element_name": d.element_name,
                    "deviation_type": d.deviation_type,
                    "severity": d.severity,
                    "description": d.description,
                }
                for d in check_result.deviations
            ],
            "details": check_result.details,
        },
    )
    session.add(db_result)
    await session.commit()
    await session.refresh(db_result)

    return {
        "id": str(db_result.id),
        "fitness_score": check_result.fitness_score,
        "precision_score": check_result.precision_score,
        "f1_score": metrics.f1_score,
        "matching_elements": check_result.matching_elements,
        "total_reference_elements": check_result.total_reference_elements,
        "total_observed_elements": check_result.total_observed_elements,
        "deviations": [
            {
                "element_name": d.element_name,
                "deviation_type": d.deviation_type,
                "severity": d.severity,
                "description": d.description,
            }
            for d in check_result.deviations
        ],
        "deviation_count": metrics.deviation_count,
        "high_severity_count": metrics.high_severity_count,
    }


@router.get("/results/{result_id}", response_model=ConformanceResultResponse)
async def get_conformance_result(
    result_id: UUID,
    user: User = Depends(require_permission("conformance:check")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get a stored conformance check result."""
    result = await session.execute(
        select(ConformanceResult).where(ConformanceResult.id == result_id)
    )
    cr = result.scalar_one_or_none()
    if not cr:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conformance result {result_id} not found",
        )

    return {
        "id": str(cr.id),
        "engagement_id": str(cr.engagement_id),
        "reference_model_id": str(cr.reference_model_id),
        "fitness_score": cr.fitness_score,
        "precision_score": cr.precision_score,
        "deviations": cr.deviations,
        "created_at": cr.created_at.isoformat() if cr.created_at else "",
    }


@router.get("/results", response_model=ConformanceResultList)
async def list_conformance_results(
    engagement_id: UUID | None = None,
    user: User = Depends(require_permission("conformance:check")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List conformance check results."""
    query = select(ConformanceResult)
    if engagement_id:
        query = query.where(ConformanceResult.engagement_id == engagement_id)
    query = query.order_by(ConformanceResult.created_at.desc())

    result = await session.execute(query)
    results = result.scalars().all()

    return {
        "items": [
            {
                "id": str(cr.id),
                "engagement_id": str(cr.engagement_id),
                "reference_model_id": str(cr.reference_model_id),
                "fitness_score": cr.fitness_score,
                "precision_score": cr.precision_score,
                "deviations": cr.deviations,
                "created_at": cr.created_at.isoformat() if cr.created_at else "",
            }
            for cr in results
        ],
        "total": len(list(results)),
    }
