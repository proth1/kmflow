"""LLM-powered gap rationale generation service.

Generates human-readable rationale for each identified gap using
structured few-shot prompting. Each rationale includes evidence
references, plain-language explanation, and recommendations.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import GapAnalysisResult, TargetOperatingModel

logger = logging.getLogger(__name__)

# Few-shot examples for rationale generation
FEW_SHOT_EXAMPLES: list[dict[str, Any]] = [
    {
        "gap_type": "full_gap",
        "dimension": "process_architecture",
        "activity": "Manual Exception Logging",
        "tom_specification": "Automated exception handling with real-time alerting",
        "rationale": (
            "The current process relies entirely on manual exception logging, "
            "requiring staff to identify, categorize, and record exceptions by hand. "
            "The TOM specifies automated exception handling with real-time alerting, "
            "which represents a complete capability gap. No automated tooling exists "
            "to bridge the current manual process to the target state."
        ),
        "recommendation": (
            "Implement an automated exception handling system with rule-based "
            "categorization and real-time alerting. Consider integrating with "
            "existing monitoring infrastructure to reduce implementation effort."
        ),
    },
    {
        "gap_type": "partial_gap",
        "dimension": "technology_and_data",
        "activity": "Credit Risk Assessment",
        "tom_specification": "Automated credit scoring with ML-based risk models",
        "rationale": (
            "The current Credit Risk Assessment process includes some automated "
            "scoring elements but lacks the ML-based risk models specified in the TOM. "
            "The existing rule-based scoring covers basic credit checks but does not "
            "incorporate predictive analytics or dynamic risk adjustment as required."
        ),
        "recommendation": (
            "Enhance the existing scoring engine with ML-based risk models. "
            "Start with a pilot using historical data to train and validate models "
            "before full production deployment."
        ),
    },
    {
        "gap_type": "deviation",
        "dimension": "governance_structures",
        "activity": "Approval Routing",
        "tom_specification": "Four-eyes approval with automated escalation paths",
        "rationale": (
            "The current Approval Routing process implements a basic two-level "
            "approval but deviates from the TOM's four-eyes principle. While "
            "approval workflows exist, automated escalation paths are missing, "
            "leading to potential bottlenecks and delayed processing."
        ),
        "recommendation": (
            "Extend the approval workflow to enforce four-eyes principle with "
            "configurable escalation timeouts and automated routing to backup approvers."
        ),
    },
]


def _sanitize_xml_content(text: str) -> str:
    """Strip XML-like closing tags that could break prompt boundaries."""
    return text.replace("</activity>", "").replace("</tom_spec>", "")


def build_rationale_prompt(
    gap_type: str,
    dimension: str,
    activity_description: str,
    tom_specification: str,
    severity: float,
    confidence: float,
) -> str:
    """Build a structured prompt for rationale generation.

    Args:
        gap_type: The gap type (full_gap, partial_gap, deviation).
        dimension: The TOM dimension affected.
        activity_description: Description of the current-state activity.
        tom_specification: The TOM target specification text.
        severity: Gap severity (0-1).
        confidence: Confidence level (0-1).

    Returns:
        Formatted prompt string.
    """
    examples_text = ""
    for ex in FEW_SHOT_EXAMPLES:
        examples_text += f"""
Example ({ex['gap_type'].upper()} in {ex['dimension']}):
Activity: {ex['activity']}
TOM Specification: {ex['tom_specification']}
Rationale: {ex['rationale']}
Recommendation: {ex['recommendation']}
---"""

    safe_activity = _sanitize_xml_content(activity_description)
    safe_tom = _sanitize_xml_content(tom_specification)

    return f"""You are a process intelligence analyst generating gap analysis rationale.

Given information about a gap between a current-state process activity and a Target Operating Model (TOM) specification, generate:
1. A clear, human-readable rationale explaining why the gap exists
2. A specific recommendation for closing the gap

The rationale should:
- Reference the TOM specification text
- Explain the nature and impact of the deviation
- Be written in professional consulting language
- Be 2-4 sentences long

The recommendation should:
- Be actionable and specific
- Consider implementation effort
- Be 1-3 sentences long

Here are examples of good rationale and recommendations:
{examples_text}

Now generate rationale and recommendation for:

Gap Type: {gap_type.upper()}
Dimension: {dimension}
Current Activity: <activity>{safe_activity}</activity>
TOM Specification: <tom_spec>{safe_tom}</tom_spec>
Severity: {severity}
Confidence: {confidence}

Respond in JSON format:
{{"rationale": "...", "recommendation": "..."}}"""


class RationaleGeneratorService:
    """Generates LLM-powered rationale for gap analysis results."""

    def __init__(self, settings: Any | None = None) -> None:
        if settings is None:
            from src.core.config import get_settings

            settings = get_settings()
        self._settings = settings

    async def generate_rationale(
        self,
        gap: GapAnalysisResult,
        tom_specification: str | None = None,
        activity_description: str | None = None,
    ) -> dict[str, str]:
        """Generate rationale for a single gap.

        Args:
            gap: The gap analysis result record.
            tom_specification: The TOM dimension specification text.
            activity_description: Description of the current-state activity.
                Falls back to gap.activity_name or gap_type if not provided.

        Returns:
            Dict with 'rationale' and 'recommendation' keys.
        """
        desc = activity_description or getattr(gap, "activity_name", None) or str(gap.gap_type)
        prompt = build_rationale_prompt(
            gap_type=str(gap.gap_type),
            dimension=str(gap.dimension),
            activity_description=desc,
            tom_specification=tom_specification or "Not specified",
            severity=gap.severity,
            confidence=gap.confidence,
        )

        try:
            response_text = await self._call_llm(prompt)
            return self._parse_response(response_text)
        except Exception:
            logger.exception("Failed to generate rationale for gap %s", gap.id)
            return self._fallback_rationale(gap)

    async def generate_bulk_rationales(
        self,
        session: AsyncSession,
        engagement_id: str,
    ) -> list[dict[str, Any]]:
        """Generate rationales for all gaps in an engagement.

        Args:
            session: Database session.
            engagement_id: The engagement UUID string.

        Returns:
            List of dicts with gap_id, rationale, recommendation.
        """
        from uuid import UUID

        # Fetch gaps without rationale
        result = await session.execute(
            select(GapAnalysisResult).where(
                GapAnalysisResult.engagement_id == UUID(engagement_id),
                GapAnalysisResult.rationale.is_(None),
            )
        )
        gaps = list(result.scalars().all())

        if not gaps:
            return []

        # Fetch TOM specifications for dimension context
        tom_specs = await self._get_tom_specifications(session, gaps)

        results = []
        for gap in gaps:
            spec = tom_specs.get(str(gap.dimension), None)
            rationale_data = await self.generate_rationale(gap, spec)

            gap.rationale = rationale_data["rationale"]
            gap.recommendation = rationale_data["recommendation"]

            results.append(
                {
                    "gap_id": str(gap.id),
                    "rationale": rationale_data["rationale"],
                    "recommendation": rationale_data["recommendation"],
                }
            )

        await session.flush()
        return results

    async def _call_llm(self, prompt: str) -> str:
        """Call the LLM API."""
        try:
            import anthropic

            client = anthropic.AsyncAnthropic()
            model = getattr(self._settings, "suggester_model", "claude-sonnet-4-5-20250929")
            response = await client.messages.create(
                model=model,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except ImportError:
            logger.warning("anthropic package not available, using fallback")
            raise
        except Exception:
            logger.exception("LLM API call failed")
            raise

    def _parse_response(self, response_text: str) -> dict[str, str]:
        """Parse LLM response into rationale and recommendation."""
        try:
            # Try to extract JSON from the response
            text = response_text.strip()
            # Handle markdown code blocks
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            data = json.loads(text)
            return {
                "rationale": str(data.get("rationale", "")),
                "recommendation": str(data.get("recommendation", "")),
            }
        except (json.JSONDecodeError, IndexError, KeyError):
            # If JSON parsing fails, use the whole response as rationale
            return {
                "rationale": response_text.strip()[:2000],
                "recommendation": "",
            }

    def _fallback_rationale(self, gap: GapAnalysisResult) -> dict[str, str]:
        """Generate fallback rationale when LLM is unavailable."""
        gap_type = str(gap.gap_type).replace("_", " ").title()
        dimension = str(gap.dimension).replace("_", " ").title()

        return {
            "rationale": (
                f"A {gap_type} has been identified in the {dimension} dimension. "
                f"The current process deviates from the target operating model specification "
                f"with a severity of {gap.severity:.1f} and confidence of {gap.confidence:.1f}."
            ),
            "recommendation": (
                f"Review the {dimension} dimension requirements in the TOM and "
                f"assess the feasibility of bridging this gap."
            ),
        }

    async def _get_tom_specifications(
        self,
        session: AsyncSession,
        gaps: list[GapAnalysisResult],
    ) -> dict[str, str]:
        """Fetch TOM dimension specifications for context."""
        from sqlalchemy.orm import selectinload

        tom_ids = {gap.tom_id for gap in gaps}
        specs: dict[str, str] = {}

        for tom_id in tom_ids:
            result = await session.execute(
                select(TargetOperatingModel)
                .where(TargetOperatingModel.id == tom_id)
                .options(selectinload(TargetOperatingModel.dimension_records))
            )
            tom = result.scalar_one_or_none()
            if tom and tom.dimension_records:
                for dr in tom.dimension_records:
                    if dr.description:
                        specs[str(dr.dimension_type)] = dr.description

        return specs


def compute_composite_score(
    business_criticality: int,
    risk_exposure: int,
    regulatory_impact: int,
    remediation_cost: int,
) -> float:
    """Compute composite priority score.

    Formula: (criticality × risk × regulatory) / cost

    Args:
        business_criticality: 1-5 scale.
        risk_exposure: 1-5 scale.
        regulatory_impact: 1-5 scale.
        remediation_cost: 1-5 scale.

    Returns:
        Composite score (higher = higher priority).
    """
    return round(
        (business_criticality * risk_exposure * regulatory_impact) / max(remediation_cost, 1),
        4,
    )
