"""Survey bot service for structured knowledge elicitation (Story #319).

Manages survey sessions, generates probes from seed terms using 8 probe
types, creates SurveyClaim objects from SME responses, and produces
session summaries with certainty tier distribution.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func as sa_func
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.survey import CertaintyTier, ProbeType, SurveyClaim
from src.core.models.survey_session import SurveySession, SurveySessionStatus

logger = logging.getLogger(__name__)

# Probe templates for each of the 8 probe types.
# Ordered to minimize SME fatigue: broad existence → specific details → edge cases.
PROBE_TEMPLATES: dict[ProbeType, dict[str, str]] = {
    ProbeType.EXISTENCE: {
        "question": "Does '{term}' happen in your area?",
        "expected_response": "exists (Yes/No), frequency, exceptions, respondent_role",
    },
    ProbeType.SEQUENCE: {
        "question": "Where does '{term}' fit in the process sequence? What comes before and after?",
        "expected_response": "predecessor activities, successor activities, ordering constraints",
    },
    ProbeType.DEPENDENCY: {
        "question": "What does '{term}' depend on to start or complete?",
        "expected_response": "required inputs, prerequisite activities, systems needed",
    },
    ProbeType.INPUT_OUTPUT: {
        "question": "What are the inputs and outputs of '{term}'?",
        "expected_response": "input documents/data, output artifacts, transformations applied",
    },
    ProbeType.GOVERNANCE: {
        "question": "What rules or criteria govern '{term}'?",
        "expected_response": "business rules, regulatory requirements, approval criteria",
    },
    ProbeType.PERFORMER: {
        "question": "Who performs '{term}' and what role do they play?",
        "expected_response": "performing role, responsible person, escalation path",
    },
    ProbeType.EXCEPTION: {
        "question": "What exceptions or edge cases occur during '{term}'?",
        "expected_response": "exception triggers, handling procedures, fallback paths",
    },
    ProbeType.UNCERTAINTY: {
        "question": "What aspects of '{term}' are uncertain or vary between instances?",
        "expected_response": "variable elements, decision points, conditional branches",
    },
}

# Fatigue-optimized probe ordering
PROBE_ORDER: list[ProbeType] = [
    ProbeType.EXISTENCE,
    ProbeType.SEQUENCE,
    ProbeType.DEPENDENCY,
    ProbeType.INPUT_OUTPUT,
    ProbeType.GOVERNANCE,
    ProbeType.PERFORMER,
    ProbeType.EXCEPTION,
    ProbeType.UNCERTAINTY,
]


class SurveyBotService:
    """Manages survey sessions and probe generation."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Session Lifecycle ────────────────────────────────────────────

    async def create_session(
        self,
        *,
        engagement_id: uuid.UUID,
        respondent_role: str,
    ) -> dict[str, Any]:
        """Create a new survey session."""
        survey_session = SurveySession(
            engagement_id=engagement_id,
            respondent_role=respondent_role,
            status=SurveySessionStatus.ACTIVE,
        )
        self._session.add(survey_session)
        await self._session.flush()

        logger.info(
            "Survey session created: engagement=%s, role=%s",
            engagement_id,
            respondent_role,
        )
        return {
            "id": str(survey_session.id),
            "engagement_id": str(engagement_id),
            "respondent_role": respondent_role,
            "status": "active",
            "created_at": survey_session.created_at.isoformat()
            if survey_session.created_at
            else datetime.now(UTC).isoformat(),
        }

    async def get_session(self, session_id: uuid.UUID) -> SurveySession | None:
        """Get a survey session by ID."""
        stmt = select(SurveySession).where(SurveySession.id == session_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def complete_session(self, session_id: uuid.UUID) -> dict[str, Any]:
        """Mark a session as complete and generate summary."""
        session_obj = await self.get_session(session_id)
        if session_obj is None:
            return {"error": "not_found"}

        if session_obj.status != SurveySessionStatus.ACTIVE:
            return {
                "error": "invalid_status",
                "current_status": session_obj.status.value,
            }

        # Get claims for this session
        claims_stmt = select(SurveyClaim).where(SurveyClaim.session_id == session_id)
        claims_result = await self._session.execute(claims_stmt)
        claims = claims_result.scalars().all()

        # Build summary
        summary = self._build_session_summary(claims)

        # Update session
        session_obj.status = SurveySessionStatus.COMPLETED
        session_obj.completed_at = datetime.now(UTC)
        session_obj.claims_count = len(claims)
        session_obj.summary = summary
        await self._session.flush()

        return {
            "session_id": str(session_id),
            "status": "completed",
            "claims_count": len(claims),
            "summary": summary,
        }

    # ── Probe Generation ─────────────────────────────────────────────

    def generate_probes_for_terms(
        self,
        terms: list[dict[str, Any]],
        *,
        session_id: uuid.UUID,
        probe_types: list[ProbeType] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate probes for seed terms, ordered by fatigue-minimization.

        Args:
            terms: List of seed term dicts with id, term, domain, category.
            session_id: The survey session ID.
            probe_types: Optional subset of probe types to generate.

        Returns:
            List of probe dicts ordered for optimal SME experience.
        """
        active_types = probe_types or PROBE_ORDER

        probes = []
        for probe_type in active_types:
            if probe_type not in PROBE_TEMPLATES:
                continue
            template = PROBE_TEMPLATES[probe_type]
            for term in terms:
                probes.append(
                    {
                        "session_id": str(session_id),
                        "seed_term_id": term["id"],
                        "seed_term": term["term"],
                        "probe_type": probe_type.value,
                        "question": template["question"].replace("{term}", term["term"]),
                        "expected_response": template["expected_response"],
                    }
                )

        return probes

    # ── Claim Creation ───────────────────────────────────────────────

    async def create_claim(
        self,
        *,
        engagement_id: uuid.UUID,
        session_id: uuid.UUID,
        probe_type: ProbeType,
        respondent_role: str,
        claim_text: str,
        certainty_tier: CertaintyTier,
        proof_expectation: str | None = None,
        related_seed_terms: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a SurveyClaim from an SME response."""
        claim = SurveyClaim(
            engagement_id=engagement_id,
            session_id=session_id,
            probe_type=probe_type,
            respondent_role=respondent_role,
            claim_text=claim_text,
            certainty_tier=certainty_tier,
            proof_expectation=proof_expectation,
            related_seed_terms=related_seed_terms or [],
        )
        self._session.add(claim)

        # Increment session claims count
        await self._session.execute(
            update(SurveySession)
            .where(SurveySession.id == session_id)
            .values(claims_count=SurveySession.claims_count + 1)
        )

        await self._session.flush()

        logger.info(
            "Claim created: session=%s, probe=%s, tier=%s",
            session_id,
            probe_type.value,
            certainty_tier.value,
        )

        return {
            "id": str(claim.id),
            "session_id": str(session_id),
            "probe_type": probe_type.value,
            "certainty_tier": certainty_tier.value,
            "claim_text": claim_text,
            "requires_conflict_check": certainty_tier == CertaintyTier.CONTRADICTED,
        }

    # ── Session Summary ──────────────────────────────────────────────

    @staticmethod
    def _build_session_summary(
        claims: list[SurveyClaim],
    ) -> dict[str, Any]:
        """Build a session summary from claims."""
        # Group by probe type
        by_probe: dict[str, int] = {}
        for claim in claims:
            key = claim.probe_type.value
            by_probe[key] = by_probe.get(key, 0) + 1

        # Certainty tier distribution
        by_tier: dict[str, int] = {}
        for claim in claims:
            key = claim.certainty_tier.value
            by_tier[key] = by_tier.get(key, 0) + 1

        return {
            "total_claims": len(claims),
            "by_probe_type": by_probe,
            "by_certainty_tier": by_tier,
            "probe_type_coverage": len(by_probe),
            "contradicted_count": by_tier.get("contradicted", 0),
        }

    # ── Multi-Respondent Consensus ──────────────────────────────────

    async def compute_consensus(
        self,
        engagement_id: uuid.UUID,
        *,
        activity_name: str | None = None,
        min_sessions: int = 2,
    ) -> dict[str, Any]:
        """Aggregate claims across multiple survey sessions for consensus.

        Identifies agreement, conflicts, and uncertainty across respondents
        for the same activities or process areas.

        Args:
            engagement_id: Engagement to analyze.
            activity_name: Optional filter to a specific activity.
            min_sessions: Minimum sessions required for consensus.

        Returns:
            Dict with consensus results, conflicts, and agreement scores.
        """
        # Get all completed sessions for the engagement
        sessions_result = await self.list_sessions(
            engagement_id,
            status=SurveySessionStatus.COMPLETED,
            limit=1000,
        )
        sessions = sessions_result["items"]

        if len(sessions) < min_sessions:
            return {
                "engagement_id": str(engagement_id),
                "status": "insufficient_sessions",
                "sessions_found": len(sessions),
                "min_required": min_sessions,
                "consensus": [],
            }

        # Get all claims for these sessions
        session_ids = [uuid.UUID(s["id"]) for s in sessions]
        claims_stmt = (
            select(SurveyClaim)
            .where(
                SurveyClaim.session_id.in_(session_ids),
                SurveyClaim.engagement_id == engagement_id,
            )
            .order_by(SurveyClaim.probe_type)
        )
        claims_result = await self._session.execute(claims_stmt)
        all_claims = claims_result.scalars().all()

        # Group claims by probe type + related seed terms for cross-session comparison
        claim_groups: dict[str, list[SurveyClaim]] = {}
        for claim in all_claims:
            # Group key: probe_type + first seed term (approximation of topic)
            terms = claim.related_seed_terms or []
            topic = terms[0] if terms else "general"
            if activity_name and activity_name.lower() not in claim.claim_text.lower():
                continue
            group_key = f"{claim.probe_type.value}:{topic}"
            claim_groups.setdefault(group_key, []).append(claim)

        # Compute consensus for each group
        consensus_items: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []

        for group_key, group_claims in sorted(claim_groups.items()):
            if len(group_claims) < 2:
                continue

            # Check tier agreement
            tiers = [c.certainty_tier for c in group_claims]
            unique_tiers = set(tiers)
            roles = list({c.respondent_role for c in group_claims})

            if len(unique_tiers) == 1:
                # Full agreement
                consensus_items.append(
                    {
                        "topic": group_key,
                        "agreement": "full",
                        "certainty_tier": tiers[0].value,
                        "respondent_count": len(group_claims),
                        "respondent_roles": roles,
                    }
                )
            elif CertaintyTier.CONTRADICTED in unique_tiers:
                # Active contradiction
                conflicts.append(
                    {
                        "topic": group_key,
                        "conflict_type": "contradiction",
                        "tiers": [t.value for t in tiers],
                        "respondent_roles": roles,
                        "claims": [
                            {
                                "role": c.respondent_role,
                                "tier": c.certainty_tier.value,
                                "text_preview": c.claim_text[:100],
                            }
                            for c in group_claims
                        ],
                    }
                )
            else:
                # Partial agreement (different tiers but no contradiction)
                consensus_items.append(
                    {
                        "topic": group_key,
                        "agreement": "partial",
                        "tiers": sorted(t.value for t in unique_tiers),
                        "respondent_count": len(group_claims),
                        "respondent_roles": roles,
                    }
                )

        # Compute agreement score
        total_groups = len(consensus_items) + len(conflicts)
        full_agreement = sum(1 for c in consensus_items if c["agreement"] == "full")
        agreement_score = full_agreement / total_groups if total_groups > 0 else 0.0

        return {
            "engagement_id": str(engagement_id),
            "status": "computed",
            "sessions_analyzed": len(sessions),
            "total_claims": len(all_claims),
            "consensus_items": consensus_items,
            "conflicts": conflicts,
            "agreement_score": round(agreement_score, 4),
            "conflict_count": len(conflicts),
        }

    # ── List Sessions ────────────────────────────────────────────────

    async def list_sessions(
        self,
        engagement_id: uuid.UUID,
        *,
        status: SurveySessionStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List survey sessions for an engagement."""
        base_filter = [SurveySession.engagement_id == engagement_id]
        if status is not None:
            base_filter.append(SurveySession.status == status)

        count_stmt = select(sa_func.count()).select_from(SurveySession).where(*base_filter)
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar() or 0

        query = (
            select(SurveySession)
            .where(*base_filter)
            .order_by(SurveySession.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(query)
        sessions = result.scalars().all()

        return {
            "items": [
                {
                    "id": str(s.id),
                    "engagement_id": str(s.engagement_id),
                    "respondent_role": s.respondent_role,
                    "status": s.status.value,
                    "claims_count": s.claims_count,
                    "created_at": s.created_at.isoformat(),
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                }
                for s in sessions
            ],
            "total_count": total,
            "limit": limit,
            "offset": offset,
        }
