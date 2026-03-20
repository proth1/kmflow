"""Tests for GDPR retention enforcement."""

from __future__ import annotations

import asyncio
import sqlite3
import time
from unittest.mock import MagicMock, patch

import pytest
from kmflow_agent.gdpr.retention import DEFAULT_RETENTION_DAYS, RetentionEnforcer


@pytest.fixture
def db_path(tmp_path) -> str:
    """Create a temporary SQLite database with an events table."""
    path = str(tmp_path / "buffer.db")
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, timestamp REAL)")
    conn.commit()
    conn.close()
    return path


def _insert_event(db_path: str, timestamp: float) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO events (timestamp) VALUES (?)", (timestamp,))
    conn.commit()
    conn.close()


def _count_events(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT COUNT(*) FROM events").fetchone()
    conn.close()
    return row[0]


class TestRetentionEnforcer:
    def test_default_retention_days(self) -> None:
        enforcer = RetentionEnforcer()
        assert enforcer.retention_days == DEFAULT_RETENTION_DAYS

    def test_enforce_now_deletes_expired_records(self, db_path: str) -> None:
        now = time.time()
        expired_ts = now - (8 * 86400)  # 8 days ago, beyond 7-day retention
        _insert_event(db_path, expired_ts)

        enforcer = RetentionEnforcer(db_path=db_path, retention_days=7)
        deleted = enforcer.enforce_now()

        assert deleted == 1
        assert _count_events(db_path) == 0

    def test_enforce_now_preserves_non_expired_records(self, db_path: str) -> None:
        now = time.time()
        recent_ts = now - (3 * 86400)  # 3 days ago, within 7-day retention
        _insert_event(db_path, recent_ts)

        enforcer = RetentionEnforcer(db_path=db_path, retention_days=7)
        deleted = enforcer.enforce_now()

        assert deleted == 0
        assert _count_events(db_path) == 1

    def test_enforce_now_mixed_records(self, db_path: str) -> None:
        now = time.time()
        _insert_event(db_path, now - (10 * 86400))  # expired
        _insert_event(db_path, now - (5 * 86400))  # not expired
        _insert_event(db_path, now - (1 * 86400))  # not expired

        enforcer = RetentionEnforcer(db_path=db_path, retention_days=7)
        deleted = enforcer.enforce_now()

        assert deleted == 1
        assert _count_events(db_path) == 2

    def test_enforce_now_returns_zero_when_db_missing(self, tmp_path) -> None:
        enforcer = RetentionEnforcer(db_path=str(tmp_path / "nonexistent.db"))
        assert enforcer.enforce_now() == 0

    def test_enforce_now_calls_audit_logger_on_deletion(self, db_path: str) -> None:
        now = time.time()
        _insert_event(db_path, now - (10 * 86400))

        mock_audit = MagicMock()
        enforcer = RetentionEnforcer(db_path=db_path, retention_days=7, audit=mock_audit)
        enforcer.enforce_now()

        mock_audit.log_retention.assert_called_once_with(rows_deleted=1, retention_days=7)

    def test_enforce_now_skips_audit_when_nothing_deleted(self, db_path: str) -> None:
        mock_audit = MagicMock()
        enforcer = RetentionEnforcer(db_path=db_path, retention_days=7, audit=mock_audit)
        enforcer.enforce_now()

        mock_audit.log_retention.assert_not_called()

    def test_retention_days_setter_rejects_zero(self) -> None:
        enforcer = RetentionEnforcer()
        with pytest.raises(ValueError, match="Retention days must be >= 1"):
            enforcer.retention_days = 0

    def test_retention_days_setter_rejects_negative(self) -> None:
        enforcer = RetentionEnforcer()
        with pytest.raises(ValueError):
            enforcer.retention_days = -1

    def test_retention_days_setter_accepts_valid_value(self) -> None:
        enforcer = RetentionEnforcer()
        enforcer.retention_days = 30
        assert enforcer.retention_days == 30

    @pytest.mark.asyncio
    async def test_run_stops_on_shutdown_event(self, db_path: str) -> None:
        enforcer = RetentionEnforcer(db_path=db_path, retention_days=7)
        shutdown = asyncio.Event()
        shutdown.set()  # Signal shutdown immediately

        # Should return without hanging
        await asyncio.wait_for(enforcer.run(shutdown), timeout=2.0)

    @pytest.mark.asyncio
    async def test_run_calls_enforce_now(self, db_path: str) -> None:
        enforcer = RetentionEnforcer(db_path=db_path, retention_days=7)
        shutdown = asyncio.Event()

        with patch.object(enforcer, "enforce_now", wraps=enforcer.enforce_now) as mock_enforce:
            shutdown.set()
            await asyncio.wait_for(enforcer.run(shutdown), timeout=2.0)

        mock_enforce.assert_called_once()
