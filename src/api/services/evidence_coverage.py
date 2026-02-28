"""Evidence Confidence Overlay service for per-scenario coverage analysis.

Surfaces which scenario modifications affect areas with Bright (high confidence),
Dim (medium confidence), or Dark (insufficient evidence) coverage. Modifications
to Dark areas are flagged as high-uncertainty changes.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.pov import BrightnessClassification, ProcessElement
from src.core.models.simulation import ScenarioModification, SimulationScenario

logger = logging.getLogger(__name__)

_WARNING_MESSAGE = "Modifying area with insufficient evidence"


class EvidenceCoverageService:
    """Computes per-element evidence confidence overlays for simulation scenarios."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_scenario_coverage(
        self,
        scenario_id: uuid.UUID,
        engagement_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Get per-element brightness classification for a scenario's modifications.

        Returns each modified element with its brightness, warning flag, and a
        coverage summary with bright/dim/dark counts and risk score.
        """
        scenario = await self._get_scenario(scenario_id, engagement_id)

        modifications = await self._session.execute(
            select(ScenarioModification).where(
                ScenarioModification.scenario_id == scenario.id,
            )
        )
        mods = modifications.scalars().all()

        if not mods:
            return self._build_response(scenario_id, [], 0, 0, 0)

        element_ids = [m.element_id for m in mods]

        brightness_map = await self._get_brightness_map(element_ids)

        modified_elements: list[dict[str, Any]] = []
        bright_count = 0
        dim_count = 0
        dark_count = 0

        for mod in mods:
            brightness = brightness_map.get(mod.element_id, BrightnessClassification.DARK)
            is_dark = brightness == BrightnessClassification.DARK
            warning_message = _WARNING_MESSAGE if is_dark else None

            modified_elements.append(
                {
                    "element_id": mod.element_id,
                    "element_name": mod.element_name,
                    "brightness": brightness.value,
                    "warning": is_dark,
                    "warning_message": warning_message,
                }
            )

            if brightness == BrightnessClassification.BRIGHT:
                bright_count += 1
            elif brightness == BrightnessClassification.DIM:
                dim_count += 1
            else:
                dark_count += 1

        return self._build_response(scenario_id, modified_elements, bright_count, dim_count, dark_count)

    async def compare_scenarios(
        self,
        scenario_ids: list[uuid.UUID],
        engagement_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """Compare multiple scenarios by evidence coverage risk score.

        Returns scenarios sorted by risk_score descending (lowest risk first).
        """
        results = []
        for sid in scenario_ids:
            coverage = await self.get_scenario_coverage(sid, engagement_id)
            results.append(coverage)

        results.sort(key=lambda r: r["coverage_summary"]["risk_score"], reverse=True)
        return results

    async def _get_scenario(
        self,
        scenario_id: uuid.UUID,
        engagement_id: uuid.UUID,
    ) -> SimulationScenario:
        """Fetch scenario, verifying it belongs to the given engagement."""
        result = await self._session.execute(
            select(SimulationScenario).where(
                SimulationScenario.id == scenario_id,
                SimulationScenario.engagement_id == engagement_id,
            )
        )
        scenario = result.scalar_one_or_none()
        if scenario is None:
            raise ValueError(f"Scenario {scenario_id} not found in engagement {engagement_id}")
        return scenario

    async def _get_brightness_map(
        self,
        element_ids: list[str],
    ) -> dict[str, BrightnessClassification]:
        """Build a map of element_id -> brightness from ProcessElement records.

        ScenarioModification.element_id stores the process element's name
        (String(512)), matching ProcessElement.name. This is intentional:
        scenarios reference elements by their human-readable name, not UUID.
        See scenarios.py create_modification where element_name=payload.element_id.
        """
        result = await self._session.execute(
            select(ProcessElement.name, ProcessElement.brightness_classification).where(
                ProcessElement.name.in_(element_ids),
            )
        )
        rows = result.all()
        return {row[0]: row[1] for row in rows}

    @staticmethod
    def compute_risk_score(bright_count: int, dark_count: int) -> float:
        """Compute risk score: bright / (bright + dark), 0-1 scale.

        Higher score = lower risk. Returns 1.0 if no bright or dark elements.
        """
        total = bright_count + dark_count
        if total == 0:
            return 1.0
        return round(bright_count / total, 4)

    @staticmethod
    def _build_response(
        scenario_id: uuid.UUID,
        modified_elements: list[dict[str, Any]],
        bright_count: int,
        dim_count: int,
        dark_count: int,
    ) -> dict[str, Any]:
        risk_score = EvidenceCoverageService.compute_risk_score(bright_count, dark_count)
        return {
            "scenario_id": str(scenario_id),
            "modified_elements": modified_elements,
            "coverage_summary": {
                "bright_count": bright_count,
                "dim_count": dim_count,
                "dark_count": dark_count,
                "risk_score": risk_score,
            },
        }
