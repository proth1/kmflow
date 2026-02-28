"""PII filtering pipeline for task mining event data.

Scans text fields in event payloads against known PII patterns and
either redacts the content (Layer 2) or quarantines the event (Layer 3).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.core.models.taskmining import PIIType
from src.taskmining.pii.patterns import ALL_PATTERNS, PIIPattern

logger = logging.getLogger(__name__)

REDACTION_MARKER = "[PII_REDACTED]"


@dataclass
class PIIDetection:
    """A single PII detection result."""

    pii_type: PIIType
    field_name: str
    matched_text: str
    confidence: float
    pattern_description: str


@dataclass
class FilterResult:
    """Result of running the PII filter on an event payload."""

    clean_data: dict
    detections: list[PIIDetection] = field(default_factory=list)
    quarantine_recommended: bool = False

    @property
    def has_pii(self) -> bool:
        return len(self.detections) > 0


# -- Fields to scan in event payloads -----------------------------------------

_SCANNABLE_FIELDS = frozenset(
    {
        "window_title",
        "application_name",
        "url",
        "file_path",
        "text_content",
        "clipboard_content",
        "field_value",
        "field_label",
    }
)

# Confidence threshold for quarantine (Layer 3)
QUARANTINE_THRESHOLD = 0.80


def scan_text(text: str, field_name: str) -> list[PIIDetection]:
    """Scan a single text string against all PII patterns.

    Args:
        text: The text to scan.
        field_name: Name of the field being scanned (for reporting).

    Returns:
        List of PII detections found in the text.
    """
    detections: list[PIIDetection] = []
    for pattern in ALL_PATTERNS:
        for match in pattern.pattern.finditer(text):
            detections.append(
                PIIDetection(
                    pii_type=pattern.pii_type,
                    field_name=field_name,
                    matched_text=match.group(),
                    confidence=pattern.confidence,
                    pattern_description=pattern.description,
                )
            )
    return detections


def redact_text(text: str, patterns: tuple[PIIPattern, ...] | None = None) -> str:
    """Replace all PII matches in text with redaction markers.

    Args:
        text: The text to redact.
        patterns: Optional subset of patterns to use. Defaults to all.

    Returns:
        Text with PII replaced by [PII_REDACTED].
    """
    if patterns is None:
        patterns = ALL_PATTERNS
    result = text
    for pattern in patterns:
        result = pattern.pattern.sub(REDACTION_MARKER, result)
    return result


def filter_event(event_data: dict, redact: bool = True) -> FilterResult:
    """Run the full PII filter pipeline on an event payload.

    Scans all scannable fields in the event data dict for PII patterns.
    Optionally redacts detected PII in place.

    Args:
        event_data: The raw event data dictionary.
        redact: If True, replace detected PII with redaction markers.

    Returns:
        FilterResult with clean data and detection details.
    """
    clean_data = dict(event_data)
    all_detections: list[PIIDetection] = []

    # Scan top-level string fields
    for field_name in _SCANNABLE_FIELDS:
        value = clean_data.get(field_name)
        if not isinstance(value, str) or not value:
            continue

        detections = scan_text(value, field_name)
        if detections:
            all_detections.extend(detections)
            if redact:
                clean_data[field_name] = redact_text(value)

    # Scan nested event_data dict if present
    nested = clean_data.get("event_data")
    if isinstance(nested, dict):
        nested_clean = dict(nested)
        for field_name, value in nested.items():
            if not isinstance(value, str) or not value:
                continue
            if field_name not in _SCANNABLE_FIELDS:
                continue
            detections = scan_text(value, f"event_data.{field_name}")
            if detections:
                all_detections.extend(detections)
                if redact:
                    nested_clean[field_name] = redact_text(value)
        clean_data["event_data"] = nested_clean

    # Determine if quarantine is recommended (any high-confidence detection)
    quarantine = any(d.confidence >= QUARANTINE_THRESHOLD for d in all_detections)

    if all_detections:
        logger.info(
            "PII filter: %d detections in event (quarantine=%s)",
            len(all_detections),
            quarantine,
        )

    return FilterResult(
        clean_data=clean_data,
        detections=all_detections,
        quarantine_recommended=quarantine,
    )
