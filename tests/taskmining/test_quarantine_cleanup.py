"""Tests for PII quarantine auto-cleanup job.

Story #212 — Part of Epic #210 (Privacy and Compliance).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models.taskmining import PIIQuarantine, PIIType, QuarantineStatus
from src.taskmining.jobs.quarantine_cleanup import (
    _CLEANUP_STATUSES,
    count_expired,
    run_quarantine_cleanup,
)


def _quarantine_record(
    *,
    hours_until_delete: float = -1.0,
    status: QuarantineStatus = QuarantineStatus.PENDING_REVIEW,
    now: datetime | None = None,
) -> PIIQuarantine:
    """Build a quarantine record with a relative auto_delete_at."""
    if now is None:
        now = datetime.now(UTC)
    return PIIQuarantine(
        id=uuid.uuid4(),
        engagement_id=uuid.uuid4(),
        original_event_data={"window_title": "[PII_REDACTED]"},
        pii_type=PIIType.SSN,
        pii_field="window_title",
        detection_confidence=0.95,
        status=status,
        auto_delete_at=now + timedelta(hours=hours_until_delete),
    )


class TestCleanupStatuses:
    """Verify which statuses are eligible for cleanup."""

    def test_pending_review_eligible(self) -> None:
        assert QuarantineStatus.PENDING_REVIEW in _CLEANUP_STATUSES

    def test_deleted_eligible(self) -> None:
        assert QuarantineStatus.DELETED in _CLEANUP_STATUSES

    def test_released_eligible(self) -> None:
        assert QuarantineStatus.RELEASED in _CLEANUP_STATUSES

    def test_auto_deleted_not_eligible(self) -> None:
        assert QuarantineStatus.AUTO_DELETED not in _CLEANUP_STATUSES


class TestCleanupJobUnit:
    """Unit tests for the cleanup job using mocked DB session."""

    @pytest.mark.asyncio
    async def test_returns_summary_dict(self) -> None:
        """Cleanup returns rows_deleted, run_at, duration_ms."""
        session = AsyncMock()
        delete_result = MagicMock()
        delete_result.rowcount = 0
        session.execute.return_value = delete_result

        summary = await run_quarantine_cleanup(session)
        assert "rows_deleted" in summary
        assert "run_at" in summary
        assert "duration_ms" in summary
        assert summary["rows_deleted"] == 0

    @pytest.mark.asyncio
    async def test_idempotent_no_expired(self) -> None:
        """Running twice with no expired records deletes 0 both times."""
        session = AsyncMock()
        delete_result = MagicMock()
        delete_result.rowcount = 0
        session.execute.return_value = delete_result

        r1 = await run_quarantine_cleanup(session)
        r2 = await run_quarantine_cleanup(session)
        assert r1["rows_deleted"] == 0
        assert r2["rows_deleted"] == 0

    @pytest.mark.asyncio
    async def test_deletes_expired_records(self) -> None:
        """Expired records are deleted when found."""
        session = AsyncMock()
        delete_result = MagicMock()
        delete_result.rowcount = 3
        session.execute.return_value = delete_result

        summary = await run_quarantine_cleanup(session)
        assert summary["rows_deleted"] == 3
        # Single atomic DELETE + flush
        assert session.execute.call_count == 1
        assert session.flush.call_count == 1

    @pytest.mark.asyncio
    async def test_custom_now_parameter(self) -> None:
        """The `now` parameter controls which records are considered expired."""
        session = AsyncMock()
        delete_result = MagicMock()
        delete_result.rowcount = 0
        session.execute.return_value = delete_result

        custom_now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
        summary = await run_quarantine_cleanup(session, now=custom_now)
        assert summary["run_at"] == custom_now.isoformat()

    @pytest.mark.asyncio
    async def test_duration_is_positive(self) -> None:
        """Duration should always be non-negative."""
        session = AsyncMock()
        delete_result = MagicMock()
        delete_result.rowcount = 0
        session.execute.return_value = delete_result

        summary = await run_quarantine_cleanup(session)
        assert summary["duration_ms"] >= 0


class TestCountExpired:
    """Tests for the count_expired helper."""

    @pytest.mark.asyncio
    async def test_returns_zero_when_none(self) -> None:
        session = AsyncMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        session.execute.return_value = count_result

        count = await count_expired(session)
        assert count == 0

    @pytest.mark.asyncio
    async def test_returns_count(self) -> None:
        session = AsyncMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 5
        session.execute.return_value = count_result

        count = await count_expired(session)
        assert count == 5
