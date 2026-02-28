"""Route-level tests for Best Practices Library and Benchmarking (Story #363).

Tests the enhanced best-practices search, percentile ranking, and gap recommendations.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.routes.auth import get_current_user
from src.core.models import (
    Benchmark,
    BestPractice,
    Engagement,
    GapAnalysisResult,
    TOMDimension,
    User,
    UserRole,
)
from src.core.permissions import require_engagement_access

ENGAGEMENT_ID = uuid.uuid4()
GAP_ID = uuid.uuid4()
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


# ── Best Practices Search (Scenario 1) ───────────────────────────────


class TestBestPracticesSearch:
    """GET /api/v1/tom/best-practices with domain/industry filters."""

    def _setup_session(self, practices: list[MagicMock] | None = None) -> AsyncMock:
        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            result = AsyncMock()
            if call_count == 1:
                # Main query
                mock_scalars = MagicMock()
                mock_scalars.all = MagicMock(return_value=practices or [])
                result.scalars = MagicMock(return_value=mock_scalars)
            elif call_count == 2:
                # Count query
                result.scalar = MagicMock(return_value=len(practices or []))
            return result

        session = AsyncMock()
        session.execute = mock_execute
        return session

    def _mock_practice(
        self,
        title: str = "Auto Exception Handling",
        domain: str = "Loan Origination",
        industry: str = "Financial Services",
    ) -> MagicMock:
        bp = MagicMock(spec=BestPractice)
        bp.id = uuid.uuid4()
        bp.title = title
        bp.domain = domain
        bp.industry = industry
        bp.description = "Automated exception handling"
        bp.source = "Industry Report 2025"
        bp.tom_dimension = TOMDimension.PROCESS_ARCHITECTURE
        bp.maturity_level_applicable = 3
        bp.created_at = datetime(2026, 2, 27, tzinfo=UTC)
        return bp

    def test_returns_practices_with_domain_filter(self) -> None:
        """Scenario 1: search with industry and domain filters."""
        practices = [self._mock_practice()]
        session = self._setup_session(practices)
        client = _make_app(session)
        resp = client.get(
            "/api/v1/tom/best-practices?industry=Financial+Services&domain=Loan+Origination"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert "title" in item
        assert "maturity_level_applicable" in item

    def test_returns_empty_when_no_match(self) -> None:
        session = self._setup_session([])
        client = _make_app(session)
        resp = client.get("/api/v1/tom/best-practices?industry=Energy")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0


# ── Percentile Ranking (Scenario 2) ──────────────────────────────────


class TestPercentileRanking:
    """GET /api/v1/tom/engagements/{id}/benchmarks."""

    def _setup_session(
        self,
        engagement: MagicMock | None = None,
        benchmarks: list[MagicMock] | None = None,
    ) -> AsyncMock:
        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            result = AsyncMock()
            if call_count == 1:
                # Engagement lookup
                result.scalar_one_or_none = MagicMock(return_value=engagement)
            elif call_count == 2:
                # Benchmarks query
                mock_scalars = MagicMock()
                mock_scalars.all = MagicMock(return_value=benchmarks or [])
                result.scalars = MagicMock(return_value=mock_scalars)
            return result

        session = AsyncMock()
        session.execute = mock_execute
        return session

    def _mock_engagement(self, client_metrics: dict | None = None) -> MagicMock:
        eng = MagicMock(spec=Engagement)
        eng.id = ENGAGEMENT_ID
        eng.metadata_json = {"client_metrics": client_metrics or {}}
        return eng

    def _mock_benchmark(
        self,
        metric_name: str = "processing_time",
        p25: float = 3.0,
        p50: float = 5.0,
        p75: float = 8.0,
        p90: float = 12.0,
    ) -> MagicMock:
        bm = MagicMock(spec=Benchmark)
        bm.id = uuid.uuid4()
        bm.metric_name = metric_name
        bm.industry = "Financial Services"
        bm.p25 = p25
        bm.p50 = p50
        bm.p75 = p75
        bm.p90 = p90
        return bm

    def test_returns_percentile_ranking(self) -> None:
        """Scenario 2: client value 6 days against p25=3/p50=5/p75=8/p90=12."""
        engagement = self._mock_engagement({"processing_time": 6.0})
        benchmarks = [self._mock_benchmark()]
        session = self._setup_session(engagement, benchmarks)
        client = _make_app(session)

        resp = client.get(
            f"/api/v1/tom/engagements/{ENGAGEMENT_ID}/benchmarks?metric=processing_time"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["engagement_id"] == str(ENGAGEMENT_ID)
        assert len(data["rankings"]) == 1
        ranking = data["rankings"][0]
        assert ranking["metric_name"] == "processing_time"
        assert ranking["client_value"] == 6.0
        assert ranking["percentile_label"] == "Between p50 and p75"
        assert ranking["distribution"] == {"p25": 3.0, "p50": 5.0, "p75": 8.0, "p90": 12.0}

    def test_returns_404_when_no_engagement(self) -> None:
        session = self._setup_session(engagement=None)
        client = _make_app(session)
        resp = client.get(f"/api/v1/tom/engagements/{uuid.uuid4()}/benchmarks")
        assert resp.status_code == 404

    def test_returns_404_when_no_benchmarks(self) -> None:
        engagement = self._mock_engagement()
        session = self._setup_session(engagement, [])
        client = _make_app(session)
        resp = client.get(f"/api/v1/tom/engagements/{ENGAGEMENT_ID}/benchmarks")
        assert resp.status_code == 404

    def test_empty_rankings_when_no_client_metrics(self) -> None:
        """Client has no metric data — returns empty rankings list."""
        engagement = self._mock_engagement({})
        benchmarks = [self._mock_benchmark()]
        session = self._setup_session(engagement, benchmarks)
        client = _make_app(session)
        resp = client.get(f"/api/v1/tom/engagements/{ENGAGEMENT_ID}/benchmarks")
        assert resp.status_code == 200
        assert len(resp.json()["rankings"]) == 0


# ── Gap Recommendations (Scenario 3) ─────────────────────────────────


class TestGapRecommendations:
    """GET /api/v1/tom/gap-findings/{id}/recommendations."""

    def _setup_session(
        self,
        gap: MagicMock | None = None,
        practices: list[MagicMock] | None = None,
    ) -> AsyncMock:
        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            result = AsyncMock()
            if call_count == 1:
                # Gap lookup
                result.scalar_one_or_none = MagicMock(return_value=gap)
            elif call_count == 2:
                # Best practices query
                mock_scalars = MagicMock()
                mock_scalars.all = MagicMock(return_value=practices or [])
                result.scalars = MagicMock(return_value=mock_scalars)
            return result

        session = AsyncMock()
        session.execute = mock_execute
        return session

    def _mock_gap(self) -> MagicMock:
        gap = MagicMock(spec=GapAnalysisResult)
        gap.id = GAP_ID
        gap.engagement_id = ENGAGEMENT_ID
        gap.rationale = "manual exception logging"
        gap.dimension = MagicMock(value="process_architecture")
        gap.gap_type = MagicMock(value="missing_capability")
        return gap

    def _mock_best_practice(self) -> MagicMock:
        bp = MagicMock(spec=BestPractice)
        bp.id = uuid.uuid4()
        bp.title = "Automated Exception Handling and Alerting"
        bp.domain = "Loan Origination"
        bp.industry = "Financial Services"
        bp.description = "Implement automated exception handling and alerting for process deviations"
        bp.tom_dimension = TOMDimension.PROCESS_ARCHITECTURE
        return bp

    def test_returns_recommendations(self) -> None:
        """Scenario 3: gap matched to relevant best practice."""
        gap = self._mock_gap()
        practices = [self._mock_best_practice()]
        session = self._setup_session(gap, practices)
        client = _make_app(session)

        resp = client.get(
            f"/api/v1/tom/gap-findings/{GAP_ID}/recommendations"
            f"?engagement_id={ENGAGEMENT_ID}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["gap_id"] == str(GAP_ID)
        assert data["gap_dimension"] == "process_architecture"
        assert len(data["recommendations"]) >= 1
        rec = data["recommendations"][0]
        assert rec["practice_title"] == "Automated Exception Handling and Alerting"
        assert rec["relevance_score"] > 0

    def test_returns_404_for_missing_gap(self) -> None:
        session = self._setup_session(gap=None)
        client = _make_app(session)
        resp = client.get(
            f"/api/v1/tom/gap-findings/{uuid.uuid4()}/recommendations"
            f"?engagement_id={ENGAGEMENT_ID}"
        )
        assert resp.status_code == 404

    def test_requires_engagement_id(self) -> None:
        session = AsyncMock()
        client = _make_app(session)
        resp = client.get(f"/api/v1/tom/gap-findings/{GAP_ID}/recommendations")
        assert resp.status_code == 422

    def test_empty_recommendations_no_practices(self) -> None:
        """No practices in DB returns empty recommendations."""
        gap = self._mock_gap()
        session = self._setup_session(gap, [])
        client = _make_app(session)
        resp = client.get(
            f"/api/v1/tom/gap-findings/{GAP_ID}/recommendations"
            f"?engagement_id={ENGAGEMENT_ID}"
        )
        assert resp.status_code == 200
        assert len(resp.json()["recommendations"]) == 0
