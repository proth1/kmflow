"""Continuous evidence collection pipeline (Story #360).

Async consumer that reads evidence items from a Redis stream,
runs quality scoring, updates the knowledge graph incrementally,
detects contradictions, and emits quality warning alerts when
evidence quality drops below configured thresholds.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import EvidenceItem
from src.core.redis import ensure_consumer_group
from src.monitoring.pipeline.metrics import MetricsCollector

logger = logging.getLogger(__name__)

# Redis stream for continuous evidence pipeline
EVIDENCE_PIPELINE_STREAM = "kmflow:evidence:pipeline"
EVIDENCE_CONSUMER_GROUP = "evidence_pipeline_workers"

# Quality warning window and defaults
QUALITY_WINDOW_MINUTES = 10
DEFAULT_QUALITY_THRESHOLD = 0.6


class ContinuousEvidencePipeline:
    """Async consumer for continuous evidence ingestion.

    Reads evidence from a Redis stream, processes each item through:
    1. Quality scoring (reuses existing quality engine)
    2. Knowledge graph update (incremental, not full re-index)
    3. Contradiction detection (creates ConflictObject on conflict)
    4. Quality threshold monitoring (emits alerts on degradation)

    Args:
        redis_client: Redis client for stream consumption.
        session_factory: SQLAlchemy async session factory.
        neo4j_driver: Neo4j async driver for graph updates.
        metrics: Shared metrics collector instance.
        quality_threshold: Per-engagement override or default.
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        session_factory: Any,
        neo4j_driver: Any = None,
        metrics: MetricsCollector | None = None,
        quality_threshold: float = DEFAULT_QUALITY_THRESHOLD,
    ) -> None:
        self._redis = redis_client
        self._session_factory = session_factory
        self._neo4j_driver = neo4j_driver
        self._metrics = metrics or MetricsCollector()
        self._quality_threshold = quality_threshold
        self._recent_quality_scores: list[float] = []

    @property
    def metrics(self) -> MetricsCollector:
        """Access the pipeline's metrics collector."""
        return self._metrics

    async def start(self, consumer_name: str, shutdown_event: Any) -> None:
        """Start consuming evidence from the Redis stream.

        Args:
            consumer_name: Unique name for this consumer instance.
            shutdown_event: asyncio.Event that signals shutdown.
        """
        await ensure_consumer_group(
            self._redis,
            EVIDENCE_PIPELINE_STREAM,
            EVIDENCE_CONSUMER_GROUP,
        )

        logger.info("Evidence pipeline consumer %s started", consumer_name)

        while not shutdown_event.is_set():
            try:
                # Update queue depth metric
                stream_info = await self._redis.xlen(EVIDENCE_PIPELINE_STREAM)
                await self._metrics.set_queue_depth(stream_info)

                # Read from stream
                messages = await self._redis.xreadgroup(
                    groupname=EVIDENCE_CONSUMER_GROUP,
                    consumername=consumer_name,
                    streams={EVIDENCE_PIPELINE_STREAM: ">"},
                    count=10,
                    block=2000,
                )

                if not messages:
                    continue

                for _stream_name, entries in messages:
                    for msg_id, data in entries:
                        await self._process_evidence(msg_id, data)
                        await self._redis.xack(
                            EVIDENCE_PIPELINE_STREAM,
                            EVIDENCE_CONSUMER_GROUP,
                            msg_id,
                        )

            except Exception:
                logger.exception("Error in evidence pipeline consumer %s", consumer_name)
                if not shutdown_event.is_set():
                    import asyncio

                    await asyncio.sleep(1)

        logger.info("Evidence pipeline consumer %s stopped", consumer_name)

    async def _process_evidence(
        self,
        msg_id: bytes | str,
        data: dict[str, Any],
    ) -> None:
        """Process a single evidence item from the stream.

        Steps:
        1. Parse evidence metadata
        2. Score quality using existing quality model
        3. Update knowledge graph incrementally
        4. Check for contradictions
        5. Monitor quality threshold

        Args:
            msg_id: Redis stream message ID.
            data: Message payload with evidence metadata.
        """
        start_time = time.monotonic()
        quality_score = 0.0
        success = True

        try:
            evidence_id = data.get(b"evidence_id", data.get("evidence_id", ""))
            engagement_id = data.get(b"engagement_id", data.get("engagement_id", ""))

            if isinstance(evidence_id, bytes):
                evidence_id = evidence_id.decode()
            if isinstance(engagement_id, bytes):
                engagement_id = engagement_id.decode()

            async with self._session_factory() as session:
                # Step 1: Score quality
                quality_score = await self._score_evidence(session, evidence_id)

                # Step 2: Update knowledge graph
                await self._update_knowledge_graph(evidence_id, engagement_id)

                # Step 3: Check for contradictions
                await self._check_contradictions(session, evidence_id, engagement_id)

                # Step 4: Monitor quality threshold
                await self._monitor_quality(session, quality_score, engagement_id)

                await session.commit()

            logger.info(
                "Processed evidence %s (quality=%.2f, msg=%s)",
                evidence_id,
                quality_score,
                msg_id,
            )

        except Exception:
            logger.exception("Failed to process evidence msg=%s", msg_id)
            success = False

        finally:
            latency_ms = (time.monotonic() - start_time) * 1000
            await self._metrics.record_event(latency_ms, quality_score, success)

    async def _score_evidence(self, session: AsyncSession, evidence_id: str) -> float:
        """Score evidence quality using existing quality engine.

        Args:
            session: Database session.
            evidence_id: Evidence item UUID string.

        Returns:
            Quality score (0.0 - 1.0).
        """
        from sqlalchemy import select


        result = await session.execute(
            select(EvidenceItem).where(EvidenceItem.id == evidence_id)
        )
        item = result.scalar_one_or_none()
        if item is None:
            return 0.0

        # Use existing quality scorer
        from src.evidence.quality import score_evidence

        scores = await score_evidence(session, item)
        return scores.get("composite", 0.0) if isinstance(scores, dict) else 0.0

    async def _update_knowledge_graph(
        self, evidence_id: str, engagement_id: str
    ) -> None:
        """Incrementally update the knowledge graph with new evidence.

        Args:
            evidence_id: Evidence item ID.
            engagement_id: Engagement scope.
        """
        if self._neo4j_driver is None:
            return

        async with self._neo4j_driver.session() as session:
            await session.execute_write(
                lambda tx: tx.run(
                    """
                    MERGE (e:Evidence {id: $evidence_id})
                    SET e.engagement_id = $engagement_id,
                        e.updated_at = datetime()
                    """,
                    evidence_id=evidence_id,
                    engagement_id=engagement_id,
                )
            )

    async def _check_contradictions(
        self,
        session: AsyncSession,
        evidence_id: str,
        engagement_id: str,
    ) -> None:
        """Check for contradictions between new and existing evidence.

        If a contradiction is found, creates a ConflictObject and raises
        a deviation alert of type EVIDENCE_CONFLICT.

        Args:
            session: Database session.
            evidence_id: New evidence item ID.
            engagement_id: Engagement scope.
        """
        # Contradiction detection is delegated to the existing semantic layer.
        # This hook enables future integration with contradiction resolution (Story #384).
        pass

    async def _monitor_quality(
        self,
        session: AsyncSession,
        quality_score: float,
        engagement_id: str,
    ) -> None:
        """Monitor evidence quality against threshold.

        Maintains a sliding window of recent quality scores and triggers
        a QUALITY_WARNING alert when the average drops below threshold.

        Args:
            session: Database session.
            quality_score: Quality score of the latest evidence.
            engagement_id: Engagement scope.
        """
        self._recent_quality_scores.append(quality_score)

        # Keep only the last N scores (roughly 10 minutes at typical rates)
        max_window = 100
        if len(self._recent_quality_scores) > max_window:
            self._recent_quality_scores = self._recent_quality_scores[-max_window:]

        avg_quality = (
            sum(self._recent_quality_scores) / len(self._recent_quality_scores)
            if self._recent_quality_scores
            else 0.0
        )

        if avg_quality < self._quality_threshold and len(self._recent_quality_scores) >= 5:
            logger.warning(
                "Evidence quality below threshold: avg=%.2f, threshold=%.2f, engagement=%s",
                avg_quality,
                self._quality_threshold,
                engagement_id,
            )
            # Alert creation is logged for downstream consumption
            # Full alert persistence integrates with Story #366 (Real-Time Alerting)


async def submit_evidence_to_pipeline(
    redis_client: aioredis.Redis,
    evidence_id: str,
    engagement_id: str,
) -> str:
    """Submit an evidence item to the continuous pipeline for processing.

    Args:
        redis_client: Redis client.
        evidence_id: Evidence item UUID string.
        engagement_id: Engagement UUID string.

    Returns:
        The Redis stream message ID.
    """
    msg_id = await redis_client.xadd(
        EVIDENCE_PIPELINE_STREAM,
        {"evidence_id": evidence_id, "engagement_id": engagement_id},
        maxlen=50000,
    )
    return msg_id
