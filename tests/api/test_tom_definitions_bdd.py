"""BDD tests for Story #344 — TOM Definition and Management APIs.

Scenario 1: TOM Creation with 6 Dimensions
Scenario 2: TOM Version History on Update
Scenario 3: Full TOM Retrieval with All Dimensions
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
    EngagementStatus,
    TargetOperatingModel,
    TOMDimension,
    TOMDimensionRecord,
    TOMVersion,
    User,
    UserRole,
)

APP = create_app()

ENGAGEMENT_ID = uuid.uuid4()
TOM_ID = uuid.uuid4()
USER_ID = uuid.uuid4()

ALL_SIX_DIMENSIONS = [
    {"dimension_type": "process_architecture", "maturity_target": 3, "description": "Process design and documentation"},
    {"dimension_type": "people_and_organization", "maturity_target": 4, "description": "Org structure and roles"},
    {"dimension_type": "technology_and_data", "maturity_target": 2, "description": "IT systems and data management"},
    {"dimension_type": "governance_structures", "maturity_target": 5, "description": "Decision-making frameworks"},
    {"dimension_type": "performance_management", "maturity_target": 3, "description": "KPIs and metrics"},
    {"dimension_type": "risk_and_compliance", "maturity_target": 4, "description": "Regulatory controls"},
]


def _mock_user() -> User:
    u = MagicMock(spec=User)
    u.id = USER_ID
    u.role = UserRole.PLATFORM_ADMIN
    return u


def _make_plain_mock(**kwargs: Any) -> MagicMock:
    """Create a MagicMock that stores kwargs as regular attributes.

    MagicMock treats 'name' specially (as the mock's own name).
    This helper works around that by setting attributes after construction.
    Also provides sensible defaults for fields expected by TOM response serialization.
    """
    m = MagicMock()
    # Set a real UUID id if not provided (mimics SA default=uuid.uuid4)
    if "id" not in kwargs:
        m.id = uuid.uuid4()
    for k, v in kwargs.items():
        setattr(m, k, v)
    # Ensure dimension_records is an empty list if not set (needed by _tom_to_response)
    if not hasattr(m, "dimension_records") or isinstance(m.dimension_records, MagicMock):
        m.dimension_records = []
    # Set timestamps if not provided
    if not hasattr(m, "created_at") or isinstance(m.created_at, MagicMock):
        m.created_at = datetime(2026, 2, 27, tzinfo=UTC)
    if not hasattr(m, "updated_at") or isinstance(m.updated_at, MagicMock):
        m.updated_at = datetime(2026, 2, 27, tzinfo=UTC)
    return m


def _mock_engagement_result() -> MagicMock:
    """Return a mock execute result that yields an engagement."""
    eng = MagicMock()
    eng.id = ENGAGEMENT_ID
    eng.name = "Test Engagement"
    eng.status = EngagementStatus.ACTIVE
    result = MagicMock()
    result.scalar_one_or_none.return_value = eng
    return result


def _mock_tom(*, with_dimensions: bool = True, version: int = 1) -> TargetOperatingModel:
    tom = MagicMock(spec=TargetOperatingModel)
    tom.id = TOM_ID
    tom.engagement_id = ENGAGEMENT_ID
    tom.name = "Financial Services TOM v1"
    tom.version = version
    tom.maturity_targets = None
    tom.created_at = datetime(2026, 2, 27, tzinfo=UTC)
    tom.updated_at = datetime(2026, 2, 27, tzinfo=UTC)

    if with_dimensions:
        dim_records = []
        for dim_data in ALL_SIX_DIMENSIONS:
            dr = MagicMock(spec=TOMDimensionRecord)
            dr.dimension_type = TOMDimension(dim_data["dimension_type"])
            dr.maturity_target = dim_data["maturity_target"]
            dr.description = dim_data["description"]
            dim_records.append(dr)
        tom.dimension_records = dim_records
    else:
        tom.dimension_records = []

    return tom


def _override_deps(session: AsyncMock) -> None:
    from src.api.deps import get_session
    from src.core.auth import get_current_user

    APP.dependency_overrides[get_session] = lambda: session
    APP.dependency_overrides[get_current_user] = lambda: _mock_user()


@pytest.fixture(autouse=True)
def _cleanup() -> None:
    yield
    APP.dependency_overrides.clear()


# ===========================================================================
# Scenario 1: TOM Creation with 6 Dimensions
# ===========================================================================


class TestScenario1TOMCreationWithDimensions:
    """Given a consultant submits POST /api/v1/tom/models with 6 dimensions,
    all dimension records are created linked to the TOM."""

    @pytest.mark.asyncio
    async def test_create_tom_returns_201(self) -> None:
        session = AsyncMock()
        session.execute.return_value = _mock_engagement_result()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        added: list = []
        session.add = MagicMock(side_effect=lambda obj: added.append(obj))

        async def fake_refresh(obj: object, attribute_names: list | None = None) -> None:
            if hasattr(obj, "__dict__"):
                obj.__dict__["dimension_records"] = [
                    MagicMock(
                        dimension_type=TOMDimension(d["dimension_type"]),
                        maturity_target=d["maturity_target"],
                        description=d["description"],
                    )
                    for d in ALL_SIX_DIMENSIONS
                ]

        session.refresh = fake_refresh
        _override_deps(session)

        with (
            mock.patch("src.api.routes.tom.TargetOperatingModel", side_effect=lambda **kw: _make_plain_mock(**kw)),
            mock.patch("src.api.routes.tom.TOMDimensionRecord", side_effect=lambda **kw: _make_plain_mock(**kw)),
            mock.patch("src.api.routes.tom.log_audit", new_callable=AsyncMock),
        ):
            async with AsyncClient(transport=ASGITransport(app=APP), base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/v1/tom/models",
                    json={
                        "engagement_id": str(ENGAGEMENT_ID),
                        "name": "Financial Services TOM v1",
                        "dimensions": ALL_SIX_DIMENSIONS,
                    },
                )

        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_tom_creates_6_dimension_records(self) -> None:
        session = AsyncMock()
        session.execute.return_value = _mock_engagement_result()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        added: list = []
        session.add = MagicMock(side_effect=lambda obj: added.append(obj))

        async def fake_refresh(obj: object, attribute_names: list | None = None) -> None:
            if hasattr(obj, "__dict__"):
                obj.__dict__["dimension_records"] = []

        session.refresh = fake_refresh
        _override_deps(session)

        with (
            mock.patch("src.api.routes.tom.TargetOperatingModel", side_effect=lambda **kw: _make_plain_mock(**kw)),
            mock.patch("src.api.routes.tom.TOMDimensionRecord", side_effect=lambda **kw: _make_plain_mock(**kw)),
            mock.patch("src.api.routes.tom.log_audit", new_callable=AsyncMock),
        ):
            async with AsyncClient(transport=ASGITransport(app=APP), base_url="http://test") as ac:
                await ac.post(
                    "/api/v1/tom/models",
                    json={
                        "engagement_id": str(ENGAGEMENT_ID),
                        "name": "Financial Services TOM v1",
                        "dimensions": ALL_SIX_DIMENSIONS,
                    },
                )

        # 1 TOM + 6 dimension records = 7 add calls (log_audit is patched out)
        assert session.add.call_count == 7

    @pytest.mark.asyncio
    async def test_maturity_target_must_be_1_to_5(self) -> None:
        session = AsyncMock()
        _override_deps(session)

        async with AsyncClient(transport=ASGITransport(app=APP), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/tom/models",
                json={
                    "engagement_id": str(ENGAGEMENT_ID),
                    "name": "Bad TOM",
                    "dimensions": [
                        {"dimension_type": "process_architecture", "maturity_target": 0, "description": "Invalid"},
                    ],
                },
            )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_maturity_target_above_5_rejected(self) -> None:
        session = AsyncMock()
        _override_deps(session)

        async with AsyncClient(transport=ASGITransport(app=APP), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/tom/models",
                json={
                    "engagement_id": str(ENGAGEMENT_ID),
                    "name": "Bad TOM",
                    "dimensions": [
                        {"dimension_type": "process_architecture", "maturity_target": 6, "description": "Too high"},
                    ],
                },
            )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_engagement_not_found_returns_404(self) -> None:
        session = AsyncMock()
        not_found = MagicMock()
        not_found.scalar_one_or_none.return_value = None
        session.execute.return_value = not_found
        _override_deps(session)

        async with AsyncClient(transport=ASGITransport(app=APP), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/tom/models",
                json={
                    "engagement_id": str(uuid.uuid4()),
                    "name": "No Engagement",
                    "dimensions": ALL_SIX_DIMENSIONS,
                },
            )

        assert resp.status_code == 404


# ===========================================================================
# Scenario 2: TOM Version History on Update
# ===========================================================================


class TestScenario2VersionHistory:
    """Given TOM at version=1, PATCH creates a version snapshot and bumps version."""

    @pytest.mark.asyncio
    async def test_patch_increments_version(self) -> None:
        session = AsyncMock()
        tom = _mock_tom(version=1)
        tom.version = 1  # real attribute for mutation

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tom
        session.execute.return_value = mock_result
        session.add = MagicMock()
        session.commit = AsyncMock()

        async def fake_refresh(obj: object, attribute_names: list | None = None) -> None:
            pass

        session.refresh = fake_refresh
        _override_deps(session)

        with mock.patch("src.api.routes.tom.TOMVersion", side_effect=lambda **kw: _make_plain_mock(**kw)):
            async with AsyncClient(transport=ASGITransport(app=APP), base_url="http://test") as ac:
                resp = await ac.patch(
                    f"/api/v1/tom/models/{TOM_ID}",
                    json={"name": "Updated TOM Name"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == 2

    @pytest.mark.asyncio
    async def test_patch_creates_version_snapshot(self) -> None:
        session = AsyncMock()
        tom = _mock_tom(version=1)
        tom.version = 1

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tom
        session.execute.return_value = mock_result

        added_objects: list = []
        session.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))
        session.commit = AsyncMock()

        async def fake_refresh(obj: object, attribute_names: list | None = None) -> None:
            pass

        session.refresh = fake_refresh
        _override_deps(session)

        async with AsyncClient(transport=ASGITransport(app=APP), base_url="http://test") as ac:
            await ac.patch(
                f"/api/v1/tom/models/{TOM_ID}",
                json={"name": "Updated TOM Name"},
            )

        # Should have added a TOMVersion object
        version_adds = [obj for obj in added_objects if isinstance(obj, TOMVersion)]
        assert len(version_adds) == 1
        assert version_adds[0].version_number == 1

    @pytest.mark.asyncio
    async def test_patch_with_dimension_update(self) -> None:
        session = AsyncMock()
        tom = _mock_tom(version=1)
        tom.version = 1

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tom
        session.execute.return_value = mock_result
        session.add = MagicMock()
        session.commit = AsyncMock()

        async def fake_refresh(obj: object, attribute_names: list | None = None) -> None:
            pass

        session.refresh = fake_refresh
        _override_deps(session)

        with mock.patch("src.api.routes.tom.TOMVersion", side_effect=lambda **kw: _make_plain_mock(**kw)):
            async with AsyncClient(transport=ASGITransport(app=APP), base_url="http://test") as ac:
                resp = await ac.patch(
                    f"/api/v1/tom/models/{TOM_ID}",
                    json={
                        "dimensions": [
                            {"dimension_type": "process_architecture", "maturity_target": 5, "description": "Updated"},
                        ],
                    },
                )

        assert resp.status_code == 200
        # The existing dimension_record for process_architecture should be updated
        pa_dim = [dr for dr in tom.dimension_records if dr.dimension_type == TOMDimension.PROCESS_ARCHITECTURE]
        assert pa_dim[0].maturity_target == 5

    @pytest.mark.asyncio
    async def test_get_versions_endpoint(self) -> None:
        session = AsyncMock()
        tom = _mock_tom(version=2)

        mock_tom_result = MagicMock()
        mock_tom_result.scalar_one_or_none.return_value = tom

        v1 = MagicMock(spec=TOMVersion)
        v1.version_number = 1
        v1.snapshot = {"name": "Financial Services TOM v1", "dimensions": []}
        v1.changed_by = str(USER_ID)
        v1.created_at = datetime(2026, 2, 27, 10, 0, 0, tzinfo=UTC)

        mock_versions_result = MagicMock()
        mock_versions_result.scalars.return_value.all.return_value = [v1]

        # Admin bypass: no member check query
        # 1st call: TOM lookup, 2nd call: versions query
        session.execute.side_effect = [mock_tom_result, mock_versions_result]
        _override_deps(session)

        async with AsyncClient(transport=ASGITransport(app=APP), base_url="http://test") as ac:
            resp = await ac.get(f"/api/v1/tom/models/{TOM_ID}/versions")

        assert resp.status_code == 200
        data = resp.json()
        assert data["current_version"] == 2
        assert len(data["versions"]) == 1
        assert data["versions"][0]["version_number"] == 1

    @pytest.mark.asyncio
    async def test_versions_not_found_returns_404(self) -> None:
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result
        _override_deps(session)

        async with AsyncClient(transport=ASGITransport(app=APP), base_url="http://test") as ac:
            resp = await ac.get(f"/api/v1/tom/models/{uuid.uuid4()}/versions")

        assert resp.status_code == 404


# ===========================================================================
# Scenario 3: Full TOM Retrieval with All Dimensions
# ===========================================================================


class TestScenario3FullRetrieval:
    """Given a TOM exists with all 6 dimensions, GET returns all data."""

    @pytest.mark.asyncio
    async def test_get_tom_includes_all_6_dimensions(self) -> None:
        session = AsyncMock()
        tom = _mock_tom(with_dimensions=True, version=1)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tom
        session.execute.return_value = mock_result
        _override_deps(session)

        async with AsyncClient(transport=ASGITransport(app=APP), base_url="http://test") as ac:
            resp = await ac.get(f"/api/v1/tom/models/{TOM_ID}")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["dimensions"]) == 6

    @pytest.mark.asyncio
    async def test_dimensions_have_correct_types(self) -> None:
        session = AsyncMock()
        tom = _mock_tom(with_dimensions=True)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tom
        session.execute.return_value = mock_result
        _override_deps(session)

        async with AsyncClient(transport=ASGITransport(app=APP), base_url="http://test") as ac:
            resp = await ac.get(f"/api/v1/tom/models/{TOM_ID}")

        data = resp.json()
        dim_types = {d["dimension_type"] for d in data["dimensions"]}
        expected_types = {
            "process_architecture",
            "people_and_organization",
            "technology_and_data",
            "governance_structures",
            "performance_management",
            "risk_and_compliance",
        }
        assert dim_types == expected_types

    @pytest.mark.asyncio
    async def test_response_includes_version_field(self) -> None:
        session = AsyncMock()
        tom = _mock_tom(version=3)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tom
        session.execute.return_value = mock_result
        _override_deps(session)

        async with AsyncClient(transport=ASGITransport(app=APP), base_url="http://test") as ac:
            resp = await ac.get(f"/api/v1/tom/models/{TOM_ID}")

        data = resp.json()
        assert data["version"] == 3

    @pytest.mark.asyncio
    async def test_each_dimension_has_required_fields(self) -> None:
        session = AsyncMock()
        tom = _mock_tom(with_dimensions=True)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tom
        session.execute.return_value = mock_result
        _override_deps(session)

        async with AsyncClient(transport=ASGITransport(app=APP), base_url="http://test") as ac:
            resp = await ac.get(f"/api/v1/tom/models/{TOM_ID}")

        data = resp.json()
        for dim in data["dimensions"]:
            assert "dimension_type" in dim
            assert "maturity_target" in dim
            assert "description" in dim
            assert isinstance(dim["maturity_target"], int)
            assert 1 <= dim["maturity_target"] <= 5


# ===========================================================================
# Import/Export Tests
# ===========================================================================


class TestImportExport:
    """Test import and export endpoints."""

    @pytest.mark.asyncio
    async def test_export_tom(self) -> None:
        session = AsyncMock()
        tom = _mock_tom(with_dimensions=True)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tom
        session.execute.return_value = mock_result
        _override_deps(session)

        async with AsyncClient(transport=ASGITransport(app=APP), base_url="http://test") as ac:
            resp = await ac.get(f"/api/v1/tom/models/{TOM_ID}/export")

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Financial Services TOM v1"
        assert len(data["dimensions"]) == 6
        assert "version" in data

    @pytest.mark.asyncio
    async def test_import_tom_creates_record(self) -> None:
        session = AsyncMock()
        session.execute.return_value = _mock_engagement_result()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        added: list = []
        session.add = MagicMock(side_effect=lambda obj: added.append(obj))

        async def fake_refresh(obj: object, attribute_names: list | None = None) -> None:
            if hasattr(obj, "__dict__"):
                obj.__dict__["dimension_records"] = []

        session.refresh = fake_refresh
        _override_deps(session)

        with (
            mock.patch("src.api.routes.tom.TargetOperatingModel", side_effect=lambda **kw: _make_plain_mock(**kw)),
            mock.patch("src.api.routes.tom.TOMDimensionRecord", side_effect=lambda **kw: _make_plain_mock(**kw)),
            mock.patch("src.api.routes.tom.log_audit", new_callable=AsyncMock),
        ):
            async with AsyncClient(transport=ASGITransport(app=APP), base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/v1/tom/models/import",
                    json={
                        "engagement_id": str(ENGAGEMENT_ID),
                        "name": "Imported TOM",
                        "dimensions": ALL_SIX_DIMENSIONS[:3],
                    },
                )

        assert resp.status_code == 201
        # 1 TOM + 3 dimensions = 4 add calls (log_audit is patched out)
        assert session.add.call_count == 4

    @pytest.mark.asyncio
    async def test_export_not_found_returns_404(self) -> None:
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result
        _override_deps(session)

        async with AsyncClient(transport=ASGITransport(app=APP), base_url="http://test") as ac:
            resp = await ac.get(f"/api/v1/tom/models/{uuid.uuid4()}/export")

        assert resp.status_code == 404
