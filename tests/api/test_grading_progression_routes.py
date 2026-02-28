"""Route-level tests for grading progression endpoint (Story #357)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.routes.auth import get_current_user
from src.core.models import User, UserRole
from src.core.models.grading_snapshot import GradingSnapshot
from src.core.permissions import require_engagement_access

ENGAGEMENT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _mock_user(role: UserRole = UserRole.ENGAGEMENT_LEAD) -> User:
    user = MagicMock(spec=User)
    user.id = USER_ID
    user.email = "lead@example.com"
    user.role = role
    return user


def _make_app(mock_session: AsyncMock) -> TestClient:
    app = create_app()
    app.state.neo4j_driver = MagicMock()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    app.dependency_overrides[require_engagement_access] = lambda: _mock_user()
    return TestClient(app)


def _mock_snapshot(
    version_number: int,
    grade_u: int = 0,
    grade_d: int = 0,
    grade_c: int = 0,
    grade_b: int = 0,
    grade_a: int = 0,
) -> MagicMock:
    snap = MagicMock(spec=GradingSnapshot)
    snap.version_number = version_number
    snap.pov_version_id = uuid.uuid4()
    snap.grade_u = grade_u
    snap.grade_d = grade_d
    snap.grade_c = grade_c
    snap.grade_b = grade_b
    snap.grade_a = grade_a
    snap.total_elements = grade_u + grade_d + grade_c + grade_b + grade_a
    snap.snapshot_at = datetime(2026, 2, 27, tzinfo=UTC)
    return snap


class TestGradingProgression:
    """GET /api/v1/validation/grading-progression"""

    def test_returns_200_with_versions(self) -> None:
        snaps = [
            _mock_snapshot(1, grade_d=10),
            _mock_snapshot(2, grade_d=7, grade_c=3),
        ]
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=snaps)
        mock_result = AsyncMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        client = _make_app(mock_session)
        resp = client.get(
            f"/api/v1/validation/grading-progression?engagement_id={ENGAGEMENT_ID}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["versions"]) == 2
        assert data["improvement_target"] == 20.0

        # First version has no improvement
        assert data["versions"][0]["improvement_pct"] is None
        # Second version shows improvement
        assert data["versions"][1]["improvement_pct"] > 0

    def test_returns_200_empty_when_no_snapshots(self) -> None:
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[])
        mock_result = AsyncMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        client = _make_app(mock_session)
        resp = client.get(
            f"/api/v1/validation/grading-progression?engagement_id={ENGAGEMENT_ID}"
        )
        assert resp.status_code == 200
        assert resp.json()["versions"] == []

    def test_response_includes_grade_counts(self) -> None:
        snaps = [_mock_snapshot(1, grade_u=2, grade_d=3, grade_c=3, grade_b=1, grade_a=1)]
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=snaps)
        mock_result = AsyncMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        client = _make_app(mock_session)
        resp = client.get(
            f"/api/v1/validation/grading-progression?engagement_id={ENGAGEMENT_ID}"
        )
        v = resp.json()["versions"][0]
        assert v["grade_counts"] == {"U": 2, "D": 3, "C": 3, "B": 1, "A": 1}
        assert v["total_elements"] == 10

    def test_requires_engagement_id(self) -> None:
        mock_session = AsyncMock()
        client = _make_app(mock_session)
        resp = client.get("/api/v1/validation/grading-progression")
        assert resp.status_code == 422  # Missing required query param
