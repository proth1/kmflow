"""Tests for task mining audit logging.

Story #214 — Part of Epic #210 (Privacy and Compliance).
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock

import pytest

from src.core.models.audit import AuditAction
from src.taskmining.audit import TaskMiningAuditLogger


@pytest.fixture
def audit_logger() -> TaskMiningAuditLogger:
    return TaskMiningAuditLogger()


@pytest.fixture
def db_session() -> AsyncMock:
    return AsyncMock()


class TestAuditEventTypes:
    """Verify all 11 task mining audit event types exist in the enum."""

    @pytest.mark.parametrize(
        "action",
        [
            AuditAction.TASK_MINING_STARTED,
            AuditAction.TASK_MINING_STOPPED,
            AuditAction.AGENT_APPROVED,
            AuditAction.AGENT_REVOKED,
            AuditAction.AGENT_CONSENT_GRANTED,
            AuditAction.AGENT_CONSENT_REVOKED,
            AuditAction.CAPTURE_MODE_CHANGED,
            AuditAction.PII_DETECTED,
            AuditAction.PII_QUARANTINED,
            AuditAction.PII_QUARANTINE_RELEASED,
            AuditAction.PII_QUARANTINE_AUTO_DELETED,
        ],
    )
    def test_event_type_exists(self, action: AuditAction) -> None:
        assert action.value is not None


class TestLogBase:
    """Test the base log() method."""

    @pytest.mark.asyncio
    async def test_creates_audit_record_with_engagement(
        self, audit_logger: TaskMiningAuditLogger, db_session: AsyncMock
    ) -> None:
        agent_id = uuid.uuid4()
        engagement_id = uuid.uuid4()

        result = await audit_logger.log(
            db_session,
            AuditAction.AGENT_APPROVED,
            agent_id,
            engagement_id=engagement_id,
            actor="admin@example.com",
        )

        assert result is not None
        assert result.action == AuditAction.AGENT_APPROVED
        assert result.engagement_id == engagement_id
        assert result.actor == "admin@example.com"
        db_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_details_contain_agent_id(self, audit_logger: TaskMiningAuditLogger, db_session: AsyncMock) -> None:
        agent_id = uuid.uuid4()
        engagement_id = uuid.uuid4()

        result = await audit_logger.log(
            db_session,
            AuditAction.AGENT_APPROVED,
            agent_id,
            engagement_id=engagement_id,
        )

        details = json.loads(result.details)
        assert details["agent_id"] == str(agent_id)

    @pytest.mark.asyncio
    async def test_no_engagement_returns_none(self, audit_logger: TaskMiningAuditLogger, db_session: AsyncMock) -> None:
        result = await audit_logger.log(
            db_session,
            AuditAction.AGENT_APPROVED,
            uuid.uuid4(),
            engagement_id=None,
        )
        assert result is None
        db_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_extra_kwargs_in_details(self, audit_logger: TaskMiningAuditLogger, db_session: AsyncMock) -> None:
        result = await audit_logger.log(
            db_session,
            AuditAction.PII_QUARANTINED,
            uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            quarantine_id=uuid.uuid4(),
            pii_type="ssn",
        )

        details = json.loads(result.details)
        assert "quarantine_id" in details
        assert details["pii_type"] == "ssn"


class TestAgentApproval:
    """Test agent approval audit logging."""

    @pytest.mark.asyncio
    async def test_log_agent_approved(self, audit_logger: TaskMiningAuditLogger, db_session: AsyncMock) -> None:
        agent_id = uuid.uuid4()
        engagement_id = uuid.uuid4()

        result = await audit_logger.log_agent_approved(db_session, agent_id, engagement_id, "admin@corp.com")

        assert result.action == AuditAction.AGENT_APPROVED
        assert result.actor == "admin@corp.com"
        details = json.loads(result.details)
        assert details["approved_by"] == "admin@corp.com"

    @pytest.mark.asyncio
    async def test_log_agent_revoked(self, audit_logger: TaskMiningAuditLogger, db_session: AsyncMock) -> None:
        result = await audit_logger.log_agent_revoked(db_session, uuid.uuid4(), uuid.uuid4(), "security@corp.com")

        assert result.action == AuditAction.AGENT_REVOKED
        details = json.loads(result.details)
        assert details["revoked_by"] == "security@corp.com"


class TestConsentAudit:
    """Test consent audit logging."""

    @pytest.mark.asyncio
    async def test_log_consent_granted(self, audit_logger: TaskMiningAuditLogger, db_session: AsyncMock) -> None:
        result = await audit_logger.log_consent_granted(
            db_session,
            uuid.uuid4(),
            uuid.uuid4(),
            consent_type="engagement",
            capture_mode="action_level",
        )

        assert result.action == AuditAction.AGENT_CONSENT_GRANTED
        details = json.loads(result.details)
        assert details["consent_type"] == "engagement"
        assert details["capture_mode"] == "action_level"

    @pytest.mark.asyncio
    async def test_log_consent_revoked(self, audit_logger: TaskMiningAuditLogger, db_session: AsyncMock) -> None:
        result = await audit_logger.log_consent_revoked(db_session, uuid.uuid4(), uuid.uuid4())
        assert result.action == AuditAction.AGENT_CONSENT_REVOKED


class TestPIIAudit:
    """Test PII quarantine audit logging."""

    @pytest.mark.asyncio
    async def test_log_pii_quarantined(self, audit_logger: TaskMiningAuditLogger, db_session: AsyncMock) -> None:
        quarantine_id = uuid.uuid4()
        result = await audit_logger.log_pii_quarantined(
            db_session,
            uuid.uuid4(),
            uuid.uuid4(),
            quarantine_id=quarantine_id,
            pii_type="ssn",
        )

        assert result.action == AuditAction.PII_QUARANTINED
        details = json.loads(result.details)
        assert details["quarantine_id"] == str(quarantine_id)
        assert details["pii_type"] == "ssn"
        assert details["detection_method"] == "regex_l3"

    @pytest.mark.asyncio
    async def test_log_quarantine_auto_deleted(
        self, audit_logger: TaskMiningAuditLogger, db_session: AsyncMock
    ) -> None:
        engagement_id = uuid.uuid4()
        result = await audit_logger.log_quarantine_auto_deleted(
            db_session, engagement_id, rows_deleted=15, duration_ms=42.5
        )

        assert result.action == AuditAction.PII_QUARANTINE_AUTO_DELETED
        details = json.loads(result.details)
        assert details["rows_deleted"] == 15
        assert details["duration_ms"] == 42.5


class TestCaptureLifecycle:
    """Test capture start/stop audit logging."""

    @pytest.mark.asyncio
    async def test_log_capture_started(self, audit_logger: TaskMiningAuditLogger, db_session: AsyncMock) -> None:
        session_id = uuid.uuid4()
        result = await audit_logger.log_capture_started(db_session, uuid.uuid4(), uuid.uuid4(), session_id)

        assert result.action == AuditAction.TASK_MINING_STARTED
        details = json.loads(result.details)
        assert details["session_id"] == str(session_id)

    @pytest.mark.asyncio
    async def test_log_capture_stopped(self, audit_logger: TaskMiningAuditLogger, db_session: AsyncMock) -> None:
        result = await audit_logger.log_capture_stopped(
            db_session,
            uuid.uuid4(),
            uuid.uuid4(),
            uuid.uuid4(),
            event_count=150,
            duration_seconds=480.0,
        )

        assert result.action == AuditAction.TASK_MINING_STOPPED
        details = json.loads(result.details)
        assert details["event_count"] == 150
        assert details["duration_seconds"] == 480.0


class TestImmutability:
    """Verify the audit logger only uses insert operations."""

    @pytest.mark.asyncio
    async def test_only_add_called_never_delete(
        self, audit_logger: TaskMiningAuditLogger, db_session: AsyncMock
    ) -> None:
        """The audit logger must never call session.delete()."""
        await audit_logger.log_agent_approved(db_session, uuid.uuid4(), uuid.uuid4(), "admin")
        await audit_logger.log_consent_granted(db_session, uuid.uuid4(), uuid.uuid4(), "engagement", "action_level")
        await audit_logger.log_pii_quarantined(db_session, uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "ssn")

        # session.add should have been called 3 times
        assert db_session.add.call_count == 3
        # session.delete should NEVER be called
        db_session.delete.assert_not_called()
