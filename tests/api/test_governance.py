"""API schema validation and route registration tests for governance routes.

Tests that the governance router is correctly registered and its endpoints
respond with proper status codes and response shapes. Uses the shared
test_app fixture which mocks auth and database access.
"""

from __future__ import annotations

import io
import uuid
import zipfile
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.auth import get_current_user
from src.core.config import Settings, get_settings
from src.core.models import DataClassification, DataLayer, User, UserRole

# ---------------------------------------------------------------------------
# Fixtures — governance-specific test app
# ---------------------------------------------------------------------------


class MockSessionFactory:
    """Callable that returns an async context manager yielding a mock session."""

    def __init__(self, session: AsyncMock) -> None:
        self._session = session

    def __call__(self) -> MockSessionFactory:
        return self

    async def __aenter__(self) -> AsyncMock:
        return self._session

    async def __aexit__(self, *args: Any) -> None:
        pass


def _make_mock_session() -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    session.add = MagicMock()
    return session


def _make_catalog_entry_dict(
    entry_id: uuid.UUID | None = None,
    dataset_name: str = "test_dataset",
    layer: str = "bronze",
    classification: str = "internal",
) -> dict[str, Any]:
    """Return a dict that looks like a serialized DataCatalogEntry."""
    now = datetime.now(UTC)
    return {
        "id": str(entry_id or uuid.uuid4()),
        "dataset_name": dataset_name,
        "dataset_type": "evidence",
        "layer": layer,
        "engagement_id": None,
        "schema_definition": None,
        "owner": None,
        "classification": classification,
        "quality_sla": None,
        "retention_days": None,
        "description": None,
        "row_count": None,
        "size_bytes": None,
        "delta_table_path": None,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }


@pytest.fixture
async def governance_app(
    mock_db_session: AsyncMock,
    mock_neo4j_driver: MagicMock,
    mock_redis_client: AsyncMock,
) -> AsyncGenerator[Any, None]:
    """FastAPI test app with only the governance router registered."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from src.api.routes import governance

    @asynccontextmanager
    async def test_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        yield

    app = FastAPI(lifespan=test_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(governance.router)

    test_settings_instance = Settings(
        jwt_secret_key="test-secret-key",
        auth_dev_mode=True,
        monitoring_worker_count=0,
    )
    app.dependency_overrides[get_settings] = lambda: test_settings_instance

    mock_user = MagicMock(spec=User)
    mock_user.id = uuid.uuid4()
    mock_user.email = "testadmin@kmflow.dev"
    mock_user.role = UserRole.PLATFORM_ADMIN
    mock_user.is_active = True
    app.dependency_overrides[get_current_user] = lambda: mock_user

    app.state.db_session_factory = MockSessionFactory(mock_db_session)
    app.state.db_engine = MagicMock()
    app.state.neo4j_driver = mock_neo4j_driver
    app.state.redis_client = mock_redis_client

    yield app


@pytest.fixture
async def governance_client(governance_app: Any) -> AsyncGenerator[AsyncClient, None]:
    """HTTP test client for the governance router."""
    transport = ASGITransport(app=governance_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Route registration smoke test
# ---------------------------------------------------------------------------


class TestRouteRegistration:
    """Verify that all governance routes are registered."""

    @pytest.mark.asyncio
    async def test_governance_router_is_importable(self) -> None:
        from src.api.routes.governance import router

        assert router is not None

    @pytest.mark.asyncio
    async def test_governance_router_has_expected_routes(self) -> None:
        from src.api.routes.governance import router

        paths = [route.path for route in router.routes]
        assert "/api/v1/governance/catalog" in paths
        assert "/api/v1/governance/policies" in paths
        assert "/api/v1/governance/policies/evaluate" in paths

    @pytest.mark.asyncio
    async def test_main_app_includes_governance_router(self) -> None:
        from src.api.main import create_app

        app = create_app()
        paths = [route.path for route in app.routes]
        assert any("governance" in p for p in paths)


# ---------------------------------------------------------------------------
# GET /api/v1/governance/catalog
# ---------------------------------------------------------------------------


class TestListCatalogEntries:
    """Tests for GET /api/v1/governance/catalog."""

    @pytest.mark.asyncio
    async def test_returns_200_with_empty_list(
        self,
        governance_client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        mock_db_session.execute = AsyncMock(return_value=result)

        response = await governance_client.get("/api/v1/governance/catalog")

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_returns_200_with_entries(
        self,
        governance_client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        entry = MagicMock()
        entry.id = uuid.uuid4()
        entry.dataset_name = "my_dataset"
        entry.dataset_type = "evidence"
        entry.layer = DataLayer.BRONZE
        entry.classification = DataClassification.INTERNAL
        entry.engagement_id = None
        entry.schema_definition = None
        entry.owner = None
        entry.quality_sla = None
        entry.retention_days = None
        entry.description = None
        entry.row_count = None
        entry.size_bytes = None
        entry.delta_table_path = None
        entry.created_at = datetime.now(UTC)
        entry.updated_at = datetime.now(UTC)

        result = MagicMock()
        result.scalars.return_value.all.return_value = [entry]
        mock_db_session.execute = AsyncMock(return_value=result)

        response = await governance_client.get("/api/v1/governance/catalog")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["dataset_name"] == "my_dataset"


# ---------------------------------------------------------------------------
# POST /api/v1/governance/catalog
# ---------------------------------------------------------------------------


class TestCreateCatalogEntry:
    """Tests for POST /api/v1/governance/catalog."""

    @pytest.mark.asyncio
    async def test_returns_201_on_success(
        self,
        governance_client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        # Patch the catalog service so it returns a fully-populated mock entry
        entry = MagicMock()
        entry.id = uuid.uuid4()
        entry.dataset_name = "new_dataset"
        entry.dataset_type = "evidence"
        entry.layer = DataLayer.BRONZE
        entry.classification = DataClassification.INTERNAL
        entry.engagement_id = None
        entry.schema_definition = None
        entry.owner = None
        entry.quality_sla = None
        entry.retention_days = None
        entry.description = None
        entry.row_count = None
        entry.size_bytes = None
        entry.delta_table_path = None
        entry.created_at = datetime.now(UTC)
        entry.updated_at = datetime.now(UTC)

        with patch(
            "src.api.routes.governance.DataCatalogService.create_entry",
            new=AsyncMock(return_value=entry),
        ):
            body = {
                "dataset_name": "new_dataset",
                "dataset_type": "evidence",
                "layer": "bronze",
            }
            response = await governance_client.post(
                "/api/v1/governance/catalog",
                json=body,
            )

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_created_entry_fields_in_response(
        self,
        governance_client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        entry = MagicMock()
        entry.id = uuid.uuid4()
        entry.dataset_name = "silver_data"
        entry.dataset_type = "processed"
        entry.layer = DataLayer.SILVER
        entry.classification = DataClassification.CONFIDENTIAL
        entry.engagement_id = None
        entry.schema_definition = None
        entry.owner = None
        entry.quality_sla = None
        entry.retention_days = 730
        entry.description = None
        entry.row_count = None
        entry.size_bytes = None
        entry.delta_table_path = None
        entry.created_at = datetime.now(UTC)
        entry.updated_at = datetime.now(UTC)

        with patch(
            "src.api.routes.governance.DataCatalogService.create_entry",
            new=AsyncMock(return_value=entry),
        ):
            body = {
                "dataset_name": "silver_data",
                "dataset_type": "processed",
                "layer": "silver",
                "classification": "confidential",
                "retention_days": 730,
            }
            response = await governance_client.post(
                "/api/v1/governance/catalog",
                json=body,
            )

        assert response.status_code == 201
        data = response.json()
        assert data["dataset_name"] == "silver_data"
        assert data["layer"] == "silver"

    @pytest.mark.asyncio
    async def test_returns_422_on_missing_required_fields(
        self,
        governance_client: AsyncClient,
    ) -> None:
        response = await governance_client.post(
            "/api/v1/governance/catalog",
            json={"dataset_name": "incomplete"},
        )

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/governance/catalog/{entry_id}
# ---------------------------------------------------------------------------


class TestGetCatalogEntry:
    """Tests for GET /api/v1/governance/catalog/{entry_id}."""

    @pytest.mark.asyncio
    async def test_returns_404_when_not_found(
        self,
        governance_client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=result)

        entry_id = uuid.uuid4()
        response = await governance_client.get(
            f"/api/v1/governance/catalog/{entry_id}"
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_200_when_found(
        self,
        governance_client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        entry_id = uuid.uuid4()
        entry = MagicMock()
        entry.id = entry_id
        entry.dataset_name = "found_dataset"
        entry.dataset_type = "evidence"
        entry.layer = DataLayer.BRONZE
        entry.classification = DataClassification.INTERNAL
        entry.engagement_id = None
        entry.schema_definition = None
        entry.owner = None
        entry.quality_sla = None
        entry.retention_days = None
        entry.description = None
        entry.row_count = None
        entry.size_bytes = None
        entry.delta_table_path = None
        entry.created_at = datetime.now(UTC)
        entry.updated_at = datetime.now(UTC)

        result = MagicMock()
        result.scalar_one_or_none.return_value = entry
        mock_db_session.execute = AsyncMock(return_value=result)

        response = await governance_client.get(
            f"/api/v1/governance/catalog/{entry_id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["dataset_name"] == "found_dataset"


# ---------------------------------------------------------------------------
# DELETE /api/v1/governance/catalog/{entry_id}
# ---------------------------------------------------------------------------


class TestDeleteCatalogEntry:
    """Tests for DELETE /api/v1/governance/catalog/{entry_id}."""

    @pytest.mark.asyncio
    async def test_returns_404_when_not_found(
        self,
        governance_client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=result)

        entry_id = uuid.uuid4()
        response = await governance_client.delete(
            f"/api/v1/governance/catalog/{entry_id}"
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_204_on_success(
        self,
        governance_client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        entry = MagicMock()
        entry.id = uuid.uuid4()

        result = MagicMock()
        result.scalar_one_or_none.return_value = entry
        mock_db_session.execute = AsyncMock(return_value=result)

        response = await governance_client.delete(
            f"/api/v1/governance/catalog/{entry.id}"
        )

        assert response.status_code == 204


# ---------------------------------------------------------------------------
# GET /api/v1/governance/policies
# ---------------------------------------------------------------------------


class TestListPolicies:
    """Tests for GET /api/v1/governance/policies."""

    @pytest.mark.asyncio
    async def test_returns_200_with_policy_dict(
        self, governance_client: AsyncClient
    ) -> None:
        response = await governance_client.get("/api/v1/governance/policies")

        assert response.status_code == 200
        data = response.json()
        assert "policies" in data
        assert "policy_file" in data

    @pytest.mark.asyncio
    async def test_policies_contain_retention(
        self, governance_client: AsyncClient
    ) -> None:
        response = await governance_client.get("/api/v1/governance/policies")

        data = response.json()
        assert "retention" in data["policies"]

    @pytest.mark.asyncio
    async def test_policies_contain_naming_convention(
        self, governance_client: AsyncClient
    ) -> None:
        response = await governance_client.get("/api/v1/governance/policies")

        data = response.json()
        assert "naming_convention" in data["policies"]


# ---------------------------------------------------------------------------
# POST /api/v1/governance/policies/evaluate
# ---------------------------------------------------------------------------


class TestEvaluatePolicies:
    """Tests for POST /api/v1/governance/policies/evaluate."""

    @pytest.mark.asyncio
    async def test_returns_404_for_missing_entry(
        self,
        governance_client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=result)

        response = await governance_client.post(
            "/api/v1/governance/policies/evaluate",
            json={"entry_id": str(uuid.uuid4())},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_compliant_for_clean_entry(
        self,
        governance_client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        entry = MagicMock()
        entry.id = uuid.uuid4()
        entry.dataset_name = "valid_dataset"
        entry.layer = DataLayer.BRONZE
        entry.classification = DataClassification.INTERNAL
        entry.retention_days = 100  # within bronze limit of 365
        entry.quality_sla = None

        result = MagicMock()
        result.scalar_one_or_none.return_value = entry
        mock_db_session.execute = AsyncMock(return_value=result)

        response = await governance_client.post(
            "/api/v1/governance/policies/evaluate",
            json={"entry_id": str(entry.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert "compliant" in data
        assert "violations" in data
        assert "violation_count" in data

    @pytest.mark.asyncio
    async def test_returns_violations_for_invalid_name(
        self,
        governance_client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        entry = MagicMock()
        entry.id = uuid.uuid4()
        entry.dataset_name = "INVALID NAME"  # violates naming convention
        entry.layer = DataLayer.BRONZE
        entry.classification = DataClassification.INTERNAL
        entry.retention_days = None
        entry.quality_sla = None

        result = MagicMock()
        result.scalar_one_or_none.return_value = entry
        mock_db_session.execute = AsyncMock(return_value=result)

        response = await governance_client.post(
            "/api/v1/governance/policies/evaluate",
            json={"entry_id": str(entry.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["compliant"] is False
        assert data["violation_count"] > 0


# ---------------------------------------------------------------------------
# GET /api/v1/governance/quality/{entry_id}
# ---------------------------------------------------------------------------


class TestCheckQualitySLA:
    """Tests for GET /api/v1/governance/quality/{entry_id}."""

    @pytest.mark.asyncio
    async def test_returns_404_for_missing_entry(
        self,
        governance_client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=result)

        response = await governance_client.get(
            f"/api/v1/governance/quality/{uuid.uuid4()}"
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_200_with_sla_result(
        self,
        governance_client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        entry = MagicMock()
        entry.id = uuid.uuid4()
        entry.dataset_name = "gold_dataset"
        entry.layer = DataLayer.GOLD
        entry.classification = DataClassification.CONFIDENTIAL
        entry.quality_sla = {"min_score": 0.8}
        entry.engagement_id = uuid.uuid4()

        # First call: get_entry (scalar_one_or_none)
        # Second call: SLA evidence items (scalars().all())
        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = entry

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []

        mock_db_session.execute = AsyncMock(
            side_effect=[entry_result, items_result]
        )

        response = await governance_client.get(
            f"/api/v1/governance/quality/{entry.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert "passing" in data
        assert "evidence_count" in data
        assert "checked_at" in data
        assert "violations" in data


# ---------------------------------------------------------------------------
# GET /api/v1/governance/export/{engagement_id}
# ---------------------------------------------------------------------------


class TestExportGovernance:
    """Tests for GET /api/v1/governance/export/{engagement_id}."""

    @pytest.mark.asyncio
    async def test_returns_zip_bytes(
        self,
        governance_client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        # catalog entries
        catalog_result = MagicMock()
        catalog_result.scalars.return_value.all.return_value = []

        # lineage
        lineage_result = MagicMock()
        lineage_result.scalars.return_value.all.return_value = []

        mock_db_session.execute = AsyncMock(
            side_effect=[catalog_result, lineage_result]
        )

        engagement_id = uuid.uuid4()
        response = await governance_client.get(
            f"/api/v1/governance/export/{engagement_id}"
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert zipfile.is_zipfile(io.BytesIO(response.content))

    @pytest.mark.asyncio
    async def test_content_disposition_header(
        self,
        governance_client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        catalog_result = MagicMock()
        catalog_result.scalars.return_value.all.return_value = []
        lineage_result = MagicMock()
        lineage_result.scalars.return_value.all.return_value = []
        mock_db_session.execute = AsyncMock(
            side_effect=[catalog_result, lineage_result]
        )

        engagement_id = uuid.uuid4()
        response = await governance_client.get(
            f"/api/v1/governance/export/{engagement_id}"
        )

        assert "attachment" in response.headers.get("content-disposition", "")
        assert ".zip" in response.headers.get("content-disposition", "")


# ---------------------------------------------------------------------------
# POST /api/v1/governance/migrate/{engagement_id}
# ---------------------------------------------------------------------------


class TestTriggerMigration:
    """Tests for POST /api/v1/governance/migrate/{engagement_id}."""

    @pytest.mark.asyncio
    async def test_returns_200_with_migration_result(
        self,
        governance_client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        from src.governance.migration import MigrationResult

        mock_result = MigrationResult(
            engagement_id=str(uuid.uuid4()),
            items_processed=3,
            items_skipped=1,
            items_failed=0,
            bronze_written=3,
            silver_written=3,
            catalog_entries_created=3,
            lineage_records_created=3,
        )

        with patch(
            "src.api.routes.governance.migrate_engagement",
            new=AsyncMock(return_value=mock_result),
        ):
            engagement_id = uuid.uuid4()
            response = await governance_client.post(
                f"/api/v1/governance/migrate/{engagement_id}"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["items_processed"] == 3
        assert data["items_skipped"] == 1
        assert data["items_failed"] == 0
        assert data["bronze_written"] == 3

    @pytest.mark.asyncio
    async def test_dry_run_param_is_passed(
        self,
        governance_client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        from src.governance.migration import MigrationResult

        mock_result = MigrationResult(
            engagement_id=str(uuid.uuid4()),
            dry_run=True,
        )

        with patch(
            "src.api.routes.governance.migrate_engagement",
            new=AsyncMock(return_value=mock_result),
        ) as mock_migrate:
            engagement_id = uuid.uuid4()
            response = await governance_client.post(
                f"/api/v1/governance/migrate/{engagement_id}?dry_run=true"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["dry_run"] is True
        # Verify dry_run=True was forwarded to migrate_engagement
        _, kwargs = mock_migrate.call_args
        assert kwargs.get("dry_run") is True

    @pytest.mark.asyncio
    async def test_migration_result_has_required_fields(
        self,
        governance_client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        from src.governance.migration import MigrationResult

        mock_result = MigrationResult(engagement_id=str(uuid.uuid4()))

        with patch(
            "src.api.routes.governance.migrate_engagement",
            new=AsyncMock(return_value=mock_result),
        ):
            engagement_id = uuid.uuid4()
            response = await governance_client.post(
                f"/api/v1/governance/migrate/{engagement_id}"
            )

        data = response.json()
        required_fields = [
            "engagement_id",
            "items_processed",
            "items_skipped",
            "items_failed",
            "bronze_written",
            "silver_written",
            "catalog_entries_created",
            "lineage_records_created",
            "errors",
            "dry_run",
        ]
        for field_name in required_fields:
            assert field_name in data, f"Missing field: {field_name}"


# ---------------------------------------------------------------------------
# POST /api/v1/governance/alerts/{engagement_id}
# ---------------------------------------------------------------------------


class TestCheckSLAAndCreateAlerts:
    """Tests for POST /api/v1/governance/alerts/{engagement_id}."""

    @pytest.mark.asyncio
    async def test_returns_200_with_alert_list(
        self,
        governance_client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        mock_alerts = [
            {
                "id": str(uuid.uuid4()),
                "engagement_id": str(uuid.uuid4()),
                "monitoring_job_id": str(uuid.uuid4()),
                "severity": "medium",
                "status": "new",
                "title": "SLA breach: dataset_abc — min_score",
                "description": "Score too low",
                "dedup_key": "abc123",
                "catalog_entry_id": str(uuid.uuid4()),
                "catalog_entry_name": "dataset_abc",
                "violation_metric": "min_score",
                "violation_threshold": 0.8,
                "violation_actual": 0.4,
                "created_at": "2026-02-18T10:00:00+00:00",
            }
        ]

        with patch(
            "src.api.routes.governance.check_and_alert_sla_breaches",
            new=AsyncMock(return_value=mock_alerts),
        ):
            engagement_id = uuid.uuid4()
            response = await governance_client.post(
                f"/api/v1/governance/alerts/{engagement_id}"
            )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["violation_metric"] == "min_score"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_breaches(
        self,
        governance_client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        with patch(
            "src.api.routes.governance.check_and_alert_sla_breaches",
            new=AsyncMock(return_value=[]),
        ):
            engagement_id = uuid.uuid4()
            response = await governance_client.post(
                f"/api/v1/governance/alerts/{engagement_id}"
            )

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_commits_after_creating_alerts(
        self,
        governance_client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        with patch(
            "src.api.routes.governance.check_and_alert_sla_breaches",
            new=AsyncMock(return_value=[]),
        ):
            engagement_id = uuid.uuid4()
            await governance_client.post(
                f"/api/v1/governance/alerts/{engagement_id}"
            )

        mock_db_session.commit.assert_called()


# ---------------------------------------------------------------------------
# GET /api/v1/governance/health/{engagement_id}
# ---------------------------------------------------------------------------


class TestGetGovernanceHealth:
    """Tests for GET /api/v1/governance/health/{engagement_id}."""

    @pytest.mark.asyncio
    async def test_returns_200_with_health_summary(
        self,
        governance_client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        entry = MagicMock()
        entry.id = uuid.uuid4()
        entry.dataset_name = "bronze_evidence"
        entry.layer = DataLayer.BRONZE
        entry.classification = DataClassification.INTERNAL
        entry.quality_sla = None
        entry.engagement_id = uuid.uuid4()

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [entry]
        evidence_result = MagicMock()
        evidence_result.scalars.return_value.all.return_value = []

        mock_db_session.execute = AsyncMock(
            side_effect=[list_result, evidence_result]
        )

        engagement_id = uuid.uuid4()
        response = await governance_client.get(
            f"/api/v1/governance/health/{engagement_id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert "total_entries" in data
        assert "passing_count" in data
        assert "failing_count" in data
        assert "compliance_percentage" in data
        assert "entries" in data

    @pytest.mark.asyncio
    async def test_empty_engagement_returns_100_pct_compliance(
        self,
        governance_client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []
        mock_db_session.execute = AsyncMock(return_value=list_result)

        engagement_id = uuid.uuid4()
        response = await governance_client.get(
            f"/api/v1/governance/health/{engagement_id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_entries"] == 0
        assert data["compliance_percentage"] == 100.0

    @pytest.mark.asyncio
    async def test_entries_list_contains_per_entry_detail(
        self,
        governance_client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        entry = MagicMock()
        entry.id = uuid.uuid4()
        entry.dataset_name = "gold_events"
        entry.layer = DataLayer.GOLD
        entry.classification = DataClassification.CONFIDENTIAL
        entry.quality_sla = {"min_score": 0.9}
        entry.engagement_id = uuid.uuid4()

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [entry]
        evidence_result = MagicMock()
        evidence_result.scalars.return_value.all.return_value = []

        mock_db_session.execute = AsyncMock(
            side_effect=[list_result, evidence_result]
        )

        engagement_id = uuid.uuid4()
        response = await governance_client.get(
            f"/api/v1/governance/health/{engagement_id}"
        )

        data = response.json()
        assert len(data["entries"]) == 1
        entry_detail = data["entries"][0]
        assert "entry_id" in entry_detail
        assert "name" in entry_detail
        assert "classification" in entry_detail
        assert "sla_passing" in entry_detail
        assert "violation_count" in entry_detail
