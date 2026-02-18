"""Tests for Phase 3 integration connectors."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from src.integrations.base import ConnectionConfig
from src.integrations.field_mapping import (
    apply_field_mapping,
    get_default_mapping,
    validate_mapping,
)
from src.integrations.salesforce import SalesforceConnector
from src.integrations.sap import SAPConnector
from src.integrations.servicenow import ServiceNowConnector


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> httpx.Response:
    """Create a mock httpx Response."""
    return httpx.Response(
        status_code=status_code,
        json=json_data or {},
        request=httpx.Request("GET", "https://example.com"),
    )


class TestSalesforceConnector:
    """Test suite for SalesforceConnector."""

    @pytest.mark.asyncio
    async def test_connection_with_valid_config(self) -> None:
        """test_connection with valid config should return True."""
        config = ConnectionConfig(
            base_url="https://example.salesforce.com",
            api_key="test_token",
        )
        connector = SalesforceConnector(config)
        mock_response = _mock_response(200)
        with patch("src.integrations.salesforce.retry_request", return_value=mock_response):
            result = await connector.test_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_connection_without_base_url(self) -> None:
        """test_connection without base_url should return False."""
        config = ConnectionConfig()
        connector = SalesforceConnector(config)
        result = await connector.test_connection()
        assert result is False

    @pytest.mark.asyncio
    async def test_sync_data_returns_dict(self) -> None:
        """sync_data should return dict with records_synced."""
        config = ConnectionConfig(
            base_url="https://example.salesforce.com",
            api_key="test_token",
        )
        connector = SalesforceConnector(config)

        async def mock_paginate(*args, **kwargs):
            yield [{"Id": "001", "Name": "Test"}]

        with patch("src.integrations.salesforce.paginate_cursor", side_effect=mock_paginate):
            result = await connector.sync_data("engagement-123", object_type="Case")
        assert "records_synced" in result
        assert isinstance(result["records_synced"], int)
        assert result["records_synced"] == 1
        assert "metadata" in result

    @pytest.mark.asyncio
    async def test_sync_data_auth_failure(self) -> None:
        """sync_data should handle auth failure."""
        config = ConnectionConfig(
            base_url="https://example.salesforce.com",
            extra={"client_id": "id", "client_secret": "secret"},
        )
        connector = SalesforceConnector(config)
        with patch("src.integrations.salesforce.retry_request", side_effect=httpx.ConnectError("fail")):
            result = await connector.sync_data("engagement-123")
        assert result["records_synced"] == 0
        assert "authentication failed" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_get_schema_returns_fields(self) -> None:
        """get_schema should return list of field names."""
        config = ConnectionConfig(
            base_url="https://example.salesforce.com",
            api_key="test_token",
        )
        connector = SalesforceConnector(config)
        schema = await connector.get_schema()
        assert isinstance(schema, list)
        assert "Id" in schema
        assert "Name" in schema
        assert "Status" in schema

    @pytest.mark.asyncio
    async def test_sync_incremental_returns_dict(self) -> None:
        """sync_incremental should add WHERE clause."""
        config = ConnectionConfig(
            base_url="https://example.salesforce.com",
            api_key="test_token",
        )
        connector = SalesforceConnector(config)

        async def mock_paginate(*args, **kwargs):
            yield [{"Id": "002"}]

        with patch("src.integrations.salesforce.paginate_cursor", side_effect=mock_paginate):
            result = await connector.sync_incremental("engagement-123", since="2024-01-01")
        assert "records_synced" in result


class TestSAPConnector:
    """Test suite for SAPConnector."""

    @pytest.mark.asyncio
    async def test_connection_with_valid_config(self) -> None:
        """test_connection with valid config should return True."""
        config = ConnectionConfig(
            base_url="https://example.sap.com",
            api_key="test_api_key",
        )
        connector = SAPConnector(config)
        mock_response = _mock_response(200)
        with patch("src.integrations.sap.retry_request", return_value=mock_response):
            result = await connector.test_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_connection_without_config(self) -> None:
        """test_connection without config should return False."""
        config = ConnectionConfig()
        connector = SAPConnector(config)
        result = await connector.test_connection()
        assert result is False

    @pytest.mark.asyncio
    async def test_sync_data_returns_dict(self) -> None:
        """sync_data should return dict."""
        config = ConnectionConfig(
            base_url="https://example.sap.com",
            api_key="test_api_key",
        )
        connector = SAPConnector(config)

        async def mock_paginate(*args, **kwargs):
            yield [{"BELNR": "001"}, {"BELNR": "002"}]

        with patch("src.integrations.sap.paginate_cursor", side_effect=mock_paginate):
            result = await connector.sync_data("engagement-123", entity_set="ZProcessLogs")
        assert "records_synced" in result
        assert "metadata" in result
        assert result["metadata"]["source"] == "sap"

    @pytest.mark.asyncio
    async def test_connection_http_error(self) -> None:
        """test_connection should handle HTTP errors."""
        config = ConnectionConfig(
            base_url="https://example.sap.com",
            api_key="test_api_key",
        )
        connector = SAPConnector(config)
        with patch("src.integrations.sap.retry_request", side_effect=httpx.ConnectError("fail")):
            result = await connector.test_connection()
        assert result is False

    @pytest.mark.asyncio
    async def test_get_schema_returns_sap_fields(self) -> None:
        """get_schema should return SAP-specific fields."""
        config = ConnectionConfig(
            base_url="https://example.sap.com",
            api_key="test_api_key",
        )
        connector = SAPConnector(config)
        schema = await connector.get_schema()
        assert isinstance(schema, list)
        assert "MANDT" in schema
        assert "BELNR" in schema
        assert "BUKRS" in schema


class TestServiceNowConnector:
    """Test suite for ServiceNowConnector."""

    @pytest.mark.asyncio
    async def test_connection_with_valid_config(self) -> None:
        """test_connection with valid config should return True."""
        config = ConnectionConfig(
            base_url="https://example.service-now.com",
            api_key="test_api_key",
        )
        connector = ServiceNowConnector(config)
        mock_response = _mock_response(200)
        with patch("src.integrations.servicenow.retry_request", return_value=mock_response):
            result = await connector.test_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_connection_without_config(self) -> None:
        """test_connection without config should return False."""
        config = ConnectionConfig()
        connector = ServiceNowConnector(config)
        result = await connector.test_connection()
        assert result is False

    @pytest.mark.asyncio
    async def test_sync_data_returns_dict(self) -> None:
        """sync_data should return dict."""
        config = ConnectionConfig(
            base_url="https://example.service-now.com",
            api_key="test_api_key",
        )
        connector = ServiceNowConnector(config)

        async def mock_paginate(*args, **kwargs):
            yield [{"sys_id": "abc", "number": "INC001"}]

        with patch("src.integrations.servicenow.paginate_offset", side_effect=mock_paginate):
            result = await connector.sync_data("engagement-123", table_name="incident")
        assert "records_synced" in result
        assert "metadata" in result
        assert result["metadata"]["source"] == "servicenow"

    @pytest.mark.asyncio
    async def test_connection_http_error(self) -> None:
        """test_connection should handle HTTP errors."""
        config = ConnectionConfig(
            base_url="https://example.service-now.com",
            api_key="test_api_key",
        )
        connector = ServiceNowConnector(config)
        with patch("src.integrations.servicenow.retry_request", side_effect=httpx.ConnectError("fail")):
            result = await connector.test_connection()
        assert result is False


class TestFieldMapping:
    """Test suite for field mapping functions."""

    def test_get_default_mapping_salesforce(self) -> None:
        mapping = get_default_mapping("salesforce")
        assert mapping["Id"] == "external_id"
        assert mapping["Name"] == "name"
        assert mapping["Description"] == "description"

    def test_get_default_mapping_sap(self) -> None:
        mapping = get_default_mapping("sap")
        assert mapping["MANDT"] == "client_id"
        assert mapping["BELNR"] == "document_number"

    def test_get_default_mapping_servicenow(self) -> None:
        mapping = get_default_mapping("servicenow")
        assert mapping["sys_id"] == "external_id"
        assert mapping["short_description"] == "name"

    def test_get_default_mapping_unknown(self) -> None:
        mapping = get_default_mapping("unknown_connector")
        assert mapping == {}

    def test_apply_field_mapping_transforms_record(self) -> None:
        record = {"Id": "123", "Name": "Test Record", "Status": "Active"}
        mapping = {"Id": "external_id", "Name": "name"}
        result = apply_field_mapping(record, mapping)
        assert result["external_id"] == "123"
        assert result["name"] == "Test Record"

    def test_apply_field_mapping_includes_unmapped(self) -> None:
        record = {"Id": "123", "Name": "Test", "Status": "Active"}
        mapping = {"Id": "external_id"}
        result = apply_field_mapping(record, mapping)
        assert result["external_id"] == "123"
        assert result["Status"] == "Active"
        assert result["Name"] == "Test"

    def test_validate_mapping_valid(self) -> None:
        mapping = {"Id": "external_id", "Name": "name"}
        schema = ["Id", "Name", "Status"]
        errors = validate_mapping(mapping, schema)
        assert errors == []

    def test_validate_mapping_invalid_field(self) -> None:
        mapping = {"Id": "external_id", "InvalidField": "target"}
        schema = ["Id", "Name", "Status"]
        errors = validate_mapping(mapping, schema)
        assert len(errors) == 1
        assert "InvalidField" in errors[0]
        assert "not in schema" in errors[0]
