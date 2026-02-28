"""Tests for the Salesforce integration connector."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from src.integrations.base import ConnectionConfig
from src.integrations.salesforce import (
    SalesforceConnector,
    _validate_field_name,
    _validate_sobject_name,
)


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> httpx.Response:
    """Build a minimal httpx.Response for mocking."""
    return httpx.Response(
        status_code=status_code,
        json=json_data or {},
        request=httpx.Request("GET", "https://sf.example.com"),
    )


# =============================================================================
# Validation helpers
# =============================================================================


class TestValidationHelpers:
    """Unit tests for SOQL injection-prevention validators."""

    def test_validate_sobject_valid(self) -> None:
        assert _validate_sobject_name("Case") == "Case"
        assert _validate_sobject_name("My_Object__c") == "My_Object__c"

    def test_validate_sobject_invalid(self) -> None:
        with pytest.raises(ValueError, match="Invalid Salesforce object name"):
            _validate_sobject_name("Case; DROP TABLE")

    def test_validate_field_valid(self) -> None:
        assert _validate_field_name("Id") == "Id"
        assert _validate_field_name("Account.Name") == "Account.Name"

    def test_validate_field_invalid(self) -> None:
        with pytest.raises(ValueError, match="Invalid Salesforce field name"):
            _validate_field_name("Id, 1=1")


# =============================================================================
# SalesforceConnector initialisation
# =============================================================================


class TestSalesforceConnectorInit:
    """Tests for SalesforceConnector construction."""

    def test_description_present(self) -> None:
        connector = SalesforceConnector(ConnectionConfig())
        assert "Salesforce" in connector.description

    def test_instance_url_from_base_url(self) -> None:
        config = ConnectionConfig(base_url="https://myorg.salesforce.com/")
        connector = SalesforceConnector(config)
        # Trailing slash stripped
        assert connector._instance_url == "https://myorg.salesforce.com"

    def test_access_token_from_api_key(self) -> None:
        config = ConnectionConfig(api_key="TOKEN123")
        connector = SalesforceConnector(config)
        assert connector._access_token == "TOKEN123"

    def test_api_version_default(self) -> None:
        connector = SalesforceConnector(ConnectionConfig())
        assert connector._api_version == "v59.0"

    def test_api_version_override(self) -> None:
        config = ConnectionConfig(extra={"api_version": "v60.0"})
        connector = SalesforceConnector(config)
        assert connector._api_version == "v60.0"


# =============================================================================
# Authentication
# =============================================================================


@pytest.mark.asyncio
class TestSalesforceAuthentication:
    """Tests for _authenticate()."""

    async def test_authenticate_skips_when_token_present(self) -> None:
        """If access token already set, _authenticate returns True without HTTP call."""
        config = ConnectionConfig(api_key="existing-token")
        connector = SalesforceConnector(config)
        result = await connector._authenticate()
        assert result is True

    async def test_authenticate_returns_false_without_credentials(self) -> None:
        """No client_id/secret and no token → False."""
        connector = SalesforceConnector(ConnectionConfig())
        result = await connector._authenticate()
        assert result is False

    async def test_authenticate_success(self) -> None:
        """Successful OAuth2 client credentials exchange sets access_token."""
        # No base_url so instance_url is empty — the token response sets it.
        config = ConnectionConfig(
            extra={"client_id": "cid", "client_secret": "csecret"},
        )
        connector = SalesforceConnector(config)

        token_response = _mock_response(
            200, {"access_token": "new-token", "instance_url": "https://myorg.salesforce.com"}
        )
        with patch("src.integrations.salesforce.retry_request", return_value=token_response):
            result = await connector._authenticate()

        assert result is True
        assert connector._access_token == "new-token"
        assert connector._instance_url == "https://myorg.salesforce.com"

    async def test_authenticate_http_error_returns_false(self) -> None:
        """HTTP error during auth returns False without raising."""
        config = ConnectionConfig(
            extra={"client_id": "cid", "client_secret": "csecret"},
        )
        connector = SalesforceConnector(config)
        with patch("src.integrations.salesforce.retry_request", side_effect=httpx.ConnectError("fail")):
            result = await connector._authenticate()
        assert result is False


# =============================================================================
# test_connection
# =============================================================================


@pytest.mark.asyncio
class TestSalesforceTestConnection:
    """Tests for test_connection()."""

    async def test_test_connection_missing_url_and_credentials(self) -> None:
        """No instance_url and no client_id → False immediately."""
        connector = SalesforceConnector(ConnectionConfig())
        result = await connector.test_connection()
        assert result is False

    async def test_test_connection_success(self) -> None:
        """Successful auth + 200 API ping → True."""
        config = ConnectionConfig(
            base_url="https://myorg.salesforce.com",
            api_key="token",
        )
        connector = SalesforceConnector(config)
        ok_response = _mock_response(200)
        with patch("src.integrations.salesforce.retry_request", return_value=ok_response):
            result = await connector.test_connection()
        assert result is True

    async def test_test_connection_non_200(self) -> None:
        """Non-200 status from API ping → False."""
        config = ConnectionConfig(base_url="https://myorg.salesforce.com", api_key="token")
        connector = SalesforceConnector(config)
        # retry_request raises HTTPStatusError for 4xx/5xx; simulate connection error path
        err_response = _mock_response(403)
        # Patch so raise_for_status does not fire; manually return 403 status
        with patch("src.integrations.salesforce.retry_request", return_value=err_response):
            result = await connector.test_connection()
        assert result is False

    async def test_test_connection_request_error(self) -> None:
        """Network error during ping → False."""
        config = ConnectionConfig(base_url="https://myorg.salesforce.com", api_key="token")
        connector = SalesforceConnector(config)
        with patch("src.integrations.salesforce.retry_request", side_effect=httpx.ConnectError("fail")):
            result = await connector.test_connection()
        assert result is False


# =============================================================================
# sync_data
# =============================================================================


@pytest.mark.asyncio
class TestSalesforceSyncData:
    """Tests for sync_data()."""

    async def test_sync_data_auth_failure(self) -> None:
        """Auth failure → zero records, error message."""
        connector = SalesforceConnector(ConnectionConfig())
        result = await connector.sync_data("eng-001")
        assert result["records_synced"] == 0
        assert any("authentication" in e.lower() for e in result["errors"])

    async def test_sync_data_success_with_records(self) -> None:
        """Successful sync returns correct record count and metadata."""
        config = ConnectionConfig(base_url="https://myorg.salesforce.com", api_key="token")
        connector = SalesforceConnector(config)

        async def mock_paginate(*args, **kwargs):
            yield [{"Id": "1", "Name": "Case 1"}, {"Id": "2", "Name": "Case 2"}]

        with patch("src.integrations.salesforce.paginate_cursor", side_effect=mock_paginate):
            result = await connector.sync_data("eng-001")

        assert result["records_synced"] == 2
        assert result["errors"] == []
        assert result["metadata"]["source"] == "salesforce"
        assert result["metadata"]["engagement_id"] == "eng-001"

    async def test_sync_data_custom_object_type(self) -> None:
        """Custom object_type kwarg is validated and used."""
        config = ConnectionConfig(base_url="https://myorg.salesforce.com", api_key="token")
        connector = SalesforceConnector(config)

        async def mock_paginate(*args, **kwargs):
            yield [{"Id": "a1"}]

        with patch("src.integrations.salesforce.paginate_cursor", side_effect=mock_paginate):
            result = await connector.sync_data("eng-001", object_type="Opportunity")

        assert result["records_synced"] == 1
        assert result["metadata"]["object_type"] == "Opportunity"

    async def test_sync_data_invalid_object_type_raises(self) -> None:
        """Invalid object_type raises ValueError immediately."""
        config = ConnectionConfig(base_url="https://myorg.salesforce.com", api_key="token")
        connector = SalesforceConnector(config)
        with pytest.raises(ValueError, match="Invalid Salesforce object name"):
            await connector.sync_data("eng-001", object_type="Case; --")

    async def test_sync_data_http_status_error(self) -> None:
        """HTTPStatusError from API → records_synced=0, error message."""
        config = ConnectionConfig(base_url="https://myorg.salesforce.com", api_key="token")
        connector = SalesforceConnector(config)

        async def mock_paginate(*args, **kwargs):
            raise httpx.HTTPStatusError(
                "401",
                request=httpx.Request("GET", "https://myorg.salesforce.com"),
                response=_mock_response(401),
            )
            yield  # make it a generator

        with patch("src.integrations.salesforce.paginate_cursor", side_effect=mock_paginate):
            result = await connector.sync_data("eng-001")

        assert result["records_synced"] == 0
        assert len(result["errors"]) == 1
        assert "401" in result["errors"][0]

    async def test_sync_data_request_error(self) -> None:
        """RequestError from network → records_synced=0, error message."""
        config = ConnectionConfig(base_url="https://myorg.salesforce.com", api_key="token")
        connector = SalesforceConnector(config)

        async def mock_paginate(*args, **kwargs):
            raise httpx.ConnectError("timeout")
            yield

        with patch("src.integrations.salesforce.paginate_cursor", side_effect=mock_paginate):
            result = await connector.sync_data("eng-001")

        assert result["records_synced"] == 0
        assert len(result["errors"]) == 1
        assert "connection" in result["errors"][0].lower()


# =============================================================================
# get_schema
# =============================================================================


@pytest.mark.asyncio
class TestSalesforceGetSchema:
    """Tests for get_schema()."""

    async def test_get_schema_returns_expected_fields(self) -> None:
        connector = SalesforceConnector(ConnectionConfig())
        schema = await connector.get_schema()
        assert "Id" in schema
        assert "Name" in schema
        assert "Status" in schema


# =============================================================================
# sync_incremental
# =============================================================================


@pytest.mark.asyncio
class TestSalesforceSyncIncremental:
    """Tests for sync_incremental()."""

    async def test_sync_incremental_without_since_falls_back_to_full(self) -> None:
        """No since timestamp → delegates to sync_data without WHERE clause."""
        config = ConnectionConfig(base_url="https://myorg.salesforce.com", api_key="token")
        connector = SalesforceConnector(config)

        called_with: list[dict] = []

        async def mock_paginate(*args, **kwargs):
            called_with.append(dict(kwargs))
            yield [{"Id": "1"}]

        with patch("src.integrations.salesforce.paginate_cursor", side_effect=mock_paginate):
            result = await connector.sync_incremental("eng-001")

        assert result["records_synced"] == 1
        # The SOQL should not contain a WHERE clause
        soql = called_with[0]["params"]["q"]
        assert "WHERE" not in soql

    async def test_sync_incremental_with_since_adds_where_clause(self) -> None:
        """With since timestamp, SOQL includes LastModifiedDate filter."""
        config = ConnectionConfig(base_url="https://myorg.salesforce.com", api_key="token")
        connector = SalesforceConnector(config)

        captured_soql: list[str] = []

        async def mock_paginate(*args, **kwargs):
            captured_soql.append(kwargs["params"]["q"])
            yield [{"Id": "1"}]

        with patch("src.integrations.salesforce.paginate_cursor", side_effect=mock_paginate):
            result = await connector.sync_incremental("eng-001", since="2024-01-01T00:00:00Z")

        assert result["records_synced"] == 1
        assert "WHERE" in captured_soql[0]
        assert "LastModifiedDate" in captured_soql[0]
        assert "2024-01-01T00:00:00Z" in captured_soql[0]
