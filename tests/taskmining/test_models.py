"""Tests for task mining SQLAlchemy model definitions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from src.core.models.taskmining import (
    ActionCategory,
    AgentStatus,
    CaptureGranularity,
    DeploymentMode,
    DesktopEventType,
    PIIQuarantine,
    PIIType,
    QuarantineStatus,
    SessionStatus,
    TaskMiningAction,
    TaskMiningAgent,
    TaskMiningEvent,
    TaskMiningSession,
)


class TestEnums:
    """Test that all enums have expected values."""

    def test_agent_status_values(self) -> None:
        assert AgentStatus.PENDING_APPROVAL == "pending_approval"
        assert AgentStatus.APPROVED == "approved"
        assert AgentStatus.ACTIVE == "active"
        assert AgentStatus.PAUSED == "paused"
        assert AgentStatus.REVOKED == "revoked"
        assert AgentStatus.EXPIRED == "expired"

    def test_deployment_mode_values(self) -> None:
        assert DeploymentMode.ENGAGEMENT == "engagement"
        assert DeploymentMode.ENTERPRISE == "enterprise"

    def test_capture_granularity_values(self) -> None:
        assert CaptureGranularity.ACTION_LEVEL == "action_level"
        assert CaptureGranularity.CONTENT_LEVEL == "content_level"

    def test_desktop_event_types(self) -> None:
        assert len(DesktopEventType) == 17
        assert DesktopEventType.APP_SWITCH == "app_switch"
        assert DesktopEventType.IDLE_END == "idle_end"

    def test_session_status_values(self) -> None:
        assert SessionStatus.ACTIVE == "active"
        assert SessionStatus.PAUSED == "paused"
        assert SessionStatus.ENDED == "ended"

    def test_action_category_values(self) -> None:
        assert ActionCategory.FILE_OPERATION == "file_operation"
        assert ActionCategory.DATA_ENTRY == "data_entry"
        assert ActionCategory.NAVIGATION == "navigation"
        assert ActionCategory.COMMUNICATION == "communication"
        assert ActionCategory.REVIEW == "review"
        assert ActionCategory.SYSTEM_OPERATION == "system_operation"
        assert ActionCategory.UNKNOWN == "unknown"

    def test_pii_type_values(self) -> None:
        assert PIIType.SSN == "ssn"
        assert PIIType.CREDIT_CARD == "credit_card"
        assert PIIType.EMAIL == "email"
        assert PIIType.PHONE == "phone"

    def test_quarantine_status_values(self) -> None:
        assert QuarantineStatus.PENDING_REVIEW == "pending_review"
        assert QuarantineStatus.RELEASED == "released"
        assert QuarantineStatus.DELETED == "deleted"
        assert QuarantineStatus.AUTO_DELETED == "auto_deleted"


class TestAgentModel:
    """Test TaskMiningAgent model instantiation.

    Note: SQLAlchemy `default=` only applies at INSERT time. For pure Python
    object construction (without DB), defaults must be passed explicitly.
    """

    def test_create_agent_with_explicit_defaults(self) -> None:
        agent = TaskMiningAgent(
            engagement_id=uuid.uuid4(),
            hostname="dev-mac-01.local",
            os_version="macOS 14.3",
            agent_version="1.0.0",
            machine_id="ABCD-1234-EFGH-5678",
            deployment_mode=DeploymentMode.ENGAGEMENT,
            status=AgentStatus.PENDING_APPROVAL,
            capture_granularity=CaptureGranularity.ACTION_LEVEL,
        )
        assert agent.status == AgentStatus.PENDING_APPROVAL
        assert agent.capture_granularity == CaptureGranularity.ACTION_LEVEL
        assert agent.hostname == "dev-mac-01.local"

    def test_agent_repr(self) -> None:
        agent = TaskMiningAgent(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            hostname="test-host",
            os_version="macOS 14",
            agent_version="1.0.0",
            machine_id="test-id",
            deployment_mode=DeploymentMode.ENTERPRISE,
            status=AgentStatus.ACTIVE,
        )
        r = repr(agent)
        assert "TaskMiningAgent" in r
        assert "test-host" in r


class TestSessionModel:
    """Test TaskMiningSession model instantiation."""

    def test_create_session(self) -> None:
        session = TaskMiningSession(
            agent_id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            status=SessionStatus.ACTIVE,
            event_count=0,
            action_count=0,
            pii_detections=0,
        )
        assert session.status == SessionStatus.ACTIVE
        assert session.event_count == 0
        assert session.action_count == 0
        assert session.pii_detections == 0


class TestEventModel:
    """Test TaskMiningEvent model instantiation."""

    def test_create_event(self) -> None:
        event = TaskMiningEvent(
            session_id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            event_type=DesktopEventType.APP_SWITCH,
            timestamp=datetime.now(UTC),
            application_name="Safari",
            window_title="Google - Safari",
            pii_filtered=False,
        )
        assert event.event_type == DesktopEventType.APP_SWITCH
        assert event.pii_filtered is False


class TestActionModel:
    """Test TaskMiningAction model instantiation."""

    def test_create_action(self) -> None:
        now = datetime.now(UTC)
        action = TaskMiningAction(
            session_id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            category=ActionCategory.DATA_ENTRY,
            application_name="Excel",
            description="Data entry in spreadsheet",
            event_count=42,
            duration_seconds=120.5,
            started_at=now,
            ended_at=now,
        )
        assert action.category == ActionCategory.DATA_ENTRY
        assert action.event_count == 42


class TestQuarantineModel:
    """Test PIIQuarantine model instantiation."""

    def test_create_quarantine(self) -> None:
        quarantine = PIIQuarantine(
            engagement_id=uuid.uuid4(),
            original_event_data={"window_title": "SSN: 123-45-6789"},
            pii_type=PIIType.SSN,
            pii_field="window_title",
            detection_confidence=0.95,
            status=QuarantineStatus.PENDING_REVIEW,
            auto_delete_at=datetime.now(UTC),
        )
        assert quarantine.status == QuarantineStatus.PENDING_REVIEW
        assert quarantine.pii_type == PIIType.SSN
