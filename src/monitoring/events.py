"""Event schema definitions for monitoring system.

Defines the structure of events published through Redis Pub/Sub
for real-time dashboard consumption via WebSocket.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def deviation_event(
    engagement_id: str,
    deviation_id: str,
    category: str,
    magnitude: float,
    affected_element: str | None = None,
    description: str = "",
) -> dict[str, Any]:
    """Create a deviation detection event."""
    return {
        "event_type": "deviation_detected",
        "engagement_id": engagement_id,
        "deviation_id": deviation_id,
        "category": category,
        "magnitude": magnitude,
        "affected_element": affected_element,
        "description": description,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def alert_event(
    engagement_id: str,
    alert_id: str,
    severity: str,
    title: str,
    description: str = "",
) -> dict[str, Any]:
    """Create an alert generation event."""
    return {
        "event_type": "alert_generated",
        "engagement_id": engagement_id,
        "alert_id": alert_id,
        "severity": severity,
        "title": title,
        "description": description,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def monitoring_status_event(
    engagement_id: str,
    job_id: str,
    status: str,
    message: str = "",
) -> dict[str, Any]:
    """Create a monitoring status change event."""
    return {
        "event_type": "monitoring_status_changed",
        "engagement_id": engagement_id,
        "job_id": job_id,
        "status": status,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def collection_complete_event(
    engagement_id: str,
    job_id: str,
    records_collected: int,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    """Create a collection completion event."""
    return {
        "event_type": "collection_complete",
        "engagement_id": engagement_id,
        "job_id": job_id,
        "records_collected": records_collected,
        "errors": errors or [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
