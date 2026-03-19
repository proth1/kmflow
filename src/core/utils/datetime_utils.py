"""Shared datetime parsing utilities."""

from __future__ import annotations

from datetime import datetime


def parse_iso_timestamp(value: str | datetime) -> datetime:
    """Parse an ISO 8601 timestamp string or return a datetime as-is.

    Handles the common ``Z`` suffix by rewriting it to ``+00:00`` before
    calling :func:`datetime.fromisoformat`.

    Args:
        value: A :class:`datetime` instance (returned unchanged) or an
            ISO 8601 string (with optional ``Z`` or ``+HH:MM`` suffix).

    Returns:
        A timezone-aware or naive :class:`datetime` as encoded in *value*.

    Raises:
        ValueError: If *value* is a string that cannot be parsed as ISO 8601.
    """
    if isinstance(value, datetime):
        return value
    ts_clean = value.replace("Z", "+00:00")
    return datetime.fromisoformat(ts_clean)
