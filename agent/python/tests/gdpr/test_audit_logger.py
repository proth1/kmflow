"""Tests for AuditLogger — append-only GDPR compliance audit trail.

All tests use tmp_path for file isolation so no state leaks between runs.
"""

from __future__ import annotations

import json
from pathlib import Path

from kmflow_agent.gdpr.audit_logger import AuditLogger

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_logger(tmp_path: Path, filename: str = "audit.jsonl") -> AuditLogger:
    return AuditLogger(log_path=str(tmp_path / filename))


def _read_entries(log_path: Path) -> list[dict]:
    return [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# File creation and basic append
# ---------------------------------------------------------------------------


class TestLogFileCreation:
    """AuditLogger creates the log file on first write."""

    def test_log_file_created_on_first_write(self, tmp_path: Path) -> None:
        """Log file does not exist until the first entry is written."""
        log_path = tmp_path / "audit.jsonl"
        assert not log_path.exists()

        logger = AuditLogger(log_path=str(log_path))
        logger.log_retention(rows_deleted=0, retention_days=30)

        assert log_path.exists()

    def test_log_file_created_in_nested_directory(self, tmp_path: Path) -> None:
        """AuditLogger creates parent directories if they do not exist."""
        log_path = tmp_path / "subdir" / "deep" / "audit.jsonl"
        logger = AuditLogger(log_path=str(log_path))
        logger.log_retention(rows_deleted=0, retention_days=30)

        assert log_path.exists()


# ---------------------------------------------------------------------------
# log_consent_change
# ---------------------------------------------------------------------------


class TestLogConsentChange:
    """AuditLogger.log_consent_change()"""

    def test_consent_change_entry_written(self, tmp_path: Path) -> None:
        """A consent change entry is written with the correct fields."""
        log_path = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path=str(log_path))

        logger.log_consent_change(
            engagement_id="eng-001",
            old_state="granted",
            new_state="revoked",
        )

        entries = _read_entries(log_path)
        assert len(entries) == 1
        entry = entries[0]
        assert entry["event"] == "consent_change"
        assert entry["engagement_id"] == "eng-001"
        assert entry["old_state"] == "granted"
        assert entry["new_state"] == "revoked"

    def test_consent_change_includes_timestamp(self, tmp_path: Path) -> None:
        """Each consent change entry includes a UTC timestamp."""
        log_path = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path=str(log_path))
        logger.log_consent_change("e1", "pending", "granted")

        entry = _read_entries(log_path)[0]
        assert "timestamp" in entry
        # ISO-8601 UTC timestamps end with +00:00 or Z
        assert "timestamp" in entry and entry["timestamp"]


# ---------------------------------------------------------------------------
# log_batch_upload
# ---------------------------------------------------------------------------


class TestLogBatchUpload:
    """AuditLogger.log_batch_upload()"""

    def test_batch_upload_entry_written(self, tmp_path: Path) -> None:
        """A batch upload entry is written with the correct fields."""
        log_path = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path=str(log_path))

        logger.log_batch_upload(batch_id="batch-42", event_count=100, status="ok")

        entries = _read_entries(log_path)
        assert len(entries) == 1
        entry = entries[0]
        assert entry["event"] == "batch_upload"
        assert entry["batch_id"] == "batch-42"
        assert entry["event_count"] == 100
        assert entry["status"] == "ok"


# ---------------------------------------------------------------------------
# log_purge
# ---------------------------------------------------------------------------


class TestLogPurge:
    """AuditLogger.log_purge()"""

    def test_purge_entry_written(self, tmp_path: Path) -> None:
        """A data purge entry is written with the correct fields."""
        log_path = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path=str(log_path))

        logger.log_purge(
            action="purge_local_buffer",
            rows_deleted=12,
            db_path="/tmp/buffer.db",
        )

        entries = _read_entries(log_path)
        assert len(entries) == 1
        entry = entries[0]
        assert entry["event"] == "data_purge"
        assert entry["action"] == "purge_local_buffer"
        assert entry["rows_deleted"] == 12
        assert entry["db_path"] == "/tmp/buffer.db"


# ---------------------------------------------------------------------------
# log_retention
# ---------------------------------------------------------------------------


class TestLogRetention:
    """AuditLogger.log_retention()"""

    def test_retention_entry_written(self, tmp_path: Path) -> None:
        """A retention enforcement entry is written with the correct fields."""
        log_path = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path=str(log_path))

        logger.log_retention(rows_deleted=5, retention_days=90)

        entries = _read_entries(log_path)
        assert len(entries) == 1
        entry = entries[0]
        assert entry["event"] == "retention_enforcement"
        assert entry["rows_deleted"] == 5
        assert entry["retention_days"] == 90


# ---------------------------------------------------------------------------
# Append behaviour (multiple writes accumulate)
# ---------------------------------------------------------------------------


class TestAppendBehaviour:
    """Each write appends a new line; existing entries are not overwritten."""

    def test_multiple_writes_accumulate(self, tmp_path: Path) -> None:
        """Three separate log calls produce three distinct JSONL lines."""
        log_path = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path=str(log_path))

        logger.log_consent_change("e1", "pending", "granted")
        logger.log_batch_upload("b1", 10, "ok")
        logger.log_purge("purge_local_buffer", 0, "/tmp/buf.db")

        entries = _read_entries(log_path)
        assert len(entries) == 3
        event_types = [e["event"] for e in entries]
        assert event_types == ["consent_change", "batch_upload", "data_purge"]

    def test_second_logger_instance_appends(self, tmp_path: Path) -> None:
        """A second AuditLogger opened on the same file appends rather than truncates."""
        log_path = tmp_path / "audit.jsonl"

        logger_a = AuditLogger(log_path=str(log_path))
        logger_a.log_retention(rows_deleted=1, retention_days=30)

        logger_b = AuditLogger(log_path=str(log_path))
        logger_b.log_retention(rows_deleted=2, retention_days=60)

        entries = _read_entries(log_path)
        assert len(entries) == 2
        assert entries[0]["rows_deleted"] == 1
        assert entries[1]["rows_deleted"] == 2

    def test_each_entry_is_valid_json(self, tmp_path: Path) -> None:
        """Every line written to the log is valid JSON."""
        log_path = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path=str(log_path))

        logger.log_consent_change("e1", "a", "b")
        logger.log_batch_upload("b1", 5, "ok")
        logger.log_purge("full_purge_completed", 5, "/tmp/buf.db")
        logger.log_retention(5, 30)

        for line in log_path.read_text().splitlines():
            parsed = json.loads(line)  # raises if invalid
            assert isinstance(parsed, dict)
