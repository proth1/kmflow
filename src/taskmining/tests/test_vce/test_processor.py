"""Tests for VCE backend processor: process_vce_event and process_vce_batch."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models.taskmining import ScreenStateClass, VCETriggerReason, VisualContextEvent
from src.taskmining.vce.processor import process_vce_batch, process_vce_event


def _minimal_event(**overrides) -> dict:
    base = {
        "engagement_id": str(uuid.uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "screen_state_class": "queue",
        "confidence": 0.85,
        "trigger_reason": "high_dwell",
        "application_name": "SAP GUI",
        "dwell_ms": 5000,
    }
    base.update(overrides)
    return base


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


class TestProcessVCEEvent:
    @pytest.mark.asyncio
    async def test_process_vce_event(self, mock_session):
        """Valid event is persisted and returned as a VisualContextEvent."""
        event_data = _minimal_event(
            ocr_text_redacted="Queue screen text",
            window_title_redacted="Work Queue - SAP",
            classification_method="rule_based",
            sensitivity_flags=["email"],
        )

        result = await process_vce_event(mock_session, event_data)

        assert isinstance(result, VisualContextEvent)
        assert result.screen_state_class == ScreenStateClass.QUEUE
        assert result.trigger_reason == VCETriggerReason.HIGH_DWELL
        assert result.application_name == "SAP GUI"
        assert result.dwell_ms == 5000
        assert result.confidence == 0.85
        mock_session.add.assert_called_once_with(result)
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_vce_missing_fields(self, mock_session):
        """Event missing required fields raises ValueError."""
        event_data = {"application_name": "SAP"}  # missing engagement_id, etc.

        with pytest.raises(ValueError, match="Missing required fields"):
            await process_vce_event(mock_session, event_data)

    @pytest.mark.asyncio
    async def test_process_vce_invalid_confidence(self, mock_session):
        """Confidence outside [0, 1] raises ValueError."""
        event_data = _minimal_event(confidence=1.5)

        with pytest.raises(ValueError, match="confidence"):
            await process_vce_event(mock_session, event_data)

    @pytest.mark.asyncio
    async def test_process_vce_invalid_screen_class(self, mock_session):
        """Invalid screen_state_class raises ValueError."""
        event_data = _minimal_event(screen_state_class="invalid_class")

        with pytest.raises(ValueError, match="screen_state_class"):
            await process_vce_event(mock_session, event_data)

    @pytest.mark.asyncio
    async def test_process_vce_optional_fields_nullable(self, mock_session):
        """Optional fields default to None when not provided."""
        event_data = _minimal_event()

        result = await process_vce_event(mock_session, event_data)

        assert result.ocr_text_redacted is None
        assert result.window_title_redacted is None
        assert result.classification_method is None
        assert result.sensitivity_flags is None


class TestProcessVCEBatch:
    @pytest.mark.asyncio
    async def test_process_vce_batch(self, mock_session):
        """Valid batch returns all events accepted."""
        events = [_minimal_event() for _ in range(3)]

        result = await process_vce_batch(mock_session, events)

        assert result["accepted"] == 3
        assert result["rejected"] == 0

    @pytest.mark.asyncio
    async def test_process_vce_batch_partial_failure(self, mock_session):
        """Mixed valid/invalid events — valid ones accepted, invalid rejected."""
        events = [
            _minimal_event(),
            {"invalid": "data"},  # missing required fields
            _minimal_event(),
        ]

        result = await process_vce_batch(mock_session, events)

        assert result["accepted"] == 2
        assert result["rejected"] == 1

    @pytest.mark.asyncio
    async def test_process_vce_missing_fields(self, mock_session):
        """All-invalid batch returns accepted=0."""
        events = [{"bad": "data"}, {"also": "bad"}]

        result = await process_vce_batch(mock_session, events)

        assert result["accepted"] == 0
        assert result["rejected"] == 2
