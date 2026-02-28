"""Feature extraction pipeline for ML task classification.

Extracts structured feature vectors from AggregatedSession data for
use as input to ML classifiers.

Story #232 — Part of Epic #231 (ML Task Segmentation).
"""

from __future__ import annotations

import logging

from src.taskmining.aggregation.session import AggregatedSession
from src.taskmining.app_categories import (
    APP_CATEGORIES as _APP_CATEGORIES,
)
from src.taskmining.app_categories import (
    detect_app_category,
)

logger = logging.getLogger(__name__)

# Feature schema version — bump when features are added/removed/reordered
# so that persisted models are invalidated on schema change.
FEATURE_SCHEMA_VERSION = 1

# Feature names in the order they appear in the vector
FEATURE_NAMES: list[str] = [
    # Interaction counts (raw)
    "keyboard_count",
    "mouse_count",
    "copy_paste_count",
    "scroll_count",
    "file_op_count",
    "url_nav_count",
    "total_event_count",
    # Interaction ratios
    "keyboard_ratio",
    "mouse_ratio",
    "copy_paste_ratio",
    "scroll_ratio",
    "file_op_ratio",
    "url_nav_ratio",
    # Duration features
    "duration_seconds",
    "active_ratio",
    "events_per_second",
    # Temporal features
    "hour_of_day",
    "day_of_week",
    "is_business_hours",
    # Derived features
    "keyboard_mouse_ratio",
    "input_diversity",
    # App category one-hot (9 features)
    *[f"app_cat_{cat}" for cat in _APP_CATEGORIES],
]


def extract_features(session: AggregatedSession) -> list[float]:
    """Extract a feature vector from an aggregated session.

    Returns a list of floats matching FEATURE_NAMES ordering.
    The vector length is always len(FEATURE_NAMES).

    Args:
        session: An aggregated desktop session.

    Returns:
        Feature vector as list of floats.
    """
    total = max(session.total_event_count, 1)  # avoid div-by-zero
    duration_s = max(session.duration_ms / 1000, 0.001)

    # Interaction counts
    keyboard = float(session.keyboard_event_count)
    mouse = float(session.mouse_event_count)
    copy_paste = float(session.copy_paste_count)
    scroll = float(session.scroll_count)
    file_op = float(session.file_operation_count)
    url_nav = float(session.url_navigation_count)
    total_f = float(session.total_event_count)

    # Interaction ratios
    keyboard_ratio = keyboard / total
    mouse_ratio = mouse / total
    copy_paste_ratio = copy_paste / total
    scroll_ratio = scroll / total
    file_op_ratio = file_op / total
    url_nav_ratio = url_nav / total

    # Duration features
    active_ratio = session.active_duration_ms / max(session.duration_ms, 1)
    events_per_second = total_f / duration_s

    # Temporal features
    hour = float(session.started_at.hour) if session.started_at else 12.0
    dow = float(session.started_at.weekday()) if session.started_at else 2.0
    is_business = 1.0 if 8 <= hour <= 18 and dow < 5 else 0.0

    # Derived features
    keyboard_mouse_ratio = keyboard / max(mouse, 1.0)
    # Input diversity: how many distinct input types are non-zero (0-6)
    input_types = sum(1 for x in [keyboard, mouse, copy_paste, scroll, file_op, url_nav] if x > 0)
    input_diversity = float(input_types) / 6.0

    # App category one-hot
    app_cat = detect_app_category(session.app_bundle_id)
    app_one_hot = [1.0 if cat == app_cat else 0.0 for cat in _APP_CATEGORIES]

    vector = [
        # Raw counts
        keyboard,
        mouse,
        copy_paste,
        scroll,
        file_op,
        url_nav,
        total_f,
        # Ratios
        keyboard_ratio,
        mouse_ratio,
        copy_paste_ratio,
        scroll_ratio,
        file_op_ratio,
        url_nav_ratio,
        # Duration
        duration_s,
        active_ratio,
        events_per_second,
        # Temporal
        hour,
        dow,
        is_business,
        # Derived
        keyboard_mouse_ratio,
        input_diversity,
        # App category one-hot
        *app_one_hot,
    ]

    assert len(vector) == len(FEATURE_NAMES), (
        f"Feature vector length {len(vector)} != schema length {len(FEATURE_NAMES)}"
    )
    return vector


def extract_features_batch(
    sessions: list[AggregatedSession],
) -> list[list[float]]:
    """Extract feature vectors from multiple sessions.

    Args:
        sessions: List of aggregated sessions.

    Returns:
        List of feature vectors (one per session).
    """
    return [extract_features(s) for s in sessions]
