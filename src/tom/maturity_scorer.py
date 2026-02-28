"""Process maturity scoring engine.

Computes CMMI-aligned maturity levels (1-5) per process area based on
evidence coverage, governance linkages, and metric availability.
"""

from __future__ import annotations

from typing import Any

from src.core.models.tom import MATURITY_LEVEL_NUMBER, ProcessMaturity


def compute_evidence_dimensions(
    process_model: dict[str, Any],
    governance_data: dict[str, Any],
) -> dict[str, Any]:
    """Gather evidence dimension metrics for a process area.

    Returns a dict of dimension scores used by the level assignment logic.
    Keys:
        form_coverage: float (0.0-1.0)  - knowledge form coverage
        governance_coverage: bool       - has governance linkages
        has_metrics: bool               - has performance metrics
        has_statistical_control: bool   - has statistical process control
        has_continuous_improvement: bool - has CI evidence
    """
    form_coverage = process_model.get("form_coverage", 0.0)
    governance_coverage = governance_data.get("has_governance", False)
    has_metrics = governance_data.get("has_metrics", False)
    has_statistical_control = governance_data.get("has_statistical_control", False)
    has_continuous_improvement = governance_data.get("has_continuous_improvement", False)

    return {
        "form_coverage": form_coverage,
        "governance_coverage": governance_coverage,
        "has_metrics": has_metrics,
        "has_statistical_control": has_statistical_control,
        "has_continuous_improvement": has_continuous_improvement,
    }


def assign_maturity_level(dimensions: dict[str, Any]) -> ProcessMaturity:
    """Assign a CMMI-aligned maturity level based on evidence dimensions.

    Level assignment rules (from issue #358):
      OPTIMIZING (5):  coverage > 80% + statistical controls + CI evidence
      QUANTITATIVELY_MANAGED (4): coverage > 80% + statistical controls + measured performance
      DEFINED (3): coverage 60-80% + full governance chain + some metrics
      MANAGED (2): coverage 40-60% + some governance
      INITIAL (1): coverage < 40%
    """
    coverage = dimensions.get("form_coverage", 0.0)
    has_governance = dimensions.get("governance_coverage", False)
    has_metrics = dimensions.get("has_metrics", False)
    has_statistical_control = dimensions.get("has_statistical_control", False)
    has_ci = dimensions.get("has_continuous_improvement", False)

    if coverage > 0.8 and has_statistical_control and has_ci:
        return ProcessMaturity.OPTIMIZING

    if coverage > 0.8 and has_statistical_control and has_metrics:
        return ProcessMaturity.QUANTITATIVELY_MANAGED

    if coverage >= 0.6 and has_governance and has_metrics:
        return ProcessMaturity.DEFINED

    if coverage >= 0.4 and has_governance:
        return ProcessMaturity.MANAGED

    return ProcessMaturity.INITIAL


def generate_recommendations(
    level: ProcessMaturity,
    dimensions: dict[str, Any],
) -> list[str]:
    """Generate improvement recommendations based on current maturity and gaps."""
    recs: list[str] = []
    coverage = dimensions.get("form_coverage", 0.0)

    if coverage < 0.4:
        recs.append("Document procedures for knowledge forms 1-4 to establish baseline coverage")
    if coverage < 0.6:
        recs.append("Define roles and responsibilities (Form 6) to achieve MANAGED level")
    if not dimensions.get("governance_coverage", False):
        recs.append("Establish governance linkages between process activities and controls")
    if not dimensions.get("has_metrics", False):
        recs.append("Introduce performance metrics and KPIs for process monitoring")
    if not dimensions.get("has_statistical_control", False) and coverage > 0.6:
        recs.append("Implement statistical process controls for quantitative management")
    if not dimensions.get("has_continuous_improvement", False) and coverage > 0.8:
        recs.append("Establish continuous improvement mechanisms to reach OPTIMIZING level")

    return recs


class MaturityScoringService:
    """Orchestrates maturity scoring across process areas for an engagement."""

    async def score_process_area(
        self,
        process_model: dict[str, Any],
        governance_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Score a single process area and return the result dict.

        Args:
            process_model: Dict with keys 'id', 'scope', 'engagement_id', 'form_coverage', etc.
            governance_data: Dict with governance and metric flags for this process area.

        Returns:
            Dict with maturity_level, level_number, evidence_dimensions, recommendations.
        """
        dimensions = compute_evidence_dimensions(process_model, governance_data)
        level = assign_maturity_level(dimensions)
        level_number = MATURITY_LEVEL_NUMBER[level]
        recommendations = generate_recommendations(level, dimensions)

        return {
            "process_model_id": process_model["id"],
            "engagement_id": process_model["engagement_id"],
            "maturity_level": level,
            "level_number": level_number,
            "evidence_dimensions": dimensions,
            "recommendations": recommendations,
        }

    async def score_engagement(
        self,
        process_models: list[dict[str, Any]],
        governance_map: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Score all process areas in an engagement.

        Args:
            process_models: List of process model dicts.
            governance_map: Mapping of process_model_id (str) to governance data.

        Returns:
            List of score result dicts.
        """
        results = []
        for pm in process_models:
            pm_id = str(pm["id"])
            gov_data = governance_map.get(pm_id, {})
            score = await self.score_process_area(pm, gov_data)
            results.append(score)
        return results
