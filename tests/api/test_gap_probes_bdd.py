"""BDD tests for Story #327: Probe Generation from Knowledge Gaps.

Tests gap-targeted probe generation with brightness-based prioritization
and form-to-probe-type mapping.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import create_app
from src.core.auth import get_current_user
from src.core.models import Engagement, User, UserRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENGAGEMENT_ID = uuid.uuid4()
ACTIVITY_APPROVE = str(uuid.uuid4())
ACTIVITY_REVIEW = str(uuid.uuid4())
ACTIVITY_SUBMIT = str(uuid.uuid4())


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


# ---------------------------------------------------------------------------
# Mock graph that returns activity-specific data
# ---------------------------------------------------------------------------


def _build_mock_run_query(
    activity_ids: list[str],
    brightness_map: dict[str, str],
    form_coverage: dict[str, set[str]],  # edge_type_key -> set of covered activity_ids
) -> Any:
    """Build a mock run_query function with configurable coverage.

    Args:
        activity_ids: IDs of activities in the engagement.
        brightness_map: activity_id -> brightness classification.
        form_coverage: First edge type per form -> set of covered activity IDs (outbound).
    """

    async def mock_run_query(query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        # Centrality query (degree count) — check before activity listing
        if "count(r) AS degree" in query:
            return [{"activity_id": aid, "degree": 3} for aid in activity_ids]

        # Brightness query
        if "brightness" in query and "type(r)" not in query:
            return [{"activity_id": aid, "brightness": brightness_map.get(aid, "dim")} for aid in activity_ids]

        # Activity listing (no edge types, no brightness, no degree)
        if "RETURN a.id AS activity_id" in query and "type(r)" not in query:
            return [{"activity_id": aid} for aid in activity_ids]

        # Form coverage queries (parameterized $edge_types)
        edge_types = params.get("edge_types", [])
        is_outbound = "-[r]->()" in query

        for edge_key, covered_ids in form_coverage.items():
            if edge_key in edge_types:
                if is_outbound:
                    return [{"activity_id": aid} for aid in covered_ids if aid in activity_ids]
                return []

        return []

    return mock_run_query


# ---------------------------------------------------------------------------
# Scenario 1: Rule Probe Generated for Dark Segment Missing Form 5
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_1_dark_activity_generates_rule_probe() -> None:
    """Given Activity 'Approve Loan' is DARK with Form 5 missing,
    a GOVERNANCE probe is generated for that activity."""
    eng = _make_engagement(ENGAGEMENT_ID)
    session = _mock_session_with_engagement(eng)
    app = _make_app(session)

    # Form coverage: all forms covered EXCEPT GOVERNED_BY/HAS_RULE for ACTIVITY_APPROVE
    form_coverage = {
        "PRECEDES": {ACTIVITY_APPROVE},
        "DEPENDS_ON": {ACTIVITY_APPROVE},
        "CONSUMES": {ACTIVITY_APPROVE},
        "GOVERNED_BY": set(),  # Form 5 missing!
        "PERFORMED_BY": {ACTIVITY_APPROVE},
        "REQUIRES_CONTROL": {ACTIVITY_APPROVE},
        "SUPPORTED_BY": {ACTIVITY_APPROVE},
        "CONTRADICTS": {ACTIVITY_APPROVE},
    }

    with patch("src.api.routes.gap_probes.KnowledgeGraphService") as mock_graph_cls:
        mock_graph = mock_graph_cls.return_value
        mock_graph.run_query = AsyncMock(
            side_effect=_build_mock_run_query(
                [ACTIVITY_APPROVE],
                {ACTIVITY_APPROVE: "dark"},
                form_coverage,
            )
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/gap-probes?limit=20")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_probes"] >= 1

    # Find probe for Form 5
    form5_probes = [p for p in data["probes"] if p["form_number"] == 5]
    assert len(form5_probes) == 1
    assert form5_probes[0]["probe_type"] == "governance"
    assert form5_probes[0]["brightness"] == "dark"
    assert form5_probes[0]["estimated_uplift"] > 0


# ---------------------------------------------------------------------------
# Scenario 2: Probe Prioritization by Estimated Confidence Uplift
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_2_probes_prioritized_by_uplift() -> None:
    """Given multiple Dim and Dark activities, probes are ranked
    by estimated confidence uplift with DARK > DIM."""
    eng = _make_engagement(ENGAGEMENT_ID)
    session = _mock_session_with_engagement(eng)
    app = _make_app(session)

    # Two activities: one DARK, one DIM. Both missing Form 5.
    form_coverage = {
        "PRECEDES": {ACTIVITY_APPROVE, ACTIVITY_REVIEW},
        "DEPENDS_ON": {ACTIVITY_APPROVE, ACTIVITY_REVIEW},
        "CONSUMES": {ACTIVITY_APPROVE, ACTIVITY_REVIEW},
        "GOVERNED_BY": set(),  # Form 5 missing for both
        "PERFORMED_BY": {ACTIVITY_APPROVE, ACTIVITY_REVIEW},
        "REQUIRES_CONTROL": {ACTIVITY_APPROVE, ACTIVITY_REVIEW},
        "SUPPORTED_BY": {ACTIVITY_APPROVE, ACTIVITY_REVIEW},
        "CONTRADICTS": {ACTIVITY_APPROVE, ACTIVITY_REVIEW},
    }

    with patch("src.api.routes.gap_probes.KnowledgeGraphService") as mock_graph_cls:
        mock_graph = mock_graph_cls.return_value
        mock_graph.run_query = AsyncMock(
            side_effect=_build_mock_run_query(
                [ACTIVITY_APPROVE, ACTIVITY_REVIEW],
                {ACTIVITY_APPROVE: "dark", ACTIVITY_REVIEW: "dim"},
                form_coverage,
            )
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/gap-probes?limit=20")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_probes"] >= 2

    # Probes should be sorted descending by uplift
    uplifts = [p["estimated_uplift"] for p in data["probes"]]
    assert uplifts == sorted(uplifts, reverse=True)

    # Dark activity should have higher uplift than dim for same form
    form5_probes = [p for p in data["probes"] if p["form_number"] == 5]
    assert len(form5_probes) == 2
    dark_probe = next(p for p in form5_probes if p["brightness"] == "dark")
    dim_probe = next(p for p in form5_probes if p["brightness"] == "dim")
    assert dark_probe["estimated_uplift"] > dim_probe["estimated_uplift"]


# ---------------------------------------------------------------------------
# Scenario 3: No Duplicate Probes for Fully Covered Activities
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_3_fully_covered_skipped() -> None:
    """Given an activity with all 9 forms covered, no probes generated."""
    eng = _make_engagement(ENGAGEMENT_ID)
    session = _mock_session_with_engagement(eng)
    app = _make_app(session)

    # All forms covered for ACTIVITY_SUBMIT
    all_covered = {ACTIVITY_SUBMIT}
    form_coverage = {
        "PRECEDES": all_covered,
        "DEPENDS_ON": all_covered,
        "CONSUMES": all_covered,
        "GOVERNED_BY": all_covered,
        "PERFORMED_BY": all_covered,
        "REQUIRES_CONTROL": all_covered,
        "SUPPORTED_BY": all_covered,
        "CONTRADICTS": all_covered,
    }

    with patch("src.api.routes.gap_probes.KnowledgeGraphService") as mock_graph_cls:
        mock_graph = mock_graph_cls.return_value
        mock_graph.run_query = AsyncMock(
            side_effect=_build_mock_run_query(
                [ACTIVITY_SUBMIT],
                {ACTIVITY_SUBMIT: "dim"},
                form_coverage,
            )
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/gap-probes")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_probes"] == 0
    assert data["probes"] == []


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_activities_returns_empty() -> None:
    """Empty engagement returns no probes."""
    eng = _make_engagement(ENGAGEMENT_ID)
    session = _mock_session_with_engagement(eng)
    app = _make_app(session)

    with patch("src.api.routes.gap_probes.KnowledgeGraphService") as mock_graph_cls:
        mock_graph = mock_graph_cls.return_value
        mock_graph.run_query = AsyncMock(return_value=[])

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/gap-probes")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_probes"] == 0


@pytest.mark.asyncio
async def test_engagement_not_found_returns_404() -> None:
    """Non-existent engagement returns 404."""
    session = _mock_session_with_engagement(None)
    app = _make_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/v1/engagements/{uuid.uuid4()}/gap-probes")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_generate_endpoint_returns_count() -> None:
    """POST /gap-probes/generate returns probe count."""
    eng = _make_engagement(ENGAGEMENT_ID)
    session = _mock_session_with_engagement(eng)
    app = _make_app(session)

    # One activity, missing Form 5 → 1 probe
    form_coverage = {
        "PRECEDES": {ACTIVITY_APPROVE},
        "DEPENDS_ON": {ACTIVITY_APPROVE},
        "CONSUMES": {ACTIVITY_APPROVE},
        "GOVERNED_BY": set(),
        "PERFORMED_BY": {ACTIVITY_APPROVE},
        "REQUIRES_CONTROL": {ACTIVITY_APPROVE},
        "SUPPORTED_BY": {ACTIVITY_APPROVE},
        "CONTRADICTS": {ACTIVITY_APPROVE},
    }

    with patch("src.api.routes.gap_probes.KnowledgeGraphService") as mock_graph_cls:
        mock_graph = mock_graph_cls.return_value
        mock_graph.run_query = AsyncMock(
            side_effect=_build_mock_run_query(
                [ACTIVITY_APPROVE],
                {ACTIVITY_APPROVE: "dark"},
                form_coverage,
            )
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/v1/engagements/{ENGAGEMENT_ID}/gap-probes/generate")

    assert resp.status_code == 201
    data = resp.json()
    assert data["probes_generated"] >= 1
    assert "Generated" in data["message"]


@pytest.mark.asyncio
async def test_generate_engagement_not_found_returns_404() -> None:
    """POST /gap-probes/generate with non-existent engagement returns 404."""
    session = _mock_session_with_engagement(None)
    app = _make_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(f"/api/v1/engagements/{uuid.uuid4()}/gap-probes/generate")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_pagination_offset_and_limit() -> None:
    """GET /gap-probes with offset and limit returns correct slice."""
    eng = _make_engagement(ENGAGEMENT_ID)
    session = _mock_session_with_engagement(eng)
    app = _make_app(session)

    # Two activities, both DARK, both missing multiple forms → many probes
    form_coverage: dict[str, set[str]] = {
        "PRECEDES": set(),
        "DEPENDS_ON": set(),
        "CONSUMES": set(),
        "GOVERNED_BY": set(),
        "PERFORMED_BY": set(),
        "REQUIRES_CONTROL": set(),
        "SUPPORTED_BY": set(),
        "CONTRADICTS": set(),
    }

    with patch("src.api.routes.gap_probes.KnowledgeGraphService") as mock_graph_cls:
        mock_graph = mock_graph_cls.return_value
        mock_graph.run_query = AsyncMock(
            side_effect=_build_mock_run_query(
                [ACTIVITY_APPROVE, ACTIVITY_REVIEW],
                {ACTIVITY_APPROVE: "dark", ACTIVITY_REVIEW: "dark"},
                form_coverage,
            )
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Get all probes first
            resp_all = await client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/gap-probes?limit=200")
            # Get paginated slice
            resp_page = await client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/gap-probes?limit=2&offset=1")

    assert resp_all.status_code == 200
    assert resp_page.status_code == 200

    all_data = resp_all.json()
    page_data = resp_page.json()

    # total_probes should be the same regardless of pagination
    assert page_data["total_probes"] == all_data["total_probes"]
    assert page_data["total_probes"] > 3  # enough probes to test pagination
    # paginated result should have exactly 2 probes
    assert len(page_data["probes"]) == 2
    # Verify offset works: paginated probes should match the slice structure
    # (same form_number/activity_id at offset 1, since probes are recomputed
    # deterministically in the same order)
    assert page_data["probes"][0]["form_number"] == all_data["probes"][1]["form_number"]
    assert page_data["probes"][0]["activity_id"] == all_data["probes"][1]["activity_id"]


@pytest.mark.asyncio
async def test_bright_activities_skipped() -> None:
    """BRIGHT activities produce no probes even with missing forms."""
    eng = _make_engagement(ENGAGEMENT_ID)
    session = _mock_session_with_engagement(eng)
    app = _make_app(session)

    form_coverage = {
        "PRECEDES": set(),
        "DEPENDS_ON": set(),
        "CONSUMES": set(),
        "GOVERNED_BY": set(),
        "PERFORMED_BY": set(),
        "REQUIRES_CONTROL": set(),
        "SUPPORTED_BY": set(),
        "CONTRADICTS": set(),
    }

    with patch("src.api.routes.gap_probes.KnowledgeGraphService") as mock_graph_cls:
        mock_graph = mock_graph_cls.return_value
        mock_graph.run_query = AsyncMock(
            side_effect=_build_mock_run_query(
                [ACTIVITY_APPROVE],
                {ACTIVITY_APPROVE: "bright"},
                form_coverage,
            )
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/gap-probes")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_probes"] == 0


# ---------------------------------------------------------------------------
# Service Unit Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_form_to_probe_type_mapping_complete() -> None:
    """Every KnowledgeForm has a probe type mapping."""
    from src.governance.knowledge_forms import KnowledgeForm
    from src.semantic.gap_probe_generator import FORM_TO_PROBE_TYPE

    for form in KnowledgeForm:
        assert form in FORM_TO_PROBE_TYPE, f"Missing probe type mapping for {form.value}"


@pytest.mark.asyncio
async def test_form_weights_complete() -> None:
    """Every KnowledgeForm has a weight for uplift calculation."""
    from src.governance.knowledge_forms import KnowledgeForm
    from src.semantic.gap_probe_generator import FORM_WEIGHTS

    for form in KnowledgeForm:
        assert form in FORM_WEIGHTS, f"Missing weight for {form.value}"
        assert FORM_WEIGHTS[form] > 0


@pytest.mark.asyncio
async def test_uplift_formula() -> None:
    """Uplift = weight × centrality × brightness_multiplier."""
    from src.semantic.gap_probe_generator import GapProbeGenerator

    # Create a minimal generator (graph_service not needed for _compute_uplift)
    gen = GapProbeGenerator.__new__(GapProbeGenerator)

    # DARK at full centrality with weight=1.2 (RULES)
    from src.governance.knowledge_forms import KnowledgeForm

    uplift = gen._compute_uplift(KnowledgeForm.RULES, "dark", 1.0)
    assert uplift == 1.2  # 1.2 × 1.0 × 1.0

    # DIM at half centrality
    uplift_dim = gen._compute_uplift(KnowledgeForm.RULES, "dim", 0.5)
    assert uplift_dim == 0.3  # 1.2 × 0.5 × 0.5

    # BRIGHT → 0
    uplift_bright = gen._compute_uplift(KnowledgeForm.RULES, "bright", 1.0)
    assert uplift_bright == 0.0
