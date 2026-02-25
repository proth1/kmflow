"""Tests for PII detection patterns — target >99% recall.

Tests cover SSN, credit card, email, phone, address, DOB, and financial PII.
"""

from __future__ import annotations

import pytest

from src.core.models.taskmining import PIIType
from src.taskmining.pii.filter import filter_event, redact_text, scan_text
from src.taskmining.pii.patterns import ALL_PATTERNS, get_patterns_for_type


# ---------------------------------------------------------------------------
# SSN Tests
# ---------------------------------------------------------------------------


class TestSSNDetection:
    """SSN pattern detection tests."""

    @pytest.mark.parametrize(
        "text",
        [
            "SSN: 123-45-6789",
            "Social Security 234-56-7890",
            "my ssn is 345-67-8901 ok",
            "SSN 456-78-9012.",
        ],
    )
    def test_detects_ssn_with_dashes(self, text: str) -> None:
        detections = scan_text(text, "test_field")
        ssn_detections = [d for d in detections if d.pii_type == PIIType.SSN]
        assert len(ssn_detections) >= 1
        assert ssn_detections[0].confidence >= 0.90

    def test_no_false_positive_on_phone(self) -> None:
        # Phone numbers should not trigger SSN pattern (different format)
        detections = scan_text("Call 555-123-4567", "test_field")
        ssn_detections = [d for d in detections if d.pii_type == PIIType.SSN]
        # Dashed SSN pattern requires 3-2-4 digit format
        assert all(d.confidence < 0.90 for d in ssn_detections)


# ---------------------------------------------------------------------------
# Credit Card Tests
# ---------------------------------------------------------------------------


class TestCreditCardDetection:
    """Credit card number pattern detection tests."""

    @pytest.mark.parametrize(
        "text,description",
        [
            ("4111111111111111", "Visa no spaces"),
            ("4111-1111-1111-1111", "Visa with dashes"),
            ("4111 1111 1111 1111", "Visa with spaces"),
            ("5500000000000004", "Mastercard"),
            ("5500-0000-0000-0004", "Mastercard with dashes"),
            ("340000000000009", "Amex"),
            ("3400-000000-00009", "Amex with dashes"),
            ("6011000000000004", "Discover"),
        ],
    )
    def test_detects_credit_cards(self, text: str, description: str) -> None:
        detections = scan_text(text, "test_field")
        cc_detections = [d for d in detections if d.pii_type == PIIType.CREDIT_CARD]
        assert len(cc_detections) >= 1, f"Failed to detect {description}: {text}"
        assert cc_detections[0].confidence >= 0.90

    def test_no_false_positive_on_random_digits(self) -> None:
        detections = scan_text("Reference number: 1234567890", "test_field")
        cc_detections = [d for d in detections if d.pii_type == PIIType.CREDIT_CARD]
        assert len(cc_detections) == 0


# ---------------------------------------------------------------------------
# Email Tests
# ---------------------------------------------------------------------------


class TestEmailDetection:
    """Email address detection tests."""

    @pytest.mark.parametrize(
        "text",
        [
            "Contact john.doe@example.com for info",
            "Email: jane_smith@company.co.uk",
            "Send to user+tag@domain.org",
            "admin@test.io is the admin",
        ],
    )
    def test_detects_email(self, text: str) -> None:
        detections = scan_text(text, "test_field")
        email_detections = [d for d in detections if d.pii_type == PIIType.EMAIL]
        assert len(email_detections) >= 1
        assert email_detections[0].confidence >= 0.95

    def test_no_false_positive_on_at_sign(self) -> None:
        detections = scan_text("item @ $5.00 each", "test_field")
        email_detections = [d for d in detections if d.pii_type == PIIType.EMAIL]
        assert len(email_detections) == 0


# ---------------------------------------------------------------------------
# Phone Tests
# ---------------------------------------------------------------------------


class TestPhoneDetection:
    """Phone number detection tests."""

    @pytest.mark.parametrize(
        "text",
        [
            "Call 555-123-4567",
            "Phone: (555) 123-4567",
            "Tel: 555.123.4567",
            "Reach me at +1-555-123-4567",
            "+1 (555) 123-4567",
        ],
    )
    def test_detects_phone(self, text: str) -> None:
        detections = scan_text(text, "test_field")
        phone_detections = [d for d in detections if d.pii_type == PIIType.PHONE]
        assert len(phone_detections) >= 1

    def test_international_phone(self) -> None:
        detections = scan_text("UK: +44 7911123456", "test_field")
        phone_detections = [d for d in detections if d.pii_type == PIIType.PHONE]
        assert len(phone_detections) >= 1


# ---------------------------------------------------------------------------
# Address Tests
# ---------------------------------------------------------------------------


class TestAddressDetection:
    """US street address detection tests."""

    @pytest.mark.parametrize(
        "text",
        [
            "123 Main Street",
            "456 Oak Ave",
            "789 Elm Boulevard",
            "1 Park Drive",
            "42 Maple Lane",
        ],
    )
    def test_detects_street_address(self, text: str) -> None:
        detections = scan_text(text, "test_field")
        addr_detections = [d for d in detections if d.pii_type == PIIType.ADDRESS]
        assert len(addr_detections) >= 1

    @pytest.mark.parametrize(
        "text",
        [
            "ZIP: 90210",
            "Postal code 10001-1234",
            "Area 94102",
        ],
    )
    def test_detects_zip_code(self, text: str) -> None:
        detections = scan_text(text, "test_field")
        addr_detections = [d for d in detections if d.pii_type == PIIType.ADDRESS]
        assert len(addr_detections) >= 1


# ---------------------------------------------------------------------------
# DOB Tests
# ---------------------------------------------------------------------------


class TestDOBDetection:
    """Date of birth detection tests."""

    @pytest.mark.parametrize(
        "text",
        [
            "DOB: 01/15/1990",
            "Date of Birth: 3/22/85",
            "Born 12-01-1975",
            "Birthday: 07/04/2000",
        ],
    )
    def test_detects_dob(self, text: str) -> None:
        detections = scan_text(text, "test_field")
        dob_detections = [d for d in detections if d.pii_type == PIIType.DATE_OF_BIRTH]
        assert len(dob_detections) >= 1


# ---------------------------------------------------------------------------
# Financial Tests
# ---------------------------------------------------------------------------


class TestFinancialDetection:
    """Financial data detection tests."""

    @pytest.mark.parametrize(
        "text",
        [
            "Account #12345678",
            "Acct: 1234567890123",
            "account 87654321",
        ],
    )
    def test_detects_account_number(self, text: str) -> None:
        detections = scan_text(text, "test_field")
        fin_detections = [d for d in detections if d.pii_type == PIIType.FINANCIAL]
        assert len(fin_detections) >= 1


# ---------------------------------------------------------------------------
# Redaction Tests
# ---------------------------------------------------------------------------


class TestRedaction:
    """PII redaction tests."""

    def test_redacts_ssn(self) -> None:
        result = redact_text("My SSN is 123-45-6789")
        assert "123-45-6789" not in result
        assert "[PII_REDACTED]" in result

    def test_redacts_email(self) -> None:
        result = redact_text("Email: user@example.com")
        assert "user@example.com" not in result
        assert "[PII_REDACTED]" in result

    def test_redacts_multiple_pii(self) -> None:
        text = "SSN: 123-45-6789, Email: a@b.com, Phone: 555-123-4567"
        result = redact_text(text)
        assert "123-45-6789" not in result
        assert "a@b.com" not in result
        assert "555-123-4567" not in result
        assert result.count("[PII_REDACTED]") >= 3

    def test_clean_text_unchanged(self) -> None:
        text = "This is a normal window title with no PII"
        result = redact_text(text)
        assert result == text


# ---------------------------------------------------------------------------
# Filter Pipeline Tests
# ---------------------------------------------------------------------------


class TestFilterPipeline:
    """End-to-end PII filter pipeline tests."""

    def test_clean_event_passes_through(self) -> None:
        event = {
            "event_type": "app_switch",
            "window_title": "Visual Studio Code",
            "application_name": "Code",
        }
        result = filter_event(event)
        assert not result.has_pii
        assert not result.quarantine_recommended
        assert result.clean_data["window_title"] == "Visual Studio Code"

    def test_pii_event_is_redacted(self) -> None:
        event = {
            "event_type": "window_focus",
            "window_title": "Customer SSN: 123-45-6789 - CRM App",
            "application_name": "CRM",
        }
        result = filter_event(event)
        assert result.has_pii
        assert "123-45-6789" not in result.clean_data["window_title"]
        assert "[PII_REDACTED]" in result.clean_data["window_title"]

    def test_pii_event_quarantine_recommended(self) -> None:
        event = {
            "event_type": "window_focus",
            "window_title": "SSN: 123-45-6789",
            "application_name": "App",
        }
        result = filter_event(event)
        assert result.quarantine_recommended

    def test_nested_event_data_scanned(self) -> None:
        event = {
            "event_type": "ui_element_interaction",
            "window_title": "Clean Title",
            "application_name": "App",
            "event_data": {
                "field_value": "john.doe@secret.com",
                "field_label": "Email Input",
            },
        }
        result = filter_event(event)
        assert result.has_pii
        assert "john.doe@secret.com" not in str(result.clean_data)

    def test_no_redaction_when_disabled(self) -> None:
        event = {
            "event_type": "window_focus",
            "window_title": "Email: test@example.com",
            "application_name": "App",
        }
        result = filter_event(event, redact=False)
        assert result.has_pii
        # PII detected but NOT redacted
        assert "test@example.com" in result.clean_data["window_title"]


# ---------------------------------------------------------------------------
# Pattern Helpers Tests
# ---------------------------------------------------------------------------


class TestPatternHelpers:
    """Tests for pattern helper functions."""

    def test_all_patterns_non_empty(self) -> None:
        assert len(ALL_PATTERNS) > 0

    def test_get_patterns_for_type(self) -> None:
        ssn_patterns = get_patterns_for_type(PIIType.SSN)
        assert len(ssn_patterns) >= 1
        assert all(p.pii_type == PIIType.SSN for p in ssn_patterns)

    def test_all_pii_types_have_patterns(self) -> None:
        # At least SSN, CC, email, phone should have patterns
        for pii_type in [PIIType.SSN, PIIType.CREDIT_CARD, PIIType.EMAIL, PIIType.PHONE]:
            patterns = get_patterns_for_type(pii_type)
            assert len(patterns) >= 1, f"No patterns for {pii_type}"
