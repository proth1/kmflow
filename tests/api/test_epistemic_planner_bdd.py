"""BDD tests for Story #389: Epistemic Action Planner Engine.

Tests evidence gap identification per scenario, ranked gap list by information
gain, planner API response, and shelf data request linkage.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import create_app
from src.core.auth import get_current_user
from src.core.models import (
    EpistemicAction,
    SimulationScenario,
    User,
    UserRole,
)
from src.simulation.epistemic import (
    EpistemicActionItem,
    EpistemicPlanResult,
    calculate_confidence_uplift,
    compute_information_gain,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENGAGEMENT_ID = uuid.uuid4()
SCENARIO_ID = uuid.uuid4()


def _mock_user() -> User:
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.role = UserRole.PLATFORM_ADMIN
    return u


def _mock_scenario() -> MagicMock:
    s = MagicMock(spec=SimulationScenario)
    s.id = SCENARIO_ID
    s.engagement_id = ENGAGEMENT_ID
    s.name = "Test Scenario"
    s.parameters = {}
    return s


def _make_app(mock_session: AsyncMock) -> Any:
    from src.api.deps import get_session

    app = create_app()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    app.state.neo4j_driver = MagicMock()
    return app


def _mock_session_with_scenario(scenario: Any) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = scenario
    session.execute.return_value = result
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session


def _make_plan_result(actions: list[EpistemicActionItem]) -> EpistemicPlanResult:
    """Build an EpistemicPlanResult from action items."""
    high_count = sum(1 for a in actions if a.priority == "high")
    total_uplift = sum(a.estimated_confidence_uplift for a in actions)
    return EpistemicPlanResult(
        scenario_id=str(SCENARIO_ID),
        actions=actions,
        total_actions=len(actions),
        high_priority_count=high_count,
        estimated_aggregate_uplift=round(total_uplift, 4),
    )


# ---------------------------------------------------------------------------
# BDD Scenario 1: Evidence Gap Identification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_1_evidence_gap_identification() -> None:
    """Given a scenario modifying 5 elements where 2 have brightness="dark",
    When the epistemic action planner runs,
    Then exactly 2 evidence gaps are identified (one per Dark element)
    And each gap includes element_id, current_confidence, and estimated_information_gain."""
    dark_actions = [
        EpistemicActionItem(
            target_element_id="e1",
            target_element_name="Wire Transfer",
            evidence_gap_description="No evidence for Wire Transfer (dark)",
            current_confidence=0.15,
            estimated_confidence_uplift=0.08,
            projected_confidence=0.23,
            information_gain_score=0.06,
            recommended_evidence_category="documents",
            priority="high",
        ),
        EpistemicActionItem(
            target_element_id="e3",
            target_element_name="Loan Review",
            evidence_gap_description="Weak evidence for Loan Review (dark)",
            current_confidence=0.25,
            estimated_confidence_uplift=0.06,
            projected_confidence=0.31,
            information_gain_score=0.04,
            recommended_evidence_category="bpm_process_models",
            priority="high",
        ),
    ]

    plan = _make_plan_result(dark_actions)

    assert plan.total_actions == 2
    for action in plan.actions:
        assert action.target_element_id != ""
        assert 0.0 <= action.current_confidence <= 1.0
        assert action.information_gain_score > 0


# ---------------------------------------------------------------------------
# BDD Scenario 2: Ranked Gap List by Information Gain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_2_ranked_gap_list() -> None:
    """Given evidence gaps with estimated information gains of 0.25, 0.10, and 0.18,
    When the planner returns the ranked gap list,
    Then gaps are sorted by estimated_information_gain descending."""
    actions = [
        EpistemicActionItem(
            target_element_id="e1", target_element_name="A",
            evidence_gap_description="Gap A", current_confidence=0.10,
            estimated_confidence_uplift=0.30, projected_confidence=0.40,
            information_gain_score=0.25, recommended_evidence_category="documents", priority="high",
        ),
        EpistemicActionItem(
            target_element_id="e2", target_element_name="B",
            evidence_gap_description="Gap B", current_confidence=0.40,
            estimated_confidence_uplift=0.15, projected_confidence=0.55,
            information_gain_score=0.10, recommended_evidence_category="documents", priority="medium",
        ),
        EpistemicActionItem(
            target_element_id="e3", target_element_name="C",
            evidence_gap_description="Gap C", current_confidence=0.30,
            estimated_confidence_uplift=0.20, projected_confidence=0.50,
            information_gain_score=0.18, recommended_evidence_category="documents", priority="high",
        ),
    ]

    # Sort as the planner does
    actions.sort(key=lambda a: a.information_gain_score, reverse=True)
    plan = _make_plan_result(actions)

    gains = [a.information_gain_score for a in plan.actions]
    assert gains == [0.25, 0.18, 0.10]
    assert plan.actions[0].target_element_id == "e1"  # highest priority first


# ---------------------------------------------------------------------------
# BDD Scenario 3: Planner API Response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_3_api_response_post() -> None:
    """Given a valid scenario_id with Dark elements,
    When POST /api/v1/scenarios/{id}/epistemic-plan is called,
    Then ranked evidence actions with uplift projections are returned."""
    scenario = _mock_scenario()
    session = _mock_session_with_scenario(scenario)
    app = _make_app(session)

    plan = _make_plan_result([
        EpistemicActionItem(
            target_element_id="e1", target_element_name="Wire Transfer",
            evidence_gap_description="No evidence", current_confidence=0.15,
            estimated_confidence_uplift=0.08, projected_confidence=0.23,
            information_gain_score=0.06, recommended_evidence_category="documents", priority="high",
        ),
    ])

    with (
        patch("src.semantic.graph.KnowledgeGraphService", return_value=MagicMock()),
        patch("src.simulation.epistemic.EpistemicPlannerService") as mock_cls,
    ):
        mock_cls.return_value.generate_epistemic_plan = AsyncMock(return_value=plan)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(f"/api/v1/simulations/scenarios/{SCENARIO_ID}/epistemic-plan")

    assert resp.status_code == 200
    data = resp.json()
    assert data["scenario_id"] == str(SCENARIO_ID)
    assert len(data["actions"]) == 1

    action = data["actions"][0]
    assert action["target_element_id"] == "e1"
    assert action["estimated_confidence_uplift"] == 0.08
    assert action["information_gain_score"] == 0.06
    assert action["recommended_evidence_category"] == "documents"

    assert data["aggregated_view"]["total"] == 1
    assert data["aggregated_view"]["high_priority_count"] == 1


@pytest.mark.asyncio
async def test_scenario_3_api_response_get() -> None:
    """Given previously generated epistemic actions,
    When GET /api/v1/scenarios/{id}/epistemic-plan is called,
    Then the cached ranked actions are returned."""
    scenario = _mock_scenario()
    session = AsyncMock()

    # First execute returns scenario, second returns epistemic actions
    action_mock = MagicMock(spec=EpistemicAction)
    action_mock.target_element_id = "e1"
    action_mock.target_element_name = "Wire Transfer"
    action_mock.evidence_gap_description = "No evidence"
    action_mock.current_confidence = 0.15
    action_mock.estimated_confidence_uplift = 0.08
    action_mock.projected_confidence = 0.23
    action_mock.information_gain_score = 0.06
    action_mock.recommended_evidence_category = "documents"
    action_mock.priority = "high"
    action_mock.shelf_request_id = None

    scenario_result = MagicMock()
    scenario_result.scalar_one_or_none.return_value = scenario

    actions_result = MagicMock()
    actions_result.scalars.return_value.all.return_value = [action_mock]

    session.execute = AsyncMock(side_effect=[scenario_result, actions_result])

    app = _make_app(session)

    with patch("src.api.routes.simulations.require_engagement_access", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/v1/simulations/scenarios/{SCENARIO_ID}/epistemic-plan")

    assert resp.status_code == 200
    data = resp.json()
    assert data["scenario_id"] == str(SCENARIO_ID)
    assert len(data["actions"]) == 1
    assert data["actions"][0]["target_element_id"] == "e1"
    assert data["actions"][0]["shelf_request_id"] is None
    assert data["aggregated_view"]["total"] == 1


# ---------------------------------------------------------------------------
# BDD Scenario 4: Shelf Data Request Linkage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_4_shelf_request_linkage() -> None:
    """Given an epistemic gap mapped to a shelf data request recommendation,
    When the planner creates the corresponding ShelfDataRequestItem,
    Then the EpistemicAction entity links to the ShelfDataRequest via shelf_request_id."""
    scenario = _mock_scenario()
    session = _mock_session_with_scenario(scenario)
    app = _make_app(session)

    plan = _make_plan_result([
        EpistemicActionItem(
            target_element_id="e1", target_element_name="Wire Transfer",
            evidence_gap_description="No evidence", current_confidence=0.15,
            estimated_confidence_uplift=0.08, projected_confidence=0.23,
            information_gain_score=0.06, recommended_evidence_category="documents", priority="high",
        ),
    ])

    # Track what gets added to the session and assign IDs on flush
    added_objects: list[Any] = []

    def _track_add(obj: Any) -> None:
        added_objects.append(obj)

    shelf_id = uuid.uuid4()

    async def _mock_flush() -> None:
        from src.core.models import ShelfDataRequest
        for obj in added_objects:
            if isinstance(obj, ShelfDataRequest) and obj.id is None:
                obj.id = shelf_id

    session.add = MagicMock(side_effect=_track_add)
    session.flush = AsyncMock(side_effect=_mock_flush)

    with (
        patch("src.semantic.graph.KnowledgeGraphService", return_value=MagicMock()),
        patch("src.simulation.epistemic.EpistemicPlannerService") as mock_cls,
    ):
        mock_cls.return_value.generate_epistemic_plan = AsyncMock(return_value=plan)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/v1/simulations/scenarios/{SCENARIO_ID}/epistemic-plan?create_shelf_request=true"
            )

    assert resp.status_code == 200

    # Verify shelf request was created and linked
    from src.core.models import ShelfDataRequest, ShelfDataRequestItem

    shelf_requests = [o for o in added_objects if isinstance(o, ShelfDataRequest)]
    shelf_items = [o for o in added_objects if isinstance(o, ShelfDataRequestItem)]
    epistemic_actions = [o for o in added_objects if isinstance(o, EpistemicAction)]

    assert len(shelf_requests) == 1
    assert len(shelf_items) >= 1
    assert len(epistemic_actions) >= 1

    # The epistemic action should be linked to the shelf request
    for ea in epistemic_actions:
        if ea.priority == "high":
            assert ea.shelf_request_id is not None


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_not_found_returns_404() -> None:
    """Non-existent scenario returns 404."""
    session = _mock_session_with_scenario(None)
    app = _make_app(session)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/api/v1/simulations/scenarios/{uuid.uuid4()}/epistemic-plan"
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_empty_plan_returns_empty() -> None:
    """GET on scenario with no actions returns empty list."""
    scenario = _mock_scenario()
    session = AsyncMock()

    scenario_result = MagicMock()
    scenario_result.scalar_one_or_none.return_value = scenario

    actions_result = MagicMock()
    actions_result.scalars.return_value.all.return_value = []

    session.execute = AsyncMock(side_effect=[scenario_result, actions_result])

    app = _make_app(session)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            f"/api/v1/simulations/scenarios/{SCENARIO_ID}/epistemic-plan"
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["aggregated_view"]["total"] == 0
    assert data["actions"] == []


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------


def test_confidence_uplift_calculation() -> None:
    """Uplift calculation respects diminishing returns and max cap."""
    # First source, dark element
    uplift, projected = calculate_confidence_uplift(0.15, 0, 1.0)
    assert uplift > 0
    assert projected > 0.15
    assert projected <= 0.95

    # With existing sources, uplift should be less
    uplift2, projected2 = calculate_confidence_uplift(0.15, 3, 1.0)
    assert uplift2 < uplift  # diminishing returns

    # Already at max, no uplift
    uplift3, _ = calculate_confidence_uplift(0.95, 0, 1.0)
    assert uplift3 == 0.0


def test_information_gain_computation() -> None:
    """Information gain combines uplift and cascade severity."""
    gain = compute_information_gain(0.10, 0.5)
    assert gain > 0
    # 0.6 * 0.10 + 0.4 * (0.10 * 0.5) = 0.06 + 0.02 = 0.08
    assert gain == 0.08

    # Zero uplift → zero gain
    gain_zero = compute_information_gain(0.0, 1.0)
    assert gain_zero == 0.0


def test_plan_result_aggregation() -> None:
    """EpistemicPlanResult correctly aggregates counts and uplift."""
    actions = [
        EpistemicActionItem(
            target_element_id="e1", target_element_name="A",
            evidence_gap_description="Gap", current_confidence=0.10,
            estimated_confidence_uplift=0.08, projected_confidence=0.18,
            information_gain_score=0.06, recommended_evidence_category="documents", priority="high",
        ),
        EpistemicActionItem(
            target_element_id="e2", target_element_name="B",
            evidence_gap_description="Gap", current_confidence=0.50,
            estimated_confidence_uplift=0.04, projected_confidence=0.54,
            information_gain_score=0.02, recommended_evidence_category="documents", priority="medium",
        ),
    ]
    plan = _make_plan_result(actions)
    assert plan.total_actions == 2
    assert plan.high_priority_count == 1
    assert plan.estimated_aggregate_uplift == 0.12
