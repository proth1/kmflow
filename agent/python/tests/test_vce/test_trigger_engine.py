"""Tests for VCE TriggerEngine: recurring exception, novel cluster, taxonomy boundary."""

from __future__ import annotations

import pytest

from kmflow_agent.vce.trigger_engine import (
    _EXCEPTION_THRESHOLD,
    TriggerEngine,
)


@pytest.fixture
def engine():
    return TriggerEngine()


class TestRecurringException:
    def test_recurring_exception_fires(self, engine):
        """After EXCEPTION_THRESHOLD error screens for the same app, trigger fires."""
        app = "SAP"
        # Fire just below threshold — should not trigger yet
        for _ in range(_EXCEPTION_THRESHOLD - 1):
            result = engine.check_recurring_exception(app, "error")
            assert result is False

        # One more — should now trigger
        assert engine.check_recurring_exception(app, "error") is True

    def test_recurring_exception_below_threshold(self, engine):
        """Fewer than threshold errors do not fire."""
        for _ in range(_EXCEPTION_THRESHOLD - 1):
            result = engine.check_recurring_exception("CRM", "error")
        assert result is False

    def test_non_error_screen_never_fires(self, engine):
        """Non-error screen class never fires RECURRING_EXCEPTION."""
        for _ in range(10):
            result = engine.check_recurring_exception("SAP", "queue")
        assert result is False

    def test_different_apps_tracked_independently(self, engine):
        """Error counts are per-app."""
        for _ in range(_EXCEPTION_THRESHOLD):
            engine.check_recurring_exception("SAP", "error")

        # A different app should not have a pre-existing count
        for _ in range(_EXCEPTION_THRESHOLD - 1):
            result = engine.check_recurring_exception("CRM", "error")
        assert result is False


class TestNovelCluster:
    def test_novel_cluster_detection(self, engine):
        """Feature vector far from known cluster fires NOVEL_CLUSTER."""
        # Bootstrap: first call registers a prototype (no trigger)
        features_a = {"word_count": 10.0, "has_error": 0.0, "form_fields": 5.0}
        result = engine.check_novel_cluster(features_a)
        assert result is False  # first call registers prototype

        # Second call with very different features → triggers
        features_novel = {"word_count": 100.0, "has_error": 1.0, "form_fields": 0.0}
        result = engine.check_novel_cluster(features_novel)
        assert result is True

    def test_similar_cluster_does_not_fire(self, engine):
        """Feature vector close to known cluster does not fire."""
        features_a = {"word_count": 10.0, "has_error": 0.0}
        engine.check_novel_cluster(features_a)  # register

        features_similar = {"word_count": 11.0, "has_error": 0.0}
        result = engine.check_novel_cluster(features_similar)
        assert result is False

    def test_first_call_never_fires(self, engine):
        """First call registers prototype and never fires."""
        result = engine.check_novel_cluster({"a": 1.0, "b": 2.0})
        assert result is False


class TestTaxonomyBoundary:
    def test_taxonomy_boundary_crossing(self, engine):
        """Transition between apps in the same boundary pair fires trigger."""
        config = {"taxonomy_boundaries": [["SAP", "Excel"]]}
        assert engine.check_taxonomy_boundary("SAP", "Excel", config) is True

    def test_taxonomy_boundary_reverse_direction(self, engine):
        """Boundary crossing is bidirectional."""
        config = {"taxonomy_boundaries": [["SAP", "Excel"]]}
        assert engine.check_taxonomy_boundary("Excel", "SAP", config) is True

    def test_no_boundary_for_unrelated_apps(self, engine):
        """Apps not in any boundary pair do not fire."""
        config = {"taxonomy_boundaries": [["SAP", "Excel"]]}
        assert engine.check_taxonomy_boundary("Chrome", "Word", config) is False

    def test_empty_config_never_fires(self, engine):
        """Empty taxonomy_boundaries config never fires."""
        assert engine.check_taxonomy_boundary("SAP", "CRM", {}) is False

    def test_same_app_does_not_fire(self, engine):
        """Transition from app to itself does not fire."""
        config = {"taxonomy_boundaries": [["SAP", "Excel"]]}
        assert engine.check_taxonomy_boundary("SAP", "SAP", config) is False
