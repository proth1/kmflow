"""BDD tests for SaaS connectors incremental sync (Story #330).

Tests sync checkpoint management, sync logging with counts,
SAP timestamp conversion, and connector-specific incremental
sync behavior.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from src.integrations.sap_timestamp import (
    dats_tims_to_iso,
    normalize_sap_timestamp,
    odata_datetime_to_iso,
)
from src.integrations.sync_checkpoint import (
    SyncCheckpointStore,
    SyncLog,
    run_incremental_sync_async,
)


class TestSyncCheckpointStore:
    """Scenario 4: Checkpoint storage for incremental sync."""

    def test_no_checkpoint_returns_none(self) -> None:
        """First sync has no checkpoint."""
        store = SyncCheckpointStore()
        assert store.get_checkpoint("servicenow", "eng-001") is None

    def test_set_and_get_checkpoint(self) -> None:
        """Checkpoint persists after set."""
        store = SyncCheckpointStore()
        store.set_checkpoint("servicenow", "eng-001", "2026-01-15T10:00:00Z")

        assert store.get_checkpoint("servicenow", "eng-001") == "2026-01-15T10:00:00Z"

    def test_different_connectors_independent(self) -> None:
        """Checkpoints are scoped to connector+engagement pairs."""
        store = SyncCheckpointStore()
        store.set_checkpoint("servicenow", "eng-001", "2026-01-15T10:00:00Z")
        store.set_checkpoint("salesforce", "eng-001", "2026-01-16T12:00:00Z")

        assert store.get_checkpoint("servicenow", "eng-001") == "2026-01-15T10:00:00Z"
        assert store.get_checkpoint("salesforce", "eng-001") == "2026-01-16T12:00:00Z"

    def test_different_engagements_independent(self) -> None:
        """Same connector, different engagements have separate checkpoints."""
        store = SyncCheckpointStore()
        store.set_checkpoint("sap", "eng-001", "2026-01-10T08:00:00Z")
        store.set_checkpoint("sap", "eng-002", "2026-01-20T14:00:00Z")

        assert store.get_checkpoint("sap", "eng-001") == "2026-01-10T08:00:00Z"
        assert store.get_checkpoint("sap", "eng-002") == "2026-01-20T14:00:00Z"

    def test_clear_checkpoint(self) -> None:
        """Clearing a checkpoint forces full re-sync."""
        store = SyncCheckpointStore()
        store.set_checkpoint("servicenow", "eng-001", "2026-01-15T10:00:00Z")
        store.clear_checkpoint("servicenow", "eng-001")

        assert store.get_checkpoint("servicenow", "eng-001") is None

    def test_clear_nonexistent_checkpoint_noop(self) -> None:
        """Clearing a non-existent checkpoint is a no-op."""
        store = SyncCheckpointStore()
        store.clear_checkpoint("servicenow", "eng-999")  # no error

    def test_redis_key_pattern(self) -> None:
        """Key follows Redis pattern sync:checkpoint:{type}:{engagement}."""
        key = SyncCheckpointStore._key("servicenow", "eng-001")
        assert key == "sync:checkpoint:servicenow:eng-001"

    def test_list_checkpoints(self) -> None:
        """All checkpoints returned."""
        store = SyncCheckpointStore()
        store.set_checkpoint("sn", "e1", "t1")
        store.set_checkpoint("sf", "e2", "t2")

        checkpoints = store.list_checkpoints()
        assert len(checkpoints) == 2

    def test_checkpoint_updates_in_place(self) -> None:
        """Setting checkpoint again overwrites previous value."""
        store = SyncCheckpointStore()
        store.set_checkpoint("sap", "eng-001", "2026-01-10T00:00:00Z")
        store.set_checkpoint("sap", "eng-001", "2026-01-20T00:00:00Z")

        assert store.get_checkpoint("sap", "eng-001") == "2026-01-20T00:00:00Z"

    def test_backend_injection(self) -> None:
        """Accepts pre-populated backend (for Redis integration)."""
        backend = {"sync:checkpoint:sn:e1": "2026-01-01T00:00:00Z"}
        store = SyncCheckpointStore(backend=backend)

        assert store.get_checkpoint("sn", "e1") == "2026-01-01T00:00:00Z"


class TestSyncLog:
    """Sync log structure and counts."""

    def test_new_records_count(self) -> None:
        log = SyncLog(connector_type="servicenow", engagement_id="eng-001")
        log.new_records = 50
        assert log.total_processed == 50

    def test_mixed_counts(self) -> None:
        log = SyncLog(
            connector_type="sap",
            engagement_id="eng-001",
            new_records=10,
            updated_records=20,
            skipped_records=5,
        )
        assert log.total_processed == 35

    def test_success_when_no_errors(self) -> None:
        log = SyncLog(connector_type="salesforce", engagement_id="eng-001")
        assert log.success is True

    def test_failure_when_errors(self) -> None:
        log = SyncLog(
            connector_type="salesforce",
            engagement_id="eng-001",
            errors=["API error: 401"],
        )
        assert log.success is False

    def test_to_dict(self) -> None:
        log = SyncLog(
            connector_type="servicenow",
            engagement_id="eng-001",
            started_at="2026-01-15T10:00:00Z",
            completed_at="2026-01-15T10:05:00Z",
            new_records=100,
        )
        d = log.to_dict()
        assert d["connector_type"] == "servicenow"
        assert d["engagement_id"] == "eng-001"
        assert d["new_records"] == 100
        assert d["total_processed"] == 100
        assert d["success"] is True


class TestIncrementalSyncAsync:
    """Scenario 4: Incremental sync with checkpoint management."""

    @pytest.mark.asyncio
    async def test_first_sync_no_checkpoint(self) -> None:
        """First sync passes since=None and counts as new records."""
        connector = AsyncMock()
        connector.sync_incremental.return_value = {
            "records_synced": 50,
            "errors": [],
        }
        store = SyncCheckpointStore()

        log = await run_incremental_sync_async(
            connector, "servicenow", "eng-001", store
        )

        connector.sync_incremental.assert_called_once()
        call_kwargs = connector.sync_incremental.call_args
        assert call_kwargs[1]["since"] is None
        assert log.new_records == 50
        assert log.updated_records == 0
        assert log.success is True

    @pytest.mark.asyncio
    async def test_checkpoint_updated_on_success(self) -> None:
        """Checkpoint is set after successful sync."""
        connector = AsyncMock()
        connector.sync_incremental.return_value = {
            "records_synced": 10,
            "errors": [],
        }
        store = SyncCheckpointStore()

        await run_incremental_sync_async(connector, "sap", "eng-001", store)

        checkpoint = store.get_checkpoint("sap", "eng-001")
        assert checkpoint is not None
        # Checkpoint should be a recent ISO timestamp
        dt = datetime.fromisoformat(checkpoint.replace("Z", "+00:00"))
        assert dt.tzinfo is not None

    @pytest.mark.asyncio
    async def test_incremental_uses_checkpoint(self) -> None:
        """Second sync passes previous checkpoint as since."""
        connector = AsyncMock()
        connector.sync_incremental.return_value = {
            "records_synced": 5,
            "errors": [],
        }
        store = SyncCheckpointStore()
        store.set_checkpoint("servicenow", "eng-001", "2026-01-15T10:00:00Z")

        log = await run_incremental_sync_async(
            connector, "servicenow", "eng-001", store
        )

        call_kwargs = connector.sync_incremental.call_args
        assert call_kwargs[1]["since"] == "2026-01-15T10:00:00Z"
        assert log.updated_records == 5
        assert log.new_records == 0

    @pytest.mark.asyncio
    async def test_checkpoint_not_updated_on_error(self) -> None:
        """Checkpoint unchanged when sync returns errors."""
        connector = AsyncMock()
        connector.sync_incremental.return_value = {
            "records_synced": 0,
            "errors": ["API error: 500"],
        }
        store = SyncCheckpointStore()
        store.set_checkpoint("salesforce", "eng-001", "2026-01-10T00:00:00Z")

        log = await run_incremental_sync_async(
            connector, "salesforce", "eng-001", store
        )

        assert not log.success
        # Checkpoint should remain unchanged
        assert store.get_checkpoint("salesforce", "eng-001") == "2026-01-10T00:00:00Z"

    @pytest.mark.asyncio
    async def test_exception_captured_in_log(self) -> None:
        """Connector exceptions are captured in sync log."""
        connector = AsyncMock()
        connector.sync_incremental.side_effect = RuntimeError("connection refused")
        store = SyncCheckpointStore()

        log = await run_incremental_sync_async(
            connector, "servicenow", "eng-001", store
        )

        assert not log.success
        assert "connection refused" in log.errors[0]
        assert store.get_checkpoint("servicenow", "eng-001") is None

    @pytest.mark.asyncio
    async def test_kwargs_forwarded_to_connector(self) -> None:
        """Extra kwargs are forwarded to sync_incremental."""
        connector = AsyncMock()
        connector.sync_incremental.return_value = {
            "records_synced": 10,
            "errors": [],
        }
        store = SyncCheckpointStore()

        await run_incremental_sync_async(
            connector,
            "servicenow",
            "eng-001",
            store,
            table_name="change_request",
            query_filter="priority=1",
        )

        call_kwargs = connector.sync_incremental.call_args
        assert call_kwargs[1]["table_name"] == "change_request"
        assert call_kwargs[1]["query_filter"] == "priority=1"

    @pytest.mark.asyncio
    async def test_log_has_timing(self) -> None:
        """Sync log includes started_at and completed_at timestamps."""
        connector = AsyncMock()
        connector.sync_incremental.return_value = {
            "records_synced": 1,
            "errors": [],
        }
        store = SyncCheckpointStore()

        log = await run_incremental_sync_async(
            connector, "sap", "eng-001", store
        )

        assert log.started_at != ""
        assert log.completed_at != ""
        assert log.started_at <= log.completed_at


class TestSAPTimestampConversion:
    """Scenario 2: SAP timestamp format conversion to ISO 8601."""

    def test_dats_only(self) -> None:
        """YYYYMMDD converts to midnight UTC."""
        result = dats_tims_to_iso("20260115")
        assert result == "2026-01-15T00:00:00Z"

    def test_dats_with_tims(self) -> None:
        """YYYYMMDD + HHMMSS converts to full datetime."""
        result = dats_tims_to_iso("20260115", "093045")
        assert result == "2026-01-15T09:30:45Z"

    def test_invalid_dats_raises(self) -> None:
        """Invalid DATS format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid SAP DATS"):
            dats_tims_to_iso("2026-01-15")

    def test_invalid_tims_raises(self) -> None:
        """Invalid TIMS format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid SAP TIMS"):
            dats_tims_to_iso("20260115", "9:30")

    def test_odata_datetime(self) -> None:
        """OData /Date(millis)/ format converts correctly."""
        # 1768507200000 ms = 2026-01-15T20:00:00Z
        result = odata_datetime_to_iso("/Date(1768507200000)/")
        assert result == "2026-01-15T20:00:00Z"

    def test_odata_invalid_format(self) -> None:
        """Invalid OData format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid OData"):
            odata_datetime_to_iso("not-odata")

    def test_normalize_odata(self) -> None:
        """normalize_sap_timestamp detects OData format."""
        result = normalize_sap_timestamp("/Date(1768507200000)/")
        assert result == "2026-01-15T20:00:00Z"

    def test_normalize_dats(self) -> None:
        """normalize_sap_timestamp detects 8-digit DATS."""
        result = normalize_sap_timestamp("20260115")
        assert result == "2026-01-15T00:00:00Z"

    def test_normalize_dats_tims_combined(self) -> None:
        """normalize_sap_timestamp detects 14-digit YYYYMMDDHHMMSS."""
        result = normalize_sap_timestamp("20260115093045")
        assert result == "2026-01-15T09:30:45Z"

    def test_normalize_iso_passthrough(self) -> None:
        """ISO 8601 passes through unchanged."""
        iso = "2026-01-15T12:00:00Z"
        assert normalize_sap_timestamp(iso) == iso

    def test_midnight_boundary(self) -> None:
        """Midnight boundary converts correctly."""
        result = dats_tims_to_iso("20260101", "000000")
        assert result == "2026-01-01T00:00:00Z"

    def test_end_of_day(self) -> None:
        """End of day converts correctly."""
        result = dats_tims_to_iso("20261231", "235959")
        assert result == "2026-12-31T23:59:59Z"
