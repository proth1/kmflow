"""BDD tests for Story #329 — Policy, Control, and Regulation Entity CRUD APIs.

Scenario 1: Regulation Creation with Framework and Obligations
Scenario 2: Full Governance Chain Traversal
Scenario 3: Control Deletion Cascades Edges but Preserves Policy and Regulation
Scenario 4: Paginated Regulation List by Framework
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest import mock
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import create_app
from src.core.models import (
    ControlEffectiveness,
    PolicyType,
    User,
    UserRole,
)

APP = create_app()

ENGAGEMENT_ID = uuid.uuid4()
POLICY_ID = uuid.uuid4()
CONTROL_ID = uuid.uuid4()
REGULATION_ID = uuid.uuid4()
ACTIVITY_ID = uuid.uuid4()
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
    if not hasattr(m, "deleted_at") or isinstance(m.deleted_at, MagicMock):
        m.deleted_at = None
    if not hasattr(m, "created_at") or isinstance(m.created_at, MagicMock):
        m.created_at = datetime(2026, 2, 27, tzinfo=UTC)
    if not hasattr(m, "updated_at") or isinstance(m.updated_at, MagicMock):
        m.updated_at = datetime(2026, 2, 27, tzinfo=UTC)
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
# BDD Scenario 1: Regulation Creation with Framework and Obligations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_1_regulation_creation() -> None:
    """
    Given a consultant submits POST /api/v1/regulations with:
        name="Basel III", framework="BCBS", obligations=[...], engagement_id=<valid>
    When the request is processed
    Then the regulation is stored with UUID PK
      And it is retrievable via GET /api/v1/regulations/{id}
    """
    mock_session = AsyncMock()

    engagement = _make_plain_mock(id=ENGAGEMENT_ID, name="Test")
    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = engagement

    mock_session.execute = AsyncMock(return_value=eng_result)
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()

    added_objects: list[Any] = []

    def capture_add(obj: Any) -> None:
        added_objects.append(obj)

    mock_session.add = capture_add

    async def fake_refresh(obj: Any, attribute_names: list | None = None) -> None:
        if hasattr(obj, "__dict__"):
            obj.__dict__.setdefault("id", uuid.uuid4())
            obj.__dict__.setdefault("created_at", datetime(2026, 2, 27, tzinfo=UTC))
            obj.__dict__.setdefault("updated_at", datetime(2026, 2, 27, tzinfo=UTC))
            obj.__dict__.setdefault("deleted_at", None)

    mock_session.refresh = fake_refresh

    _override_deps(mock_session)

    with mock.patch("src.api.routes.regulatory.log_audit", new_callable=AsyncMock):
        transport = ASGITransport(app=APP, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/regulatory/regulations",
                json={
                    "engagement_id": str(ENGAGEMENT_ID),
                    "name": "Basel III",
                    "framework": "BCBS",
                    "obligations": {"items": ["Capital Adequacy Ratio >= 8%", "Leverage ratio reporting"]},
                },
            )

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "Basel III"
    assert data["framework"] == "BCBS"
    assert data["obligations"] is not None
    assert "id" in data

    # Verify an object was added to session
    assert len(added_objects) == 1
    assert added_objects[0].name == "Basel III"
    assert added_objects[0].framework == "BCBS"


# ---------------------------------------------------------------------------
# BDD Scenario 2: Full Governance Chain Traversal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_2_governance_chain_traversal() -> None:
    """
    Given Policy -> Regulation, Control -> Policy, Activity -> Control edges exist
    When GET /api/v1/activities/{id}/governance-chain is called
    Then the response returns Activity -> Control -> Policy -> Regulation chain
    """
    mock_session = AsyncMock()
    _override_deps(mock_session)

    # Mock the KnowledgeGraphService
    mock_graph = AsyncMock()
    mock_graph.run_query = AsyncMock(
        return_value=[
            {
                "activity_id": str(ACTIVITY_ID),
                "activity_name": "Wire Transfer Review",
                "control_id": str(CONTROL_ID),
                "control_name": "Transaction Monitoring",
                "policy_id": str(POLICY_ID),
                "policy_name": "AML Policy",
                "regulation_id": str(REGULATION_ID),
                "regulation_name": "BSA",
            }
        ]
    )

    APP.state.neo4j_driver = MagicMock()

    with mock.patch("src.semantic.graph.KnowledgeGraphService", return_value=mock_graph):
        transport = ASGITransport(app=APP, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/regulatory/activities/{ACTIVITY_ID}/governance-chain")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["activity_id"] == str(ACTIVITY_ID)
    assert len(data["chain"]) == 4

    chain = data["chain"]
    assert chain[0]["entity_type"] == "Activity"
    assert chain[0]["name"] == "Wire Transfer Review"
    assert chain[1]["entity_type"] == "Control"
    assert chain[1]["relationship_type"] == "ENFORCED_BY"
    assert chain[2]["entity_type"] == "Policy"
    assert chain[2]["relationship_type"] == "ENFORCES"
    assert chain[3]["entity_type"] == "Regulation"
    assert chain[3]["relationship_type"] == "GOVERNED_BY"


@pytest.mark.asyncio
async def test_governance_chain_empty() -> None:
    """Chain returns empty when no edges exist."""
    mock_session = AsyncMock()
    _override_deps(mock_session)

    mock_graph = AsyncMock()
    mock_graph.run_query = AsyncMock(return_value=[])

    APP.state.neo4j_driver = MagicMock()

    with mock.patch("src.semantic.graph.KnowledgeGraphService", return_value=mock_graph):
        transport = ASGITransport(app=APP, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/regulatory/activities/{ACTIVITY_ID}/governance-chain")

    assert resp.status_code == 200
    data = resp.json()
    assert data["chain"] == []


# ---------------------------------------------------------------------------
# BDD Scenario 3: Control Deletion Cascades Edges but Preserves Policy/Regulation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_3_control_soft_delete() -> None:
    """
    Given Control "Transaction Monitoring" exists with ENFORCED_BY edges
    When DELETE /api/v1/controls/{id} is called
    Then the Control is soft-deleted (deleted_at set)
      And ENFORCED_BY edges are removed from Neo4j
      And GET /api/v1/controls/{id} returns 404
    """
    mock_session = AsyncMock()

    control = _make_plain_mock(
        id=CONTROL_ID,
        engagement_id=ENGAGEMENT_ID,
        name="Transaction Monitoring",
        deleted_at=None,
    )

    # DELETE: find control (not deleted)
    ctrl_result = MagicMock()
    ctrl_result.scalar_one_or_none.return_value = control

    # GET after delete: control now has deleted_at set, so query returns None
    not_found_result = MagicMock()
    not_found_result.scalar_one_or_none.return_value = None

    mock_session.execute = AsyncMock(side_effect=[ctrl_result, not_found_result])
    mock_session.commit = AsyncMock()

    _override_deps(mock_session)

    mock_graph = AsyncMock()
    mock_graph.run_write_query = AsyncMock(return_value=[])

    APP.state.neo4j_driver = MagicMock()

    with (
        mock.patch("src.api.routes.regulatory.log_audit", new_callable=AsyncMock),
        mock.patch("src.semantic.graph.KnowledgeGraphService", return_value=mock_graph),
    ):
        transport = ASGITransport(app=APP, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Delete the control
            del_resp = await client.delete(f"/api/v1/regulatory/controls/{CONTROL_ID}")
            assert del_resp.status_code == 204

            # Verify soft-delete was set
            assert control.deleted_at is not None

            # Verify ENFORCED_BY edges were removed via write query
            mock_graph.run_write_query.assert_called_once()
            call_args = mock_graph.run_write_query.call_args
            assert "ENFORCED_BY" in call_args[0][0]
            assert "DELETE r" in call_args[0][0]

            # GET after delete should 404
            get_resp = await client.get(f"/api/v1/regulatory/controls/{CONTROL_ID}")
            assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# BDD Scenario 4: Paginated Regulation List by Framework
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_4_regulation_list_by_framework() -> None:
    """
    Given 20 regulations across 3 frameworks: BCBS, AML, GDPR
    When GET /regulations?framework=AML&limit=10&offset=0
    Then only AML regulations are returned with correct total_count
    """
    mock_session = AsyncMock()

    # Create AML regulations
    aml_regs = [
        _make_plain_mock(
            id=uuid.uuid4(),
            engagement_id=ENGAGEMENT_ID,
            name=f"AML Regulation {i}",
            framework="AML",
            jurisdiction="US",
            obligations=None,
        )
        for i in range(7)
    ]

    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = aml_regs

    count_result = MagicMock()
    count_result.scalar.return_value = 7

    mock_session.execute = AsyncMock(side_effect=[list_result, count_result])

    _override_deps(mock_session)

    transport = ASGITransport(app=APP, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/regulatory/regulations",
            params={
                "engagement_id": str(ENGAGEMENT_ID),
                "framework": "AML",
                "limit": 10,
                "offset": 0,
            },
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 7
    assert len(data["items"]) == 7
    for item in data["items"]:
        assert item["framework"] == "AML"


# ---------------------------------------------------------------------------
# Additional CRUD tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_policy_patch() -> None:
    """PATCH updates policy fields."""
    mock_session = AsyncMock()

    policy = _make_plain_mock(
        id=POLICY_ID,
        engagement_id=ENGAGEMENT_ID,
        name="Old Name",
        policy_type=PolicyType.ORGANIZATIONAL,
        source_evidence_id=None,
        clauses=None,
        description=None,
    )

    result = MagicMock()
    result.scalar_one_or_none.return_value = policy

    mock_session.execute = AsyncMock(return_value=result)
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    _override_deps(mock_session)

    transport = ASGITransport(app=APP, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.patch(
            f"/api/v1/regulatory/policies/{POLICY_ID}",
            json={"name": "Updated Name"},
        )

    assert resp.status_code == 200, resp.text
    assert policy.name == "Updated Name"


@pytest.mark.asyncio
async def test_policy_soft_delete() -> None:
    """DELETE soft-deletes a policy."""
    mock_session = AsyncMock()

    policy = _make_plain_mock(
        id=POLICY_ID,
        engagement_id=ENGAGEMENT_ID,
        name="AML Policy",
    )

    result = MagicMock()
    result.scalar_one_or_none.return_value = policy

    mock_session.execute = AsyncMock(return_value=result)
    mock_session.commit = AsyncMock()

    _override_deps(mock_session)

    with mock.patch("src.api.routes.regulatory.log_audit", new_callable=AsyncMock):
        transport = ASGITransport(app=APP, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete(f"/api/v1/regulatory/policies/{POLICY_ID}")

    assert resp.status_code == 204
    assert policy.deleted_at is not None


@pytest.mark.asyncio
async def test_regulation_soft_delete() -> None:
    """DELETE soft-deletes a regulation."""
    mock_session = AsyncMock()

    regulation = _make_plain_mock(
        id=REGULATION_ID,
        engagement_id=ENGAGEMENT_ID,
        name="GDPR",
    )

    result = MagicMock()
    result.scalar_one_or_none.return_value = regulation

    mock_session.execute = AsyncMock(return_value=result)
    mock_session.commit = AsyncMock()

    _override_deps(mock_session)

    with mock.patch("src.api.routes.regulatory.log_audit", new_callable=AsyncMock):
        transport = ASGITransport(app=APP, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete(f"/api/v1/regulatory/regulations/{REGULATION_ID}")

    assert resp.status_code == 204
    assert regulation.deleted_at is not None


@pytest.mark.asyncio
async def test_get_deleted_regulation_returns_404() -> None:
    """GET returns 404 for soft-deleted regulation."""
    mock_session = AsyncMock()

    result = MagicMock()
    result.scalar_one_or_none.return_value = None

    mock_session.execute = AsyncMock(return_value=result)

    _override_deps(mock_session)

    transport = ASGITransport(app=APP, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/v1/regulatory/regulations/{REGULATION_ID}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_control_patch() -> None:
    """PATCH updates control fields."""
    mock_session = AsyncMock()

    control = _make_plain_mock(
        id=CONTROL_ID,
        engagement_id=ENGAGEMENT_ID,
        name="Old Control",
        description=None,
        effectiveness=ControlEffectiveness.EFFECTIVE,
        effectiveness_score=0.5,
        linked_policy_ids=None,
    )

    result = MagicMock()
    result.scalar_one_or_none.return_value = control

    mock_session.execute = AsyncMock(return_value=result)
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    _override_deps(mock_session)

    transport = ASGITransport(app=APP, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.patch(
            f"/api/v1/regulatory/controls/{CONTROL_ID}",
            json={"name": "Updated Control", "effectiveness_score": 0.9},
        )

    assert resp.status_code == 200, resp.text
    assert control.name == "Updated Control"
    assert control.effectiveness_score == 0.9
