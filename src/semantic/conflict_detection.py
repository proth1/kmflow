"""Cross-Source Conflict Detection Engine (Stories #372, #375).

Detects cross-source conflicts in the knowledge graph:
- Sequence mismatches: contradictory PRECEDES edges (A→B vs B→A)
- Role mismatches: different PERFORMED_BY assignments for same activity
- Rule mismatches: contradictory business rule values from different sources
- Existence mismatches: activity in one source but absent in another

Temporal resolution: when conflicting sources have non-overlapping
effective date ranges, suggests TEMPORAL_SHIFT resolution.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import ConflictObject, MismatchType, ResolutionStatus, ResolutionType

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
    conflict_detail: dict[str, Any] | None = None
    resolution_hint: str | None = None


# Default authority weights per evidence category.
# Category 9 (Regulatory/Policy) = 0.9, interview transcripts = 0.5.
DEFAULT_AUTHORITY_WEIGHTS: dict[str, float] = {
    "policy_document": 0.9,
    "regulatory_filing": 0.9,
    "control_register": 0.85,
    "system_export": 0.8,
    "structured_data": 0.75,
    "bpm_model": 0.7,
    "interview_transcript": 0.5,
    "observation_notes": 0.4,
    "email_communication": 0.3,
}


def get_authority_weight(evidence_type: str | None) -> float:
    """Return default authority weight for an evidence type.

    Falls back to 0.5 for unknown types.
    """
    if evidence_type is None:
        return 0.5
    return DEFAULT_AUTHORITY_WEIGHTS.get(evidence_type, 0.5)


def check_temporal_resolution(
    effective_from_a: date | datetime | None,
    effective_to_a: date | datetime | None,
    effective_from_b: date | datetime | None,
    effective_to_b: date | datetime | None,
) -> dict[str, Any] | None:
    """Check whether a conflict can be explained by non-overlapping time ranges.

    Returns a temporal annotation dict if ranges don't overlap, else None.
    """
    if effective_from_a is None or effective_from_b is None:
        return None

    # Normalise to date for comparison
    def _to_date(d: date | datetime) -> date:
        return d.date() if isinstance(d, datetime) else d

    from_a = _to_date(effective_from_a)
    to_a = _to_date(effective_to_a) if effective_to_a else None
    from_b = _to_date(effective_from_b)
    to_b = _to_date(effective_to_b) if effective_to_b else None

    # Check overlap. Ranges overlap if: start_a <= end_b AND start_b <= end_a
    # With open-ended ranges (no end date), the range extends to "present"
    far_future = date(9999, 12, 31)
    end_a = to_a or far_future
    end_b = to_b or far_future

    if from_a <= end_b and from_b <= end_a:
        # Overlapping → not a temporal shift
        return None

    # Non-overlapping: temporal shift
    range_a = f"{from_a.isoformat()}" + (f" to {to_a.isoformat()}" if to_a else "–present")
    range_b = f"{from_b.isoformat()}" + (f" to {to_b.isoformat()}" if to_b else "–present")

    return {
        "resolution_type": "TEMPORAL_SHIFT",
        "annotation": f"Source A valid {range_a}; Source B valid {range_b}",
        "source_a_range": {"from": from_a.isoformat(), "to": to_a.isoformat() if to_a else None},
        "source_b_range": {"from": from_b.isoformat(), "to": to_b.isoformat() if to_b else None},
    }


@dataclass
class DetectionResult:
    """Result of a conflict detection run."""

    engagement_id: str
    conflicts: list[DetectedConflict] = field(default_factory=list)
    sequence_conflicts_found: int = 0
    role_conflicts_found: int = 0
    rule_conflicts_found: int = 0
    existence_conflicts_found: int = 0

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
                LIMIT $limit
                """,
                {"engagement_id": engagement_id, "limit": 500},
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
                LIMIT $limit
                """,
                {"engagement_id": engagement_id, "limit": 500},
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


class RuleConflictDetector:
    """Detect rule mismatches in the knowledge graph.

    Finds BusinessRule nodes attached to the same activity from different
    sources with contradictory values (e.g., different approval thresholds).
    When both rules have effective date metadata with non-overlapping ranges,
    a TEMPORAL_SHIFT resolution hint is suggested.
    """

    def __init__(self, graph_service: Any) -> None:
        self._graph = graph_service

    async def detect(self, engagement_id: str) -> list[DetectedConflict]:
        """Find rule mismatches for an engagement."""
        conflicts: list[DetectedConflict] = []

        try:
            records = await self._graph.run_query(
                """
                MATCH (act:Activity)-[:HAS_RULE]->(r1:BusinessRule)
                WHERE r1.engagement_id = $engagement_id
                WITH act, r1
                MATCH (act)-[:HAS_RULE]->(r2:BusinessRule)
                WHERE r2.engagement_id = $engagement_id
                  AND r1.source_id <> r2.source_id
                  AND r1.rule_text <> r2.rule_text
                  AND id(r1) < id(r2)
                RETURN
                    act.name AS activity_name,
                    r1.rule_text AS rule_text_a,
                    r2.rule_text AS rule_text_b,
                    r1.threshold_value AS threshold_a,
                    r2.threshold_value AS threshold_b,
                    r1.source_id AS source_a_id,
                    r2.source_id AS source_b_id,
                    r1.source_weight AS weight_a,
                    r2.source_weight AS weight_b,
                    r1.created_at AS created_a,
                    r2.created_at AS created_b,
                    r1.effective_from AS effective_from_a,
                    r1.effective_to AS effective_to_a,
                    r2.effective_from AS effective_from_b,
                    r2.effective_to AS effective_to_b
                LIMIT $limit
                """,
                {"engagement_id": engagement_id, "limit": 500},
            )
        except Exception:
            logger.exception("Failed to query rule conflicts for %s", engagement_id)
            return conflicts

        for record in records:
            weight_a = float(record.get("weight_a", 0.5) or 0.5)
            weight_b = float(record.get("weight_b", 0.5) or 0.5)
            created_a = record.get("created_a")
            created_b = record.get("created_b")

            score = compute_severity(weight_a, weight_b, created_a, created_b)
            label = severity_label(score)

            detail_dict: dict[str, Any] = {
                "activity": record.get("activity_name"),
                "rule_text_a": record.get("rule_text_a"),
                "rule_text_b": record.get("rule_text_b"),
                "threshold_a": record.get("threshold_a"),
                "threshold_b": record.get("threshold_b"),
            }

            # Check temporal resolution
            resolution_hint = None
            temporal = check_temporal_resolution(
                record.get("effective_from_a"),
                record.get("effective_to_a"),
                record.get("effective_from_b"),
                record.get("effective_to_b"),
            )
            if temporal:
                resolution_hint = ResolutionType.TEMPORAL_SHIFT.value
                detail_dict["temporal_annotation"] = temporal["annotation"]
                detail_dict["source_a_range"] = temporal["source_a_range"]
                detail_dict["source_b_range"] = temporal["source_b_range"]

            conflicts.append(
                DetectedConflict(
                    mismatch_type=MismatchType.RULE_MISMATCH,
                    engagement_id=engagement_id,
                    source_a_id=str(record.get("source_a_id", "")),
                    source_b_id=str(record.get("source_b_id", "")),
                    severity_score=score,
                    severity_label=label,
                    detail=(
                        f"Rule mismatch for '{record.get('activity_name')}': "
                        f"'{record.get('rule_text_a')}' vs '{record.get('rule_text_b')}'"
                    ),
                    edge_a_data={"rule_text": record.get("rule_text_a"), "threshold": record.get("threshold_a")},
                    edge_b_data={"rule_text": record.get("rule_text_b"), "threshold": record.get("threshold_b")},
                    conflict_detail=detail_dict,
                    resolution_hint=resolution_hint,
                )
            )

        return conflicts


class ExistenceConflictDetector:
    """Detect existence mismatches in the knowledge graph.

    Finds Activity nodes present in one source's evidence but absent
    from another source's evidence for the same engagement scope.
    Authority weight of each source determines severity.
    """

    def __init__(self, graph_service: Any) -> None:
        self._graph = graph_service

    async def detect(self, engagement_id: str) -> list[DetectedConflict]:
        """Find existence mismatches for an engagement.

        Queries Neo4j for activities that appear in one source but not another,
        where both sources cover the same engagement.
        """
        conflicts: list[DetectedConflict] = []

        try:
            records = await self._graph.run_query(
                """
                MATCH (act:Activity)-[r1:EVIDENCED_BY]->(ev1:Evidence)
                WHERE r1.engagement_id = $engagement_id
                WITH act, ev1, r1
                MATCH (ev2:Evidence)
                WHERE ev2.engagement_id = $engagement_id
                  AND ev1.source_id <> ev2.source_id
                  AND NOT EXISTS {
                    MATCH (act)-[:EVIDENCED_BY]->(ev2)
                  }
                RETURN
                    act.name AS activity_name,
                    ev1.source_id AS source_present_id,
                    ev2.source_id AS source_absent_id,
                    ev1.evidence_type AS type_present,
                    ev2.evidence_type AS type_absent,
                    ev1.source_weight AS weight_present,
                    ev2.source_weight AS weight_absent,
                    ev1.created_at AS created_present,
                    ev2.created_at AS created_absent,
                    ev1.effective_from AS effective_from_present,
                    ev1.effective_to AS effective_to_present,
                    ev2.effective_from AS effective_from_absent,
                    ev2.effective_to AS effective_to_absent
                LIMIT $limit
                """,
                {"engagement_id": engagement_id, "limit": 500},
            )
        except Exception:
            logger.exception("Failed to query existence conflicts for %s", engagement_id)
            return conflicts

        for record in records:
            weight_present = float(record.get("weight_present", 0.5) or 0.5)
            weight_absent = float(record.get("weight_absent", 0.5) or 0.5)

            # If absent source has low authority (e.g., interview omission
            # vs policy document assertion), severity is lower
            type_present = record.get("type_present")
            type_absent = record.get("type_absent")
            if weight_present == 0.5 and type_present:
                weight_present = get_authority_weight(type_present)
            if weight_absent == 0.5 and type_absent:
                weight_absent = get_authority_weight(type_absent)

            score = compute_severity(weight_present, weight_absent)
            label = severity_label(score)

            detail_dict: dict[str, Any] = {
                "activity": record.get("activity_name"),
                "source_present_type": type_present,
                "source_absent_type": type_absent,
                "weight_present": weight_present,
                "weight_absent": weight_absent,
                "note": (
                    f"Source B ({type_absent or 'unknown'}) has "
                    f"{'lower' if weight_absent < weight_present else 'higher'} "
                    f"default authority weight than Source A ({type_present or 'unknown'})"
                ),
            }

            # Check temporal resolution
            resolution_hint = None
            temporal = check_temporal_resolution(
                record.get("effective_from_present"),
                record.get("effective_to_present"),
                record.get("effective_from_absent"),
                record.get("effective_to_absent"),
            )
            if temporal:
                resolution_hint = ResolutionType.TEMPORAL_SHIFT.value
                detail_dict["temporal_annotation"] = temporal["annotation"]

            conflicts.append(
                DetectedConflict(
                    mismatch_type=MismatchType.EXISTENCE_MISMATCH,
                    engagement_id=engagement_id,
                    source_a_id=str(record.get("source_present_id", "")),
                    source_b_id=str(record.get("source_absent_id", "")),
                    severity_score=score,
                    severity_label=label,
                    detail=(
                        f"Existence mismatch: '{record.get('activity_name')}' "
                        f"present in source {record.get('source_present_id')} "
                        f"but absent from source {record.get('source_absent_id')}"
                    ),
                    edge_a_data={"activity": record.get("activity_name"), "status": "present"},
                    edge_b_data={"activity": record.get("activity_name"), "status": "absent"},
                    conflict_detail=detail_dict,
                    resolution_hint=resolution_hint,
                )
            )

        return conflicts


async def run_conflict_detection(
    graph_service: Any,
    session: AsyncSession,
    engagement_id: str,
) -> DetectionResult:
    """Run full conflict detection pipeline for an engagement.

    Detects sequence, role, rule, and existence mismatches, persists
    new conflicts as ConflictObjects (idempotent — skips duplicates).

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
    result.sequence_conflicts_found = len(seq_conflicts)

    # Detect role mismatches
    role_detector = RoleConflictDetector(graph_service)
    role_conflicts = await role_detector.detect(engagement_id)
    result.conflicts.extend(role_conflicts)
    result.role_conflicts_found = len(role_conflicts)

    # Detect rule mismatches
    rule_detector = RuleConflictDetector(graph_service)
    rule_conflicts = await rule_detector.detect(engagement_id)
    result.conflicts.extend(rule_conflicts)
    result.rule_conflicts_found = len(rule_conflicts)

    # Detect existence mismatches
    existence_detector = ExistenceConflictDetector(graph_service)
    existence_conflicts = await existence_detector.detect(engagement_id)
    result.conflicts.extend(existence_conflicts)
    result.existence_conflicts_found = len(existence_conflicts)

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
            conflict_detail=conflict.conflict_detail,
            resolution_hint=conflict.resolution_hint,
        )
        session.add(obj)
        persisted += 1

    if persisted > 0:
        await session.flush()

    logger.info(
        "Conflict detection for %s: %d conflicts found (%d seq, %d role, %d rule, %d existence), %d new persisted",
        engagement_id,
        result.total_conflicts,
        result.sequence_conflicts_found,
        result.role_conflicts_found,
        result.rule_conflicts_found,
        result.existence_conflicts_found,
        persisted,
    )

    return result
