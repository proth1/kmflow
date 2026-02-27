"""BDD tests for Story #393: Evidence Gap Ranking with Confidence Uplift Projection.

Tests uplift projection computation, cross-scenario shared gap detection,
and projected vs actual uplift correlation tracking.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import create_app
from src.api.services.evidence_gap_ranking import (
    EVIDENCE_COVERAGE_FACTORS,
    EvidenceGapRankingService,
)
from src.core.auth import get_current_user
from src.core.models import Engagement, User, UserRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENGAGEMENT_ID = uuid.uuid4()
ELEMENT_DARK = str(uuid.uuid4())
ELEMENT_DIM = str(uuid.uuid4())


def _mock_user() -> User:
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.role = UserRole.PLATFORM_ADMIN
    return u


def _mock_session_with_engagement(engagement: Any) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = engagement
    session.execute.return_value = result
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session


def _make_engagement(eid: uuid.UUID) -> MagicMock:
    eng = MagicMock(spec=Engagement)
    eng.id = eid
    return eng


def _make_app(mock_session: AsyncMock) -> Any:
    from src.api.deps import get_session

    app = create_app()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    app.state.neo4j_driver = MagicMock()
    return app


def _mock_graph_with_elements(elements: list[dict[str, Any]]) -> Any:
    """Build a mock graph service returning configured elements."""

    async def mock_run_query(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if "brightness" in query:
            return elements
        return []

    return mock_run_query


# ---------------------------------------------------------------------------
# BDD Scenario 1: Per-Gap Confidence Uplift Projection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_1_per_gap_uplift_projection() -> None:
    """Given a Dark element with current_confidence=0.35,
    When uplift is projected,
    Then projected_confidence and uplift_delta are computed for each evidence type."""
    eng = _make_engagement(ENGAGEMENT_ID)
    session = _mock_session_with_engagement(eng)
    app = _make_app(session)

    elements = [
        {
            "element_id": ELEMENT_DARK,
            "element_name": "Wire Transfer Review",
            "confidence": 0.35,
            "brightness": "dark",
        },
    ]

    with patch("src.api.routes.evidence_gap_ranking.KnowledgeGraphService") as mock_kgs:
        instance = mock_kgs.return_value
        instance.run_query = AsyncMock(side_effect=_mock_graph_with_elements(elements))

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/v1/epistemic/uplift-projections?engagement_id={ENGAGEMENT_ID}"
            )

    assert resp.status_code == 201
    data = resp.json()
    assert data["projections_count"] == len(EVIDENCE_COVERAGE_FACTORS)

    # Check a specific projection: document type
    doc_projs = [p for p in data["projections"] if p["evidence_type"] == "document"]
    assert len(doc_projs) == 1
    proj = doc_projs[0]

    # brightness_gap = 1.0 - 0.35 = 0.65
    # document factor = 0.25
    # uplift = 0.25 * 0.65 = 0.1625
    assert proj["current_confidence"] == 0.35
    assert proj["projected_uplift"] == 0.1625
    assert proj["projected_confidence"] == 0.5125
    assert proj["element_id"] == ELEMENT_DARK


# ---------------------------------------------------------------------------
# BDD Scenario 2: Cross-Scenario Shared Gap Detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_2_cross_scenario_shared_gaps() -> None:
    """Given 3 scenarios all modifying the same element E1,
    When cross-scenario view is computed,
    Then E1 is flagged as shared gap with 'improves all scenarios' label."""
    eng = _make_engagement(ENGAGEMENT_ID)

    # Mock session with multiple return values for different queries
    session = AsyncMock()

    # First call: engagement existence check
    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = eng

    # Second call: cross-scenario query (shared gaps)
    shared_row = MagicMock()
    shared_row.element_id = ELEMENT_DARK
    shared_row.element_name = "Wire Transfer Review"
    shared_row.scenario_count = 3
    shared_result = MagicMock()
    shared_result.all.return_value = [shared_row]

    # Third call: uplift sum query
    uplift_result = MagicMock()
    uplift_result.scalar.return_value = 0.45

    session.execute = AsyncMock(
        side_effect=[eng_result, shared_result, uplift_result]
    )

    app = _make_app(session)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            f"/api/v1/epistemic/cross-scenario-gaps?engagement_id={ENGAGEMENT_ID}"
        )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["shared_gaps"]) == 1

    gap = data["shared_gaps"][0]
    assert gap["element_id"] == ELEMENT_DARK
    assert gap["scenario_count"] == 3
    assert gap["label"] == "improves all scenarios"
    assert gap["combined_estimated_uplift"] == 0.45


# ---------------------------------------------------------------------------
# BDD Scenario 3: Projected vs Actual Uplift Correlation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_3_uplift_correlation_sufficient_data() -> None:
    """Given 20 resolved projections,
    When correlation is computed,
    Then Pearson correlation is returned with meets_target flag."""
    eng = _make_engagement(ENGAGEMENT_ID)

    session = AsyncMock()
    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = eng

    # 20 pairs with strong positive correlation
    pairs = [(0.10 + i * 0.02, 0.09 + i * 0.02) for i in range(20)]
    corr_result = MagicMock()
    corr_result.all.return_value = pairs

    session.execute = AsyncMock(side_effect=[eng_result, corr_result])

    app = _make_app(session)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            f"/api/v1/epistemic/uplift-accuracy?engagement_id={ENGAGEMENT_ID}"
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["resolved_count"] == 20
    assert data["correlation"] is not None
    assert data["correlation"] > 0.9  # Strong positive correlation
    assert data["meets_target"] is True
    assert data["insufficient_data"] is False


@pytest.mark.asyncio
async def test_scenario_3_insufficient_data() -> None:
    """Given fewer than 10 resolved projections,
    When correlation is computed,
    Then insufficient_data flag is returned."""
    eng = _make_engagement(ENGAGEMENT_ID)

    session = AsyncMock()
    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = eng

    # Only 5 pairs
    pairs = [(0.10, 0.09), (0.12, 0.11), (0.15, 0.14), (0.18, 0.17), (0.20, 0.19)]
    corr_result = MagicMock()
    corr_result.all.return_value = pairs

    session.execute = AsyncMock(side_effect=[eng_result, corr_result])
    app = _make_app(session)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            f"/api/v1/epistemic/uplift-accuracy?engagement_id={ENGAGEMENT_ID}"
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["insufficient_data"] is True
    assert data["correlation"] is None
    assert data["resolved_count"] == 5


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engagement_not_found_returns_404() -> None:
    """Non-existent engagement returns 404 for all endpoints."""
    session = _mock_session_with_engagement(None)
    app = _make_app(session)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/api/v1/epistemic/uplift-projections?engagement_id={uuid.uuid4()}"
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_no_dark_dim_elements_returns_empty() -> None:
    """Engagement with no Dark/Dim elements returns zero projections."""
    eng = _make_engagement(ENGAGEMENT_ID)
    session = _mock_session_with_engagement(eng)
    app = _make_app(session)

    with patch("src.api.routes.evidence_gap_ranking.KnowledgeGraphService") as mock_kgs:
        instance = mock_kgs.return_value
        instance.run_query = AsyncMock(return_value=[])

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/v1/epistemic/uplift-projections?engagement_id={ENGAGEMENT_ID}"
            )

    assert resp.status_code == 201
    data = resp.json()
    assert data["projections_count"] == 0
    assert data["projections"] == []


@pytest.mark.asyncio
async def test_cross_scenario_no_shared_gaps() -> None:
    """Engagement with no shared gaps returns empty list."""
    eng = _make_engagement(ENGAGEMENT_ID)

    session = AsyncMock()
    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = eng

    empty_result = MagicMock()
    empty_result.all.return_value = []

    session.execute = AsyncMock(side_effect=[eng_result, empty_result])
    app = _make_app(session)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            f"/api/v1/epistemic/cross-scenario-gaps?engagement_id={ENGAGEMENT_ID}"
        )

    assert resp.status_code == 200
    assert resp.json()["shared_gaps"] == []


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pearson_correlation_perfect() -> None:
    """Perfect positive correlation returns 1.0."""
    result = EvidenceGapRankingService._pearson_correlation(
        [1.0, 2.0, 3.0, 4.0, 5.0],
        [2.0, 4.0, 6.0, 8.0, 10.0],
    )
    assert abs(result - 1.0) < 0.001


@pytest.mark.asyncio
async def test_pearson_correlation_negative() -> None:
    """Perfect negative correlation returns -1.0."""
    result = EvidenceGapRankingService._pearson_correlation(
        [1.0, 2.0, 3.0, 4.0, 5.0],
        [10.0, 8.0, 6.0, 4.0, 2.0],
    )
    assert abs(result - (-1.0)) < 0.001


@pytest.mark.asyncio
async def test_pearson_correlation_single_point() -> None:
    """Single data point returns 0.0."""
    result = EvidenceGapRankingService._pearson_correlation([1.0], [2.0])
    assert result == 0.0


@pytest.mark.asyncio
async def test_uplift_formula_dark_element() -> None:
    """Dark element uplift = coverage_factor × brightness_gap."""
    graph = MagicMock()
    graph.run_query = AsyncMock(return_value=[
        {
            "element_id": "e1",
            "element_name": "Activity A",
            "confidence": 0.35,
            "brightness": "dark",
        },
    ])

    session = AsyncMock()
    service = EvidenceGapRankingService(session, graph)
    projections = await service.compute_uplift_projections("eng-1")

    # Should have one projection per evidence type
    assert len(projections) == len(EVIDENCE_COVERAGE_FACTORS)

    # Verify document projection: 0.25 * (1.0 - 0.35) = 0.1625
    doc_proj = next(p for p in projections if p["evidence_type"] == "document")
    assert doc_proj["projected_uplift"] == 0.1625
    assert doc_proj["projected_confidence"] == 0.5125


@pytest.mark.asyncio
async def test_evidence_coverage_factors_complete() -> None:
    """All evidence types have coverage factors."""
    assert len(EVIDENCE_COVERAGE_FACTORS) == 8
    for factor in EVIDENCE_COVERAGE_FACTORS.values():
        assert 0 < factor <= 1.0
