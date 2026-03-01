"""Route-level tests for Republish Cycle and Version Diff (Story #361).

Tests the POST /republish and GET /diff endpoints.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.routes.auth import get_current_user
from src.core.models import ProcessElement, ProcessModel, ProcessModelStatus, User, UserRole
from src.core.permissions import require_engagement_access

ENGAGEMENT_ID = uuid.uuid4()
POV_V1_ID = uuid.uuid4()
POV_V2_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _mock_user() -> User:
    user = MagicMock(spec=User)
    user.id = USER_ID
    user.email = "lead@example.com"
    user.role = UserRole.ENGAGEMENT_LEAD
    return user


def _make_app(mock_session: AsyncMock) -> TestClient:
    app = create_app()
    app.state.neo4j_driver = MagicMock()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    app.dependency_overrides[require_engagement_access] = lambda: _mock_user()
    return TestClient(app)


def _mock_pov(
    pov_id: uuid.UUID | None = None,
    version: int = 1,
) -> MagicMock:
    pov = MagicMock(spec=ProcessModel)
    pov.id = pov_id or POV_V1_ID
    pov.engagement_id = ENGAGEMENT_ID
    pov.version = version
    pov.scope = "Process A"
    pov.status = ProcessModelStatus.COMPLETED
    pov.confidence_score = 0.75
    pov.element_count = 3
    pov.evidence_count = 10
    pov.metadata_json = {}
    pov.generated_by = "consensus_algorithm"
    return pov


def _mock_element(
    element_id: str = "e1",
    name: str = "Task A",
    element_type: str = "activity",
    confidence_score: float = 0.7,
) -> MagicMock:
    el = MagicMock(spec=ProcessElement)
    el.id = uuid.uuid4()
    el.name = name
    el.element_type = MagicMock(value=element_type)
    el.confidence_score = confidence_score
    el.evidence_grade = MagicMock(value="C")
    el.brightness_classification = MagicMock(value="DIM")
    el.evidence_count = 2
    el.evidence_ids = ["ev_1"]
    el.created_at = datetime(2026, 2, 27, tzinfo=UTC)
    return el


# ── Republish Endpoint ───────────────────────────────────────────────


class TestRepublish:
    """POST /api/v1/validation/republish"""

    def _setup_session(
        self,
        pov: MagicMock | None = None,
        elements: list[MagicMock] | None = None,
        decisions: list[MagicMock] | None = None,
    ) -> AsyncMock:
        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            result = AsyncMock()
            if call_count == 1:
                # POV lookup
                result.scalar_one_or_none = MagicMock(return_value=pov)
            elif call_count == 2:
                # Elements query
                mock_scalars = MagicMock()
                mock_scalars.all = MagicMock(return_value=elements or [])
                result.scalars = MagicMock(return_value=mock_scalars)
            elif call_count == 3:
                # Decisions query
                mock_scalars = MagicMock()
                mock_scalars.all = MagicMock(return_value=decisions or [])
                result.scalars = MagicMock(return_value=mock_scalars)
            return result

        session = AsyncMock()
        session.execute = mock_execute
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        return session

    def test_returns_201_on_successful_republish(self) -> None:
        pov = _mock_pov()
        elements = [_mock_element("e1", "Task A"), _mock_element("e2", "Task B")]
        session = self._setup_session(pov=pov, elements=elements, decisions=[])

        client = _make_app(session)
        resp = client.post(
            "/api/v1/validation/republish",
            json={
                "pov_version_id": str(POV_V1_ID),
                "engagement_id": str(ENGAGEMENT_ID),
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["new_version_number"] == 2
        assert data["total_elements"] == 2
        assert "changes_summary" in data

    def test_returns_404_for_missing_pov(self) -> None:
        session = self._setup_session(pov=None)
        client = _make_app(session)
        resp = client.post(
            "/api/v1/validation/republish",
            json={
                "pov_version_id": str(uuid.uuid4()),
                "engagement_id": str(ENGAGEMENT_ID),
            },
        )
        assert resp.status_code == 404


# ── Diff Endpoint ────────────────────────────────────────────────────


class TestVersionDiff:
    """GET /api/v1/validation/diff"""

    def _setup_session(
        self,
        v1_pov: MagicMock | None = None,
        v2_pov: MagicMock | None = None,
        v1_elements: list[MagicMock] | None = None,
        v2_elements: list[MagicMock] | None = None,
    ) -> AsyncMock:
        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            result = AsyncMock()
            if call_count == 1:
                result.scalar_one_or_none = MagicMock(return_value=v1_pov)
            elif call_count == 2:
                result.scalar_one_or_none = MagicMock(return_value=v2_pov)
            elif call_count == 3:
                mock_scalars = MagicMock()
                mock_scalars.all = MagicMock(return_value=v1_elements or [])
                result.scalars = MagicMock(return_value=mock_scalars)
            elif call_count == 4:
                mock_scalars = MagicMock()
                mock_scalars.all = MagicMock(return_value=v2_elements or [])
                result.scalars = MagicMock(return_value=mock_scalars)
            return result

        session = AsyncMock()
        session.execute = mock_execute
        return session

    def test_returns_200_with_diff(self) -> None:
        v1_pov = _mock_pov(POV_V1_ID, version=1)
        v2_pov = _mock_pov(POV_V2_ID, version=2)
        v1_els = [_mock_element("e1", "Task A")]
        v2_els = [_mock_element("e1", "Task A"), _mock_element("e2", "Task B")]

        session = self._setup_session(v1_pov, v2_pov, v1_els, v2_els)
        client = _make_app(session)
        resp = client.get(f"/api/v1/validation/diff?v1={POV_V1_ID}&v2={POV_V2_ID}&engagement_id={ENGAGEMENT_ID}")
        assert resp.status_code == 200
        data = resp.json()
        assert "added" in data
        assert "removed" in data
        assert "modified" in data
        assert "total_changes" in data
        assert data["v1_id"] == str(POV_V1_ID)
        assert data["v2_id"] == str(POV_V2_ID)

    def test_returns_404_for_missing_v1(self) -> None:
        session = self._setup_session(v1_pov=None)
        client = _make_app(session)
        resp = client.get(f"/api/v1/validation/diff?v1={uuid.uuid4()}&v2={POV_V2_ID}&engagement_id={ENGAGEMENT_ID}")
        assert resp.status_code == 404

    def test_returns_404_for_missing_v2(self) -> None:
        v1_pov = _mock_pov(POV_V1_ID)
        session = self._setup_session(v1_pov=v1_pov, v2_pov=None)
        client = _make_app(session)
        resp = client.get(f"/api/v1/validation/diff?v1={POV_V1_ID}&v2={uuid.uuid4()}&engagement_id={ENGAGEMENT_ID}")
        assert resp.status_code == 404

    def test_diff_includes_color_coding(self) -> None:
        """Verify BPMN color-coding in diff response."""
        v1_pov = _mock_pov(POV_V1_ID)
        v2_pov = _mock_pov(POV_V2_ID)
        v1_els: list[MagicMock] = []
        v2_els = [_mock_element("e1", "New Task")]

        session = self._setup_session(v1_pov, v2_pov, v1_els, v2_els)
        client = _make_app(session)
        resp = client.get(f"/api/v1/validation/diff?v1={POV_V1_ID}&v2={POV_V2_ID}&engagement_id={ENGAGEMENT_ID}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["added"]) == 1
        assert data["added"][0]["color"] == "#28a745"
        assert data["added"][0]["css_class"] == "diff-added"

    def test_requires_engagement_id(self) -> None:
        session = AsyncMock()
        client = _make_app(session)
        resp = client.get(f"/api/v1/validation/diff?v1={POV_V1_ID}&v2={POV_V2_ID}")
        assert resp.status_code == 422
