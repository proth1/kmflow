"""Tests for the action classification rules engine."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.core.models.taskmining import ActionCategory
from src.taskmining.aggregation.classifier import ActionClassifier, ClassificationResult
from src.taskmining.aggregation.session import AggregatedSession


def _session(**kwargs) -> AggregatedSession:
    """Helper: build a session with defaults."""
    defaults = {
        "app_bundle_id": "com.test.app",
        "window_title_sample": "Test Window",
        "started_at": datetime(2026, 2, 25, 10, 0, tzinfo=timezone.utc),
        "ended_at": datetime(2026, 2, 25, 10, 8, tzinfo=timezone.utc),
        "duration_ms": 480_000,
        "active_duration_ms": 480_000,
        "keyboard_event_count": 0,
        "mouse_event_count": 0,
        "copy_paste_count": 0,
        "scroll_count": 0,
        "file_operation_count": 0,
        "url_navigation_count": 0,
        "total_event_count": 0,
        "session_id": "test-session",
        "engagement_id": "test-engagement",
    }
    defaults.update(kwargs)
    return AggregatedSession(**defaults)


class TestDataEntryClassification:
    def test_high_keyboard_classified_as_data_entry(self):
        classifier = ActionClassifier()
        session = _session(
            app_bundle_id="com.microsoft.Excel",
            keyboard_event_count=150,
            mouse_event_count=20,
            total_event_count=170,
        )
        result = classifier.classify(session)
        assert result.category == ActionCategory.DATA_ENTRY
        assert result.confidence >= 0.80

    def test_keyboard_below_threshold_not_data_entry(self):
        classifier = ActionClassifier()
        session = _session(
            keyboard_event_count=10,
            mouse_event_count=50,
            total_event_count=60,
        )
        result = classifier.classify(session)
        assert result.category != ActionCategory.DATA_ENTRY


class TestFileOperationClassification:
    def test_file_heavy_session(self):
        classifier = ActionClassifier()
        session = _session(
            file_operation_count=8,
            keyboard_event_count=20,
            total_event_count=28,
        )
        result = classifier.classify(session)
        assert result.category == ActionCategory.FILE_OPERATION

    def test_few_file_ops_not_classified(self):
        classifier = ActionClassifier()
        session = _session(
            file_operation_count=1,
            keyboard_event_count=100,
            total_event_count=101,
        )
        result = classifier.classify(session)
        assert result.category != ActionCategory.FILE_OPERATION


class TestNavigationClassification:
    def test_url_navigation_session(self):
        classifier = ActionClassifier()
        session = _session(
            app_bundle_id="com.google.Chrome",
            url_navigation_count=12,
            keyboard_event_count=5,
            total_event_count=17,
        )
        result = classifier.classify(session)
        assert result.category == ActionCategory.NAVIGATION

    def test_scroll_heavy_session(self):
        classifier = ActionClassifier()
        session = _session(
            scroll_count=25,
            keyboard_event_count=3,
            total_event_count=28,
        )
        result = classifier.classify(session)
        assert result.category == ActionCategory.NAVIGATION


class TestCommunicationClassification:
    def test_outlook_classified_as_communication(self):
        classifier = ActionClassifier()
        session = _session(
            app_bundle_id="Outlook",
            keyboard_event_count=40,
            total_event_count=50,
        )
        result = classifier.classify(session)
        assert result.category == ActionCategory.COMMUNICATION
        assert result.confidence >= 0.90

    def test_slack_classified_as_communication(self):
        classifier = ActionClassifier()
        session = _session(
            app_bundle_id="Slack",
            total_event_count=10,
        )
        result = classifier.classify(session)
        assert result.category == ActionCategory.COMMUNICATION


class TestReviewClassification:
    def test_review_pattern(self):
        classifier = ActionClassifier()
        session = _session(
            scroll_count=20,
            keyboard_event_count=5,
            copy_paste_count=4,
            total_event_count=29,
        )
        result = classifier.classify(session)
        assert result.category == ActionCategory.REVIEW


class TestUnknownFallback:
    def test_no_match_returns_unknown(self):
        classifier = ActionClassifier()
        session = _session(
            keyboard_event_count=3,
            mouse_event_count=2,
            total_event_count=5,
        )
        result = classifier.classify(session)
        assert result.category == ActionCategory.UNKNOWN
        assert result.rule_name == "no_match"

    def test_empty_session_returns_unknown(self):
        classifier = ActionClassifier()
        session = _session(total_event_count=0)
        result = classifier.classify(session)
        assert result.category == ActionCategory.UNKNOWN
        assert result.rule_name == "empty_session"


class TestYAMLConfig:
    def test_load_from_yaml(self, tmp_path):
        config = tmp_path / "rules.yaml"
        config.write_text("""
rules:
  - name: custom_rule
    category: data_entry
    confidence: 0.95
    conditions:
      keyboard_event_count_min: 10
      keyboard_ratio_min: 0.30
""")
        classifier = ActionClassifier.from_yaml(config)
        session = _session(
            keyboard_event_count=20,
            total_event_count=30,
        )
        result = classifier.classify(session)
        assert result.category == ActionCategory.DATA_ENTRY
        assert result.confidence == 0.95
        assert result.rule_name == "custom_rule"


class TestClassifyBatch:
    def test_batch_classification(self):
        classifier = ActionClassifier()
        sessions = [
            _session(
                app_bundle_id="Outlook",
                total_event_count=10,
            ),
            _session(
                keyboard_event_count=100,
                total_event_count=100,
            ),
        ]
        results = classifier.classify_batch(sessions)
        assert len(results) == 2
        assert results[0].category == ActionCategory.COMMUNICATION
        assert results[1].category == ActionCategory.DATA_ENTRY
