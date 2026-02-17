"""Tests for integration connectors and API routes."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from src.integrations.base import BaseConnector, ConnectionConfig, ConnectionStatus, ConnectorRegistry
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
    async def test_sync_data(self) -> None:
        config = ConnectionConfig(base_url="https://celonis.example.com", api_key="test-key")
        connector = CelonisConnector(config)
        result = await connector.sync_data(engagement_id="test-123")
        assert "records_synced" in result
        assert "errors" in result
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_sync_data_not_configured(self) -> None:
        config = ConnectionConfig()
        connector = CelonisConnector(config)
        result = await connector.sync_data(engagement_id="test-123")
        assert result["records_synced"] == 0
        assert len(result["errors"]) > 0


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
        result = await connector.test_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_test_connection_no_config(self) -> None:
        config = ConnectionConfig()
        connector = SorocoConnector(config)
        result = await connector.test_connection()
        assert result is False

    @pytest.mark.asyncio
    async def test_sync_data(self) -> None:
        config = ConnectionConfig(
            base_url="https://soroco.example.com",
            api_key="test-key",
            extra={"tenant_id": "tenant-1"},
        )
        connector = SorocoConnector(config)
        result = await connector.sync_data(engagement_id="test-123", team_id="team-a")
        assert result["records_synced"] == 0
        assert result["errors"] == []


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
    async def test_create_connection(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
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
    async def test_list_connections(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
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
    async def test_test_connection_not_found(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """POST /api/v1/integrations/connections/{id}/test returns 404."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await client.post(f"/api/v1/integrations/connections/{uuid.uuid4()}/test")
        assert response.status_code == 404
