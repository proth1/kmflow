"""Tests for the evidence materialization pipeline."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from src.core.models.evidence import EvidenceCategory, ValidationStatus
from src.core.models.taskmining import ActionCategory
from src.taskmining.aggregation.classifier import ClassificationResult
from src.taskmining.aggregation.materializer import (
    TASK_MINING_RELIABILITY_SCORE,
    EvidenceMaterializer,
)
from src.taskmining.aggregation.session import AggregatedSession


def _session(**kwargs) -> AggregatedSession:
    defaults = {
        "app_bundle_id": "com.microsoft.Excel",
        "window_title_sample": "Budget.xlsx",
        "started_at": datetime(2026, 2, 25, 10, 0, tzinfo=timezone.utc),
        "ended_at": datetime(2026, 2, 25, 10, 8, tzinfo=timezone.utc),
        "duration_ms": 480_000,
        "active_duration_ms": 480_000,
        "keyboard_event_count": 150,
        "mouse_event_count": 20,
        "total_event_count": 170,
        "session_id": str(uuid.uuid4()),
        "engagement_id": str(uuid.uuid4()),
    }
    defaults.update(kwargs)
    return AggregatedSession(**defaults)


def _classification(**kwargs) -> ClassificationResult:
    defaults = {
        "category": ActionCategory.DATA_ENTRY,
        "confidence": 0.85,
        "rule_name": "data_entry",
        "description": "Data entry in Excel (150 keystrokes, 480s)",
    }
    defaults.update(kwargs)
    return ClassificationResult(**defaults)


class TestEvidenceMaterialization:
    """Scenario: Completed session is materialized as an EvidenceItem."""

    def test_creates_evidence_item(self):
        materializer = EvidenceMaterializer()
        session = _session()
        classification = _classification()

        item = materializer.materialize_action(session, classification)
        assert item is not None
        assert item.category == EvidenceCategory.KM4WORK
        assert item.format == "task_mining_agent"
        assert item.source_system == "kmflow_task_mining_agent"
        assert item.reliability_score == TASK_MINING_RELIABILITY_SCORE
        assert item.validation_status == ValidationStatus.VALIDATED

    def test_metadata_contains_required_fields(self):
        materializer = EvidenceMaterializer()
        session = _session()
        classification = _classification()
        action_id = uuid.uuid4()

        item = materializer.materialize_action(session, classification, action_id)
        assert item is not None
        meta = item.metadata_json
        assert meta["source"] == "kmflow_task_mining_agent"
        assert meta["action_category"] == "data_entry"
        assert meta["application"] == "com.microsoft.Excel"
        assert meta["event_count"] == 170
        assert meta["keyboard_event_count"] == 150
        assert meta["action_id"] == str(action_id)
        assert meta["description"] is not None

    def test_content_hash_is_set(self):
        materializer = EvidenceMaterializer()
        item = materializer.materialize_action(_session(), _classification())
        assert item is not None
        assert item.content_hash is not None
        assert len(item.content_hash) == 64  # SHA-256 hex

    def test_reliability_score_is_090(self):
        materializer = EvidenceMaterializer()
        item = materializer.materialize_action(_session(), _classification())
        assert item is not None
        assert item.reliability_score == 0.90

    def test_name_contains_category_and_app(self):
        materializer = EvidenceMaterializer()
        item = materializer.materialize_action(_session(), _classification())
        assert item is not None
        assert "data_entry" in item.name
        assert "com.microsoft.Excel" in item.name


class TestSkipConditions:
    """Scenario: Sessions with zero events are not materialized."""

    def test_zero_events_skipped(self):
        materializer = EvidenceMaterializer()
        session = _session(total_event_count=0)
        classification = _classification(category=ActionCategory.UNKNOWN)

        item = materializer.materialize_action(session, classification)
        assert item is None

    def test_no_engagement_id_skipped(self):
        materializer = EvidenceMaterializer()
        session = _session(engagement_id=None)
        classification = _classification()

        item = materializer.materialize_action(session, classification)
        assert item is None


class TestShouldMaterialize:
    """Test the pre-filter check."""

    def test_valid_session_should_materialize(self):
        materializer = EvidenceMaterializer()
        session = _session(total_event_count=50)
        classification = _classification()
        assert materializer.should_materialize(session, classification) is True

    def test_zero_events_should_not_materialize(self):
        materializer = EvidenceMaterializer()
        session = _session(total_event_count=0)
        classification = _classification()
        assert materializer.should_materialize(session, classification) is False

    def test_no_engagement_should_not_materialize(self):
        materializer = EvidenceMaterializer()
        session = _session(engagement_id=None, total_event_count=50)
        classification = _classification()
        assert materializer.should_materialize(session, classification) is False


class TestQualityScores:
    def test_completeness_with_rich_session(self):
        materializer = EvidenceMaterializer()
        session = _session(
            window_title_sample="Budget.xlsx",
            duration_ms=60_000,
            keyboard_event_count=10,
            mouse_event_count=5,
            scroll_count=3,
            copy_paste_count=1,
            total_event_count=19,
        )
        item = materializer.materialize_action(session, _classification())
        assert item is not None
        # Has title (+0.15), >10s (+0.15), 4 types (+0.20) = 0.5+0.5=1.0
        assert item.completeness_score >= 0.80

    def test_completeness_with_minimal_session(self):
        materializer = EvidenceMaterializer()
        session = _session(
            window_title_sample=None,
            duration_ms=5_000,
            keyboard_event_count=3,
            mouse_event_count=0,
            scroll_count=0,
            total_event_count=3,
        )
        item = materializer.materialize_action(session, _classification())
        assert item is not None
        assert item.completeness_score < 0.80

    def test_freshness_recent_is_high(self):
        materializer = EvidenceMaterializer()
        session = _session(ended_at=datetime.now(timezone.utc))
        item = materializer.materialize_action(session, _classification())
        assert item is not None
        assert item.freshness_score >= 0.95

    def test_freshness_old_is_low(self):
        materializer = EvidenceMaterializer()
        from datetime import timedelta
        old = datetime.now(timezone.utc) - timedelta(days=200)
        session = _session(ended_at=old)
        item = materializer.materialize_action(session, _classification())
        assert item is not None
        assert item.freshness_score < 0.50

    def test_consistency_matches_confidence(self):
        materializer = EvidenceMaterializer()
        classification = _classification(confidence=0.92)
        item = materializer.materialize_action(_session(), classification)
        assert item is not None
        assert item.consistency_score == 0.92


class TestBatchMaterialization:
    def test_batch_returns_only_valid_items(self):
        materializer = EvidenceMaterializer()
        sessions = [
            _session(total_event_count=100),
            _session(total_event_count=0),  # Should be skipped
            _session(total_event_count=50),
        ]
        classifications = [
            _classification(),
            _classification(category=ActionCategory.UNKNOWN),
            _classification(),
        ]
        items = materializer.materialize_batch(sessions, classifications)
        assert len(items) == 2


class TestIdempotency:
    def test_same_session_produces_same_content_hash(self):
        materializer = EvidenceMaterializer()
        session = _session()
        classification = _classification()

        item1 = materializer.materialize_action(session, classification)
        item2 = materializer.materialize_action(session, classification)
        assert item1 is not None and item2 is not None
        assert item1.content_hash == item2.content_hash
