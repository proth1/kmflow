"""Append-only audit trail for GDPR-significant operations.

Logs consent changes, batch uploads (aggregate counts), data purges,
and retention enforcement runs to a JSON-lines file.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_AUDIT_DIR = os.path.expanduser("~/Library/Application Support/KMFlowAgent")
_AUDIT_LOG = os.path.join(_AUDIT_DIR, "audit.jsonl")


class AuditLogger:
    """Append-only JSON-lines audit logger for compliance operations."""

    def __init__(self, log_path: str = _AUDIT_LOG) -> None:
        self._log_path = log_path

    def _append(self, entry: dict[str, Any]) -> None:
        """Append a single JSON-lines entry to the audit log."""
        entry["timestamp"] = datetime.now(UTC).isoformat()
        try:
            Path(os.path.dirname(self._log_path)).mkdir(parents=True, exist_ok=True)
            with open(self._log_path, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except OSError as exc:
            logger.error("Failed to write audit log: %s", exc)

    def log_consent_change(self, engagement_id: str, old_state: str, new_state: str) -> None:
        """Log a consent state transition."""
        self._append(
            {
                "event": "consent_change",
                "engagement_id": engagement_id,
                "old_state": old_state,
                "new_state": new_state,
            }
        )

    def log_batch_upload(self, batch_id: str, event_count: int, status: str) -> None:
        """Log a batch upload (aggregate count, no event data)."""
        self._append(
            {
                "event": "batch_upload",
                "batch_id": batch_id,
                "event_count": event_count,
                "status": status,
            }
        )

    def log_purge(self, action: str, rows_deleted: int, db_path: str) -> None:
        """Log a data purge operation."""
        self._append(
            {
                "event": "data_purge",
                "action": action,
                "rows_deleted": rows_deleted,
                "db_path": db_path,
            }
        )

    def log_retention(self, rows_deleted: int, retention_days: int) -> None:
        """Log a retention enforcement run."""
        self._append(
            {
                "event": "retention_enforcement",
                "rows_deleted": rows_deleted,
                "retention_days": retention_days,
            }
        )
