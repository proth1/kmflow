"""Comprehensive PII detection test suite — 200+ cases targeting >99% recall.

Covers all 7 PII types: SSN, credit card, email, phone, DOB, address, financial.
Each test case documents input, expected PII type, and whether it is a true
positive or false positive check.

Story #211 — Part of Epic #210 (Privacy and Compliance).
"""

from __future__ import annotations

import pytest

from src.core.models.taskmining import PIIType
from src.taskmining.pii.filter import filter_event, redact_text, scan_text
from src.taskmining.pii.patterns import ALL_PATTERNS, get_patterns_for_type


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _has_type(text: str, pii_type: PIIType) -> bool:
    """Return True if scan_text finds at least one detection of the given type."""
    return any(d.pii_type == pii_type for d in scan_text(text, "test"))


def _count_type(text: str, pii_type: PIIType) -> int:
    """Count detections of a given PII type."""
    return sum(1 for d in scan_text(text, "test") if d.pii_type == pii_type)


def _high_confidence(text: str, pii_type: PIIType, threshold: float = 0.80) -> bool:
    """Return True if any detection of the given type exceeds threshold."""
    return any(
        d.pii_type == pii_type and d.confidence >= threshold
        for d in scan_text(text, "test")
    )


# ===================================================================
# SSN Tests (40+ cases)
# ===================================================================


class TestSSNDetection:
    """SSN detection — standard dashed format (high confidence)."""

    @pytest.mark.parametrize(
        "text",
        [
            "123-45-6789",
            "SSN: 123-45-6789",
            "Social Security Number: 234-56-7890",
            "my ssn is 345-67-8901",
            "SSN=456-78-9012",
            "ssn 567-89-0123",
            "Tax ID: 678-90-1234",
            "SSN: 789-01-2345 on file",
            "record shows 890-12-3456",
            "Patient SSN 901-23-4567",
            "Employee: 012-34-5678",
            "applicant SSN: 111-22-3333",
            "SSN#: 222-33-4444",
            "SS#: 333-44-5555",
            "social security: 444-55-6666",
            "Their SSN is 555-66-7777.",
            "ssn — 666-77-8888",
            "SSN (verified): 777-88-9999",
            "Prior SSN: 888-99-0000",
            "New SSN: 999-00-1111",
        ],
    )
    def test_dashed_ssn_detected(self, text: str) -> None:
        assert _has_type(text, PIIType.SSN)
        assert _high_confidence(text, PIIType.SSN, 0.90)

    @pytest.mark.parametrize(
        "text",
        [
            "123456789",
            "SSN: 234567890",
            "ssn 345678901",
            "TIN: 456789012",
            "id number 567890123",
            "reference 678901234",
            "code: 789012345",
            "ID 890123456",
            "number is 901234567",
            "pin 012345678",
        ],
    )
    def test_undashed_9digit_detected(self, text: str) -> None:
        assert _has_type(text, PIIType.SSN)

    @pytest.mark.parametrize(
        "text,reason",
        [
            ("Call 555-123-4567", "phone number (3-3-4 format)"),
            ("Order #12345", "too few digits"),
            ("Code: 1234567890", "10 digits, not 9"),
            ("Date: 2026-02-25", "date format"),
            ("Version 1.2.3", "version number"),
            ("IP: 192.168.1.1", "IP address"),
            ("Score: 99-100", "score range"),
            ("Room 101-A", "room number"),
            ("Page 50-75", "page range"),
            ("Flight AA-123", "flight number"),
        ],
    )
    def test_ssn_false_positive_rejected(self, text: str, reason: str) -> None:
        detections = [d for d in scan_text(text, "test") if d.pii_type == PIIType.SSN and d.confidence >= 0.90]
        assert len(detections) == 0, f"False positive SSN on {reason}: {text}"


# ===================================================================
# Credit Card Tests (30+ cases)
# ===================================================================


class TestCreditCardDetection:
    """Credit card number detection — Visa, MC, Amex, Discover."""

    @pytest.mark.parametrize(
        "text,card_type",
        [
            ("4111111111111111", "Visa plain"),
            ("4111-1111-1111-1111", "Visa dashed"),
            ("4111 1111 1111 1111", "Visa spaced"),
            ("4012888888881881", "Visa test card"),
            ("4532015112830366", "Visa generated"),
        ],
    )
    def test_visa_detected(self, text: str, card_type: str) -> None:
        assert _has_type(text, PIIType.CREDIT_CARD), f"Missed {card_type}: {text}"

    @pytest.mark.parametrize(
        "text,card_type",
        [
            ("5500000000000004", "MC plain"),
            ("5500-0000-0000-0004", "MC dashed"),
            ("5500 0000 0000 0004", "MC spaced"),
            ("5105105105105100", "MC test"),
            ("5200828282828210", "MC range 52"),
            ("5300000000000006", "MC range 53"),
        ],
    )
    def test_mastercard_detected(self, text: str, card_type: str) -> None:
        assert _has_type(text, PIIType.CREDIT_CARD), f"Missed {card_type}: {text}"

    @pytest.mark.parametrize(
        "text,card_type",
        [
            ("340000000000009", "Amex 34 plain"),
            ("3400-000000-00009", "Amex 34 dashed"),
            ("370000000000002", "Amex 37 plain"),
            ("3700 000000 00002", "Amex 37 spaced"),
            ("378282246310005", "Amex test"),
            ("371449635398431", "Amex test 2"),
        ],
    )
    def test_amex_detected(self, text: str, card_type: str) -> None:
        assert _has_type(text, PIIType.CREDIT_CARD), f"Missed {card_type}: {text}"

    @pytest.mark.parametrize(
        "text,card_type",
        [
            ("6011000000000004", "Discover plain"),
            ("6011-0000-0000-0004", "Discover dashed"),
            ("6011 0000 0000 0004", "Discover spaced"),
            ("6500000000000002", "Discover 65xx"),
        ],
    )
    def test_discover_detected(self, text: str, card_type: str) -> None:
        assert _has_type(text, PIIType.CREDIT_CARD), f"Missed {card_type}: {text}"

    @pytest.mark.parametrize(
        "text,reason",
        [
            ("1234567890123456", "random 16 digits (no valid prefix)"),
            ("Reference: 9999888877776666", "non-card prefix"),
            ("Order ID: 1234-5678", "8 digits"),
            ("Phone: 1234567890", "10 digits"),
            ("Tracking: 1Z999AA10123456784", "UPS tracking"),
        ],
    )
    def test_credit_card_false_positive_rejected(self, text: str, reason: str) -> None:
        cc = [d for d in scan_text(text, "test") if d.pii_type == PIIType.CREDIT_CARD]
        assert len(cc) == 0, f"False positive CC on {reason}: {text}"


# ===================================================================
# Email Tests (25+ cases)
# ===================================================================


class TestEmailDetection:
    """Email address detection tests."""

    @pytest.mark.parametrize(
        "text",
        [
            "john.doe@example.com",
            "JANE_SMITH@COMPANY.CO.UK",
            "user+tag@domain.org",
            "admin@test.io",
            "first.last@subdomain.example.com",
            "user123@numbers.net",
            "a@b.co",
            "very.long.email.address@extremely.long.domain.name.example.com",
            "contact@company.com.au",
            "name@my-company.org",
            "test.email@gov.uk",
            "user@university.edu",
            "user@health.care",
            "support@domain.technology",
        ],
    )
    def test_email_detected(self, text: str) -> None:
        assert _has_type(text, PIIType.EMAIL), f"Missed email: {text}"

    @pytest.mark.parametrize(
        "text",
        [
            "Contact john.doe@example.com for details",
            "Email: jane@company.org is correct",
            "Send to user@domain.com ASAP",
            "Reply to admin@host.net (urgent)",
            "CC: team@work.com; lead@work.com",
        ],
    )
    def test_email_in_context(self, text: str) -> None:
        assert _has_type(text, PIIType.EMAIL)

    @pytest.mark.parametrize(
        "text,reason",
        [
            ("item @ $5.00 each", "at-sign in price"),
            ("user@", "incomplete email"),
            ("@domain.com", "no local part"),
            ("not an email address", "no at-sign"),
            ("user@.com", "empty domain"),
            ("@", "bare at-sign"),
        ],
    )
    def test_email_false_positive_rejected(self, text: str, reason: str) -> None:
        emails = [d for d in scan_text(text, "test") if d.pii_type == PIIType.EMAIL]
        assert len(emails) == 0, f"False positive email on {reason}: {text}"


# ===================================================================
# Phone Tests (30+ cases)
# ===================================================================


class TestPhoneDetection:
    """Phone number detection — US and international formats."""

    @pytest.mark.parametrize(
        "text",
        [
            "555-123-4567",
            "(555) 123-4567",
            "555.123.4567",
            "555 123 4567",
            "(800) 555-0100",
            "888-555-0199",
            "Call 555-867-5309",
            "Phone: 555-444-3333",
            "Tel: (212) 555-1212",
            "Fax: 555-999-8888",
            "Contact 800-555-1234",
            "(900) 555-0000",
            "555.444.3210",
            "(303) 555-6789",
            "415-555-2345",
        ],
    )
    def test_us_phone_detected(self, text: str) -> None:
        assert _has_type(text, PIIType.PHONE), f"Missed US phone: {text}"

    @pytest.mark.parametrize(
        "text",
        [
            "+1-555-123-4567",
            "+1 (555) 123-4567",
            "+1.555.123.4567",
            "+1 555 123 4567",
            "+1-800-555-0199",
        ],
    )
    def test_us_with_country_code(self, text: str) -> None:
        assert _has_type(text, PIIType.PHONE), f"Missed +1 phone: {text}"

    @pytest.mark.parametrize(
        "text",
        [
            "+44 7911123456",
            "+61 412345678",
            "+33 612345678",
            "+49 15112345678",
            "+81 9012345678",
            "+86 13812345678",
            "+91 9876543210",
            "+55 11987654321",
            "+7 9161234567",
        ],
    )
    def test_international_phone(self, text: str) -> None:
        assert _has_type(text, PIIType.PHONE), f"Missed intl phone: {text}"

    @pytest.mark.parametrize(
        "text,reason",
        [
            ("12345", "too few digits"),
            ("12", "two digits"),
            ("Version 3.14", "version number"),
        ],
    )
    def test_phone_false_positive_rejected(self, text: str, reason: str) -> None:
        phones = [d for d in scan_text(text, "test") if d.pii_type == PIIType.PHONE]
        assert len(phones) == 0, f"False positive phone on {reason}: {text}"


# ===================================================================
# Date of Birth Tests (20+ cases)
# ===================================================================


class TestDOBDetection:
    """Date of birth detection — requires contextual label."""

    @pytest.mark.parametrize(
        "text",
        [
            "DOB: 01/15/1990",
            "DOB: 3/22/85",
            "DOB: 12-01-1975",
            "DOB 07/04/2000",
            "DOB: 6/1/99",
            "Date of Birth: 01/15/1990",
            "Date of Birth: 3/22/1985",
            "Date of Birth: 12-01-1975",
            "Date of Birth 11/30/2001",
            "Born 07/04/2000",
            "Born 01-15-1990",
            "Born: 3/22/85",
            "Birthday: 12/25/1995",
            "Birthday: 6-15-80",
            "birthday: 01/01/2000",
            "DOB:01/01/90",
            "Born: 2/28/1988",
            "DOB: 10/31/1965",
            "Birthday 9/9/99",
            "Date of Birth:05/05/1955",
        ],
    )
    def test_dob_detected(self, text: str) -> None:
        assert _has_type(text, PIIType.DATE_OF_BIRTH), f"Missed DOB: {text}"

    @pytest.mark.parametrize(
        "text,reason",
        [
            ("Invoice date: 01/15/2026", "invoice date (no DOB label)"),
            ("Created: 2026-02-25", "creation date"),
            ("Expires: 12/2028", "expiry date"),
            ("Period: 01/01 - 12/31", "date range"),
        ],
    )
    def test_dob_false_positive_rejected(self, text: str, reason: str) -> None:
        dobs = [d for d in scan_text(text, "test") if d.pii_type == PIIType.DATE_OF_BIRTH]
        assert len(dobs) == 0, f"False positive DOB on {reason}: {text}"


# ===================================================================
# Address Tests (20+ cases)
# ===================================================================


class TestAddressDetection:
    """US street address and ZIP code detection."""

    @pytest.mark.parametrize(
        "text",
        [
            "123 Main Street",
            "456 Oak Ave",
            "789 Elm Boulevard",
            "1 Park Drive",
            "42 Maple Lane",
            "1600 Pennsylvania Ave",
            "350 Fifth Avenue",
            "1 Infinite Loop Dr",
            "100 Broadway",
            "2500 University Ave",
            "55 Water St",
            "1 Microsoft Way",
            "500 Oracle Rd",
            "77 Massachusetts Avenue",
        ],
    )
    def test_street_address_detected(self, text: str) -> None:
        assert _has_type(text, PIIType.ADDRESS), f"Missed address: {text}"

    @pytest.mark.parametrize(
        "text",
        [
            "90210",
            "10001",
            "94102",
            "60601-1234",
            "90210-1234",
            "02134",
        ],
    )
    def test_zip_code_detected(self, text: str) -> None:
        assert _has_type(text, PIIType.ADDRESS), f"Missed ZIP: {text}"

    @pytest.mark.parametrize(
        "text,reason",
        [
            ("Open file menu", "no address"),
            ("Click button 3", "no address"),
        ],
    )
    def test_address_false_positive_rejected(self, text: str, reason: str) -> None:
        addrs = [d for d in scan_text(text, "test") if d.pii_type == PIIType.ADDRESS and d.confidence >= 0.70]
        assert len(addrs) == 0, f"False positive address on {reason}: {text}"


# ===================================================================
# Financial Tests (20+ cases)
# ===================================================================


class TestFinancialDetection:
    """Bank account and routing number detection."""

    @pytest.mark.parametrize(
        "text",
        [
            "Account #12345678",
            "Acct: 1234567890123",
            "account 87654321",
            "Account: 99887766",
            "Acct #: 11223344556",
            "ACCOUNT 12345678901234567",
            "acct number: 55443322",
            "Account# 66778899",
            "ACCT: 98765432",
            "account: 11111111",
        ],
    )
    def test_account_number_detected(self, text: str) -> None:
        assert _has_type(text, PIIType.FINANCIAL), f"Missed account: {text}"

    @pytest.mark.parametrize(
        "text",
        [
            "021000021 routing number",
            "routing: 121000248",
            "ABA 021000021",
            "021000021 ABA number",
            "routing number is 122000247",
        ],
    )
    def test_routing_number_detected(self, text: str) -> None:
        assert _has_type(text, PIIType.FINANCIAL), f"Missed routing: {text}"

    @pytest.mark.parametrize(
        "text,reason",
        [
            ("Order #1234", "too few digits"),
            ("Version 2.0", "version"),
            ("Page 15", "page number"),
            ("Year 2026", "year"),
            ("Score: 95", "score"),
        ],
    )
    def test_financial_false_positive_rejected(self, text: str, reason: str) -> None:
        fin = [d for d in scan_text(text, "test") if d.pii_type == PIIType.FINANCIAL]
        assert len(fin) == 0, f"False positive financial on {reason}: {text}"


# ===================================================================
# Redaction Tests
# ===================================================================


class TestRedactionComprehensive:
    """Verify redaction across all PII types."""

    def test_redacts_ssn(self) -> None:
        assert "123-45-6789" not in redact_text("SSN: 123-45-6789")

    def test_redacts_credit_card(self) -> None:
        assert "4111111111111111" not in redact_text("Card: 4111111111111111")

    def test_redacts_email(self) -> None:
        assert "user@example.com" not in redact_text("Email: user@example.com")

    def test_redacts_phone(self) -> None:
        assert "555-123-4567" not in redact_text("Phone: 555-123-4567")

    def test_redacts_address(self) -> None:
        result = redact_text("Address: 123 Main Street")
        assert "[PII_REDACTED]" in result

    def test_redacts_dob(self) -> None:
        result = redact_text("DOB: 01/15/1990")
        assert "01/15/1990" not in result

    def test_redacts_financial(self) -> None:
        result = redact_text("Account #12345678")
        assert "12345678" not in result

    def test_multiple_pii_all_redacted(self) -> None:
        text = "SSN: 123-45-6789, Email: a@b.com, Phone: 555-123-4567, Card: 4111111111111111"
        result = redact_text(text)
        assert "123-45-6789" not in result
        assert "a@b.com" not in result
        assert "555-123-4567" not in result
        assert "4111111111111111" not in result

    def test_clean_text_unchanged(self) -> None:
        text = "Normal window title with no PII content"
        assert redact_text(text) == text


# ===================================================================
# Filter Pipeline End-to-End Tests
# ===================================================================


class TestFilterPipelineComprehensive:
    """End-to-end tests for the filter_event pipeline."""

    def test_clean_event_no_detections(self) -> None:
        event = {"window_title": "Visual Studio Code", "application_name": "Code"}
        result = filter_event(event)
        assert not result.has_pii
        assert not result.quarantine_recommended

    def test_ssn_triggers_quarantine(self) -> None:
        event = {"window_title": "SSN: 123-45-6789", "application_name": "CRM"}
        result = filter_event(event)
        assert result.has_pii
        assert result.quarantine_recommended
        assert "123-45-6789" not in result.clean_data["window_title"]

    def test_credit_card_triggers_quarantine(self) -> None:
        event = {"window_title": "Card: 4111111111111111", "application_name": "App"}
        result = filter_event(event)
        assert result.quarantine_recommended

    def test_email_triggers_quarantine(self) -> None:
        event = {"window_title": "Email: user@secret.com", "application_name": "App"}
        result = filter_event(event)
        assert result.quarantine_recommended

    def test_nested_event_data_scanned(self) -> None:
        event = {
            "window_title": "Clean",
            "application_name": "App",
            "event_data": {"field_value": "SSN: 123-45-6789"},
        }
        result = filter_event(event)
        assert result.has_pii
        assert result.quarantine_recommended

    def test_multiple_fields_all_redacted(self) -> None:
        event = {
            "window_title": "SSN: 123-45-6789",
            "url": "https://example.com/user@test.com",
            "application_name": "Browser",
        }
        result = filter_event(event)
        assert "123-45-6789" not in str(result.clean_data)

    def test_no_redaction_when_disabled(self) -> None:
        event = {"window_title": "Email: user@test.com", "application_name": "App"}
        result = filter_event(event, redact=False)
        assert result.has_pii
        assert "user@test.com" in result.clean_data["window_title"]


# ===================================================================
# Recall and Precision Assertions
# ===================================================================


class TestRecallMetrics:
    """Aggregate recall assertions per PII type."""

    def test_ssn_recall(self) -> None:
        """SSN patterns detect at least 99% of true positives."""
        positives = [
            "123-45-6789", "SSN: 234-56-7890", "my ssn is 345-67-8901",
            "SSN 456-78-9012", "ssn 567-89-0123", "Tax ID: 678-90-1234",
            "SSN: 789-01-2345", "890-12-3456", "901-23-4567", "012-34-5678",
        ]
        detected = sum(1 for t in positives if _has_type(t, PIIType.SSN))
        recall = detected / len(positives)
        assert recall >= 0.99, f"SSN recall {recall:.2f} < 0.99"

    def test_credit_card_recall(self) -> None:
        positives = [
            "4111111111111111", "4111-1111-1111-1111", "5500000000000004",
            "5500-0000-0000-0004", "340000000000009", "370000000000002",
            "6011000000000004", "6011-0000-0000-0004", "378282246310005",
            "5105105105105100",
        ]
        detected = sum(1 for t in positives if _has_type(t, PIIType.CREDIT_CARD))
        recall = detected / len(positives)
        assert recall >= 0.99, f"CC recall {recall:.2f} < 0.99"

    def test_email_recall(self) -> None:
        positives = [
            "john@example.com", "JANE@COMPANY.CO.UK", "user+tag@domain.org",
            "admin@test.io", "first.last@sub.example.com", "a@b.co",
            "user123@numbers.net", "contact@company.com.au", "name@my-co.org",
            "test@gov.uk",
        ]
        detected = sum(1 for t in positives if _has_type(t, PIIType.EMAIL))
        recall = detected / len(positives)
        assert recall >= 0.99, f"Email recall {recall:.2f} < 0.99"

    def test_phone_recall(self) -> None:
        positives = [
            "555-123-4567", "(555) 123-4567", "555.123.4567",
            "+1-555-123-4567", "+1 (555) 123-4567", "+44 7911123456",
            "(800) 555-0100", "888-555-0199", "+61 412345678",
            "+33 612345678",
        ]
        detected = sum(1 for t in positives if _has_type(t, PIIType.PHONE))
        recall = detected / len(positives)
        assert recall >= 0.99, f"Phone recall {recall:.2f} < 0.99"

    def test_dob_recall(self) -> None:
        positives = [
            "DOB: 01/15/1990", "DOB: 3/22/85", "Date of Birth: 12-01-1975",
            "Born 07/04/2000", "Birthday: 12/25/1995", "DOB: 6/1/99",
            "Born: 2/28/1988", "DOB: 10/31/1965", "Birthday 9/9/99",
            "Date of Birth:05/05/1955",
        ]
        detected = sum(1 for t in positives if _has_type(t, PIIType.DATE_OF_BIRTH))
        recall = detected / len(positives)
        assert recall >= 0.99, f"DOB recall {recall:.2f} < 0.99"

    def test_address_recall(self) -> None:
        positives = [
            "123 Main Street", "456 Oak Ave", "789 Elm Boulevard",
            "1 Park Drive", "42 Maple Lane", "1600 Pennsylvania Ave",
            "350 Fifth Avenue", "100 Broadway", "77 Massachusetts Avenue",
            "55 Water St",
        ]
        detected = sum(1 for t in positives if _has_type(t, PIIType.ADDRESS))
        recall = detected / len(positives)
        assert recall >= 0.99, f"Address recall {recall:.2f} < 0.99"

    def test_financial_recall(self) -> None:
        positives = [
            "Account #12345678", "Acct: 1234567890123", "account 87654321",
            "Account: 99887766", "Acct #: 11223344556", "ACCOUNT 12345678901234567",
            "acct number: 55443322", "Account# 66778899", "ACCT: 98765432",
            "account: 11111111",
        ]
        detected = sum(1 for t in positives if _has_type(t, PIIType.FINANCIAL))
        recall = detected / len(positives)
        assert recall >= 0.99, f"Financial recall {recall:.2f} < 0.99"


class TestFalsePositiveRate:
    """Aggregate false positive rate assertions."""

    def test_overall_false_positive_rate_below_1_percent(self) -> None:
        """Known non-PII strings should not trigger high-confidence detections."""
        clean_texts = [
            "Open file menu",
            "Click button 3",
            "Save document",
            "Switch to Excel",
            "Scroll down",
            "Copy text",
            "Paste clipboard",
            "Navigate to settings",
            "Close window",
            "Minimize application",
            "Enter key pressed",
            "Tab to next field",
            "Select all text",
            "Undo last action",
            "Redo change",
            "Print document",
            "Export as PDF",
            "Share with team",
            "Comment on cell A1",
            "Format bold",
            "Insert row",
            "Delete column",
            "Filter by date",
            "Sort ascending",
            "Group by category",
            "Pivot table refresh",
            "Chart updated",
            "Dashboard view",
            "Process completed",
            "Task finished",
            "Meeting scheduled",
            "Calendar event",
            "Notification dismissed",
            "Search results",
            "Loading data",
            "Connection established",
            "Upload complete",
            "Download started",
            "Sync in progress",
            "Update available",
            "Version 3.14.0",
            "Build #12345",
            "Commit abc1234",
            "Branch main",
            "Pull request merged",
            "Test passed",
            "Coverage 85%",
            "Performance improved",
            "Memory usage normal",
            "CPU at 45%",
        ]
        false_positives = 0
        for text in clean_texts:
            detections = [d for d in scan_text(text, "test") if d.confidence >= 0.80]
            if detections:
                false_positives += 1
        fp_rate = false_positives / len(clean_texts)
        assert fp_rate < 0.01, f"FP rate {fp_rate:.3f} >= 0.01 ({false_positives}/{len(clean_texts)})"


# ===================================================================
# Pattern Coverage
# ===================================================================


class TestPatternCoverage:
    """Verify pattern infrastructure."""

    def test_all_patterns_loaded(self) -> None:
        assert len(ALL_PATTERNS) >= 12

    def test_each_detection_type_has_patterns(self) -> None:
        required = [PIIType.SSN, PIIType.CREDIT_CARD, PIIType.EMAIL,
                    PIIType.PHONE, PIIType.ADDRESS, PIIType.DATE_OF_BIRTH,
                    PIIType.FINANCIAL]
        for pii_type in required:
            patterns = get_patterns_for_type(pii_type)
            assert len(patterns) >= 1, f"No patterns for {pii_type}"

    def test_all_patterns_have_positive_confidence(self) -> None:
        for p in ALL_PATTERNS:
            assert p.confidence > 0.0
            assert p.confidence <= 1.0

    def test_all_patterns_compile(self) -> None:
        for p in ALL_PATTERNS:
            assert p.pattern is not None
            assert hasattr(p.pattern, "finditer")
