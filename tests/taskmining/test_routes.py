"""Tests for task mining API routes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from src.core.models.taskmining import (
    AgentStatus,
    CaptureGranularity,
    DeploymentMode,
    PIIQuarantine,
    PIIType,
    QuarantineStatus,
    TaskMiningAgent,
)


class TestAgentRegistration:
    """Tests for POST /api/v1/taskmining/agents/register."""

    @pytest.mark.asyncio
    async def test_register_agent(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        engagement_id = uuid.uuid4()
        agent_id = uuid.uuid4()

        def refresh_side_effect(obj: Any) -> None:
            if isinstance(obj, TaskMiningAgent):
                obj.id = agent_id
                obj.status = AgentStatus.PENDING_APPROVAL
                obj.deployment_mode = DeploymentMode.ENGAGEMENT
                obj.capture_granularity = CaptureGranularity.ACTION_LEVEL
                obj.created_at = datetime.now(UTC)
                obj.updated_at = datetime.now(UTC)

        mock_db_session.refresh.side_effect = refresh_side_effect

        response = await client.post(
            "/api/v1/taskmining/agents/register",
            json={
                "engagement_id": str(engagement_id),
                "hostname": "dev-mac-01.local",
                "os_version": "macOS 14.3",
                "agent_version": "1.0.0",
                "machine_id": "UNIQUE-MACHINE-ID-001",
                "deployment_mode": "engagement",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["hostname"] == "dev-mac-01.local"
        assert data["status"] == "pending_approval"
        assert data["deployment_mode"] == "engagement"
        assert data["capture_granularity"] == "action_level"

    @pytest.mark.asyncio
    async def test_register_duplicate_machine_id(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        # Simulate existing agent found
        existing_agent = MagicMock(spec=TaskMiningAgent)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_agent
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await client.post(
            "/api/v1/taskmining/agents/register",
            json={
                "engagement_id": str(uuid.uuid4()),
                "hostname": "dev-mac-02.local",
                "os_version": "macOS 14.3",
                "agent_version": "1.0.0",
                "machine_id": "DUPLICATE-ID",
                "deployment_mode": "engagement",
            },
        )
        assert response.status_code == 409


class TestAgentApproval:
    """Tests for POST /api/v1/taskmining/agents/{id}/approve."""

    @pytest.mark.asyncio
    async def test_approve_agent(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        agent_id = uuid.uuid4()
        agent = MagicMock(spec=TaskMiningAgent)
        agent.id = agent_id
        agent.engagement_id = uuid.uuid4()
        agent.hostname = "test-host"
        agent.os_version = "macOS 14"
        agent.agent_version = "1.0.0"
        agent.machine_id = "test-machine"
        agent.status = AgentStatus.PENDING_APPROVAL
        agent.deployment_mode = DeploymentMode.ENGAGEMENT
        agent.capture_granularity = CaptureGranularity.ACTION_LEVEL
        agent.config_json = None
        agent.last_heartbeat_at = None
        agent.engagement_end_date = None
        agent.approved_by = None
        agent.approved_at = None
        agent.revoked_at = None
        agent.created_at = datetime.now(UTC)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = agent
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await client.post(
            f"/api/v1/taskmining/agents/{agent_id}/approve",
            json={"status": "approved"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_approve_nonexistent_agent(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await client.post(
            f"/api/v1/taskmining/agents/{uuid.uuid4()}/approve",
            json={"status": "approved"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_approve_invalid_status(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        response = await client.post(
            f"/api/v1/taskmining/agents/{uuid.uuid4()}/approve",
            json={"status": "active"},
        )
        assert response.status_code == 422


class TestAgentList:
    """Tests for GET /api/v1/taskmining/agents."""

    @pytest.mark.asyncio
    async def test_list_agents_empty(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        response = await client.get("/api/v1/taskmining/agents")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0


class TestHeartbeat:
    """Tests for POST /api/v1/taskmining/heartbeat."""

    @pytest.mark.asyncio
    async def test_heartbeat_ok(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        agent_id = uuid.uuid4()
        agent = MagicMock(spec=TaskMiningAgent)
        agent.id = agent_id
        agent.status = AgentStatus.ACTIVE
        agent.engagement_end_date = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = agent
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await client.post(
            "/api/v1/taskmining/heartbeat",
            json={"agent_id": str(agent_id)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_heartbeat_revoked_agent(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        agent_id = uuid.uuid4()
        agent = MagicMock(spec=TaskMiningAgent)
        agent.id = agent_id
        agent.status = AgentStatus.REVOKED
        agent.engagement_end_date = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = agent
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await client.post(
            "/api/v1/taskmining/heartbeat",
            json={"agent_id": str(agent_id)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "revoked"

    @pytest.mark.asyncio
    async def test_heartbeat_unknown_agent(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await client.post(
            "/api/v1/taskmining/heartbeat",
            json={"agent_id": str(uuid.uuid4())},
        )
        assert response.status_code == 404


class TestAgentConfig:
    """Tests for GET /api/v1/taskmining/config/{agent_id}."""

    @pytest.mark.asyncio
    async def test_get_config(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        agent_id = uuid.uuid4()
        agent = MagicMock(spec=TaskMiningAgent)
        agent.id = agent_id
        agent.capture_granularity = CaptureGranularity.ACTION_LEVEL
        agent.config_json = {"app_blocklist": ["com.apple.systempreferences"]}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = agent
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await client.get(f"/api/v1/taskmining/config/{agent_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["capture_granularity"] == "action_level"
        assert data["url_domain_only"] is True
        assert data["batch_size"] == 1000


class TestSessions:
    """Tests for GET /api/v1/taskmining/sessions."""

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        response = await client.get("/api/v1/taskmining/sessions")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0


class TestActions:
    """Tests for GET /api/v1/taskmining/actions."""

    @pytest.mark.asyncio
    async def test_list_actions_empty(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        response = await client.get("/api/v1/taskmining/actions")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0


class TestQuarantine:
    """Tests for quarantine management endpoints."""

    @pytest.mark.asyncio
    async def test_list_quarantine_empty(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        response = await client.get("/api/v1/taskmining/quarantine")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_quarantine_delete_action(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        quarantine_id = uuid.uuid4()
        item = MagicMock(spec=PIIQuarantine)
        item.id = quarantine_id
        item.engagement_id = uuid.uuid4()
        item.pii_type = PIIType.SSN
        item.pii_field = "window_title"
        item.detection_confidence = 0.95
        item.status = QuarantineStatus.PENDING_REVIEW
        item.reviewed_by = None
        item.reviewed_at = None
        item.auto_delete_at = datetime.now(UTC)
        item.created_at = datetime.now(UTC)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = item
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await client.post(
            f"/api/v1/taskmining/quarantine/{quarantine_id}/action",
            json={"action": "delete"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_quarantine_invalid_action(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        response = await client.post(
            f"/api/v1/taskmining/quarantine/{uuid.uuid4()}/action",
            json={"action": "invalid"},
        )
        assert response.status_code == 422


class TestDashboardStats:
    """Tests for GET /api/v1/taskmining/dashboard/stats."""

    @pytest.mark.asyncio
    async def test_get_dashboard_stats(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        # Mock multiple execute calls returning 0 counts
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_result.all.return_value = []
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await client.get("/api/v1/taskmining/dashboard/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_agents"] == 0
        assert data["active_agents"] == 0
        assert data["total_events"] == 0
        assert data["app_usage"] == []
