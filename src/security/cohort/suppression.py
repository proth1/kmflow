"""Cohort suppression service for analytics privacy (Story #391).

Enforces minimum cohort size thresholds. When a group being analyzed
falls below the configured minimum, individual-level data is suppressed
and replaced with a suppression notice. The threshold is configurable
per engagement or globally via platform settings.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.models.audit import AuditAction, AuditLog
from src.core.models.engagement import Engagement

logger = logging.getLogger(__name__)


class CohortSuppressionService:
    """Evaluates cohort size and enforces suppression thresholds."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._default_minimum = get_settings().cohort_minimum_size

    async def check_cohort(
        self,
        *,
        engagement_id: uuid.UUID,
        cohort_size: int,
        context: str | None = None,
    ) -> dict[str, Any]:
        """Check whether a cohort meets the minimum size threshold.

        Args:
            engagement_id: The engagement context.
            cohort_size: Number of participants in the group.
            context: Optional description of the analytics context.

        Returns:
            Dict with suppressed flag, reason, and threshold info.
        """
        minimum = await self._get_minimum(engagement_id)

        if cohort_size < minimum:
            logger.info(
                "Cohort suppressed: engagement=%s size=%d minimum=%d context=%s",
                engagement_id,
                cohort_size,
                minimum,
                context,
            )
            return {
                "suppressed": True,
                "reason": "insufficient_cohort_size",
                "cohort_size_observed": cohort_size,
                "cohort_minimum": minimum,
                "data": None,
            }

        return {
            "suppressed": False,
            "reason": None,
            "cohort_size_observed": cohort_size,
            "cohort_minimum": minimum,
        }

    async def check_export(
        self,
        *,
        engagement_id: uuid.UUID,
        cohort_size: int,
        requester: str,
    ) -> dict[str, Any]:
        """Check whether an export is allowed based on cohort size.

        Args:
            engagement_id: The engagement context.
            cohort_size: Number of participants in the exported group.
            requester: Identity of the export requester.

        Returns:
            Dict with allowed flag and block reason if applicable.

        Raises:
            CohortExportBlockedError: If export is blocked due to suppression.
        """
        minimum = await self._get_minimum(engagement_id)

        if cohort_size < minimum:
            logger.warning(
                "Export blocked: engagement=%s cohort=%d minimum=%d requester=%s",
                engagement_id,
                cohort_size,
                minimum,
                requester,
            )
            # Audit log the blocked export attempt
            audit_entry = AuditLog(
                engagement_id=engagement_id,
                action=AuditAction.EXPORT_BLOCKED,
                actor=requester,
                details=(f"Export blocked: cohort size {cohort_size} below minimum {minimum}"),
            )
            self._session.add(audit_entry)
            await self._session.flush()
            raise CohortExportBlockedError(
                cohort_size=cohort_size,
                minimum=minimum,
            )

        return {
            "allowed": True,
            "cohort_size": cohort_size,
            "cohort_minimum": minimum,
        }

    async def configure_engagement(
        self,
        *,
        engagement_id: uuid.UUID,
        minimum_cohort_size: int,
    ) -> dict[str, Any]:
        """Configure the minimum cohort size for an engagement.

        Args:
            engagement_id: The engagement to configure.
            minimum_cohort_size: New minimum cohort size (must be >= 2).

        Returns:
            Updated configuration.

        Raises:
            ValueError: If engagement not found or invalid size.
        """
        if minimum_cohort_size < 2:
            raise ValueError("Minimum cohort size must be at least 2")

        result = await self._session.execute(select(Engagement).where(Engagement.id == engagement_id))
        engagement = result.scalar_one_or_none()
        if engagement is None:
            raise ValueError(f"Engagement {engagement_id} not found")

        engagement.cohort_minimum_size = minimum_cohort_size
        await self._session.flush()
        await self._session.commit()

        return {
            "engagement_id": str(engagement_id),
            "cohort_minimum_size": minimum_cohort_size,
            "updated_at": datetime.now(UTC).isoformat(),
        }

    async def get_engagement_config(
        self,
        *,
        engagement_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Get the cohort configuration for an engagement.

        Args:
            engagement_id: The engagement to query.

        Returns:
            Configuration dict with minimum cohort size.

        Raises:
            ValueError: If engagement not found.
        """
        minimum = await self._get_minimum(engagement_id)
        return {
            "engagement_id": str(engagement_id),
            "cohort_minimum_size": minimum,
            "is_default": minimum == self._default_minimum,
        }

    async def _get_minimum(self, engagement_id: uuid.UUID) -> int:
        """Get the effective minimum cohort size for an engagement.

        Raises:
            ValueError: If the engagement does not exist.
        """
        result = await self._session.execute(
            select(Engagement.id, Engagement.cohort_minimum_size).where(Engagement.id == engagement_id)
        )
        row = result.one_or_none()
        if row is None:
            raise ValueError(f"Engagement {engagement_id} not found")
        override = row[1]
        if override is not None:
            return override
        return self._default_minimum


class CohortExportBlockedError(Exception):
    """Raised when an export is blocked due to cohort suppression."""

    def __init__(self, cohort_size: int, minimum: int) -> None:
        self.cohort_size = cohort_size
        self.minimum = minimum
        super().__init__(f"Export blocked: cohort size {cohort_size} is below minimum threshold {minimum}")
