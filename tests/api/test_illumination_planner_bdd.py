"""BDD tests for Story #396: Illumination Planner — Targeted Evidence Acquisition.

Tests illumination plan creation, persona probes, acquisition progress
tracking, and segment completion with confidence recalculation trigger.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import create_app
from src.api.services.illumination_planner import (
    FORM_ACTION_TYPE_MAP,
    IlluminationPlannerService,
)
from src.core.auth import get_current_user
from src.core.models import (
    IlluminationAction,
    IlluminationActionStatus,
    IlluminationActionType,
    ProcessModel,
    User,
    UserRole,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENGAGEMENT_ID = uuid.uuid4()
MODEL_ID = uuid.uuid4()
ELEMENT_ID = str(uuid.uuid4())


def _mock_user() -> User:
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.role = UserRole.PLATFORM_ADMIN
    return u


def _mock_process_model() -> MagicMock:
    pm = MagicMock(spec=ProcessModel)
    pm.id = MODEL_ID
    pm.engagement_id = ENGAGEMENT_ID
    return pm


def _make_app(mock_session: AsyncMock) -> Any:
    from src.api.deps import get_session

    app = create_app()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    app.state.neo4j_driver = MagicMock()
    return app


def _mock_session_with_model(model: Any) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = model
    session.execute.return_value = result
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.add_all = MagicMock()
    return session


def _make_backlog_service_mock(
    items: list[dict[str, Any]],
) -> MagicMock:
    """Mock DarkRoomBacklogService returning items."""

    async def mock_get_dark_segments(
        engagement_id: str, limit: int = 50, offset: int = 0
    ) -> dict[str, Any]:
        return {
            "engagement_id": engagement_id,
            "dark_threshold": 0.4,
            "total_count": len(items),
            "items": items[offset:offset + limit],
        }

    service = MagicMock()
    service.get_dark_segments = AsyncMock(side_effect=mock_get_dark_segments)
    return service


# ---------------------------------------------------------------------------
# BDD Scenario 1: Shelf Data Request for Missing Evidence Form
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_1_shelf_request_for_missing_evidence() -> None:
    """Given a Dark segment missing Form 8 (Evidence),
    When the illumination plan runs,
    Then a shelf_request action is generated for Form 8."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add_all = MagicMock()

    planner = IlluminationPlannerService(session)
    missing_forms = [
        {"form_number": 8, "form_name": "evidence", "recommended_probes": [], "probe_type": "existence"},
    ]

    actions = await planner.create_illumination_plan(
        engagement_id=str(ENGAGEMENT_ID),
        element_id=ELEMENT_ID,
        element_name="Wire Transfer Review",
        missing_forms=missing_forms,
    )

    assert len(actions) == 1
    action = actions[0]
    assert action["action_type"] == IlluminationActionType.SHELF_REQUEST
    assert action["target_knowledge_form"] == 8
    assert action["target_form_name"] == "evidence"
    assert action["element_id"] == ELEMENT_ID
    assert action["status"] == IlluminationActionStatus.PENDING


# ---------------------------------------------------------------------------
# BDD Scenario 2: Persona Probe for Missing Personas Form
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_2_persona_probe_for_missing_personas() -> None:
    """Given a Dark segment missing Form 6 (Personas),
    When the illumination plan runs,
    Then a persona_probe action is generated for Form 6."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add_all = MagicMock()

    planner = IlluminationPlannerService(session)
    missing_forms = [
        {"form_number": 6, "form_name": "personas", "recommended_probes": [], "probe_type": "performer"},
    ]

    actions = await planner.create_illumination_plan(
        engagement_id=str(ENGAGEMENT_ID),
        element_id=ELEMENT_ID,
        element_name="Loan Approval",
        missing_forms=missing_forms,
    )

    assert len(actions) == 1
    action = actions[0]
    assert action["action_type"] == IlluminationActionType.PERSONA_PROBE
    assert action["target_knowledge_form"] == 6


# ---------------------------------------------------------------------------
# BDD Scenario 3: Acquisition Progress Tracking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_3_acquisition_progress() -> None:
    """Given 3 actions with 2 complete,
    When progress is retrieved,
    Then response shows 2/3 complete with per-action status."""
    session = AsyncMock()

    # Mock 3 actions: 2 complete, 1 pending
    action1 = MagicMock(spec=IlluminationAction)
    action1.id = uuid.uuid4()
    action1.action_type = IlluminationActionType.SHELF_REQUEST
    action1.target_knowledge_form = 8
    action1.target_form_name = "evidence"
    action1.status = IlluminationActionStatus.COMPLETE
    action1.linked_item_id = "shelf-req-1"
    action1.completed_at = MagicMock()
    action1.completed_at.isoformat.return_value = "2026-02-27T12:00:00Z"

    action2 = MagicMock(spec=IlluminationAction)
    action2.id = uuid.uuid4()
    action2.action_type = IlluminationActionType.PERSONA_PROBE
    action2.target_knowledge_form = 6
    action2.target_form_name = "personas"
    action2.status = IlluminationActionStatus.COMPLETE
    action2.linked_item_id = "probe-1"
    action2.completed_at = MagicMock()
    action2.completed_at.isoformat.return_value = "2026-02-27T13:00:00Z"

    action3 = MagicMock(spec=IlluminationAction)
    action3.id = uuid.uuid4()
    action3.action_type = IlluminationActionType.SYSTEM_EXTRACT
    action3.target_knowledge_form = 2
    action3.target_form_name = "sequences"
    action3.status = IlluminationActionStatus.PENDING
    action3.linked_item_id = None
    action3.completed_at = None

    result = MagicMock()
    result.scalars.return_value.all.return_value = [action1, action2, action3]
    session.execute = AsyncMock(return_value=result)

    planner = IlluminationPlannerService(session)
    progress = await planner.get_progress(str(ENGAGEMENT_ID), ELEMENT_ID)

    assert progress["total_actions"] == 3
    assert progress["completed_actions"] == 2
    assert progress["pending_actions"] == 1
    assert progress["in_progress_actions"] == 0
    assert progress["all_complete"] is False
    assert len(progress["actions"]) == 3


# ---------------------------------------------------------------------------
# BDD Scenario 4: Confidence Recalculation Trigger
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_4_all_complete_triggers_recalculation() -> None:
    """Given all 3 actions are complete,
    When completion is checked,
    Then should_recalculate is True."""
    session = AsyncMock()

    # Mock 3 actions all complete
    actions = []
    for i, (form, atype) in enumerate([(8, "shelf_request"), (6, "persona_probe"), (2, "system_extract")]):
        action = MagicMock(spec=IlluminationAction)
        action.id = uuid.uuid4()
        action.action_type = atype
        action.target_knowledge_form = form
        action.target_form_name = f"form_{form}"
        action.status = IlluminationActionStatus.COMPLETE
        action.linked_item_id = f"item-{i}"
        action.completed_at = MagicMock()
        action.completed_at.isoformat.return_value = "2026-02-27T14:00:00Z"
        actions.append(action)

    result = MagicMock()
    result.scalars.return_value.all.return_value = actions
    session.execute = AsyncMock(return_value=result)

    planner = IlluminationPlannerService(session)
    completion = await planner.check_segment_completion(str(ENGAGEMENT_ID), ELEMENT_ID)

    assert completion["all_complete"] is True
    assert completion["should_recalculate"] is True
    assert completion["completed_actions"] == 3
    assert completion["total_actions"] == 3


# ---------------------------------------------------------------------------
# API Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_create_illumination_plan() -> None:
    """POST /dark-room/{element_id}/illuminate creates an illumination plan."""
    pm = _mock_process_model()
    session = _mock_session_with_model(pm)
    app = _make_app(session)

    backlog_items = [
        {
            "element_id": ELEMENT_ID,
            "element_name": "Wire Transfer",
            "current_confidence": 0.2,
            "brightness": "dark",
            "estimated_confidence_uplift": 0.3,
            "missing_knowledge_forms": [
                {"form_number": 6, "form_name": "personas", "recommended_probes": [], "probe_type": "performer"},
                {"form_number": 8, "form_name": "evidence", "recommended_probes": [], "probe_type": "existence"},
            ],
            "missing_form_count": 2,
            "covered_form_count": 7,
        },
    ]

    with (
        patch("src.api.routes.pov.KnowledgeGraphService", return_value=MagicMock()),
        patch("src.api.routes.pov.DarkRoomBacklogService", return_value=_make_backlog_service_mock(backlog_items)),
        patch("src.api.routes.pov.IlluminationPlannerService") as mock_planner_cls,
    ):
        mock_planner = mock_planner_cls.return_value
        mock_planner.create_illumination_plan = AsyncMock(return_value=[
            {
                "id": str(uuid.uuid4()),
                "element_id": ELEMENT_ID,
                "element_name": "Wire Transfer",
                "action_type": "persona_probe",
                "target_knowledge_form": 6,
                "target_form_name": "personas",
                "status": "pending",
                "linked_item_id": None,
            },
            {
                "id": str(uuid.uuid4()),
                "element_id": ELEMENT_ID,
                "element_name": "Wire Transfer",
                "action_type": "shelf_request",
                "target_knowledge_form": 8,
                "target_form_name": "evidence",
                "status": "pending",
                "linked_item_id": None,
            },
        ])

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/v1/pov/{MODEL_ID}/dark-room/{ELEMENT_ID}/illuminate"
            )

    assert resp.status_code == 201
    data = resp.json()
    assert data["actions_created"] == 2
    assert len(data["actions"]) == 2


@pytest.mark.asyncio
async def test_api_get_progress() -> None:
    """GET /dark-room/{element_id}/progress returns progress."""
    pm = _mock_process_model()
    session = _mock_session_with_model(pm)
    app = _make_app(session)

    with patch("src.api.routes.pov.IlluminationPlannerService") as mock_planner_cls:
        mock_planner = mock_planner_cls.return_value
        mock_planner.get_progress = AsyncMock(return_value={
            "engagement_id": str(ENGAGEMENT_ID),
            "element_id": ELEMENT_ID,
            "total_actions": 3,
            "completed_actions": 1,
            "pending_actions": 2,
            "in_progress_actions": 0,
            "all_complete": False,
            "actions": [],
        })

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/v1/pov/{MODEL_ID}/dark-room/{ELEMENT_ID}/progress"
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_actions"] == 3
    assert data["completed_actions"] == 1
    assert data["all_complete"] is False


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_model_not_found_returns_404() -> None:
    """Non-existent process model returns 404."""
    session = _mock_session_with_model(None)
    app = _make_app(session)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/api/v1/pov/{uuid.uuid4()}/dark-room/{ELEMENT_ID}/illuminate"
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_no_actions_returns_empty_progress() -> None:
    """Element with no actions returns zero counts."""
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=result)

    planner = IlluminationPlannerService(session)
    progress = await planner.get_progress(str(ENGAGEMENT_ID), ELEMENT_ID)

    assert progress["total_actions"] == 0
    assert progress["all_complete"] is False


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------


def test_form_action_type_map_complete() -> None:
    """All 9 forms have action type mappings."""
    assert len(FORM_ACTION_TYPE_MAP) == 9
    for form_num in range(1, 10):
        assert form_num in FORM_ACTION_TYPE_MAP


def test_form_action_type_values() -> None:
    """Specific forms map to expected action types."""
    # System extracts for structural forms (1, 2, 3)
    assert FORM_ACTION_TYPE_MAP[1] == IlluminationActionType.SYSTEM_EXTRACT
    assert FORM_ACTION_TYPE_MAP[2] == IlluminationActionType.SYSTEM_EXTRACT
    assert FORM_ACTION_TYPE_MAP[3] == IlluminationActionType.SYSTEM_EXTRACT

    # Persona probe for Form 6
    assert FORM_ACTION_TYPE_MAP[6] == IlluminationActionType.PERSONA_PROBE

    # Shelf requests for the rest
    assert FORM_ACTION_TYPE_MAP[4] == IlluminationActionType.SHELF_REQUEST
    assert FORM_ACTION_TYPE_MAP[5] == IlluminationActionType.SHELF_REQUEST
    assert FORM_ACTION_TYPE_MAP[7] == IlluminationActionType.SHELF_REQUEST
    assert FORM_ACTION_TYPE_MAP[8] == IlluminationActionType.SHELF_REQUEST


@pytest.mark.asyncio
async def test_multiple_missing_forms_create_multiple_actions() -> None:
    """Multiple missing forms create one action each."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add_all = MagicMock()

    planner = IlluminationPlannerService(session)
    missing_forms = [
        {"form_number": 2, "form_name": "sequences", "recommended_probes": [], "probe_type": "sequence"},
        {"form_number": 6, "form_name": "personas", "recommended_probes": [], "probe_type": "performer"},
        {"form_number": 8, "form_name": "evidence", "recommended_probes": [], "probe_type": "existence"},
    ]

    actions = await planner.create_illumination_plan(
        engagement_id=str(ENGAGEMENT_ID),
        element_id=ELEMENT_ID,
        element_name="Activity A",
        missing_forms=missing_forms,
    )

    assert len(actions) == 3
    action_types = {a["action_type"] for a in actions}
    assert IlluminationActionType.SYSTEM_EXTRACT in action_types
    assert IlluminationActionType.PERSONA_PROBE in action_types
    assert IlluminationActionType.SHELF_REQUEST in action_types
