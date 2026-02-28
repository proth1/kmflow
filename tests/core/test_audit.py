"""Tests for the audit logging module (src/core/audit.py).

Covers log_audit_event_async, log_security_event, log_audit,
and edge cases for missing fields and sensitive data handling.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.core.audit import (
    log_audit,
    log_audit_event_async,
    log_data_access,
    log_login,
    log_permission_denied,
    log_security_event,
)
from src.core.models import AuditAction, AuditLog, HttpAuditEvent


# ---------------------------------------------------------------------------
# log_audit_event_async
# ---------------------------------------------------------------------------


class TestLogAuditEventAsync:
    """Tests for the HTTP audit event logger."""

    @pytest.mark.asyncio
    async def test_log_audit_event_async_with_session(self) -> None:
        """Should persist an HttpAuditEvent when session is provided."""
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()

        await log_audit_event_async(
            method="POST",
            path="/api/v1/evidence",
            user_id="user-123",
            status_code=201,
            engagement_id="eng-abc",
            duration_ms=42.5,
            session=session,
        )

        session.add.assert_called_once()
        added_obj = session.add.call_args[0][0]
        assert isinstance(added_obj, HttpAuditEvent)
        assert added_obj.method == "POST"
        assert added_obj.path == "/api/v1/evidence"
        assert added_obj.user_id == "user-123"
        assert added_obj.status_code == 201
        assert added_obj.engagement_id == "eng-abc"
        assert added_obj.duration_ms == 42.5
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_log_audit_event_async_without_session(self) -> None:
        """Should only log (not persist) when session is None."""
        with patch("src.core.audit.logger") as mock_logger:
            await log_audit_event_async(
                method="DELETE",
                path="/api/v1/users/1",
                user_id="admin",
                status_code=204,
            )
            mock_logger.info.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_audit_event_async_no_engagement_id(self) -> None:
        """Should handle None engagement_id gracefully."""
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()

        await log_audit_event_async(
            method="GET",
            path="/api/v1/health",
            user_id="anonymous",
            status_code=200,
            session=session,
        )

        added_obj = session.add.call_args[0][0]
        assert added_obj.engagement_id is None


# ---------------------------------------------------------------------------
# log_security_event
# ---------------------------------------------------------------------------


class TestLogSecurityEvent:
    """Tests for the security event logger."""

    @pytest.mark.asyncio
    async def test_log_security_event_with_engagement(self) -> None:
        """Should create AuditLog when engagement_id is provided."""
        session = AsyncMock()
        session.add = MagicMock()

        engagement_id = uuid.uuid4()
        result = await log_security_event(
            session=session,
            action=AuditAction.DATA_ACCESS,
            actor="user@example.com",
            engagement_id=engagement_id,
            details={"resource": "/api/v1/evidence"},
            ip_address="10.0.0.1",
            resource="/api/v1/evidence",
        )

        assert result is not None
        assert isinstance(result, AuditLog)
        assert result.engagement_id == engagement_id
        assert result.action == AuditAction.DATA_ACCESS
        assert result.actor == "user@example.com"
        session.add.assert_called_once_with(result)

    @pytest.mark.asyncio
    async def test_log_security_event_without_engagement(self) -> None:
        """Should return None and log warning when engagement_id is None."""
        session = AsyncMock()

        with patch("src.core.audit.logger") as mock_logger:
            result = await log_security_event(
                session=session,
                action=AuditAction.LOGIN,
                actor="user@example.com",
            )
            assert result is None
            mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_security_event_details_serialized(self) -> None:
        """Details dict should be serialized to JSON string."""
        session = AsyncMock()
        session.add = MagicMock()

        engagement_id = uuid.uuid4()
        result = await log_security_event(
            session=session,
            action=AuditAction.PERMISSION_DENIED,
            actor="test",
            engagement_id=engagement_id,
            details={"permission": "admin:write"},
            ip_address="192.168.1.1",
        )

        assert result is not None
        parsed = json.loads(result.details)
        assert parsed["permission"] == "admin:write"
        assert parsed["ip_address"] == "192.168.1.1"

    @pytest.mark.asyncio
    async def test_log_security_event_no_optional_fields(self) -> None:
        """Should handle all optional fields being None."""
        session = AsyncMock()
        session.add = MagicMock()

        engagement_id = uuid.uuid4()
        result = await log_security_event(
            session=session,
            action=AuditAction.DATA_ACCESS,
            engagement_id=engagement_id,
        )

        assert result is not None
        assert result.details is None
        assert result.actor == "system"

    @pytest.mark.asyncio
    async def test_sensitive_data_not_logged_plaintext(self) -> None:
        """Passwords and tokens should not appear in audit details."""
        session = AsyncMock()
        session.add = MagicMock()

        engagement_id = uuid.uuid4()
        # Even if someone passes sensitive data, the log_security_event only
        # serializes what's in 'details' — verify it doesn't add extra fields.
        result = await log_security_event(
            session=session,
            action=AuditAction.LOGIN,
            actor="user@example.com",
            engagement_id=engagement_id,
            details={"success": True},
        )

        assert result is not None
        parsed = json.loads(result.details)
        # Should only contain what was passed, no passwords or tokens
        assert "password" not in parsed
        assert "token" not in parsed
        assert parsed == {"success": True}


# ---------------------------------------------------------------------------
# log_audit (synchronous wrapper)
# ---------------------------------------------------------------------------


class TestLogAudit:
    """Tests for the business action audit logger."""

    @pytest.mark.asyncio
    async def test_log_audit_creates_entry(self) -> None:
        """Should add an AuditLog with the given engagement_id and action."""
        session = AsyncMock()
        session.add = MagicMock()

        engagement_id = uuid.uuid4()
        await log_audit(
            session=session,
            engagement_id=engagement_id,
            action=AuditAction.EVIDENCE_UPLOADED,
            details="Uploaded file.pdf",
            actor="user-456",
        )

        session.add.assert_called_once()
        added_obj = session.add.call_args[0][0]
        assert isinstance(added_obj, AuditLog)
        assert added_obj.engagement_id == engagement_id
        assert added_obj.action == AuditAction.EVIDENCE_UPLOADED
        assert added_obj.details == "Uploaded file.pdf"
        assert added_obj.actor == "user-456"

    @pytest.mark.asyncio
    async def test_log_audit_default_actor(self) -> None:
        """Should default actor to 'system' when not specified."""
        session = AsyncMock()
        session.add = MagicMock()

        engagement_id = uuid.uuid4()
        await log_audit(
            session=session,
            engagement_id=engagement_id,
            action=AuditAction.POV_GENERATED,
        )

        added_obj = session.add.call_args[0][0]
        assert added_obj.actor == "system"

    @pytest.mark.asyncio
    async def test_log_audit_none_details(self) -> None:
        """Should handle None details gracefully."""
        session = AsyncMock()
        session.add = MagicMock()

        engagement_id = uuid.uuid4()
        await log_audit(
            session=session,
            engagement_id=engagement_id,
            action=AuditAction.ENGAGEMENT_CREATED,
        )

        added_obj = session.add.call_args[0][0]
        assert added_obj.details is None


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------


class TestConvenienceHelpers:
    """Tests for log_login, log_permission_denied, log_data_access."""

    @pytest.mark.asyncio
    async def test_log_login_success(self) -> None:
        """log_login should call log_security_event with LOGIN action."""
        session = AsyncMock()

        with patch("src.core.audit.logger"):
            result = await log_login(
                session=session,
                actor="user@example.com",
                ip_address="10.0.0.1",
                success=True,
            )
            # engagement_id is None for login -> returns None
            assert result is None

    @pytest.mark.asyncio
    async def test_log_permission_denied(self) -> None:
        """log_permission_denied should record the denied permission."""
        session = AsyncMock()
        session.add = MagicMock()

        engagement_id = uuid.uuid4()
        result = await log_permission_denied(
            session=session,
            actor="user@example.com",
            permission="admin:delete",
            engagement_id=engagement_id,
        )

        assert result is not None
        assert result.action == AuditAction.PERMISSION_DENIED

    @pytest.mark.asyncio
    async def test_log_data_access(self) -> None:
        """log_data_access should record the accessed resource."""
        session = AsyncMock()
        session.add = MagicMock()

        engagement_id = uuid.uuid4()
        result = await log_data_access(
            session=session,
            actor="user@example.com",
            resource="/api/v1/evidence/123",
            engagement_id=engagement_id,
        )

        assert result is not None
        assert result.action == AuditAction.DATA_ACCESS
