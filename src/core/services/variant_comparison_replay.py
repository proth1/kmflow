"""Variant comparison replay service (Story #342).

Implements side-by-side replay comparison of two process variants using
longest common subsequence (LCS) alignment. Identifies divergence points,
compares performers and cycle times at each aligned stage, and surfaces
evidence explaining variant divergence.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class VariantFrame:
    """Frame data for one variant at a given process stage.

    Attributes:
        activity_name: Name of the activity at this stage.
        performer: Role or user performing the activity.
        timestamp_utc: ISO 8601 UTC timestamp of the event.
        confidence_score: Confidence score (0.0-1.0).
        cycle_time_ms: Milliseconds elapsed since previous stage (0 for first).
        evidence_refs: UUIDs of supporting evidence artifacts.
    """

    activity_name: str
    performer: str = ""
    timestamp_utc: str = ""
    confidence_score: float = 0.0
    cycle_time_ms: int = 0
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize frame to dict for API response."""
        return {
            "activity_name": self.activity_name,
            "performer": self.performer,
            "timestamp_utc": self.timestamp_utc,
            "confidence_score": self.confidence_score,
            "cycle_time_ms": self.cycle_time_ms,
            "evidence_refs": self.evidence_refs,
        }


@dataclass
class ComparisonStage:
    """A single aligned stage in the variant comparison.

    When both variants share the same activity at a stage, both frames are
    populated. When one variant has an activity the other doesn't (divergence),
    only one frame is populated and the other is None.

    Attributes:
        stage_index: Zero-based index in the aligned sequence.
        variant_a_frame: Frame data for Variant A (None if absent at this stage).
        variant_b_frame: Frame data for Variant B (None if absent at this stage).
        is_divergence: Whether this stage is a divergence point.
        divergence_type: Type of divergence (activity_mismatch, performer_mismatch,
            a_only, b_only, or None if no divergence).
        divergence_evidence_refs: Evidence refs explaining the divergence.
        cycle_time_delta_ms: Difference in cycle time (A - B) at this stage.
    """

    stage_index: int
    variant_a_frame: VariantFrame | None = None
    variant_b_frame: VariantFrame | None = None
    is_divergence: bool = False
    divergence_type: str | None = None
    divergence_evidence_refs: list[str] = field(default_factory=list)
    cycle_time_delta_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize stage to dict for API response."""
        return {
            "stage_index": self.stage_index,
            "variant_a_frame": self.variant_a_frame.to_dict() if self.variant_a_frame else None,
            "variant_b_frame": self.variant_b_frame.to_dict() if self.variant_b_frame else None,
            "is_divergence": self.is_divergence,
            "divergence_type": self.divergence_type,
            "divergence_evidence_refs": self.divergence_evidence_refs,
            "cycle_time_delta_ms": self.cycle_time_delta_ms,
        }


@dataclass
class VariantComparisonResult:
    """Result of a variant comparison replay.

    Attributes:
        task_id: Unique replay task identifier.
        variant_a_id: Identifier for Variant A.
        variant_b_id: Identifier for Variant B.
        status: Task status (pending/completed/failed).
        stages: Aligned comparison stages.
        total_stages: Number of aligned stages.
        total_divergences: Number of divergence points.
        variant_a_total_cycle_time_ms: End-to-end cycle time for Variant A.
        variant_b_total_cycle_time_ms: End-to-end cycle time for Variant B.
        created_at: ISO 8601 creation timestamp.
        error: Error message if generation failed.
    """

    task_id: str = ""
    variant_a_id: str = ""
    variant_b_id: str = ""
    status: str = "pending"
    stages: list[ComparisonStage] = field(default_factory=list)
    total_stages: int = 0
    total_divergences: int = 0
    variant_a_total_cycle_time_ms: int = 0
    variant_b_total_cycle_time_ms: int = 0
    created_at: str = ""
    error: str | None = None

    def __post_init__(self) -> None:
        if not self.task_id:
            self.task_id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now(tz=UTC).isoformat()

    def to_status_dict(self) -> dict[str, Any]:
        """Serialize task status for polling endpoint."""
        return {
            "task_id": self.task_id,
            "replay_type": "variant_comparison",
            "status": self.status,
            "progress_pct": 100 if self.status == "completed" else 0,
            "created_at": self.created_at,
        }


def _parse_timestamp(ts: Any) -> datetime | None:
    """Parse a timestamp value to datetime, returning None on failure."""
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, str) and ts:
        try:
            return datetime.fromisoformat(ts)
        except ValueError:
            return None
    return None


def _compute_cycle_times(events: list[dict[str, Any]]) -> list[int]:
    """Compute per-step cycle times in milliseconds.

    Cycle time at index i = elapsed time from event i-1 to event i.
    First event has cycle time 0.

    Args:
        events: Canonical events sorted chronologically.

    Returns:
        List of cycle times in ms, same length as events.
    """
    cycle_times: list[int] = []
    prev_ts: datetime | None = None

    for event in events:
        ts = _parse_timestamp(event.get("timestamp_utc"))
        if ts is not None and prev_ts is not None:
            delta = ts - prev_ts
            cycle_times.append(int(delta.total_seconds() * 1000))
        else:
            cycle_times.append(0)
        if ts is not None:
            prev_ts = ts

    return cycle_times


def _build_variant_frames(events: list[dict[str, Any]]) -> list[VariantFrame]:
    """Convert canonical events into variant frames with cycle times.

    Args:
        events: Canonical events sorted chronologically.

    Returns:
        List of VariantFrame objects.
    """
    cycle_times = _compute_cycle_times(events)
    frames: list[VariantFrame] = []

    for i, event in enumerate(events):
        ts = event.get("timestamp_utc", "")
        if hasattr(ts, "isoformat"):
            ts = ts.isoformat()

        raw_refs = event.get("evidence_refs") or []
        evidence_refs = [str(ref) for ref in raw_refs]

        frames.append(
            VariantFrame(
                activity_name=event.get("activity_name", ""),
                performer=event.get("performer_role_ref", "") or "",
                timestamp_utc=str(ts),
                confidence_score=float(event.get("confidence_score", 0.0)),
                cycle_time_ms=cycle_times[i],
                evidence_refs=evidence_refs,
            )
        )

    return frames


def compute_lcs_alignment(
    seq_a: list[str],
    seq_b: list[str],
) -> list[tuple[int | None, int | None]]:
    """Align two activity sequences using Longest Common Subsequence.

    Returns a list of (index_a, index_b) pairs. When both are non-None,
    the activities match. When one is None, that variant doesn't have
    an activity at that aligned position.

    Args:
        seq_a: Activity name sequence for Variant A.
        seq_b: Activity name sequence for Variant B.

    Returns:
        List of aligned index pairs.
    """
    m, n = len(seq_a), len(seq_b)

    # Build LCS table
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if seq_a[i - 1] == seq_b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    # Backtrack to find alignment
    alignment: list[tuple[int | None, int | None]] = []
    i, j = m, n
    lcs_pairs: list[tuple[int, int]] = []

    while i > 0 and j > 0:
        if seq_a[i - 1] == seq_b[j - 1]:
            lcs_pairs.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif dp[i - 1][j] >= dp[i][j - 1]:
            i -= 1
        else:
            j -= 1

    lcs_pairs.reverse()

    # Build full alignment by interleaving unmatched elements
    ai, bj = 0, 0
    for la, lb in lcs_pairs:
        # Add unmatched from A before this LCS match
        while ai < la:
            alignment.append((ai, None))
            ai += 1
        # Add unmatched from B before this LCS match
        while bj < lb:
            alignment.append((None, bj))
            bj += 1
        # Add the matched pair
        alignment.append((ai, bj))
        ai += 1
        bj += 1

    # Add remaining unmatched
    while ai < m:
        alignment.append((ai, None))
        ai += 1
    while bj < n:
        alignment.append((None, bj))
        bj += 1

    return alignment


def _collect_divergence_evidence(
    frame_a: VariantFrame | None,
    frame_b: VariantFrame | None,
    divergence_annotations: dict[int, list[str]] | None = None,
    stage_index: int = 0,
) -> list[str]:
    """Collect evidence refs relevant to a divergence point.

    Combines evidence from both variant frames and any explicit
    divergence annotations.

    Args:
        frame_a: Variant A frame (may be None).
        frame_b: Variant B frame (may be None).
        divergence_annotations: Optional mapping of stage_index -> evidence_refs.
        stage_index: Current stage index for annotation lookup.

    Returns:
        Deduplicated list of evidence ref strings.
    """
    refs: list[str] = []

    if frame_a:
        refs.extend(frame_a.evidence_refs)
    if frame_b:
        refs.extend(frame_b.evidence_refs)

    if divergence_annotations and stage_index in divergence_annotations:
        refs.extend(divergence_annotations[stage_index])

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            unique.append(ref)

    return unique


def build_comparison_stages(
    frames_a: list[VariantFrame],
    frames_b: list[VariantFrame],
    alignment: list[tuple[int | None, int | None]],
    divergence_annotations: dict[int, list[str]] | None = None,
) -> list[ComparisonStage]:
    """Build comparison stages from aligned variant frames.

    Detects divergences by comparing (activity_name, performer) tuples
    at each aligned position.

    Args:
        frames_a: Variant A frames.
        frames_b: Variant B frames.
        alignment: LCS alignment pairs.
        divergence_annotations: Optional stage->evidence mapping.

    Returns:
        List of ComparisonStage with divergence detection.
    """
    stages: list[ComparisonStage] = []

    for stage_idx, (ai, bi) in enumerate(alignment):
        fa = frames_a[ai] if ai is not None else None
        fb = frames_b[bi] if bi is not None else None

        is_divergence = False
        divergence_type: str | None = None

        if fa is not None and fb is not None:
            # Both variants have activities at this stage
            if fa.activity_name != fb.activity_name:
                is_divergence = True
                divergence_type = "activity_mismatch"
            elif fa.performer != fb.performer:
                is_divergence = True
                divergence_type = "performer_mismatch"
        elif fa is not None:
            is_divergence = True
            divergence_type = "a_only"
        elif fb is not None:
            is_divergence = True
            divergence_type = "b_only"

        # Cycle time delta
        ct_a = fa.cycle_time_ms if fa else 0
        ct_b = fb.cycle_time_ms if fb else 0

        # Collect divergence evidence
        evidence_refs: list[str] = []
        if is_divergence:
            evidence_refs = _collect_divergence_evidence(fa, fb, divergence_annotations, stage_idx)

        stages.append(
            ComparisonStage(
                stage_index=stage_idx,
                variant_a_frame=fa,
                variant_b_frame=fb,
                is_divergence=is_divergence,
                divergence_type=divergence_type,
                divergence_evidence_refs=evidence_refs,
                cycle_time_delta_ms=ct_a - ct_b,
            )
        )

    return stages


def generate_variant_comparison(
    variant_a_id: str,
    variant_b_id: str,
    events_a: list[dict[str, Any]],
    events_b: list[dict[str, Any]],
    divergence_annotations: dict[int, list[str]] | None = None,
) -> VariantComparisonResult:
    """Generate a variant comparison replay from canonical events.

    Aligns two variant event spines using LCS, detects divergence points,
    computes cycle time deltas, and links divergence evidence.

    Args:
        variant_a_id: Identifier for Variant A.
        variant_b_id: Identifier for Variant B.
        events_a: Canonical events for Variant A, sorted chronologically.
        events_b: Canonical events for Variant B, sorted chronologically.
        divergence_annotations: Optional mapping of aligned stage index
            to evidence refs explaining divergence.

    Returns:
        VariantComparisonResult with aligned stages and metrics.
    """
    result = VariantComparisonResult(
        variant_a_id=variant_a_id,
        variant_b_id=variant_b_id,
    )

    if not events_a and not events_b:
        result.status = "completed"
        return result

    # Build variant frames
    frames_a = _build_variant_frames(events_a)
    frames_b = _build_variant_frames(events_b)

    # Extract activity sequences for LCS alignment
    seq_a = [f.activity_name for f in frames_a]
    seq_b = [f.activity_name for f in frames_b]

    # Compute LCS alignment
    alignment = compute_lcs_alignment(seq_a, seq_b)

    # Build comparison stages
    stages = build_comparison_stages(frames_a, frames_b, alignment, divergence_annotations)

    # Compute totals
    total_a = sum(f.cycle_time_ms for f in frames_a)
    total_b = sum(f.cycle_time_ms for f in frames_b)
    divergence_count = sum(1 for s in stages if s.is_divergence)

    result.stages = stages
    result.total_stages = len(stages)
    result.total_divergences = divergence_count
    result.variant_a_total_cycle_time_ms = total_a
    result.variant_b_total_cycle_time_ms = total_b
    result.status = "completed"

    logger.info(
        "Variant comparison %s vs %s: %d stages, %d divergences",
        variant_a_id,
        variant_b_id,
        len(stages),
        divergence_count,
    )

    return result
