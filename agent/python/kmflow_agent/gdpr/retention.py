"""Data retention enforcement — deletes events older than the configured limit.

Runs on a periodic timer (default: daily) to enforce the retention policy.
Default retention is 7 days, configurable via EngagementConfig.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from kmflow_agent.gdpr.audit_logger import AuditLogger

logger = logging.getLogger(__name__)

_BUFFER_DIR = Path("~/Library/Application Support/KMFlowAgent").expanduser()
_BUFFER_DB = str(_BUFFER_DIR / "buffer.db")

# Default retention period
DEFAULT_RETENTION_DAYS = 7

# Run retention check every 24 hours
_CHECK_INTERVAL_SECONDS = 86400


class RetentionEnforcer:
    """Periodically deletes events older than the retention limit."""

    def __init__(
        self,
        db_path: str = _BUFFER_DB,
        retention_days: int = DEFAULT_RETENTION_DAYS,
        audit: AuditLogger | None = None,
    ) -> None:
        self._db_path = db_path
        self._retention_days = retention_days
        self._audit = audit or AuditLogger()

    @property
    def retention_days(self) -> int:
        return self._retention_days

    @retention_days.setter
    def retention_days(self, value: int) -> None:
        if value < 1:
            raise ValueError("Retention days must be >= 1")
        self._retention_days = value

    def enforce_now(self) -> int:
        """Delete events older than retention_days. Returns count deleted."""
        if not Path(self._db_path).exists():
            return 0

        cutoff = datetime.now(UTC).timestamp() - (self._retention_days * 86400)

        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.execute("DELETE FROM events WHERE timestamp < ?", (cutoff,))
            deleted = cursor.rowcount
            conn.commit()
            conn.close()

            if deleted > 0:
                self._audit.log_retention(
                    rows_deleted=deleted,
                    retention_days=self._retention_days,
                )
                logger.info(
                    "Retention enforced: deleted %d events older than %d days",
                    deleted,
                    self._retention_days,
                )
            return deleted
        except sqlite3.Error as exc:
            logger.error("Retention enforcement failed: %s", exc)
            return 0

    async def run(self, shutdown_event: asyncio.Event) -> None:
        """Periodically enforce retention until shutdown."""
        logger.info(
            "Retention enforcer started (retention=%d days)",
            self._retention_days,
        )
        while not shutdown_event.is_set():
            await asyncio.to_thread(self.enforce_now)
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=_CHECK_INTERVAL_SECONDS)
                break
            except TimeoutError:
                pass
        logger.info("Retention enforcer stopped")
