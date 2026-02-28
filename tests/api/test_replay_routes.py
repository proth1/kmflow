"""Route-level tests for replay API endpoints (Story #345)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.routes.auth import get_current_user
from src.core.models import User, UserRole
from src.core.services.replay_service import clear_task_store


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


class TestSingleCaseReplay:
    """POST /api/v1/replay/single-case."""

    def setup_method(self) -> None:
        clear_task_store()

    def test_returns_202_with_task_id(self) -> None:
        client = _make_client()
        resp = client.post(
            "/api/v1/replay/single-case",
            json={"case_id": "CASE-001"},
        )

        assert resp.status_code == 202
        data = resp.json()
        assert "task_id" in data
        assert data["status"] == "completed"
        assert data["replay_type"] == "single_case"

    def test_missing_case_id_returns_422(self) -> None:
        client = _make_client()
        resp = client.post("/api/v1/replay/single-case", json={})

        assert resp.status_code == 422


class TestAggregateReplay:
    """POST /api/v1/replay/aggregate."""

    def setup_method(self) -> None:
        clear_task_store()

    def test_returns_202(self) -> None:
        client = _make_client()
        resp = client.post(
            "/api/v1/replay/aggregate",
            json={
                "engagement_id": "eng-1",
                "time_range_start": "2026-01-01",
                "time_range_end": "2026-01-31",
                "interval_granularity": "daily",
            },
        )

        assert resp.status_code == 202
        data = resp.json()
        assert data["replay_type"] == "aggregate"

    def test_missing_fields_returns_422(self) -> None:
        client = _make_client()
        resp = client.post(
            "/api/v1/replay/aggregate",
            json={"engagement_id": "eng-1"},
        )

        assert resp.status_code == 422

    def test_invalid_granularity_returns_422(self) -> None:
        client = _make_client()
        resp = client.post(
            "/api/v1/replay/aggregate",
            json={
                "engagement_id": "eng-1",
                "time_range_start": "2026-01-01",
                "time_range_end": "2026-01-31",
                "interval_granularity": "every-5-mins",
            },
        )

        assert resp.status_code == 422

    def test_invalid_date_returns_422(self) -> None:
        client = _make_client()
        resp = client.post(
            "/api/v1/replay/aggregate",
            json={
                "engagement_id": "eng-1",
                "time_range_start": "not-a-date",
                "time_range_end": "2026-01-31",
            },
        )

        assert resp.status_code == 422


class TestVariantComparisonReplay:
    """POST /api/v1/replay/variant-comparison."""

    def setup_method(self) -> None:
        clear_task_store()

    def test_returns_202(self) -> None:
        client = _make_client()
        resp = client.post(
            "/api/v1/replay/variant-comparison",
            json={"variant_a_id": "var-A", "variant_b_id": "var-B"},
        )

        assert resp.status_code == 202
        data = resp.json()
        assert data["replay_type"] == "variant_comparison"

    def test_missing_variant_id_returns_422(self) -> None:
        client = _make_client()
        resp = client.post(
            "/api/v1/replay/variant-comparison",
            json={"variant_a_id": "var-A"},
        )

        assert resp.status_code == 422


class TestReplayStatus:
    """GET /api/v1/replay/{id}/status."""

    def setup_method(self) -> None:
        clear_task_store()

    def test_returns_status(self) -> None:
        client = _make_client()
        # Create a task first
        create_resp = client.post(
            "/api/v1/replay/single-case",
            json={"case_id": "CASE-001"},
        )
        task_id = create_resp.json()["task_id"]

        resp = client.get(f"/api/v1/replay/{task_id}/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == task_id
        assert "status" in data
        assert "progress_pct" in data

    def test_unknown_task_returns_404(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/replay/nonexistent/status")

        assert resp.status_code == 404


class TestReplayFrames:
    """GET /api/v1/replay/{id}/frames."""

    def setup_method(self) -> None:
        clear_task_store()

    def test_returns_paginated_frames(self) -> None:
        client = _make_client()
        create_resp = client.post(
            "/api/v1/replay/single-case",
            json={"case_id": "CASE-001"},
        )
        task_id = create_resp.json()["task_id"]

        resp = client.get(f"/api/v1/replay/{task_id}/frames?limit=10&offset=0")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["frames"]) == 10
        assert data["total"] == 20
        assert data["has_more"] is True

    def test_second_page(self) -> None:
        client = _make_client()
        create_resp = client.post(
            "/api/v1/replay/single-case",
            json={"case_id": "CASE-001"},
        )
        task_id = create_resp.json()["task_id"]

        resp = client.get(f"/api/v1/replay/{task_id}/frames?limit=10&offset=10")

        assert resp.status_code == 200
        data = resp.json()
        assert data["has_more"] is False

    def test_offset_beyond_total_returns_empty(self) -> None:
        client = _make_client()
        create_resp = client.post(
            "/api/v1/replay/single-case",
            json={"case_id": "CASE-001"},
        )
        task_id = create_resp.json()["task_id"]

        resp = client.get(f"/api/v1/replay/{task_id}/frames?limit=10&offset=100")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["frames"]) == 0
        assert data["has_more"] is False

    def test_unknown_task_returns_404(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/replay/nonexistent/frames")

        assert resp.status_code == 404

    def test_full_lifecycle(self) -> None:
        """Integration test: POST → poll status → GET frames."""
        client = _make_client()

        # 1. Create task
        create_resp = client.post(
            "/api/v1/replay/single-case",
            json={"case_id": "LIFECYCLE-001"},
        )
        assert create_resp.status_code == 202
        task_id = create_resp.json()["task_id"]

        # 2. Check status
        status_resp = client.get(f"/api/v1/replay/{task_id}/status")
        assert status_resp.status_code == 200

        # 3. Get frames
        frames_resp = client.get(f"/api/v1/replay/{task_id}/frames?limit=5&offset=0")
        assert frames_resp.status_code == 200
        data = frames_resp.json()
        assert len(data["frames"]) == 5
        assert data["total"] == 20
