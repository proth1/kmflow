"""BDD tests for Story #399: Integration with Shelf Data Request Workflow.

Tests auto-creation of shelf items from epistemic actions, follow-through
rate computation, and source attribution in request reporting.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import create_app
from src.api.services.shelf_integration import (
    CATEGORY_MAP,
    PRIORITY_MAP,
    ShelfIntegrationService,
)
from src.core.auth import get_current_user
from src.core.models import (
    EpistemicAction,
    EvidenceCategory,
    ShelfDataRequestItem,
    ShelfRequestItemPriority,
    ShelfRequestItemSource,
    User,
    UserRole,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENGAGEMENT_ID = uuid.uuid4()
SCENARIO_ID = uuid.uuid4()
SHELF_REQUEST_ID = uuid.uuid4()


def _mock_user() -> User:
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.role = UserRole.PLATFORM_ADMIN
    return u


def _make_app(mock_session: AsyncMock) -> Any:
    from src.api.deps import get_session

    app = create_app()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    return app


def _mock_epistemic_action(
    *,
    action_id: uuid.UUID | None = None,
    element_name: str = "Wire Transfer Review",
    category: str = "documents",
    uplift: float = 0.12,
    priority: str = "high",
) -> MagicMock:
    """Create a mock EpistemicAction."""
    action = MagicMock(spec=EpistemicAction)
    action.id = action_id or uuid.uuid4()
    action.target_element_id = str(uuid.uuid4())
    action.target_element_name = element_name
    action.evidence_gap_description = f"Missing evidence for {element_name}"
    action.current_confidence = 0.2
    action.estimated_confidence_uplift = uplift
    action.projected_confidence = 0.2 + uplift
    action.information_gain_score = 0.06
    action.recommended_evidence_category = category
    action.priority = priority
    action.shelf_request_id = None
    return action


# ---------------------------------------------------------------------------
# BDD Scenario 1: Auto-Creation of Shelf Request from Epistemic Action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_1_auto_create_shelf_items() -> None:
    """Given an epistemic action recommending evidence collection,
    When auto_create_shelf_items is called,
    Then a ShelfDataRequestItem is created with planner source and
    epistemic_action_id linked."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    action = _mock_epistemic_action(category="documents", priority="high")
    service = ShelfIntegrationService(session)

    items = await service.auto_create_shelf_items(
        engagement_id=ENGAGEMENT_ID,
        epistemic_actions=[action],
        shelf_request_id=SHELF_REQUEST_ID,
    )

    assert len(items) == 1
    item = items[0]
    assert item["epistemic_action_id"] == str(action.id)
    assert item["source"] == "planner"
    assert item["category"] == "documents"
    assert item["priority"] == "high"
    assert "[Planner]" in item["item_name"]

    # Verify session.add was called with a ShelfDataRequestItem
    session.add.assert_called_once()
    added_item = session.add.call_args[0][0]
    assert isinstance(added_item, ShelfDataRequestItem)
    assert added_item.epistemic_action_id == action.id
    assert added_item.source == ShelfRequestItemSource.PLANNER
    assert added_item.request_id == SHELF_REQUEST_ID


@pytest.mark.asyncio
async def test_scenario_1_multiple_actions_create_multiple_items() -> None:
    """Multiple epistemic actions create one shelf item each."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    actions = [
        _mock_epistemic_action(category="documents", priority="high"),
        _mock_epistemic_action(
            element_name="Loan Approval",
            category="bpm_process_models",
            priority="medium",
        ),
        _mock_epistemic_action(
            element_name="Policy Review",
            category="controls_evidence",
            priority="low",
        ),
    ]

    service = ShelfIntegrationService(session)
    items = await service.auto_create_shelf_items(
        engagement_id=ENGAGEMENT_ID,
        epistemic_actions=actions,
        shelf_request_id=SHELF_REQUEST_ID,
    )

    assert len(items) == 3
    assert session.add.call_count == 3
    assert items[0]["category"] == "documents"
    assert items[1]["category"] == "bpm_process_models"
    assert items[2]["category"] == "controls_evidence"


# ---------------------------------------------------------------------------
# BDD Scenario 2: Follow-Through Rate Calculation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_2_follow_through_rate_60_percent() -> None:
    """Given 20 epistemic actions and 12 linked shelf items,
    When follow-through rate is computed,
    Then rate is 60% and meets the 50% target."""
    session = AsyncMock()

    # First query: count total epistemic actions → 20
    total_result = MagicMock()
    total_result.scalar.return_value = 20

    # Second query: count linked shelf items → 12
    linked_result = MagicMock()
    linked_result.scalar.return_value = 12

    session.execute = AsyncMock(side_effect=[total_result, linked_result])

    service = ShelfIntegrationService(session)
    rate = await service.get_follow_through_rate(ENGAGEMENT_ID)

    assert rate["total_epistemic_actions"] == 20
    assert rate["linked_shelf_items"] == 12
    assert rate["follow_through_rate"] == 60.0
    assert rate["target_rate"] == 50.0
    assert rate["meets_target"] is True


@pytest.mark.asyncio
async def test_scenario_2_follow_through_rate_below_target() -> None:
    """Given 20 actions and 8 linked items,
    When follow-through rate is computed,
    Then rate is 40% and does not meet the 50% target."""
    session = AsyncMock()

    total_result = MagicMock()
    total_result.scalar.return_value = 20
    linked_result = MagicMock()
    linked_result.scalar.return_value = 8

    session.execute = AsyncMock(side_effect=[total_result, linked_result])

    service = ShelfIntegrationService(session)
    rate = await service.get_follow_through_rate(ENGAGEMENT_ID)

    assert rate["follow_through_rate"] == 40.0
    assert rate["meets_target"] is False


@pytest.mark.asyncio
async def test_scenario_2_follow_through_rate_zero_actions() -> None:
    """Given 0 epistemic actions,
    When follow-through rate is computed,
    Then rate is 0% (no division by zero)."""
    session = AsyncMock()

    total_result = MagicMock()
    total_result.scalar.return_value = 0
    linked_result = MagicMock()
    linked_result.scalar.return_value = 0

    session.execute = AsyncMock(side_effect=[total_result, linked_result])

    service = ShelfIntegrationService(session)
    rate = await service.get_follow_through_rate(ENGAGEMENT_ID)

    assert rate["total_epistemic_actions"] == 0
    assert rate["follow_through_rate"] == 0.0
    assert rate["meets_target"] is False


@pytest.mark.asyncio
async def test_scenario_2_follow_through_rate_100_percent() -> None:
    """Given 10 actions and 10 linked items,
    When follow-through rate is computed,
    Then rate is 100%."""
    session = AsyncMock()

    total_result = MagicMock()
    total_result.scalar.return_value = 10
    linked_result = MagicMock()
    linked_result.scalar.return_value = 10

    session.execute = AsyncMock(side_effect=[total_result, linked_result])

    service = ShelfIntegrationService(session)
    rate = await service.get_follow_through_rate(ENGAGEMENT_ID)

    assert rate["follow_through_rate"] == 100.0
    assert rate["meets_target"] is True


# ---------------------------------------------------------------------------
# BDD Scenario 3: Source Attribution in Request Reporting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_3_api_follow_through_rate() -> None:
    """GET /shelf-requests/follow-through-rate returns follow-through rate."""
    session = AsyncMock()
    app = _make_app(session)

    mock_rate = {
        "engagement_id": str(ENGAGEMENT_ID),
        "total_epistemic_actions": 20,
        "linked_shelf_items": 12,
        "follow_through_rate": 60.0,
        "target_rate": 50.0,
        "meets_target": True,
    }

    with patch(
        "src.api.services.shelf_integration.ShelfIntegrationService"
    ) as mock_cls:
        mock_service = mock_cls.return_value
        mock_service.get_follow_through_rate = AsyncMock(return_value=mock_rate)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/v1/shelf-requests/follow-through-rate?engagement_id={ENGAGEMENT_ID}"
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["follow_through_rate"] == 60.0
    assert data["meets_target"] is True


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_actions_returns_empty_items() -> None:
    """Given no epistemic actions,
    When auto_create_shelf_items is called,
    Then no items are created and flush is not called."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    service = ShelfIntegrationService(session)
    items = await service.auto_create_shelf_items(
        engagement_id=ENGAGEMENT_ID,
        epistemic_actions=[],
        shelf_request_id=SHELF_REQUEST_ID,
    )

    assert len(items) == 0
    session.add.assert_not_called()
    session.flush.assert_not_called()


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------


def test_category_map_complete() -> None:
    """CATEGORY_MAP covers key evidence categories."""
    assert "documents" in CATEGORY_MAP
    assert "bpm_process_models" in CATEGORY_MAP
    assert "controls_evidence" in CATEGORY_MAP
    assert "regulatory_policy" in CATEGORY_MAP
    assert "structured_data" in CATEGORY_MAP
    assert "domain_communications" in CATEGORY_MAP

    # Values are all EvidenceCategory instances
    for cat in CATEGORY_MAP.values():
        assert isinstance(cat, EvidenceCategory)


def test_priority_map_complete() -> None:
    """PRIORITY_MAP covers all priority levels."""
    assert PRIORITY_MAP["high"] == ShelfRequestItemPriority.HIGH
    assert PRIORITY_MAP["medium"] == ShelfRequestItemPriority.MEDIUM
    assert PRIORITY_MAP["low"] == ShelfRequestItemPriority.LOW


def test_source_enum_values() -> None:
    """ShelfRequestItemSource has planner and manual values."""
    assert ShelfRequestItemSource.PLANNER == "planner"
    assert ShelfRequestItemSource.MANUAL == "manual"
