"""Tests for capture consent management.

Story #213 — Part of Epic #210 (Privacy and Compliance).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models.taskmining import AgentStatus, TaskMiningAgent
from src.taskmining.consent import (
    ConsentManager,
    ConsentRecord,
    ConsentStatus,
    ConsentType,
)


def _mock_agent(status: AgentStatus = AgentStatus.PENDING_APPROVAL) -> TaskMiningAgent:
    """Build a mock agent."""
    agent = MagicMock(spec=TaskMiningAgent)
    agent.id = uuid.uuid4()
    agent.status = status
    agent.engagement_id = uuid.uuid4()
    return agent


class TestConsentRecordModel:
    """Verify ConsentRecord model structure."""

    def test_consent_type_values(self) -> None:
        assert ConsentType.ENGAGEMENT == "engagement"
        assert ConsentType.ENTERPRISE == "enterprise"

    def test_consent_status_values(self) -> None:
        assert ConsentStatus.ACTIVE == "active"
        assert ConsentStatus.REVOKED == "revoked"
        assert ConsentStatus.NOT_RECORDED == "not_recorded"


class TestRecordConsent:
    """Test consent grant flow."""

    @pytest.mark.asyncio
    async def test_creates_consent_record(self) -> None:
        session = AsyncMock()
        agent = _mock_agent(AgentStatus.PENDING_APPROVAL)
        session.get.return_value = agent

        mgr = ConsentManager()
        record = await mgr.record_consent(
            session,
            agent_id=agent.id,
            engagement_id=agent.engagement_id,
            consent_type=ConsentType.ENGAGEMENT,
            capture_mode="action_level",
        )

        assert isinstance(record, ConsentRecord)
        assert record.agent_id == agent.id
        assert record.consent_type == ConsentType.ENGAGEMENT
        assert record.capture_mode == "action_level"
        assert record.user_acknowledged is True
        assert record.revoked_at is None
        session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_transitions_agent_to_approved(self) -> None:
        session = AsyncMock()
        agent = _mock_agent(AgentStatus.PENDING_APPROVAL)
        session.get.return_value = agent

        mgr = ConsentManager()
        await mgr.record_consent(
            session,
            agent_id=agent.id,
            engagement_id=agent.engagement_id,
            consent_type=ConsentType.ENGAGEMENT,
        )

        assert agent.status == AgentStatus.APPROVED

    @pytest.mark.asyncio
    async def test_ip_address_hashed(self) -> None:
        session = AsyncMock()
        session.get.return_value = _mock_agent()

        mgr = ConsentManager()
        record = await mgr.record_consent(
            session,
            agent_id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            consent_type=ConsentType.ENTERPRISE,
            ip_address="192.168.1.1",
        )

        assert record.ip_address_hash is not None
        assert len(record.ip_address_hash) == 64  # SHA-256 hex
        assert "192.168.1.1" not in record.ip_address_hash

    @pytest.mark.asyncio
    async def test_no_ip_produces_null_hash(self) -> None:
        session = AsyncMock()
        session.get.return_value = _mock_agent()

        mgr = ConsentManager()
        record = await mgr.record_consent(
            session,
            agent_id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            consent_type=ConsentType.ENGAGEMENT,
        )

        assert record.ip_address_hash is None


class TestRevokeConsent:
    """Test consent revocation flow."""

    @pytest.mark.asyncio
    async def test_revokes_active_consent(self) -> None:
        session = AsyncMock()
        agent = _mock_agent(AgentStatus.APPROVED)
        session.get.return_value = agent

        # Mock finding an active consent record
        existing = ConsentRecord(
            agent_id=agent.id,
            engagement_id=agent.engagement_id,
            consent_type=ConsentType.ENGAGEMENT,
            capture_mode="action_level",
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        session.execute.return_value = result_mock

        mgr = ConsentManager()
        record = await mgr.revoke_consent(session, agent.id)

        assert record is not None
        assert record.revoked_at is not None
        assert agent.status == AgentStatus.REVOKED

    @pytest.mark.asyncio
    async def test_revoke_no_active_returns_none(self) -> None:
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute.return_value = result_mock

        mgr = ConsentManager()
        record = await mgr.revoke_consent(session, uuid.uuid4())
        assert record is None


class TestGetConsentStatus:
    """Test consent status lookup."""

    @pytest.mark.asyncio
    async def test_active_consent(self) -> None:
        session = AsyncMock()
        existing = ConsentRecord(
            agent_id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            consent_type=ConsentType.ENGAGEMENT,
            capture_mode="action_level",
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        session.execute.return_value = result_mock

        mgr = ConsentManager()
        status = await mgr.get_consent_status(session, existing.agent_id)
        assert status == ConsentStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_revoked_consent(self) -> None:
        session = AsyncMock()
        existing = ConsentRecord(
            agent_id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            consent_type=ConsentType.ENGAGEMENT,
            capture_mode="action_level",
        )
        existing.revoked_at = datetime.now(timezone.utc)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        session.execute.return_value = result_mock

        mgr = ConsentManager()
        status = await mgr.get_consent_status(session, existing.agent_id)
        assert status == ConsentStatus.REVOKED

    @pytest.mark.asyncio
    async def test_no_record(self) -> None:
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute.return_value = result_mock

        mgr = ConsentManager()
        status = await mgr.get_consent_status(session, uuid.uuid4())
        assert status == ConsentStatus.NOT_RECORDED


class TestHasActiveConsent:
    """Test the convenience check."""

    @pytest.mark.asyncio
    async def test_returns_true_for_active(self) -> None:
        session = AsyncMock()
        existing = ConsentRecord(
            agent_id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            consent_type=ConsentType.ENGAGEMENT,
            capture_mode="action_level",
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        session.execute.return_value = result_mock

        mgr = ConsentManager()
        assert await mgr.has_active_consent(session, existing.agent_id) is True

    @pytest.mark.asyncio
    async def test_returns_false_for_revoked(self) -> None:
        session = AsyncMock()
        existing = ConsentRecord(
            agent_id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            consent_type=ConsentType.ENGAGEMENT,
            capture_mode="action_level",
        )
        existing.revoked_at = datetime.now(timezone.utc)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        session.execute.return_value = result_mock

        mgr = ConsentManager()
        assert await mgr.has_active_consent(session, existing.agent_id) is False


class TestEngagementConsentTrail:
    """Test consent audit trail retrieval."""

    @pytest.mark.asyncio
    async def test_returns_all_records(self) -> None:
        session = AsyncMock()
        engagement_id = uuid.uuid4()
        records = [
            ConsentRecord(
                agent_id=uuid.uuid4(),
                engagement_id=engagement_id,
                consent_type=ConsentType.ENGAGEMENT,
                capture_mode="action_level",
            )
            for _ in range(3)
        ]
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = records
        result_mock.scalars.return_value = scalars_mock
        session.execute.return_value = result_mock

        mgr = ConsentManager()
        trail = await mgr.get_engagement_consent_trail(session, engagement_id)
        assert len(trail) == 3

    @pytest.mark.asyncio
    async def test_empty_engagement(self) -> None:
        session = AsyncMock()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        session.execute.return_value = result_mock

        mgr = ConsentManager()
        trail = await mgr.get_engagement_consent_trail(session, uuid.uuid4())
        assert len(trail) == 0
