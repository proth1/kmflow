"""Service for integrating epistemic actions with shelf data requests.

Auto-creates ShelfDataRequestItems from planner recommendations and
tracks follow-through rate (target: >50%).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import (
    EpistemicAction,
    EvidenceCategory,
    ShelfDataRequest,
    ShelfDataRequestItem,
    ShelfRequestItemPriority,
    ShelfRequestItemSource,
)

logger = logging.getLogger(__name__)

# Mapping from recommended_evidence_category to EvidenceCategory enum
CATEGORY_MAP: dict[str, EvidenceCategory] = {
    "documents": EvidenceCategory.DOCUMENTS,
    "bpm_process_models": EvidenceCategory.BPM_PROCESS_MODELS,
    "controls_evidence": EvidenceCategory.CONTROLS_EVIDENCE,
    "regulatory_policy": EvidenceCategory.REGULATORY_POLICY,
    "structured_data": EvidenceCategory.STRUCTURED_DATA,
    "domain_communications": EvidenceCategory.DOMAIN_COMMUNICATIONS,
}

PRIORITY_MAP: dict[str, ShelfRequestItemPriority] = {
    "high": ShelfRequestItemPriority.HIGH,
    "medium": ShelfRequestItemPriority.MEDIUM,
    "low": ShelfRequestItemPriority.LOW,
}


class ShelfIntegrationService:
    """Connects epistemic planner output to shelf data request workflow."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def auto_create_shelf_items(
        self,
        engagement_id: uuid.UUID,
        epistemic_actions: list[EpistemicAction],
        shelf_request_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """Auto-create shelf request items from epistemic action recommendations.

        Args:
            engagement_id: The engagement ID for context.
            epistemic_actions: Actions that recommend evidence collection.
            shelf_request_id: The parent shelf request to add items to.

        Returns:
            List of created item summaries.
        """
        created_items: list[dict[str, Any]] = []

        for action in epistemic_actions:
            category = CATEGORY_MAP.get(
                action.recommended_evidence_category,
                EvidenceCategory.DOCUMENTS,
            )
            priority = PRIORITY_MAP.get(action.priority, ShelfRequestItemPriority.MEDIUM)

            item = ShelfDataRequestItem(
                request_id=shelf_request_id,
                category=category,
                item_name=f"[Planner] {action.evidence_gap_description[:480]}",
                description=(
                    f"Auto-generated from epistemic planner. "
                    f"Target: {action.target_element_name}, "
                    f"expected uplift: {action.estimated_confidence_uplift:.2f}"
                ),
                priority=priority,
                epistemic_action_id=action.id,
                source=ShelfRequestItemSource.PLANNER,
            )
            self._session.add(item)
            created_items.append(
                {
                    "epistemic_action_id": str(action.id),
                    "item_name": item.item_name,
                    "category": category.value,
                    "priority": priority.value,
                    "source": ShelfRequestItemSource.PLANNER.value,
                }
            )

        if created_items:
            await self._session.flush()

        return created_items

    async def get_follow_through_rate(
        self,
        engagement_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Compute follow-through rate for an engagement.

        Follow-through rate = items with epistemic_action_id / total epistemic actions.
        Target: >50%.

        Args:
            engagement_id: The engagement to compute for.

        Returns:
            Dict with rate, counts, and target assessment.
        """
        from src.core.models import SimulationScenario

        total_result = await self._session.execute(
            select(func.count(EpistemicAction.id))
            .join(SimulationScenario, EpistemicAction.scenario_id == SimulationScenario.id)
            .where(SimulationScenario.engagement_id == engagement_id)
        )
        total_actions = total_result.scalar() or 0

        # Count shelf request items with planner source for this engagement
        linked_result = await self._session.execute(
            select(func.count(ShelfDataRequestItem.id))
            .join(ShelfDataRequest, ShelfDataRequestItem.request_id == ShelfDataRequest.id)
            .where(
                ShelfDataRequest.engagement_id == engagement_id,
                ShelfDataRequestItem.source == ShelfRequestItemSource.PLANNER,
            )
        )
        linked_items = linked_result.scalar() or 0

        rate = (linked_items / total_actions * 100) if total_actions > 0 else 0.0
        target = 50.0

        return {
            "engagement_id": str(engagement_id),
            "total_epistemic_actions": total_actions,
            "linked_shelf_items": linked_items,
            "follow_through_rate": round(rate, 1),
            "target_rate": target,
            "meets_target": rate >= target,
        }
