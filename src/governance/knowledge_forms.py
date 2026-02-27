"""Nine Universal Process Knowledge Forms coverage service.

Computes coverage of the 9 knowledge forms per activity by querying
Neo4j for the presence of specific edge types. Each form maps to
one or more Neo4j relationship types:

  Form 1 (Activities)     → HAS_ACTIVITY
  Form 2 (Sequences)      → PRECEDES / FOLLOWED_BY
  Form 3 (Dependencies)   → DEPENDS_ON
  Form 4 (Inputs/Outputs) → CONSUMES / PRODUCES
  Form 5 (Rules)          → GOVERNED_BY
  Form 6 (Personas)       → PERFORMED_BY
  Form 7 (Controls)       → ENFORCED_BY
  Form 8 (Evidence)       → SUPPORTED_BY
  Form 9 (Uncertainty)    → HAS_UNCERTAINTY / CONTRADICTS
"""

from __future__ import annotations

import enum
import logging
from typing import Any

logger = logging.getLogger(__name__)


class KnowledgeForm(enum.StrEnum):
    """The 9 universal process knowledge forms."""

    ACTIVITIES = "activities"
    SEQUENCES = "sequences"
    DEPENDENCIES = "dependencies"
    INPUTS_OUTPUTS = "inputs_outputs"
    RULES = "rules"
    PERSONAS = "personas"
    CONTROLS = "controls"
    EVIDENCE = "evidence"
    UNCERTAINTY = "uncertainty"


# Mapping from form to Neo4j edge types that satisfy it.
FORM_EDGE_MAPPINGS: dict[KnowledgeForm, list[str]] = {
    KnowledgeForm.ACTIVITIES: ["HAS_ACTIVITY"],
    KnowledgeForm.SEQUENCES: ["PRECEDES", "FOLLOWED_BY"],
    KnowledgeForm.DEPENDENCIES: ["DEPENDS_ON"],
    KnowledgeForm.INPUTS_OUTPUTS: ["CONSUMES", "PRODUCES"],
    KnowledgeForm.RULES: ["GOVERNED_BY"],
    KnowledgeForm.PERSONAS: ["PERFORMED_BY"],
    KnowledgeForm.CONTROLS: ["ENFORCED_BY"],
    KnowledgeForm.EVIDENCE: ["SUPPORTED_BY"],
    KnowledgeForm.UNCERTAINTY: ["HAS_UNCERTAINTY", "CONTRADICTS"],
}

FORM_NUMBERS: dict[KnowledgeForm, int] = {
    KnowledgeForm.ACTIVITIES: 1,
    KnowledgeForm.SEQUENCES: 2,
    KnowledgeForm.DEPENDENCIES: 3,
    KnowledgeForm.INPUTS_OUTPUTS: 4,
    KnowledgeForm.RULES: 5,
    KnowledgeForm.PERSONAS: 6,
    KnowledgeForm.CONTROLS: 7,
    KnowledgeForm.EVIDENCE: 8,
    KnowledgeForm.UNCERTAINTY: 9,
}


class KnowledgeFormsCoverageService:
    """Computes per-activity and engagement-wide coverage of the 9 forms."""

    def __init__(self, graph_service: Any) -> None:
        self._graph = graph_service

    async def get_activity_ids(self, engagement_id: str) -> list[str]:
        """Return all activity IDs in an engagement."""
        query = (
            "MATCH (a:Activity {engagement_id: $engagement_id}) "
            "RETURN a.id AS activity_id"
        )
        records = await self._graph.run_query(query, {"engagement_id": engagement_id})
        return [r["activity_id"] for r in records]

    async def compute_form_coverage(
        self,
        engagement_id: str,
        activity_ids: list[str],
        form: KnowledgeForm,
    ) -> set[str]:
        """Return activity IDs that have edges satisfying the given form.

        Uses a single Cypher query that checks for any of the edge types
        mapped to the form.
        """
        edge_types = FORM_EDGE_MAPPINGS[form]

        if form == KnowledgeForm.ACTIVITIES:
            # Form 1: activity exists → automatically covered
            return set(activity_ids)

        # Build MATCH pattern for edge types
        # Use OPTIONAL MATCH with relationship type filter
        edge_type_list = "[" + ", ".join(f"'{e}'" for e in edge_types) + "]"
        query = (
            "MATCH (a:Activity) "
            "WHERE a.id IN $activity_ids AND a.engagement_id = $engagement_id "
            f"MATCH (a)-[r]->() WHERE type(r) IN {edge_type_list} "
            "RETURN DISTINCT a.id AS activity_id"
        )
        records = await self._graph.run_query(
            query, {"engagement_id": engagement_id, "activity_ids": activity_ids}
        )
        covered = {r["activity_id"] for r in records}

        # Also check inbound edges (e.g., PRECEDES may come from another node)
        query_inbound = (
            "MATCH (a:Activity) "
            "WHERE a.id IN $activity_ids AND a.engagement_id = $engagement_id "
            f"MATCH ()-[r]->(a) WHERE type(r) IN {edge_type_list} "
            "RETURN DISTINCT a.id AS activity_id"
        )
        records_in = await self._graph.run_query(
            query_inbound, {"engagement_id": engagement_id, "activity_ids": activity_ids}
        )
        covered.update(r["activity_id"] for r in records_in)

        return covered

    async def compute_engagement_coverage(
        self, engagement_id: str
    ) -> dict[str, Any]:
        """Compute full coverage across all 9 forms for an engagement.

        Returns per-form and per-activity coverage data, plus an overall
        engagement-level completeness score.
        """
        activity_ids = await self.get_activity_ids(engagement_id)
        total = len(activity_ids)

        if total == 0:
            return {
                "engagement_id": engagement_id,
                "total_activities": 0,
                "forms": [],
                "per_activity": [],
                "overall_completeness": 0.0,
            }

        # Compute coverage per form
        form_results = {}
        for form in KnowledgeForm:
            covered = await self.compute_form_coverage(engagement_id, activity_ids, form)
            form_results[form] = covered

        # Build per-form response
        forms_data = []
        for form in KnowledgeForm:
            covered = form_results[form]
            covered_count = len(covered)
            pct = round(covered_count / total * 100, 2) if total > 0 else 0.0
            forms_data.append({
                "form_number": FORM_NUMBERS[form],
                "form_name": form.value,
                "covered_count": covered_count,
                "total_count": total,
                "coverage_percentage": pct,
            })

        # Build per-activity response
        per_activity = []
        for aid in activity_ids:
            forms_present = []
            gaps = []
            for form in KnowledgeForm:
                if aid in form_results[form]:
                    forms_present.append(FORM_NUMBERS[form])
                else:
                    gaps.append({
                        "form_number": FORM_NUMBERS[form],
                        "form_name": form.value,
                    })
            score = round(len(forms_present) / 9 * 100, 2)
            per_activity.append({
                "activity_id": aid,
                "forms_present": forms_present,
                "gaps": gaps,
                "completeness_score": score,
            })

        # Overall engagement completeness
        total_cells = total * 9
        covered_cells = sum(len(form_results[f]) for f in KnowledgeForm)
        overall = round(covered_cells / total_cells * 100, 2) if total_cells > 0 else 0.0

        return {
            "engagement_id": engagement_id,
            "total_activities": total,
            "forms": forms_data,
            "per_activity": per_activity,
            "overall_completeness": overall,
        }

    async def compute_knowledge_gaps(
        self, engagement_id: str
    ) -> list[dict[str, Any]]:
        """Return a flat list of all missing form coverage entries.

        Each entry includes activity_id, form_number, form_name, and a
        suggested_probe_type mapping for targeted evidence acquisition.
        """
        activity_ids = await self.get_activity_ids(engagement_id)
        if not activity_ids:
            return []

        # Map form to suggested probe type for gap remediation
        probe_type_map: dict[KnowledgeForm, str] = {
            KnowledgeForm.ACTIVITIES: "existence",
            KnowledgeForm.SEQUENCES: "sequence",
            KnowledgeForm.DEPENDENCIES: "dependency",
            KnowledgeForm.INPUTS_OUTPUTS: "input_output",
            KnowledgeForm.RULES: "governance",
            KnowledgeForm.PERSONAS: "performer",
            KnowledgeForm.CONTROLS: "governance",
            KnowledgeForm.EVIDENCE: "existence",
            KnowledgeForm.UNCERTAINTY: "uncertainty",
        }

        gaps = []
        for form in KnowledgeForm:
            covered = await self.compute_form_coverage(engagement_id, activity_ids, form)
            uncovered = set(activity_ids) - covered
            for aid in uncovered:
                gaps.append({
                    "activity_id": aid,
                    "form_number": FORM_NUMBERS[form],
                    "form_name": form.value,
                    "gap_type": "missing_evidence",
                    "suggested_probe_type": probe_type_map[form],
                })

        return gaps
