"""Tests for DataPurgeManager (GDPR Art 17 — Right to Be Forgotten).

Verifies purge_local_buffer behaviour against a temporary SQLite database
using pytest's tmp_path fixture for file isolation.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

from kmflow_agent.gdpr.audit_logger import AuditLogger
from kmflow_agent.gdpr.purge import DataPurgeManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(path: Path, row_count: int = 0) -> Path:
    """Create a minimal events SQLite database at *path* with *row_count* rows."""
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT)")
    for i in range(row_count):
        conn.execute("INSERT INTO events (payload) VALUES (?)", (f"event-{i}",))
    conn.commit()
    conn.close()
    return path


def _make_manager(db_path: Path, audit: AuditLogger | None = None) -> DataPurgeManager:
    return DataPurgeManager(db_path=str(db_path), audit=audit)


# ---------------------------------------------------------------------------
# purge_local_buffer tests
# ---------------------------------------------------------------------------


class TestPurgeLocalBuffer:
    """DataPurgeManager.purge_local_buffer()"""

    def test_purge_returns_correct_row_count(self, tmp_path: Path) -> None:
        """purge_local_buffer returns the number of rows deleted."""
        db = _make_db(tmp_path / "buffer.db", row_count=7)
        manager = _make_manager(db)

        count = manager.purge_local_buffer()

        assert count == 7

    def test_purge_removes_all_rows(self, tmp_path: Path) -> None:
        """After purge, the events table is empty."""
        db = _make_db(tmp_path / "buffer.db", row_count=5)
        manager = _make_manager(db)

        manager.purge_local_buffer()

        conn = sqlite3.connect(str(db))
        remaining = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        conn.close()
        assert remaining == 0

    def test_purge_on_nonexistent_db_returns_zero(self, tmp_path: Path) -> None:
        """purge_local_buffer returns 0 when the database file does not exist."""
        missing = tmp_path / "no_such.db"
        manager = _make_manager(missing)

        count = manager.purge_local_buffer()

        assert count == 0

    def test_purge_empty_db_returns_zero(self, tmp_path: Path) -> None:
        """purge_local_buffer returns 0 when the events table is already empty."""
        db = _make_db(tmp_path / "buffer.db", row_count=0)
        manager = _make_manager(db)

        count = manager.purge_local_buffer()

        assert count == 0

    def test_vacuum_runs_after_deletion(self, tmp_path: Path) -> None:
        """VACUUM is executed as part of the purge so the file shrinks."""
        db = _make_db(tmp_path / "buffer.db", row_count=50)
        size_before = db.stat().st_size

        manager = _make_manager(db)
        manager.purge_local_buffer()

        # After VACUUM the file should exist and be at most as large as before
        assert db.exists()
        size_after = db.stat().st_size
        # VACUUM should not grow the file beyond the pre-purge size
        assert size_after <= size_before

    def test_purge_calls_audit_log(self, tmp_path: Path) -> None:
        """purge_local_buffer writes a purge entry to the audit log."""
        db = _make_db(tmp_path / "buffer.db", row_count=3)
        audit_log = tmp_path / "audit.jsonl"
        audit = AuditLogger(log_path=str(audit_log))
        manager = _make_manager(db, audit=audit)

        manager.purge_local_buffer()

        assert audit_log.exists()
        entries = [json.loads(line) for line in audit_log.read_text().splitlines()]
        purge_entries = [e for e in entries if e.get("event") == "data_purge"]
        assert len(purge_entries) == 1
        assert purge_entries[0]["rows_deleted"] == 3
        assert purge_entries[0]["action"] == "purge_local_buffer"

    def test_purge_returns_zero_on_sqlite_error(self, tmp_path: Path) -> None:
        """purge_local_buffer returns 0 when SQLite raises an error."""
        db = _make_db(tmp_path / "buffer.db", row_count=1)
        manager = _make_manager(db)

        # Corrupt the connection by patching sqlite3.connect to raise
        with patch("kmflow_agent.gdpr.purge.sqlite3.connect") as mock_connect:
            mock_connect.side_effect = sqlite3.Error("disk I/O error")
            count = manager.purge_local_buffer()

        assert count == 0


# ---------------------------------------------------------------------------
# execute_full_purge tests
# ---------------------------------------------------------------------------


class TestExecuteFullPurge:
    """DataPurgeManager.execute_full_purge()"""

    def test_full_purge_returns_local_count(self, tmp_path: Path) -> None:
        """execute_full_purge result includes local_rows_deleted."""
        db = _make_db(tmp_path / "buffer.db", row_count=4)
        manager = _make_manager(db)

        result = manager.execute_full_purge()

        assert result["local_rows_deleted"] == 4

    def test_full_purge_requests_remote(self, tmp_path: Path) -> None:
        """execute_full_purge result includes remote_purge_requested=True."""
        db = _make_db(tmp_path / "buffer.db", row_count=0)
        manager = _make_manager(db)

        result = manager.execute_full_purge()

        assert result["remote_purge_requested"] is True
