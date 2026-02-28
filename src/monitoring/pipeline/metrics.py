"""Pipeline metrics collector for continuous evidence ingestion.

Tracks processing rate, queue depth, latency, and quality metrics
over rolling time windows. Thread-safe via asyncio locks.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Rolling window for metrics aggregation
DEFAULT_WINDOW_SECONDS = 300  # 5 minutes


@dataclass
class ProcessingEvent:
    """A single evidence processing event for metrics tracking."""

    timestamp: float
    latency_ms: float
    quality_score: float
    success: bool = True


@dataclass
class PipelineMetrics:
    """Aggregated pipeline metrics over a rolling window."""

    processing_rate: float = 0.0  # items/min
    queue_depth: int = 0
    p99_latency_ms: float = 0.0
    avg_latency_ms: float = 0.0
    total_processed: int = 0
    total_errors: int = 0
    avg_quality: float = 0.0
    window_seconds: int = DEFAULT_WINDOW_SECONDS


class MetricsCollector:
    """Collects and aggregates pipeline processing metrics.

    Maintains a rolling window of processing events and computes
    aggregated metrics on demand.

    Args:
        window_seconds: Size of the rolling window for aggregation.
    """

    def __init__(self, window_seconds: int = DEFAULT_WINDOW_SECONDS) -> None:
        self._window_seconds = window_seconds
        self._events: deque[ProcessingEvent] = deque()
        self._queue_depth = 0
        self._total_processed = 0
        self._total_errors = 0
        self._lock = asyncio.Lock()

    async def record_event(
        self,
        latency_ms: float,
        quality_score: float,
        success: bool = True,
    ) -> None:
        """Record a single evidence processing event.

        Args:
            latency_ms: Processing latency in milliseconds.
            quality_score: Quality score of the processed evidence.
            success: Whether processing succeeded.
        """
        async with self._lock:
            event = ProcessingEvent(
                timestamp=time.monotonic(),
                latency_ms=latency_ms,
                quality_score=quality_score,
                success=success,
            )
            self._events.append(event)
            self._total_processed += 1
            if not success:
                self._total_errors += 1

    async def set_queue_depth(self, depth: int) -> None:
        """Update the current queue depth."""
        async with self._lock:
            self._queue_depth = depth

    async def get_metrics(self) -> PipelineMetrics:
        """Compute aggregated metrics over the rolling window.

        Returns:
            PipelineMetrics with current aggregations.
        """
        async with self._lock:
            now = time.monotonic()
            cutoff = now - self._window_seconds

            # Prune old events
            while self._events and self._events[0].timestamp < cutoff:
                self._events.popleft()

            events = list(self._events)

        if not events:
            return PipelineMetrics(
                queue_depth=self._queue_depth,
                total_processed=self._total_processed,
                total_errors=self._total_errors,
                window_seconds=self._window_seconds,
            )

        # Processing rate (items per minute)
        window_duration = min(
            time.monotonic() - events[0].timestamp,
            self._window_seconds,
        )
        rate = (len(events) / max(window_duration, 1.0)) * 60.0

        # Latency stats
        latencies = sorted(e.latency_ms for e in events)
        p99_idx = max(0, int(len(latencies) * 0.99) - 1)
        avg_latency = sum(latencies) / len(latencies)

        # Quality stats
        quality_scores = [e.quality_score for e in events if e.quality_score > 0]
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0

        return PipelineMetrics(
            processing_rate=round(rate, 2),
            queue_depth=self._queue_depth,
            p99_latency_ms=round(latencies[p99_idx], 2),
            avg_latency_ms=round(avg_latency, 2),
            total_processed=self._total_processed,
            total_errors=self._total_errors,
            avg_quality=round(avg_quality, 4),
            window_seconds=self._window_seconds,
        )
