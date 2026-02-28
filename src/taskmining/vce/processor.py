"""VCE event processing: persist and batch-validate visual context events.

Accepts agent-uploaded VCE metadata, validates required fields, and
creates VisualContextEvent database records. Batch processing returns
per-event accept/reject accounting for agent acknowledgement.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.taskmining import ScreenStateClass, VCETriggerReason, VisualContextEvent

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = {
    "engagement_id",
    "timestamp",
    "screen_state_class",
    "confidence",
    "trigger_reason",
    "application_name",
    "dwell_ms",
}

_VALID_SCREEN_STATE_VALUES = {v.value for v in ScreenStateClass}
_VALID_TRIGGER_VALUES = {v.value for v in VCETriggerReason}


def _validate_event(event_data: dict[str, Any]) -> str | None:
    """Return an error string if event_data is invalid, else None."""
    missing = _REQUIRED_FIELDS - event_data.keys()
    if missing:
        return f"Missing required fields: {sorted(missing)}"

    if event_data["screen_state_class"] not in _VALID_SCREEN_STATE_VALUES:
        return f"Invalid screen_state_class: {event_data['screen_state_class']!r}"

    if event_data["trigger_reason"] not in _VALID_TRIGGER_VALUES:
        return f"Invalid trigger_reason: {event_data['trigger_reason']!r}"

    confidence = event_data.get("confidence")
    if not isinstance(confidence, (int, float)) or not (0.0 <= float(confidence) <= 1.0):
        return f"confidence must be a float in [0.0, 1.0], got {confidence!r}"

    dwell_ms = event_data.get("dwell_ms")
    if not isinstance(dwell_ms, int) or dwell_ms < 0:
        return f"dwell_ms must be a non-negative integer, got {dwell_ms!r}"

    return None


async def process_vce_event(session: AsyncSession, event_data: dict[str, Any]) -> VisualContextEvent:
    """Persist a single VCE metadata record.

    Args:
        session: Async database session.
        event_data: Raw VCE payload dict from the agent.

    Returns:
        The persisted VisualContextEvent ORM record.

    Raises:
        ValueError: If required fields are missing or invalid.
    """
    error = _validate_event(event_data)
    if error:
        raise ValueError(error)

    # Parse timestamp — accept ISO string or datetime
    ts = event_data["timestamp"]
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)

    # Parse UUIDs — accept strings or UUID objects
    def _uuid(val: Any) -> UUID:
        return UUID(str(val)) if not isinstance(val, UUID) else val

    vce = VisualContextEvent(
        id=uuid.uuid4(),
        engagement_id=_uuid(event_data["engagement_id"]),
        session_id=_uuid(event_data["session_id"]) if event_data.get("session_id") else None,
        agent_id=_uuid(event_data["agent_id"]) if event_data.get("agent_id") else None,
        timestamp=ts,
        screen_state_class=ScreenStateClass(event_data["screen_state_class"]),
        system_guess=event_data.get("system_guess"),
        module_guess=event_data.get("module_guess"),
        confidence=float(event_data["confidence"]),
        trigger_reason=VCETriggerReason(event_data["trigger_reason"]),
        sensitivity_flags=event_data.get("sensitivity_flags"),
        application_name=event_data["application_name"],
        window_title_redacted=event_data.get("window_title_redacted"),
        dwell_ms=int(event_data["dwell_ms"]),
        interaction_intensity=event_data.get("interaction_intensity"),
        snapshot_ref=event_data.get("snapshot_ref"),
        ocr_text_redacted=event_data.get("ocr_text_redacted"),
        classification_method=event_data.get("classification_method"),
    )
    session.add(vce)
    await session.flush()

    logger.debug(
        "VCE persisted: id=%s engagement=%s screen_state=%s trigger=%s",
        vce.id,
        vce.engagement_id,
        vce.screen_state_class,
        vce.trigger_reason,
    )
    return vce


async def process_vce_batch(
    session: AsyncSession,
    events: list[dict[str, Any]],
) -> dict[str, int]:
    """Batch-process a list of VCE event dicts.

    Each event is validated and persisted independently so a single bad
    record does not block the rest of the batch.

    Args:
        session: Async database session.
        events: List of raw VCE payload dicts.

    Returns:
        Dict with "accepted" and "rejected" counts.
    """
    accepted = 0
    rejected = 0

    for event_data in events:
        try:
            await process_vce_event(session, event_data)
            accepted += 1
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("VCE event rejected: %s | data_keys=%s", exc, list(event_data.keys()))
            rejected += 1

    logger.info("VCE batch complete: accepted=%d rejected=%d", accepted, rejected)
    return {"accepted": accepted, "rejected": rejected}
