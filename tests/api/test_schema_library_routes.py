"""Route-level tests for schema library endpoints (Story #335)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.routes.auth import get_current_user
from src.core.models import User, UserRole


def _mock_user() -> User:
    user = MagicMock(spec=User)
    user.id = "user-1"
    user.email = "analyst@example.com"
    user.role = UserRole.PLATFORM_ADMIN
    return user


def _make_client() -> TestClient:
    app = create_app()
    app.state.neo4j_driver = MagicMock()
    app.state.db_session_factory = AsyncMock()
    session = AsyncMock()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    return TestClient(app)


class TestListPlatforms:
    """GET /api/v1/schema-library/platforms."""

    def test_returns_all_platforms(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/schema-library/platforms")

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 3
        assert "salesforce" in data["platforms"]
        assert "sap" in data["platforms"]
        assert "servicenow" in data["platforms"]


class TestGetPlatformTemplate:
    """GET /api/v1/schema-library/platforms/{platform}."""

    def test_returns_servicenow_template(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/schema-library/platforms/servicenow")

        assert resp.status_code == 200
        data = resp.json()
        assert data["platform"] == "servicenow"
        assert len(data["tables"]) == 3

    def test_returns_sap_template(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/schema-library/platforms/sap")

        assert resp.status_code == 200
        data = resp.json()
        assert data["platform"] == "sap"
        assert len(data["tables"]) == 3

    def test_returns_salesforce_template(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/schema-library/platforms/salesforce")

        assert resp.status_code == 200
        data = resp.json()
        assert data["platform"] == "salesforce"
        assert len(data["tables"]) == 2

    def test_unknown_platform_returns_404(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/schema-library/platforms/oracle")

        assert resp.status_code == 404
        assert "manual mapping" in resp.json()["detail"].lower()


class TestGetTableTemplate:
    """GET /api/v1/schema-library/platforms/{platform}/tables/{table_name}."""

    def test_returns_incident_table(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/schema-library/platforms/servicenow/tables/incident")

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "incident"
        assert len(data["fields"]) > 0
        assert len(data["lifecycle_states"]) > 0

    def test_returns_bkpf_table(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/schema-library/platforms/sap/tables/BKPF")

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "BKPF"

    def test_unknown_table_returns_404(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/schema-library/platforms/servicenow/tables/nonexistent")

        assert resp.status_code == 404

    def test_unknown_platform_returns_404(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/schema-library/platforms/oracle/tables/anything")

        assert resp.status_code == 404


class TestCheckPlatformSupport:
    """GET /api/v1/schema-library/platforms/{platform}/check."""

    def test_supported_platform(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/schema-library/platforms/servicenow/check")

        assert resp.status_code == 200
        data = resp.json()
        assert data["supported"] is True
        assert data["mode"] == "auto"

    def test_unsupported_platform(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/schema-library/platforms/oracle/check")

        assert resp.status_code == 200
        data = resp.json()
        assert data["supported"] is False
        assert data["mode"] == "manual"
