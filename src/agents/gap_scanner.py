"""Proactive evidence gap identification agent.

Scans engagements for missing evidence, weak coverage areas,
and stale data using knowledge graph topology analysis.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from neo4j import AsyncDriver

logger = logging.getLogger(__name__)

# TOM dimensions and their expected node labels in the knowledge graph
_DIMENSION_NODE_LABELS: dict[str, list[str]] = {
    "process_architecture": ["Process", "Activity"],
    "people_and_organization": ["Role"],
    "technology_and_data": ["System"],
    "governance_structures": ["Policy", "Control"],
    "performance_management": ["TOM"],
    "risk_and_compliance": ["Regulation", "Control"],
}

# Minimum node counts for a dimension to be considered "covered"
_MIN_NODES_FOR_COVERAGE = 2
_MIN_RELATIONSHIPS_FOR_DENSITY = 3


async def scan_evidence_gaps_graph(
    engagement_id: str,
    neo4j_driver: AsyncDriver,
    coverage_threshold: float = 0.6,
) -> dict[str, Any]:
    """Scan for evidence gaps using knowledge graph topology.

    Analyzes the Neo4j graph for an engagement to identify:
    - Dimensions with insufficient node coverage
    - Orphaned nodes (no relationships)
    - Low relationship density areas
    - Missing bridge relationships

    Args:
        engagement_id: The engagement to scan.
        neo4j_driver: Neo4j async driver.
        coverage_threshold: Minimum coverage score (0-1) to not flag.

    Returns:
        Dict with dimension_scores, gaps, orphaned_nodes, and summary.
    """
    async with neo4j_driver.session() as session:
        # Count nodes by label
        node_result = await session.run(
            """
            MATCH (n {engagement_id: $engagement_id})
            RETURN labels(n)[0] AS label, count(n) AS count
            """,
            engagement_id=engagement_id,
        )
        nodes_by_label: dict[str, int] = {}
        async for record in node_result:
            nodes_by_label[record["label"]] = record["count"]

        # Count relationships by type
        rel_result = await session.run(
            """
            MATCH (a {engagement_id: $engagement_id})-[r]->(b)
            RETURN type(r) AS rel_type, count(r) AS count
            """,
            engagement_id=engagement_id,
        )
        rels_by_type: dict[str, int] = {}
        async for record in rel_result:
            rels_by_type[record["rel_type"]] = record["count"]

        # Find orphaned nodes (no relationships)
        orphan_result = await session.run(
            """
            MATCH (n {engagement_id: $engagement_id})
            WHERE NOT (n)-[]-()
            RETURN n.name AS name, labels(n)[0] AS label, n.id AS id
            """,
            engagement_id=engagement_id,
        )
        orphaned_nodes: list[dict[str, str]] = []
        async for record in orphan_result:
            orphaned_nodes.append(
                {
                    "id": record["id"],
                    "name": record["name"] or "Unknown",
                    "label": record["label"],
                }
            )

        # Check for Evidence nodes without SUPPORTED_BY
        unsupported_result = await session.run(
            """
            MATCH (n {engagement_id: $engagement_id})
            WHERE labels(n)[0] IN ['Process', 'Activity']
              AND NOT (n)-[:SUPPORTED_BY]->()
              AND NOT ()-[:SUPPORTED_BY]->(n)
            RETURN n.name AS name, labels(n)[0] AS label, n.id AS id
            """,
            engagement_id=engagement_id,
        )
        unsupported: list[dict[str, str]] = []
        async for record in unsupported_result:
            unsupported.append(
                {
                    "id": record["id"],
                    "name": record["name"] or "Unknown",
                    "label": record["label"],
                }
            )

    # Calculate dimension coverage scores
    dimension_scores: dict[str, float] = {}
    for dimension, labels in _DIMENSION_NODE_LABELS.items():
        total_nodes = sum(nodes_by_label.get(label, 0) for label in labels)
        if total_nodes >= _MIN_NODES_FOR_COVERAGE:
            # Score based on node count and relationship density
            node_score = min(1.0, total_nodes / (_MIN_NODES_FOR_COVERAGE * 3))
            dimension_scores[dimension] = round(node_score, 2)
        else:
            dimension_scores[dimension] = round(total_nodes / max(_MIN_NODES_FOR_COVERAGE, 1), 2)

    # Build gaps list
    gaps: list[dict[str, Any]] = []

    # Dimension coverage gaps
    for dimension, score in dimension_scores.items():
        if score < coverage_threshold:
            severity = "high" if score < 0.3 else "medium"
            gaps.append(
                {
                    "gap_type": "dimension_coverage",
                    "severity": severity,
                    "dimension": dimension,
                    "coverage_score": score,
                    "description": f"Dimension '{dimension}' has low graph coverage (score: {score:.2f})",
                    "recommendation": f"Add more evidence related to {dimension.replace('_', ' ')}",
                }
            )

    # Orphaned node gaps
    for node in orphaned_nodes:
        gaps.append(
            {
                "gap_type": "orphaned_node",
                "severity": "medium",
                "element_name": node["name"],
                "element_id": node["id"],
                "description": f"{node['label']} '{node['name']}' has no relationships",
                "recommendation": f"Add evidence linking '{node['name']}' to other elements",
            }
        )

    # Unsupported process elements
    for node in unsupported:
        gaps.append(
            {
                "gap_type": "unsupported_process",
                "severity": "high",
                "element_name": node["name"],
                "element_id": node["id"],
                "description": f"{node['label']} '{node['name']}' lacks evidence support",
                "recommendation": f"Collect evidence supporting '{node['name']}'",
            }
        )

    # Missing bridge relationship types
    expected_bridge_types = {"SUPPORTED_BY", "GOVERNED_BY", "IMPLEMENTS", "DEVIATES_FROM"}
    missing_bridges = expected_bridge_types - set(rels_by_type.keys())
    for bridge_type in missing_bridges:
        gaps.append(
            {
                "gap_type": "missing_bridge_type",
                "severity": "low",
                "element_name": bridge_type,
                "description": f"No {bridge_type} relationships exist in the graph",
                "recommendation": f"Run semantic bridges to create {bridge_type} relationships",
            }
        )

    total_nodes = sum(nodes_by_label.values())
    total_rels = sum(rels_by_type.values())

    return {
        "engagement_id": engagement_id,
        "dimension_scores": dimension_scores,
        "gaps": gaps,
        "orphaned_nodes": orphaned_nodes,
        "summary": {
            "total_nodes": total_nodes,
            "total_relationships": total_rels,
            "nodes_by_label": nodes_by_label,
            "relationships_by_type": rels_by_type,
            "gap_count": len(gaps),
            "dimensions_below_threshold": sum(1 for s in dimension_scores.values() if s < coverage_threshold),
        },
    }


def scan_evidence_gaps(
    evidence_items: list[dict[str, Any]],
    process_elements: list[dict[str, Any]],
    shelf_requests: list[dict[str, Any]] | None = None,
    coverage_threshold: float = 0.6,
) -> list[dict[str, Any]]:
    """Scan for evidence gaps across an engagement (heuristic fallback).

    Used when Neo4j is not available. For graph-aware scanning,
    use scan_evidence_gaps_graph() instead.

    Args:
        evidence_items: Current evidence items with categories and scores.
        process_elements: Process elements that need evidence support.
        shelf_requests: Existing shelf data requests.
        coverage_threshold: Minimum coverage score to not flag as gap.

    Returns:
        List of identified gaps with severity and recommendations.
    """
    gaps: list[dict[str, Any]] = []

    # Check for unsupported process elements
    evidence_ids = {str(e.get("id", "")) for e in evidence_items}
    for element in process_elements:
        element_evidence = element.get("evidence_ids", []) or []
        supported_count = sum(1 for eid in element_evidence if eid in evidence_ids)

        if supported_count == 0:
            gaps.append(
                {
                    "gap_type": "missing_evidence",
                    "severity": "high",
                    "element_name": element.get("name", "Unknown"),
                    "element_id": str(element.get("id", "")),
                    "description": f"No evidence supports element '{element.get('name', 'Unknown')}'",
                    "recommendation": f"Collect evidence for '{element.get('name', 'Unknown')}'",
                }
            )
        elif supported_count == 1:
            gaps.append(
                {
                    "gap_type": "single_source",
                    "severity": "medium",
                    "element_name": element.get("name", "Unknown"),
                    "element_id": str(element.get("id", "")),
                    "description": (
                        f"Only one evidence source for '{element.get('name', 'Unknown')}' - triangulation not possible"
                    ),
                    "recommendation": f"Add corroborating evidence for '{element.get('name', 'Unknown')}'",
                }
            )

    # Check for low quality evidence
    for item in evidence_items:
        quality = item.get("quality_score", 0)
        if quality < coverage_threshold:
            gaps.append(
                {
                    "gap_type": "weak_evidence",
                    "severity": "medium",
                    "element_name": item.get("name", "Unknown"),
                    "element_id": str(item.get("id", "")),
                    "description": f"Low quality evidence: '{item.get('name', '')}' (score: {quality:.2f})",
                    "recommendation": f"Improve or replace evidence '{item.get('name', '')}'",
                }
            )

    # Check for category coverage gaps
    categories_present = {e.get("category") for e in evidence_items}
    expected_categories = {
        "documents",
        "structured_data",
        "bpm_process_models",
        "controls_evidence",
        "domain_communications",
    }
    missing_categories = expected_categories - categories_present
    for cat in missing_categories:
        gaps.append(
            {
                "gap_type": "missing_category",
                "severity": "low",
                "element_name": cat,
                "element_id": None,
                "description": f"No evidence in category: {cat}",
                "recommendation": f"Collect {cat.replace('_', ' ')} evidence",
            }
        )

    # Check for stale evidence
    now = datetime.now(UTC)
    for item in evidence_items:
        source_date = item.get("source_date")
        if source_date:
            if isinstance(source_date, str):
                try:
                    source_date = datetime.fromisoformat(source_date)
                except ValueError:
                    continue
            if hasattr(source_date, "year") and (now.year - source_date.year) > 1:
                gaps.append(
                    {
                        "gap_type": "stale_evidence",
                        "severity": "medium",
                        "element_name": item.get("name", "Unknown"),
                        "element_id": str(item.get("id", "")),
                        "description": f"Evidence '{item.get('name', '')}' is over a year old",
                        "recommendation": f"Request updated version of '{item.get('name', '')}'",
                    }
                )

    return gaps
