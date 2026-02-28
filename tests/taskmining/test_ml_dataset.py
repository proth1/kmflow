"""Tests for training data infrastructure (Story #233)."""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime

import pytest

from src.core.models.taskmining import ActionCategory
from src.taskmining.aggregation.session import AggregatedSession
from src.taskmining.ml.dataset import (
    DatasetBuilder,
    LabeledSample,
    TrainingDataset,
    export_dataset,
    import_dataset,
)
from src.taskmining.ml.features import FEATURE_NAMES


def _make_session(
    app: str = "Excel",
    keyboard: int = 50,
    mouse: int = 30,
) -> AggregatedSession:
    start = datetime(2026, 1, 6, 14, 0, 0, tzinfo=UTC)
    total = keyboard + mouse
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
        copy_paste_count=0,
        scroll_count=0,
        file_operation_count=0,
        url_navigation_count=0,
        total_event_count=total,
        session_id="s1",
    )


class TestTrainingDataset:
    def test_add_sample(self):
        ds = TrainingDataset()
        ds.add_sample(LabeledSample(features=[1.0, 2.0], label="data_entry"))
        assert ds.size == 1

    def test_add_samples_bumps_version(self):
        ds = TrainingDataset()
        assert ds.version == 1
        ds.add_samples([LabeledSample(features=[1.0], label="review")])
        assert ds.version == 2

    def test_label_distribution(self):
        ds = TrainingDataset()
        ds.add_sample(LabeledSample(features=[1.0], label="data_entry"))
        ds.add_sample(LabeledSample(features=[2.0], label="data_entry"))
        ds.add_sample(LabeledSample(features=[3.0], label="navigation"))
        dist = ds.label_distribution
        assert dist == {"data_entry": 2, "navigation": 1}

    def test_stratified_split_proportional(self):
        ds = TrainingDataset()
        for i in range(20):
            ds.add_sample(LabeledSample(features=[float(i)], label="data_entry"))
        for i in range(10):
            ds.add_sample(LabeledSample(features=[float(i + 20)], label="navigation"))

        split = ds.stratified_split(test_ratio=0.2)

        # 20% of 20 = 4 data_entry test, 20% of 10 = 2 navigation test
        assert split.train_size + split.test_size == 30
        assert split.test_size >= 2  # at least 1 per label

    def test_stratified_split_deterministic(self):
        ds = TrainingDataset()
        for i in range(20):
            ds.add_sample(LabeledSample(features=[float(i)], label="data_entry"))
        for i in range(10):
            ds.add_sample(LabeledSample(features=[float(i + 20)], label="review"))

        split1 = ds.stratified_split(seed=42)
        split2 = ds.stratified_split(seed=42)
        assert split1.train_labels == split2.train_labels
        assert split1.test_labels == split2.test_labels

    def test_split_has_all_labels(self):
        ds = TrainingDataset()
        for label in ["data_entry", "navigation", "review"]:
            for i in range(10):
                ds.add_sample(LabeledSample(features=[float(i)], label=label))

        split = ds.stratified_split()
        assert set(split.train_labels) == {"data_entry", "navigation", "review"}
        assert set(split.test_labels) == {"data_entry", "navigation", "review"}


class TestDatasetBuilder:
    def test_build_from_sessions(self):
        sessions = [_make_session(keyboard=50, mouse=10), _make_session(keyboard=5, mouse=50)]
        labels = [ActionCategory.DATA_ENTRY, ActionCategory.NAVIGATION]

        builder = DatasetBuilder()
        dataset = builder.build_from_sessions(sessions, labels)

        assert dataset.size == 2
        assert dataset.samples[0].label == "data_entry"
        assert dataset.samples[1].label == "navigation"
        assert len(dataset.samples[0].features) == len(FEATURE_NAMES)

    def test_mismatched_lengths_raises(self):
        sessions = [_make_session()]
        labels = [ActionCategory.DATA_ENTRY, ActionCategory.NAVIGATION]

        builder = DatasetBuilder()
        with pytest.raises(ValueError, match="same length"):
            builder.build_from_sessions(sessions, labels)

    def test_source_label_propagated(self):
        sessions = [_make_session()]
        labels = [ActionCategory.DATA_ENTRY]

        builder = DatasetBuilder()
        dataset = builder.build_from_sessions(sessions, labels, source="human")

        assert dataset.samples[0].source == "human"


class TestExportImport:
    def test_roundtrip(self):
        ds = TrainingDataset(version=3)
        ds.add_sample(LabeledSample(features=[1.0, 2.0, 3.0], label="data_entry", session_id="s1"))
        ds.add_sample(LabeledSample(features=[4.0, 5.0, 6.0], label="review", session_id="s2"))

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        export_dataset(ds, path)

        loaded = import_dataset(path)
        assert loaded.version == 3
        assert loaded.size == 2
        assert loaded.samples[0].label == "data_entry"
        assert loaded.samples[0].features == [1.0, 2.0, 3.0]
        assert loaded.samples[1].session_id == "s2"

    def test_export_creates_valid_json(self):
        ds = TrainingDataset()
        ds.add_sample(LabeledSample(features=[1.0], label="review"))

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        export_dataset(ds, path)

        with open(path) as f:
            data = json.load(f)

        assert data["version"] == 1
        assert data["sample_count"] == 1
        assert "label_distribution" in data
        assert data["label_distribution"]["review"] == 1
