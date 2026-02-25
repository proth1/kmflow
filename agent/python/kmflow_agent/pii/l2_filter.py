"""Layer 2 PII filter: regex-based scrubbing before events enter local storage.

Patterns are synchronized with src/taskmining/pii/patterns.py on the backend
and agent/macos/Sources/PII/L1Filter.swift on the Swift side.
"""

from __future__ import annotations

import re

# PII patterns — must match backend patterns
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("EMAIL", re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")),
    ("PHONE", re.compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    # Visa, MC, Discover, JCB (16-digit)
    ("CREDIT_CARD", re.compile(r"\b(?:4\d{3}|5[1-5]\d{2}|6011|35\d{2})[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b")),
    # AmEx (15-digit): 3[47]xx-xxxxxx-xxxxx
    ("AMEX", re.compile(r"\b3[47]\d{2}[-\s]?\d{6}[-\s]?\d{5}\b")),
]

REDACTION_MARKER = "[PII_REDACTED]"

# Fields to scan for PII
_SCANNABLE_FIELDS = {"window_title", "application_name", "url", "file_path", "text_content"}


class L2Filter:
    """Layer 2 PII filter for the Python agent layer."""

    def scrub(self, text: str) -> str:
        """Replace PII patterns with redaction markers."""
        result = text
        for _name, pattern in _PATTERNS:
            result = pattern.sub(REDACTION_MARKER, result)
        return result

    def contains_pii(self, text: str) -> bool:
        """Check if text contains any PII pattern."""
        return any(pattern.search(text) for _name, pattern in _PATTERNS)

    def filter_event(self, event: dict) -> dict:
        """Apply L2 PII filtering to an event dict."""
        filtered = dict(event)
        for field in _SCANNABLE_FIELDS:
            if field in filtered and isinstance(filtered[field], str):
                filtered[field] = self.scrub(filtered[field])

        # Also scan nested event_data
        if "event_data" in filtered and isinstance(filtered["event_data"], dict):
            for key, value in filtered["event_data"].items():
                if isinstance(value, str):
                    filtered["event_data"][key] = self.scrub(value)

        return filtered
