"""Consolidated PII regex patterns shared by all agent PII filters.

Single source of truth for PII detection patterns used by:
  - L2 filter (agent/python/kmflow_agent/pii/l2_filter.py)
  - VCE redactor (agent/python/kmflow_agent/vce/redactor.py)

When adding or modifying patterns here, no other files need updating.
"""

from __future__ import annotations

import re

# Redaction marker replacing detected PII
REDACTION_MARKER = "[PII_REDACTED]"

# Base PII patterns — high-precision identifiers safe for general L2 filtering.
BASE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("EMAIL", re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")),
    ("PHONE", re.compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    # Visa, MC, Discover, JCB (16-digit)
    ("CREDIT_CARD", re.compile(r"\b(?:4\d{3}|5[1-5]\d{2}|6011|35\d{2})[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b")),
    # AmEx (15-digit): 3[47]xx-xxxxxx-xxxxx
    ("AMEX", re.compile(r"\b3[47]\d{2}[-\s]?\d{6}[-\s]?\d{5}\b")),
]

# Extended patterns — heuristic patterns with higher false positive rates.
# Used by VCE redactor (OCR output) where aggressive redaction is preferred.
EXTENDED_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Names (simple heuristic — two Title-cased words together)
    ("NAME", re.compile(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b")),
    # US addresses (e.g., "123 Main St")
    ("ADDRESS", re.compile(r"\b\d{1,5}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:St|Ave|Blvd|Dr|Ln|Rd|Way)\b")),
]

# All patterns combined — base + extended.
CORE_PATTERNS: list[tuple[str, re.Pattern[str]]] = BASE_PATTERNS + EXTENDED_PATTERNS

# Sensitivity flag labels — maps pattern name to a normalized label for metadata
FLAG_LABELS: dict[str, str] = {
    "SSN": "ssn",
    "EMAIL": "email",
    "PHONE": "phone",
    "CREDIT_CARD": "credit_card",
    "AMEX": "credit_card",
    "NAME": "name",
    "ADDRESS": "address",
}
