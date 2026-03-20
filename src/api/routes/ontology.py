"""Ontology derivation API routes (KMFLOW-6).

Provides endpoints for triggering ontology derivation, viewing derived
ontologies, running validation, and exporting to OWL/YAML.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import User
from src.core.models.ontology import (
    OntologyAxiom,
    OntologyClass,
    OntologyProperty,
    OntologyVersion,
)
from src.core.permissions import require_engagement_access, require_permission
from src.semantic.ontology_derivation import OntologyDerivationService, OntologyValidationService
from src.semantic.ontology_export import OntologyExportService

# -- Schemas ------------------------------------------------------------------


class OntologyDeriveResponse(BaseModel):
    """Response for ontology derivation trigger."""

    ontology_id: str
    version: int
    status: str
    class_count: int
    property_count: int
    axiom_count: int


class OntologyClassItem(BaseModel):
    id: str
    name: str
    description: str | None = None
    parent: str | None = None
    instance_count: int
    confidence: float
    source_seed_terms: list[str] | None = None


class OntologyPropertyItem(BaseModel):
    id: str
    name: str
    source_edge_type: str | None = None
    domain: str | None = None
    range: str | None = None
    usage_count: int
    confidence: float


class OntologyAxiomItem(BaseModel):
    id: str
    expression: str
    type: str
    confidence: float
    source_pattern: str | None = None


class OntologyGetResponse(BaseModel):
    """Response for getting the latest ontology."""

    ontology_id: str
    engagement_id: str
    version: int
    status: str
    completeness_score: float
    derived_at: str | None = None
    classes: list[OntologyClassItem]
    properties: list[OntologyPropertyItem]
    axioms: list[OntologyAxiomItem]


class OntologyExportResponse(BaseModel):
    """Response for ontology export."""

    ontology_id: str
    format: str
    content: str
    sha256: str


class OntologyValidationResponse(BaseModel):
    """Response for ontology validation."""

    ontology_id: str
    completeness_score: float
    orphan_classes: list[str] = []
    disconnected_subgraphs: int = 0
    recommendations: list[str] = []


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/engagements", tags=["ontology"])


async def _get_latest_ontology(session: AsyncSession, engagement_id: UUID) -> OntologyVersion:
    """Fetch the latest ontology version for an engagement or raise 404."""
    result = await session.execute(
        select(OntologyVersion)
        .where(OntologyVersion.engagement_id == engagement_id)
        .order_by(OntologyVersion.version.desc())
        .limit(1)
    )
    ontology = result.scalar_one_or_none()
    if not ontology:
        raise HTTPException(status_code=404, detail="No ontology found for this engagement")
    return ontology


@router.post("/{engagement_id}/ontology/derive", response_model=OntologyDeriveResponse, status_code=201)
async def derive_ontology(
    engagement_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("pov:generate")),
    _access: None = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Trigger ontology derivation for an engagement.

    Analyzes the engagement's seed terms and knowledge graph relationships
    to produce a versioned domain ontology with classes, properties, and axioms.
    """
    neo4j_driver = getattr(request.app.state, "neo4j_driver", None)
    if neo4j_driver is None:
        raise HTTPException(status_code=503, detail="Neo4j is not available")

    service = OntologyDerivationService(session, neo4j_driver)
    result = await service.derive(engagement_id)
    await session.commit()
    return result


@router.get("/{engagement_id}/ontology", response_model=OntologyGetResponse)
async def get_ontology(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _access: None = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get the latest derived ontology for an engagement.

    Returns the ontology version with all classes, properties, and axioms.
    """
    ontology = await _get_latest_ontology(session, engagement_id)

    # Fetch related entities
    classes_result = await session.execute(select(OntologyClass).where(OntologyClass.ontology_id == ontology.id))
    classes = list(classes_result.scalars().all())

    props_result = await session.execute(select(OntologyProperty).where(OntologyProperty.ontology_id == ontology.id))
    properties = list(props_result.scalars().all())

    axioms_result = await session.execute(select(OntologyAxiom).where(OntologyAxiom.ontology_id == ontology.id))
    axioms = list(axioms_result.scalars().all())

    class_map = {c.id: c.name for c in classes}

    return {
        "ontology_id": str(ontology.id),
        "engagement_id": str(ontology.engagement_id),
        "version": ontology.version,
        "status": ontology.status.value,
        "completeness_score": ontology.completeness_score,
        "derived_at": ontology.derived_at.isoformat() if ontology.derived_at else None,
        "classes": [
            {
                "id": str(c.id),
                "name": c.name,
                "description": c.description,
                "parent": class_map.get(c.parent_class_id) if c.parent_class_id else None,
                "instance_count": c.instance_count,
                "confidence": c.confidence,
                "source_seed_terms": c.source_seed_terms,
            }
            for c in classes
        ],
        "properties": [
            {
                "id": str(p.id),
                "name": p.name,
                "source_edge_type": p.source_edge_type,
                "domain": class_map.get(p.domain_class_id) if p.domain_class_id else None,
                "range": class_map.get(p.range_class_id) if p.range_class_id else None,
                "usage_count": p.usage_count,
                "confidence": p.confidence,
            }
            for p in properties
        ],
        "axioms": [
            {
                "id": str(a.id),
                "expression": a.expression,
                "type": a.axiom_type,
                "confidence": a.confidence,
                "source_pattern": a.source_pattern,
            }
            for a in axioms
        ],
    }


@router.get("/{engagement_id}/ontology/export", response_model=OntologyExportResponse)
async def export_ontology(
    engagement_id: UUID,
    fmt: str = Query(default="yaml", pattern="^(owl|yaml)$"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _access: None = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Export the latest ontology in OWL/XML or YAML format.

    Returns the serialized content with a SHA-256 hash for integrity verification.
    """
    ontology = await _get_latest_ontology(session, engagement_id)

    service = OntologyExportService(session)
    export_result = await service.export(ontology.id, fmt=fmt)
    await session.commit()
    return export_result


@router.get("/{engagement_id}/ontology/validation", response_model=OntologyValidationResponse)
async def validate_ontology(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _access: None = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Run completeness validation on the latest derived ontology.

    Returns orphan classes, disconnected subgraphs, completeness score,
    and enrichment recommendations.
    """
    ontology = await _get_latest_ontology(session, engagement_id)

    service = OntologyValidationService(session)
    report = await service.validate(ontology.id)
    await session.commit()
    return report
