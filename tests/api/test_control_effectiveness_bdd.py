"""BDD tests for Story #336 — Control Effectiveness Scoring Engine.

Scenario 1: HIGHLY_EFFECTIVE Rating from Strong Evidence
Scenario 2: INEFFECTIVE Rating from Sparse Evidence
Scenario 3: Historical Scores Preserved on Recalculation
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest import mock
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import create_app
from src.core.auth import get_current_user
from src.core.models import (
    ControlEffectiveness,
    User,
    UserRole,
)
from src.governance.effectiveness import (
    ControlEffectivenessScoringService,
    classify_effectiveness,
    generate_recommendation,
)

ENGAGEMENT_ID = uuid.uuid4()
CONTROL_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _mock_user() -> User:
    u = MagicMock(spec=User)
    u.id = USER_ID
    u.role = UserRole.PLATFORM_ADMIN
    return u


def _make_plain_mock(**kwargs: Any) -> MagicMock:
    """Create a MagicMock that stores kwargs as regular attributes."""
    m = MagicMock()
    if "id" not in kwargs:
        m.id = uuid.uuid4()
    for k, v in kwargs.items():
        setattr(m, k, v)
    return m


def _make_app_with_session(mock_session: AsyncMock) -> Any:
    """Create app with overridden dependencies."""
    from src.api.deps import get_session

    app = create_app()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    return app


# ---------------------------------------------------------------------------
# Unit tests for classify_effectiveness
# ---------------------------------------------------------------------------


class TestClassifyEffectiveness:
    """Tests for the effectiveness classification function."""

    def test_highly_effective_at_95(self) -> None:
        assert classify_effectiveness(Decimal("95.00")) == ControlEffectiveness.HIGHLY_EFFECTIVE

    def test_highly_effective_at_90(self) -> None:
        assert classify_effectiveness(Decimal("90.00")) == ControlEffectiveness.HIGHLY_EFFECTIVE

    def test_effective_at_85(self) -> None:
        assert classify_effectiveness(Decimal("85.00")) == ControlEffectiveness.EFFECTIVE

    def test_effective_at_70(self) -> None:
        assert classify_effectiveness(Decimal("70.00")) == ControlEffectiveness.EFFECTIVE

    def test_moderately_effective_at_65(self) -> None:
        assert classify_effectiveness(Decimal("65.00")) == ControlEffectiveness.MODERATELY_EFFECTIVE

    def test_moderately_effective_at_50(self) -> None:
        assert classify_effectiveness(Decimal("50.00")) == ControlEffectiveness.MODERATELY_EFFECTIVE

    def test_ineffective_at_49(self) -> None:
        assert classify_effectiveness(Decimal("49.00")) == ControlEffectiveness.INEFFECTIVE

    def test_ineffective_at_0(self) -> None:
        assert classify_effectiveness(Decimal("0.00")) == ControlEffectiveness.INEFFECTIVE

    def test_highly_effective_at_100(self) -> None:
        assert classify_effectiveness(Decimal("100.00")) == ControlEffectiveness.HIGHLY_EFFECTIVE


class TestGenerateRecommendation:
    """Tests for recommendation generation."""

    def test_highly_effective_no_recommendation(self) -> None:
        result = generate_recommendation(
            ControlEffectiveness.HIGHLY_EFFECTIVE, "Dual Auth", Decimal("95.00")
        )
        assert result is None

    def test_ineffective_generates_recommendation(self) -> None:
        result = generate_recommendation(
            ControlEffectiveness.INEFFECTIVE, "Manual Review Gate", Decimal("40.00")
        )
        assert result is not None
        assert "Manual Review Gate" in result
        assert "40.00%" in result
        assert "shelf data request" in result

    def test_moderately_effective_generates_recommendation(self) -> None:
        result = generate_recommendation(
            ControlEffectiveness.MODERATELY_EFFECTIVE, "KYC Check", Decimal("55.00")
        )
        assert result is not None
        assert "KYC Check" in result


# ---------------------------------------------------------------------------
# Unit tests for ControlEffectivenessScoringService
# ---------------------------------------------------------------------------


class TestScoringService:
    """Tests for the scoring service."""

    @pytest.mark.asyncio
    async def test_score_highly_effective(self) -> None:
        """Scenario 1: 95/100 evidence → HIGHLY_EFFECTIVE at 95%."""
        mock_graph = AsyncMock()

        # SUPPORTED_BY returns 100 records, 95 have execution markers
        evidence_records = []
        for i in range(100):
            evidence_records.append({
                "evidence_id": f"ev{i}",
                "has_marker": i < 95,  # First 95 have markers
            })

        mock_graph.run_query = AsyncMock(return_value=evidence_records)

        service = ControlEffectivenessScoringService(mock_graph)
        result = await service.score_control("ctrl1", "Dual Authorization Check", "eng1")

        assert result["effectiveness"] == ControlEffectiveness.HIGHLY_EFFECTIVE
        assert result["execution_rate"] == Decimal("95.00")
        assert len(result["evidence_source_ids"]) == 100
        assert result["recommendation"] is None

    @pytest.mark.asyncio
    async def test_score_ineffective_sparse(self) -> None:
        """Scenario 2: 2/5 evidence, 40% execution rate → INEFFECTIVE."""
        mock_graph = AsyncMock()

        evidence_records = [
            {"evidence_id": "ev1", "has_marker": True},
            {"evidence_id": "ev2", "has_marker": True},
            {"evidence_id": "ev3", "has_marker": False},
            {"evidence_id": "ev4", "has_marker": False},
            {"evidence_id": "ev5", "has_marker": False},
        ]

        mock_graph.run_query = AsyncMock(return_value=evidence_records)

        service = ControlEffectivenessScoringService(mock_graph)
        result = await service.score_control("ctrl1", "Manual Review Gate", "eng1")

        assert result["effectiveness"] == ControlEffectiveness.INEFFECTIVE
        assert result["execution_rate"] == Decimal("40.00")
        assert result["recommendation"] is not None
        assert "shelf data request" in result["recommendation"]

    @pytest.mark.asyncio
    async def test_score_no_evidence_returns_ineffective(self) -> None:
        """No SUPPORTED_BY edges → INEFFECTIVE at 0%."""
        mock_graph = AsyncMock()
        mock_graph.run_query = AsyncMock(return_value=[])

        service = ControlEffectivenessScoringService(mock_graph)
        result = await service.score_control("ctrl1", "Missing Control", "eng1")

        assert result["effectiveness"] == ControlEffectiveness.INEFFECTIVE
        assert result["execution_rate"] == Decimal("0.00")

    @pytest.mark.asyncio
    async def test_graph_failure_returns_ineffective(self) -> None:
        """Graph query failure → INEFFECTIVE with 0%."""
        mock_graph = AsyncMock()
        mock_graph.run_query = AsyncMock(side_effect=Exception("Connection refused"))

        service = ControlEffectivenessScoringService(mock_graph)
        result = await service.score_control("ctrl1", "Broken Control", "eng1")

        assert result["effectiveness"] == ControlEffectiveness.INEFFECTIVE
        assert result["execution_rate"] == Decimal("0.00")


# ---------------------------------------------------------------------------
# API endpoint tests — Score Control
# ---------------------------------------------------------------------------


class TestScoreControlEndpoint:
    """POST /api/v1/governance/controls/{id}/score"""

    @pytest.mark.asyncio
    async def test_score_returns_201(self) -> None:
        """Scenario 1: Returns 201 with effectiveness score."""
        mock_session = AsyncMock()

        # Control lookup → found
        control = _make_plain_mock(
            id=CONTROL_ID,
            engagement_id=ENGAGEMENT_ID,
        )
        control.name = "Dual Authorization Check"
        ctrl_result = MagicMock()
        ctrl_result.scalar_one_or_none.return_value = control

        mock_session.execute = AsyncMock(return_value=ctrl_result)
        mock_session.commit = AsyncMock()

        _added_objects: list[Any] = []

        def _fake_add(obj: Any) -> None:
            _added_objects.append(obj)

        mock_session.add = _fake_add

        async def _fake_refresh(obj: Any) -> None:
            obj.id = uuid.uuid4()
            obj.scored_at = datetime.now(UTC)

        mock_session.refresh = _fake_refresh

        app = _make_app_with_session(mock_session)
        app.state.neo4j_driver = MagicMock()

        mock_score = {
            "effectiveness": ControlEffectiveness.HIGHLY_EFFECTIVE,
            "execution_rate": Decimal("95.00"),
            "evidence_source_ids": [str(uuid.uuid4()) for _ in range(5)],
            "total_required": 100,
            "evidenced_count": 95,
            "recommendation": None,
        }

        with (
            mock.patch(
                "src.api.routes.governance.ControlEffectivenessScoringService"
            ) as mock_svc_cls,
            mock.patch("src.api.routes.governance.log_audit", new_callable=AsyncMock),
        ):
            mock_svc = AsyncMock()
            mock_svc.score_control = AsyncMock(return_value=mock_score)
            mock_svc_cls.return_value = mock_svc

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    f"/api/v1/governance/controls/{CONTROL_ID}/score",
                )

        assert resp.status_code == 201
        data = resp.json()
        assert data["effectiveness"] == "highly_effective"
        assert data["execution_rate"] == 95.0

    @pytest.mark.asyncio
    async def test_score_404_control_not_found(self) -> None:
        """Returns 404 when control does not exist."""
        mock_session = AsyncMock()

        ctrl_result = MagicMock()
        ctrl_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=ctrl_result)

        app = _make_app_with_session(mock_session)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                f"/api/v1/governance/controls/{CONTROL_ID}/score",
            )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API endpoint tests — Score History
# ---------------------------------------------------------------------------


class TestScoreHistory:
    """GET /api/v1/governance/controls/{id}/effectiveness-scores"""

    @pytest.mark.asyncio
    async def test_get_history_chronological(self) -> None:
        """Scenario 3: Returns historical scores in chronological order."""
        mock_session = AsyncMock()

        # Control exists
        control = _make_plain_mock(id=CONTROL_ID, engagement_id=ENGAGEMENT_ID)
        ctrl_result = MagicMock()
        ctrl_result.scalar_one_or_none.return_value = control

        # Count → 2
        count_result = MagicMock()
        count_result.scalar.return_value = 2

        # Historical scores
        now = datetime.now(UTC)
        scores = [
            _make_plain_mock(
                id=uuid.uuid4(),
                control_id=CONTROL_ID,
                engagement_id=ENGAGEMENT_ID,
                effectiveness=ControlEffectiveness.MODERATELY_EFFECTIVE,
                execution_rate=Decimal("55.00"),
                evidence_source_ids=None,
                recommendation="Improve coverage",
                scored_at=now - timedelta(days=30),
                scored_by=str(USER_ID),
            ),
            _make_plain_mock(
                id=uuid.uuid4(),
                control_id=CONTROL_ID,
                engagement_id=ENGAGEMENT_ID,
                effectiveness=ControlEffectiveness.EFFECTIVE,
                execution_rate=Decimal("78.00"),
                evidence_source_ids=None,
                recommendation=None,
                scored_at=now,
                scored_by=str(USER_ID),
            ),
        ]

        scores_result = MagicMock()
        scores_result.scalars.return_value.all.return_value = scores

        mock_session.execute = AsyncMock(
            side_effect=[ctrl_result, count_result, scores_result]
        )

        app = _make_app_with_session(mock_session)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                f"/api/v1/governance/controls/{CONTROL_ID}/effectiveness-scores",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["scores"]) == 2
        # First score is older (chronological)
        assert data["scores"][0]["effectiveness"] == "moderately_effective"
        assert data["scores"][1]["effectiveness"] == "effective"

    @pytest.mark.asyncio
    async def test_get_history_404_control_not_found(self) -> None:
        """Returns 404 when control does not exist."""
        mock_session = AsyncMock()

        ctrl_result = MagicMock()
        ctrl_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=ctrl_result)

        app = _make_app_with_session(mock_session)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                f"/api/v1/governance/controls/{CONTROL_ID}/effectiveness-scores",
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_history_empty(self) -> None:
        """Returns empty list when no scores exist."""
        mock_session = AsyncMock()

        control = _make_plain_mock(id=CONTROL_ID, engagement_id=ENGAGEMENT_ID)
        ctrl_result = MagicMock()
        ctrl_result.scalar_one_or_none.return_value = control

        count_result = MagicMock()
        count_result.scalar.return_value = 0

        scores_result = MagicMock()
        scores_result.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(
            side_effect=[ctrl_result, count_result, scores_result]
        )

        app = _make_app_with_session(mock_session)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                f"/api/v1/governance/controls/{CONTROL_ID}/effectiveness-scores",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["scores"] == []
