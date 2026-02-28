"""Route-level tests for Seed List Coverage and Dark Room Backlog (Story #367).

Tests the coverage and dark room backlog endpoints.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.routes.auth import get_current_user
from src.core.models import ProcessElement, ProcessModel, ProcessModelStatus, User, UserRole
from src.core.models.pov import BrightnessClassification, EvidenceGrade, ProcessElementType
from src.core.models.seed_term import SeedTerm, TermCategory, TermSource, TermStatus
from src.core.permissions import require_engagement_access

ENGAGEMENT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
POV_ID = uuid.uuid4()


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


def _mock_seed_term(term_id: str = "t1", term: str = "Login", status: TermStatus = TermStatus.ACTIVE) -> MagicMock:
    t = MagicMock(spec=SeedTerm)
    t.id = uuid.UUID(int=int(term_id.replace("t", ""))) if term_id.startswith("t") else uuid.uuid4()
    t.engagement_id = ENGAGEMENT_ID
    t.term = term
    t.domain = "general"
    t.category = TermCategory.ACTIVITY
    t.source = TermSource.CONSULTANT_PROVIDED
    t.status = status
    return t


def _mock_pov(version: int = 1) -> MagicMock:
    pov = MagicMock(spec=ProcessModel)
    pov.id = POV_ID
    pov.engagement_id = ENGAGEMENT_ID
    pov.version = version
    pov.status = ProcessModelStatus.COMPLETED
    return pov


def _mock_element(
    name: str = "Login",
    confidence: float = 0.2,
    evidence_count: int = 0,
    evidence_grade: EvidenceGrade = EvidenceGrade.U,
) -> MagicMock:
    el = MagicMock(spec=ProcessElement)
    el.id = uuid.uuid4()
    el.name = name
    el.element_type = ProcessElementType.ACTIVITY
    el.confidence_score = confidence
    el.evidence_count = evidence_count
    el.evidence_grade = evidence_grade
    el.brightness_classification = BrightnessClassification.DARK
    return el


# ── Seed List Coverage ───────────────────────────────────────────────


class TestSeedListCoverage:
    """GET /api/v1/engagements/{id}/seed-list/coverage"""

    def _setup_session(
        self,
        terms: list[MagicMock] | None = None,
        pov: MagicMock | None = None,
        elements: list[MagicMock] | None = None,
    ) -> AsyncMock:
        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            result = AsyncMock()
            if call_count == 1:
                # Seed terms query
                mock_scalars = MagicMock()
                mock_scalars.all = MagicMock(return_value=terms or [])
                result.scalars = MagicMock(return_value=mock_scalars)
            elif call_count == 2:
                # Latest POV query
                result.scalar_one_or_none = MagicMock(return_value=pov)
            elif call_count == 3:
                # Elements query (only if POV found)
                mock_scalars = MagicMock()
                mock_scalars.all = MagicMock(return_value=elements or [])
                result.scalars = MagicMock(return_value=mock_scalars)
            return result

        session = AsyncMock()
        session.execute = mock_execute
        return session

    def test_returns_coverage_with_uncovered_terms(self) -> None:
        """Returns correct coverage when some terms are uncovered."""
        terms = [
            _mock_seed_term("t1", "Login"),
            _mock_seed_term("t2", "Logout"),
            _mock_seed_term("t3", "Register"),
        ]
        pov = _mock_pov()
        elements = [_mock_element("Login", confidence=0.8)]

        session = self._setup_session(terms, pov, elements)
        client = _make_app(session)
        resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/seed-list/coverage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_terms"] == 3
        assert data["covered_count"] >= 1
        assert "uncovered_terms" in data

    def test_returns_zero_coverage_when_no_pov(self) -> None:
        """No POV → all terms uncovered."""
        terms = [_mock_seed_term("t1", "Login")]
        session = self._setup_session(terms, pov=None)
        client = _make_app(session)
        resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/seed-list/coverage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_terms"] == 1
        assert data["covered_count"] == 0
        assert data["coverage_percentage"] == 0.0

    def test_returns_empty_when_no_terms(self) -> None:
        session = self._setup_session([], pov=None)
        client = _make_app(session)
        resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/seed-list/coverage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_terms"] == 0


# ── Dark Room Backlog ────────────────────────────────────────────────


class TestDarkRoomBacklog:
    """GET /api/v1/engagements/{id}/dark-room/backlog"""

    def _setup_session(
        self,
        pov: MagicMock | None = None,
        elements: list[MagicMock] | None = None,
    ) -> AsyncMock:
        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            result = AsyncMock()
            if call_count == 1:
                # Latest POV
                result.scalar_one_or_none = MagicMock(return_value=pov)
            elif call_count == 2:
                # Elements
                mock_scalars = MagicMock()
                mock_scalars.all = MagicMock(return_value=elements or [])
                result.scalars = MagicMock(return_value=mock_scalars)
            return result

        session = AsyncMock()
        session.execute = mock_execute
        return session

    def test_returns_dark_segments_sorted_by_uplift(self) -> None:
        """Dark segments are returned sorted by estimated uplift descending."""
        pov = _mock_pov()
        elements = [
            _mock_element("Task A", confidence=0.1, evidence_count=0),
            _mock_element("Task B", confidence=0.3, evidence_count=1, evidence_grade=EvidenceGrade.D),
            _mock_element("Task C", confidence=0.8),  # Above threshold, excluded
        ]
        session = self._setup_session(pov, elements)
        client = _make_app(session)
        resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/dark-room/backlog")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_dark"] == 2
        assert len(data["segments"]) == 2
        # First segment should have higher uplift (lower confidence)
        assert data["segments"][0]["estimated_uplift"] >= data["segments"][1]["estimated_uplift"]

    def test_segments_include_actions(self) -> None:
        """Each segment includes missing knowledge forms and recommended actions."""
        pov = _mock_pov()
        elements = [_mock_element("Dark Task", confidence=0.1, evidence_count=0)]
        session = self._setup_session(pov, elements)
        client = _make_app(session)
        resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/dark-room/backlog")
        assert resp.status_code == 200
        seg = resp.json()["segments"][0]
        assert "missing_knowledge_forms" in seg
        assert "recommended_actions" in seg
        assert len(seg["missing_knowledge_forms"]) >= 1
        assert len(seg["recommended_actions"]) >= 1

    def test_returns_empty_when_no_pov(self) -> None:
        session = self._setup_session(pov=None)
        client = _make_app(session)
        resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/dark-room/backlog")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_dark"] == 0
        assert len(data["segments"]) == 0

    def test_returns_empty_when_all_bright(self) -> None:
        """All elements above threshold → no dark segments."""
        pov = _mock_pov()
        elements = [_mock_element("Bright Task", confidence=0.9)]
        session = self._setup_session(pov, elements)
        client = _make_app(session)
        resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/dark-room/backlog")
        assert resp.status_code == 200
        assert resp.json()["total_dark"] == 0

    def test_custom_threshold(self) -> None:
        """Custom threshold changes which elements are dark."""
        pov = _mock_pov()
        elements = [_mock_element("Mid Task", confidence=0.5)]
        session = self._setup_session(pov, elements)
        client = _make_app(session)
        # Default threshold 0.40 → 0.5 is above, excluded
        resp1 = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/dark-room/backlog")
        assert resp1.json()["total_dark"] == 0
        # Custom threshold 0.60 → 0.5 is below, included
        session2 = self._setup_session(pov, elements)
        client2 = _make_app(session2)
        resp2 = client2.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/dark-room/backlog?threshold=0.6")
        assert resp2.json()["total_dark"] == 1
