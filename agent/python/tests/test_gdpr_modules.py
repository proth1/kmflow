"""Tests for agent GDPR compliance modules.

Covers retention enforcement (RetentionEnforcer) which doesn't have
dedicated tests yet. audit_logger and purge are tested in tests/gdpr/.
"""

from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path

import pytest
from kmflow_agent.gdpr.audit_logger import AuditLogger
from kmflow_agent.gdpr.retention import DEFAULT_RETENTION_DAYS, RetentionEnforcer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path, event_count: int = 0, age_seconds: float = 0) -> Path:
    """Create a SQLite event buffer with optional pre-populated rows."""
    db_path = tmp_path / "buffer.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, timestamp REAL, data TEXT)")
    now = time.time()
    for i in range(event_count):
        ts = now - age_seconds - i
        conn.execute("INSERT INTO events (timestamp, data) VALUES (?, ?)", (ts, f"event-{i}"))
    conn.commit()
    conn.close()
    return db_path


def _make_enforcer(tmp_path: Path, retention_days: int = 7) -> RetentionEnforcer:
    audit = AuditLogger(log_path=str(tmp_path / "audit.jsonl"))
    db_path = _make_db(tmp_path)
    return RetentionEnforcer(
        db_path=str(db_path),
        retention_days=retention_days,
        audit=audit,
    )


# ===========================================================================
# RetentionEnforcer basic properties
# ===========================================================================


class TestRetentionEnforcerProperties:
    """RetentionEnforcer has correct default configuration."""

    def test_default_retention_days_is_7(self, tmp_path: Path) -> None:
        enforcer = _make_enforcer(tmp_path)
        assert enforcer.retention_days == DEFAULT_RETENTION_DAYS

    def test_custom_retention_days(self, tmp_path: Path) -> None:
        enforcer = _make_enforcer(tmp_path, retention_days=30)
        assert enforcer.retention_days == 30

    def test_set_retention_days(self, tmp_path: Path) -> None:
        enforcer = _make_enforcer(tmp_path)
        enforcer.retention_days = 14
        assert enforcer.retention_days == 14

    def test_retention_days_below_one_raises(self, tmp_path: Path) -> None:
        enforcer = _make_enforcer(tmp_path)
        with pytest.raises(ValueError, match="Retention days must be >= 1"):
            enforcer.retention_days = 0


# ===========================================================================
# enforce_now
# ===========================================================================


class TestEnforceNow:
    """RetentionEnforcer.enforce_now() deletes expired events."""

    def test_returns_zero_when_db_missing(self, tmp_path: Path) -> None:
        enforcer = RetentionEnforcer(
            db_path=str(tmp_path / "nonexistent.db"),
            retention_days=7,
        )
        assert enforcer.enforce_now() == 0

    def test_no_deletion_when_events_are_fresh(self, tmp_path: Path) -> None:
        """Events within the retention window are not deleted."""
        db_path = _make_db(tmp_path, event_count=5, age_seconds=60)  # 1 minute old
        audit = AuditLogger(log_path=str(tmp_path / "audit.jsonl"))
        enforcer = RetentionEnforcer(
            db_path=str(db_path),
            retention_days=7,
            audit=audit,
        )

        deleted = enforcer.enforce_now()

        assert deleted == 0
        # Verify rows still exist
        conn = sqlite3.connect(str(db_path))
        count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        conn.close()
        assert count == 5

    def test_deletes_events_older_than_retention(self, tmp_path: Path) -> None:
        """Events older than retention_days are deleted."""
        # 8 days old (beyond 7-day window)
        age_seconds = 8 * 86400
        db_path = _make_db(tmp_path, event_count=3, age_seconds=age_seconds)
        audit = AuditLogger(log_path=str(tmp_path / "audit.jsonl"))
        enforcer = RetentionEnforcer(
            db_path=str(db_path),
            retention_days=7,
            audit=audit,
        )

        deleted = enforcer.enforce_now()

        assert deleted == 3
        conn = sqlite3.connect(str(db_path))
        count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        conn.close()
        assert count == 0

    def test_deletes_only_expired_events(self, tmp_path: Path) -> None:
        """Only events older than the cutoff are deleted."""
        db_path = tmp_path / "buffer.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, timestamp REAL, data TEXT)")
        now = time.time()
        # 2 old events (10 days ago)
        for i in range(2):
            conn.execute("INSERT INTO events (timestamp, data) VALUES (?, ?)", (now - 10 * 86400 - i, "old"))
        # 3 fresh events (1 hour ago)
        for i in range(3):
            conn.execute("INSERT INTO events (timestamp, data) VALUES (?, ?)", (now - 3600 + i, "fresh"))
        conn.commit()
        conn.close()

        audit = AuditLogger(log_path=str(tmp_path / "audit.jsonl"))
        enforcer = RetentionEnforcer(
            db_path=str(db_path),
            retention_days=7,
            audit=audit,
        )

        deleted = enforcer.enforce_now()

        assert deleted == 2
        conn = sqlite3.connect(str(db_path))
        count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        conn.close()
        assert count == 3

    def test_audit_log_written_after_deletion(self, tmp_path: Path) -> None:
        """Audit log entry is written when events are deleted."""
        import json

        age_seconds = 10 * 86400
        db_path = _make_db(tmp_path, event_count=2, age_seconds=age_seconds)
        audit_log_path = tmp_path / "audit.jsonl"
        audit = AuditLogger(log_path=str(audit_log_path))
        enforcer = RetentionEnforcer(
            db_path=str(db_path),
            retention_days=7,
            audit=audit,
        )

        enforcer.enforce_now()

        assert audit_log_path.exists()
        entries = [json.loads(line) for line in audit_log_path.read_text().splitlines() if line.strip()]
        assert len(entries) == 1
        assert entries[0]["event"] == "retention_enforcement"
        assert entries[0]["rows_deleted"] == 2
        assert entries[0]["retention_days"] == 7

    def test_no_audit_log_when_nothing_deleted(self, tmp_path: Path) -> None:
        """No audit entry is written when no events are deleted."""
        db_path = _make_db(tmp_path, event_count=2, age_seconds=60)  # fresh
        audit_log_path = tmp_path / "audit.jsonl"
        audit = AuditLogger(log_path=str(audit_log_path))
        enforcer = RetentionEnforcer(
            db_path=str(db_path),
            retention_days=7,
            audit=audit,
        )

        enforcer.enforce_now()

        assert not audit_log_path.exists() or audit_log_path.read_text().strip() == ""


# ===========================================================================
# RetentionEnforcer.run() — async periodic loop
# ===========================================================================


class TestRetentionEnforcerRun:
    """RetentionEnforcer.run() loop exits on shutdown_event."""

    @pytest.mark.asyncio
    async def test_run_stops_on_shutdown(self, tmp_path: Path) -> None:
        """Setting shutdown_event causes run() to exit cleanly."""
        db_path = _make_db(tmp_path)
        audit = AuditLogger(log_path=str(tmp_path / "audit.jsonl"))
        enforcer = RetentionEnforcer(
            db_path=str(db_path),
            retention_days=7,
            audit=audit,
        )

        shutdown = asyncio.Event()

        async def stop() -> None:
            await asyncio.sleep(0.05)
            shutdown.set()

        await asyncio.gather(
            enforcer.run(shutdown),
            stop(),
        )

        assert shutdown.is_set()

    @pytest.mark.asyncio
    async def test_run_calls_enforce_on_each_cycle(self, tmp_path: Path) -> None:
        """enforce_now() is called at least once during the run loop."""
        db_path = _make_db(tmp_path)
        audit = AuditLogger(log_path=str(tmp_path / "audit.jsonl"))
        enforcer = RetentionEnforcer(
            db_path=str(db_path),
            retention_days=7,
            audit=audit,
        )

        enforce_calls = 0
        original_enforce = enforcer.enforce_now

        def counting_enforce() -> int:
            nonlocal enforce_calls
            enforce_calls += 1
            return original_enforce()

        enforcer.enforce_now = counting_enforce  # type: ignore[method-assign]

        shutdown = asyncio.Event()

        async def stop() -> None:
            await asyncio.sleep(0.05)
            shutdown.set()

        await asyncio.gather(
            enforcer.run(shutdown),
            stop(),
        )

        assert enforce_calls >= 1
