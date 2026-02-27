"""Sequence and Role Conflict Detection Engine (Story #372).

Detects cross-source conflicts in the knowledge graph:
- Sequence mismatches: contradictory PRECEDES edges (A→B vs B→A)
- Role mismatches: different PERFORMED_BY assignments for same activity

Each detected conflict creates a ConflictObject with severity scoring
based on source weights and recency.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import ConflictObject, MismatchType, ResolutionStatus

logger = logging.getLogger(__name__)

# Severity label thresholds
SEVERITY_CRITICAL = 0.8
SEVERITY_HIGH = 0.6
SEVERITY_MEDIUM = 0.4


def severity_label(score: float) -> str:
    """Map a severity score to a human-readable label."""
    if score >= SEVERITY_CRITICAL:
        return "critical"
    elif score >= SEVERITY_HIGH:
        return "high"
    elif score >= SEVERITY_MEDIUM:
        return "medium"
    return "low"


def compute_severity(
    weight_a: float,
    weight_b: float,
    created_a: datetime | None = None,
    created_b: datetime | None = None,
    recency_window_days: int = 30,
) -> float:
    """Compute conflict severity from source weights and recency.

    Higher weight differential with a more recent high-authority source
    means LOWER severity (the conflict is less ambiguous).
    Similar weights means HIGHER severity (genuinely ambiguous).

    Args:
        weight_a: Source A authority weight (0-1).
        weight_b: Source B authority weight (0-1).
        created_a: Source A creation timestamp.
        created_b: Source B creation timestamp.
        recency_window_days: Window for recency bonus.

    Returns:
        Severity score between 0.0 and 1.0.
    """
    weight_diff = abs(weight_a - weight_b)

    # Base severity: 1 - weight_diff (similar weights → high severity)
    base_severity = 1.0 - weight_diff

    # Recency factor: if the higher-authority source is recent, lower severity
    recency_factor = 1.0
    if created_a and created_b:
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=recency_window_days)
        high_source_time = created_a if weight_a >= weight_b else created_b
        if high_source_time >= cutoff:
            # More recent high-authority source → reduce severity by up to 20%
            days_ago = (now - high_source_time).total_seconds() / 86400
            freshness = max(0.0, 1.0 - (days_ago / recency_window_days))
            recency_factor = 1.0 - (0.2 * freshness)

    severity = base_severity * recency_factor
    return round(max(0.0, min(1.0, severity)), 4)


@dataclass
class DetectedConflict:
    """A conflict detected during analysis."""

    mismatch_type: MismatchType
    engagement_id: str
    source_a_id: str
    source_b_id: str
    severity_score: float
    severity_label: str
    detail: str = ""
    edge_a_data: dict[str, Any] = field(default_factory=dict)
    edge_b_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class DetectionResult:
    """Result of a conflict detection run."""

    engagement_id: str
    conflicts: list[DetectedConflict] = field(default_factory=list)
    sequences_checked: int = 0
    roles_checked: int = 0

    @property
    def total_conflicts(self) -> int:
        return len(self.conflicts)


class SequenceConflictDetector:
    """Detect sequence mismatches in the knowledge graph.

    Finds contradictory PRECEDES edges: (A)-[:PRECEDES]->(B)
    and (B)-[:PRECEDES]->(A) from different sources.
    """

    def __init__(self, graph_service: Any) -> None:
        self._graph = graph_service

    async def detect(self, engagement_id: str) -> list[DetectedConflict]:
        """Find sequence mismatches for an engagement.

        Queries Neo4j for pairs of PRECEDES edges that contradict each other.
        """
        conflicts: list[DetectedConflict] = []

        try:
            records = await self._graph.run_query(
                """
                MATCH (a:Activity)-[r1:PRECEDES]->(b:Activity)
                WHERE r1.engagement_id = $engagement_id
                WITH a, b, r1
                MATCH (b)-[r2:PRECEDES]->(a)
                WHERE r2.engagement_id = $engagement_id
                  AND r1.source_id <> r2.source_id
                  AND id(a) < id(b)
                RETURN
                    a.name AS activity_a,
                    b.name AS activity_b,
                    r1.source_id AS source_a_id,
                    r2.source_id AS source_b_id,
                    r1.source_weight AS weight_a,
                    r2.source_weight AS weight_b,
                    r1.created_at AS created_a,
                    r2.created_at AS created_b
                """,
                {"engagement_id": engagement_id},
            )
        except Exception:
            logger.exception("Failed to query sequence conflicts for %s", engagement_id)
            return conflicts

        for record in records:
            weight_a = float(record.get("weight_a", 0.5) or 0.5)
            weight_b = float(record.get("weight_b", 0.5) or 0.5)
            created_a = record.get("created_a")
            created_b = record.get("created_b")

            score = compute_severity(weight_a, weight_b, created_a, created_b)
            label = severity_label(score)

            conflicts.append(
                DetectedConflict(
                    mismatch_type=MismatchType.SEQUENCE_MISMATCH,
                    engagement_id=engagement_id,
                    source_a_id=str(record.get("source_a_id", "")),
                    source_b_id=str(record.get("source_b_id", "")),
                    severity_score=score,
                    severity_label=label,
                    detail=f"Contradictory sequence: {record.get('activity_a')} ↔ {record.get('activity_b')}",
                    edge_a_data={"from": record.get("activity_a"), "to": record.get("activity_b")},
                    edge_b_data={"from": record.get("activity_b"), "to": record.get("activity_a")},
                )
            )

        return conflicts


class RoleConflictDetector:
    """Detect role mismatches in the knowledge graph.

    Finds activities with multiple PERFORMED_BY edges pointing to
    different roles from different source evidence items.
    """

    def __init__(self, graph_service: Any) -> None:
        self._graph = graph_service

    async def detect(self, engagement_id: str) -> list[DetectedConflict]:
        """Find role mismatches for an engagement."""
        conflicts: list[DetectedConflict] = []

        try:
            records = await self._graph.run_query(
                """
                MATCH (act:Activity)-[r1:PERFORMED_BY]->(role1:Role)
                WHERE r1.engagement_id = $engagement_id
                WITH act, r1, role1
                MATCH (act)-[r2:PERFORMED_BY]->(role2:Role)
                WHERE r2.engagement_id = $engagement_id
                  AND r1.source_id <> r2.source_id
                  AND role1.name <> role2.name
                  AND id(r1) < id(r2)
                RETURN
                    act.name AS activity_name,
                    role1.name AS role_a,
                    role2.name AS role_b,
                    r1.source_id AS source_a_id,
                    r2.source_id AS source_b_id,
                    r1.source_weight AS weight_a,
                    r2.source_weight AS weight_b,
                    r1.created_at AS created_a,
                    r2.created_at AS created_b
                """,
                {"engagement_id": engagement_id},
            )
        except Exception:
            logger.exception("Failed to query role conflicts for %s", engagement_id)
            return conflicts

        for record in records:
            weight_a = float(record.get("weight_a", 0.5) or 0.5)
            weight_b = float(record.get("weight_b", 0.5) or 0.5)
            created_a = record.get("created_a")
            created_b = record.get("created_b")

            score = compute_severity(weight_a, weight_b, created_a, created_b)
            label = severity_label(score)

            conflicts.append(
                DetectedConflict(
                    mismatch_type=MismatchType.ROLE_MISMATCH,
                    engagement_id=engagement_id,
                    source_a_id=str(record.get("source_a_id", "")),
                    source_b_id=str(record.get("source_b_id", "")),
                    severity_score=score,
                    severity_label=label,
                    detail=(
                        f"Role mismatch for '{record.get('activity_name')}': "
                        f"{record.get('role_a')} vs {record.get('role_b')}"
                    ),
                    edge_a_data={"activity": record.get("activity_name"), "role": record.get("role_a")},
                    edge_b_data={"activity": record.get("activity_name"), "role": record.get("role_b")},
                )
            )

        return conflicts


async def run_conflict_detection(
    graph_service: Any,
    session: AsyncSession,
    engagement_id: str,
) -> DetectionResult:
    """Run full conflict detection pipeline for an engagement.

    Detects both sequence and role mismatches, persists new conflicts
    as ConflictObjects (idempotent — skips duplicates).

    Args:
        graph_service: Knowledge graph service for Cypher queries.
        session: Database session for persisting ConflictObjects.
        engagement_id: The engagement to analyze.

    Returns:
        DetectionResult with all detected conflicts.
    """
    result = DetectionResult(engagement_id=engagement_id)

    # Detect sequence mismatches
    seq_detector = SequenceConflictDetector(graph_service)
    seq_conflicts = await seq_detector.detect(engagement_id)
    result.conflicts.extend(seq_conflicts)
    result.sequences_checked = len(seq_conflicts)

    # Detect role mismatches
    role_detector = RoleConflictDetector(graph_service)
    role_conflicts = await role_detector.detect(engagement_id)
    result.conflicts.extend(role_conflicts)
    result.roles_checked = len(role_conflicts)

    # Persist new conflicts (idempotent: check for existing by source pair + type)
    eng_uuid = uuid.UUID(engagement_id) if isinstance(engagement_id, str) else engagement_id
    persisted = 0

    for conflict in result.conflicts:
        # Check for existing conflict with same sources and type
        src_a = uuid.UUID(conflict.source_a_id) if conflict.source_a_id else None
        src_b = uuid.UUID(conflict.source_b_id) if conflict.source_b_id else None

        existing = await session.execute(
            select(ConflictObject).where(
                ConflictObject.engagement_id == eng_uuid,
                ConflictObject.mismatch_type == conflict.mismatch_type,
                ConflictObject.source_a_id == src_a,
                ConflictObject.source_b_id == src_b,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        obj = ConflictObject(
            engagement_id=eng_uuid,
            mismatch_type=conflict.mismatch_type,
            source_a_id=src_a,
            source_b_id=src_b,
            severity=conflict.severity_score,
            resolution_status=ResolutionStatus.UNRESOLVED,
        )
        session.add(obj)
        persisted += 1

    if persisted > 0:
        await session.flush()

    logger.info(
        "Conflict detection for %s: %d conflicts found, %d new persisted",
        engagement_id,
        result.total_conflicts,
        persisted,
    )

    return result
