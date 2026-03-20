"""Singleton metrics collector for pipeline stage events."""

from __future__ import annotations

import threading
import uuid
from collections import deque
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.pipeline_quality import PipelineStageMetric
from src.quality.instrumentation import PipelineStageEvent

_MAX_BUFFER_SIZE = 100


class MetricsCollector:
    """Thread-safe singleton that buffers :class:`PipelineStageEvent` objects.

    Events are buffered in memory and written to the database in bulk when
    :meth:`flush` is called.  When the buffer reaches ``_MAX_BUFFER_SIZE`` the
    oldest entry is dropped to make room for the newest one (ring-buffer
    behaviour), preventing unbounded memory growth between explicit flushes.

    Flushing is the caller's responsibility — no background thread is used so
    that the collector stays compatible with both synchronous and async
    execution contexts.
    """

    _instance: MetricsCollector | None = None
    _init_lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        # deque(maxlen=N) discards from the left (oldest) in O(1) when full,
        # unlike list.pop(0) which is O(n).
        self._buffer: deque[PipelineStageEvent] = deque(maxlen=_MAX_BUFFER_SIZE)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Singleton access
    # ------------------------------------------------------------------

    @classmethod
    def instance(cls) -> MetricsCollector:
        """Return the process-wide singleton, creating it on first call."""
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(self, event: PipelineStageEvent) -> None:
        """Append *event* to the in-memory buffer.

        When the buffer is already at capacity the oldest event is silently
        discarded to maintain the fixed upper bound (deque maxlen handles this).
        """
        with self._lock:
            self._buffer.append(event)

    # ------------------------------------------------------------------
    # Flushing
    # ------------------------------------------------------------------

    async def flush(self, session: AsyncSession) -> int:
        """Bulk-insert all buffered events into the database then clear the buffer.

        Args:
            session: An open async SQLAlchemy session.  The caller is
                responsible for committing the transaction.

        Returns:
            The number of rows inserted.
        """
        with self._lock:
            events = list(self._buffer)
            self._buffer.clear()

        if not events:
            return 0

        metrics = [_event_to_model(event) for event in events]
        session.add_all(metrics)
        await session.flush()
        return len(metrics)

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    @classmethod
    async def get_stage_summary(
        cls,
        session: AsyncSession,
        engagement_id: str | uuid.UUID,
        stage: str | None = None,
        since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Return aggregated pipeline metrics from the database.

        Groups results by stage and returns one dict per stage containing
        average duration, total input/output counts, total errors, and
        execution count.

        Args:
            session: An open async SQLAlchemy session.
            engagement_id: Filter results to this engagement.
            stage: When provided, restrict results to a single stage name.
            since: When provided, restrict results to rows whose
                ``started_at`` is at or after this timestamp.  The value
                should be timezone-aware; if it is naive it is treated as UTC.

        Returns:
            A list of dicts with keys: ``stage``, ``execution_count``,
            ``avg_duration_ms``, ``total_input``, ``total_output``,
            ``total_errors``.
        """
        engagement_uuid = uuid.UUID(str(engagement_id)) if not isinstance(engagement_id, uuid.UUID) else engagement_id

        stmt = (
            select(
                PipelineStageMetric.stage,
                func.count(PipelineStageMetric.id).label("execution_count"),
                func.avg(PipelineStageMetric.duration_ms).label("avg_duration_ms"),
                func.sum(PipelineStageMetric.input_count).label("total_input"),
                func.sum(PipelineStageMetric.output_count).label("total_output"),
                func.sum(PipelineStageMetric.error_count).label("total_errors"),
            )
            .where(PipelineStageMetric.engagement_id == engagement_uuid)
            .group_by(PipelineStageMetric.stage)
            .order_by(PipelineStageMetric.stage)
        )

        if stage is not None:
            stmt = stmt.where(PipelineStageMetric.stage == stage)

        if since is not None:
            since_aware = since if since.tzinfo is not None else since.replace(tzinfo=UTC)
            stmt = stmt.where(PipelineStageMetric.started_at >= since_aware)

        result = await session.execute(stmt)
        rows = result.all()

        return [
            {
                "stage": row.stage,
                "execution_count": row.execution_count,
                "avg_duration_ms": float(row.avg_duration_ms) if row.avg_duration_ms is not None else 0.0,
                "total_input": int(row.total_input) if row.total_input is not None else 0,
                "total_output": int(row.total_output) if row.total_output is not None else 0,
                "total_errors": int(row.total_errors) if row.total_errors is not None else 0,
            }
            for row in rows
        ]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _event_to_model(event: PipelineStageEvent) -> PipelineStageMetric:
    """Convert a :class:`PipelineStageEvent` to a :class:`PipelineStageMetric` ORM instance."""
    engagement_uuid: uuid.UUID | None = None
    if event.engagement_id is not None:
        try:
            engagement_uuid = uuid.UUID(event.engagement_id)
        except ValueError:
            engagement_uuid = None

    evidence_uuid: uuid.UUID | None = None
    if event.evidence_item_id is not None:
        try:
            evidence_uuid = uuid.UUID(event.evidence_item_id)
        except ValueError:
            evidence_uuid = None

    return PipelineStageMetric(
        engagement_id=engagement_uuid,
        evidence_item_id=evidence_uuid,
        stage=event.stage,
        started_at=event.started_at,
        duration_ms=event.duration_ms,
        input_count=event.input_count,
        output_count=event.output_count,
        error_count=event.error_count,
        error_type=event.error_type,
        metadata_json=event.metadata,
    )
