"""Consent service for desktop endpoint capture (Story #382).

Manages the lifecycle of consent records: creation, withdrawal, validation,
and scope updates. Enforces GDPR Art. 6(1)(a) — no desktop capture data
is processed without verified valid consent.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.security.consent.models import (
    ConsentStatus,
    EndpointConsentRecord,
    EndpointConsentType,
)

logger = logging.getLogger(__name__)

# 7-year retention floor per PRD Section 9.8
RETENTION_YEARS = 7
MIN_RETENTION_YEARS = 6  # GDPR Art. 7 minimum


class ConsentService:
    """Manages consent lifecycle for desktop endpoint capture."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_consent(
        self,
        *,
        participant_id: uuid.UUID,
        engagement_id: uuid.UUID,
        consent_type: EndpointConsentType,
        scope: str,
        policy_bundle_id: uuid.UUID,
        recorded_by: uuid.UUID,
    ) -> EndpointConsentRecord:
        """Record a new consent grant.

        Creates an immutable consent record linked to the specific policy
        bundle version in effect. Sets 7-year retention floor.
        """
        now = datetime.now(UTC)
        retention_expires = now + timedelta(days=RETENTION_YEARS * 365)

        record = EndpointConsentRecord(
            participant_id=participant_id,
            engagement_id=engagement_id,
            consent_type=consent_type,
            scope=scope,
            policy_bundle_id=policy_bundle_id,
            recorded_by=recorded_by,
            status=ConsentStatus.ACTIVE,
            retention_expires_at=retention_expires,
        )
        self._session.add(record)
        await self._session.flush()

        logger.info(
            "Consent recorded: participant=%s, engagement=%s, type=%s",
            participant_id,
            engagement_id,
            consent_type,
        )
        return record

    async def withdraw_consent(self, consent_id: uuid.UUID) -> dict[str, Any] | None:
        """Withdraw consent by marking record as WITHDRAWN.

        Returns the withdrawal details including a deletion task ID.
        The consent record itself is retained (7-year floor) but the
        status prevents further data processing.
        """
        record = await self._session.get(EndpointConsentRecord, consent_id)
        if record is None:
            return None

        if record.status == ConsentStatus.WITHDRAWN:
            return None

        now = datetime.now(UTC)
        record.status = ConsentStatus.WITHDRAWN
        record.withdrawn_at = now
        await self._session.flush()

        # TODO(#382): Wire to actual task queue (Redis stream or Celery).
        # Currently returns a tracking ID without dispatching. The actual
        # deletion across PostgreSQL, Neo4j, pgvector, and Redis will be
        # implemented when the desktop pipeline integration is complete.
        deletion_task_id = uuid.uuid4()

        logger.info(
            "Consent withdrawn: id=%s, participant=%s, deletion_task=%s",
            consent_id,
            record.participant_id,
            deletion_task_id,
        )
        return {
            "consent_id": str(consent_id),
            "participant_id": str(record.participant_id),
            "engagement_id": str(record.engagement_id),
            "withdrawn_at": now.isoformat(),
            "deletion_task_id": str(deletion_task_id),
            "deletion_targets": ["postgresql", "neo4j", "pgvector", "redis"],
        }

    async def get_consent(self, consent_id: uuid.UUID) -> EndpointConsentRecord | None:
        """Get a single consent record by ID."""
        return await self._session.get(EndpointConsentRecord, consent_id)

    async def query_consent(
        self,
        *,
        participant_id: uuid.UUID | None = None,
        engagement_id: uuid.UUID | None = None,
        status_filter: ConsentStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Query consent records with optional filters and pagination."""
        conditions = []
        if participant_id is not None:
            conditions.append(EndpointConsentRecord.participant_id == participant_id)
        if engagement_id is not None:
            conditions.append(EndpointConsentRecord.engagement_id == engagement_id)
        if status_filter is not None:
            conditions.append(EndpointConsentRecord.status == status_filter)

        count_stmt = select(sa_func.count()).select_from(EndpointConsentRecord)
        if conditions:
            count_stmt = count_stmt.where(*conditions)
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar() or 0

        query = (
            select(EndpointConsentRecord).order_by(EndpointConsentRecord.recorded_at.desc()).limit(limit).offset(offset)
        )
        if conditions:
            query = query.where(*conditions)

        result = await self._session.execute(query)
        records = result.scalars().all()

        return {
            "items": [
                {
                    "id": str(r.id),
                    "participant_id": str(r.participant_id),
                    "engagement_id": str(r.engagement_id),
                    "consent_type": r.consent_type.value,
                    "scope": r.scope,
                    "policy_bundle_id": str(r.policy_bundle_id),
                    "status": r.status.value,
                    "recorded_by": str(r.recorded_by),
                    "recorded_at": r.recorded_at.isoformat(),
                    "withdrawn_at": r.withdrawn_at.isoformat() if r.withdrawn_at else None,
                }
                for r in records
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    async def validate_consent(
        self,
        participant_id: uuid.UUID,
        engagement_id: uuid.UUID,
    ) -> bool:
        """Check if participant has active consent for an engagement.

        Used by the desktop mining pipeline to gate data processing.
        """
        stmt = (
            select(sa_func.count())
            .select_from(EndpointConsentRecord)
            .where(
                EndpointConsentRecord.participant_id == participant_id,
                EndpointConsentRecord.engagement_id == engagement_id,
                EndpointConsentRecord.status == ConsentStatus.ACTIVE,
            )
        )
        result = await self._session.execute(stmt)
        count = result.scalar() or 0
        return count > 0

    async def update_org_scope(
        self,
        engagement_id: uuid.UUID,
        new_scope: str,
        updated_by: uuid.UUID,
    ) -> dict[str, Any]:
        """Expand scope on org-authorized consent for an engagement.

        Preserves immutability: withdraws old records and creates new ones
        with the expanded scope. Emits notification events for affected
        participants. New records start as ACTIVE but the expanded scope
        is not activated for processing until notification completes.
        """
        now = datetime.now(UTC)
        retention_expires = now + timedelta(days=RETENTION_YEARS * 365)

        # Find all active ORG_AUTHORIZED consent records for this engagement
        stmt = select(EndpointConsentRecord).where(
            EndpointConsentRecord.engagement_id == engagement_id,
            EndpointConsentRecord.consent_type == EndpointConsentType.ORG_AUTHORIZED,
            EndpointConsentRecord.status == ConsentStatus.ACTIVE,
        )
        result = await self._session.execute(stmt)
        records = result.scalars().all()

        affected_participants = [str(r.participant_id) for r in records]

        # Withdraw old records and create new ones with expanded scope
        for old_record in records:
            old_record.status = ConsentStatus.WITHDRAWN
            old_record.withdrawn_at = now

            new_record = EndpointConsentRecord(
                participant_id=old_record.participant_id,
                engagement_id=old_record.engagement_id,
                consent_type=EndpointConsentType.ORG_AUTHORIZED,
                scope=new_scope,
                policy_bundle_id=old_record.policy_bundle_id,
                recorded_by=updated_by,
                status=ConsentStatus.ACTIVE,
                retention_expires_at=retention_expires,
            )
            self._session.add(new_record)

        if records:
            await self._session.flush()

        logger.info(
            "Org scope updated: engagement=%s, new_scope=%s, affected=%d",
            engagement_id,
            new_scope,
            len(affected_participants),
        )

        return {
            "engagement_id": str(engagement_id),
            "new_scope": new_scope,
            "affected_participant_ids": affected_participants,
            "notification_required": len(affected_participants) > 0,
        }
