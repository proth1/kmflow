"""Cron-based scheduling for monitoring jobs.

Manages scheduling of monitoring collection tasks using cron expressions.
Calculates next run times and determines which jobs need execution.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


def parse_cron_field(field: str, min_val: int, max_val: int) -> set[int]:
    """Parse a single cron field into a set of valid values."""
    values: set[int] = set()
    for part in field.split(","):
        if "/" in part:
            base, step = part.split("/", 1)
            step_val = int(step)
            start = min_val if base == "*" else int(base)
            for v in range(start, max_val + 1, step_val):
                values.add(v)
        elif "-" in part:
            lo, hi = part.split("-", 1)
            for v in range(int(lo), int(hi) + 1):
                values.add(v)
        elif part == "*":
            values.update(range(min_val, max_val + 1))
        else:
            values.add(int(part))
    return values


def should_run_now(cron_expr: str, now: datetime | None = None) -> bool:
    """Check if a cron expression matches the current time.

    Args:
        cron_expr: 5-field cron expression (minute hour dom month dow).
        now: Optional current time (defaults to UTC now).

    Returns:
        True if the cron matches the current minute.
    """
    if now is None:
        now = datetime.now(UTC)

    fields = cron_expr.strip().split()
    if len(fields) != 5:
        return False

    minutes = parse_cron_field(fields[0], 0, 59)
    hours = parse_cron_field(fields[1], 0, 23)
    doms = parse_cron_field(fields[2], 1, 31)
    months = parse_cron_field(fields[3], 1, 12)
    dows = parse_cron_field(fields[4], 0, 6)

    return (
        now.minute in minutes
        and now.hour in hours
        and now.day in doms
        and now.month in months
        and now.weekday() in dows  # Python weekday: Mon=0, Sun=6
    )


def calculate_next_run(cron_expr: str, from_time: datetime | None = None) -> datetime | None:
    """Calculate the next run time for a cron expression.

    Simple implementation that checks the next 1440 minutes (24 hours).
    """
    if from_time is None:
        from_time = datetime.now(UTC)

    from datetime import timedelta

    for minutes_ahead in range(1, 1441):
        candidate = from_time + timedelta(minutes=minutes_ahead)
        candidate = candidate.replace(second=0, microsecond=0)
        if should_run_now(cron_expr, candidate):
            return candidate

    return None
