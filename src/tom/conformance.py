"""Conformance Checking Engine.

Compares generated POV process models against reference BPMN models.
Calculates fitness scores and detects deviations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import ProcessElement

logger = logging.getLogger(__name__)


@dataclass
class Deviation:
    """A detected deviation between POV and reference model.

    Attributes:
        element_name: Name of the deviating element.
        deviation_type: Type of deviation (missing, extra, different).
        severity: Deviation severity (0-1).
        description: Human-readable description.
    """

    element_name: str = ""
    deviation_type: str = "missing"
    severity: float = 0.5
    description: str = ""


@dataclass
class ConformanceResult:
    """Result of conformance checking.

    Attributes:
        pov_model_id: The POV model checked.
        reference_model_id: The reference model compared against.
        fitness_score: Overall fitness (0-1, 1 = perfect conformance).
        deviations: List of detected deviations.
        matching_elements: Count of matching elements.
        total_reference_elements: Total elements in reference model.
    """

    pov_model_id: str = ""
    reference_model_id: str = ""
    fitness_score: float = 0.0
    deviations: list[Deviation] = field(default_factory=list)
    matching_elements: int = 0
    total_reference_elements: int = 0


class ConformanceCheckingEngine:
    """Engine for comparing POV models against reference BPMN models.

    Uses element-level comparison to calculate fitness scores and
    identify deviations between discovered and reference processes.
    """

    async def check_conformance(
        self,
        session: AsyncSession,
        pov_model_id: str,
        reference_model_id: str,
    ) -> ConformanceResult:
        """Compare a POV model against a reference model.

        Args:
            session: Database session.
            pov_model_id: ID of the POV-generated process model.
            reference_model_id: ID of the reference BPMN model.

        Returns:
            ConformanceResult with fitness score and deviations.
        """
        result = ConformanceResult(
            pov_model_id=pov_model_id,
            reference_model_id=reference_model_id,
        )

        # Fetch POV model elements
        pov_elements = await self._fetch_elements(session, pov_model_id)
        ref_elements = await self._fetch_elements(session, reference_model_id)

        if not ref_elements:
            logger.warning("No reference elements found for model %s", reference_model_id)
            return result

        result.total_reference_elements = len(ref_elements)

        # Build name-based lookup for comparison
        pov_names = {e.name.lower().strip() for e in pov_elements}
        ref_names = {e.name.lower().strip() for e in ref_elements}

        # Find matches
        matches = pov_names & ref_names
        result.matching_elements = len(matches)

        # Find missing (in reference but not in POV)
        missing = ref_names - pov_names
        for name in missing:
            result.deviations.append(
                Deviation(
                    element_name=name,
                    deviation_type="missing",
                    severity=0.7,
                    description=f"Reference element '{name}' not found in POV model",
                )
            )

        # Find extra (in POV but not in reference)
        extra = pov_names - ref_names
        for name in extra:
            result.deviations.append(
                Deviation(
                    element_name=name,
                    deviation_type="extra",
                    severity=0.3,
                    description=f"POV element '{name}' not in reference model (potential discovery)",
                )
            )

        # Calculate fitness score
        if result.total_reference_elements > 0:
            result.fitness_score = round(result.matching_elements / result.total_reference_elements, 4)

        return result

    async def _fetch_elements(
        self,
        session: AsyncSession,
        model_id: str,
    ) -> list[ProcessElement]:
        """Fetch process elements for a model."""
        query = select(ProcessElement).where(ProcessElement.model_id == model_id)
        result = await session.execute(query)
        return list(result.scalars().all())
