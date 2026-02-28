"""Micro-survey generation service for telemetry-triggered probes.

Generates short, targeted surveys (2-3 probes) when process deviations
are detected, routing them to the relevant SME.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import (
    MicroSurvey,
    MicroSurveyStatus,
    ProbeType,
    ProcessDeviation,
    SurveyClaim,
)

logger = logging.getLogger(__name__)

# Default anomaly threshold: >2 standard deviations from baseline
DEFAULT_ANOMALY_THRESHOLD = 2.0

# Probe selection: map deviation categories to most relevant probes
DEVIATION_PROBE_MAP: dict[str, list[ProbeType]] = {
    "frequency": [ProbeType.EXISTENCE, ProbeType.SEQUENCE, ProbeType.UNCERTAINTY],
    "timing": [ProbeType.SEQUENCE, ProbeType.DEPENDENCY, ProbeType.EXCEPTION],
    "performer": [ProbeType.PERFORMER, ProbeType.GOVERNANCE, ProbeType.EXCEPTION],
    "volume": [ProbeType.INPUT_OUTPUT, ProbeType.EXISTENCE, ProbeType.DEPENDENCY],
    "default": [ProbeType.EXISTENCE, ProbeType.UNCERTAINTY, ProbeType.EXCEPTION],
}


class MicroSurveyService:
    """Generates and manages telemetry-triggered micro-surveys."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def select_probes(
        self,
        deviation_category: str,
        anomaly_description: str,
        max_probes: int = 3,
    ) -> list[dict[str, str]]:
        """Select 2-3 relevant probes based on deviation type.

        Args:
            deviation_category: Category of the detected deviation.
            anomaly_description: Description for probe context.
            max_probes: Maximum probes (2-3, enforced).

        Returns:
            List of probe dicts with type and question.
        """
        max_probes = max(2, min(3, max_probes))
        probe_types = DEVIATION_PROBE_MAP.get(
            deviation_category.lower(),
            DEVIATION_PROBE_MAP["default"],
        )[:max_probes]

        probes: list[dict[str, str]] = []
        for pt in probe_types:
            question = _generate_probe_question(pt, anomaly_description)
            probes.append({
                "probe_type": pt.value,
                "question": question,
            })

        return probes

    async def generate_micro_survey(
        self,
        engagement_id: uuid.UUID,
        deviation: ProcessDeviation,
        target_sme_role: str = "process_owner",
        anomaly_threshold: float = DEFAULT_ANOMALY_THRESHOLD,
    ) -> MicroSurvey | None:
        """Generate a micro-survey from a telemetry deviation.

        Args:
            engagement_id: The engagement context.
            deviation: The triggering process deviation.
            target_sme_role: The SME role to route the survey to.
            anomaly_threshold: Threshold for triggering (default: 2.0 std devs).

        Returns:
            Created MicroSurvey or None if deviation doesn't exceed threshold.
        """
        # Check threshold — deviation must have severity_score or magnitude
        magnitude = getattr(deviation, "severity_score", None) or getattr(deviation, "magnitude", 0.0)
        if magnitude <= anomaly_threshold:
            return None

        category = getattr(deviation, "category", "default")
        if hasattr(category, "value"):
            category = category.value

        description = getattr(deviation, "description", "") or f"Anomalous pattern detected at {deviation.element_name}"

        probes = self.select_probes(
            deviation_category=category,
            anomaly_description=description,
        )

        survey = MicroSurvey(
            engagement_id=engagement_id,
            triggering_deviation_id=deviation.id,
            target_element_id=getattr(deviation, "element_id", str(deviation.id)),
            target_element_name=getattr(deviation, "element_name", "Unknown Element"),
            target_sme_role=target_sme_role,
            anomaly_description=description,
            probes=probes,
            status=MicroSurveyStatus.GENERATED,
        )
        self._session.add(survey)
        await self._session.flush()

        return survey

    async def submit_response(
        self,
        survey_id: uuid.UUID,
        responses: list[dict[str, Any]],
        respondent_role: str,
    ) -> list[dict[str, Any]]:
        """Process micro-survey responses and create SurveyClaims.

        Args:
            survey_id: The micro-survey being responded to.
            responses: List of dicts with probe_type, claim_text, certainty_tier.
            respondent_role: The respondent's role.

        Returns:
            List of created claim summaries.
        """
        result = await self._session.execute(
            select(MicroSurvey).where(MicroSurvey.id == survey_id)
        )
        survey = result.scalar_one_or_none()
        if survey is None:
            raise ValueError(f"Micro-survey {survey_id} not found")

        claims: list[dict[str, Any]] = []
        for resp in responses:
            claim = SurveyClaim(
                engagement_id=survey.engagement_id,
                session_id=survey_id,  # Use survey ID as session
                probe_type=resp["probe_type"],
                respondent_role=respondent_role,
                claim_text=resp["claim_text"],
                certainty_tier=resp["certainty_tier"],
                micro_survey_id=survey_id,
            )
            self._session.add(claim)
            claims.append({
                "probe_type": resp["probe_type"],
                "claim_text": resp["claim_text"],
                "certainty_tier": resp["certainty_tier"],
                "micro_survey_id": str(survey_id),
            })

        survey.status = MicroSurveyStatus.RESPONDED
        survey.responded_at = datetime.now(UTC)
        await self._session.flush()

        return claims


def _generate_probe_question(probe_type: ProbeType, context: str) -> str:
    """Generate a contextual probe question based on type and anomaly context."""
    templates: dict[ProbeType, str] = {
        ProbeType.EXISTENCE: f"We detected an anomaly: {context}. Does this activity actually occur as described?",
        ProbeType.SEQUENCE: f"Regarding the anomaly: {context}. Has the order of steps changed recently?",
        ProbeType.DEPENDENCY: f"Regarding the anomaly: {context}. Are there new dependencies or missing inputs?",
        ProbeType.INPUT_OUTPUT: f"Regarding the anomaly: {context}. Have the inputs or outputs changed?",
        ProbeType.GOVERNANCE: f"Regarding the anomaly: {context}. Are there policy or governance changes?",
        ProbeType.PERFORMER: f"Regarding the anomaly: {context}. Has there been a change in who performs this?",
        ProbeType.EXCEPTION: f"Regarding the anomaly: {context}. Is this an exception or a new normal?",
        ProbeType.UNCERTAINTY: f"Regarding the anomaly: {context}. How confident are you about this process?",
    }
    return templates.get(probe_type, f"Regarding the anomaly: {context}. Please provide context.")
