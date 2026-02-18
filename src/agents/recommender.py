"""Recommendation generation from identified gaps.

Converts gap analysis results into actionable recommendations
using knowledge graph queries and embedding similarity for
evidence-based confidence scoring.
"""

from __future__ import annotations

import logging
from typing import Any

from neo4j import AsyncDriver

logger = logging.getLogger(__name__)


async def generate_recommendations_graph(
    engagement_id: str,
    gaps: list[dict[str, Any]],
    neo4j_driver: AsyncDriver,
    existing_requests: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Generate evidence-based recommendations from gaps using the knowledge graph.

    Queries the graph for remediation patterns and similar evidence to
    produce recommendations with confidence scores based on evidence density.

    Args:
        engagement_id: The engagement to generate recommendations for.
        gaps: Identified gaps from gap scanner.
        neo4j_driver: Neo4j async driver.
        existing_requests: Already-created shelf data requests.

    Returns:
        Prioritized list of recommendations with confidence scores.
    """
    existing_items = set()
    if existing_requests:
        for req in existing_requests:
            for item in req.get("items", []):
                existing_items.add(item.get("item_name", "").lower())

    # Query graph for evidence density and relationship patterns
    async with neo4j_driver.session() as session:
        # Get node counts per label for context
        stats_result = await session.run(
            """
            MATCH (n {engagement_id: $engagement_id})
            RETURN labels(n)[0] AS label, count(n) AS count
            """,
            engagement_id=engagement_id,
        )
        node_counts: dict[str, int] = {}
        async for record in stats_result:
            node_counts[record["label"]] = record["count"]

        # Find well-connected nodes (strong evidence patterns)
        well_connected_result = await session.run(
            """
            MATCH (n {engagement_id: $engagement_id})-[r]-()
            WITH n, labels(n)[0] AS label, count(r) AS rel_count
            WHERE rel_count >= 3
            RETURN n.name AS name, label, rel_count
            ORDER BY rel_count DESC
            LIMIT 10
            """,
            engagement_id=engagement_id,
        )
        strong_patterns: list[dict[str, Any]] = []
        async for record in well_connected_result:
            strong_patterns.append({
                "name": record["name"],
                "label": record["label"],
                "relationship_count": record["rel_count"],
            })

    # Generate recommendations
    severity_order = {"high": 0, "medium": 1, "low": 2}
    sorted_gaps = sorted(gaps, key=lambda g: severity_order.get(g.get("severity", "low"), 3))

    recommendations: list[dict[str, Any]] = []
    total_nodes = sum(node_counts.values())

    for gap in sorted_gaps:
        rec_text = gap.get("recommendation", "")
        if rec_text.lower() in existing_items:
            continue

        # Calculate confidence based on graph density
        gap_type = gap.get("gap_type", "")
        confidence = _calculate_confidence(gap, node_counts, total_nodes, strong_patterns)

        recommendation = {
            "gap_type": gap_type,
            "severity": gap["severity"],
            "recommendation": rec_text,
            "element_name": gap.get("element_name"),
            "confidence": confidence,
            "auto_request": gap["severity"] in ("high", "medium") and confidence > 0.5,
            "evidence_context": _get_evidence_context(gap, strong_patterns),
        }

        # Add dimension-specific remediation guidance
        if gap_type == "dimension_coverage":
            dimension = gap.get("dimension", "")
            recommendation["remediation_strategy"] = _get_dimension_remediation(
                dimension, node_counts
            )

        recommendations.append(recommendation)

    return recommendations


def _calculate_confidence(
    gap: dict[str, Any],
    node_counts: dict[str, int],
    total_nodes: int,
    strong_patterns: list[dict[str, Any]],
) -> float:
    """Calculate recommendation confidence based on evidence density.

    Higher graph density = higher confidence in the recommendation.
    """
    base_confidence = 0.5

    # Adjust based on total graph size (more data = more confident)
    if total_nodes > 50:
        base_confidence += 0.2
    elif total_nodes > 20:
        base_confidence += 0.1

    # Adjust based on gap type
    gap_type = gap.get("gap_type", "")
    if gap_type == "unsupported_process":
        base_confidence += 0.1  # High confidence - clearly missing
    elif gap_type == "orphaned_node":
        base_confidence += 0.05
    elif gap_type == "dimension_coverage":
        score = gap.get("coverage_score", 0)
        base_confidence += 0.1 * (1 - score)  # Lower coverage = higher confidence

    # Adjust based on related strong patterns
    element_name = gap.get("element_name", "").lower()
    for pattern in strong_patterns:
        pattern_name = (pattern.get("name") or "").lower()
        # If strong patterns exist in related areas, increase confidence
        if any(word in pattern_name for word in element_name.split() if len(word) > 3):
            base_confidence += 0.05

    return round(min(1.0, base_confidence), 2)


def _get_evidence_context(
    gap: dict[str, Any],
    strong_patterns: list[dict[str, Any]],
) -> list[str]:
    """Get evidence context notes for a recommendation."""
    context: list[str] = []

    element_name = gap.get("element_name", "").lower()
    for pattern in strong_patterns:
        pattern_name = (pattern.get("name") or "").lower()
        if any(word in pattern_name for word in element_name.split() if len(word) > 3):
            context.append(
                f"Related well-connected element: {pattern['name']} "
                f"({pattern['label']}, {pattern['relationship_count']} relationships)"
            )

    return context


def _get_dimension_remediation(
    dimension: str,
    node_counts: dict[str, int],
) -> str:
    """Get dimension-specific remediation strategy."""
    strategies = {
        "process_architecture": (
            "Collect process documentation, workflow diagrams, and SOPs. "
            f"Current: {node_counts.get('Process', 0)} processes, {node_counts.get('Activity', 0)} activities."
        ),
        "people_and_organization": (
            "Gather org charts, role descriptions, and RACI matrices. "
            f"Current: {node_counts.get('Role', 0)} roles identified."
        ),
        "technology_and_data": (
            "Document system inventories, integration maps, and data flows. "
            f"Current: {node_counts.get('System', 0)} systems identified."
        ),
        "governance_structures": (
            "Collect policy documents, control frameworks, and approval matrices. "
            f"Current: {node_counts.get('Policy', 0)} policies, {node_counts.get('Control', 0)} controls."
        ),
        "performance_management": (
            "Gather KPI definitions, SLA documents, and performance dashboards. "
            f"Current: {node_counts.get('TOM', 0)} TOM elements."
        ),
        "risk_and_compliance": (
            "Collect risk registers, compliance checklists, and audit reports. "
            f"Current: {node_counts.get('Regulation', 0)} regulations, {node_counts.get('Control', 0)} controls."
        ),
    }
    return strategies.get(dimension, "Review evidence collection strategy for this dimension.")


def generate_recommendations(
    gaps: list[dict[str, Any]],
    existing_requests: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Generate prioritized recommendations from gaps (heuristic fallback).

    Used when Neo4j is not available. For graph-based recommendations,
    use generate_recommendations_graph() instead.

    Args:
        gaps: List of identified gaps from gap_scanner.
        existing_requests: Already-created shelf data requests.

    Returns:
        Prioritized list of recommendations.
    """
    existing_items = set()
    if existing_requests:
        for req in existing_requests:
            for item in req.get("items", []):
                existing_items.add(item.get("item_name", "").lower())

    severity_order = {"high": 0, "medium": 1, "low": 2}
    sorted_gaps = sorted(gaps, key=lambda g: severity_order.get(g.get("severity", "low"), 3))

    recommendations: list[dict[str, Any]] = []
    for gap in sorted_gaps:
        rec_text = gap.get("recommendation", "")
        if rec_text.lower() in existing_items:
            continue

        recommendations.append(
            {
                "gap_type": gap["gap_type"],
                "severity": gap["severity"],
                "recommendation": rec_text,
                "element_name": gap.get("element_name"),
                "auto_request": gap["severity"] in ("high", "medium"),
            }
        )

    return recommendations


def build_shelf_request_items(
    recommendations: list[dict[str, Any]],
    engagement_id: str,
) -> list[dict[str, Any]]:
    """Build shelf data request items from recommendations.

    Args:
        recommendations: Recommendations that should be auto-requested.
        engagement_id: Engagement to create requests for.

    Returns:
        List of shelf data request item dicts.
    """
    items: list[dict[str, Any]] = []
    for rec in recommendations:
        if not rec.get("auto_request"):
            continue

        category = "documents"
        if "structured_data" in rec.get("gap_type", ""):
            category = "structured_data"
        elif "bpm" in str(rec.get("element_name", "")):
            category = "bpm_process_models"

        priority = "high" if rec["severity"] == "high" else "medium"

        items.append(
            {
                "engagement_id": engagement_id,
                "category": category,
                "item_name": rec["recommendation"],
                "description": f"Auto-generated from gap analysis: {rec.get('gap_type', '')}",
                "priority": priority,
            }
        )

    return items
