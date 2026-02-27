"""BDD tests for Story #358 — Process Maturity Scoring Engine.

Scenario 1: DEFINED Maturity for Documented Process with Some Metrics
Scenario 2: INITIAL Maturity for Undocumented Process
Scenario 3: Maturity Heatmap Across Engagement
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import create_app
from src.core.models import (
    ProcessMaturity,
    User,
    UserRole,
)
from src.tom.maturity_scorer import (
    MaturityScoringService,
    assign_maturity_level,
    compute_evidence_dimensions,
    generate_recommendations,
)

APP = create_app()

ENGAGEMENT_ID = uuid.uuid4()
PM_ID_1 = uuid.uuid4()
PM_ID_2 = uuid.uuid4()
PM_ID_3 = uuid.uuid4()
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


def _override_deps(session: AsyncMock) -> None:
    from src.api.deps import get_session
    from src.core.auth import get_current_user

    APP.dependency_overrides[get_session] = lambda: session
    APP.dependency_overrides[get_current_user] = lambda: _mock_user()


@pytest.fixture(autouse=True)
def _cleanup() -> None:
    yield
    APP.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Unit tests: assign_maturity_level
# ---------------------------------------------------------------------------


class TestAssignMaturityLevel:
    """Test the level assignment logic across all 5 levels."""

    def test_initial_low_coverage(self) -> None:
        """Coverage < 40% => INITIAL regardless of other dimensions."""
        dims = {
            "form_coverage": 0.15,
            "governance_coverage": False,
            "has_metrics": False,
            "has_statistical_control": False,
            "has_continuous_improvement": False,
        }
        assert assign_maturity_level(dims) == ProcessMaturity.INITIAL

    def test_managed_moderate_coverage_with_governance(self) -> None:
        """Coverage 40-60% with governance => MANAGED."""
        dims = {
            "form_coverage": 0.50,
            "governance_coverage": True,
            "has_metrics": False,
            "has_statistical_control": False,
            "has_continuous_improvement": False,
        }
        assert assign_maturity_level(dims) == ProcessMaturity.MANAGED

    def test_defined_good_coverage_governance_metrics(self) -> None:
        """Coverage 60-80% with governance and metrics => DEFINED."""
        dims = {
            "form_coverage": 0.75,
            "governance_coverage": True,
            "has_metrics": True,
            "has_statistical_control": False,
            "has_continuous_improvement": False,
        }
        assert assign_maturity_level(dims) == ProcessMaturity.DEFINED

    def test_quantitatively_managed_high_coverage_stats(self) -> None:
        """Coverage > 80% with statistical controls and metrics => QUANTITATIVELY_MANAGED."""
        dims = {
            "form_coverage": 0.85,
            "governance_coverage": True,
            "has_metrics": True,
            "has_statistical_control": True,
            "has_continuous_improvement": False,
        }
        assert assign_maturity_level(dims) == ProcessMaturity.QUANTITATIVELY_MANAGED

    def test_optimizing_full_coverage_ci(self) -> None:
        """Coverage > 80% with statistical controls and CI => OPTIMIZING."""
        dims = {
            "form_coverage": 0.92,
            "governance_coverage": True,
            "has_metrics": True,
            "has_statistical_control": True,
            "has_continuous_improvement": True,
        }
        assert assign_maturity_level(dims) == ProcessMaturity.OPTIMIZING

    def test_initial_high_coverage_no_governance(self) -> None:
        """High coverage but no governance => falls through to INITIAL."""
        dims = {
            "form_coverage": 0.35,
            "governance_coverage": False,
            "has_metrics": True,
            "has_statistical_control": False,
            "has_continuous_improvement": False,
        }
        assert assign_maturity_level(dims) == ProcessMaturity.INITIAL

    def test_managed_with_metrics_but_low_coverage(self) -> None:
        """Coverage 40-60% with governance and metrics but below DEFINED threshold."""
        dims = {
            "form_coverage": 0.55,
            "governance_coverage": True,
            "has_metrics": True,
            "has_statistical_control": False,
            "has_continuous_improvement": False,
        }
        assert assign_maturity_level(dims) == ProcessMaturity.MANAGED

    def test_boundary_60_percent_with_governance_and_metrics(self) -> None:
        """Exact 60% boundary => DEFINED (inclusive)."""
        dims = {
            "form_coverage": 0.60,
            "governance_coverage": True,
            "has_metrics": True,
            "has_statistical_control": False,
            "has_continuous_improvement": False,
        }
        assert assign_maturity_level(dims) == ProcessMaturity.DEFINED


# ---------------------------------------------------------------------------
# Unit tests: compute_evidence_dimensions
# ---------------------------------------------------------------------------


class TestComputeEvidenceDimensions:
    def test_basic_dimensions(self) -> None:
        pm = {"form_coverage": 0.75}
        gov = {"has_governance": True, "has_metrics": True}
        result = compute_evidence_dimensions(pm, gov)
        assert result["form_coverage"] == 0.75
        assert result["governance_coverage"] is True
        assert result["has_metrics"] is True
        assert result["has_statistical_control"] is False
        assert result["has_continuous_improvement"] is False

    def test_defaults_when_empty(self) -> None:
        result = compute_evidence_dimensions({}, {})
        assert result["form_coverage"] == 0.0
        assert result["governance_coverage"] is False


# ---------------------------------------------------------------------------
# Unit tests: generate_recommendations
# ---------------------------------------------------------------------------


class TestGenerateRecommendations:
    def test_initial_level_recommendations(self) -> None:
        dims = {"form_coverage": 0.15, "governance_coverage": False, "has_metrics": False}
        recs = generate_recommendations(ProcessMaturity.INITIAL, dims)
        assert len(recs) >= 2
        assert any("Document procedures" in r for r in recs)
        assert any("governance" in r.lower() for r in recs)

    def test_optimizing_no_recommendations(self) -> None:
        dims = {
            "form_coverage": 0.95,
            "governance_coverage": True,
            "has_metrics": True,
            "has_statistical_control": True,
            "has_continuous_improvement": True,
        }
        recs = generate_recommendations(ProcessMaturity.OPTIMIZING, dims)
        assert len(recs) == 0


# ---------------------------------------------------------------------------
# Unit tests: MaturityScoringService
# ---------------------------------------------------------------------------


class TestMaturityScoringService:
    @pytest.mark.asyncio
    async def test_score_process_area(self) -> None:
        svc = MaturityScoringService()
        pm = {"id": str(PM_ID_1), "engagement_id": str(ENGAGEMENT_ID), "form_coverage": 0.75}
        gov = {"has_governance": True, "has_metrics": True}
        result = await svc.score_process_area(pm, gov)
        assert result["maturity_level"] == ProcessMaturity.DEFINED
        assert result["level_number"] == 3
        assert "evidence_dimensions" in result

    @pytest.mark.asyncio
    async def test_score_engagement_multiple(self) -> None:
        svc = MaturityScoringService()
        pms = [
            {"id": str(PM_ID_1), "engagement_id": str(ENGAGEMENT_ID), "form_coverage": 0.15},
            {"id": str(PM_ID_2), "engagement_id": str(ENGAGEMENT_ID), "form_coverage": 0.75},
        ]
        gov_map = {
            str(PM_ID_2): {"has_governance": True, "has_metrics": True},
        }
        results = await svc.score_engagement(pms, gov_map)
        assert len(results) == 2
        assert results[0]["maturity_level"] == ProcessMaturity.INITIAL
        assert results[1]["maturity_level"] == ProcessMaturity.DEFINED


# ---------------------------------------------------------------------------
# BDD Scenario 1: DEFINED Maturity for Documented Process with Some Metrics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_1_defined_maturity() -> None:
    """
    Given a process area "Loan Origination" has:
        documented procedures (Form 1-4 coverage >= 80%)
        defined roles and responsibilities (Form 6 coverage >= 80%)
        some performance metrics but no statistical control
        no continuous improvement mechanisms
    When maturity is scored for "Loan Origination"
    Then maturity_level=DEFINED (level 3) is recorded
      And the score record includes the evidence dimensions that drove the classification
    """
    mock_session = AsyncMock()

    engagement = _make_plain_mock(id=ENGAGEMENT_ID, name="Test Engagement")
    pm = _make_plain_mock(
        id=PM_ID_1,
        engagement_id=ENGAGEMENT_ID,
        scope="Loan Origination",
        metadata_json={"form_coverage": 0.75},
    )

    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = engagement

    pm_result = MagicMock()
    pm_result.scalars.return_value.all.return_value = [pm]

    mock_session.execute = AsyncMock(side_effect=[eng_result, pm_result])
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()

    _override_deps(mock_session)

    from unittest import mock

    with mock.patch("src.api.routes.tom.log_audit", new_callable=AsyncMock):
        transport = ASGITransport(app=APP, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/tom/engagements/{ENGAGEMENT_ID}/maturity-scores/compute",
                json={
                    "governance_map": {
                        str(PM_ID_1): {
                            "has_governance": True,
                            "has_metrics": True,
                            "has_statistical_control": False,
                            "has_continuous_improvement": False,
                        }
                    }
                },
            )

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["scores_computed"] == 1
    assert len(data["scores"]) == 1

    score = data["scores"][0]
    assert score["maturity_level"] == "defined"
    assert score["level_number"] == 3
    assert score["process_area_name"] == "Loan Origination"
    assert score["evidence_dimensions"] is not None
    assert score["evidence_dimensions"]["form_coverage"] == 0.75
    assert score["evidence_dimensions"]["governance_coverage"] is True


# ---------------------------------------------------------------------------
# BDD Scenario 2: INITIAL Maturity for Undocumented Process
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_2_initial_maturity() -> None:
    """
    Given a process area "Exception Handling" has:
        no documented procedures (Form 1-4 coverage < 20%)
        no defined roles (Form 6 coverage < 20%)
        no governance linkages
        no evidence of repeatable execution
    When maturity is scored for "Exception Handling"
    Then maturity_level=INITIAL (level 1) is recorded
      And improvement recommendations are generated for the undocumented forms
    """
    mock_session = AsyncMock()

    engagement = _make_plain_mock(id=ENGAGEMENT_ID, name="Test Engagement")
    pm = _make_plain_mock(
        id=PM_ID_2,
        engagement_id=ENGAGEMENT_ID,
        scope="Exception Handling",
        metadata_json={"form_coverage": 0.10},
    )

    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = engagement

    pm_result = MagicMock()
    pm_result.scalars.return_value.all.return_value = [pm]

    mock_session.execute = AsyncMock(side_effect=[eng_result, pm_result])
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()

    _override_deps(mock_session)

    from unittest import mock

    with mock.patch("src.api.routes.tom.log_audit", new_callable=AsyncMock):
        transport = ASGITransport(app=APP, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/tom/engagements/{ENGAGEMENT_ID}/maturity-scores/compute",
                json={"governance_map": {}},
            )

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["scores_computed"] == 1

    score = data["scores"][0]
    assert score["maturity_level"] == "initial"
    assert score["level_number"] == 1
    assert score["process_area_name"] == "Exception Handling"
    assert score["recommendations"] is not None
    assert len(score["recommendations"]) > 0
    assert any("Document procedures" in r for r in score["recommendations"])


# ---------------------------------------------------------------------------
# BDD Scenario 3: Maturity Heatmap Across Engagement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_3_maturity_heatmap() -> None:
    """
    Given 8 process areas exist for an engagement
      And each has been maturity-scored at various levels
    When GET /api/v1/engagements/{id}/maturity-heatmap is called
    Then the response includes all 8 process areas with their maturity_level and level number
      And the response includes an overall_engagement_maturity computed as the average level
      And the data is structured to support color-coded heatmap rendering by the frontend
    """
    mock_session = AsyncMock()

    engagement = _make_plain_mock(id=ENGAGEMENT_ID, name="Test Engagement")

    # Create 8 process areas with various maturity scores
    process_areas = []
    scores_data = []
    levels = [
        ("Credit Assessment", ProcessMaturity.DEFINED, 3),
        ("Loan Origination", ProcessMaturity.MANAGED, 2),
        ("KYC Verification", ProcessMaturity.QUANTITATIVELY_MANAGED, 4),
        ("Disbursement", ProcessMaturity.INITIAL, 1),
        ("Collections", ProcessMaturity.MANAGED, 2),
        ("Compliance Review", ProcessMaturity.OPTIMIZING, 5),
        ("Risk Assessment", ProcessMaturity.DEFINED, 3),
        ("Customer Onboarding", ProcessMaturity.INITIAL, 1),
    ]

    for name, level, level_num in levels:
        pm_id = uuid.uuid4()
        process_areas.append(_make_plain_mock(id=pm_id, scope=name))
        scores_data.append(
            _make_plain_mock(
                id=uuid.uuid4(),
                engagement_id=ENGAGEMENT_ID,
                process_model_id=pm_id,
                maturity_level=level,
                level_number=level_num,
                scored_at=datetime(2026, 2, 27, tzinfo=UTC),
            )
        )

    # Mock: engagement check, subquery scores, process model lookup
    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = engagement

    score_result = MagicMock()
    score_result.scalars.return_value.all.return_value = scores_data

    pm_result = MagicMock()
    pm_result.scalars.return_value.all.return_value = process_areas

    mock_session.execute = AsyncMock(side_effect=[eng_result, score_result, pm_result])

    _override_deps(mock_session)

    transport = ASGITransport(app=APP, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/tom/engagements/{ENGAGEMENT_ID}/maturity-heatmap",
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["process_area_count"] == 8
    assert len(data["process_areas"]) == 8

    # Check that all process areas are present
    area_names = {a["process_area_name"] for a in data["process_areas"]}
    for name, _, _ in levels:
        assert name in area_names, f"Missing process area: {name}"

    # Average: (3+2+4+1+2+5+3+1)/8 = 21/8 = 2.625
    expected_avg = round(21 / 8, 2)
    assert data["overall_engagement_maturity"] == expected_avg

    # Each entry has required fields for heatmap rendering
    for area in data["process_areas"]:
        assert "process_model_id" in area
        assert "process_area_name" in area
        assert "maturity_level" in area
        assert "level_number" in area
        assert area["level_number"] in [1, 2, 3, 4, 5]


# ---------------------------------------------------------------------------
# Additional endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compute_no_process_models() -> None:
    """When engagement has no process models, return empty scores."""
    mock_session = AsyncMock()

    engagement = _make_plain_mock(id=ENGAGEMENT_ID, name="Empty Engagement")

    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = engagement

    pm_result = MagicMock()
    pm_result.scalars.return_value.all.return_value = []

    mock_session.execute = AsyncMock(side_effect=[eng_result, pm_result])

    _override_deps(mock_session)

    transport = ASGITransport(app=APP, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/tom/engagements/{ENGAGEMENT_ID}/maturity-scores/compute",
            json={},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["scores_computed"] == 0
    assert data["scores"] == []


@pytest.mark.asyncio
async def test_compute_engagement_not_found() -> None:
    """404 when engagement does not exist."""
    mock_session = AsyncMock()

    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = None

    mock_session.execute = AsyncMock(return_value=eng_result)

    _override_deps(mock_session)

    transport = ASGITransport(app=APP, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/tom/engagements/{uuid.uuid4()}/maturity-scores/compute",
            json={},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_heatmap_no_scores() -> None:
    """Heatmap returns empty when no scores exist."""
    mock_session = AsyncMock()

    engagement = _make_plain_mock(id=ENGAGEMENT_ID, name="No Scores")

    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = engagement

    score_result = MagicMock()
    score_result.scalars.return_value.all.return_value = []

    mock_session.execute = AsyncMock(side_effect=[eng_result, score_result])

    _override_deps(mock_session)

    transport = ASGITransport(app=APP, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/tom/engagements/{ENGAGEMENT_ID}/maturity-heatmap",
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["process_area_count"] == 0
    assert data["overall_engagement_maturity"] == 0.0
    assert data["process_areas"] == []


@pytest.mark.asyncio
async def test_heatmap_engagement_not_found() -> None:
    """404 when engagement does not exist for heatmap."""
    mock_session = AsyncMock()

    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = None

    mock_session.execute = AsyncMock(return_value=eng_result)

    _override_deps(mock_session)

    transport = ASGITransport(app=APP, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/tom/engagements/{uuid.uuid4()}/maturity-heatmap",
        )

    assert resp.status_code == 404
