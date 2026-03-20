"""Shared test helpers for the KMFlow test suite."""

from __future__ import annotations

import asyncio
from collections.abc import Callable


async def wait_for_condition(
    condition_fn: Callable[[], bool],
    timeout: float = 5.0,
    interval: float = 0.05,
    message: str = "Condition not met",
) -> None:
    """Wait for a condition to become True, checking at regular intervals.

    Args:
        condition_fn: Callable that returns True when the condition is satisfied.
        timeout: Maximum seconds to wait before raising AssertionError.
        interval: Seconds between condition checks.
        message: Error message prefix if condition is not met in time.

    Raises:
        AssertionError: If the condition is not met within the timeout.
    """
    elapsed = 0.0
    while elapsed < timeout:
        if condition_fn():
            return
        await asyncio.sleep(interval)
        elapsed += interval
    raise AssertionError(f"{message} (waited {timeout}s)")
