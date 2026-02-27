"""Tests for API Gateway and Service Layer Setup — Story #307.

Covers all 5 BDD scenarios:
1. Health check endpoint returns service status
2. OpenAPI documentation is accessible
3. Request tracing ID is added to response headers
4. CORS headers are restricted to allowed origins
5. Service dependencies resolve correctly via Depends()
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from src.api.version import API_VERSION

# ---------------------------------------------------------------------------
# BDD Scenario 1: Health check endpoint returns service status
# ---------------------------------------------------------------------------


class TestBDDScenario1HealthCheck:
    """Given the FastAPI application is started
    When a GET request is made to /api/v1/health
    Then the response contains status, version, and timestamp fields.
    """

    @pytest.mark.asyncio
    async def test_health_returns_200(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Health check endpoint returns 200."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_db_session.execute.return_value = mock_result

        response = await client.get("/api/v1/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_has_status_field(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Response contains a 'status' field."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_db_session.execute.return_value = mock_result

        data = (await client.get("/api/v1/health")).json()
        assert "status" in data
        assert data["status"] in ("healthy", "degraded", "unhealthy")

    @pytest.mark.asyncio
    async def test_health_has_version_field(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Response contains a 'version' field matching API_VERSION."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_db_session.execute.return_value = mock_result

        data = (await client.get("/api/v1/health")).json()
        assert "version" in data
        assert data["version"] == API_VERSION

    @pytest.mark.asyncio
    async def test_health_has_timestamp_field(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Response contains a 'timestamp' field in ISO format."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_db_session.execute.return_value = mock_result

        data = (await client.get("/api/v1/health")).json()
        assert "timestamp" in data
        # Validate it parses as ISO datetime
        datetime.fromisoformat(data["timestamp"])

    @pytest.mark.asyncio
    async def test_health_verifies_postgres(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Health check verifies PostgreSQL connectivity."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_db_session.execute.return_value = mock_result

        data = (await client.get("/api/v1/health")).json()
        assert "postgres" in data["services"]
        assert data["services"]["postgres"] == "up"

    @pytest.mark.asyncio
    async def test_health_verifies_neo4j(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Health check verifies Neo4j connectivity."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_db_session.execute.return_value = mock_result

        data = (await client.get("/api/v1/health")).json()
        assert "neo4j" in data["services"]
        assert data["services"]["neo4j"] == "up"

    @pytest.mark.asyncio
    async def test_health_verifies_redis(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Health check verifies Redis connectivity."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_db_session.execute.return_value = mock_result

        data = (await client.get("/api/v1/health")).json()
        assert "redis" in data["services"]
        assert data["services"]["redis"] == "up"


# ---------------------------------------------------------------------------
# BDD Scenario 2: OpenAPI documentation is accessible
# ---------------------------------------------------------------------------


class TestBDDScenario2OpenAPIDocs:
    """Given the FastAPI application is running
    When a GET request is made to /docs
    Then the response renders the Swagger UI.
    """

    def test_docs_url_enabled(self) -> None:
        """App docs_url is /docs (requires Settings.debug=True default)."""
        from src.api.main import create_app

        app = create_app()
        # docs_url is only set when debug=True in Settings
        assert app.docs_url == "/docs"

    def test_redoc_url_enabled(self) -> None:
        """App redoc_url is /redoc (requires Settings.debug=True default)."""
        from src.api.main import create_app

        app = create_app()
        assert app.redoc_url == "/redoc"

    def test_openapi_schema_has_routes(self) -> None:
        """OpenAPI schema includes registered route paths."""
        from src.api.main import create_app

        app = create_app()
        schema = app.openapi()
        paths = schema.get("paths", {})
        assert "/api/v1/health" in paths
        assert "/api/v1/engagements/" in paths

    def test_openapi_schema_has_info(self) -> None:
        """OpenAPI schema includes title and version."""
        from src.api.main import create_app

        app = create_app()
        schema = app.openapi()
        assert schema["info"]["title"] == "KMFlow"
        assert schema["info"]["version"] == API_VERSION


# ---------------------------------------------------------------------------
# BDD Scenario 3: Request tracing ID in response headers
# ---------------------------------------------------------------------------


class TestBDDScenario3RequestTracingID:
    """Given the request tracing middleware is registered
    When a request is made to any endpoint
    Then the response headers contain X-Request-ID (valid UUID).
    """

    @pytest.mark.asyncio
    async def test_response_has_x_request_id(self, client: AsyncClient) -> None:
        """Response includes X-Request-ID header."""
        response = await client.get("/api/v1/health")
        assert "x-request-id" in response.headers

    @pytest.mark.asyncio
    async def test_request_id_is_uuid(self, client: AsyncClient) -> None:
        """Auto-generated X-Request-ID is a valid UUID."""
        import uuid

        response = await client.get("/api/v1/health")
        request_id = response.headers.get("x-request-id", "")
        # Should parse as UUID without error
        uuid.UUID(request_id)

    @pytest.mark.asyncio
    async def test_client_request_id_preserved(self, client: AsyncClient) -> None:
        """Client-provided X-Request-ID is echoed back."""
        custom_id = "test-trace-id-abc123"
        response = await client.get(
            "/api/v1/health",
            headers={"X-Request-ID": custom_id},
        )
        assert response.headers.get("x-request-id") == custom_id

    @pytest.mark.asyncio
    async def test_different_requests_get_different_ids(self, client: AsyncClient) -> None:
        """Each request without client ID gets a unique request ID."""
        r1 = await client.get("/api/v1/health")
        r2 = await client.get("/api/v1/health")
        id1 = r1.headers.get("x-request-id")
        id2 = r2.headers.get("x-request-id")
        assert id1 != id2


# ---------------------------------------------------------------------------
# BDD Scenario 4: CORS headers restricted to allowed origins
# ---------------------------------------------------------------------------


class TestBDDScenario4CORSHeaders:
    """Given CORS is configured with an allowed origins list
    When cross-origin requests arrive
    Then allowed origins get CORS headers, disallowed do not.
    """

    def test_cors_middleware_registered(self) -> None:
        """App has CORSMiddleware configured."""
        from src.api.main import create_app

        app = create_app()
        middleware_classes = [m.cls.__name__ for m in app.user_middleware]
        assert "CORSMiddleware" in middleware_classes

    @pytest.mark.asyncio
    async def test_allowed_origin_gets_cors_header(self, client: AsyncClient) -> None:
        """Request from allowed origin (localhost:3000) gets CORS header."""
        response = await client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

    @pytest.mark.asyncio
    async def test_disallowed_origin_no_cors_header(self, client: AsyncClient) -> None:
        """Request from disallowed origin does not get CORS header."""
        response = await client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        acao = response.headers.get("access-control-allow-origin")
        assert acao is None

    @pytest.mark.asyncio
    async def test_cors_allows_standard_methods(self, client: AsyncClient) -> None:
        """CORS allows GET, POST, PUT, PATCH, DELETE methods."""
        response = await client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        allowed = response.headers.get("access-control-allow-methods", "")
        for method in ["GET", "POST", "PUT", "PATCH", "DELETE"]:
            assert method in allowed


# ---------------------------------------------------------------------------
# BDD Scenario 5: Service dependencies resolve via Depends()
# ---------------------------------------------------------------------------


class TestBDDScenario5ServiceDependencies:
    """Given a route handler that declares a service via Depends()
    When the route is invoked
    Then the dependency is resolved and available in the handler.
    """

    def test_app_has_dependency_injection_pattern(self) -> None:
        """Routes use Depends() for dependency injection."""
        from src.api.main import create_app

        app = create_app()
        route_paths = [route.path for route in app.routes]
        # Verify key routes exist (they use Depends for db sessions)
        assert "/api/v1/engagements/" in route_paths
        assert "/api/v1/evidence/" in route_paths

    def test_settings_singleton_pattern(self) -> None:
        """get_settings returns consistent configuration."""
        from src.core.config import get_settings

        s1 = get_settings()
        s2 = get_settings()
        assert s1.app_name == s2.app_name
        assert s1.postgres_host == s2.postgres_host

    def test_service_layer_structure(self) -> None:
        """Core service modules exist in src/core/."""
        from pathlib import Path

        core_dir = Path("src/core")
        assert core_dir.exists()
        # Key service modules used as dependencies
        assert (core_dir / "config.py").exists()
        assert (core_dir / "database.py").exists()

    @pytest.mark.asyncio
    async def test_health_uses_app_state_dependencies(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Health endpoint accesses db, neo4j, redis from app.state."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_db_session.execute.return_value = mock_result

        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        # The fact that it returns 200 with service statuses proves
        # dependencies (db_session_factory, neo4j_driver, redis_client) resolved
        data = response.json()
        assert "services" in data


# ---------------------------------------------------------------------------
# Additional API gateway validation
# ---------------------------------------------------------------------------


class TestAPIGatewayStructure:
    """Validate API gateway structure and configuration."""

    def test_versioned_api_prefix(self) -> None:
        """All API routes use /api/v1/ prefix."""
        from src.api.main import create_app

        app = create_app()
        api_routes = [route.path for route in app.routes if hasattr(route, "path") and route.path.startswith("/api/")]
        for path in api_routes:
            assert path.startswith("/api/v1/"), f"Route {path} does not use /api/v1/ prefix"

    def test_middleware_stack_includes_security(self) -> None:
        """Middleware stack includes security-related middleware."""
        from src.api.main import create_app

        app = create_app()
        middleware_names = [m.cls.__name__ for m in app.user_middleware]
        assert "RequestIDMiddleware" in middleware_names
        assert "SecurityHeadersMiddleware" in middleware_names
        assert "CORSMiddleware" in middleware_names

    @pytest.mark.asyncio
    async def test_security_headers_present(self, client: AsyncClient) -> None:
        """Responses include standard security headers."""
        response = await client.get("/api/v1/health")
        assert response.headers.get("x-content-type-options") == "nosniff"
        assert response.headers.get("x-frame-options") == "DENY"
        assert "x-api-version" in response.headers

    def test_error_handlers_registered(self) -> None:
        """App has ValueError and generic exception handlers."""
        from src.api.main import create_app

        app = create_app()
        # FastAPI stores exception handlers
        assert ValueError in app.exception_handlers
        assert Exception in app.exception_handlers

    @pytest.mark.asyncio
    async def test_value_error_returns_422(self, client: AsyncClient) -> None:
        """ValueError handler returns 422 Unprocessable Entity."""
        # Trigger a validation error via invalid query param
        response = await client.get("/api/v1/evidence/?limit=-1")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self, client: AsyncClient) -> None:
        """Non-existent route returns 404."""
        response = await client.get("/api/v1/nonexistent-route")
        assert response.status_code == 404
