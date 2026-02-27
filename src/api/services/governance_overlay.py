"""Governance overlay computation service.

Computes per-activity governance status by traversing Neo4j governance
chain edges: Activity → GOVERNED_BY → Policy, Activity → REQUIRES_CONTROL → Control,
Control → references → Regulation. Activities are classified as:

  GOVERNED: policy + control + regulation all present
  PARTIALLY_GOVERNED: at least one governance entity linked
  UNGOVERNED: no governance entities linked
"""

from __future__ import annotations

import enum
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.semantic.graph import KnowledgeGraphService

logger = logging.getLogger(__name__)


class GovernanceStatus(enum.StrEnum):
    """Governance coverage classification for a process element."""

    GOVERNED = "governed"
    PARTIALLY_GOVERNED = "partially_governed"
    UNGOVERNED = "ungoverned"


class GovernanceOverlayService:
    """Computes governance overlay data for process model activities."""

    def __init__(self, graph_service: KnowledgeGraphService) -> None:
        self._graph = graph_service

    async def compute_overlay(
        self, process_model_id: str, engagement_id: str
    ) -> dict[str, Any]:
        """Compute governance overlay for all activities in a process model.

        Queries Neo4j for governance chains and classifies each activity.

        Returns:
            Dict with activities, governance_gaps, and coverage percentage.
        """
        # Get all activities for this process model
        activities = await self._get_activities(process_model_id, engagement_id)
        if not activities:
            return {
                "process_model_id": process_model_id,
                "engagement_id": engagement_id,
                "activities": [],
                "governance_gaps": [],
                "overall_coverage_percentage": 0.0,
                "total_activities": 0,
                "governed_count": 0,
                "partially_governed_count": 0,
                "ungoverned_count": 0,
            }

        activity_ids = [a["activity_id"] for a in activities]

        # Fetch governance chains for all activities
        chains = await self._get_governance_chains(activity_ids, engagement_id)

        # Classify each activity
        overlay_entries = []
        governance_gaps = []
        governed_count = 0
        partially_governed_count = 0
        ungoverned_count = 0

        for activity in activities:
            aid = activity["activity_id"]
            chain = chains.get(aid, {})

            has_policy = chain.get("policy") is not None
            has_control = chain.get("control") is not None
            has_regulation = chain.get("regulation") is not None

            if has_policy and has_control and has_regulation:
                gov_status = GovernanceStatus.GOVERNED
                governed_count += 1
            elif has_policy or has_control or has_regulation:
                gov_status = GovernanceStatus.PARTIALLY_GOVERNED
                partially_governed_count += 1
            else:
                gov_status = GovernanceStatus.UNGOVERNED
                ungoverned_count += 1

            entry: dict[str, Any] = {
                "activity_id": aid,
                "activity_name": activity["activity_name"],
                "governance_status": gov_status.value,
            }

            if has_policy:
                entry["policy"] = chain["policy"]
            if has_control:
                entry["control"] = chain["control"]
            if has_regulation:
                entry["regulation"] = chain["regulation"]

            overlay_entries.append(entry)

            if gov_status == GovernanceStatus.UNGOVERNED:
                governance_gaps.append({
                    "activity_id": aid,
                    "activity_name": activity["activity_name"],
                    "gap_type": "UNGOVERNED",
                })

        total = len(activities)
        coverage_pct = round(
            (governed_count + partially_governed_count) / total * 100, 2
        ) if total > 0 else 0.0

        return {
            "process_model_id": process_model_id,
            "engagement_id": engagement_id,
            "activities": overlay_entries,
            "governance_gaps": governance_gaps,
            "overall_coverage_percentage": coverage_pct,
            "total_activities": total,
            "governed_count": governed_count,
            "partially_governed_count": partially_governed_count,
            "ungoverned_count": ungoverned_count,
        }

    async def _get_activities(
        self, process_model_id: str, engagement_id: str
    ) -> list[dict[str, Any]]:
        """Get all Activity nodes for a process model."""
        query = (
            "MATCH (a:Activity) "
            "WHERE a.process_model_id = $process_model_id "
            "AND a.engagement_id = $engagement_id "
            "RETURN a.id AS activity_id, a.name AS activity_name "
            "ORDER BY a.name"
        )
        return await self._graph.run_query(
            query, {"process_model_id": process_model_id, "engagement_id": engagement_id}
        )

    async def _get_governance_chains(
        self, activity_ids: list[str], engagement_id: str
    ) -> dict[str, dict[str, Any]]:
        """Fetch governance chain (policy, control, regulation) for each activity.

        Uses a single Cypher query with OPTIONAL MATCH to efficiently
        retrieve all governance entities in one round-trip.
        """
        query = (
            "MATCH (a:Activity) "
            "WHERE a.id IN $activity_ids AND a.engagement_id = $engagement_id "
            "OPTIONAL MATCH (a)-[:GOVERNED_BY]->(p:Policy) "
            "OPTIONAL MATCH (a)-[:REQUIRES_CONTROL]->(c:Control) "
            "OPTIONAL MATCH (c)-[:IMPLEMENTS]->(r:Regulation) "
            "RETURN a.id AS activity_id, "
            "p.id AS policy_id, p.name AS policy_name, "
            "c.id AS control_id, c.name AS control_name, "
            "r.id AS regulation_id, r.name AS regulation_name"
        )
        records = await self._graph.run_query(
            query, {"activity_ids": activity_ids, "engagement_id": engagement_id}
        )

        chains: dict[str, dict[str, Any]] = {}
        for r in records:
            aid = r["activity_id"]
            chain: dict[str, Any] = {}

            if r.get("policy_id"):
                chain["policy"] = {"id": r["policy_id"], "name": r["policy_name"]}
            if r.get("control_id"):
                chain["control"] = {"id": r["control_id"], "name": r["control_name"]}
            if r.get("regulation_id"):
                chain["regulation"] = {"id": r["regulation_id"], "name": r["regulation_name"]}

            chains[aid] = chain

        return chains
