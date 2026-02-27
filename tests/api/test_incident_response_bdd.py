"""BDD tests for Story #397: Incident Response Automation.

Tests P1 incident creation with GDPR 72-hour deadline, containment
actions (access restriction + audit freeze), escalation monitoring,
and incident closure with timeline generation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.services.incident import IncidentService
from src.core.models import (
    Incident,
    IncidentClassification,
    IncidentEvent,
    IncidentEventType,
    IncidentStatus,
)
from src.core.models.incident import ESCALATION_THRESHOLD_HOURS, GDPR_NOTIFICATION_HOURS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENGAGEMENT_ID = uuid.uuid4()


def _mock_session() -> AsyncMock:
    """Create a mock async session with common setup."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


def _mock_incident(
    *,
    classification: IncidentClassification = IncidentClassification.P1,
    status: IncidentStatus = IncidentStatus.OPEN,
    hours_ago: float = 0,
) -> MagicMock:
    """Create a mock Incident."""
    now = datetime.now(UTC)
    created = now - timedelta(hours=hours_ago)

    i = MagicMock(spec=Incident)
    i.id = uuid.uuid4()
    i.engagement_id = ENGAGEMENT_ID
    i.classification = classification
    i.status = status
    i.title = "Test Incident"
    i.description = "Test incident description"
    i.reported_by = "security_team"
    i.created_at = created
    i.contained_at = None
    i.resolved_at = None
    i.closed_at = None
    i.timeline_json = None
    i.resolution_summary = None

    if classification in (IncidentClassification.P1, IncidentClassification.P2):
        i.notification_deadline = created + timedelta(hours=GDPR_NOTIFICATION_HOURS)
        delta = i.notification_deadline - now
        i.hours_until_deadline = max(0.0, delta.total_seconds() / 3600)
        i.needs_escalation = hours_ago >= ESCALATION_THRESHOLD_HOURS
    else:
        i.notification_deadline = None
        i.hours_until_deadline = None
        i.needs_escalation = False

    return i


# ---------------------------------------------------------------------------
# BDD Scenario 1: P1 Incident Creation with 72-hour Deadline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_1_p1_incident_sets_72_hour_deadline() -> None:
    """Given a P1 data breach is detected,
    When an incident is created,
    Then notification_deadline is set to created_at + 72 hours."""
    session = _mock_session()
    service = IncidentService(session)

    incident = await service.create_incident(
        engagement_id=ENGAGEMENT_ID,
        classification=IncidentClassification.P1,
        title="Data Breach Detected",
        description="Unauthorized data export from engagement",
        reported_by="security_team",
    )

    assert incident is not None
    assert isinstance(incident, Incident)
    assert incident.classification == IncidentClassification.P1
    assert incident.status == IncidentStatus.OPEN
    assert incident.notification_deadline is not None

    # Verify 72-hour deadline
    delta = incident.notification_deadline - incident.created_at
    assert abs(delta.total_seconds() - GDPR_NOTIFICATION_HOURS * 3600) < 2

    # Verify events: creation event logged
    assert session.add.call_count >= 2  # incident + event


@pytest.mark.asyncio
async def test_scenario_1_p3_incident_no_deadline() -> None:
    """Given a P3 vulnerability is detected,
    When an incident is created,
    Then no notification deadline is set."""
    session = _mock_session()
    service = IncidentService(session)

    incident = await service.create_incident(
        engagement_id=ENGAGEMENT_ID,
        classification=IncidentClassification.P3,
        title="Vulnerability Found",
        description="XSS in upload form",
        reported_by="security_team",
    )

    assert incident.notification_deadline is None


@pytest.mark.asyncio
async def test_scenario_1_p2_incident_has_deadline() -> None:
    """P2 security incidents also get notification deadlines."""
    session = _mock_session()
    service = IncidentService(session)

    incident = await service.create_incident(
        engagement_id=ENGAGEMENT_ID,
        classification=IncidentClassification.P2,
        title="Security Incident",
        description="Unauthorized access attempt",
        reported_by="security_team",
    )

    assert incident.notification_deadline is not None


# ---------------------------------------------------------------------------
# BDD Scenario 2: Containment Actions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_2_p1_containment_restricts_access_and_freezes_audit() -> None:
    """Given a P1 incident is active,
    When containment is executed,
    Then access is restricted and audit logs are frozen."""
    session = _mock_session()
    incident = _mock_incident(classification=IncidentClassification.P1)

    result = MagicMock()
    result.scalar_one_or_none.return_value = incident
    session.execute = AsyncMock(return_value=result)

    service = IncidentService(session)
    containment = await service.contain_incident(
        incident_id=incident.id,
        actor="dpo_user",
    )

    assert containment["status"] == IncidentStatus.CONTAINED
    assert "access_restricted" in containment["actions_taken"]
    assert "audit_logs_frozen" in containment["actions_taken"]
    assert containment["actor"] == "dpo_user"
    assert incident.status == IncidentStatus.CONTAINED
    assert incident.contained_at is not None


@pytest.mark.asyncio
async def test_scenario_2_p4_containment_no_access_restriction() -> None:
    """P4 policy violations don't trigger access restriction."""
    session = _mock_session()
    incident = _mock_incident(classification=IncidentClassification.P4)

    result = MagicMock()
    result.scalar_one_or_none.return_value = incident
    session.execute = AsyncMock(return_value=result)

    service = IncidentService(session)
    containment = await service.contain_incident(
        incident_id=incident.id,
        actor="admin",
    )

    assert containment["actions_taken"] == []


@pytest.mark.asyncio
async def test_scenario_2_contain_not_found_raises() -> None:
    """Containing a non-existent incident raises ValueError."""
    session = _mock_session()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)

    service = IncidentService(session)
    with pytest.raises(ValueError, match="not found"):
        await service.contain_incident(
            incident_id=uuid.uuid4(),
            actor="admin",
        )


@pytest.mark.asyncio
async def test_scenario_2_contain_already_contained_raises() -> None:
    """Cannot contain an already contained incident."""
    session = _mock_session()
    incident = _mock_incident(status=IncidentStatus.CONTAINED)

    result = MagicMock()
    result.scalar_one_or_none.return_value = incident
    session.execute = AsyncMock(return_value=result)

    service = IncidentService(session)
    with pytest.raises(ValueError, match="Cannot contain"):
        await service.contain_incident(
            incident_id=incident.id,
            actor="admin",
        )


# ---------------------------------------------------------------------------
# BDD Scenario 3: Escalation at 48 Hours
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_3_escalation_at_48_hours() -> None:
    """Given a P1 incident was created 48+ hours ago,
    When the deadline monitor runs,
    Then a DPO escalation alert is generated."""
    session = _mock_session()
    incident = _mock_incident(
        classification=IncidentClassification.P1,
        hours_ago=49,
    )

    # Mock the select queries
    incident_result = MagicMock()
    incident_result.scalars.return_value.all.return_value = [incident]

    # Mock no existing escalation event
    no_event_result = MagicMock()
    no_event_result.scalar_one_or_none.return_value = None

    session.execute = AsyncMock(side_effect=[incident_result, no_event_result])

    service = IncidentService(session)
    alerts = await service.check_escalations()

    assert len(alerts) == 1
    assert alerts[0]["classification"] == "P1"
    assert "DPO" in alerts[0]["recipients"]
    assert alerts[0]["priority"] == "highest"
    assert "GDPR notification deadline" in alerts[0]["message"]


@pytest.mark.asyncio
async def test_scenario_3_no_escalation_before_threshold() -> None:
    """Given a P1 incident was created recently,
    When the deadline monitor runs,
    Then no escalation is generated."""
    session = _mock_session()

    # No incidents match the threshold query
    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=empty_result)

    service = IncidentService(session)
    alerts = await service.check_escalations()

    assert len(alerts) == 0


@pytest.mark.asyncio
async def test_scenario_3_no_duplicate_escalation() -> None:
    """Given an escalation was already sent,
    When the deadline monitor runs again,
    Then no duplicate escalation is generated."""
    session = _mock_session()
    incident = _mock_incident(
        classification=IncidentClassification.P1,
        hours_ago=50,
    )

    incident_result = MagicMock()
    incident_result.scalars.return_value.all.return_value = [incident]

    # Existing escalation event found
    existing_event = MagicMock(spec=IncidentEvent)
    existing_event_result = MagicMock()
    existing_event_result.scalar_one_or_none.return_value = existing_event

    session.execute = AsyncMock(side_effect=[incident_result, existing_event_result])

    service = IncidentService(session)
    alerts = await service.check_escalations()

    assert len(alerts) == 0


# ---------------------------------------------------------------------------
# BDD Scenario 4: Incident Closure with Timeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_4_close_generates_timeline() -> None:
    """Given a P1 incident has been through detection and containment,
    When the incident is closed,
    Then a full timeline is generated."""
    session = _mock_session()
    incident = _mock_incident(status=IncidentStatus.CONTAINED)

    incident_result = MagicMock()
    incident_result.scalar_one_or_none.return_value = incident

    # Mock timeline events
    events = [
        MagicMock(
            spec=IncidentEvent,
            event_type=IncidentEventType.CREATED,
            actor="reporter",
            description="Incident created",
            created_at=datetime.now(UTC) - timedelta(hours=24),
            details_json={"classification": "P1"},
        ),
        MagicMock(
            spec=IncidentEvent,
            event_type=IncidentEventType.CONTAINMENT_STARTED,
            actor="dpo",
            description="Containment started",
            created_at=datetime.now(UTC) - timedelta(hours=23),
            details_json=None,
        ),
        MagicMock(
            spec=IncidentEvent,
            event_type=IncidentEventType.CLOSED,
            actor="admin",
            description="Incident closed",
            created_at=datetime.now(UTC),
            details_json={"resolution_summary": "Issue resolved"},
        ),
    ]
    event_result = MagicMock()
    event_result.scalars.return_value.all.return_value = events

    session.execute = AsyncMock(side_effect=[incident_result, event_result])

    service = IncidentService(session)
    result = await service.close_incident(
        incident_id=incident.id,
        resolution_summary="Breach contained, no data exfiltrated",
        actor="security_lead",
    )

    assert result["status"] == IncidentStatus.CLOSED
    assert result["retention_years"] == 7
    assert len(result["timeline"]) == 3
    assert result["timeline"][0]["event_type"] == "created"
    assert result["timeline"][-1]["event_type"] == "closed"
    assert incident.status == IncidentStatus.CLOSED
    assert incident.resolved_at is not None
    assert incident.timeline_json is not None


@pytest.mark.asyncio
async def test_scenario_4_close_not_found_raises() -> None:
    """Closing a non-existent incident raises ValueError."""
    session = _mock_session()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)

    service = IncidentService(session)
    with pytest.raises(ValueError, match="not found"):
        await service.close_incident(
            incident_id=uuid.uuid4(),
            resolution_summary="N/A",
            actor="admin",
        )


@pytest.mark.asyncio
async def test_scenario_4_close_already_closed_raises() -> None:
    """Cannot close an already closed incident."""
    session = _mock_session()
    incident = _mock_incident(status=IncidentStatus.CLOSED)

    result = MagicMock()
    result.scalar_one_or_none.return_value = incident
    session.execute = AsyncMock(return_value=result)

    service = IncidentService(session)
    with pytest.raises(ValueError, match="already closed"):
        await service.close_incident(
            incident_id=incident.id,
            resolution_summary="N/A",
            actor="admin",
        )


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------


def test_incident_classification_values() -> None:
    """IncidentClassification has correct P1-P4 values."""
    assert IncidentClassification.P1 == "P1"
    assert IncidentClassification.P2 == "P2"
    assert IncidentClassification.P3 == "P3"
    assert IncidentClassification.P4 == "P4"


def test_incident_status_values() -> None:
    """IncidentStatus has correct lifecycle values."""
    assert IncidentStatus.OPEN == "open"
    assert IncidentStatus.CONTAINED == "contained"
    assert IncidentStatus.RESOLVED == "resolved"
    assert IncidentStatus.CLOSED == "closed"


def test_gdpr_constants() -> None:
    """GDPR notification and escalation constants are correct."""
    assert GDPR_NOTIFICATION_HOURS == 72
    assert ESCALATION_THRESHOLD_HOURS == 48
