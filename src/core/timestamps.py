"""Shared timestamp parsing utilities."""

from __future__ import annotations

from datetime import UTC, datetime


def parse_timestamp(value: str | datetime | None) -> datetime | None:
    """Parse a timestamp string into a timezone-aware datetime.

    Supports ISO 8601 format. Returns None for None input.

    Args:
        value: A datetime object, ISO 8601 string, or None.

    Returns:
        Timezone-aware datetime, or None if value is None or unparseable.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    if isinstance(value, str) and not value:
        return None
    # Try ISO format first
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        pass
    # Additional formats as fallback
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=UTC)
        except ValueError:
            continue
    return None
