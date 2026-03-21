"""Compensation job for failed dual-writes (PostgreSQL → Neo4j).

When a write to Neo4j fails after the primary PostgreSQL write has already
committed, the failure is recorded in ``dual_write_failures``. This module
provides a retry job that re-executes the Neo4j write based on the failure
record's source table and source ID.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.dual_write_failure import DualWriteFailure

logger = logging.getLogger(__name__)


async def retry_dual_write_failures(
    session: AsyncSession,
    neo4j_driver: Any,  # Any because: neo4j.AsyncDriver; avoids circular import
) -> int:
    """Retry failed dual-writes. Returns count of successful retries.

    Fetches up to 100 unretried DualWriteFailure records and re-executes
    the corresponding Neo4j write. Each failure specifies a ``source_table``
    and ``source_id`` that identify which PostgreSQL row needs to be
    synced back to the graph.

    Args:
        session: Database session for reading and updating failure records.
        neo4j_driver: Neo4j async driver for graph writes.

    Returns:
        Number of failures successfully retried.
    """
    result = await session.execute(
        select(DualWriteFailure)
        .where(DualWriteFailure.retried == False)  # noqa: E712
        .order_by(DualWriteFailure.created_at)
        .limit(100)
    )
    failures = result.scalars().all()

    if not failures:
        logger.debug("No dual-write failures to retry")
        return 0

    retried = 0
    for failure in failures:
        try:
            await _replay_graph_write(session, neo4j_driver, failure)
            failure.retried = True
            retried += 1
        except Exception:  # Intentionally broad: compensation best-effort
            logger.warning(
                "Compensation retry failed for %s id=%s target=%s",
                failure.source_table,
                failure.source_id,
                failure.target,
            )

    await session.commit()
    logger.info("Dual-write compensation: retried %d / %d failures", retried, len(failures))
    return retried


async def _replay_graph_write(
    session: AsyncSession,
    neo4j_driver: Any,  # Any because: neo4j.AsyncDriver
    failure: DualWriteFailure,
) -> None:
    """Re-execute the Neo4j write identified by the failure record.

    Dispatches to source-table-specific write helpers. Raises on failure
    so the caller can log and skip without marking as retried.
    """
    from src.semantic.graph import KnowledgeGraphService

    graph = KnowledgeGraphService(neo4j_driver)

    if failure.source_table == "evidence_items":
        await _replay_evidence_node(session, graph, failure.source_id)
    elif failure.source_table == "process_elements":
        await _replay_process_element_node(session, graph, failure.source_id)
    else:
        # Generic fallback: log and treat as retried to avoid infinite loops
        logger.warning(
            "No replay handler for source_table=%s — marking as retried without write",
            failure.source_table,
        )


async def _replay_evidence_node(
    session: AsyncSession,
    graph: Any,  # Any because: KnowledgeGraphService; avoid circular import at module level
    source_id: str,
) -> None:
    """Re-ingest an evidence item node into Neo4j."""
    from src.core.models import EvidenceItem

    result = await session.execute(select(EvidenceItem).where(EvidenceItem.id == source_id))
    item = result.scalar_one_or_none()
    if item is None:
        logger.warning("Evidence item %s not found; skipping graph write", source_id)
        return

    await graph.upsert_node(
        "Evidence",
        {
            "id": str(item.id),
            "name": item.name,
            "engagement_id": str(item.engagement_id),
            "category": str(item.category),
            "format": item.format,
            "source": "compensation_retry",
        },
    )


async def _replay_process_element_node(
    session: AsyncSession,
    graph: Any,  # Any because: KnowledgeGraphService; avoid circular import at module level
    source_id: str,
) -> None:
    """Re-ingest a process element node into Neo4j."""
    from src.core.models import ProcessElement

    result = await session.execute(select(ProcessElement).where(ProcessElement.id == source_id))
    elem = result.scalar_one_or_none()
    if elem is None:
        logger.warning("ProcessElement %s not found; skipping graph write", source_id)
        return

    await graph.upsert_node(
        "Activity",
        {
            "id": str(elem.id),
            "name": elem.name,
            "engagement_id": str(elem.model.engagement_id) if hasattr(elem, "model") else "",
            "confidence_score": elem.confidence_score,
            "source": "compensation_retry",
        },
    )
