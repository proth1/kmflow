"""Tests for the L2 PII filter."""

from __future__ import annotations

import pytest

from kmflow_agent.pii.l2_filter import L2Filter


@pytest.fixture
def l2_filter():
    return L2Filter()


class TestL2Scrub:
    def test_scrubs_ssn(self, l2_filter):
        result = l2_filter.scrub("SSN: 123-45-6789")
        assert "123-45-6789" not in result
        assert "[PII_REDACTED]" in result

    def test_scrubs_email(self, l2_filter):
        result = l2_filter.scrub("Contact: user@example.com")
        assert "user@example.com" not in result
        assert "[PII_REDACTED]" in result

    def test_scrubs_phone(self, l2_filter):
        result = l2_filter.scrub("Call (555) 123-4567")
        assert "(555) 123-4567" not in result

    def test_scrubs_credit_card(self, l2_filter):
        result = l2_filter.scrub("Card: 4111-1111-1111-1111")
        assert "4111-1111-1111-1111" not in result

    def test_clean_text_unchanged(self, l2_filter):
        text = "Budget Report Q4 2026"
        assert l2_filter.scrub(text) == text

    def test_scrubs_multiple_pii(self, l2_filter):
        text = "SSN 123-45-6789, email user@test.com"
        result = l2_filter.scrub(text)
        assert "123-45-6789" not in result
        assert "user@test.com" not in result


class TestL2ContainsPII:
    def test_detects_ssn(self, l2_filter):
        assert l2_filter.contains_pii("SSN: 123-45-6789")

    def test_detects_email(self, l2_filter):
        assert l2_filter.contains_pii("user@example.com")

    def test_no_pii_in_clean_text(self, l2_filter):
        assert not l2_filter.contains_pii("Normal window title")


class TestL2FilterEvent:
    def test_filters_window_title(self, l2_filter):
        event = {"window_title": "SSN: 123-45-6789 - CRM", "event_type": "focus"}
        result = l2_filter.filter_event(event)
        assert "123-45-6789" not in result["window_title"]
        assert result["event_type"] == "focus"

    def test_filters_nested_event_data(self, l2_filter):
        event = {
            "window_title": "Clean",
            "event_data": {"field_value": "user@secret.com"},
        }
        result = l2_filter.filter_event(event)
        assert "user@secret.com" not in str(result["event_data"])

    def test_non_string_fields_unchanged(self, l2_filter):
        event = {"event_type": "click", "x": 100, "y": 200}
        result = l2_filter.filter_event(event)
        assert result["x"] == 100
        assert result["y"] == 200
