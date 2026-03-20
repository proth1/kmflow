"""Evidence batch processing worker (KMFLOW-58).

Processes batches of evidence items asynchronously.  Each batch runs
the full pipeline: classify → parse → fragment → store → intelligence
for every item, reporting per-item progress.

Payload::

    {
        "engagement_id": "uuid-string",
        "evidence_item_ids": ["uuid-1", "uuid-2", ...],
    }
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.tasks.base import TaskWorker

logger = logging.getLogger(__name__)


class EvidenceBatchWorker(TaskWorker):
    """Process a batch of evidence items through the ingestion pipeline.

    Reports progress as each item completes so callers can track
    per-item status via the polling API.
    """

    task_type = "evidence_batch"
    max_retries = 3

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute evidence batch processing.

        Args:
            payload: Must contain ``engagement_id`` and ``evidence_item_ids``.

        Returns:
            Summary dict with processed/failed counts and per-item results.

        Raises:
            ValueError: If required fields are missing.
        """
        engagement_id = payload.get("engagement_id", "")
        item_ids: list[str] = payload.get("evidence_item_ids", [])

        if not engagement_id:
            raise ValueError("engagement_id is required in payload")
        if not item_ids:
            raise ValueError("evidence_item_ids must be a non-empty list")

        total = len(item_ids)
        self.report_progress(0, total)

        processed = 0
        failed = 0
        results: list[dict[str, Any]] = []

        # Lazy imports to avoid circular dependencies
        from src.core.database import async_session_factory  # type: ignore[attr-defined]

        async with async_session_factory() as session:
            for i, item_id in enumerate(item_ids):
                try:
                    result = await self._process_item(session, engagement_id, item_id)
                    results.append({"item_id": item_id, "status": "completed", **result})
                    processed += 1
                except Exception as exc:  # Intentionally broad: top-level error boundary for per-item isolation
                    logger.warning(
                        "Evidence batch: item %s failed: %s",
                        item_id,
                        exc,
                    )
                    results.append({"item_id": item_id, "status": "failed", "error": str(exc)})
                    failed += 1

                self.report_progress(i + 1, total)

            await session.commit()

        logger.info(
            "Evidence batch complete for engagement %s: %d processed, %d failed",
            engagement_id,
            processed,
            failed,
        )

        return {
            "engagement_id": engagement_id,
            "total": total,
            "processed": processed,
            "failed": failed,
            "items": results,
        }

    async def _process_item(
        self,
        session: AsyncSession,
        engagement_id: str,
        item_id: str,
    ) -> dict[str, Any]:
        """Process a single evidence item through the intelligence pipeline.

        Loads the item's fragments from the DB and runs entity extraction,
        graph building, embedding generation, and semantic bridge.

        Args:
            session: Async database session.
            engagement_id: The engagement this evidence belongs to.
            item_id: UUID of the EvidenceItem to process.

        Returns:
            Dict with processing results (entities_extracted, etc.).
        """
        from sqlalchemy import select

        from src.core.models import EvidenceFragment, EvidenceItem

        result = await session.execute(
            select(EvidenceItem).where(
                EvidenceItem.id == item_id,
                EvidenceItem.engagement_id == engagement_id,
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise ValueError(f"Evidence item {item_id} not found in engagement {engagement_id}")

        # Mark as processing
        item.status = "processing"
        await session.flush()

        # Load fragments for this evidence item
        frag_result = await session.execute(select(EvidenceFragment).where(EvidenceFragment.evidence_id == item.id))
        fragments = list(frag_result.scalars().all())

        # Run intelligence pipeline on fragments
        from src.evidence.pipeline import run_intelligence_pipeline

        intel_result = await run_intelligence_pipeline(session, fragments, engagement_id)

        item.status = "completed"
        await session.flush()

        return {
            "fragments_processed": len(fragments),
            "entities_extracted": intel_result.get("entities_extracted", 0),
            "graph_nodes": intel_result.get("graph_nodes", 0),
        }
