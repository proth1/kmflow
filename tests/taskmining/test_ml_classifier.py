"""Tests for gradient boosting task classifier (Story #234)."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone

import pytest

from src.core.models.taskmining import ActionCategory
from src.taskmining.aggregation.session import AggregatedSession
from src.taskmining.ml.classifier import GradientBoostingTaskClassifier, TrainingMetrics
from src.taskmining.ml.dataset import LabeledSample, TrainingDataset
from src.taskmining.ml.features import FEATURE_NAMES, extract_features


def _make_session(
    app: str = "Excel",
    keyboard: int = 50,
    mouse: int = 30,
    scroll: int = 0,
    file_ops: int = 0,
    url_nav: int = 0,
    copy_paste: int = 0,
) -> AggregatedSession:
    start = datetime(2026, 1, 6, 14, 0, 0, tzinfo=timezone.utc)
    total = keyboard + mouse + scroll + file_ops + url_nav + copy_paste
    return AggregatedSession(
        app_bundle_id=app,
        window_title_sample="Test",
        started_at=start,
        ended_at=start,
        duration_ms=30000,
        active_duration_ms=28000,
        idle_duration_ms=2000,
        keyboard_event_count=keyboard,
        mouse_event_count=mouse,
        copy_paste_count=copy_paste,
        scroll_count=scroll,
        file_operation_count=file_ops,
        url_navigation_count=url_nav,
        total_event_count=total,
    )


def _build_training_dataset(n_per_class: int = 15) -> TrainingDataset:
    """Build a synthetic dataset with clear class separation."""
    ds = TrainingDataset()

    # Data entry: high keyboard
    for i in range(n_per_class):
        session = _make_session(keyboard=50 + i, mouse=5, app="Excel")
        ds.add_sample(LabeledSample(
            features=extract_features(session),
            label="data_entry",
        ))

    # Navigation: high scroll + URL
    for i in range(n_per_class):
        session = _make_session(keyboard=3, mouse=10, scroll=20 + i, url_nav=5, app="Chrome")
        ds.add_sample(LabeledSample(
            features=extract_features(session),
            label="navigation",
        ))

    # Review: scroll + copy_paste, low keyboard
    for i in range(n_per_class):
        session = _make_session(keyboard=2, mouse=5, scroll=15 + i, copy_paste=3, app="Chrome")
        ds.add_sample(LabeledSample(
            features=extract_features(session),
            label="review",
        ))

    # File operation: high file ops
    for i in range(n_per_class):
        session = _make_session(keyboard=10, mouse=5, file_ops=5 + i, app="Excel")
        ds.add_sample(LabeledSample(
            features=extract_features(session),
            label="file_operation",
        ))

    return ds


class TestClassifierTraining:
    def test_train_produces_metrics(self):
        ds = _build_training_dataset(n_per_class=15)
        clf = GradientBoostingTaskClassifier()

        metrics = clf.train(ds)

        assert isinstance(metrics, TrainingMetrics)
        assert 0.0 <= metrics.accuracy <= 1.0
        assert 0.0 <= metrics.weighted_f1 <= 1.0
        assert metrics.sample_count == ds.size
        assert len(metrics.per_class) > 0

    def test_train_too_few_samples_raises(self):
        ds = TrainingDataset()
        for i in range(5):
            ds.add_sample(LabeledSample(features=[float(i)] * len(FEATURE_NAMES), label="data_entry"))

        clf = GradientBoostingTaskClassifier()
        with pytest.raises(ValueError, match="at least 10"):
            clf.train(ds)

    def test_is_trained_after_training(self):
        ds = _build_training_dataset()
        clf = GradientBoostingTaskClassifier()

        assert not clf.is_trained
        clf.train(ds)
        assert clf.is_trained


class TestClassifierPrediction:
    @pytest.fixture
    def trained_clf(self) -> GradientBoostingTaskClassifier:
        ds = _build_training_dataset(n_per_class=15)
        clf = GradientBoostingTaskClassifier()
        clf.train(ds)
        return clf

    def test_predict_returns_ml_prediction(self, trained_clf):
        session = _make_session(keyboard=60, mouse=5, app="Excel")
        prediction = trained_clf.predict(session)

        assert prediction is not None
        assert isinstance(prediction.category, ActionCategory)
        assert 0.0 <= prediction.confidence <= 1.0
        assert isinstance(prediction.probabilities, dict)

    def test_predict_confidence_is_calibrated(self, trained_clf):
        session = _make_session(keyboard=60, mouse=5)
        prediction = trained_clf.predict(session)

        assert prediction is not None
        # Probabilities should sum to ~1.0
        prob_sum = sum(prediction.probabilities.values())
        assert prob_sum == pytest.approx(1.0, abs=0.01)

    def test_predict_batch(self, trained_clf):
        sessions = [
            _make_session(keyboard=60, mouse=5),
            _make_session(keyboard=3, mouse=5, scroll=25, url_nav=5, app="Chrome"),
        ]
        results = trained_clf.predict_batch(sessions)

        assert len(results) == 2
        assert all(r is not None for r in results)

    def test_untrained_predict_returns_none(self):
        clf = GradientBoostingTaskClassifier()
        session = _make_session()

        assert clf.predict(session) is None

    def test_untrained_batch_returns_nones(self):
        clf = GradientBoostingTaskClassifier()
        results = clf.predict_batch([_make_session(), _make_session()])
        assert results == [None, None]


class TestModelPersistence:
    def test_save_and_load(self):
        ds = _build_training_dataset()
        clf = GradientBoostingTaskClassifier()
        clf.train(ds)

        with tempfile.NamedTemporaryFile(suffix=".joblib", delete=False) as f:
            path = f.name

        clf.save_model(path)

        # Load into new classifier
        clf2 = GradientBoostingTaskClassifier()
        assert not clf2.is_trained
        loaded = clf2.load_model(path)

        assert loaded is True
        assert clf2.is_trained

        # Predictions should match
        session = _make_session(keyboard=60, mouse=5)
        p1 = clf.predict(session)
        p2 = clf2.predict(session)
        assert p1 is not None and p2 is not None
        assert p1.category == p2.category

    def test_save_untrained_raises(self):
        clf = GradientBoostingTaskClassifier()
        with pytest.raises(RuntimeError, match="No trained model"):
            clf.save_model("/tmp/test_model.joblib")

    def test_load_nonexistent_returns_false(self):
        clf = GradientBoostingTaskClassifier()
        loaded = clf.load_model("/tmp/nonexistent_model_12345.joblib")
        assert loaded is False
        assert not clf.is_trained
