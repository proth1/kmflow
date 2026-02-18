"""Tests for integration connectors and API routes."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import AsyncClient

from src.integrations.base import ConnectionConfig, ConnectionStatus, ConnectorRegistry
from src.integrations.celonis import CelonisConnector
from src.integrations.soroco import SorocoConnector

# -- Base Connector Tests ----------------------------------------------------


class TestBaseConnector:
    """Tests for connector base class and registry."""

    def test_connection_status_values(self) -> None:
        assert ConnectionStatus.CONFIGURED == "configured"
        assert ConnectionStatus.CONNECTED == "connected"
        assert ConnectionStatus.ERROR == "error"

    def test_connection_config_defaults(self) -> None:
        config = ConnectionConfig()
        assert config.base_url == ""
        assert config.api_key is None
        assert config.extra == {}

    def test_connector_registry_list(self) -> None:
        connectors = ConnectorRegistry.list_connectors()
        assert "celonis" in connectors
        assert "soroco" in connectors

    def test_connector_registry_get(self) -> None:
        cls = ConnectorRegistry.get("celonis")
        assert cls is CelonisConnector

        cls = ConnectorRegistry.get("soroco")
        assert cls is SorocoConnector

    def test_connector_registry_get_unknown(self) -> None:
        cls = ConnectorRegistry.get("unknown_connector")
        assert cls is None


# -- Celonis Connector Tests -------------------------------------------------


def _mock_httpx_response(status_code: int = 200, json_data: dict | None = None) -> httpx.Response:
    """Create a mock httpx Response."""
    resp = httpx.Response(
        status_code=status_code,
        json=json_data or {},
        request=httpx.Request("GET", "https://example.com"),
    )
    return resp


class TestCelonisConnector:
    """Tests for Celonis EMS connector."""

    def test_description(self) -> None:
        config = ConnectionConfig(base_url="https://celonis.example.com", api_key="test-key")
        connector = CelonisConnector(config)
        assert "Celonis" in connector.description

    @pytest.mark.asyncio
    async def test_test_connection_success(self) -> None:
        config = ConnectionConfig(base_url="https://celonis.example.com", api_key="test-key")
        connector = CelonisConnector(config)
        mock_response = _mock_httpx_response(200)
        with patch("src.integrations.celonis.retry_request", return_value=mock_response):
            result = await connector.test_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_test_connection_no_url(self) -> None:
        config = ConnectionConfig()
        connector = CelonisConnector(config)
        result = await connector.test_connection()
        assert result is False

    @pytest.mark.asyncio
    async def test_test_connection_no_key(self) -> None:
        config = ConnectionConfig(base_url="https://celonis.example.com")
        connector = CelonisConnector(config)
        result = await connector.test_connection()
        assert result is False

    @pytest.mark.asyncio
    async def test_test_connection_http_error(self) -> None:
        config = ConnectionConfig(base_url="https://celonis.example.com", api_key="test-key")
        connector = CelonisConnector(config)
        with patch("src.integrations.celonis.retry_request", side_effect=httpx.ConnectError("fail")):
            result = await connector.test_connection()
        assert result is False

    @pytest.mark.asyncio
    async def test_sync_data_no_pool_id(self) -> None:
        config = ConnectionConfig(base_url="https://celonis.example.com", api_key="test-key")
        connector = CelonisConnector(config)
        result = await connector.sync_data(engagement_id="test-123")
        assert result["records_synced"] == 0
        assert "data_pool_id is required" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_sync_data_success(self) -> None:
        config = ConnectionConfig(base_url="https://celonis.example.com", api_key="test-key")
        connector = CelonisConnector(config)

        async def mock_paginate(*args, **kwargs):
            yield [{"id": 1, "case_id": "case-1"}, {"id": 2, "case_id": "case-2"}]

        with patch("src.integrations.celonis.paginate_offset", side_effect=mock_paginate):
            result = await connector.sync_data(engagement_id="test-123", data_pool_id="pool-1")
        assert result["records_synced"] == 2
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_sync_data_with_db_session_persists_items(self) -> None:
        """When db_session is provided, EvidenceItems are created."""
        config = ConnectionConfig(base_url="https://celonis.example.com", api_key="test-key")
        connector = CelonisConnector(config)

        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        async def mock_paginate(*args, **kwargs):
            yield [{"case_id": "case-abc", "activity": "Submit", "timestamp": "2024-01"}]

        with patch("src.integrations.celonis.paginate_offset", side_effect=mock_paginate):
            result = await connector.sync_data(
                engagement_id="test-123",
                data_pool_id="pool-1",
                db_session=mock_session,
            )

        assert result["records_synced"] == 1
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sync_data_not_configured(self) -> None:
        config = ConnectionConfig()
        connector = CelonisConnector(config)
        result = await connector.sync_data(engagement_id="test-123")
        assert result["records_synced"] == 0
        assert len(result["errors"]) > 0

    @pytest.mark.asyncio
    async def test_get_schema(self) -> None:
        config = ConnectionConfig(base_url="https://celonis.example.com", api_key="test-key")
        connector = CelonisConnector(config)
        schema = await connector.get_schema()
        assert isinstance(schema, list)
        assert "case_id" in schema
        assert "activity" in schema


# -- Soroco Connector Tests --------------------------------------------------


class TestSorocoConnector:
    """Tests for Soroco Scout connector."""

    def test_description(self) -> None:
        config = ConnectionConfig(base_url="https://soroco.example.com", api_key="test-key")
        connector = SorocoConnector(config)
        assert "Soroco" in connector.description

    @pytest.mark.asyncio
    async def test_test_connection_success(self) -> None:
        config = ConnectionConfig(
            base_url="https://soroco.example.com",
            api_key="test-key",
            extra={"tenant_id": "tenant-1"},
        )
        connector = SorocoConnector(config)
        mock_response = _mock_httpx_response(200)
        with patch("src.integrations.soroco.retry_request", return_value=mock_response):
            result = await connector.test_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_test_connection_no_config(self) -> None:
        config = ConnectionConfig()
        connector = SorocoConnector(config)
        result = await connector.test_connection()
        assert result is False

    @pytest.mark.asyncio
    async def test_sync_data_success(self) -> None:
        config = ConnectionConfig(
            base_url="https://soroco.example.com",
            api_key="test-key",
            extra={"tenant_id": "tenant-1"},
        )
        connector = SorocoConnector(config)

        async def mock_paginate(*args, **kwargs):
            yield [{"task_id": "t1"}, {"task_id": "t2"}, {"task_id": "t3"}]

        with patch("src.integrations.soroco.paginate_offset", side_effect=mock_paginate):
            result = await connector.sync_data(engagement_id="test-123", project_id="proj-1")
        assert result["records_synced"] == 3
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_sync_data_with_db_session_persists_items(self) -> None:
        """When db_session is provided, EvidenceItems are created."""
        config = ConnectionConfig(
            base_url="https://soroco.example.com",
            api_key="test-key",
            extra={"tenant_id": "tenant-1"},
        )
        connector = SorocoConnector(config)

        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        async def mock_paginate(*args, **kwargs):
            yield [{"task_id": "task-xyz", "task_name": "Review Docs", "application": "Word"}]

        with patch("src.integrations.soroco.paginate_offset", side_effect=mock_paginate):
            result = await connector.sync_data(
                engagement_id="test-123",
                project_id="proj-1",
                db_session=mock_session,
            )

        assert result["records_synced"] == 1
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sync_data_not_configured(self) -> None:
        config = ConnectionConfig()
        connector = SorocoConnector(config)
        result = await connector.sync_data(engagement_id="test-123")
        assert result["records_synced"] == 0
        assert len(result["errors"]) > 0


# -- Integration API Route Tests ---------------------------------------------


class TestIntegrationRoutes:
    """Tests for integration management API routes (DB-backed)."""

    @pytest.mark.asyncio
    async def test_list_connectors(self, client: AsyncClient) -> None:
        """GET /api/v1/integrations/connectors lists available types."""
        response = await client.get("/api/v1/integrations/connectors")
        assert response.status_code == 200
        data = response.json()
        types = [c["type"] for c in data]
        assert "celonis" in types
        assert "soroco" in types

    @pytest.mark.asyncio
    async def test_create_connection(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """POST /api/v1/integrations/connections creates a connection."""
        from typing import Any

        from src.core.models import IntegrationConnection

        def refresh_side_effect(obj: Any) -> None:
            if isinstance(obj, IntegrationConnection):
                if obj.id is None:
                    obj.id = uuid.uuid4()
                if obj.last_sync_records is None:
                    obj.last_sync_records = 0

        mock_db_session.refresh.side_effect = refresh_side_effect

        response = await client.post(
            "/api/v1/integrations/connections",
            json={
                "engagement_id": str(uuid.uuid4()),
                "connector_type": "celonis",
                "name": "Test Celonis",
                "config": {"base_url": "https://celonis.example.com", "api_key": "key"},
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["connector_type"] == "celonis"
        assert data["status"] == "configured"

    @pytest.mark.asyncio
    async def test_create_connection_unknown_type(self, client: AsyncClient) -> None:
        """POST /api/v1/integrations/connections rejects unknown type."""
        response = await client.post(
            "/api/v1/integrations/connections",
            json={
                "engagement_id": str(uuid.uuid4()),
                "connector_type": "nonexistent",
                "name": "Test",
                "config": {},
            },
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_list_connections(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """GET /api/v1/integrations/connections lists connections."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        response = await client.get("/api/v1/integrations/connections")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_test_connection_not_found(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """POST /api/v1/integrations/connections/{id}/test returns 404."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await client.post(f"/api/v1/integrations/connections/{uuid.uuid4()}/test")
        assert response.status_code == 404
