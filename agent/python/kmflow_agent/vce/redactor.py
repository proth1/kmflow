"""PII redaction for VCE OCR output.

Applies the same regex patterns as agent/python/kmflow_agent/pii/l2_filter.py
to OCR text before it is stored in a VCERecord or sent to the backend.
"""

from __future__ import annotations

import re

# Mirror patterns from l2_filter.py — kept in sync manually.
# Any addition here should also be added to l2_filter._PATTERNS.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("EMAIL", re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")),
    ("PHONE", re.compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    ("CREDIT_CARD", re.compile(r"\b(?:4\d{3}|5[1-5]\d{2}|6011|35\d{2})[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b")),
    ("AMEX", re.compile(r"\b3[47]\d{2}[-\s]?\d{6}[-\s]?\d{5}\b")),
    # Names (simple heuristic — two Title-cased words together)
    ("NAME", re.compile(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b")),
    # US addresses (e.g., "123 Main St")
    ("ADDRESS", re.compile(r"\b\d{1,5}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:St|Ave|Blvd|Dr|Ln|Rd|Way)\b")),
]

REDACTION_MARKER = "[PII_REDACTED]"

# Sensitivity flag labels — returned alongside redacted text
_FLAG_LABELS = {
    "SSN": "ssn",
    "EMAIL": "email",
    "PHONE": "phone",
    "CREDIT_CARD": "credit_card",
    "AMEX": "credit_card",
    "NAME": "name",
    "ADDRESS": "address",
}


def redact_pii(text: str) -> tuple[str, list[str]]:
    """Replace PII patterns with redaction markers.

    Args:
        text: Raw OCR output.

    Returns:
        Tuple of (redacted_text, sensitivity_flags) where sensitivity_flags
        is a deduplicated list of PII type labels found.
    """
    result = text
    flags: list[str] = []
    for name, pattern in _PATTERNS:
        if pattern.search(result):
            result = pattern.sub(REDACTION_MARKER, result)
            flag = _FLAG_LABELS.get(name, name.lower())
            if flag not in flags:
                flags.append(flag)
    return result, flags
