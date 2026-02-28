"""Process variant detection from task mining behavior.

Compares observed UserAction sequences (linked via SUPPORTS) against
documented Activity sequences on Process nodes to detect deviations:
  - extra_step: observed step not in documented process
  - missing_step: documented step not observed
  - different_order: steps observed in non-standard sequence

Story #229 — Part of Epic #225 (Knowledge Graph Integration).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.semantic.graph import GraphNode, KnowledgeGraphService

logger = logging.getLogger(__name__)

# Max nodes to fetch per label (guards against silent truncation).
_MAX_NODES = 10000

_SEVERITY_MAP = {
    "missing_step": "warning",
    "extra_step": "info",
    "different_order": "info",
}


@dataclass
class ProcessVariant:
    """A detected process variant."""

    process_id: str
    process_name: str
    session_id: str
    deviation_type: str  # extra_step | missing_step | different_order
    severity: str  # warning | info
    confidence: float
    description: str


@dataclass
class VariantDetectionResult:
    """Result summary from variant detection."""

    variants: list[ProcessVariant] = field(default_factory=list)
    deviates_from_created: int = 0
    sessions_analyzed: int = 0
    errors: list[str] = field(default_factory=list)


async def detect_variants(
    graph_service: KnowledgeGraphService,
    engagement_id: str,
) -> VariantDetectionResult:
    """Detect process variants from observed UserAction sequences.

    Requires SUPPORTS relationships (from semantic bridge) to map
    UserActions to documented Activities, and FOLLOWED_BY relationships
    on Activities to define the expected sequence.

    Args:
        graph_service: Neo4j knowledge graph service.
        engagement_id: Engagement to analyze.

    Returns:
        VariantDetectionResult with variant details.
    """
    result = VariantDetectionResult()

    # Load processes with their expected activity sequences
    processes = await graph_service.find_nodes("Process", {"engagement_id": engagement_id}, limit=_MAX_NODES)
    if not processes:
        logger.info("No processes found for engagement %s", engagement_id)
        return result

    # Load UserAction nodes with their PRECEDED_BY chains and SUPPORTS links
    user_actions = await graph_service.find_nodes("UserAction", {"engagement_id": engagement_id}, limit=_MAX_NODES)
    if not user_actions:
        logger.info("No UserActions found for engagement %s", engagement_id)
        return result

    # Build activity-to-process mapping and expected sequences
    process_sequences = await _build_process_sequences(graph_service, processes)

    # Build observed session sequences via PRECEDED_BY + SUPPORTS
    session_sequences = await _build_session_sequences(graph_service, user_actions)

    result.sessions_analyzed = len(session_sequences)

    # Compare each session against matching processes
    for session_id, observed_activity_ids in session_sequences.items():
        for process in processes:
            expected = process_sequences.get(process.id, [])
            if not expected:
                continue

            variants = _compare_sequences(
                expected_ids=expected,
                observed_ids=observed_activity_ids,
                process_id=process.id,
                process_name=process.properties.get("name", ""),
                session_id=session_id,
            )

            for variant in variants:
                result.variants.append(variant)
                try:
                    await graph_service.create_relationship(
                        from_id=session_id,
                        to_id=process.id,
                        relationship_type="DEVIATES_FROM",
                        properties={
                            "deviation_type": variant.deviation_type,
                            "confidence": variant.confidence,
                            "description": variant.description,
                            "severity": variant.severity,
                            "source": "task_mining_variant_detection",
                        },
                    )
                    result.deviates_from_created += 1
                except (ConnectionError, RuntimeError) as e:
                    result.errors.append(f"DEVIATES_FROM failed: {e}")

    logger.info(
        "Variant detection complete for engagement %s: %d sessions, %d variants, %d relationships created",
        engagement_id,
        result.sessions_analyzed,
        len(result.variants),
        result.deviates_from_created,
    )
    return result


async def _build_process_sequences(
    graph_service: KnowledgeGraphService,
    processes: list[GraphNode],
) -> dict[str, list[str]]:
    """Build expected activity sequences for each process.

    Follows FOLLOWED_BY chains from activities linked to each process.

    Returns:
        Map of process_id -> ordered list of activity node IDs.
    """
    sequences: dict[str, list[str]] = {}

    for process in processes:
        # Get activities linked to this process via outgoing relationships
        rels = await graph_service.get_relationships(process.id, direction="outgoing")
        # Find activities connected by FOLLOWED_BY to build the sequence
        activity_ids = [r.to_id for r in rels if r.relationship_type in ("REQUIRES", "OWNED_BY", "USES", "FOLLOWED_BY")]

        # Get FOLLOWED_BY chains among these activities
        if not activity_ids:
            continue

        # Build ordering from FOLLOWED_BY relationships
        ordered = await _topological_sort_activities(graph_service, activity_ids)
        if ordered:
            sequences[process.id] = ordered

    return sequences


async def _topological_sort_activities(
    graph_service: KnowledgeGraphService,
    activity_ids: list[str],
) -> list[str]:
    """Sort activities by FOLLOWED_BY chain order.

    Returns:
        Ordered list of activity IDs from first to last.
    """
    id_set = set(activity_ids)
    successors: dict[str, str] = {}  # from_id -> to_id
    has_predecessor: set[str] = set()

    for aid in activity_ids:
        rels = await graph_service.get_relationships(aid, direction="outgoing", relationship_type="FOLLOWED_BY")
        for r in rels:
            if r.to_id in id_set:
                successors[aid] = r.to_id
                has_predecessor.add(r.to_id)

    # Find start node (no predecessor)
    starts = [aid for aid in activity_ids if aid not in has_predecessor]
    if not starts:
        return activity_ids  # No FOLLOWED_BY chain, return as-is

    # Walk the chain from start
    ordered: list[str] = []
    current = starts[0]
    visited: set[str] = set()
    while current and current not in visited:
        ordered.append(current)
        visited.add(current)
        current = successors.get(current)

    return ordered


async def _build_session_sequences(
    graph_service: KnowledgeGraphService,
    user_actions: list[GraphNode],
) -> dict[str, list[str]]:
    """Build observed activity sequences per session.

    Groups UserActions by session, resolves their SUPPORTS links to
    get the mapped Activity ID, and orders by PRECEDED_BY chain.

    Returns:
        Map of first_ua_node_id (as session proxy) -> list of activity IDs.
    """
    # Resolve each UserAction's mapped Activity via SUPPORTS
    ua_to_activity: dict[str, str] = {}
    for ua in user_actions:
        rels = await graph_service.get_relationships(ua.id, direction="outgoing", relationship_type="SUPPORTS")
        if rels:
            # Take the highest-confidence link
            best = max(rels, key=lambda r: r.properties.get("similarity_score", 0))
            ua_to_activity[ua.id] = best.to_id

    # Group user actions into sessions via PRECEDED_BY chains
    # Walk backward to find chain starts, then walk forward
    has_successor: set[str] = set()
    preceded_by: dict[str, str] = {}  # ua_id -> predecessor_ua_id

    for ua in user_actions:
        rels = await graph_service.get_relationships(ua.id, direction="outgoing", relationship_type="PRECEDED_BY")
        for r in rels:
            preceded_by[ua.id] = r.to_id
            has_successor.add(r.to_id)

    # Build inverse map for forward traversal
    successor_of: dict[str, str] = {v: k for k, v in preceded_by.items()}

    # Find chain starts (no predecessor = first in temporal sequence)
    ua_ids = {ua.id for ua in user_actions}
    chain_starts = [uid for uid in ua_ids if uid not in preceded_by]

    sessions: dict[str, list[str]] = {}
    for start_id in chain_starts:
        chain: list[str] = []
        current: str | None = start_id
        visited: set[str] = set()
        while current and current not in visited:
            activity_id = ua_to_activity.get(current)
            if activity_id:
                chain.append(activity_id)
            visited.add(current)
            current = successor_of.get(current)

        if chain:
            sessions[start_id] = chain

    return sessions


def _compare_sequences(
    expected_ids: list[str],
    observed_ids: list[str],
    process_id: str,
    process_name: str,
    session_id: str,
) -> list[ProcessVariant]:
    """Compare expected vs observed activity sequences.

    Returns list of detected variants.
    """
    variants: list[ProcessVariant] = []

    expected_set = set(expected_ids)
    observed_set = set(observed_ids)

    # Extra steps: observed but not in expected
    extra = observed_set - expected_set
    if extra:
        variants.append(
            ProcessVariant(
                process_id=process_id,
                process_name=process_name,
                session_id=session_id,
                deviation_type="extra_step",
                severity=_SEVERITY_MAP["extra_step"],
                confidence=0.8,
                description=(f"Observed {len(extra)} step(s) not in documented process '{process_name}'"),
            )
        )

    # Missing steps: expected but not observed
    missing = expected_set - observed_set
    if missing:
        variants.append(
            ProcessVariant(
                process_id=process_id,
                process_name=process_name,
                session_id=session_id,
                deviation_type="missing_step",
                severity=_SEVERITY_MAP["missing_step"],
                confidence=0.7,
                description=(f"{len(missing)} expected step(s) in '{process_name}' were not observed"),
            )
        )

    # Order deviation: check if common elements are in same relative order
    common = [aid for aid in observed_ids if aid in expected_set]
    expected_common = [aid for aid in expected_ids if aid in observed_set]

    if common and expected_common and common != expected_common:
        variants.append(
            ProcessVariant(
                process_id=process_id,
                process_name=process_name,
                session_id=session_id,
                deviation_type="different_order",
                severity=_SEVERITY_MAP["different_order"],
                confidence=0.75,
                description=(f"Steps in '{process_name}' were performed in a different order than documented"),
            )
        )

    return variants
