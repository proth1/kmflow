"""GDPR compliance service (Story #317).

Centralizes data classification access control, retention policy enforcement,
processing activity tracking, and compliance reporting. Used by routes to
enforce GDPR requirements at the API layer.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.evidence import DataClassification, EvidenceItem, ValidationStatus
from src.core.models.gdpr import (
    DataProcessingActivity,
    LawfulBasis,
    RetentionAction,
    RetentionPolicy,
)

logger = logging.getLogger(__name__)

# Classification hierarchy for access control: higher index = more restricted
CLASSIFICATION_HIERARCHY = {
    DataClassification.PUBLIC: 0,
    DataClassification.INTERNAL: 1,
    DataClassification.CONFIDENTIAL: 2,
    DataClassification.RESTRICTED: 3,
}


class GdprComplianceService:
    """Manages GDPR compliance operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Classification Access Control ──────────────────────────────────

    def check_classification_access(
        self,
        classification: DataClassification,
        has_restricted_access: bool,
    ) -> bool:
        """Check if a user can access evidence of a given classification.

        Restricted evidence requires explicit authorization. All other
        classification levels are accessible to any authenticated user
        with engagement access.
        """
        if classification == DataClassification.RESTRICTED:
            return has_restricted_access
        return True

    # ── Retention Policy ──────────────────────────────────────────────

    async def get_retention_policy(
        self, engagement_id: uuid.UUID
    ) -> RetentionPolicy | None:
        """Get the retention policy for an engagement."""
        stmt = select(RetentionPolicy).where(
            RetentionPolicy.engagement_id == engagement_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def set_retention_policy(
        self,
        engagement_id: uuid.UUID,
        retention_days: int,
        action: RetentionAction = RetentionAction.ARCHIVE,
        created_by: uuid.UUID | None = None,
    ) -> RetentionPolicy:
        """Set or update the retention policy for an engagement."""
        existing = await self.get_retention_policy(engagement_id)
        if existing:
            existing.retention_days = retention_days
            existing.action = action
            await self._session.flush()
            return existing

        policy = RetentionPolicy(
            engagement_id=engagement_id,
            retention_days=retention_days,
            action=action,
            created_by=created_by,
        )
        self._session.add(policy)
        await self._session.flush()
        return policy

    async def enforce_retention(
        self, engagement_id: uuid.UUID
    ) -> dict[str, Any]:
        """Enforce retention policy for an engagement.

        Archives or deletes evidence items older than the retention period.
        Returns a summary of affected items.
        """
        policy = await self.get_retention_policy(engagement_id)
        if policy is None:
            return {"affected_count": 0, "message": "No retention policy configured"}

        cutoff = datetime.now(UTC) - timedelta(days=policy.retention_days)

        # Find expired evidence items
        stmt = (
            select(EvidenceItem)
            .where(
                EvidenceItem.engagement_id == engagement_id,
                EvidenceItem.created_at < cutoff,
                EvidenceItem.validation_status != ValidationStatus.ARCHIVED,
            )
        )
        result = await self._session.execute(stmt)
        expired_items = result.scalars().all()

        affected_ids = []
        for item in expired_items:
            if policy.action == RetentionAction.ARCHIVE:
                item.validation_status = ValidationStatus.ARCHIVED
            elif policy.action == RetentionAction.DELETE:
                await self._session.delete(item)
            affected_ids.append(str(item.id))

        if expired_items:
            await self._session.flush()

        logger.info(
            "Retention enforcement: engagement=%s, action=%s, affected=%d",
            engagement_id, policy.action, len(affected_ids),
        )
        return {
            "engagement_id": str(engagement_id),
            "action": policy.action.value,
            "retention_days": policy.retention_days,
            "affected_count": len(affected_ids),
            "affected_item_ids": affected_ids,
        }

    # ── Processing Activity (ROPA) ────────────────────────────────────

    async def create_processing_activity(
        self,
        *,
        engagement_id: uuid.UUID,
        name: str,
        lawful_basis: LawfulBasis,
        article_6_basis: str,
        created_by: uuid.UUID,
        description: str | None = None,
    ) -> DataProcessingActivity:
        """Record a data processing activity with its GDPR lawful basis."""
        activity = DataProcessingActivity(
            engagement_id=engagement_id,
            name=name,
            description=description,
            lawful_basis=lawful_basis,
            article_6_basis=article_6_basis,
            created_by=created_by,
        )
        self._session.add(activity)
        await self._session.flush()

        logger.info(
            "Processing activity created: name=%s, basis=%s, engagement=%s",
            name, lawful_basis, engagement_id,
        )
        return activity

    async def query_processing_activities(
        self,
        engagement_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List processing activities for an engagement."""
        count_stmt = (
            select(sa_func.count())
            .select_from(DataProcessingActivity)
            .where(DataProcessingActivity.engagement_id == engagement_id)
        )
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar() or 0

        query = (
            select(DataProcessingActivity)
            .where(DataProcessingActivity.engagement_id == engagement_id)
            .order_by(DataProcessingActivity.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(query)
        activities = result.scalars().all()

        return {
            "items": [
                {
                    "id": str(a.id),
                    "engagement_id": str(a.engagement_id),
                    "name": a.name,
                    "description": a.description,
                    "lawful_basis": a.lawful_basis.value,
                    "article_6_basis": a.article_6_basis,
                    "created_at": a.created_at.isoformat(),
                    "created_by": str(a.created_by),
                }
                for a in activities
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    async def get_compliance_report(
        self, engagement_id: uuid.UUID
    ) -> dict[str, Any]:
        """Generate a GDPR compliance report for an engagement.

        Identifies processing activities without lawful basis and
        evidence items without classification.
        """
        # Count activities per lawful basis
        basis_stmt = (
            select(
                DataProcessingActivity.lawful_basis,
                sa_func.count().label("count"),
            )
            .where(DataProcessingActivity.engagement_id == engagement_id)
            .group_by(DataProcessingActivity.lawful_basis)
        )
        basis_result = await self._session.execute(basis_stmt)
        basis_counts = {row.lawful_basis.value: row.count for row in basis_result}

        # Count evidence by classification
        class_stmt = (
            select(
                EvidenceItem.classification,
                sa_func.count().label("count"),
            )
            .where(EvidenceItem.engagement_id == engagement_id)
            .group_by(EvidenceItem.classification)
        )
        class_result = await self._session.execute(class_stmt)
        classification_counts = {
            row.classification.value: row.count for row in class_result
        }

        # Total activities
        total_stmt = (
            select(sa_func.count())
            .select_from(DataProcessingActivity)
            .where(DataProcessingActivity.engagement_id == engagement_id)
        )
        total_result = await self._session.execute(total_stmt)
        total_activities = total_result.scalar() or 0

        return {
            "engagement_id": str(engagement_id),
            "total_processing_activities": total_activities,
            "activities_by_lawful_basis": basis_counts,
            "evidence_by_classification": classification_counts,
            "compliant": total_activities > 0,
        }
