"""Event processor for task mining data.

Receives raw event batches from agents, applies Layer 3 PII filtering,
validates events, and routes them to the Redis stream for worker processing.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.taskmining import (
    PIIQuarantine,
    PIIType,
    QuarantineStatus,
    TaskMiningEvent,
    TaskMiningSession,
)
from src.core.redis import TASK_MINING_STREAM, stream_add
from src.taskmining.pii.filter import FilterResult, PIIDetection, filter_event, redact_text

logger = logging.getLogger(__name__)

PII_QUARANTINE_HOURS = 24


async def process_event_batch(
    session: AsyncSession,
    redis_client: aioredis.Redis,
    session_id: uuid.UUID,
    engagement_id: uuid.UUID,
    events: list[dict[str, Any]],
    max_stream_len: int = 10000,
) -> dict[str, int]:
    """Process a batch of raw events from a desktop agent.

    For each event:
    1. Check idempotency key for duplicates
    2. Run Layer 3 PII filter
    3. If PII detected with high confidence: quarantine
    4. Otherwise: persist to database and push to Redis stream

    Args:
        session: Database session.
        redis_client: Redis client for stream operations.
        session_id: The capture session ID.
        engagement_id: The engagement ID.
        events: List of event dicts from the agent.
        max_stream_len: Max Redis stream length.

    Returns:
        Dict with counts: accepted, rejected, duplicates, pii_quarantined.
    """
    accepted = 0
    rejected = 0
    duplicates = 0
    pii_quarantined = 0

    for event_data in events:
        try:
            # 1. Idempotency check
            idempotency_key = event_data.get("idempotency_key")
            if idempotency_key:
                existing = await session.execute(
                    select(TaskMiningEvent.id).where(
                        TaskMiningEvent.idempotency_key == idempotency_key
                    ).limit(1)
                )
                if existing.scalar_one_or_none() is not None:
                    duplicates += 1
                    continue

            # 2. Layer 3 PII filter
            filter_result = filter_event(event_data, redact=True)

            # 3. Quarantine if high-confidence PII detected
            if filter_result.quarantine_recommended:
                await _quarantine_event(
                    session, engagement_id, event_data, filter_result.detections
                )
                pii_quarantined += 1
                continue

            # 4. Persist clean event
            event = TaskMiningEvent(
                session_id=session_id,
                engagement_id=engagement_id,
                event_type=filter_result.clean_data.get("event_type", "app_switch"),
                timestamp=event_data.get("timestamp", datetime.now(UTC)),
                application_name=filter_result.clean_data.get("application_name"),
                window_title=filter_result.clean_data.get("window_title"),
                event_data=filter_result.clean_data.get("event_data"),
                idempotency_key=idempotency_key,
                pii_filtered=filter_result.has_pii,
            )
            session.add(event)
            accepted += 1

            # 5. Push to Redis stream for worker processing
            await stream_add(
                redis_client,
                TASK_MINING_STREAM,
                {
                    "task_type": "aggregate",
                    "event_type": event_data.get("event_type"),
                    "session_id": str(session_id),
                    "engagement_id": str(engagement_id),
                    "application_name": filter_result.clean_data.get("application_name"),
                    "window_title": filter_result.clean_data.get("window_title"),
                    "timestamp": str(event_data.get("timestamp")),
                },
                max_len=max_stream_len,
            )

        except Exception:
            logger.exception("Failed to process event")
            rejected += 1

    # Update session event count
    if accepted > 0:
        mining_session = await session.get(TaskMiningSession, session_id)
        if mining_session:
            mining_session.event_count += accepted
            mining_session.pii_detections += pii_quarantined

    await session.flush()

    return {
        "accepted": accepted,
        "rejected": rejected,
        "duplicates": duplicates,
        "pii_quarantined": pii_quarantined,
    }


def _redact_event_data(event_data: dict[str, Any]) -> dict[str, Any]:
    """Redact PII from event data before quarantine storage.

    Quarantine records store redacted copies — never raw PII.
    This ensures no plaintext PII persists in the database even
    during the 24h quarantine review window.
    """
    redacted = {}
    for key, value in event_data.items():
        if isinstance(value, str):
            redacted[key] = redact_text(value)
        elif isinstance(value, dict):
            redacted[key] = _redact_event_data(value)
        else:
            redacted[key] = value
    return redacted


async def _quarantine_event(
    session: AsyncSession,
    engagement_id: uuid.UUID,
    event_data: dict[str, Any],
    detections: list[PIIDetection],
) -> None:
    """Create a quarantine record for a PII-flagged event.

    The original event data is redacted before storage — quarantine
    records never contain plaintext PII. The record preserves metadata
    (PII type, field, confidence) for review decisions.
    """
    # Use the highest-confidence detection as the primary PII type
    primary = max(detections, key=lambda d: d.confidence)

    quarantine = PIIQuarantine(
        engagement_id=engagement_id,
        original_event_data=_redact_event_data(event_data),
        pii_type=primary.pii_type,
        pii_field=primary.field_name,
        detection_confidence=primary.confidence,
        status=QuarantineStatus.PENDING_REVIEW,
        auto_delete_at=datetime.now(UTC) + timedelta(hours=PII_QUARANTINE_HOURS),
    )
    session.add(quarantine)

    logger.info(
        "Event quarantined: pii_type=%s field=%s confidence=%.2f",
        primary.pii_type,
        primary.field_name,
        primary.confidence,
    )
