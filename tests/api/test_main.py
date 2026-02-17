"""Tests for the FastAPI application creation."""

from __future__ import annotations

from src.api.main import create_app


class TestAppCreation:
    """Test suite for FastAPI app factory."""

    def test_create_app_returns_fastapi(self) -> None:
        """create_app should return a FastAPI instance."""
        from fastapi import FastAPI

        app = create_app()
        assert isinstance(app, FastAPI)

    def test_app_metadata(self) -> None:
        """App should have correct metadata."""
        app = create_app()
        assert app.title == "KMFlow"
        assert app.version == "0.1.0"

    def test_app_has_docs(self) -> None:
        """App should have OpenAPI docs enabled."""
        app = create_app()
        assert app.docs_url == "/docs"
        assert app.redoc_url == "/redoc"

    def test_routes_registered(self) -> None:
        """App should have health and engagement routes."""
        app = create_app()
        route_paths = [route.path for route in app.routes]
        assert "/health" in route_paths
        assert "/api/v1/engagements/" in route_paths
        assert "/api/v1/engagements/{engagement_id}" in route_paths

    def test_cors_middleware_configured(self) -> None:
        """App should have CORS middleware."""
        app = create_app()
        middleware_classes = [m.cls.__name__ for m in app.user_middleware]
        assert "CORSMiddleware" in middleware_classes
