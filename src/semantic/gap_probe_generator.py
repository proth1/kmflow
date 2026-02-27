"""Gap-targeted probe generation from knowledge form gaps.

Generates survey probes for Dim and Dark process segments where
evidence is insufficient or absent. Prioritizes probes by estimated
confidence uplift to focus SME time on highest-value targets.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from src.core.models.pov import BrightnessClassification
from src.core.models.survey import ProbeType
from src.governance.knowledge_forms import (
    FORM_NUMBERS,
    KnowledgeForm,
    KnowledgeFormsCoverageService,
)

if TYPE_CHECKING:
    from src.semantic.graph import KnowledgeGraphService

logger = logging.getLogger(__name__)

# Mapping from knowledge form to the probe type that fills the gap.
FORM_TO_PROBE_TYPE: dict[KnowledgeForm, ProbeType] = {
    KnowledgeForm.ACTIVITIES: ProbeType.EXISTENCE,
    KnowledgeForm.SEQUENCES: ProbeType.SEQUENCE,
    KnowledgeForm.DEPENDENCIES: ProbeType.DEPENDENCY,
    KnowledgeForm.INPUTS_OUTPUTS: ProbeType.INPUT_OUTPUT,
    KnowledgeForm.RULES: ProbeType.GOVERNANCE,
    KnowledgeForm.PERSONAS: ProbeType.PERFORMER,
    KnowledgeForm.CONTROLS: ProbeType.GOVERNANCE,
    KnowledgeForm.EVIDENCE: ProbeType.EXISTENCE,
    KnowledgeForm.UNCERTAINTY: ProbeType.UNCERTAINTY,
}

# Weight per form for confidence uplift calculation.
# Higher weight = bigger impact when missing.
FORM_WEIGHTS: dict[KnowledgeForm, float] = {
    KnowledgeForm.ACTIVITIES: 0.5,
    KnowledgeForm.SEQUENCES: 1.0,
    KnowledgeForm.DEPENDENCIES: 0.8,
    KnowledgeForm.INPUTS_OUTPUTS: 0.9,
    KnowledgeForm.RULES: 1.2,
    KnowledgeForm.PERSONAS: 0.7,
    KnowledgeForm.CONTROLS: 1.1,
    KnowledgeForm.EVIDENCE: 1.0,
    KnowledgeForm.UNCERTAINTY: 0.6,
}

# Prompt templates per probe type for generating probe text.
PROBE_TEMPLATES: dict[ProbeType, str] = {
    ProbeType.EXISTENCE: "Can you confirm whether '{activity}' is actually performed in your process?",
    ProbeType.SEQUENCE: "What steps come before and after '{activity}' in your process?",
    ProbeType.DEPENDENCY: "What does '{activity}' depend on to start? What other activities depend on it?",
    ProbeType.INPUT_OUTPUT: "What inputs does '{activity}' consume, and what outputs does it produce?",
    ProbeType.GOVERNANCE: "What rules, policies, or controls govern how '{activity}' is performed?",
    ProbeType.PERFORMER: "Who is responsible for performing '{activity}'? What role or team?",
    ProbeType.UNCERTAINTY: "Are there any disagreements or uncertainties about how '{activity}' works?",
}


class GapProbeGenerator:
    """Generates targeted probes for knowledge form gaps."""

    def __init__(self, graph_service: KnowledgeGraphService) -> None:
        self._graph = graph_service
        self._coverage_service = KnowledgeFormsCoverageService(graph_service)

    async def _get_activity_brightness(
        self, engagement_id: str, activity_ids: list[str]
    ) -> dict[str, str]:
        """Fetch brightness classification for activities from Neo4j."""
        query = (
            "MATCH (a:Activity) "
            "WHERE a.id IN $activity_ids AND a.engagement_id = $engagement_id "
            "RETURN a.id AS activity_id, a.brightness AS brightness"
        )
        records = await self._graph.run_query(
            query, {"engagement_id": engagement_id, "activity_ids": activity_ids}
        )
        return {
            r["activity_id"]: r.get("brightness", BrightnessClassification.DIM)
            for r in records
        }

    async def _get_activity_centrality(
        self, engagement_id: str, activity_ids: list[str]
    ) -> dict[str, float]:
        """Compute centrality (degree count) per activity as a proxy for importance."""
        query = (
            "MATCH (a:Activity) "
            "WHERE a.id IN $activity_ids AND a.engagement_id = $engagement_id "
            "OPTIONAL MATCH (a)-[r]-() "
            "RETURN a.id AS activity_id, count(r) AS degree"
        )
        records = await self._graph.run_query(
            query, {"engagement_id": engagement_id, "activity_ids": activity_ids}
        )
        max_degree = max((r["degree"] for r in records), default=1) or 1
        return {
            r["activity_id"]: r["degree"] / max_degree
            for r in records
        }

    def _compute_uplift(
        self,
        form: KnowledgeForm,
        brightness: str,
        centrality: float,
    ) -> float:
        """Compute estimated confidence uplift for filling a gap.

        Formula: form_weight × activity_centrality × brightness_multiplier
        where DARK=1.0, DIM=0.5, BRIGHT=0.0
        """
        weight = FORM_WEIGHTS.get(form, 1.0)
        brightness_multiplier = {
            BrightnessClassification.DARK: 1.0,
            BrightnessClassification.DIM: 0.5,
            BrightnessClassification.BRIGHT: 0.0,
        }.get(brightness, 0.5)
        return round(weight * centrality * brightness_multiplier, 4)

    async def generate_probes(
        self, engagement_id: str
    ) -> list[dict[str, Any]]:
        """Generate gap-targeted probes for an engagement.

        Returns probes sorted by estimated confidence uplift (descending).
        Fully covered activities produce no probes.
        """
        activity_ids = await self._coverage_service.get_activity_ids(engagement_id)
        if not activity_ids:
            return []

        # Get brightness and centrality for all activities
        brightness_map = await self._get_activity_brightness(engagement_id, activity_ids)
        centrality_map = await self._get_activity_centrality(engagement_id, activity_ids)

        # Compute coverage per form
        form_coverage: dict[KnowledgeForm, set[str]] = {}
        for form in KnowledgeForm:
            covered = await self._coverage_service.compute_form_coverage(
                engagement_id, activity_ids, form
            )
            form_coverage[form] = covered

        probes: list[dict[str, Any]] = []
        skipped_count = 0

        for aid in activity_ids:
            # Check how many forms are covered for this activity
            covered_forms = [f for f in KnowledgeForm if aid in form_coverage[f]]
            if len(covered_forms) == 9:
                skipped_count += 1
                continue  # Fully covered, no probes needed

            brightness = brightness_map.get(aid, BrightnessClassification.DIM)

            # Skip bright activities (no gaps worth probing)
            if brightness == BrightnessClassification.BRIGHT:
                skipped_count += 1
                continue

            centrality = centrality_map.get(aid, 0.5)

            for form in KnowledgeForm:
                if aid in form_coverage[form]:
                    continue  # This form is covered

                probe_type = FORM_TO_PROBE_TYPE[form]
                uplift = self._compute_uplift(form, brightness, centrality)

                if uplift <= 0:
                    continue

                probe_text = PROBE_TEMPLATES.get(probe_type, "").format(activity=aid)

                probes.append({
                    "id": str(uuid.uuid4()),
                    "activity_id": aid,
                    "form_number": FORM_NUMBERS[form],
                    "form_name": form.value,
                    "probe_type": probe_type.value,
                    "probe_text": probe_text,
                    "brightness": brightness,
                    "estimated_uplift": uplift,
                })

        # Sort by uplift descending
        probes.sort(key=lambda p: p["estimated_uplift"], reverse=True)

        logger.info(
            "Generated %d probes for engagement %s (%d activities skipped as fully covered)",
            len(probes), engagement_id, skipped_count,
        )

        return probes
