"""Survey claim management service (Story #322).

Handles CRUD operations, certainty tier transitions with history tracking,
shelf data request auto-generation for SUSPECTED claims, and filtered
paginated queries.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.engagement import (
    ShelfDataRequest,
    ShelfDataRequestItem,
    ShelfRequestStatus,
)
from src.core.models.evidence import EvidenceCategory
from src.core.models.survey import CertaintyTier, ProbeType, SurveyClaim
from src.core.models.survey_claim_history import SurveyClaimHistory

logger = logging.getLogger(__name__)


class SurveyClaimService:
    """Manages survey claim lifecycle and certainty tier tracking."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_claim(self, claim_id: uuid.UUID) -> SurveyClaim | None:
        """Get a single survey claim by ID."""
        stmt = select(SurveyClaim).where(SurveyClaim.id == claim_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_certainty_tier(
        self,
        claim_id: uuid.UUID,
        new_tier: CertaintyTier,
        changed_by: uuid.UUID,
    ) -> dict[str, Any]:
        """Update a claim's certainty tier and record the transition.

        Returns dict with the updated claim info and history entry.
        """
        claim = await self.get_claim(claim_id)
        if claim is None:
            return {"error": "not_found"}

        previous_tier = claim.certainty_tier
        if previous_tier == new_tier:
            return {"error": "no_change", "current_tier": new_tier.value}

        # Record history
        history = SurveyClaimHistory(
            claim_id=claim_id,
            previous_tier=previous_tier,
            new_tier=new_tier,
            changed_by=changed_by,
        )
        self._session.add(history)

        # Update claim
        claim.certainty_tier = new_tier
        await self._session.flush()

        logger.info(
            "Certainty tier updated: claim=%s, %s -> %s, by=%s",
            claim_id,
            previous_tier,
            new_tier,
            changed_by,
        )
        return {
            "claim_id": str(claim_id),
            "previous_tier": previous_tier.value,
            "new_tier": new_tier.value,
            "changed_by": str(changed_by),
        }

    async def query_claims(
        self,
        engagement_id: uuid.UUID,
        *,
        certainty_tier: CertaintyTier | None = None,
        probe_type: ProbeType | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Query claims with optional filters and pagination."""
        base_filter = [SurveyClaim.engagement_id == engagement_id]
        if certainty_tier is not None:
            base_filter.append(SurveyClaim.certainty_tier == certainty_tier)
        if probe_type is not None:
            base_filter.append(SurveyClaim.probe_type == probe_type)

        # Total count
        count_stmt = select(sa_func.count()).select_from(SurveyClaim).where(*base_filter)
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar() or 0

        # Paginated items
        query = (
            select(SurveyClaim).where(*base_filter).order_by(SurveyClaim.created_at.desc()).limit(limit).offset(offset)
        )
        result = await self._session.execute(query)
        claims = result.scalars().all()

        return {
            "items": [
                {
                    "id": str(c.id),
                    "engagement_id": str(c.engagement_id),
                    "session_id": str(c.session_id),
                    "probe_type": c.probe_type.value,
                    "respondent_role": c.respondent_role,
                    "claim_text": c.claim_text,
                    "certainty_tier": c.certainty_tier.value,
                    "proof_expectation": c.proof_expectation,
                    "created_at": c.created_at.isoformat(),
                }
                for c in claims
            ],
            "total_count": total,
            "limit": limit,
            "offset": offset,
        }

    async def create_shelf_data_request(self, claim_id: uuid.UUID) -> dict[str, Any]:
        """Auto-generate a shelf data request from a SUSPECTED claim's proof_expectation.

        Only valid for claims with certainty_tier=SUSPECTED and a non-empty
        proof_expectation field.
        """
        claim = await self.get_claim(claim_id)
        if claim is None:
            return {"error": "not_found"}

        if claim.certainty_tier != CertaintyTier.SUSPECTED:
            return {"error": "not_suspected", "certainty_tier": claim.certainty_tier.value}

        if not claim.proof_expectation:
            return {"error": "no_proof_expectation"}

        # Create shelf data request
        request = ShelfDataRequest(
            engagement_id=claim.engagement_id,
            title=f"Evidence for claim: {claim.claim_text[:100]}",
            description=claim.proof_expectation,
            status=ShelfRequestStatus.DRAFT,
        )
        self._session.add(request)
        await self._session.flush()

        # Create item linked to the request
        item = ShelfDataRequestItem(
            request_id=request.id,
            category=EvidenceCategory.DOCUMENTS,
            item_name=f"Proof: {claim.proof_expectation[:200]}",
            description=claim.proof_expectation,
        )
        self._session.add(item)
        await self._session.flush()

        logger.info(
            "Shelf data request created from claim: claim=%s, request=%s",
            claim_id,
            request.id,
        )
        return {
            "shelf_data_request_id": str(request.id),
            "claim_id": str(claim_id),
            "engagement_id": str(claim.engagement_id),
            "description": claim.proof_expectation,
        }

    async def get_claim_history(self, claim_id: uuid.UUID) -> list[dict[str, Any]]:
        """Get the tier transition history for a claim."""
        stmt = (
            select(SurveyClaimHistory)
            .where(SurveyClaimHistory.claim_id == claim_id)
            .order_by(SurveyClaimHistory.changed_at.desc())
        )
        result = await self._session.execute(stmt)
        entries = result.scalars().all()

        return [
            {
                "id": str(e.id),
                "claim_id": str(e.claim_id),
                "previous_tier": e.previous_tier.value,
                "new_tier": e.new_tier.value,
                "changed_by": str(e.changed_by),
                "changed_at": e.changed_at.isoformat(),
            }
            for e in entries
        ]
