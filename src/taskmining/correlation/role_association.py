"""Role association: aggregate unlinked events to role cohorts.

When deterministic and assisted passes cannot link an event to a specific case,
the event is attributed to its performer role.  This preserves the time spent
(endpoint time) in aggregate reporting even when the work cannot be traced to
a particular ticket.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.canonical_event import CanonicalActivityEvent
from src.core.models.correlation import CaseLinkEdge

logger = logging.getLogger(__name__)

# Synthetic case_id prefix used for role aggregates so they remain distinct
# from real case IDs and are easy to filter in queries.
ROLE_AGGREGATE_PREFIX = "ROLE_AGGREGATE"


class RoleAssociator:
    """Aggregates unlinked events to a role-cohort pseudo-case."""

    async def associate_unlinked(
        self,
        session: AsyncSession,
        engagement_id: uuid.UUID,
    ) -> int:
        """Create role-aggregate CaseLinkEdge records for events without a link.

        Fetches all canonical events for the engagement that have no entry in
        case_link_edges, then groups them by performer_role_ref (falling back to
        "unknown_role" when null).  One CaseLinkEdge per (event, role) is created
        with method='role_aggregate' and confidence=0.0.

        Args:
            session: Async database session.
            engagement_id: Engagement to process.

        Returns:
            Count of CaseLinkEdge records created.
        """
        # IDs of events that already have a link
        linked_subq = select(CaseLinkEdge.event_id).where(
            CaseLinkEdge.engagement_id == engagement_id
        )

        # Events with no link at all
        stmt = select(CanonicalActivityEvent).where(
            CanonicalActivityEvent.engagement_id == engagement_id,
            CanonicalActivityEvent.id.not_in(linked_subq),
        )
        result = await session.execute(stmt)
        unlinked_events = list(result.scalars().all())

        if not unlinked_events:
            logger.info(
                "RoleAssociator: no unlinked events for engagement %s", engagement_id
            )
            return 0

        edges: list[CaseLinkEdge] = []
        for event in unlinked_events:
            role = event.performer_role_ref or "unknown_role"
            synthetic_case_id = f"{ROLE_AGGREGATE_PREFIX}:{role}"

            edge = CaseLinkEdge(
                id=uuid.uuid4(),
                engagement_id=engagement_id,
                event_id=event.id,
                case_id=synthetic_case_id,
                method="role_aggregate",
                confidence=0.0,
                explainability={
                    "role": role,
                    "reason": "no_deterministic_or_assisted_match",
                },
            )
            session.add(edge)
            edges.append(edge)

        logger.info(
            "RoleAssociator: associated %d unlinked events to role cohorts for engagement %s",
            len(edges),
            engagement_id,
        )
        return len(edges)
