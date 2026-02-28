"""BDD tests for Story #331: Governance Overlay Visualization on Process Models.

Tests governance overlay computation per-activity with governance chain
traversal and gap detection against mocked Neo4j graph data.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import create_app
from src.api.services.governance_overlay import GovernanceOverlayService, GovernanceStatus
from src.core.auth import get_current_user
from src.core.models import ProcessModel, User, UserRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROCESS_MODEL_ID = uuid.uuid4()
ENGAGEMENT_ID = uuid.uuid4()


def _mock_user() -> User:
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.role = UserRole.PLATFORM_ADMIN
    return u


def _mock_process_model() -> MagicMock:
    pm = MagicMock(spec=ProcessModel)
    pm.id = PROCESS_MODEL_ID
    pm.engagement_id = ENGAGEMENT_ID
    return pm


def _mock_session(process_model: Any = None) -> AsyncMock:
    """Build a mock session that returns the given process model from SELECT."""
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = process_model
    session.execute.return_value = result
    return session


def _make_app(mock_session: AsyncMock) -> Any:
    """Create app with overridden dependencies."""
    from src.api.deps import get_session

    app = create_app()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    app.state.neo4j_driver = MagicMock()
    return app


# ---------------------------------------------------------------------------
# Mock graph query builder
# ---------------------------------------------------------------------------


def _build_mock_run_query(
    activities: list[dict[str, str]],
    chains: list[dict[str, Any]],
) -> Any:
    """Build a mock run_query function returning configured graph data.

    Args:
        activities: list of {activity_id, activity_name} dicts
        chains: list of governance chain dicts with activity_id, policy_*, control_*, regulation_*
    """

    async def mock_run_query(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if "OPTIONAL MATCH" in query:
            # Governance chain query
            return chains
        if "RETURN a.id AS activity_id" in query:
            # Activity listing query
            return activities
        return []

    return mock_run_query


# ---------------------------------------------------------------------------
# BDD Scenario 1: Governance Status Per Activity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_1_governance_status_classification() -> None:
    """Given 10 activities with mixed governance coverage,
    4 governed, 3 partially governed, 3 ungoverned,
    When GET /governance-overlay is called,
    Then correct status counts are returned."""
    activities = [
        {"activity_id": f"act-{i}", "activity_name": f"Activity {i}"}
        for i in range(10)
    ]

    # 4 fully governed (policy + control + regulation)
    chains: list[dict[str, Any]] = []
    for i in range(4):
        chains.append({
            "activity_id": f"act-{i}",
            "policy_id": f"pol-{i}", "policy_name": f"Policy {i}",
            "control_id": f"ctl-{i}", "control_name": f"Control {i}",
            "regulation_id": f"reg-{i}", "regulation_name": f"Regulation {i}",
        })

    # 3 partially governed (policy only, no control/regulation)
    for i in range(4, 7):
        chains.append({
            "activity_id": f"act-{i}",
            "policy_id": f"pol-{i}", "policy_name": f"Policy {i}",
            "control_id": None, "control_name": None,
            "regulation_id": None, "regulation_name": None,
        })

    # 3 ungoverned (no governance entities)
    for i in range(7, 10):
        chains.append({
            "activity_id": f"act-{i}",
            "policy_id": None, "policy_name": None,
            "control_id": None, "control_name": None,
            "regulation_id": None, "regulation_name": None,
        })

    mock_session = _mock_session(_mock_process_model())
    app = _make_app(mock_session)
    mock_rq = _build_mock_run_query(activities, chains)

    with patch("src.api.routes.governance_overlay.KnowledgeGraphService") as mock_kgs:
        instance = mock_kgs.return_value
        instance.run_query = mock_rq

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/v1/process-models/{PROCESS_MODEL_ID}/governance-overlay"
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_activities"] == 10
    assert data["governed_count"] == 4
    assert data["partially_governed_count"] == 3
    assert data["ungoverned_count"] == 3
    assert len(data["activities"]) == 10


# ---------------------------------------------------------------------------
# BDD Scenario 2: Full Governance Chain Returned Per Activity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_2_full_governance_chain() -> None:
    """Given Activity 'Wire Transfer Review' is fully governed,
    When GET /governance-overlay is called,
    Then the response entry includes the full governance chain."""
    activities = [
        {"activity_id": "act-wtr", "activity_name": "Wire Transfer Review"},
    ]
    chains = [
        {
            "activity_id": "act-wtr",
            "policy_id": "pol-aml", "policy_name": "AML Policy",
            "control_id": "ctl-txn", "control_name": "Transaction Monitoring",
            "regulation_id": "reg-bsa", "regulation_name": "BSA",
        },
    ]

    mock_session = _mock_session(_mock_process_model())
    app = _make_app(mock_session)
    mock_rq = _build_mock_run_query(activities, chains)

    with patch("src.api.routes.governance_overlay.KnowledgeGraphService") as mock_kgs:
        instance = mock_kgs.return_value
        instance.run_query = mock_rq

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/v1/process-models/{PROCESS_MODEL_ID}/governance-overlay"
            )

    assert resp.status_code == 200
    data = resp.json()
    entry = data["activities"][0]
    assert entry["governance_status"] == "governed"
    assert entry["policy"]["name"] == "AML Policy"
    assert entry["control"]["name"] == "Transaction Monitoring"
    assert entry["regulation"]["name"] == "BSA"


# ---------------------------------------------------------------------------
# BDD Scenario 3: Ungoverned Activities Highlighted as Gaps
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_3_ungoverned_activities_as_gaps() -> None:
    """Given 3 ungoverned out of 10 activities,
    When GET /governance-overlay is called,
    Then the 3 ungoverned appear in governance_gaps and coverage = 70%."""
    activities = [
        {"activity_id": f"act-{i}", "activity_name": f"Activity {i}"}
        for i in range(10)
    ]

    chains: list[dict[str, Any]] = []
    # 7 governed (4 full + 3 partial)
    for i in range(4):
        chains.append({
            "activity_id": f"act-{i}",
            "policy_id": f"pol-{i}", "policy_name": f"Policy {i}",
            "control_id": f"ctl-{i}", "control_name": f"Control {i}",
            "regulation_id": f"reg-{i}", "regulation_name": f"Regulation {i}",
        })
    for i in range(4, 7):
        chains.append({
            "activity_id": f"act-{i}",
            "policy_id": f"pol-{i}", "policy_name": f"Policy {i}",
            "control_id": None, "control_name": None,
            "regulation_id": None, "regulation_name": None,
        })
    # 3 ungoverned
    for i in range(7, 10):
        chains.append({
            "activity_id": f"act-{i}",
            "policy_id": None, "policy_name": None,
            "control_id": None, "control_name": None,
            "regulation_id": None, "regulation_name": None,
        })

    mock_session = _mock_session(_mock_process_model())
    app = _make_app(mock_session)
    mock_rq = _build_mock_run_query(activities, chains)

    with patch("src.api.routes.governance_overlay.KnowledgeGraphService") as mock_kgs:
        instance = mock_kgs.return_value
        instance.run_query = mock_rq

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/v1/process-models/{PROCESS_MODEL_ID}/governance-overlay"
            )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["governance_gaps"]) == 3
    for gap in data["governance_gaps"]:
        assert gap["gap_type"] == "UNGOVERNED"
        assert gap["activity_id"].startswith("act-")
        assert gap["activity_name"].startswith("Activity")

    assert data["overall_coverage_percentage"] == 70.0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_model_not_found_returns_404() -> None:
    """Process model not in database returns 404."""
    mock_session = _mock_session(None)  # No process model found
    app = _make_app(mock_session)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            f"/api/v1/process-models/{uuid.uuid4()}/governance-overlay"
        )

    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_no_activities_returns_empty() -> None:
    """Process model with no activities returns zero counts."""
    mock_session = _mock_session(_mock_process_model())
    app = _make_app(mock_session)
    mock_rq = _build_mock_run_query([], [])

    with patch("src.api.routes.governance_overlay.KnowledgeGraphService") as mock_kgs:
        instance = mock_kgs.return_value
        instance.run_query = mock_rq

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/v1/process-models/{PROCESS_MODEL_ID}/governance-overlay"
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_activities"] == 0
    assert data["governed_count"] == 0
    assert data["partially_governed_count"] == 0
    assert data["ungoverned_count"] == 0
    assert data["activities"] == []
    assert data["governance_gaps"] == []
    assert data["overall_coverage_percentage"] == 0.0


@pytest.mark.asyncio
async def test_all_governed_100_percent_coverage() -> None:
    """All activities governed yields 100% coverage."""
    activities = [
        {"activity_id": "act-1", "activity_name": "Activity 1"},
        {"activity_id": "act-2", "activity_name": "Activity 2"},
    ]
    chains = [
        {
            "activity_id": "act-1",
            "policy_id": "pol-1", "policy_name": "P1",
            "control_id": "ctl-1", "control_name": "C1",
            "regulation_id": "reg-1", "regulation_name": "R1",
        },
        {
            "activity_id": "act-2",
            "policy_id": "pol-2", "policy_name": "P2",
            "control_id": "ctl-2", "control_name": "C2",
            "regulation_id": "reg-2", "regulation_name": "R2",
        },
    ]

    mock_session = _mock_session(_mock_process_model())
    app = _make_app(mock_session)
    mock_rq = _build_mock_run_query(activities, chains)

    with patch("src.api.routes.governance_overlay.KnowledgeGraphService") as mock_kgs:
        instance = mock_kgs.return_value
        instance.run_query = mock_rq

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/v1/process-models/{PROCESS_MODEL_ID}/governance-overlay"
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["overall_coverage_percentage"] == 100.0
    assert data["governed_count"] == 2
    assert data["governance_gaps"] == []


@pytest.mark.asyncio
async def test_all_ungoverned_zero_percent_coverage() -> None:
    """All activities ungoverned yields 0% coverage."""
    activities = [
        {"activity_id": "act-1", "activity_name": "Activity 1"},
        {"activity_id": "act-2", "activity_name": "Activity 2"},
    ]
    chains = [
        {
            "activity_id": "act-1",
            "policy_id": None, "policy_name": None,
            "control_id": None, "control_name": None,
            "regulation_id": None, "regulation_name": None,
        },
        {
            "activity_id": "act-2",
            "policy_id": None, "policy_name": None,
            "control_id": None, "control_name": None,
            "regulation_id": None, "regulation_name": None,
        },
    ]

    mock_session = _mock_session(_mock_process_model())
    app = _make_app(mock_session)
    mock_rq = _build_mock_run_query(activities, chains)

    with patch("src.api.routes.governance_overlay.KnowledgeGraphService") as mock_kgs:
        instance = mock_kgs.return_value
        instance.run_query = mock_rq

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/v1/process-models/{PROCESS_MODEL_ID}/governance-overlay"
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["overall_coverage_percentage"] == 0.0
    assert data["ungoverned_count"] == 2
    assert len(data["governance_gaps"]) == 2


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_governance_status_enum_values() -> None:
    """GovernanceStatus enum has correct string values."""
    assert GovernanceStatus.GOVERNED.value == "governed"
    assert GovernanceStatus.PARTIALLY_GOVERNED.value == "partially_governed"
    assert GovernanceStatus.UNGOVERNED.value == "ungoverned"


@pytest.mark.asyncio
async def test_service_classifies_partial_with_control_only() -> None:
    """Activity with only control (no policy/regulation) is PARTIALLY_GOVERNED."""
    activities = [
        {"activity_id": "act-1", "activity_name": "Activity 1"},
    ]
    chains = [
        {
            "activity_id": "act-1",
            "policy_id": None, "policy_name": None,
            "control_id": "ctl-1", "control_name": "Control 1",
            "regulation_id": None, "regulation_name": None,
        },
    ]

    graph_service = MagicMock()
    graph_service.run_query = AsyncMock(side_effect=_build_mock_run_query(activities, chains))

    service = GovernanceOverlayService(graph_service)
    result = await service.compute_overlay(str(PROCESS_MODEL_ID), str(ENGAGEMENT_ID))

    assert result["partially_governed_count"] == 1
    assert result["activities"][0]["governance_status"] == "partially_governed"
    assert result["activities"][0]["control"]["name"] == "Control 1"
    assert "policy" not in result["activities"][0]


@pytest.mark.asyncio
async def test_service_classifies_partial_with_regulation_only() -> None:
    """Activity with only regulation (no policy/control) is PARTIALLY_GOVERNED."""
    activities = [
        {"activity_id": "act-1", "activity_name": "Activity 1"},
    ]
    chains = [
        {
            "activity_id": "act-1",
            "policy_id": None, "policy_name": None,
            "control_id": None, "control_name": None,
            "regulation_id": "reg-1", "regulation_name": "Regulation 1",
        },
    ]

    graph_service = MagicMock()
    graph_service.run_query = AsyncMock(side_effect=_build_mock_run_query(activities, chains))

    service = GovernanceOverlayService(graph_service)
    result = await service.compute_overlay(str(PROCESS_MODEL_ID), str(ENGAGEMENT_ID))

    assert result["partially_governed_count"] == 1
    assert result["activities"][0]["governance_status"] == "partially_governed"
    assert result["activities"][0]["regulation"]["name"] == "Regulation 1"
    assert "policy" not in result["activities"][0]
    assert "control" not in result["activities"][0]
