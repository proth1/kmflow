"""BDD tests for Story #316: Nine Universal Process Knowledge Forms.

Tests knowledge form coverage computation and gap detection against
mocked Neo4j graph data.
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
ACTIVITY_A = str(uuid.uuid4())
ACTIVITY_B = str(uuid.uuid4())
ACTIVITY_C = str(uuid.uuid4())


def _mock_user() -> User:
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.role = UserRole.PLATFORM_ADMIN
    return u


def _mock_session_with_engagement(engagement: Any) -> AsyncMock:
    """Build a mock session that returns the given engagement from a SELECT."""
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
    """Create app with overridden dependencies."""
    from src.api.deps import get_session

    app = create_app()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    app.state.neo4j_driver = MagicMock()
    return app


# ---------------------------------------------------------------------------
# Scenario 1: Knowledge Form Coverage Computation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_1_coverage_computation() -> None:
    """Given an engagement with activities and graph edges,
    when coverage is computed, then all 9 forms show correct percentages."""
    eng = _make_engagement(ENGAGEMENT_ID)
    session = _mock_session_with_engagement(eng)
    app = _make_app(session)

    with patch("src.api.routes.knowledge_forms.KnowledgeGraphService") as mock_graph_cls:
        mock_graph = mock_graph_cls.return_value

        async def mock_run_query(query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            # Activity listing (no edge_types param)
            if "RETURN a.id AS activity_id" in query and "type(r)" not in query:
                return [
                    {"activity_id": ACTIVITY_A},
                    {"activity_id": ACTIVITY_B},
                    {"activity_id": ACTIVITY_C},
                ]
            edge_types = params.get("edge_types", [])
            is_outbound = "-[r]->()" in query
            # Sequences (PRECEDES/FOLLOWED_BY) - outbound A,B; inbound C
            if "PRECEDES" in edge_types:
                if is_outbound:
                    return [{"activity_id": ACTIVITY_A}, {"activity_id": ACTIVITY_B}]
                return [{"activity_id": ACTIVITY_C}]
            # Dependencies (DEPENDS_ON) - none
            if "DEPENDS_ON" in edge_types:
                return []
            # Inputs/Outputs (CONSUMES/PRODUCES) - outbound A only
            if "CONSUMES" in edge_types:
                return [{"activity_id": ACTIVITY_A}] if is_outbound else []
            # Rules (GOVERNED_BY/HAS_RULE) - none
            if "GOVERNED_BY" in edge_types:
                return []
            # Personas (PERFORMED_BY) - outbound all 3
            if "PERFORMED_BY" in edge_types:
                if is_outbound:
                    return [
                        {"activity_id": ACTIVITY_A},
                        {"activity_id": ACTIVITY_B},
                        {"activity_id": ACTIVITY_C},
                    ]
                return []
            # Controls (REQUIRES_CONTROL/MITIGATES) - A only
            if "REQUIRES_CONTROL" in edge_types:
                return [{"activity_id": ACTIVITY_A}] if is_outbound else []
            # Evidence (SUPPORTED_BY/EVIDENCED_BY) - A and B
            if "SUPPORTED_BY" in edge_types:
                if is_outbound:
                    return [{"activity_id": ACTIVITY_A}, {"activity_id": ACTIVITY_B}]
                return []
            # Uncertainty (CONTRADICTS/DEVIATES_FROM) - none
            if "CONTRADICTS" in edge_types:
                return []
            return []

        mock_graph.run_query = AsyncMock(side_effect=mock_run_query)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/knowledge-coverage")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_activities"] == 3
    assert len(data["forms"]) == 9

    # Form 1 (Activities) = 100% (all exist)
    form1 = next(f for f in data["forms"] if f["form_number"] == 1)
    assert form1["coverage_percentage"] == 100.0

    # Form 2 (Sequences) = 100% (all covered via outbound + inbound)
    form2 = next(f for f in data["forms"] if f["form_number"] == 2)
    assert form2["coverage_percentage"] == 100.0

    # Form 3 (Dependencies) = 0%
    form3 = next(f for f in data["forms"] if f["form_number"] == 3)
    assert form3["coverage_percentage"] == 0.0

    # Form 6 (Personas) = 100%
    form6 = next(f for f in data["forms"] if f["form_number"] == 6)
    assert form6["coverage_percentage"] == 100.0


# ---------------------------------------------------------------------------
# Scenario 2: Missing Form Detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_2_missing_form_detection() -> None:
    """Given activity A with PRECEDES and PERFORMED_BY but no GOVERNED_BY,
    Form 5 (Rules) should be flagged as missing."""
    eng = _make_engagement(ENGAGEMENT_ID)
    session = _mock_session_with_engagement(eng)
    app = _make_app(session)

    with patch("src.api.routes.knowledge_forms.KnowledgeGraphService") as mock_graph_cls:
        mock_graph = mock_graph_cls.return_value

        async def mock_run_query(query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            if "RETURN a.id AS activity_id" in query and "type(r)" not in query:
                return [{"activity_id": ACTIVITY_A}]
            edge_types = params.get("edge_types", [])
            is_outbound = "-[r]->()" in query
            if "PRECEDES" in edge_types and is_outbound:
                return [{"activity_id": ACTIVITY_A}]
            if "PERFORMED_BY" in edge_types and is_outbound:
                return [{"activity_id": ACTIVITY_A}]
            if "GOVERNED_BY" in edge_types:
                return []  # No rules!
            return []

        mock_graph.run_query = AsyncMock(side_effect=mock_run_query)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/knowledge-coverage")

    assert resp.status_code == 200
    data = resp.json()

    # Check per-activity for activity A
    activity = next(a for a in data["per_activity"] if a["activity_id"] == ACTIVITY_A)

    # Form 1 (Activities) should be present (auto-covered)
    assert 1 in activity["forms_present"]
    # Form 2 (Sequences) should be present
    assert 2 in activity["forms_present"]
    # Form 6 (Personas) should be present
    assert 6 in activity["forms_present"]
    # Form 5 (Rules) should be in gaps
    gap_numbers = [g["form_number"] for g in activity["gaps"]]
    assert 5 in gap_numbers


# ---------------------------------------------------------------------------
# Scenario 3: Full Coverage Completeness Score
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_3_full_coverage() -> None:
    """Given activity with all 9 forms, completeness = 100%."""
    eng = _make_engagement(ENGAGEMENT_ID)
    session = _mock_session_with_engagement(eng)
    app = _make_app(session)

    with patch("src.api.routes.knowledge_forms.KnowledgeGraphService") as mock_graph_cls:
        mock_graph = mock_graph_cls.return_value

        async def mock_run_query(query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            if "RETURN a.id AS activity_id" in query and "type(r)" not in query:
                return [{"activity_id": ACTIVITY_A}]
            # All edge types return ACTIVITY_A as covered
            if "-[r]->()" in query or "()-[r]->" in query:
                return [{"activity_id": ACTIVITY_A}]
            return []

        mock_graph.run_query = AsyncMock(side_effect=mock_run_query)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/knowledge-coverage")

    assert resp.status_code == 200
    data = resp.json()

    activity = data["per_activity"][0]
    assert activity["completeness_score"] == 100.0
    assert len(activity["gaps"]) == 0
    assert data["overall_completeness"] == 100.0


# ---------------------------------------------------------------------------
# Scenario 4: Knowledge Gaps Endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_4_knowledge_gaps() -> None:
    """Given Form 5 and Form 9 gaps, GET /knowledge-gaps returns gap entries
    with activity_id, form_number, and suggested_probe_type."""
    eng = _make_engagement(ENGAGEMENT_ID)
    session = _mock_session_with_engagement(eng)
    app = _make_app(session)

    with patch("src.api.routes.knowledge_forms.KnowledgeGraphService") as mock_graph_cls:
        mock_graph = mock_graph_cls.return_value

        async def mock_run_query(query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            if "RETURN a.id AS activity_id" in query and "type(r)" not in query:
                return [{"activity_id": ACTIVITY_A}, {"activity_id": ACTIVITY_B}]
            edge_types = params.get("edge_types", [])
            # GOVERNED_BY/HAS_RULE (Form 5) - neither covered
            if "GOVERNED_BY" in edge_types:
                return []
            # CONTRADICTS/DEVIATES_FROM (Form 9) - neither covered
            if "CONTRADICTS" in edge_types:
                return []
            # Everything else - all covered
            if "-[r]->()" in query or "()-[r]->" in query:
                return [{"activity_id": ACTIVITY_A}, {"activity_id": ACTIVITY_B}]
            return []

        mock_graph.run_query = AsyncMock(side_effect=mock_run_query)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/knowledge-gaps")

    assert resp.status_code == 200
    data = resp.json()

    # 2 activities x 2 missing forms = 4 gaps
    assert data["total_gaps"] == 4

    form5_gaps = [g for g in data["gaps"] if g["form_number"] == 5]
    assert len(form5_gaps) == 2
    assert form5_gaps[0]["gap_type"] == "missing_evidence"
    assert form5_gaps[0]["suggested_probe_type"] == "governance"

    form9_gaps = [g for g in data["gaps"] if g["form_number"] == 9]
    assert len(form9_gaps) == 2
    assert form9_gaps[0]["suggested_probe_type"] == "uncertainty"


# ---------------------------------------------------------------------------
# Scenario 5: Coverage Progression (Recomputation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_5_coverage_progression() -> None:
    """Given initial coverage with Form 5 missing, after adding edges,
    recomputation shows increased coverage."""
    eng = _make_engagement(ENGAGEMENT_ID)
    session = _mock_session_with_engagement(eng)
    app = _make_app(session)

    with patch("src.api.routes.knowledge_forms.KnowledgeGraphService") as mock_graph_cls:
        mock_graph = mock_graph_cls.return_value

        # First call: Form 5 missing for both activities
        async def mock_run_query_v1(query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            if "RETURN a.id AS activity_id" in query and "type(r)" not in query:
                return [{"activity_id": ACTIVITY_A}, {"activity_id": ACTIVITY_B}]
            edge_types = params.get("edge_types", [])
            if "GOVERNED_BY" in edge_types:
                return []  # No rules
            if "-[r]->()" in query or "()-[r]->" in query:
                return [{"activity_id": ACTIVITY_A}, {"activity_id": ACTIVITY_B}]
            return []

        mock_graph.run_query = AsyncMock(side_effect=mock_run_query_v1)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp1 = await client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/knowledge-coverage")

    assert resp1.status_code == 200
    data1 = resp1.json()
    form5_v1 = next(f for f in data1["forms"] if f["form_number"] == 5)
    assert form5_v1["coverage_percentage"] == 0.0

    # Second call: Form 5 now covered for activity A
    with patch("src.api.routes.knowledge_forms.KnowledgeGraphService") as mock_graph_cls2:
        mock_graph2 = mock_graph_cls2.return_value

        async def mock_run_query_v2(query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            if "RETURN a.id AS activity_id" in query and "type(r)" not in query:
                return [{"activity_id": ACTIVITY_A}, {"activity_id": ACTIVITY_B}]
            edge_types = params.get("edge_types", [])
            is_outbound = "-[r]->()" in query
            if "GOVERNED_BY" in edge_types and is_outbound:
                return [{"activity_id": ACTIVITY_A}]  # A now has rules
            if "GOVERNED_BY" in edge_types:
                return []
            if "-[r]->()" in query or "()-[r]->" in query:
                return [{"activity_id": ACTIVITY_A}, {"activity_id": ACTIVITY_B}]
            return []

        mock_graph2.run_query = AsyncMock(side_effect=mock_run_query_v2)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp2 = await client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/knowledge-coverage")

    assert resp2.status_code == 200
    data2 = resp2.json()
    form5_v2 = next(f for f in data2["forms"] if f["form_number"] == 5)
    assert form5_v2["coverage_percentage"] == 50.0  # 1 of 2 activities


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_activities_returns_zero_coverage() -> None:
    """Empty engagement returns 0 activities and 0 completeness."""
    eng = _make_engagement(ENGAGEMENT_ID)
    session = _mock_session_with_engagement(eng)
    app = _make_app(session)

    with patch("src.api.routes.knowledge_forms.KnowledgeGraphService") as mock_graph_cls:
        mock_graph = mock_graph_cls.return_value
        mock_graph.run_query = AsyncMock(return_value=[])

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/knowledge-coverage")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_activities"] == 0
    assert data["overall_completeness"] == 0.0
    assert data["forms"] == []


@pytest.mark.asyncio
async def test_no_activities_returns_empty_gaps() -> None:
    """Empty engagement returns empty gaps list."""
    eng = _make_engagement(ENGAGEMENT_ID)
    session = _mock_session_with_engagement(eng)
    app = _make_app(session)

    with patch("src.api.routes.knowledge_forms.KnowledgeGraphService") as mock_graph_cls:
        mock_graph = mock_graph_cls.return_value
        mock_graph.run_query = AsyncMock(return_value=[])

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/knowledge-gaps")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_gaps"] == 0
    assert data["gaps"] == []


@pytest.mark.asyncio
async def test_engagement_not_found_returns_404() -> None:
    """Non-existent engagement returns 404."""
    session = _mock_session_with_engagement(None)
    app = _make_app(session)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.get(f"/api/v1/engagements/{uuid.uuid4()}/knowledge-coverage")
    assert resp.status_code == 404

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp2 = await client.get(f"/api/v1/engagements/{uuid.uuid4()}/knowledge-gaps")
    assert resp2.status_code == 404


# ---------------------------------------------------------------------------
# Service Unit Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_knowledge_form_enum_has_9_forms() -> None:
    """KnowledgeForm enum must have exactly 9 members."""
    from src.governance.knowledge_forms import KnowledgeForm

    assert len(KnowledgeForm) == 9


@pytest.mark.asyncio
async def test_form_edge_mappings_complete() -> None:
    """Every form must have at least one edge mapping."""
    from src.governance.knowledge_forms import FORM_EDGE_MAPPINGS, KnowledgeForm

    for form in KnowledgeForm:
        assert len(FORM_EDGE_MAPPINGS[form]) >= 1, f"Form {form.value} has no edge mappings"


@pytest.mark.asyncio
async def test_form_numbers_complete() -> None:
    """Form numbers must be 1-9."""
    from src.governance.knowledge_forms import FORM_NUMBERS, KnowledgeForm

    numbers = set(FORM_NUMBERS.values())
    assert numbers == set(range(1, 10))
    assert len(FORM_NUMBERS) == len(KnowledgeForm)


@pytest.mark.asyncio
async def test_edge_types_exist_in_ontology() -> None:
    """All edge types in FORM_EDGE_MAPPINGS must exist in kmflow_ontology.yaml."""
    import yaml

    from src.governance.knowledge_forms import FORM_EDGE_MAPPINGS

    ontology_path = "src/semantic/ontology/kmflow_ontology.yaml"
    with open(ontology_path) as f:
        ontology = yaml.safe_load(f)

    ontology_edges = set(ontology.get("relationship_types", {}).keys())

    for form, edge_types in FORM_EDGE_MAPPINGS.items():
        for edge_type in edge_types:
            assert edge_type in ontology_edges, (
                f"Edge type '{edge_type}' for form '{form.value}' "
                f"not found in ontology. Available: {sorted(ontology_edges)}"
            )
