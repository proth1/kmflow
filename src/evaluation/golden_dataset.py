"""CRUD operations for the golden evaluation dataset.

Provides create/read/update/deactivate operations on GoldenEvalQuery rows,
plus YAML import/export and promotion of copilot feedback corrections.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.auth import CopilotMessage
from src.core.models.pipeline_quality import CopilotFeedback, GoldenEvalQuery


async def create_query(
    session: AsyncSession,
    *,
    query: str,
    expected_answer: str,
    expected_source_ids: list[str],
    query_type: str,
    difficulty: str,
    engagement_id: uuid.UUID | None = None,
    tags: list[str] | None = None,
    source: str = "manual",
) -> GoldenEvalQuery:
    """Create a new golden evaluation query.

    Args:
        session: Async database session.
        query: The question text.
        expected_answer: The reference answer for judge evaluation.
        expected_source_ids: List of evidence_item UUID strings that must be retrieved.
        query_type: Category of query (e.g. "factual", "multi-hop", "comparative").
        difficulty: Difficulty level — "easy", "medium", or "hard".
        engagement_id: Optional engagement scope for the query.
        tags: Optional list of string tags for filtering/grouping.
        source: Origin of the query — "manual", "correction", or "synthetic".

    Returns:
        The newly created GoldenEvalQuery instance (added to session, not yet committed).
    """
    record = GoldenEvalQuery(
        id=uuid.uuid4(),
        engagement_id=engagement_id,
        query=query,
        expected_answer=expected_answer,
        expected_source_ids=expected_source_ids,
        query_type=query_type,
        difficulty=difficulty,
        tags=tags,
        is_active=True,
        source=source,
    )
    session.add(record)
    await session.flush()
    return record


async def list_queries(
    session: AsyncSession,
    engagement_id: uuid.UUID | None = None,
    query_type: str | None = None,
    is_active: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> list[GoldenEvalQuery]:
    """Return a filtered, paginated list of golden queries.

    Args:
        session: Async database session.
        engagement_id: Filter to a specific engagement; None returns all engagements.
        query_type: Filter by query type string; None returns all types.
        is_active: If True, return only active queries.
        limit: Maximum number of records to return.
        offset: Number of records to skip for pagination.

    Returns:
        List of GoldenEvalQuery rows matching the filters.
    """
    stmt = select(GoldenEvalQuery)

    if engagement_id is not None:
        stmt = stmt.where(GoldenEvalQuery.engagement_id == engagement_id)
    if query_type is not None:
        stmt = stmt.where(GoldenEvalQuery.query_type == query_type)
    stmt = stmt.where(GoldenEvalQuery.is_active == is_active)
    stmt = stmt.order_by(GoldenEvalQuery.created_at.desc()).limit(limit).offset(offset)

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_query(session: AsyncSession, query_id: uuid.UUID) -> GoldenEvalQuery | None:
    """Fetch a single golden query by primary key.

    Args:
        session: Async database session.
        query_id: UUID of the GoldenEvalQuery row.

    Returns:
        The GoldenEvalQuery if found, else None.
    """
    stmt = select(GoldenEvalQuery).where(GoldenEvalQuery.id == query_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_query(
    session: AsyncSession,
    query_id: uuid.UUID,
    **kwargs: Any,
) -> GoldenEvalQuery:
    """Update fields on an existing golden query.

    Args:
        session: Async database session.
        query_id: UUID of the GoldenEvalQuery to update.
        **kwargs: Column names and their new values.

    Returns:
        The updated GoldenEvalQuery instance.

    Raises:
        ValueError: If no query with the given ID is found.
    """
    record = await get_query(session, query_id)
    if record is None:
        raise ValueError(f"GoldenEvalQuery {query_id} not found")

    allowed_fields = {
        "query",
        "expected_answer",
        "expected_source_ids",
        "query_type",
        "difficulty",
        "tags",
        "is_active",
        "source",
        "engagement_id",
    }
    for field, value in kwargs.items():
        if field not in allowed_fields:
            raise ValueError(f"Field '{field}' is not updatable on GoldenEvalQuery")
        setattr(record, field, value)

    await session.flush()
    return record


async def deactivate_query(session: AsyncSession, query_id: uuid.UUID) -> None:
    """Mark a golden query as inactive (soft delete).

    Args:
        session: Async database session.
        query_id: UUID of the GoldenEvalQuery to deactivate.

    Raises:
        ValueError: If no query with the given ID is found.
    """
    record = await get_query(session, query_id)
    if record is None:
        raise ValueError(f"GoldenEvalQuery {query_id} not found")
    record.is_active = False
    await session.flush()


async def import_from_yaml(session: AsyncSession, yaml_path: Path) -> int:
    """Import golden queries from a YAML file.

    Expected YAML structure::

        queries:
          - query: "What is the approval SLA?"
            expected_answer: "3 business days"
            expected_source_ids: ["<uuid>", ...]
            query_type: "factual"
            difficulty: "easy"
            engagement_id: "<uuid>"   # optional
            tags: ["sla", "approval"] # optional
            source: "manual"          # optional, defaults to "manual"

    Args:
        session: Async database session.
        yaml_path: Path to the YAML file containing query definitions.

    Returns:
        Number of queries successfully imported.
    """
    with yaml_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    raw_queries: list[dict[str, Any]] = data.get("queries", [])
    count = 0
    for item in raw_queries:
        engagement_id_raw = item.get("engagement_id")
        engagement_id = uuid.UUID(engagement_id_raw) if engagement_id_raw else None

        await create_query(
            session,
            query=item["query"],
            expected_answer=item["expected_answer"],
            expected_source_ids=item["expected_source_ids"],
            query_type=item["query_type"],
            difficulty=item["difficulty"],
            engagement_id=engagement_id,
            tags=item.get("tags"),
            source=item.get("source", "manual"),
        )
        count += 1

    return count


async def export_to_yaml(
    session: AsyncSession,
    engagement_id: uuid.UUID | None = None,
) -> str:
    """Export active golden queries to a YAML string.

    Args:
        session: Async database session.
        engagement_id: If provided, export only queries for this engagement.

    Returns:
        YAML-encoded string of all matching active queries.
    """
    records = await list_queries(session, engagement_id=engagement_id, is_active=True, limit=10_000)

    rows: list[dict[str, Any]] = []
    for rec in records:
        entry: dict[str, Any] = {
            "id": str(rec.id),
            "query": rec.query,
            "expected_answer": rec.expected_answer,
            "expected_source_ids": rec.expected_source_ids,
            "query_type": rec.query_type,
            "difficulty": rec.difficulty,
            "source": rec.source,
        }
        if rec.engagement_id is not None:
            entry["engagement_id"] = str(rec.engagement_id)
        if rec.tags is not None:
            entry["tags"] = rec.tags
        rows.append(entry)

    return yaml.dump({"queries": rows}, allow_unicode=True, sort_keys=False)


async def promote_correction(
    session: AsyncSession,
    feedback_id: uuid.UUID,
) -> GoldenEvalQuery:
    """Create a golden query from a thumbs-down copilot feedback correction.

    Only feedback with rating=1 (thumbs down) and a non-empty correction_text
    is eligible for promotion. The original query is sourced from the linked
    CopilotMessage.

    Args:
        session: Async database session.
        feedback_id: UUID of the CopilotFeedback row to promote.

    Returns:
        Newly created GoldenEvalQuery sourced from the correction.

    Raises:
        ValueError: If the feedback record is not found, has no correction text,
            or was not a thumbs-down rating.
    """
    feedback_stmt = select(CopilotFeedback).where(CopilotFeedback.id == feedback_id)
    feedback_result = await session.execute(feedback_stmt)
    feedback = feedback_result.scalar_one_or_none()

    if feedback is None:
        raise ValueError(f"CopilotFeedback {feedback_id} not found")
    if feedback.rating != 1:
        raise ValueError(f"CopilotFeedback {feedback_id} is not a thumbs-down correction (rating={feedback.rating})")
    if not feedback.correction_text:
        raise ValueError(f"CopilotFeedback {feedback_id} has no correction_text")

    message_stmt = select(CopilotMessage).where(CopilotMessage.id == feedback.copilot_message_id)
    message_result = await session.execute(message_stmt)
    message = message_result.scalar_one_or_none()

    if message is None:
        raise ValueError(f"CopilotMessage {feedback.copilot_message_id} not found for feedback {feedback_id}")

    # Derive expected source IDs from correction_sources if present
    correction_sources: list[str] = []
    if feedback.correction_sources:
        correction_sources = list(feedback.correction_sources) if isinstance(feedback.correction_sources, list) else []

    return await create_query(
        session,
        query=message.content if hasattr(message, "content") else "",
        expected_answer=feedback.correction_text,
        expected_source_ids=correction_sources,
        query_type="correction",
        difficulty="medium",
        engagement_id=feedback.engagement_id,
        tags=["promoted_correction"],
        source="correction",
    )
