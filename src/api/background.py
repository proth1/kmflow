"""Shared background task tracking to prevent GC cancellation.

Asyncio tasks that are not awaited can be garbage-collected before completion.
This module provides a module-level strong-reference set and a helper to track
fire-and-forget tasks safely.
"""

from __future__ import annotations

import asyncio

_background_tasks: set[asyncio.Task[None]] = set()


def track_background_task(task: asyncio.Task[None]) -> None:
    """Track a background task to prevent GC. Removes itself when done."""
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
