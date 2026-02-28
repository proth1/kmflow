"""Tests for VCE analytics: distribution, trigger summary, dwell analysis."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.taskmining.vce.analytics import (
    get_dwell_analysis,
    get_trigger_summary,
    get_vce_distribution,
)


def _make_row(screen_state_class: str, count: int):
    row = MagicMock()
    row.screen_state_class = screen_state_class
    row.count = count
    return row


def _make_trigger_row(trigger_reason: str, count: int, avg_confidence: float):
    row = MagicMock()
    row.trigger_reason = trigger_reason
    row.count = count
    row.avg_confidence = avg_confidence
    return row


@pytest.fixture
def mock_session():
    session = AsyncMock()
    return session


class TestVCEDistribution:
    @pytest.mark.asyncio
    async def test_vce_distribution(self, mock_session):
        """Distribution returns correct counts and percentages."""
        rows = [_make_row("queue", 60), _make_row("error", 40)]
        result_mock = MagicMock()
        result_mock.all.return_value = rows
        mock_session.execute.return_value = result_mock

        engagement_id = uuid.uuid4()
        result = await get_vce_distribution(mock_session, engagement_id)

        assert result["total"] == 100
        distributions = {d["screen_state_class"]: d for d in result["distributions"]}
        assert distributions["queue"]["count"] == 60
        assert distributions["queue"]["percentage"] == 60.0
        assert distributions["error"]["count"] == 40
        assert distributions["error"]["percentage"] == 40.0

    @pytest.mark.asyncio
    async def test_vce_distribution_empty(self, mock_session):
        """Empty result set returns total=0 and empty distributions."""
        result_mock = MagicMock()
        result_mock.all.return_value = []
        mock_session.execute.return_value = result_mock

        result = await get_vce_distribution(mock_session, uuid.uuid4())

        assert result["total"] == 0
        assert result["distributions"] == []


class TestTriggerSummary:
    @pytest.mark.asyncio
    async def test_trigger_summary(self, mock_session):
        """Trigger summary returns correct trigger_reason counts and avg_confidence."""
        rows = [
            _make_trigger_row("high_dwell", 50, 0.80),
            _make_trigger_row("low_confidence", 20, 0.45),
        ]
        result_mock = MagicMock()
        result_mock.all.return_value = rows
        mock_session.execute.return_value = result_mock

        result = await get_trigger_summary(mock_session, uuid.uuid4())

        assert len(result["triggers"]) == 2
        by_reason = {t["trigger_reason"]: t for t in result["triggers"]}
        assert by_reason["high_dwell"]["count"] == 50
        assert abs(by_reason["high_dwell"]["avg_confidence"] - 0.80) < 0.001
        assert by_reason["low_confidence"]["count"] == 20


class TestDwellAnalysis:
    @pytest.mark.asyncio
    async def test_dwell_analysis(self, mock_session):
        """Dwell analysis returns per_app and per_class with correct statistics."""
        rows = [
            MagicMock(application_name="SAP GUI", screen_state_class="queue", dwell_ms=4000),
            MagicMock(application_name="SAP GUI", screen_state_class="queue", dwell_ms=6000),
            MagicMock(application_name="Excel", screen_state_class="data_entry", dwell_ms=3000),
        ]
        result_mock = MagicMock()
        result_mock.all.return_value = rows
        mock_session.execute.return_value = result_mock

        result = await get_dwell_analysis(mock_session, uuid.uuid4())

        assert "per_app" in result
        assert "per_class" in result

        per_app = {entry["application_name"]: entry for entry in result["per_app"]}
        assert "SAP GUI" in per_app
        assert per_app["SAP GUI"]["avg"] == 5000.0
        assert per_app["SAP GUI"]["count"] == 2

        per_class = {entry["screen_state_class"]: entry for entry in result["per_class"]}
        assert "queue" in per_class
        assert "data_entry" in per_class
