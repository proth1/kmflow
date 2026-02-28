"""Tests for VCE classifier: rule-based, VLM stub, and hybrid."""

from __future__ import annotations

import pytest

from kmflow_agent.vce.classifier import (
    DATA_ENTRY,
    ERROR,
    NAVIGATION,
    OTHER,
    QUEUE,
    REVIEW,
    SEARCH,
    WAITING_LATENCY,
    HybridClassifier,
    RuleBasedClassifier,
)


@pytest.fixture
def classifier():
    return RuleBasedClassifier()


@pytest.fixture
def hybrid():
    return HybridClassifier()


# ---------------------------------------------------------------------------
# RuleBasedClassifier
# ---------------------------------------------------------------------------


class TestRuleBasedClassifier:
    def test_rule_based_error_detection(self, classifier):
        """Error keyword in OCR text → ERROR classification with high confidence."""
        cls, conf = classifier.classify(
            ocr_text="An error occurred: connection timeout",
            window_title="App",
            app_name="CRM",
            interaction_intensity=0.1,
            dwell_ms=2000,
        )
        assert cls == ERROR
        assert conf >= 0.75

    def test_rule_based_search_detection(self, classifier):
        """Search keyword → SEARCH classification."""
        cls, conf = classifier.classify(
            ocr_text="Search results: 42 items found",
            window_title="Search - CRM",
            app_name="CRM",
            interaction_intensity=0.5,
            dwell_ms=3000,
        )
        assert cls == SEARCH
        assert conf >= 0.75

    def test_rule_based_queue_detection(self, classifier):
        """Queue keyword in window title → QUEUE classification."""
        cls, conf = classifier.classify(
            ocr_text="Items pending review",
            window_title="Work Queue",
            app_name="CRM",
            interaction_intensity=0.2,
            dwell_ms=4000,
        )
        assert cls == QUEUE
        assert conf >= 0.75

    def test_rule_based_data_entry_detection(self, classifier):
        """High interaction intensity + form keyword → DATA_ENTRY."""
        cls, conf = classifier.classify(
            ocr_text="Edit customer record. Required fields: Name, Email",
            window_title="Edit Record",
            app_name="CRM",
            interaction_intensity=2.5,
            dwell_ms=8000,
        )
        assert cls == DATA_ENTRY

    def test_rule_based_low_confidence_fallback(self, classifier):
        """Text with no matching keywords → OTHER with low confidence."""
        cls, conf = classifier.classify(
            ocr_text="",
            window_title="",
            app_name="Notepad",
            interaction_intensity=0.1,
            dwell_ms=1000,
        )
        assert cls == OTHER
        assert conf < 0.60

    def test_rule_based_waiting_detection(self, classifier):
        """Loading indicator with low interaction → WAITING_LATENCY."""
        cls, conf = classifier.classify(
            ocr_text="Loading, please wait...",
            window_title="CRM",
            app_name="CRM",
            interaction_intensity=0.0,
            dwell_ms=5000,
        )
        assert cls == WAITING_LATENCY

    def test_rule_based_review_detection(self, classifier):
        """Review/approve keywords → REVIEW."""
        cls, conf = classifier.classify(
            ocr_text="Please review and approve the request",
            window_title="Approval",
            app_name="CRM",
            interaction_intensity=0.3,
            dwell_ms=6000,
        )
        assert cls == REVIEW


# ---------------------------------------------------------------------------
# HybridClassifier
# ---------------------------------------------------------------------------


class TestHybridClassifier:
    def test_hybrid_classifier_rule_based_only(self, hybrid):
        """Without image bytes, hybrid returns rule-based result."""
        cls, conf, method = hybrid.classify(
            ocr_text="Error: record not found",
            window_title="Error Page",
            app_name="CRM",
            interaction_intensity=0.0,
            dwell_ms=2000,
            image_bytes=None,
        )
        assert cls == ERROR
        assert method == "rule_based"

    def test_hybrid_returns_tuple(self, hybrid):
        """Hybrid always returns a 3-tuple."""
        result = hybrid.classify(
            ocr_text="",
            window_title="",
            app_name="App",
            interaction_intensity=0.0,
            dwell_ms=1000,
        )
        assert len(result) == 3
        screen_class, confidence, method = result
        assert isinstance(screen_class, str)
        assert isinstance(confidence, float)
        assert method in ("rule_based", "vlm")
