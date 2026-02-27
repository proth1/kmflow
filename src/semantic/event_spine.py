"""Event Spine Builder — canonicalizes, deduplicates, and orders events.

Takes raw events from heterogeneous source systems, normalizes them to
CanonicalActivityEvent format, removes duplicates (retaining highest
confidence), and orders by timestamp to form a complete case timeline.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Default deduplication tolerance: events within this window for the same
# (case_id, activity_name) are considered duplicates.
DEFAULT_DEDUP_TOLERANCE_SECONDS = 60


class EventSpineBuilder:
    """Builds a chronological event spine from raw multi-source events."""

    def __init__(
        self,
        mapping_rules: dict[str, dict[str, str]] | None = None,
        dedup_tolerance_seconds: int = DEFAULT_DEDUP_TOLERANCE_SECONDS,
    ) -> None:
        """Initialize the builder.

        Args:
            mapping_rules: Per-source-system field name mappings.
                Format: {source_system: {source_field: canonical_field}}
            dedup_tolerance_seconds: Time window for deduplication.
        """
        self._mapping_rules = mapping_rules or {}
        self._dedup_tolerance = timedelta(seconds=dedup_tolerance_seconds)

    def canonicalize(
        self, raw_events: list[dict[str, Any]], source_system: str
    ) -> list[dict[str, Any]]:
        """Normalize raw events from a source system to canonical schema.

        Args:
            raw_events: Raw event dicts from the source system.
            source_system: Identifier for the source system.

        Returns:
            List of dicts in canonical format.
        """
        rules = self._mapping_rules.get(source_system, {})
        canonical_events = []

        for raw in raw_events:
            event = self._apply_mapping(raw, rules, source_system)
            canonical_events.append(event)

        return canonical_events

    def _apply_mapping(
        self,
        raw: dict[str, Any],
        rules: dict[str, str],
        source_system: str,
    ) -> dict[str, Any]:
        """Map a single raw event to canonical format.

        Uses explicit mapping rules if available, falls back to
        direct field name matching for standard fields.
        """
        # Apply field-level mapping rules
        mapped = {}
        for src_field, canon_field in rules.items():
            if src_field in raw:
                mapped[canon_field] = raw[src_field]

        # Standard canonical fields with fallbacks
        event: dict[str, Any] = {
            "case_id": mapped.get("case_id") or raw.get("case_id", ""),
            "activity_name": mapped.get("activity_name") or raw.get("activity_name", ""),
            "timestamp_utc": mapped.get("timestamp_utc") or raw.get("timestamp_utc"),
            "source_system": source_system,
            "performer_role_ref": mapped.get("performer_role_ref") or raw.get("performer_role_ref"),
            "evidence_refs": mapped.get("evidence_refs") or raw.get("evidence_refs"),
            "confidence_score": float(
                mapped.get("confidence_score") or raw.get("confidence_score", 0.0)
            ),
            "brightness": mapped.get("brightness") or raw.get("brightness"),
            "mapping_status": "mapped",
            "process_element_id": mapped.get("process_element_id") or raw.get("process_element_id"),
            "raw_payload": raw,
        }

        # Validate required fields after mapping
        if not event["case_id"]:
            logger.warning("Event missing case_id after mapping from %s: %s", source_system, raw)

        # Check if activity_name mapped to a known process element
        if not event["activity_name"]:
            event["mapping_status"] = "unmapped"
            event["activity_name"] = raw.get("activity_name") or raw.get("name") or "unknown"

        return event

    def deduplicate(
        self, events: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Remove duplicate events, retaining the highest-confidence version.

        Duplicates are identified by (case_id, activity_name) where
        timestamps are within the tolerance window.
        """
        if not events:
            return []

        # Sort by timestamp to group nearby events
        sorted_events = sorted(
            events, key=lambda e: e.get("timestamp_utc") or datetime.min
        )

        deduped: list[dict[str, Any]] = []
        for event in sorted_events:
            merged = False
            for i, existing in enumerate(deduped):
                if self._is_duplicate(existing, event):
                    # Keep the one with higher confidence
                    if event.get("confidence_score", 0) > existing.get("confidence_score", 0):
                        deduped[i] = event
                    merged = True
                    break
            if not merged:
                deduped.append(event)

        return deduped

    def _is_duplicate(
        self, a: dict[str, Any], b: dict[str, Any]
    ) -> bool:
        """Check if two events are duplicates based on key + time tolerance."""
        if a.get("case_id") != b.get("case_id"):
            return False
        if a.get("activity_name") != b.get("activity_name"):
            return False

        ts_a = a.get("timestamp_utc")
        ts_b = b.get("timestamp_utc")
        if ts_a is None or ts_b is None:
            return False

        # Ensure both are datetime objects
        if isinstance(ts_a, str):
            ts_a = datetime.fromisoformat(ts_a)
        if isinstance(ts_b, str):
            ts_b = datetime.fromisoformat(ts_b)

        # Normalize timezone-naive datetimes to UTC for safe comparison
        if ts_a.tzinfo is None:
            ts_a = ts_a.replace(tzinfo=UTC)
        if ts_b.tzinfo is None:
            ts_b = ts_b.replace(tzinfo=UTC)

        return abs(ts_a - ts_b) <= self._dedup_tolerance

    def build_spine(
        self, events: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Build the complete event spine: deduplicate and order by timestamp.

        Args:
            events: Canonicalized events (possibly from multiple sources).

        Returns:
            Deduplicated, chronologically ordered event list.
        """
        deduped = self.deduplicate(events)
        spine = sorted(
            deduped, key=lambda e: e.get("timestamp_utc") or datetime.min
        )
        return spine

    def check_unmapped(
        self,
        events: list[dict[str, Any]],
        known_activities: set[str],
    ) -> list[dict[str, Any]]:
        """Flag events with activity names not in the known set.

        Args:
            events: Canonicalized events.
            known_activities: Set of known activity names.

        Returns:
            Events with mapping_status updated for unmapped activities.
        """
        for event in events:
            if event.get("activity_name") not in known_activities:
                event["mapping_status"] = "unmapped"
        return events
