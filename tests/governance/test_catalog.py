"""Tests for DataCatalogService CRUD operations.

Uses mock SQLAlchemy sessions to avoid a real database dependency.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models import DataCatalogEntry, DataClassification, DataLayer
from src.governance.catalog import DataCatalogService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    entry_id: uuid.UUID | None = None,
    dataset_name: str = "test_dataset",
    layer: DataLayer = DataLayer.BRONZE,
    classification: DataClassification = DataClassification.INTERNAL,
    retention_days: int | None = None,
    quality_sla: dict | None = None,
    engagement_id: uuid.UUID | None = None,
) -> MagicMock:
    """Build a mock DataCatalogEntry."""
    entry = MagicMock(spec=DataCatalogEntry)
    entry.id = entry_id or uuid.uuid4()
    entry.dataset_name = dataset_name
    entry.dataset_type = "evidence"
    entry.layer = layer
    entry.classification = classification
    entry.retention_days = retention_days
    entry.quality_sla = quality_sla
    entry.engagement_id = engagement_id
    entry.owner = None
    entry.schema_definition = None
    entry.description = None
    entry.row_count = None
    entry.size_bytes = None
    entry.delta_table_path = None
    return entry


def _make_session(scalar_result=None, scalars_result: list | None = None) -> AsyncMock:
    """Build a mock AsyncSession."""
    session = AsyncMock()

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = scalar_result
    execute_result.scalars.return_value.all.return_value = scalars_result or []

    session.execute = AsyncMock(return_value=execute_result)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    session.commit = AsyncMock()

    return session


# ---------------------------------------------------------------------------
# create_entry
# ---------------------------------------------------------------------------


class TestCreateEntry:
    """Tests for DataCatalogService.create_entry."""

    @pytest.mark.asyncio
    async def test_adds_entry_to_session(self) -> None:
        session = _make_session()
        svc = DataCatalogService(session)

        await svc.create_entry(
            dataset_name="my_dataset",
            dataset_type="evidence",
            layer=DataLayer.BRONZE,
        )

        session.add.assert_called_once()
        session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_creates_with_all_fields(self) -> None:
        session = _make_session()
        svc = DataCatalogService(session)
        engagement_id = uuid.uuid4()

        await svc.create_entry(
            dataset_name="silver_evidence",
            dataset_type="processed",
            layer=DataLayer.SILVER,
            engagement_id=engagement_id,
            classification=DataClassification.CONFIDENTIAL,
            quality_sla={"min_score": 0.8},
            retention_days=365,
            description="Processed evidence for silver layer",
        )

        session.add.assert_called_once()
        added_entry = session.add.call_args[0][0]
        assert added_entry.dataset_name == "silver_evidence"
        assert added_entry.layer == DataLayer.SILVER
        assert added_entry.classification == DataClassification.CONFIDENTIAL
        assert added_entry.retention_days == 365

    @pytest.mark.asyncio
    async def test_returns_the_created_entry(self) -> None:
        session = _make_session()
        svc = DataCatalogService(session)

        result = await svc.create_entry(
            dataset_name="gold_report",
            dataset_type="report",
            layer=DataLayer.GOLD,
        )

        # The returned object is the DataCatalogEntry instance added to session
        assert result is not None
        assert isinstance(result, DataCatalogEntry)


# ---------------------------------------------------------------------------
# get_entry
# ---------------------------------------------------------------------------


class TestGetEntry:
    """Tests for DataCatalogService.get_entry."""

    @pytest.mark.asyncio
    async def test_returns_entry_when_found(self) -> None:
        entry = _make_entry()
        session = _make_session(scalar_result=entry)
        svc = DataCatalogService(session)

        result = await svc.get_entry(entry.id)

        assert result is entry

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self) -> None:
        session = _make_session(scalar_result=None)
        svc = DataCatalogService(session)

        result = await svc.get_entry(uuid.uuid4())

        assert result is None


# ---------------------------------------------------------------------------
# list_entries
# ---------------------------------------------------------------------------


class TestListEntries:
    """Tests for DataCatalogService.list_entries."""

    @pytest.mark.asyncio
    async def test_returns_all_entries(self) -> None:
        entries = [_make_entry(), _make_entry()]
        session = _make_session(scalars_result=entries)
        svc = DataCatalogService(session)

        result = await svc.list_entries()

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_returns_empty_list(self) -> None:
        session = _make_session(scalars_result=[])
        svc = DataCatalogService(session)

        result = await svc.list_entries()

        assert result == []

    @pytest.mark.asyncio
    async def test_calls_execute_once(self) -> None:
        session = _make_session(scalars_result=[])
        svc = DataCatalogService(session)

        await svc.list_entries(engagement_id=uuid.uuid4(), limit=10, offset=5)

        session.execute.assert_called_once()


# ---------------------------------------------------------------------------
# update_entry
# ---------------------------------------------------------------------------


class TestUpdateEntry:
    """Tests for DataCatalogService.update_entry."""

    @pytest.mark.asyncio
    async def test_updates_specified_fields(self) -> None:
        entry = _make_entry()
        session = _make_session(scalar_result=entry)
        svc = DataCatalogService(session)

        result = await svc.update_entry(
            entry.id,
            dataset_name="updated_name",
            retention_days=730,
        )

        assert result is entry
        assert entry.dataset_name == "updated_name"
        assert entry.retention_days == 730

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self) -> None:
        session = _make_session(scalar_result=None)
        svc = DataCatalogService(session)

        result = await svc.update_entry(uuid.uuid4(), dataset_name="x")

        assert result is None

    @pytest.mark.asyncio
    async def test_does_not_overwrite_id(self) -> None:
        original_id = uuid.uuid4()
        entry = _make_entry(entry_id=original_id)
        session = _make_session(scalar_result=entry)
        svc = DataCatalogService(session)

        new_id = uuid.uuid4()
        await svc.update_entry(original_id, id=new_id)

        # id must remain unchanged — it's immutable
        assert entry.id == original_id


# ---------------------------------------------------------------------------
# delete_entry
# ---------------------------------------------------------------------------


class TestDeleteEntry:
    """Tests for DataCatalogService.delete_entry."""

    @pytest.mark.asyncio
    async def test_deletes_found_entry(self) -> None:
        entry = _make_entry()
        session = _make_session(scalar_result=entry)
        svc = DataCatalogService(session)

        result = await svc.delete_entry(entry.id)

        assert result is True
        session.delete.assert_called_once_with(entry)
        session.flush.assert_called()

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self) -> None:
        session = _make_session(scalar_result=None)
        svc = DataCatalogService(session)

        result = await svc.delete_entry(uuid.uuid4())

        assert result is False
        session.delete.assert_not_called()


# ---------------------------------------------------------------------------
# classify_entry
# ---------------------------------------------------------------------------


class TestClassifyEntry:
    """Tests for DataCatalogService.classify_entry."""

    @pytest.mark.asyncio
    async def test_updates_classification(self) -> None:
        entry = _make_entry(classification=DataClassification.INTERNAL)
        session = _make_session(scalar_result=entry)
        svc = DataCatalogService(session)

        result = await svc.classify_entry(entry.id, DataClassification.CONFIDENTIAL)

        assert result is entry
        assert entry.classification == DataClassification.CONFIDENTIAL

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self) -> None:
        session = _make_session(scalar_result=None)
        svc = DataCatalogService(session)

        result = await svc.classify_entry(uuid.uuid4(), DataClassification.RESTRICTED)

        assert result is None


# ---------------------------------------------------------------------------
# get_entries_by_layer / get_entries_by_classification
# ---------------------------------------------------------------------------


class TestFilterMethods:
    """Tests for layer and classification filtering."""

    @pytest.mark.asyncio
    async def test_get_entries_by_layer(self) -> None:
        bronze_entry = _make_entry(layer=DataLayer.BRONZE)
        session = _make_session(scalars_result=[bronze_entry])
        svc = DataCatalogService(session)

        result = await svc.get_entries_by_layer(DataLayer.BRONZE)

        assert len(result) == 1
        assert result[0] is bronze_entry

    @pytest.mark.asyncio
    async def test_get_entries_by_classification(self) -> None:
        conf_entry = _make_entry(classification=DataClassification.CONFIDENTIAL)
        session = _make_session(scalars_result=[conf_entry])
        svc = DataCatalogService(session)

        result = await svc.get_entries_by_classification(DataClassification.CONFIDENTIAL)

        assert len(result) == 1
        assert result[0] is conf_entry

    @pytest.mark.asyncio
    async def test_get_entries_by_layer_with_engagement(self) -> None:
        engagement_id = uuid.uuid4()
        entry = _make_entry(engagement_id=engagement_id)
        session = _make_session(scalars_result=[entry])
        svc = DataCatalogService(session)

        result = await svc.get_entries_by_layer(
            DataLayer.BRONZE, engagement_id=engagement_id
        )

        assert len(result) == 1
