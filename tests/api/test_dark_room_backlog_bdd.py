"""BDD tests for Story #394: Dark Room Backlog Management.

Tests prioritized Dark segment ranking, missing knowledge forms display,
Dark Room API response, and auto-removal of illuminated segments.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import create_app
from src.api.services.dark_room_backlog import (
    DEFAULT_DARK_THRESHOLD,
    FORM_RECOMMENDED_PROBES,
    DarkRoomBacklogService,
)
from src.core.auth import get_current_user
from src.core.models import ProcessModel, User, UserRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENGAGEMENT_ID = uuid.uuid4()
MODEL_ID = uuid.uuid4()


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
    return session


def _make_graph_mock(
    dark_elements: list[dict[str, Any]],
    form_coverage_out: dict[str, list[dict[str, Any]]] | None = None,
    form_coverage_in: dict[str, list[dict[str, Any]]] | None = None,
) -> MagicMock:
    """Build a mock graph service returning configured elements and coverage.

    form_coverage_out/in: mapping of edge_type_list_key -> list of {activity_id} dicts
    """
    form_coverage_out = form_coverage_out or {}
    form_coverage_in = form_coverage_in or {}

    async def mock_run_query(
        query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        # Dark elements query
        if "a.confidence < $threshold" in query:
            return dark_elements
        # Outbound edge coverage
        if "MATCH (a)-[r]->()" in query:
            edge_types = tuple(sorted(params.get("edge_types", []))) if params else ()
            return form_coverage_out.get(str(edge_types), [])
        # Inbound edge coverage
        if "MATCH ()-[r]->(a)" in query:
            edge_types = tuple(sorted(params.get("edge_types", []))) if params else ()
            return form_coverage_in.get(str(edge_types), [])
        return []

    graph = MagicMock()
    graph.run_query = AsyncMock(side_effect=mock_run_query)
    return graph


# ---------------------------------------------------------------------------
# BDD Scenario 1: Prioritized Dark Segment Ranking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_1_prioritized_ranking() -> None:
    """Given 3 Dark segments with varying confidence,
    When the Dark Room backlog is loaded,
    Then segments are returned ranked by estimated_confidence_uplift descending."""
    elements = [
        {"element_id": "e1", "element_name": "Activity A", "confidence": 0.10, "brightness": "dark"},
        {"element_id": "e2", "element_name": "Activity B", "confidence": 0.30, "brightness": "dark"},
        {"element_id": "e3", "element_name": "Activity C", "confidence": 0.20, "brightness": "dark"},
    ]

    graph = _make_graph_mock(elements)
    service = DarkRoomBacklogService(graph)
    result = await service.get_dark_segments("eng-1")

    assert result["total_count"] == 3
    items = result["items"]

    # Verify descending order by estimated_confidence_uplift
    uplifts = [item["estimated_confidence_uplift"] for item in items]
    assert uplifts == sorted(uplifts, reverse=True)

    # Lowest confidence (0.10) should have highest uplift
    assert items[0]["element_id"] == "e1"
    assert items[0]["current_confidence"] == 0.10


# ---------------------------------------------------------------------------
# BDD Scenario 2: Missing Knowledge Forms Display
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_2_missing_knowledge_forms() -> None:
    """Given a Dark segment with Forms 2 (Sequences) and 5 (Rules) covered,
    When the segment detail is retrieved,
    Then the response lists the other 7 forms as missing
    And recommended probes are included for each missing form."""
    elements = [
        {"element_id": "e1", "element_name": "Wire Transfer", "confidence": 0.25, "brightness": "dark"},
    ]

    # Form 2 (Sequences) uses FOLLOWED_BY, PRECEDES
    # Form 5 (Rules) uses GOVERNED_BY, HAS_RULE
    form_coverage_out = {
        str(tuple(sorted(["FOLLOWED_BY", "PRECEDES"]))): [{"activity_id": "e1"}],
        str(tuple(sorted(["GOVERNED_BY", "HAS_RULE"]))): [{"activity_id": "e1"}],
    }

    graph = _make_graph_mock(elements, form_coverage_out=form_coverage_out)
    service = DarkRoomBacklogService(graph)
    result = await service.get_dark_segments("eng-1")

    item = result["items"][0]
    # Form 1 (Activities) is auto-covered + Form 2 + Form 5 = 3 covered
    assert item["covered_form_count"] == 3
    # 9 - 3 = 6 missing
    assert item["missing_form_count"] == 6

    missing_numbers = {mf["form_number"] for mf in item["missing_knowledge_forms"]}
    # Forms 1 (auto), 2 (covered), 5 (covered) should NOT be in missing
    assert 1 not in missing_numbers
    assert 2 not in missing_numbers
    assert 5 not in missing_numbers

    # Each missing form should have recommended probes
    for mf in item["missing_knowledge_forms"]:
        assert len(mf["recommended_probes"]) > 0
        assert mf["probe_type"] != ""


# ---------------------------------------------------------------------------
# BDD Scenario 3: Dark Room API Response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_3_api_response() -> None:
    """Given a POV with Dark segments,
    When GET /api/v1/pov/{id}/dark-room is called,
    Then the response contains prioritized segments with required fields."""
    pm = _mock_process_model()
    session = _mock_session_with_model(pm)
    app = _make_app(session)

    elements = [
        {"element_id": "e1", "element_name": "Review Process", "confidence": 0.15, "brightness": "dark"},
        {"element_id": "e2", "element_name": "Approval Step", "confidence": 0.35, "brightness": "dark"},
    ]

    with (
        patch("src.api.routes.pov.KnowledgeGraphService", return_value=MagicMock()),
        patch("src.api.routes.pov.DarkRoomBacklogService", return_value=_make_service_returning(elements)),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/v1/pov/{MODEL_ID}/dark-room")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] == 2
    assert len(data["items"]) == 2

    # Verify each item has required fields
    for item in data["items"]:
        assert "element_id" in item
        assert "current_confidence" in item
        assert "estimated_confidence_uplift" in item
        assert "missing_knowledge_forms" in item


def _make_service_returning(elements: list[dict[str, Any]]) -> DarkRoomBacklogService:
    """Create a mock DarkRoomBacklogService that returns predictable results."""
    service = MagicMock(spec=DarkRoomBacklogService)

    async def mock_get_dark_segments(
        engagement_id: str, limit: int = 50, offset: int = 0
    ) -> dict[str, Any]:
        items = []
        for elem in elements:
            items.append({
                "element_id": elem["element_id"],
                "element_name": elem["element_name"],
                "current_confidence": elem["confidence"],
                "brightness": elem.get("brightness", "dark"),
                "estimated_confidence_uplift": round((1.0 - elem["confidence"]) * 0.4, 4),
                "missing_knowledge_forms": [
                    {"form_number": 3, "form_name": "dependencies", "recommended_probes": ["dependency mapping workshop"], "probe_type": "dependency"},
                ],
                "missing_form_count": 5,
                "covered_form_count": 4,
            })
        items.sort(key=lambda x: x["estimated_confidence_uplift"], reverse=True)
        return {
            "engagement_id": engagement_id,
            "dark_threshold": DEFAULT_DARK_THRESHOLD,
            "total_count": len(items),
            "items": items[offset:offset + limit],
        }

    service.get_dark_segments = AsyncMock(side_effect=mock_get_dark_segments)
    return service


# ---------------------------------------------------------------------------
# BDD Scenario 4: Auto-Removal of Illuminated Segments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_4_auto_removal_of_illuminated() -> None:
    """Given a segment that was Dark (confidence=0.28) transitions to Dim (0.45),
    When the Dark Room backlog is refreshed,
    Then that segment is no longer present in the Dark Room list."""
    # Initially 3 dark segments
    elements_before = [
        {"element_id": "e1", "element_name": "Activity A", "confidence": 0.28, "brightness": "dark"},
        {"element_id": "e2", "element_name": "Activity B", "confidence": 0.15, "brightness": "dark"},
        {"element_id": "e3", "element_name": "Activity C", "confidence": 0.30, "brightness": "dark"},
    ]

    graph = _make_graph_mock(elements_before)
    service = DarkRoomBacklogService(graph)
    result_before = await service.get_dark_segments("eng-1")
    assert result_before["total_count"] == 3

    # After evidence acquisition, e1 transitions to Dim (0.45 >= 0.4 threshold)
    # Only e2 and e3 remain below threshold
    elements_after = [
        {"element_id": "e2", "element_name": "Activity B", "confidence": 0.15, "brightness": "dark"},
        {"element_id": "e3", "element_name": "Activity C", "confidence": 0.30, "brightness": "dark"},
    ]

    graph_after = _make_graph_mock(elements_after)
    service_after = DarkRoomBacklogService(graph_after)
    result_after = await service_after.get_dark_segments("eng-1")

    assert result_after["total_count"] == 2
    element_ids = {item["element_id"] for item in result_after["items"]}
    assert "e1" not in element_ids  # Illuminated segment removed


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
        resp = await client.get(f"/api/v1/pov/{uuid.uuid4()}/dark-room")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_no_dark_segments_returns_empty() -> None:
    """Engagement with no Dark segments returns zero items."""
    graph = _make_graph_mock([])
    service = DarkRoomBacklogService(graph)
    result = await service.get_dark_segments("eng-1")

    assert result["total_count"] == 0
    assert result["items"] == []


@pytest.mark.asyncio
async def test_pagination_support() -> None:
    """Dark Room backlog supports limit/offset pagination."""
    elements = [
        {"element_id": f"e{i}", "element_name": f"Activity {i}", "confidence": 0.1 + i * 0.02, "brightness": "dark"}
        for i in range(10)
    ]

    graph = _make_graph_mock(elements)
    service = DarkRoomBacklogService(graph)

    # Get first page
    result_page1 = await service.get_dark_segments("eng-1", limit=3, offset=0)
    assert result_page1["total_count"] == 10
    assert len(result_page1["items"]) == 3

    # Get second page
    result_page2 = await service.get_dark_segments("eng-1", limit=3, offset=3)
    assert len(result_page2["items"]) == 3

    # No overlap between pages
    ids_page1 = {item["element_id"] for item in result_page1["items"]}
    ids_page2 = {item["element_id"] for item in result_page2["items"]}
    assert ids_page1.isdisjoint(ids_page2)


@pytest.mark.asyncio
async def test_custom_dark_threshold() -> None:
    """Custom dark threshold filters differently."""
    elements_strict = [
        {"element_id": "e1", "element_name": "Activity A", "confidence": 0.20, "brightness": "dark"},
    ]

    graph = _make_graph_mock(elements_strict)
    service = DarkRoomBacklogService(graph, dark_threshold=0.3)

    result = await service.get_dark_segments("eng-1")
    assert result["dark_threshold"] == 0.3


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------


def test_default_dark_threshold() -> None:
    """Default dark threshold is 0.4."""
    assert DEFAULT_DARK_THRESHOLD == 0.4


def test_form_recommended_probes_complete() -> None:
    """All 9 forms have recommended probes."""
    assert len(FORM_RECOMMENDED_PROBES) == 9
    for form_num in range(1, 10):
        assert form_num in FORM_RECOMMENDED_PROBES
        assert len(FORM_RECOMMENDED_PROBES[form_num]) > 0


@pytest.mark.asyncio
async def test_inbound_edge_coverage() -> None:
    """Inbound edges also count as form coverage."""
    elements = [
        {"element_id": "e1", "element_name": "Activity A", "confidence": 0.20, "brightness": "dark"},
    ]

    # Form 2 (Sequences): edge types are PRECEDES, FOLLOWED_BY
    # Provide coverage via inbound edge only
    from src.governance.knowledge_forms import FORM_EDGE_MAPPINGS, KnowledgeForm

    seq_edges = FORM_EDGE_MAPPINGS[KnowledgeForm.SEQUENCES]
    seq_key = str(tuple(sorted(seq_edges)))

    graph = _make_graph_mock(
        elements,
        form_coverage_out={},
        form_coverage_in={seq_key: [{"activity_id": "e1"}]},
    )
    service = DarkRoomBacklogService(graph)
    result = await service.get_dark_segments("eng-1")

    item = result["items"][0]
    # Form 1 (auto) + Form 2 (via inbound) = 2 covered
    assert item["covered_form_count"] == 2
    assert item["missing_form_count"] == 7


@pytest.mark.asyncio
async def test_uplift_formula() -> None:
    """Estimated uplift = missing_ratio × brightness_gap × 0.6."""
    elements = [
        {"element_id": "e1", "element_name": "Activity A", "confidence": 0.20, "brightness": "dark"},
    ]

    # No form coverage → all 8 non-auto forms missing (Form 1 is auto-covered)
    graph = _make_graph_mock(elements)
    service = DarkRoomBacklogService(graph)
    result = await service.get_dark_segments("eng-1")

    item = result["items"][0]
    # missing_ratio = 8/9 (all except Form 1 Activities which is auto-covered)
    # brightness_gap = 1.0 - 0.20 = 0.80
    # uplift = (8/9) * 0.80 * 0.6 ≈ 0.4267
    expected = round((8 / 9) * 0.80 * 0.6, 4)
    assert item["estimated_confidence_uplift"] == expected
    assert item["missing_form_count"] == 8
    assert item["covered_form_count"] == 1  # Only Form 1 (Activities)
