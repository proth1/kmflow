"""Tests for AuditLoggingMiddleware.

Tests cover:
- POST triggers audit logging
- GET does NOT trigger audit logging
- User ID extracted from request.state.user
- Anonymous user when no auth state
- Engagement ID extracted from URL path
- Duration is measured
- X-Audit-Logged header set on response
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from src.api.middleware.audit import MUTATING_METHODS, AuditLoggingMiddleware

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def _make_app(user: object | None = None) -> FastAPI:
    """Build a minimal app with AuditLoggingMiddleware and a state-injecting route."""
    app = FastAPI()
    app.add_middleware(AuditLoggingMiddleware)

    @app.middleware("http")
    async def inject_user(request: Request, call_next):  # noqa: ANN001, ANN202
        """Set request.state.user before the route handles the request."""
        if user is not None:
            request.state.user = user
        return await call_next(request)

    @app.get("/api/v1/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.post("/api/v1/engagements/{engagement_id}/items")
    async def create_item(engagement_id: str) -> JSONResponse:
        return JSONResponse({"created": True}, status_code=201)

    @app.post("/api/v1/other")
    async def other_post() -> JSONResponse:
        return JSONResponse({"ok": True})

    return app


# ---------------------------------------------------------------------------
# MUTATING_METHODS constant
# ---------------------------------------------------------------------------


class TestMutatingMethods:
    """The MUTATING_METHODS set contains the expected HTTP methods."""

    def test_mutating_methods_includes_post(self) -> None:
        assert "POST" in MUTATING_METHODS

    def test_mutating_methods_includes_put(self) -> None:
        assert "PUT" in MUTATING_METHODS

    def test_mutating_methods_includes_patch(self) -> None:
        assert "PATCH" in MUTATING_METHODS

    def test_mutating_methods_includes_delete(self) -> None:
        assert "DELETE" in MUTATING_METHODS

    def test_mutating_methods_excludes_get(self) -> None:
        assert "GET" not in MUTATING_METHODS

    def test_mutating_methods_excludes_head(self) -> None:
        assert "HEAD" not in MUTATING_METHODS


# ---------------------------------------------------------------------------
# GET does not trigger audit logging
# ---------------------------------------------------------------------------


class TestGetNotAudited:
    """GET requests bypass the audit middleware."""

    def test_get_request_no_audit_header(self) -> None:
        """GET responses should NOT contain X-Audit-Logged header."""
        app = _make_app()
        client = TestClient(app)
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert "X-Audit-Logged" not in response.headers

    def test_get_request_no_log_audit_called(self) -> None:
        """log_audit_event_async should NOT be called for GET requests."""
        app = _make_app()
        client = TestClient(app)

        with patch("src.api.middleware.audit.log_audit_event_async", new_callable=AsyncMock) as mock_log:
            response = client.get("/api/v1/health")
            assert response.status_code == 200
            mock_log.assert_not_called()


# ---------------------------------------------------------------------------
# POST triggers audit logging
# ---------------------------------------------------------------------------


class TestPostAudited:
    """POST requests are captured by the audit middleware."""

    def test_post_sets_audit_logged_header(self) -> None:
        """POST response should include X-Audit-Logged: true header."""
        app = _make_app()
        client = TestClient(app)
        response = client.post("/api/v1/other")
        assert response.status_code == 200
        assert response.headers.get("X-Audit-Logged") == "true"

    def test_post_calls_log_audit_event_async(self) -> None:
        """log_audit_event_async should be awaited for POST requests."""
        app = _make_app()
        client = TestClient(app)

        with patch("src.api.middleware.audit.log_audit_event_async", new_callable=AsyncMock) as mock_log:
            response = client.post("/api/v1/other")
            assert response.status_code == 200
            mock_log.assert_called_once()

    def test_post_audit_receives_correct_method(self) -> None:
        """log_audit_event_async should be called with method=POST."""
        app = _make_app()
        client = TestClient(app)

        with patch("src.api.middleware.audit.log_audit_event_async", new_callable=AsyncMock) as mock_log:
            client.post("/api/v1/other")
            call_kwargs = mock_log.call_args.kwargs
            assert call_kwargs["method"] == "POST"

    def test_post_audit_receives_correct_path(self) -> None:
        """log_audit_event_async should be called with the request path."""
        app = _make_app()
        client = TestClient(app)

        with patch("src.api.middleware.audit.log_audit_event_async", new_callable=AsyncMock) as mock_log:
            client.post("/api/v1/other")
            call_kwargs = mock_log.call_args.kwargs
            assert call_kwargs["path"] == "/api/v1/other"


# ---------------------------------------------------------------------------
# User identity extraction
# ---------------------------------------------------------------------------


class TestUserExtraction:
    """Middleware extracts user identity from request.state.user."""

    def test_user_id_extracted_from_state(self) -> None:
        """When request.state.user exists, its .id should be logged."""
        user_id = uuid.uuid4()
        mock_user = MagicMock()
        mock_user.id = user_id

        app = _make_app(user=mock_user)
        client = TestClient(app)

        with patch("src.api.middleware.audit.log_audit_event_async", new_callable=AsyncMock) as mock_log:
            client.post("/api/v1/other")
            call_kwargs = mock_log.call_args.kwargs
            assert call_kwargs["user_id"] == str(user_id)

    def test_anonymous_user_when_no_state(self) -> None:
        """When no user is in request.state, user_id should be 'anonymous'."""
        # No user injected into state
        app = _make_app(user=None)
        client = TestClient(app)

        with patch("src.api.middleware.audit.log_audit_event_async", new_callable=AsyncMock) as mock_log:
            client.post("/api/v1/other")
            call_kwargs = mock_log.call_args.kwargs
            assert call_kwargs["user_id"] == "anonymous"


# ---------------------------------------------------------------------------
# Engagement ID extraction
# ---------------------------------------------------------------------------


class TestEngagementExtraction:
    """Middleware extracts engagement_id from URL paths containing /engagements/{uuid}."""

    def test_engagement_id_extracted_from_path(self) -> None:
        """engagement_id should be extracted from /engagements/{id}/... paths."""
        engagement_id = str(uuid.uuid4())
        app = _make_app()
        client = TestClient(app)

        with patch("src.api.middleware.audit.log_audit_event_async", new_callable=AsyncMock) as mock_log:
            client.post(f"/api/v1/engagements/{engagement_id}/items")
            call_kwargs = mock_log.call_args.kwargs
            assert call_kwargs["engagement_id"] == engagement_id

    def test_no_engagement_id_for_non_engagement_path(self) -> None:
        """engagement_id should be None for paths without /engagements/."""
        app = _make_app()
        client = TestClient(app)

        with patch("src.api.middleware.audit.log_audit_event_async", new_callable=AsyncMock) as mock_log:
            client.post("/api/v1/other")
            call_kwargs = mock_log.call_args.kwargs
            assert call_kwargs["engagement_id"] is None


# ---------------------------------------------------------------------------
# Duration measurement
# ---------------------------------------------------------------------------


class TestDurationMeasurement:
    """Middleware measures request duration."""

    def test_duration_ms_is_non_negative(self) -> None:
        """duration_ms passed to log_audit_event_async should be >= 0."""
        app = _make_app()
        client = TestClient(app)

        with patch("src.api.middleware.audit.log_audit_event_async", new_callable=AsyncMock) as mock_log:
            client.post("/api/v1/other")
            call_kwargs = mock_log.call_args.kwargs
            assert call_kwargs["duration_ms"] >= 0.0

    def test_duration_ms_is_float(self) -> None:
        """duration_ms should be a float value."""
        app = _make_app()
        client = TestClient(app)

        with patch("src.api.middleware.audit.log_audit_event_async", new_callable=AsyncMock) as mock_log:
            client.post("/api/v1/other")
            call_kwargs = mock_log.call_args.kwargs
            assert isinstance(call_kwargs["duration_ms"], float)


# ---------------------------------------------------------------------------
# Audit persistence failures don't block requests
# ---------------------------------------------------------------------------


class TestAuditPersistenceFailure:
    """Audit persistence errors must not break the HTTP response."""

    def test_audit_failure_does_not_break_response(self) -> None:
        """If log_audit_event_async raises, the response still completes."""
        app = _make_app()
        client = TestClient(app)

        with patch(
            "src.api.middleware.audit.log_audit_event_async",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB unavailable"),
        ):
            response = client.post("/api/v1/other")
            # Response still completes successfully
            assert response.status_code == 200
            # Header still set even on failure
            assert response.headers.get("X-Audit-Logged") == "true"
