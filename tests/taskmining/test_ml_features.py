"""Tests for ML feature extraction pipeline (Story #232)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.taskmining.aggregation.session import AggregatedSession
from src.taskmining.ml.features import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_VERSION,
    detect_app_category,
    extract_features,
    extract_features_batch,
)


def _make_session(
    app: str = "Excel",
    keyboard: int = 50,
    mouse: int = 30,
    copy_paste: int = 3,
    scroll: int = 10,
    file_ops: int = 2,
    url_nav: int = 0,
    duration_ms: int = 60000,
    active_ms: int = 55000,
    started_at: datetime | None = None,
) -> AggregatedSession:
    start = started_at or datetime(2026, 1, 6, 14, 30, 0, tzinfo=timezone.utc)  # Monday 14:30
    return AggregatedSession(
        app_bundle_id=app,
        window_title_sample="Test Window",
        started_at=start,
        ended_at=start,
        duration_ms=duration_ms,
        active_duration_ms=active_ms,
        idle_duration_ms=duration_ms - active_ms,
        keyboard_event_count=keyboard,
        mouse_event_count=mouse,
        copy_paste_count=copy_paste,
        scroll_count=scroll,
        file_operation_count=file_ops,
        url_navigation_count=url_nav,
        total_event_count=keyboard + mouse + copy_paste + scroll + file_ops + url_nav,
    )


class TestExtractFeatures:
    def test_vector_length_matches_schema(self):
        session = _make_session()
        features = extract_features(session)
        assert len(features) == len(FEATURE_NAMES)

    def test_all_features_are_floats(self):
        session = _make_session()
        features = extract_features(session)
        for i, f in enumerate(features):
            assert isinstance(f, float), f"Feature {FEATURE_NAMES[i]} is {type(f)}, not float"

    def test_raw_counts_correct(self):
        session = _make_session(keyboard=50, mouse=30, copy_paste=3, scroll=10, file_ops=2, url_nav=0)
        features = extract_features(session)
        assert features[0] == 50.0  # keyboard_count
        assert features[1] == 30.0  # mouse_count
        assert features[2] == 3.0   # copy_paste_count
        assert features[3] == 10.0  # scroll_count
        assert features[4] == 2.0   # file_op_count
        assert features[5] == 0.0   # url_nav_count
        assert features[6] == 95.0  # total_event_count

    def test_ratios_sum_to_at_most_one(self):
        session = _make_session()
        features = extract_features(session)
        # Ratios are features 7-12
        ratio_sum = sum(features[7:13])
        assert ratio_sum <= 1.01  # allow for floating point

    def test_duration_features(self):
        session = _make_session(duration_ms=60000, active_ms=55000)
        features = extract_features(session)
        assert features[13] == pytest.approx(60.0)  # duration_seconds
        assert features[14] == pytest.approx(55000 / 60000)  # active_ratio

    def test_temporal_features(self):
        # Monday 14:30 UTC
        start = datetime(2026, 1, 5, 14, 30, 0, tzinfo=timezone.utc)
        session = _make_session(started_at=start)
        features = extract_features(session)
        assert features[16] == 14.0  # hour_of_day
        assert features[17] == 0.0   # day_of_week (Monday=0)
        assert features[18] == 1.0   # is_business_hours

    def test_weekend_not_business_hours(self):
        # Saturday 14:30
        start = datetime(2026, 1, 10, 14, 30, 0, tzinfo=timezone.utc)
        session = _make_session(started_at=start)
        features = extract_features(session)
        assert features[18] == 0.0  # is_business_hours

    def test_evening_not_business_hours(self):
        # Monday 21:00
        start = datetime(2026, 1, 5, 21, 0, 0, tzinfo=timezone.utc)
        session = _make_session(started_at=start)
        features = extract_features(session)
        assert features[18] == 0.0

    def test_app_category_one_hot(self):
        session = _make_session(app="Microsoft Excel")
        features = extract_features(session)
        # App category features start at index 21
        app_cat_start = FEATURE_NAMES.index("app_cat_spreadsheet")
        # spreadsheet should be 1.0, rest 0.0
        assert features[app_cat_start] == 1.0
        assert sum(features[app_cat_start:app_cat_start + 9]) == 1.0

    def test_zero_event_session_no_division_error(self):
        session = _make_session(keyboard=0, mouse=0, copy_paste=0, scroll=0, file_ops=0, url_nav=0)
        session.total_event_count = 0
        features = extract_features(session)
        assert len(features) == len(FEATURE_NAMES)
        # Ratios should be 0 (not NaN)
        for i in range(7, 13):
            assert features[i] == 0.0

    def test_input_diversity(self):
        # 4 non-zero input types
        session = _make_session(keyboard=10, mouse=5, copy_paste=2, scroll=3, file_ops=0, url_nav=0)
        features = extract_features(session)
        diversity_idx = FEATURE_NAMES.index("input_diversity")
        assert features[diversity_idx] == pytest.approx(4 / 6)

    def test_keyboard_mouse_ratio(self):
        session = _make_session(keyboard=50, mouse=10)
        features = extract_features(session)
        km_idx = FEATURE_NAMES.index("keyboard_mouse_ratio")
        assert features[km_idx] == pytest.approx(50.0 / 10.0)


class TestExtractFeaturesBatch:
    def test_batch_produces_list_per_session(self):
        sessions = [_make_session(app="Excel"), _make_session(app="Chrome")]
        batch = extract_features_batch(sessions)
        assert len(batch) == 2
        assert len(batch[0]) == len(FEATURE_NAMES)
        assert len(batch[1]) == len(FEATURE_NAMES)

    def test_empty_batch(self):
        assert extract_features_batch([]) == []


class TestDetectAppCategory:
    @pytest.mark.parametrize("app,expected", [
        ("Microsoft Excel", "spreadsheet"),
        ("Google Chrome", "browser"),
        ("Outlook", "email"),
        ("Slack", "communication"),
        ("Microsoft Word", "document"),
        ("Salesforce", "crm"),
        ("Jira", "project_management"),
        ("VS Code", "development"),
        ("Calculator", "other"),
    ])
    def test_categories(self, app: str, expected: str):
        assert detect_app_category(app) == expected


class TestFeatureSchemaVersion:
    def test_version_is_positive_int(self):
        assert isinstance(FEATURE_SCHEMA_VERSION, int)
        assert FEATURE_SCHEMA_VERSION >= 1

    def test_feature_names_non_empty(self):
        assert len(FEATURE_NAMES) > 20
