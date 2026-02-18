"""Tests for the governance SLA breach alerting integration.

Verifies that check_and_alert_sla_breaches creates MonitoringAlert records
when SLA violations are detected, skips passing entries, deduplicates
open alerts, and correctly populates alert fields.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import (
    AlertSeverity,
    AlertStatus,
    DataCatalogEntry,
    DataClassification,
    DataLayer,
    MonitoringJob,
    MonitoringSourceType,
    MonitoringStatus,
)
from src.governance.alerting import (
    _GOVERNANCE_JOB_NAME,
    _make_dedup_key,
    check_and_alert_sla_breaches,
)
from src.governance.quality import SLAResult, SLAViolation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_catalog_entry(
    engagement_id: uuid.UUID,
    quality_sla: dict | None = None,
) -> MagicMock:
    """Build a mock DataCatalogEntry."""
    entry = MagicMock(spec=DataCatalogEntry)
    entry.id = uuid.uuid4()
    entry.dataset_name = f"dataset_{uuid.uuid4().hex[:8]}"
    entry.layer = DataLayer.BRONZE
    entry.classification = DataClassification.INTERNAL
    entry.quality_sla = quality_sla
    entry.engagement_id = engagement_id
    return entry


def _make_monitoring_job(engagement_id: uuid.UUID) -> MagicMock:
    """Build a mock MonitoringJob."""
    job = MagicMock(spec=MonitoringJob)
    job.id = uuid.uuid4()
    job.engagement_id = engagement_id
    job.name = _GOVERNANCE_JOB_NAME
    job.source_type = MonitoringSourceType.FILE_WATCH
    job.status = MonitoringStatus.ACTIVE
    return job


def _make_passing_sla_result(entry_id: uuid.UUID) -> SLAResult:
    return SLAResult(passing=True, violations=[], entry_id=entry_id, evidence_count=0)


def _make_failing_sla_result(
    entry_id: uuid.UUID,
    metric: str = "min_score",
) -> SLAResult:
    violation = SLAViolation(
        metric=metric,
        threshold=0.8,
        actual=0.4,
        message=f"Score too low on {metric}",
    )
    return SLAResult(
        passing=False,
        violations=[violation],
        entry_id=entry_id,
        evidence_count=3,
    )


def _make_session(
    entries: list[Any],
    job_exists: bool = False,
    alert_exists: bool = False,
) -> AsyncMock:
    """Build a mock AsyncSession for alerting tests."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    # Entries query
    entries_result = MagicMock()
    entries_result.scalars.return_value.all.return_value = entries

    # Job lookup
    job_result = MagicMock()
    job_result.scalar_one_or_none.return_value = (
        _make_monitoring_job(uuid.uuid4()) if job_exists else None
    )

    # Alert dedup lookup
    alert_result = MagicMock()
    alert_result.scalar_one_or_none.return_value = (
        MagicMock() if alert_exists else None
    )

    # Provide enough side_effects
    session.execute = AsyncMock(
        side_effect=[entries_result, job_result]
        + [alert_result] * max(len(entries), 1) * 5
    )
    return session


# ---------------------------------------------------------------------------
# _make_dedup_key
# ---------------------------------------------------------------------------


class TestMakeDedupKey:
    """Tests for _make_dedup_key."""

    def test_deterministic_for_same_inputs(self) -> None:
        entry_id = uuid.uuid4()
        key1 = _make_dedup_key(entry_id, "min_score")
        key2 = _make_dedup_key(entry_id, "min_score")
        assert key1 == key2

    def test_different_for_different_metrics(self) -> None:
        entry_id = uuid.uuid4()
        key1 = _make_dedup_key(entry_id, "min_score")
        key2 = _make_dedup_key(entry_id, "min_completeness")
        assert key1 != key2

    def test_different_for_different_entries(self) -> None:
        key1 = _make_dedup_key(uuid.uuid4(), "min_score")
        key2 = _make_dedup_key(uuid.uuid4(), "min_score")
        assert key1 != key2

    def test_returns_string_of_expected_length(self) -> None:
        key = _make_dedup_key(uuid.uuid4(), "min_score")
        assert isinstance(key, str)
        assert len(key) == 32


# ---------------------------------------------------------------------------
# check_and_alert_sla_breaches
# ---------------------------------------------------------------------------


class TestCheckAndAlertSlaBReaches:
    """Tests for check_and_alert_sla_breaches."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_invalid_engagement_id(self) -> None:
        session = AsyncMock()
        result = await check_and_alert_sla_breaches(session, "not-a-uuid")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_catalog_entries(self) -> None:
        engagement_id = str(uuid.uuid4())
        session = _make_session(entries=[])

        result = await check_and_alert_sla_breaches(session, engagement_id)

        assert result == []

    @pytest.mark.asyncio
    async def test_no_alert_when_sla_passing(self) -> None:
        engagement_id = str(uuid.uuid4())
        eng_uuid = uuid.UUID(engagement_id)
        entry = _make_catalog_entry(eng_uuid)
        session = _make_session(entries=[entry], job_exists=True)

        passing_result = _make_passing_sla_result(entry.id)

        with patch(
            "src.governance.alerting.check_quality_sla",
            new=AsyncMock(return_value=passing_result),
        ):
            alerts = await check_and_alert_sla_breaches(session, engagement_id)

        assert alerts == []
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_alert_for_failing_sla(self) -> None:
        engagement_id = str(uuid.uuid4())
        eng_uuid = uuid.UUID(engagement_id)
        entry = _make_catalog_entry(eng_uuid, quality_sla={"min_score": 0.8})
        session = _make_session(entries=[entry], job_exists=True, alert_exists=False)

        failing_result = _make_failing_sla_result(entry.id, "min_score")

        with patch(
            "src.governance.alerting.check_quality_sla",
            new=AsyncMock(return_value=failing_result),
        ):
            alerts = await check_and_alert_sla_breaches(session, engagement_id)

        assert len(alerts) == 1
        session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_alert_fields_are_populated(self) -> None:
        engagement_id = str(uuid.uuid4())
        eng_uuid = uuid.UUID(engagement_id)
        entry = _make_catalog_entry(eng_uuid, quality_sla={"min_score": 0.8})
        session = _make_session(entries=[entry], job_exists=True, alert_exists=False)

        failing_result = _make_failing_sla_result(entry.id, "min_score")

        with patch(
            "src.governance.alerting.check_quality_sla",
            new=AsyncMock(return_value=failing_result),
        ):
            alerts = await check_and_alert_sla_breaches(session, engagement_id)

        assert len(alerts) == 1
        alert = alerts[0]
        assert alert["severity"] == AlertSeverity.MEDIUM.value
        assert alert["status"] == AlertStatus.NEW.value
        assert "min_score" in alert["title"]
        assert alert["violation_metric"] == "min_score"
        assert alert["violation_threshold"] == 0.8
        assert alert["violation_actual"] == 0.4
        assert alert["catalog_entry_id"] == str(entry.id)
        assert alert["catalog_entry_name"] == entry.dataset_name

    @pytest.mark.asyncio
    async def test_dedup_skips_existing_open_alert(self) -> None:
        engagement_id = str(uuid.uuid4())
        eng_uuid = uuid.UUID(engagement_id)
        entry = _make_catalog_entry(eng_uuid, quality_sla={"min_score": 0.8})
        # alert_exists=True means the dedup query returns an existing alert
        session = _make_session(entries=[entry], job_exists=True, alert_exists=True)

        failing_result = _make_failing_sla_result(entry.id, "min_score")

        with patch(
            "src.governance.alerting.check_quality_sla",
            new=AsyncMock(return_value=failing_result),
        ):
            alerts = await check_and_alert_sla_breaches(session, engagement_id)

        assert alerts == []
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_one_alert_per_violation(self) -> None:
        engagement_id = str(uuid.uuid4())
        eng_uuid = uuid.UUID(engagement_id)
        entry = _make_catalog_entry(eng_uuid, quality_sla={"min_score": 0.8})

        # Two violations
        failing_result = SLAResult(
            passing=False,
            violations=[
                SLAViolation("min_score", 0.8, 0.4, "Score too low"),
                SLAViolation("min_completeness", 0.9, 0.5, "Too many unscored"),
            ],
            entry_id=entry.id,
            evidence_count=5,
        )

        # Session needs enough side_effects for two alert dedup queries
        entries_result = MagicMock()
        entries_result.scalars.return_value.all.return_value = [entry]
        job_result = MagicMock()
        job_result.scalar_one_or_none.return_value = _make_monitoring_job(eng_uuid)
        no_alert = MagicMock()
        no_alert.scalar_one_or_none.return_value = None

        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[entries_result, job_result, no_alert, no_alert]
        )

        with patch(
            "src.governance.alerting.check_quality_sla",
            new=AsyncMock(return_value=failing_result),
        ):
            alerts = await check_and_alert_sla_breaches(session, engagement_id)

        assert len(alerts) == 2
        assert session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_creates_governance_job_when_absent(self) -> None:
        engagement_id = str(uuid.uuid4())
        eng_uuid = uuid.UUID(engagement_id)
        entry = _make_catalog_entry(eng_uuid)

        entries_result = MagicMock()
        entries_result.scalars.return_value.all.return_value = [entry]
        # No existing job
        job_result = MagicMock()
        job_result.scalar_one_or_none.return_value = None

        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[entries_result, job_result]
        )

        passing_result = _make_passing_sla_result(entry.id)

        with patch(
            "src.governance.alerting.check_quality_sla",
            new=AsyncMock(return_value=passing_result),
        ):
            await check_and_alert_sla_breaches(session, engagement_id)

        # session.add should have been called to create the governance job
        session.add.assert_called_once()
        # The object added should be a MonitoringJob
        added_obj = session.add.call_args[0][0]
        assert hasattr(added_obj, "name")
        assert added_obj.name == _GOVERNANCE_JOB_NAME

    @pytest.mark.asyncio
    async def test_multiple_entries_mixed_results(self) -> None:
        engagement_id = str(uuid.uuid4())
        eng_uuid = uuid.UUID(engagement_id)
        passing_entry = _make_catalog_entry(eng_uuid)
        failing_entry = _make_catalog_entry(eng_uuid, quality_sla={"min_score": 0.9})

        passing_result = _make_passing_sla_result(passing_entry.id)
        failing_result = _make_failing_sla_result(failing_entry.id, "min_score")

        entries_result = MagicMock()
        entries_result.scalars.return_value.all.return_value = [
            passing_entry, failing_entry
        ]
        job_result = MagicMock()
        job_result.scalar_one_or_none.return_value = _make_monitoring_job(eng_uuid)
        no_alert = MagicMock()
        no_alert.scalar_one_or_none.return_value = None

        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[entries_result, job_result, no_alert, no_alert]
        )

        with patch(
            "src.governance.alerting.check_quality_sla",
            new=AsyncMock(side_effect=[passing_result, failing_result]),
        ):
            alerts = await check_and_alert_sla_breaches(session, engagement_id)

        assert len(alerts) == 1
        assert alerts[0]["catalog_entry_id"] == str(failing_entry.id)
