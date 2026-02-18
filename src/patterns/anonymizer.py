"""Data anonymization engine for cross-engagement patterns.

Strips client-specific and sensitive information from process data
before storing in the shared pattern library.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Patterns that look like PII or client-specific data
PII_PATTERNS = [
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),  # email
    re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),  # phone
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # SSN
]


def anonymize_text(text: str) -> str:
    """Replace PII patterns in text with anonymized placeholders."""
    result = text
    for i, pattern in enumerate(PII_PATTERNS):
        result = pattern.sub(f"[REDACTED_{i}]", result)
    return result


def anonymize_pattern_data(
    data: dict[str, Any],
    client_name: str | None = None,
    engagement_name: str | None = None,
) -> dict[str, Any]:
    """Anonymize process pattern data for cross-engagement use.

    Args:
        data: The raw pattern data to anonymize.
        client_name: Client name to replace.
        engagement_name: Engagement name to replace.

    Returns:
        Anonymized copy of the data.
    """
    result = _deep_copy_and_anonymize(data)

    # Replace client/engagement names if provided
    if client_name:
        result = _replace_in_dict(result, client_name, "[CLIENT]")
    if engagement_name:
        result = _replace_in_dict(result, engagement_name, "[ENGAGEMENT]")

    return result


def _deep_copy_and_anonymize(obj: Any) -> Any:
    """Recursively copy and anonymize data."""
    if isinstance(obj, dict):
        return {k: _deep_copy_and_anonymize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_deep_copy_and_anonymize(item) for item in obj]
    elif isinstance(obj, str):
        return anonymize_text(obj)
    return obj


def _replace_in_dict(obj: Any, old: str, new: str) -> Any:
    """Recursively replace a string value throughout a data structure."""
    if isinstance(obj, dict):
        return {k: _replace_in_dict(v, old, new) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_replace_in_dict(item, old, new) for item in obj]
    elif isinstance(obj, str):
        return obj.replace(old, new)
    return obj


def compute_anonymization_hash(original_data: dict[str, Any]) -> str:
    """Generate a hash to verify anonymization was applied."""
    import json

    canonical = json.dumps(original_data, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
