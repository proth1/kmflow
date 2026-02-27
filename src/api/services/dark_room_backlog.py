"""Dark Room Backlog service for prioritized Dark segment management.

Provides a prioritized list of all Dark process segments ordered by
estimated confidence uplift. Each backlog item shows which of the 9
knowledge forms are missing and recommends probe types to acquire them.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from src.governance.knowledge_forms import (
    FORM_EDGE_MAPPINGS,
    FORM_NUMBERS,
    FORM_PROBE_TYPE_MAP,
    KnowledgeForm,
)

if TYPE_CHECKING:
    from src.semantic.graph import KnowledgeGraphService

logger = logging.getLogger(__name__)

# Default Dark threshold: confidence < 0.4
DEFAULT_DARK_THRESHOLD = 0.4

# Recommended probes per form — maps form_number to human-readable probe descriptions.
# Derived from FORM_PROBE_TYPE_MAP with richer descriptions for the Dark Room UI.
FORM_RECOMMENDED_PROBES: dict[int, list[str]] = {
    1: ["existence check via stakeholder interview"],
    2: ["process observation", "sequence walkthrough"],
    3: ["dependency mapping workshop"],
    4: ["input/output document review"],
    5: ["policy document review", "rule extraction interview"],
    6: ["performer identification interview"],
    7: ["control assessment", "governance review"],
    8: ["evidence collection from source systems"],
    9: ["uncertainty assessment interview", "contradiction resolution"],
}


class DarkRoomBacklogService:
    """Manages the Dark Room backlog: prioritized Dark segments with gap details."""

    def __init__(
        self,
        graph_service: KnowledgeGraphService,
        dark_threshold: float = DEFAULT_DARK_THRESHOLD,
    ) -> None:
        self._graph = graph_service
        self._dark_threshold = dark_threshold

    async def get_dark_segments(
        self,
        engagement_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Get prioritized Dark segments for an engagement.

        Returns segments ranked by estimated_confidence_uplift descending.
        Each segment includes missing knowledge forms and recommended probes.
        """
        # Query graph for all Dark activities (confidence < threshold)
        elements = await self._get_dark_elements(engagement_id)

        if not elements:
            return {
                "engagement_id": engagement_id,
                "dark_threshold": self._dark_threshold,
                "total_count": 0,
                "items": [],
            }

        # Compute missing forms for each element
        activity_ids = [e["element_id"] for e in elements]
        form_coverage = await self._compute_form_coverage(engagement_id, activity_ids)

        # Build backlog items with uplift estimates
        items: list[dict[str, Any]] = []
        for elem in elements:
            aid = elem["element_id"]
            current_conf = elem["confidence"]
            brightness_gap = 1.0 - current_conf

            # Determine which forms are missing
            covered_forms = form_coverage.get(aid, set())
            missing_forms: list[dict[str, Any]] = []
            for form in KnowledgeForm:
                if form not in covered_forms:
                    form_num = FORM_NUMBERS[form]
                    missing_forms.append({
                        "form_number": form_num,
                        "form_name": form.value,
                        "recommended_probes": FORM_RECOMMENDED_PROBES.get(form_num, []),
                        "probe_type": FORM_PROBE_TYPE_MAP[form],
                    })

            # Estimated uplift: proportional to missing forms ratio × brightness gap
            missing_ratio = len(missing_forms) / 9
            estimated_uplift = round(missing_ratio * brightness_gap * 0.6, 4)

            items.append({
                "element_id": aid,
                "element_name": elem["element_name"],
                "current_confidence": current_conf,
                "brightness": elem.get("brightness", "dark"),
                "estimated_confidence_uplift": estimated_uplift,
                "missing_knowledge_forms": missing_forms,
                "missing_form_count": len(missing_forms),
                "covered_form_count": len(covered_forms),
            })

        # Sort by estimated uplift descending
        items.sort(key=lambda x: x["estimated_confidence_uplift"], reverse=True)

        total = len(items)
        paginated = items[offset : offset + limit]

        return {
            "engagement_id": engagement_id,
            "dark_threshold": self._dark_threshold,
            "total_count": total,
            "items": paginated,
        }

    async def _get_dark_elements(
        self, engagement_id: str
    ) -> list[dict[str, Any]]:
        """Get all Dark activities from the knowledge graph."""
        query = (
            "MATCH (a:Activity) "
            "WHERE a.engagement_id = $engagement_id "
            "AND a.confidence < $threshold "
            "RETURN a.id AS element_id, a.name AS element_name, "
            "a.confidence AS confidence, a.brightness AS brightness"
        )
        records = await self._graph.run_query(
            query,
            {
                "engagement_id": engagement_id,
                "threshold": self._dark_threshold,
            },
        )
        return [
            {
                "element_id": r["element_id"],
                "element_name": r["element_name"],
                "confidence": r.get("confidence", 0.2),
                "brightness": r.get("brightness", "dark"),
            }
            for r in records
        ]

    async def _compute_form_coverage(
        self, engagement_id: str, activity_ids: list[str]
    ) -> dict[str, set[KnowledgeForm]]:
        """Compute which knowledge forms are covered per activity.

        Returns a dict mapping activity_id -> set of covered KnowledgeForm values.
        """
        coverage: dict[str, set[KnowledgeForm]] = {aid: set() for aid in activity_ids}

        for form in KnowledgeForm:
            if form == KnowledgeForm.ACTIVITIES:
                # Form 1: activity exists → automatically covered
                for aid in activity_ids:
                    coverage[aid].add(form)
                continue

            edge_types = FORM_EDGE_MAPPINGS[form]
            params = {
                "engagement_id": engagement_id,
                "activity_ids": activity_ids,
                "edge_types": edge_types,
            }

            # Check outbound edges
            query_out = (
                "MATCH (a:Activity) "
                "WHERE a.id IN $activity_ids AND a.engagement_id = $engagement_id "
                "MATCH (a)-[r]->() WHERE type(r) IN $edge_types "
                "RETURN DISTINCT a.id AS activity_id"
            )
            records_out = await self._graph.run_query(query_out, params)
            for r in records_out:
                coverage[r["activity_id"]].add(form)

            # Check inbound edges
            query_in = (
                "MATCH (a:Activity) "
                "WHERE a.id IN $activity_ids AND a.engagement_id = $engagement_id "
                "MATCH ()-[r]->(a) WHERE type(r) IN $edge_types "
                "RETURN DISTINCT a.id AS activity_id"
            )
            records_in = await self._graph.run_query(query_in, params)
            for r in records_in:
                coverage[r["activity_id"]].add(form)

        return coverage
