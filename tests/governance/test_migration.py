"""Tests for the bulk evidence migration job.

Verifies that migrate_engagement correctly processes EvidenceItem records,
writes to Bronze/Silver, creates lineage and catalog records, skips
already-migrated items, handles failures gracefully, and respects dry_run.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import (
    DataCatalogEntry,
    EvidenceCategory,
    EvidenceItem,
    EvidenceLineage,
    ValidationStatus,
)
from src.datalake.backend import StorageMetadata
from src.governance.migration import (
    MigrationResult,
    _build_fragments_from_item,
    _quality_scores_from_item,
    _read_local_file,
    migrate_engagement,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_evidence_item(
    engagement_id: uuid.UUID,
    delta_path: str | None = None,
    lineage_id: uuid.UUID | None = None,
) -> MagicMock:
    """Build a mock EvidenceItem."""
    item = MagicMock(spec=EvidenceItem)
    item.id = uuid.uuid4()
    item.engagement_id = engagement_id
    item.name = "test_evidence.pdf"
    item.category = EvidenceCategory.DOCUMENTS
    item.format = "pdf"
    item.file_path = None
    item.delta_path = delta_path
    item.lineage_id = lineage_id
    item.completeness_score = 0.8
    item.reliability_score = 0.7
    item.freshness_score = 0.9
    item.consistency_score = 0.6
    item.validation_status = ValidationStatus.ACTIVE
    item.created_at = None
    return item


def _make_storage_backend() -> AsyncMock:
    """Build a mock StorageBackend."""
    backend = AsyncMock()
    meta = StorageMetadata(
        path="/tmp/evidence/file.pdf",
        version=1,
        content_hash="abc123",
        size_bytes=1024,
    )
    backend.write = AsyncMock(return_value=meta)
    backend.exists = AsyncMock(return_value=False)
    return backend


def _make_silver_writer() -> AsyncMock:
    """Build a mock SilverLayerWriter."""
    writer = AsyncMock()
    writer.write_fragments = AsyncMock(return_value={"rows_written": 1, "table_path": "/tmp/silver/frags"})
    writer.write_entities = AsyncMock(return_value={"rows_written": 0, "table_path": ""})
    writer.write_quality_event = AsyncMock(return_value={"rows_written": 1, "table_path": "/tmp/silver/quality"})
    return writer


def _make_session(
    items: list[Any],
    lineage_exists: bool = False,
    catalog_exists: bool = False,
) -> AsyncMock:
    """Build a mock AsyncSession.

    The session's execute() is configured to return in sequence:
    1. Evidence items query (scalars().all())
    2. Lineage check for each item (scalar_one_or_none())
    3. Catalog entry check for each item (scalar_one_or_none())
    """
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.delete = AsyncMock()

    # Configure begin_nested() as an async context manager (savepoint support)
    nested_cm = MagicMock()
    nested_cm.__aenter__ = AsyncMock(return_value=None)
    nested_cm.__aexit__ = AsyncMock(return_value=False)
    session.begin_nested = MagicMock(return_value=nested_cm)

    # Items result
    items_result = MagicMock()
    items_result.scalars.return_value.all.return_value = items

    # Lineage result
    lineage_result = MagicMock()
    lineage_result.scalar_one_or_none.return_value = MagicMock(spec=EvidenceLineage) if lineage_exists else None

    # Catalog result (used by _has_catalog_entry and DataCatalogService.get_entry)
    catalog_result = MagicMock()
    catalog_result.scalar_one_or_none.return_value = MagicMock(spec=DataCatalogEntry) if catalog_exists else None
    catalog_result.scalars.return_value.all.return_value = []

    # Provide enough side_effects for any number of items
    session.execute = AsyncMock(side_effect=[items_result] + [lineage_result, catalog_result] * max(len(items), 1) * 5)
    return session


# ---------------------------------------------------------------------------
# MigrationResult dataclass
# ---------------------------------------------------------------------------


class TestMigrationResult:
    """Tests for the MigrationResult dataclass."""

    def test_default_values(self) -> None:
        result = MigrationResult(engagement_id="abc")
        assert result.items_processed == 0
        assert result.items_skipped == 0
        assert result.items_failed == 0
        assert result.bronze_written == 0
        assert result.silver_written == 0
        assert result.catalog_entries_created == 0
        assert result.lineage_records_created == 0
        assert result.errors == []
        assert result.dry_run is False

    def test_dry_run_flag(self) -> None:
        result = MigrationResult(engagement_id="abc", dry_run=True)
        assert result.dry_run is True


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestBuildFragmentsFromItem:
    """Tests for _build_fragments_from_item."""

    def test_returns_one_fragment(self) -> None:
        item = MagicMock()
        item.name = "report.pdf"
        item.category = EvidenceCategory.DOCUMENTS
        fragments = _build_fragments_from_item(item)
        assert len(fragments) == 1

    def test_fragment_has_required_keys(self) -> None:
        item = MagicMock()
        item.name = "data.csv"
        item.category = EvidenceCategory.STRUCTURED_DATA
        fragment = _build_fragments_from_item(item)[0]
        assert "id" in fragment
        assert "fragment_type" in fragment
        assert "content" in fragment
        assert fragment["fragment_type"] == "text"

    def test_fragment_content_contains_name(self) -> None:
        item = MagicMock()
        item.name = "unique_doc_name.pdf"
        item.category = EvidenceCategory.DOCUMENTS
        fragment = _build_fragments_from_item(item)[0]
        assert "unique_doc_name.pdf" in fragment["content"]


class TestQualityScoresFromItem:
    """Tests for _quality_scores_from_item."""

    def test_extracts_all_four_scores(self) -> None:
        item = MagicMock()
        item.completeness_score = 0.8
        item.reliability_score = 0.7
        item.freshness_score = 0.9
        item.consistency_score = 0.6
        scores = _quality_scores_from_item(item)
        assert scores["completeness"] == 0.8
        assert scores["reliability"] == 0.7
        assert scores["freshness"] == 0.9
        assert scores["consistency"] == 0.6

    def test_defaults_to_zero_for_none(self) -> None:
        item = MagicMock()
        item.completeness_score = None
        item.reliability_score = None
        item.freshness_score = None
        item.consistency_score = None
        scores = _quality_scores_from_item(item)
        assert all(v == 0.0 for v in scores.values())


class TestReadLocalFile:
    """Tests for _read_local_file."""

    def test_returns_none_when_file_not_found(self, tmp_path: Any) -> None:
        item = MagicMock()
        item.file_path = None
        item.name = "nonexistent_file.pdf"
        item.id = uuid.uuid4()
        result = _read_local_file(item, "some-engagement-id")
        assert result is None

    def test_reads_from_file_path_when_set(self, tmp_path: Any) -> None:
        # Files must reside under evidence_store/ to pass the path-boundary check.
        # Create the directory and place the file inside it.
        evidence_store = tmp_path / "evidence_store"
        evidence_store.mkdir()
        test_file = evidence_store / "test.pdf"
        test_file.write_bytes(b"PDF content")

        item = MagicMock()
        item.file_path = str(test_file)
        item.name = "test.pdf"
        item.id = uuid.uuid4()

        # Patch Path.resolve so that the boundary resolves to tmp_path/evidence_store
        from pathlib import Path as _Path

        original_resolve = _Path.resolve

        def patched_resolve(self: _Path, **kwargs: Any) -> _Path:
            # Remap the cwd-relative "evidence_store" anchor to our tmp dir
            result = original_resolve(self, **kwargs)
            cwd_store = original_resolve(_Path("evidence_store"))
            if str(result).startswith(str(cwd_store)):
                # already resolves into real evidence_store — leave alone
                return result
            # For the test file inside tmp evidence_store, return as-is
            return result

        # Use a simpler approach: monkeypatch the base_resolved computation
        # by temporarily setting the cwd to tmp_path so Path("evidence_store")
        # resolves to our temp evidence_store directory.
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = _read_local_file(item, "any-engagement")
        finally:
            os.chdir(original_cwd)

        assert result == b"PDF content"

    def test_rejects_file_outside_evidence_store(self, tmp_path: Any) -> None:
        # Files outside evidence_store/ should be blocked by path traversal check.
        test_file = tmp_path / "secret.txt"
        test_file.write_bytes(b"secret")

        item = MagicMock()
        item.file_path = str(test_file)
        item.name = "secret.txt"
        item.id = uuid.uuid4()

        result = _read_local_file(item, "any-engagement")
        # Path traversal detected: returns None rather than reading the file
        assert result is None


# ---------------------------------------------------------------------------
# migrate_engagement
# ---------------------------------------------------------------------------


class TestMigrateEngagement:
    """Tests for migrate_engagement."""

    @pytest.mark.asyncio
    async def test_returns_migration_result(self) -> None:
        engagement_id = str(uuid.uuid4())
        session = _make_session(items=[])
        backend = _make_storage_backend()
        writer = _make_silver_writer()

        result = await migrate_engagement(
            session=session,
            engagement_id=engagement_id,
            storage_backend=backend,
            silver_writer=writer,
        )

        assert isinstance(result, MigrationResult)
        assert result.engagement_id == engagement_id

    @pytest.mark.asyncio
    async def test_invalid_engagement_id_returns_error(self) -> None:
        session = AsyncMock()
        backend = _make_storage_backend()
        writer = _make_silver_writer()

        result = await migrate_engagement(
            session=session,
            engagement_id="not-a-uuid",
            storage_backend=backend,
            silver_writer=writer,
        )

        assert result.items_failed == 1
        assert len(result.errors) == 1
        assert "Invalid engagement_id" in result.errors[0]

    @pytest.mark.asyncio
    async def test_empty_engagement_processes_zero_items(self) -> None:
        engagement_id = str(uuid.uuid4())
        session = _make_session(items=[])
        backend = _make_storage_backend()
        writer = _make_silver_writer()

        result = await migrate_engagement(
            session=session,
            engagement_id=engagement_id,
            storage_backend=backend,
            silver_writer=writer,
        )

        assert result.items_processed == 0
        assert result.items_failed == 0
        assert result.items_skipped == 0

    @pytest.mark.asyncio
    async def test_dry_run_does_not_call_storage_write(self) -> None:
        engagement_id = str(uuid.uuid4())
        item = _make_evidence_item(uuid.UUID(engagement_id))
        session = _make_session(items=[item])
        backend = _make_storage_backend()
        writer = _make_silver_writer()

        with patch(
            "src.governance.migration._read_local_file",
            return_value=b"fake content",
        ):
            result = await migrate_engagement(
                session=session,
                engagement_id=engagement_id,
                storage_backend=backend,
                silver_writer=writer,
                dry_run=True,
            )

        backend.write.assert_not_called()
        writer.write_fragments.assert_not_called()
        writer.write_quality_event.assert_not_called()
        assert result.dry_run is True

    @pytest.mark.asyncio
    async def test_dry_run_counts_bronze_and_silver(self) -> None:
        engagement_id = str(uuid.uuid4())
        item = _make_evidence_item(uuid.UUID(engagement_id))
        session = _make_session(items=[item])
        backend = _make_storage_backend()
        writer = _make_silver_writer()

        with patch(
            "src.governance.migration._read_local_file",
            return_value=b"fake content",
        ):
            result = await migrate_engagement(
                session=session,
                engagement_id=engagement_id,
                storage_backend=backend,
                silver_writer=writer,
                dry_run=True,
            )

        assert result.bronze_written == 1
        assert result.silver_written == 1

    @pytest.mark.asyncio
    async def test_skips_bronze_write_when_delta_path_set(self) -> None:
        engagement_id = str(uuid.uuid4())
        item = _make_evidence_item(
            uuid.UUID(engagement_id),
            delta_path="/existing/path",
        )
        # Already has lineage and catalog so it will be skipped
        session = _make_session(
            items=[item],
            lineage_exists=True,
            catalog_exists=True,
        )
        backend = _make_storage_backend()
        writer = _make_silver_writer()

        result = await migrate_engagement(
            session=session,
            engagement_id=engagement_id,
            storage_backend=backend,
            silver_writer=writer,
        )

        backend.write.assert_not_called()
        assert result.items_skipped == 1

    @pytest.mark.asyncio
    async def test_creates_lineage_when_missing(self) -> None:
        engagement_id = str(uuid.uuid4())
        item = _make_evidence_item(uuid.UUID(engagement_id))
        session = _make_session(items=[item], lineage_exists=False)
        backend = _make_storage_backend()
        writer = _make_silver_writer()

        with (
            patch(
                "src.governance.migration.create_lineage_record",
                new=AsyncMock(return_value=MagicMock()),
            ) as mock_create,
            patch(
                "src.governance.migration._read_local_file",
                return_value=None,
            ),
        ):
            result = await migrate_engagement(
                session=session,
                engagement_id=engagement_id,
                storage_backend=backend,
                silver_writer=writer,
            )

        mock_create.assert_called_once()
        assert result.lineage_records_created == 1

    @pytest.mark.asyncio
    async def test_skips_lineage_when_already_exists(self) -> None:
        engagement_id = str(uuid.uuid4())
        item = _make_evidence_item(uuid.UUID(engagement_id))
        session = _make_session(items=[item], lineage_exists=True)
        backend = _make_storage_backend()
        writer = _make_silver_writer()

        with (
            patch(
                "src.governance.migration.create_lineage_record",
                new=AsyncMock(),
            ) as mock_create,
            patch(
                "src.governance.migration._read_local_file",
                return_value=None,
            ),
        ):
            result = await migrate_engagement(
                session=session,
                engagement_id=engagement_id,
                storage_backend=backend,
                silver_writer=writer,
            )

        mock_create.assert_not_called()
        assert result.lineage_records_created == 0

    @pytest.mark.asyncio
    async def test_creates_catalog_entry_when_missing(self) -> None:
        engagement_id = str(uuid.uuid4())
        item = _make_evidence_item(uuid.UUID(engagement_id))
        session = _make_session(items=[item], catalog_exists=False)
        backend = _make_storage_backend()
        writer = _make_silver_writer()

        with (
            patch(
                "src.governance.migration.create_lineage_record",
                new=AsyncMock(return_value=MagicMock()),
            ),
            patch(
                "src.governance.migration._read_local_file",
                return_value=None,
            ),
            patch(
                "src.governance.migration.DataCatalogService.create_entry",
                new=AsyncMock(return_value=MagicMock()),
            ) as mock_cat,
        ):
            result = await migrate_engagement(
                session=session,
                engagement_id=engagement_id,
                storage_backend=backend,
                silver_writer=writer,
            )

        mock_cat.assert_called_once()
        assert result.catalog_entries_created == 1

    @pytest.mark.asyncio
    async def test_handles_per_item_failure_and_continues(self) -> None:
        engagement_id = str(uuid.uuid4())
        good_item = _make_evidence_item(uuid.UUID(engagement_id))

        # Session that raises on second items query (first item fails)
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.delete = AsyncMock()

        # Configure begin_nested() as an async context manager (savepoint)
        nested_cm = MagicMock()
        nested_cm.__aenter__ = AsyncMock(return_value=None)
        nested_cm.__aexit__ = AsyncMock(return_value=False)
        session.begin_nested = MagicMock(return_value=nested_cm)

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [good_item]
        # Lineage check raises (simulates a DB error inside the savepoint)
        session.execute = AsyncMock(
            side_effect=[
                items_result,
                RuntimeError("DB connection lost"),
            ]
        )

        backend = _make_storage_backend()
        writer = _make_silver_writer()

        result = await migrate_engagement(
            session=session,
            engagement_id=engagement_id,
            storage_backend=backend,
            silver_writer=writer,
        )

        assert result.items_failed == 1
        assert len(result.errors) == 1
        assert str(good_item.id) in result.errors[0]

    @pytest.mark.asyncio
    async def test_commits_on_success(self) -> None:
        engagement_id = str(uuid.uuid4())
        session = _make_session(items=[])

        await migrate_engagement(
            session=session,
            engagement_id=engagement_id,
            storage_backend=_make_storage_backend(),
            silver_writer=_make_silver_writer(),
        )

        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_dry_run_does_not_commit(self) -> None:
        engagement_id = str(uuid.uuid4())
        session = _make_session(items=[])

        await migrate_engagement(
            session=session,
            engagement_id=engagement_id,
            storage_backend=_make_storage_backend(),
            silver_writer=_make_silver_writer(),
            dry_run=True,
        )

        session.commit.assert_not_called()
