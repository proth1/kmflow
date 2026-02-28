"""Tests for hybrid classification and sequence mining (Story #235)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from src.core.models.taskmining import ActionCategory
from src.taskmining.aggregation.classifier import ClassificationResult
from src.taskmining.aggregation.session import AggregatedSession
from src.taskmining.ml.classifier import MLPrediction
from src.taskmining.ml.hybrid import HybridClassifier
from src.taskmining.ml.sequence_mining import mine_sequences


def _make_session(app: str = "Excel", keyboard: int = 50) -> AggregatedSession:
    start = datetime(2026, 1, 6, 14, 0, 0, tzinfo=UTC)
    return AggregatedSession(
        app_bundle_id=app,
        window_title_sample="Test",
        started_at=start,
        ended_at=start,
        duration_ms=30000,
        active_duration_ms=28000,
        idle_duration_ms=2000,
        keyboard_event_count=keyboard,
        mouse_event_count=10,
        total_event_count=keyboard + 10,
    )


class TestHybridClassifier:
    def test_ml_used_when_confidence_above_threshold(self):
        ml_clf = MagicMock()
        ml_clf.is_trained = True
        ml_clf.predict.return_value = MLPrediction(
            category=ActionCategory.DATA_ENTRY,
            confidence=0.85,
            probabilities={"data_entry": 0.85, "navigation": 0.15},
        )

        rule_clf = MagicMock()

        hybrid = HybridClassifier(ml_classifier=ml_clf, rule_classifier=rule_clf, ml_threshold=0.75)
        result = hybrid.classify(_make_session())

        assert result.source == "ml"
        assert result.category == ActionCategory.DATA_ENTRY
        assert result.confidence == 0.85
        rule_clf.classify.assert_not_called()

    def test_rules_fallback_when_ml_confidence_low(self):
        ml_clf = MagicMock()
        ml_clf.is_trained = True
        ml_clf.predict.return_value = MLPrediction(
            category=ActionCategory.REVIEW,
            confidence=0.45,
            probabilities={"review": 0.45, "navigation": 0.55},
        )

        rule_clf = MagicMock()
        rule_clf.classify.return_value = ClassificationResult(
            category=ActionCategory.DATA_ENTRY,
            confidence=0.85,
            rule_name="data_entry",
            description="Data entry in Excel",
        )

        hybrid = HybridClassifier(ml_classifier=ml_clf, rule_classifier=rule_clf, ml_threshold=0.75)
        result = hybrid.classify(_make_session())

        assert result.source == "rule_based"
        assert result.category == ActionCategory.DATA_ENTRY
        assert result.ml_confidence == 0.45
        assert result.ml_category == "review"

    def test_rules_fallback_when_no_model(self):
        ml_clf = MagicMock()
        ml_clf.is_trained = False
        ml_clf.predict.return_value = None

        rule_clf = MagicMock()
        rule_clf.classify.return_value = ClassificationResult(
            category=ActionCategory.UNKNOWN,
            confidence=0.50,
            rule_name="no_match",
            description="Unclassified",
        )

        hybrid = HybridClassifier(ml_classifier=ml_clf, rule_classifier=rule_clf)
        result = hybrid.classify(_make_session())

        assert result.source == "rule_based"
        assert result.ml_confidence is None

    def test_ml_at_exact_threshold(self):
        ml_clf = MagicMock()
        ml_clf.is_trained = True
        ml_clf.predict.return_value = MLPrediction(
            category=ActionCategory.NAVIGATION,
            confidence=0.75,
            probabilities={"navigation": 0.75},
        )

        hybrid = HybridClassifier(ml_classifier=ml_clf, ml_threshold=0.75)
        result = hybrid.classify(_make_session())

        assert result.source == "ml"

    def test_ml_below_threshold(self):
        ml_clf = MagicMock()
        ml_clf.is_trained = True
        ml_clf.predict.return_value = MLPrediction(
            category=ActionCategory.NAVIGATION,
            confidence=0.74,
            probabilities={"navigation": 0.74},
        )

        rule_clf = MagicMock()
        rule_clf.classify.return_value = ClassificationResult(
            category=ActionCategory.NAVIGATION,
            confidence=0.80,
            rule_name="navigation_url",
            description="Nav",
        )

        hybrid = HybridClassifier(ml_classifier=ml_clf, rule_classifier=rule_clf, ml_threshold=0.75)
        result = hybrid.classify(_make_session())

        assert result.source == "rule_based"

    def test_classify_batch(self):
        ml_clf = MagicMock()
        ml_clf.is_trained = True
        ml_clf.predict.return_value = MLPrediction(
            category=ActionCategory.DATA_ENTRY,
            confidence=0.90,
            probabilities={"data_entry": 0.90},
        )

        hybrid = HybridClassifier(ml_classifier=ml_clf, ml_threshold=0.75)
        results = hybrid.classify_batch([_make_session(), _make_session()])

        assert len(results) == 2
        assert all(r.source == "ml" for r in results)

    def test_ml_available_property(self):
        ml_clf = MagicMock()
        ml_clf.is_trained = True
        hybrid = HybridClassifier(ml_classifier=ml_clf)
        assert hybrid.ml_available is True

        ml_clf.is_trained = False
        assert hybrid.ml_available is False


class TestSequenceMining:
    def test_finds_frequent_bigrams(self):
        sequences = [
            ["data_entry", "navigation", "file_operation"],
            ["data_entry", "navigation", "review"],
            ["data_entry", "navigation", "file_operation"],
            ["communication", "review"],
        ]
        result = mine_sequences(sequences, min_n=2, max_n=2, min_support=2)

        assert result.sessions_analyzed == 4
        # "data_entry, navigation" appears in 3 sessions
        patterns = {p.pattern: p for p in result.patterns}
        assert ("data_entry", "navigation") in patterns
        assert patterns[("data_entry", "navigation")].support == 3

    def test_filters_by_min_support(self):
        sequences = [
            ["a", "b", "c"],
            ["a", "b", "d"],
            ["x", "y", "z"],
        ]
        result = mine_sequences(sequences, min_n=2, max_n=2, min_support=2)

        # Only ("a", "b") should survive
        assert result.total_patterns_found == 1
        assert result.patterns[0].pattern == ("a", "b")

    def test_empty_sequences(self):
        result = mine_sequences([], min_n=2, max_n=3)
        assert result.patterns == []
        assert result.sessions_analyzed == 0

    def test_short_sequences_skipped(self):
        sequences = [["a"], ["b"]]
        result = mine_sequences(sequences, min_n=2, max_n=3, min_support=1)
        assert result.total_patterns_found == 0

    def test_trigrams_extracted(self):
        sequences = [
            ["a", "b", "c", "d"],
            ["a", "b", "c", "e"],
            ["a", "b", "c", "d"],
        ]
        result = mine_sequences(sequences, min_n=3, max_n=3, min_support=2)

        patterns = {p.pattern for p in result.patterns}
        assert ("a", "b", "c") in patterns

    def test_patterns_sorted_by_support_desc(self):
        sequences = [
            ["a", "b", "c"],
            ["a", "b", "d"],
            ["a", "b", "c"],
            ["x", "y"],
            ["x", "y"],
        ]
        result = mine_sequences(sequences, min_n=2, max_n=2, min_support=2)

        # a,b has support 3; x,y has support 2
        assert result.patterns[0].support >= result.patterns[1].support

    def test_frequency_calculated(self):
        sequences = [
            ["a", "b"],
            ["a", "b"],
            ["c", "d"],
            ["c", "d"],
        ]
        result = mine_sequences(sequences, min_n=2, max_n=2, min_support=2)

        for p in result.patterns:
            assert p.frequency == pytest.approx(p.support / 4)

    def test_unique_per_session(self):
        # Same pattern repeated in one session should only count once
        sequences = [
            ["a", "b", "a", "b"],
            ["a", "b"],
        ]
        result = mine_sequences(sequences, min_n=2, max_n=2, min_support=2)

        ab = next((p for p in result.patterns if p.pattern == ("a", "b")), None)
        assert ab is not None
        assert ab.support == 2  # 2 sessions, not 3 occurrences
