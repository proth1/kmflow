"""Illumination Planner service for targeted evidence acquisition.

Generates acquisition plans for Dark segments based on missing knowledge
forms. Each missing form maps to an action type (shelf request, persona
probe, or system extraction). Tracks progress per action and per segment.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import (
    IlluminationAction,
    IlluminationActionStatus,
    IlluminationActionType,
)

if TYPE_CHECKING:
    from src.api.services.dark_room_backlog import DarkRoomBacklogService

logger = logging.getLogger(__name__)

# Form number → action type mapping (from technical notes in issue #396)
FORM_ACTION_TYPE_MAP: dict[int, IlluminationActionType] = {
    1: IlluminationActionType.SYSTEM_EXTRACT,   # Activities
    2: IlluminationActionType.SYSTEM_EXTRACT,   # Sequences
    3: IlluminationActionType.SYSTEM_EXTRACT,   # Dependencies
    4: IlluminationActionType.SHELF_REQUEST,    # Inputs/Outputs
    5: IlluminationActionType.SHELF_REQUEST,    # Rules
    6: IlluminationActionType.PERSONA_PROBE,    # Personas
    7: IlluminationActionType.SHELF_REQUEST,    # Controls
    8: IlluminationActionType.SHELF_REQUEST,    # Evidence
    9: IlluminationActionType.SHELF_REQUEST,    # Uncertainty
}


class IlluminationPlannerService:
    """Generates and manages illumination plans for Dark segments."""

    def __init__(
        self,
        session: AsyncSession,
        backlog_service: DarkRoomBacklogService | None = None,
    ) -> None:
        self._session = session
        self._backlog = backlog_service

    async def create_illumination_plan(
        self,
        engagement_id: str,
        element_id: str,
        element_name: str,
        missing_forms: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Create acquisition actions for a Dark segment's missing forms.

        Returns list of created action dicts.
        """
        eng_uuid = uuid.UUID(engagement_id)
        actions: list[dict[str, Any]] = []
        records: list[IlluminationAction] = []

        for form_info in missing_forms:
            form_num = form_info["form_number"]
            form_name = form_info["form_name"]
            action_type = FORM_ACTION_TYPE_MAP.get(form_num, IlluminationActionType.SHELF_REQUEST)

            action_id = uuid.uuid4()
            record = IlluminationAction(
                id=action_id,
                engagement_id=eng_uuid,
                element_id=element_id,
                element_name=element_name,
                action_type=action_type,
                target_knowledge_form=form_num,
                target_form_name=form_name,
                status=IlluminationActionStatus.PENDING,
            )
            records.append(record)

            actions.append({
                "id": str(action_id),
                "element_id": element_id,
                "element_name": element_name,
                "action_type": action_type,
                "target_knowledge_form": form_num,
                "target_form_name": form_name,
                "status": IlluminationActionStatus.PENDING,
                "linked_item_id": None,
            })

        self._session.add_all(records)
        await self._session.flush()
        return actions

    async def get_progress(
        self, engagement_id: str, element_id: str
    ) -> dict[str, Any]:
        """Get illumination progress for a specific segment.

        Returns total/completed/pending counts and per-action status.
        """
        eng_uuid = uuid.UUID(engagement_id)

        result = await self._session.execute(
            select(IlluminationAction)
            .where(
                IlluminationAction.engagement_id == eng_uuid,
                IlluminationAction.element_id == element_id,
            )
            .order_by(IlluminationAction.target_knowledge_form)
        )
        rows = list(result.scalars().all())

        if not rows:
            return {
                "engagement_id": engagement_id,
                "element_id": element_id,
                "total_actions": 0,
                "completed_actions": 0,
                "pending_actions": 0,
                "in_progress_actions": 0,
                "all_complete": False,
                "actions": [],
            }

        actions = []
        completed = 0
        pending = 0
        in_progress = 0

        for row in rows:
            status = row.status
            if status == IlluminationActionStatus.COMPLETE:
                completed += 1
            elif status == IlluminationActionStatus.IN_PROGRESS:
                in_progress += 1
            else:
                pending += 1

            actions.append({
                "id": str(row.id),
                "action_type": row.action_type,
                "target_knowledge_form": row.target_knowledge_form,
                "target_form_name": row.target_form_name,
                "status": status,
                "linked_item_id": row.linked_item_id,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            })

        total = len(rows)
        return {
            "engagement_id": engagement_id,
            "element_id": element_id,
            "total_actions": total,
            "completed_actions": completed,
            "pending_actions": pending,
            "in_progress_actions": in_progress,
            "all_complete": completed == total,
            "actions": actions,
        }

    async def update_action_status(
        self,
        action_id: str,
        new_status: IlluminationActionStatus,
        linked_item_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Update the status of an illumination action.

        Returns the updated action dict, or None if not found.
        """
        action_uuid = uuid.UUID(action_id)
        result = await self._session.execute(
            select(IlluminationAction).where(IlluminationAction.id == action_uuid)
        )
        action = result.scalar_one_or_none()
        if not action:
            return None

        action.status = new_status
        if linked_item_id is not None:
            action.linked_item_id = linked_item_id
        if new_status == IlluminationActionStatus.COMPLETE:
            action.completed_at = func.now()

        await self._session.flush()
        return {
            "id": str(action.id),
            "element_id": action.element_id,
            "action_type": action.action_type,
            "target_knowledge_form": action.target_knowledge_form,
            "status": action.status,
            "linked_item_id": action.linked_item_id,
        }

    async def check_segment_completion(
        self, engagement_id: str, element_id: str
    ) -> dict[str, Any]:
        """Check if all actions for a segment are complete.

        Returns completion status and whether confidence recalculation
        should be triggered.
        """
        progress = await self.get_progress(engagement_id, element_id)
        return {
            "element_id": element_id,
            "all_complete": progress["all_complete"],
            "total_actions": progress["total_actions"],
            "completed_actions": progress["completed_actions"],
            "should_recalculate": progress["all_complete"] and progress["total_actions"] > 0,
        }
