"""Tests for governance package export.

Verifies that export_governance_package produces a valid ZIP archive with
the expected files and structure. Uses mock sessions to avoid database
dependency.
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import DataCatalogEntry, DataClassification, DataLayer
from src.governance.export import export_governance_package


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_catalog_entry(
    dataset_name: str = "test_dataset",
    layer: DataLayer = DataLayer.SILVER,
    engagement_id: uuid.UUID | None = None,
) -> MagicMock:
    """Build a mock DataCatalogEntry."""
    entry = MagicMock(spec=DataCatalogEntry)
    entry.id = uuid.uuid4()
    entry.dataset_name = dataset_name
    entry.dataset_type = "evidence"
    entry.layer = layer
    entry.classification = DataClassification.INTERNAL
    entry.owner = "team-data"
    entry.retention_days = 365
    entry.quality_sla = None
    entry.schema_definition = None
    entry.description = "Test dataset"
    entry.row_count = None
    entry.size_bytes = None
    entry.delta_table_path = None
    entry.created_at = datetime.now(UTC)
    entry.updated_at = datetime.now(UTC)
    entry.engagement_id = engagement_id
    return entry


def _make_session(
    catalog_entries: list,
    lineage_records: list | None = None,
    evidence_items: list | None = None,
) -> AsyncMock:
    """Build a mock AsyncSession with configurable execute results.

    The session is called multiple times (once for catalog, once for lineage,
    once per catalog entry for SLA quality check). We use side_effect to
    return different results per call.
    """
    session = AsyncMock()

    # catalog result
    catalog_result = MagicMock()
    catalog_result.scalars.return_value.all.return_value = catalog_entries

    # lineage result
    lineage_result = MagicMock()
    lineage_result.scalars.return_value.all.return_value = lineage_records or []

    # evidence/SLA results (one per catalog entry)
    sla_results = []
    for _ in catalog_entries:
        sla_result = MagicMock()
        sla_result.scalars.return_value.all.return_value = evidence_items or []
        sla_results.append(sla_result)

    session.execute = AsyncMock(
        side_effect=[catalog_result, lineage_result] + sla_results
    )

    return session


# ---------------------------------------------------------------------------
# ZIP structure tests
# ---------------------------------------------------------------------------


class TestExportGovernancePackage:
    """Tests that the export ZIP has the correct structure and files."""

    @pytest.mark.asyncio
    async def test_returns_bytes(self) -> None:
        engagement_id = uuid.uuid4()
        session = _make_session(catalog_entries=[])

        result = await export_governance_package(session, engagement_id)

        assert isinstance(result, bytes)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_result_is_valid_zip(self) -> None:
        engagement_id = uuid.uuid4()
        session = _make_session(catalog_entries=[])

        result = await export_governance_package(session, engagement_id)

        assert zipfile.is_zipfile(io.BytesIO(result))

    @pytest.mark.asyncio
    async def test_zip_contains_required_files(self) -> None:
        engagement_id = uuid.uuid4()
        session = _make_session(catalog_entries=[])

        result = await export_governance_package(session, engagement_id)

        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            names = zf.namelist()

        assert "catalog.json" in names
        assert "policies.yaml" in names
        assert "lineage_summary.json" in names
        assert "quality_report.json" in names

    @pytest.mark.asyncio
    async def test_catalog_json_is_valid_json(self) -> None:
        engagement_id = uuid.uuid4()
        session = _make_session(catalog_entries=[])

        result = await export_governance_package(session, engagement_id)

        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            catalog_bytes = zf.read("catalog.json")

        catalog = json.loads(catalog_bytes)
        assert isinstance(catalog, list)

    @pytest.mark.asyncio
    async def test_catalog_json_contains_entries(self) -> None:
        engagement_id = uuid.uuid4()
        entry = _make_catalog_entry(
            dataset_name="my_dataset",
            engagement_id=engagement_id,
        )
        session = _make_session(catalog_entries=[entry])

        result = await export_governance_package(session, engagement_id)

        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            catalog = json.loads(zf.read("catalog.json"))

        assert len(catalog) == 1
        assert catalog[0]["dataset_name"] == "my_dataset"

    @pytest.mark.asyncio
    async def test_policies_yaml_is_valid_yaml(self) -> None:
        import yaml

        engagement_id = uuid.uuid4()
        session = _make_session(catalog_entries=[])

        result = await export_governance_package(session, engagement_id)

        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            policies_text = zf.read("policies.yaml").decode()

        parsed = yaml.safe_load(policies_text)
        assert isinstance(parsed, dict)

    @pytest.mark.asyncio
    async def test_lineage_summary_contains_engagement_id(self) -> None:
        engagement_id = uuid.uuid4()
        session = _make_session(catalog_entries=[])

        result = await export_governance_package(session, engagement_id)

        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            summary = json.loads(zf.read("lineage_summary.json"))

        assert summary["engagement_id"] == str(engagement_id)
        assert "total_lineage_records" in summary
        assert "records" in summary

    @pytest.mark.asyncio
    async def test_quality_report_structure(self) -> None:
        engagement_id = uuid.uuid4()
        session = _make_session(catalog_entries=[])

        result = await export_governance_package(session, engagement_id)

        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            report = json.loads(zf.read("quality_report.json"))

        assert "engagement_id" in report
        assert "total_entries" in report
        assert "passing_entries" in report
        assert "failing_entries" in report
        assert "results" in report

    @pytest.mark.asyncio
    async def test_quality_report_counts_match_entries(self) -> None:
        engagement_id = uuid.uuid4()
        entry1 = _make_catalog_entry(engagement_id=engagement_id)
        entry2 = _make_catalog_entry(dataset_name="second_dataset", engagement_id=engagement_id)
        session = _make_session(catalog_entries=[entry1, entry2])

        result = await export_governance_package(session, engagement_id)

        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            report = json.loads(zf.read("quality_report.json"))

        assert report["total_entries"] == 2
        assert len(report["results"]) == 2

    @pytest.mark.asyncio
    async def test_catalog_entry_fields_serialized(self) -> None:
        engagement_id = uuid.uuid4()
        entry = _make_catalog_entry(
            dataset_name="serialized_dataset",
            layer=DataLayer.GOLD,
            engagement_id=engagement_id,
        )
        session = _make_session(catalog_entries=[entry])

        result = await export_governance_package(session, engagement_id)

        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            catalog = json.loads(zf.read("catalog.json"))

        record = catalog[0]
        assert record["dataset_name"] == "serialized_dataset"
        assert record["layer"] == "gold"
        assert "id" in record
        assert "created_at" in record

    @pytest.mark.asyncio
    async def test_empty_engagement_produces_valid_package(self) -> None:
        engagement_id = uuid.uuid4()
        session = _make_session(catalog_entries=[])

        result = await export_governance_package(session, engagement_id)

        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            catalog = json.loads(zf.read("catalog.json"))
            report = json.loads(zf.read("quality_report.json"))

        assert catalog == []
        assert report["total_entries"] == 0
