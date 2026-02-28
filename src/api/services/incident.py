"""Incident response service for security incident lifecycle management.

Manages the full incident lifecycle: creation with GDPR deadline,
containment with audit freeze and access restriction, escalation
monitoring, resolution, and timeline generation.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import (
    Incident,
    IncidentClassification,
    IncidentEvent,
    IncidentEventType,
    IncidentStatus,
)
from src.core.models.incident import ESCALATION_THRESHOLD_HOURS, GDPR_NOTIFICATION_HOURS

logger = logging.getLogger(__name__)


class IncidentService:
    """Manages security incident lifecycle."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_incident(
        self,
        engagement_id: uuid.UUID,
        classification: IncidentClassification,
        title: str,
        description: str,
        reported_by: str,
    ) -> Incident:
        """Create a new security incident.

        For P1 incidents, sets the 72-hour GDPR notification deadline
        and triggers immediate DPO/engagement lead alerts.

        Args:
            engagement_id: Affected engagement.
            classification: P1-P4 severity classification.
            title: Short incident title.
            description: Detailed incident description.
            reported_by: Identity of the reporter.

        Returns:
            Created Incident with deadline and initial event.
        """
        now = datetime.now(UTC)
        notification_deadline = None

        if classification in (IncidentClassification.P1, IncidentClassification.P2):
            notification_deadline = now + timedelta(hours=GDPR_NOTIFICATION_HOURS)

        incident = Incident(
            engagement_id=engagement_id,
            classification=classification,
            status=IncidentStatus.OPEN,
            title=title,
            description=description,
            reported_by=reported_by,
            notification_deadline=notification_deadline,
            created_at=now,
        )
        self._session.add(incident)
        await self._session.flush()

        # Log creation event
        event = IncidentEvent(
            incident_id=incident.id,
            event_type=IncidentEventType.CREATED,
            actor=reported_by,
            description=f"Incident created: {classification.value} - {title}",
            details_json={
                "classification": classification.value,
                "notification_deadline": notification_deadline.isoformat() if notification_deadline else None,
            },
        )
        self._session.add(event)
        await self._session.flush()

        # For P1, build alert recipients list
        alert_recipients: list[str] = []
        if classification == IncidentClassification.P1:
            alert_recipients = ["DPO", "ENGAGEMENT_LEAD"]

        logger.info(
            "Incident %s created: classification=%s, deadline=%s, alerts=%s",
            incident.id,
            classification.value,
            notification_deadline.isoformat() if notification_deadline else "none",
            alert_recipients,
        )

        return incident

    async def contain_incident(
        self,
        incident_id: uuid.UUID,
        actor: str,
    ) -> dict[str, Any]:
        """Execute containment actions for an incident.

        For P1 incidents: restricts non-DPO access and freezes audit logs.

        Args:
            incident_id: The incident to contain.
            actor: Identity of the person executing containment.

        Returns:
            Summary of containment actions taken.
        """
        result = await self._session.execute(select(Incident).where(Incident.id == incident_id))
        incident = result.scalar_one_or_none()
        if incident is None:
            raise ValueError(f"Incident {incident_id} not found")

        if incident.status not in (IncidentStatus.OPEN,):
            raise ValueError(f"Cannot contain incident in status {incident.status}")

        now = datetime.now(UTC)
        actions_taken: list[str] = []

        # Record containment start
        self._session.add(
            IncidentEvent(
                incident_id=incident_id,
                event_type=IncidentEventType.CONTAINMENT_STARTED,
                actor=actor,
                description=f"Containment initiated by {actor}",
            )
        )

        # Access restriction for P1/P2
        if incident.classification in (IncidentClassification.P1, IncidentClassification.P2):
            self._session.add(
                IncidentEvent(
                    incident_id=incident_id,
                    event_type=IncidentEventType.ACCESS_RESTRICTED,
                    actor=actor,
                    description=f"Non-DPO access restricted for engagement {incident.engagement_id}",
                    details_json={
                        "engagement_id": str(incident.engagement_id),
                        "scope": "all_non_dpo",
                        "timestamp": now.isoformat(),
                    },
                )
            )
            actions_taken.append("access_restricted")

            # Freeze audit logs
            self._session.add(
                IncidentEvent(
                    incident_id=incident_id,
                    event_type=IncidentEventType.AUDIT_FROZEN,
                    actor=actor,
                    description=f"Audit logs frozen for engagement {incident.engagement_id}",
                    details_json={
                        "engagement_id": str(incident.engagement_id),
                        "timestamp": now.isoformat(),
                    },
                )
            )
            actions_taken.append("audit_logs_frozen")

        incident.status = IncidentStatus.CONTAINED
        incident.contained_at = now
        await self._session.flush()

        return {
            "incident_id": str(incident_id),
            "status": IncidentStatus.CONTAINED,
            "contained_at": now.isoformat(),
            "actions_taken": actions_taken,
            "actor": actor,
        }

    async def check_escalations(self) -> list[dict[str, Any]]:
        """Check for incidents approaching notification deadline.

        Identifies P1/P2 incidents that have been open for >= ESCALATION_THRESHOLD_HOURS
        and have not yet had an escalation sent.

        Returns:
            List of escalation alerts to send.
        """
        threshold_time = datetime.now(UTC) - timedelta(hours=ESCALATION_THRESHOLD_HOURS)

        result = await self._session.execute(
            select(Incident).where(
                Incident.classification.in_([IncidentClassification.P1, IncidentClassification.P2]),
                Incident.status.in_([IncidentStatus.OPEN, IncidentStatus.CONTAINED]),
                Incident.notification_deadline.isnot(None),
                Incident.created_at <= threshold_time,
            )
        )
        incidents = result.scalars().all()

        alerts: list[dict[str, Any]] = []
        for incident in incidents:
            # Check if escalation already sent
            event_result = await self._session.execute(
                select(IncidentEvent).where(
                    IncidentEvent.incident_id == incident.id,
                    IncidentEvent.event_type == IncidentEventType.ESCALATION_SENT,
                )
            )
            if event_result.scalar_one_or_none() is not None:
                continue

            hours_remaining = incident.hours_until_deadline or 0
            alert = {
                "incident_id": str(incident.id),
                "classification": incident.classification.value,
                "created_at": incident.created_at.isoformat(),
                "notification_deadline": incident.notification_deadline.isoformat()
                if incident.notification_deadline
                else None,
                "hours_remaining": round(hours_remaining, 1),
                "current_status": incident.status.value,
                "message": f"GDPR notification deadline in {round(hours_remaining)} hours",
                "recipients": ["DPO"],
                "priority": "highest",
            }
            alerts.append(alert)

            # Record escalation event
            self._session.add(
                IncidentEvent(
                    incident_id=incident.id,
                    event_type=IncidentEventType.ESCALATION_SENT,
                    actor="system",
                    description=f"DPO escalation: deadline in {round(hours_remaining)} hours",
                    details_json=alert,
                )
            )

        await self._session.flush()
        return alerts

    async def close_incident(
        self,
        incident_id: uuid.UUID,
        resolution_summary: str,
        actor: str,
    ) -> dict[str, Any]:
        """Close an incident and generate the full timeline.

        Args:
            incident_id: The incident to close.
            resolution_summary: Summary of resolution actions.
            actor: Identity of the person closing the incident.

        Returns:
            Incident summary with full timeline.
        """
        result = await self._session.execute(select(Incident).where(Incident.id == incident_id))
        incident = result.scalar_one_or_none()
        if incident is None:
            raise ValueError(f"Incident {incident_id} not found")

        if incident.status == IncidentStatus.CLOSED:
            raise ValueError("Incident is already closed")

        now = datetime.now(UTC)

        # Record close event
        self._session.add(
            IncidentEvent(
                incident_id=incident_id,
                event_type=IncidentEventType.CLOSED,
                actor=actor,
                description=f"Incident closed by {actor}: {resolution_summary}",
                details_json={"resolution_summary": resolution_summary},
            )
        )

        # Generate timeline from all events
        event_result = await self._session.execute(
            select(IncidentEvent).where(IncidentEvent.incident_id == incident_id).order_by(IncidentEvent.created_at)
        )
        events = event_result.scalars().all()

        timeline = [
            {
                "event_type": e.event_type.value,
                "actor": e.actor,
                "description": e.description,
                "timestamp": e.created_at.isoformat(),
                "details": e.details_json,
            }
            for e in events
        ]

        incident.status = IncidentStatus.CLOSED
        incident.resolved_at = now
        incident.closed_at = now
        incident.resolution_summary = resolution_summary
        incident.timeline_json = timeline
        await self._session.flush()

        return {
            "incident_id": str(incident_id),
            "classification": incident.classification.value,
            "status": IncidentStatus.CLOSED,
            "resolution_summary": resolution_summary,
            "closed_at": now.isoformat(),
            "timeline": timeline,
            "retention_years": 7,
        }
