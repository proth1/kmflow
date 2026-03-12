"""Graph analytics API routes (KMFLOW-67).

Exposes graph metrics, relationship analysis, and triangulation
results for knowledge graph introspection.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import User
from src.core.permissions import require_engagement_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/graph-analytics", tags=["graph-analytics"])


# -- Request/Response Schemas ------------------------------------------------


class GraphMetricsResponse(BaseModel):
    """Graph metrics for an engagement."""

    engagement_id: str
    total_nodes: int
    total_relationships: int
    nodes_by_label: dict[str, int]
    relationships_by_type: dict[str, int]
    avg_degree: float
    density: float


class TriangulationResult(BaseModel):
    """Triangulation result for a single activity."""

    activity_name: str
    evidence_planes: list[str]
    plane_count: int
    has_system_behavioral: bool
    has_documented_formal: bool
    has_human_interpretation: bool
    triangulation_score: float


class TriangulationResponse(BaseModel):
    """Triangulation results for an engagement."""

    engagement_id: str
    activities: list[TriangulationResult]
    total_activities: int
    fully_triangulated_count: int
    partially_triangulated_count: int
    untriangulated_count: int


class RelationshipAnalysisResponse(BaseModel):
    """Relationship analysis for a specific node."""

    node_id: str
    node_label: str
    node_name: str
    incoming: list[dict[str, Any]]
    outgoing: list[dict[str, Any]]
    total_relationships: int


# -- Endpoints ---------------------------------------------------------------


@router.get("/metrics/{engagement_id}", response_model=GraphMetricsResponse)
async def get_graph_metrics(
    engagement_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get graph metrics for an engagement.

    Returns node/relationship counts, average degree, and graph density.
    """
    from src.semantic.graph import KnowledgeGraphService

    graph_service = KnowledgeGraphService()
    stats = await graph_service.get_stats(str(engagement_id))

    total_nodes = sum(stats.nodes_by_label.values())
    total_rels = sum(stats.relationships_by_type.values())

    # Compute density: edges / (nodes * (nodes - 1)) for directed graph
    density = 0.0
    if total_nodes > 1:
        density = total_rels / (total_nodes * (total_nodes - 1))

    # Average degree: total_rels / total_nodes
    avg_degree = total_rels / total_nodes if total_nodes > 0 else 0.0

    return {
        "engagement_id": str(engagement_id),
        "total_nodes": total_nodes,
        "total_relationships": total_rels,
        "nodes_by_label": stats.nodes_by_label,
        "relationships_by_type": stats.relationships_by_type,
        "avg_degree": round(avg_degree, 2),
        "density": round(density, 6),
    }


@router.get("/triangulation/{engagement_id}", response_model=TriangulationResponse)
async def get_triangulation_results(
    engagement_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_engagement_access),
    min_planes: int = Query(0, ge=0, le=3, description="Minimum evidence planes"),
) -> dict[str, Any]:
    """Get evidence triangulation results for an engagement.

    Uses the POV triangulation engine to show which activities have
    evidence from multiple planes (system_behavioral, documented_formal,
    human_interpretation).
    """
    # Fetch evidence fragments for the engagement
    from sqlalchemy import select

    from src.core.models import EvidenceItem
    from src.pov.triangulation import triangulate_elements
    from src.semantic.entity_extraction import extract_entities

    evidence_result = await session.execute(select(EvidenceItem).where(EvidenceItem.engagement_id == engagement_id))
    evidence_items = list(evidence_result.scalars().all())

    if not evidence_items:
        return {
            "engagement_id": str(engagement_id),
            "activities": [],
            "total_activities": 0,
            "fully_triangulated_count": 0,
            "partially_triangulated_count": 0,
            "untriangulated_count": 0,
        }

    # Extract entities from evidence content and build entity-to-evidence map
    all_entities = []
    entity_to_evidence: dict[str, list[str]] = {}

    for item in evidence_items:
        content = getattr(item, "raw_content", "") or getattr(item, "content", "") or ""
        if not content:
            continue
        result = await extract_entities(str(content))
        for entity in result.entities:
            all_entities.append(entity)
            if entity.id not in entity_to_evidence:
                entity_to_evidence[entity.id] = []
            entity_to_evidence[entity.id].append(str(item.id))

    # Run triangulation
    triangulated = triangulate_elements(all_entities, entity_to_evidence, evidence_items)

    activities = []
    fully = 0
    partially = 0
    un = 0

    for elem in triangulated:
        planes = list(elem.supporting_planes)
        plane_count = len(planes)

        if plane_count < min_planes:
            continue

        has_system = "system_behavioral" in planes
        has_documented = "documented_formal" in planes
        has_human = "human_interpretation" in planes
        score = plane_count / 3.0

        if plane_count >= 3:
            fully += 1
        elif plane_count >= 1:
            partially += 1
        else:
            un += 1

        activities.append(
            {
                "activity_name": elem.entity.name,
                "evidence_planes": planes,
                "plane_count": plane_count,
                "has_system_behavioral": has_system,
                "has_documented_formal": has_documented,
                "has_human_interpretation": has_human,
                "triangulation_score": round(score, 2),
            }
        )

    return {
        "engagement_id": str(engagement_id),
        "activities": activities,
        "total_activities": len(activities),
        "fully_triangulated_count": fully,
        "partially_triangulated_count": partially,
        "untriangulated_count": un,
    }


@router.get("/relationships/{node_id}")
async def get_node_relationships(
    node_id: str,
    engagement_id: UUID = Query(..., description="Engagement ID for access control"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get all relationships for a specific graph node.

    Returns both incoming and outgoing relationships with their types
    and connected node details.
    """
    from src.semantic.graph import KnowledgeGraphService

    graph_service = KnowledgeGraphService()
    node = await graph_service.get_node(node_id)

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Verify engagement access
    node_engagement = node.properties.get("engagement_id", "")
    if node_engagement != str(engagement_id):
        raise HTTPException(status_code=403, detail="Node does not belong to this engagement")

    relationships = await graph_service.get_relationships(
        node_id=node_id,
    )

    incoming = []
    outgoing = []
    for rel in relationships:
        rel_dict = {
            "relationship_type": rel.relationship_type,
            "source_id": rel.source_id,
            "target_id": rel.target_id,
            "properties": rel.properties,
        }
        if rel.target_id == node_id:
            incoming.append(rel_dict)
        else:
            outgoing.append(rel_dict)

    return {
        "node_id": node.id,
        "node_label": node.label,
        "node_name": node.properties.get("name", ""),
        "incoming": incoming,
        "outgoing": outgoing,
        "total_relationships": len(relationships),
    }
