"""Regex patterns for PII detection in task mining event data.

Implements Layer 2 (at-source) and Layer 3 (server-side) PII detection.
Patterns target SSN, credit card, email, phone, address, and other PII
types with high recall (>99% target).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.core.models.taskmining import PIIType


@dataclass(frozen=True)
class PIIPattern:
    """A compiled PII detection pattern with metadata."""

    pii_type: PIIType
    pattern: re.Pattern[str]
    description: str
    confidence: float  # Base confidence score for this pattern


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

_PATTERNS: list[PIIPattern] = [
    # -- SSN ------------------------------------------------------------------
    PIIPattern(
        pii_type=PIIType.SSN,
        pattern=re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        description="US SSN with dashes (XXX-XX-XXXX)",
        confidence=0.95,
    ),
    PIIPattern(
        pii_type=PIIType.SSN,
        pattern=re.compile(r"\b\d{9}\b"),
        description="US SSN without dashes (9 consecutive digits)",
        confidence=0.6,
    ),
    # -- Credit Card ----------------------------------------------------------
    PIIPattern(
        pii_type=PIIType.CREDIT_CARD,
        pattern=re.compile(r"\b4\d{3}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),
        description="Visa card number",
        confidence=0.95,
    ),
    PIIPattern(
        pii_type=PIIType.CREDIT_CARD,
        pattern=re.compile(r"\b5[1-5]\d{2}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),
        description="Mastercard number",
        confidence=0.95,
    ),
    PIIPattern(
        pii_type=PIIType.CREDIT_CARD,
        pattern=re.compile(r"\b3[47]\d{2}[\s-]?\d{6}[\s-]?\d{5}\b"),
        description="American Express card number",
        confidence=0.95,
    ),
    PIIPattern(
        pii_type=PIIType.CREDIT_CARD,
        pattern=re.compile(r"\b6(?:011|5\d{2})[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),
        description="Discover card number",
        confidence=0.95,
    ),
    # -- Email ----------------------------------------------------------------
    PIIPattern(
        pii_type=PIIType.EMAIL,
        pattern=re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
        description="Email address",
        confidence=0.98,
    ),
    # -- Phone ----------------------------------------------------------------
    PIIPattern(
        pii_type=PIIType.PHONE,
        pattern=re.compile(r"\b\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b"),
        description="US phone number (XXX-XXX-XXXX variants)",
        confidence=0.85,
    ),
    PIIPattern(
        pii_type=PIIType.PHONE,
        pattern=re.compile(r"\b\+1[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b"),
        description="US phone with country code (+1)",
        confidence=0.95,
    ),
    PIIPattern(
        pii_type=PIIType.PHONE,
        pattern=re.compile(r"\b\+\d{1,3}[\s.-]?\d{4,14}\b"),
        description="International phone number",
        confidence=0.80,
    ),
    # -- Address (US) ---------------------------------------------------------
    PIIPattern(
        pii_type=PIIType.ADDRESS,
        pattern=re.compile(
            r"\b\d{1,5}\s+[A-Za-z]+(?:\s+[A-Za-z]+){0,3}\s+"
            r"(?:St|Street|Ave|Avenue|Blvd|Boulevard|Dr|Drive|Ln|Lane|Rd|Road|Way|Ct|Court|Pl|Place)\.?\b",
            re.IGNORECASE,
        ),
        description="US street address",
        confidence=0.80,
    ),
    PIIPattern(
        pii_type=PIIType.ADDRESS,
        pattern=re.compile(r"\b\d{5}(?:-\d{4})?\b"),
        description="US ZIP code",
        confidence=0.50,
    ),
    # -- Date of Birth --------------------------------------------------------
    PIIPattern(
        pii_type=PIIType.DATE_OF_BIRTH,
        pattern=re.compile(r"\b(?:DOB|Date of Birth|Born|Birthday)[\s:]*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", re.IGNORECASE),
        description="Date of birth with label",
        confidence=0.95,
    ),
    # -- Financial ------------------------------------------------------------
    PIIPattern(
        pii_type=PIIType.FINANCIAL,
        pattern=re.compile(r"\b(?:account|acct)[\s#:]*\d{8,17}\b", re.IGNORECASE),
        description="Bank account number",
        confidence=0.85,
    ),
    PIIPattern(
        pii_type=PIIType.FINANCIAL,
        pattern=re.compile(r"\b\d{9}(?:\s?\d{0,4})?\b.*?(?:routing|ABA)\b", re.IGNORECASE),
        description="Bank routing number with context",
        confidence=0.90,
    ),
]

# Precomputed set for fast lookup
ALL_PATTERNS: tuple[PIIPattern, ...] = tuple(_PATTERNS)


def get_patterns_for_type(pii_type: PIIType) -> list[PIIPattern]:
    """Return all patterns for a specific PII type."""
    return [p for p in ALL_PATTERNS if p.pii_type == pii_type]
