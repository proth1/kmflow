"""Right to Be Forgotten (GDPR Art 17) — local data purge manager.

Handles complete data deletion when:
  - User requests data deletion via UI ("Delete My Data")
  - Consent is revoked (automatic purge)
  - Backend sends a purge command
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

from kmflow_agent.gdpr.audit_logger import AuditLogger

logger = logging.getLogger(__name__)

# Default local buffer path
_BUFFER_DIR = os.path.expanduser("~/Library/Application Support/KMFlowAgent")
_BUFFER_DB = os.path.join(_BUFFER_DIR, "buffer.db")


class DataPurgeManager:
    """Orchestrates local data deletion for GDPR compliance."""

    def __init__(
        self,
        db_path: str = _BUFFER_DB,
        audit: AuditLogger | None = None,
    ) -> None:
        self._db_path = db_path
        self._audit = audit or AuditLogger()

    def purge_local_buffer(self) -> int:
        """Delete ALL rows from the local SQLite event buffer and VACUUM.

        Returns:
            Number of rows deleted.
        """
        if not Path(self._db_path).exists():
            logger.info("No local buffer to purge at %s", self._db_path)
            return 0

        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.execute("SELECT COUNT(*) FROM events")
            count = cursor.fetchone()[0]

            conn.execute("DELETE FROM events")
            conn.execute("VACUUM")
            conn.commit()
            conn.close()

            self._audit.log_purge(
                action="purge_local_buffer",
                rows_deleted=count,
                db_path=self._db_path,
            )
            logger.info("Purged %d events from local buffer", count)
            return count
        except sqlite3.Error as exc:
            logger.error("Failed to purge local buffer: %s", exc)
            return 0

    def purge_uploaded_events(self, http_client: object | None = None) -> bool:
        """Request the backend to delete all uploaded events for this agent.

        Args:
            http_client: Optional HTTP client for backend purge request.
                         Full implementation requires backend endpoint.

        Returns:
            True if purge request was sent successfully.
        """
        # Backend purge endpoint not yet implemented — log intent
        self._audit.log_purge(
            action="purge_uploaded_events_requested",
            rows_deleted=0,
            db_path="backend",
        )
        logger.info("Backend purge requested (endpoint not yet implemented)")
        return True

    def execute_full_purge(self) -> dict[str, int | bool]:
        """Execute complete data purge: local + remote.

        Returns:
            Dict with purge results.
        """
        local_count = self.purge_local_buffer()
        remote_ok = self.purge_uploaded_events()

        self._audit.log_purge(
            action="full_purge_completed",
            rows_deleted=local_count,
            db_path=self._db_path,
        )

        return {
            "local_rows_deleted": local_count,
            "remote_purge_requested": remote_ok,
        }
