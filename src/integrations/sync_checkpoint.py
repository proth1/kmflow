"""Incremental sync checkpoint and logging service (Story #330).

Manages per-connector, per-engagement sync checkpoints for tracking
the last successful sync timestamp. Provides sync log tracking with
counts of new, updated, and skipped records.

Checkpoint storage is abstracted via a backend dict (in production,
backed by Redis with key pattern ``sync:checkpoint:{connector_type}:{engagement_id}``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SyncLog:
    """Log entry for a sync operation."""

    connector_type: str
    engagement_id: str
    started_at: str = ""
    completed_at: str = ""
    new_records: int = 0
    updated_records: int = 0
    skipped_records: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total_processed(self) -> int:
        return self.new_records + self.updated_records + self.skipped_records

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "connector_type": self.connector_type,
            "engagement_id": self.engagement_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "new_records": self.new_records,
            "updated_records": self.updated_records,
            "skipped_records": self.skipped_records,
            "total_processed": self.total_processed,
            "success": self.success,
            "errors": self.errors,
        }


@dataclass
class WatermarkState:
    """Watermark/offset tracking for incremental sync position.

    Tracks both timestamp-based and offset-based sync positions,
    supporting connectors that use either or both strategies.
    """

    connector_type: str
    engagement_id: str
    last_timestamp: str | None = None
    last_offset: int | None = None
    last_cursor: str | None = None
    records_since_reset: int = 0
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.updated_at:
            self.updated_at = _now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "connector_type": self.connector_type,
            "engagement_id": self.engagement_id,
            "last_timestamp": self.last_timestamp,
            "last_offset": self.last_offset,
            "last_cursor": self.last_cursor,
            "records_since_reset": self.records_since_reset,
            "updated_at": self.updated_at,
        }


class SyncCheckpointStore:
    """Store for sync checkpoints (last_sync_at per connector+engagement).

    In production this would be backed by Redis. The in-memory dict
    mirrors the Redis key pattern ``sync:checkpoint:{connector_type}:{engagement_id}``.
    """

    def __init__(self, backend: dict[str, str] | None = None) -> None:
        self._store: dict[str, str] = backend if backend is not None else {}

    @staticmethod
    def _key(connector_type: str, engagement_id: str) -> str:
        return f"sync:checkpoint:{connector_type}:{engagement_id}"

    def get_checkpoint(self, connector_type: str, engagement_id: str) -> str | None:
        """Get the last successful sync timestamp.

        Returns:
            ISO 8601 timestamp string, or None if no previous sync.
        """
        return self._store.get(self._key(connector_type, engagement_id))

    def set_checkpoint(
        self,
        connector_type: str,
        engagement_id: str,
        timestamp: str,
    ) -> None:
        """Set the sync checkpoint to the given timestamp."""
        key = self._key(connector_type, engagement_id)
        self._store[key] = timestamp
        logger.info(
            "Updated sync checkpoint %s = %s",
            key,
            timestamp,
        )

    def clear_checkpoint(self, connector_type: str, engagement_id: str) -> None:
        """Remove a sync checkpoint (forces full re-sync)."""
        key = self._key(connector_type, engagement_id)
        self._store.pop(key, None)

    def list_checkpoints(self) -> dict[str, str]:
        """Return all stored checkpoints."""
        return dict(self._store)

    # ── Watermark/Offset Tracking ────────────────────────────────────

    @staticmethod
    def _watermark_key(connector_type: str, engagement_id: str) -> str:
        return f"sync:watermark:{connector_type}:{engagement_id}"

    def get_watermark(self, connector_type: str, engagement_id: str) -> WatermarkState | None:
        """Get the watermark state for a connector+engagement.

        Returns:
            WatermarkState if exists, None otherwise.
        """
        key = self._watermark_key(connector_type, engagement_id)
        raw = self._store.get(key)
        if raw is None:
            return None
        # Deserialize from JSON string
        import json
        data = json.loads(raw)
        return WatermarkState(**data)

    def set_watermark(
        self,
        connector_type: str,
        engagement_id: str,
        *,
        timestamp: str | None = None,
        offset: int | None = None,
        cursor: str | None = None,
        records_processed: int = 0,
    ) -> WatermarkState:
        """Update the watermark state for a connector+engagement.

        Args:
            connector_type: Connector identifier.
            engagement_id: Engagement being synced.
            timestamp: Last processed timestamp (ISO 8601).
            offset: Last processed numeric offset.
            cursor: Last pagination cursor.
            records_processed: Records processed in this batch.

        Returns:
            Updated WatermarkState.
        """
        import json

        existing = self.get_watermark(connector_type, engagement_id)
        state = WatermarkState(
            connector_type=connector_type,
            engagement_id=engagement_id,
            last_timestamp=timestamp or (existing.last_timestamp if existing else None),
            last_offset=offset if offset is not None else (existing.last_offset if existing else None),
            last_cursor=cursor or (existing.last_cursor if existing else None),
            records_since_reset=(existing.records_since_reset if existing else 0) + records_processed,
        )

        key = self._watermark_key(connector_type, engagement_id)
        self._store[key] = json.dumps(state.to_dict())
        logger.info("Updated watermark %s: offset=%s, cursor=%s", key, offset, cursor)
        return state

    def reset_watermark(self, connector_type: str, engagement_id: str) -> None:
        """Reset watermark state (forces full re-sync)."""
        key = self._watermark_key(connector_type, engagement_id)
        self._store.pop(key, None)


def _now_iso() -> str:
    """Current UTC time as ISO 8601 string."""
    return datetime.now(tz=UTC).isoformat()


async def run_incremental_sync_async(
    connector: Any,
    connector_type: str,
    engagement_id: str,
    checkpoint_store: SyncCheckpointStore,
    **kwargs: Any,
) -> SyncLog:
    """Run an async incremental sync with checkpoint management.

    1. Reads the last checkpoint timestamp.
    2. Calls connector.sync_incremental(engagement_id, since=checkpoint, **kwargs).
    3. On success, updates the checkpoint to sync start time.
    4. Returns a SyncLog with record counts.

    Args:
        connector: A BaseConnector instance.
        connector_type: Identifier (e.g., "servicenow").
        engagement_id: The engagement being synced.
        checkpoint_store: Where to read/write checkpoints.
        **kwargs: Additional arguments passed to sync_incremental.

    Returns:
        SyncLog with counts and timing.
    """
    start_time = _now_iso()
    log = SyncLog(
        connector_type=connector_type,
        engagement_id=engagement_id,
        started_at=start_time,
    )

    since = checkpoint_store.get_checkpoint(connector_type, engagement_id)

    try:
        result = await connector.sync_incremental(
            engagement_id,
            since=since,
            **kwargs,
        )

        records_synced = result.get("records_synced", 0)
        errors = result.get("errors", [])

        if since is None:
            # First sync — all records are new
            log.new_records = records_synced
        else:
            # Incremental — records are updates (simplified; real
            # dedup would compare IDs against existing records)
            log.updated_records = records_synced

        log.errors = errors

        if log.success:
            checkpoint_store.set_checkpoint(
                connector_type,
                engagement_id,
                start_time,
            )

    except Exception as exc:
        log.errors.append(str(exc))
        logger.error(
            "Incremental sync failed for %s/%s: %s",
            connector_type,
            engagement_id,
            exc,
        )

    log.completed_at = _now_iso()
    return log
