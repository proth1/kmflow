"""Ontology derivation API routes (KMFLOW-6).

Provides endpoints for triggering ontology derivation, viewing derived
ontologies, running validation, and exporting to OWL/YAML.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/engagements", tags=["ontology"])


@router.post("/{engagement_id}/ontology/derive")
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
    return result


@router.get("/{engagement_id}/ontology")
async def get_ontology(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _access: None = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get the latest derived ontology for an engagement.

    Returns the ontology version with all classes, properties, and axioms.
    """
    result = await session.execute(
        select(OntologyVersion)
        .where(OntologyVersion.engagement_id == engagement_id)
        .order_by(OntologyVersion.version.desc())
        .limit(1)
    )
    ontology = result.scalar_one_or_none()
    if not ontology:
        raise HTTPException(status_code=404, detail="No ontology found for this engagement")

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


@router.get("/{engagement_id}/ontology/export")
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
    result = await session.execute(
        select(OntologyVersion)
        .where(OntologyVersion.engagement_id == engagement_id)
        .order_by(OntologyVersion.version.desc())
        .limit(1)
    )
    ontology = result.scalar_one_or_none()
    if not ontology:
        raise HTTPException(status_code=404, detail="No ontology found for this engagement")

    service = OntologyExportService(session)
    export_result = await service.export(ontology.id, fmt=fmt)
    if "error" in export_result:
        raise HTTPException(status_code=404, detail=export_result["error"])

    return export_result


@router.get("/{engagement_id}/ontology/validation")
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
    result = await session.execute(
        select(OntologyVersion)
        .where(OntologyVersion.engagement_id == engagement_id)
        .order_by(OntologyVersion.version.desc())
        .limit(1)
    )
    ontology = result.scalar_one_or_none()
    if not ontology:
        raise HTTPException(status_code=404, detail="No ontology found for this engagement")

    service = OntologyValidationService(session)
    return await service.validate(ontology.id)
