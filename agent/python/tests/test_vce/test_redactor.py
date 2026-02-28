"""Tests for VCE PII redactor."""

from __future__ import annotations

import pytest

from kmflow_agent.vce.redactor import REDACTION_MARKER, redact_pii


class TestRedactPII:
    def test_redact_email(self):
        text, flags = redact_pii("Contact: user@example.com for help")
        assert "user@example.com" not in text
        assert REDACTION_MARKER in text
        assert "email" in flags

    def test_redact_ssn(self):
        text, flags = redact_pii("SSN: 123-45-6789")
        assert "123-45-6789" not in text
        assert REDACTION_MARKER in text
        assert "ssn" in flags

    def test_redact_phone(self):
        text, flags = redact_pii("Call (555) 987-6543 now")
        assert "987-6543" not in text
        assert REDACTION_MARKER in text
        assert "phone" in flags

    def test_redact_credit_card(self):
        text, flags = redact_pii("Card number: 4111-1111-1111-1111")
        assert "4111-1111-1111-1111" not in text
        assert REDACTION_MARKER in text
        assert "credit_card" in flags

    def test_no_pii_unchanged(self):
        text, flags = redact_pii("Processing invoice INV-2026-001 for Q1")
        assert text == "Processing invoice INV-2026-001 for Q1"
        assert flags == []

    def test_multiple_pii_types(self):
        text, flags = redact_pii("SSN 123-45-6789, email user@test.com")
        assert "123-45-6789" not in text
        assert "user@test.com" not in text
        assert "ssn" in flags
        assert "email" in flags

    def test_returns_tuple(self):
        result = redact_pii("some text")
        assert isinstance(result, tuple)
        assert len(result) == 2
        text, flags = result
        assert isinstance(text, str)
        assert isinstance(flags, list)

    def test_empty_string(self):
        text, flags = redact_pii("")
        assert text == ""
        assert flags == []
