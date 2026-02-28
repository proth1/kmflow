"""Switching sequence analysis service.

Assembles APP_SWITCH event chains into SwitchingTrace records, computes
friction scores, detects ping-pong patterns, and builds transition matrices
from desktop event data.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.taskmining import (
    DesktopEventType,
    SwitchingTrace,
    TaskMiningEvent,
    TransitionMatrix,
)

logger = logging.getLogger(__name__)

# Idle gap threshold: traces are broken when no switch occurs for this long
IDLE_GAP_SECONDS = 300  # 5 minutes

# Rapid-switch threshold: dwell times below this (ms) indicate high friction
RAPID_SWITCH_MS = 5_000  # 5 seconds

# Top-N transitions to persist in the matrix summary
TOP_TRANSITIONS_N = 10

# Ping-pong detection default minimum alternations
DEFAULT_PING_PONG_THRESHOLD = 3


def detect_ping_pong(trace_sequence: list[str], threshold: int = DEFAULT_PING_PONG_THRESHOLD) -> tuple[bool, int]:
    """Detect A→B→A→B alternating patterns in a switching trace.

    Args:
        trace_sequence: Ordered list of application names in the trace.
        threshold: Minimum number of A→B alternations to qualify as ping-pong.

    Returns:
        Tuple of (is_ping_pong, count) where count is the number of alternations
        for the most frequent pair detected.
    """
    if len(trace_sequence) < threshold * 2:
        return False, 0

    # Count alternations for every ordered pair (a, b) where a != b
    pair_counts: dict[tuple[str, str], int] = defaultdict(int)
    for i in range(len(trace_sequence) - 1):
        a, b = trace_sequence[i], trace_sequence[i + 1]
        if a != b:
            # Normalize pair direction: use canonical (min, max) key but track direction
            pair_counts[(a, b)] += 1

    # A ping-pong is when the same A→B and B→A both occur frequently
    max_alternations = 0
    for (a, b), fwd_count in pair_counts.items():
        rev_count = pair_counts.get((b, a), 0)
        # Alternations = minimum of forward + reverse crossings
        alternations = min(fwd_count, rev_count)
        if alternations > max_alternations:
            max_alternations = alternations

    is_pp = max_alternations >= threshold
    return is_pp, max_alternations if is_pp else 0


def compute_friction_score(
    trace_sequence: list[str],
    dwell_durations: list[int],
    total_duration_ms: int,
    is_ping_pong: bool,
    ping_pong_count: int,
) -> float:
    """Compute a friction score for a switching trace on a 0.0–1.0 scale.

    Score components (each 0.0–1.0, weighted):
    - switch_rate_component (40%): rapid switches relative to total duration
    - ping_pong_component (40%): presence and severity of ping-pong
    - context_diversity_component (20%): high unique-app count relative to trace length

    Args:
        trace_sequence: Ordered list of application names.
        dwell_durations: Dwell time in ms per app in the sequence.
        total_duration_ms: Total trace duration in ms.
        is_ping_pong: Whether ping-pong was detected.
        ping_pong_count: Number of ping-pong alternations.

    Returns:
        Friction score between 0.0 and 1.0.
    """
    if not trace_sequence or total_duration_ms <= 0:
        return 0.0

    n_switches = len(trace_sequence) - 1

    # Component 1: rapid-switch ratio (fraction of dwells below rapid threshold)
    rapid_count = sum(1 for d in dwell_durations if d < RAPID_SWITCH_MS)
    switch_rate_component = rapid_count / max(len(dwell_durations), 1)

    # Component 2: ping-pong severity (0 if absent, scaled by alternation count)
    if is_ping_pong and ping_pong_count > 0:
        # Cap at 10 alternations = max severity
        ping_pong_component = min(ping_pong_count / 10.0, 1.0)
    else:
        ping_pong_component = 0.0

    # Component 3: context diversity (unique apps / total switches)
    unique_apps = len(set(trace_sequence))
    if n_switches > 0:
        context_diversity_component = min(unique_apps / max(n_switches, 1), 1.0)
    else:
        context_diversity_component = 0.0

    score = (
        0.40 * switch_rate_component
        + 0.40 * ping_pong_component
        + 0.20 * context_diversity_component
    )
    return round(min(max(score, 0.0), 1.0), 4)


async def assemble_switching_traces(
    session: AsyncSession,
    engagement_id: UUID,
    session_id: UUID | None = None,
) -> list[SwitchingTrace]:
    """Assemble APP_SWITCH events into SwitchingTrace records.

    Groups sequential APP_SWITCH events into discrete traces, breaking when
    an idle gap of >5 minutes is detected between consecutive events.
    Computes friction score and detects ping-pong for each trace.

    Args:
        session: Async database session.
        engagement_id: Engagement to process.
        session_id: Optional session filter; processes all sessions if None.

    Returns:
        List of persisted SwitchingTrace records.
    """
    # Fetch APP_SWITCH events ordered by timestamp
    stmt = (
        select(TaskMiningEvent)
        .where(
            TaskMiningEvent.engagement_id == engagement_id,
            TaskMiningEvent.event_type == DesktopEventType.APP_SWITCH,
        )
        .order_by(TaskMiningEvent.timestamp.asc())
    )
    if session_id is not None:
        stmt = stmt.where(TaskMiningEvent.session_id == session_id)

    result = await session.execute(stmt)
    events = list(result.scalars().all())

    if not events:
        logger.info("No APP_SWITCH events found for engagement %s", engagement_id)
        return []

    traces: list[SwitchingTrace] = []
    idle_gap = timedelta(seconds=IDLE_GAP_SECONDS)

    # Group events into trace windows by idle-gap breaks
    current_window: list[TaskMiningEvent] = [events[0]]
    for evt in events[1:]:
        gap = evt.timestamp - current_window[-1].timestamp
        if gap > idle_gap:
            # Flush current window and start a new one
            trace = _build_trace(current_window, engagement_id)
            if trace is not None:
                session.add(trace)
                traces.append(trace)
            current_window = [evt]
        else:
            current_window.append(evt)

    # Flush the final window
    if current_window:
        trace = _build_trace(current_window, engagement_id)
        if trace is not None:
            session.add(trace)
            traces.append(trace)

    await session.flush()
    logger.info("Assembled %d switching traces for engagement %s", len(traces), engagement_id)
    return traces


def _build_trace(events: list[TaskMiningEvent], engagement_id: UUID) -> SwitchingTrace | None:
    """Build a SwitchingTrace from a window of APP_SWITCH events.

    Args:
        events: Ordered APP_SWITCH events in one idle-gap window.
        engagement_id: Engagement the trace belongs to.

    Returns:
        A SwitchingTrace instance, or None if insufficient data.
    """
    if len(events) < 2:
        # A single event has no "switch" — skip
        return None

    # Build sequence from application_name fields
    trace_sequence: list[str] = [e.application_name or "unknown" for e in events]

    # Compute dwell durations (ms each app was active before the next switch)
    dwell_durations: list[int] = []
    for i in range(len(events) - 1):
        delta_ms = int((events[i + 1].timestamp - events[i].timestamp).total_seconds() * 1000)
        dwell_durations.append(max(delta_ms, 0))
    # Last app in sequence gets 0 dwell (we don't know when it ended)
    dwell_durations.append(0)

    total_duration_ms = sum(dwell_durations)
    app_count = len(set(trace_sequence))

    is_ping_pong, pp_count = detect_ping_pong(trace_sequence)
    friction = compute_friction_score(
        trace_sequence=trace_sequence,
        dwell_durations=dwell_durations,
        total_duration_ms=total_duration_ms,
        is_ping_pong=is_ping_pong,
        ping_pong_count=pp_count,
    )

    # Use the session_id from the first event (all events in window should share it)
    sess_id = events[0].session_id

    return SwitchingTrace(
        engagement_id=engagement_id,
        session_id=sess_id,
        trace_sequence=trace_sequence,
        dwell_durations=dwell_durations,
        total_duration_ms=total_duration_ms,
        friction_score=friction,
        is_ping_pong=is_ping_pong,
        ping_pong_count=pp_count if is_ping_pong else None,
        app_count=app_count,
        started_at=events[0].timestamp,
        ended_at=events[-1].timestamp,
    )


async def compute_transition_matrix(
    session: AsyncSession,
    engagement_id: UUID,
    role_id: UUID | None,
    period_start: datetime,
    period_end: datetime,
) -> TransitionMatrix:
    """Build and persist a transition count matrix for an engagement period.

    Queries APP_SWITCH events in the given period and tallies from→to
    application pairs. Computes top-N transitions by frequency.

    Args:
        session: Async database session.
        engagement_id: Engagement to analyze.
        role_id: Optional role filter (stored for reference; filtering by role
                 requires role assignment on events, currently unused).
        period_start: Start of the analysis window (inclusive).
        period_end: End of the analysis window (inclusive).

    Returns:
        Persisted TransitionMatrix record.
    """
    stmt = (
        select(TaskMiningEvent)
        .where(
            TaskMiningEvent.engagement_id == engagement_id,
            TaskMiningEvent.event_type == DesktopEventType.APP_SWITCH,
            TaskMiningEvent.timestamp >= period_start,
            TaskMiningEvent.timestamp <= period_end,
        )
        .order_by(TaskMiningEvent.timestamp.asc())
    )
    result = await session.execute(stmt)
    events = list(result.scalars().all())

    # Build from→to count matrix
    matrix_data: dict[str, dict[str, int]] = {}
    all_apps: set[str] = set()
    total_transitions = 0

    for i in range(len(events) - 1):
        from_app = events[i].application_name or "unknown"
        to_app = events[i + 1].application_name or "unknown"
        all_apps.add(from_app)
        all_apps.add(to_app)
        if from_app not in matrix_data:
            matrix_data[from_app] = {}
        matrix_data[from_app][to_app] = matrix_data[from_app].get(to_app, 0) + 1
        total_transitions += 1

    # Build top-N transitions list
    flat_transitions: list[dict[str, Any]] = []
    for from_app, to_dict in matrix_data.items():
        for to_app, count in to_dict.items():
            flat_transitions.append({"from_app": from_app, "to_app": to_app, "count": count})
    flat_transitions.sort(key=lambda x: x["count"], reverse=True)
    top_transitions = flat_transitions[:TOP_TRANSITIONS_N]

    matrix = TransitionMatrix(
        engagement_id=engagement_id,
        role_id=role_id,
        period_start=period_start,
        period_end=period_end,
        matrix_data=matrix_data,
        total_transitions=total_transitions,
        unique_apps=len(all_apps),
        top_transitions=top_transitions if top_transitions else None,
    )
    session.add(matrix)
    await session.flush()
    logger.info(
        "Computed transition matrix for engagement %s: %d transitions, %d unique apps",
        engagement_id,
        total_transitions,
        len(all_apps),
    )
    return matrix


async def get_friction_analysis(session: AsyncSession, engagement_id: UUID) -> dict[str, Any]:
    """Compute aggregate friction statistics for an engagement.

    Args:
        session: Async database session.
        engagement_id: Engagement to analyze.

    Returns:
        Dict with avg_friction_score, high_friction_traces, top_ping_pong_pairs,
        total_traces_analyzed.
    """
    stmt = select(SwitchingTrace).where(SwitchingTrace.engagement_id == engagement_id)
    result = await session.execute(stmt)
    traces = list(result.scalars().all())

    if not traces:
        return {
            "avg_friction_score": 0.0,
            "high_friction_traces": [],
            "top_ping_pong_pairs": [],
            "total_traces_analyzed": 0,
        }

    friction_scores = [t.friction_score for t in traces]
    avg_friction = sum(friction_scores) / len(friction_scores)

    # High friction: top 5 traces by friction score
    sorted_by_friction = sorted(traces, key=lambda t: t.friction_score, reverse=True)
    high_friction_traces = [
        {
            "id": str(t.id),
            "friction_score": t.friction_score,
            "app_count": t.app_count,
            "is_ping_pong": t.is_ping_pong,
            "total_duration_ms": t.total_duration_ms,
        }
        for t in sorted_by_friction[:5]
    ]

    # Top ping-pong pairs: aggregate ping-pong traces by most common A/B pairs
    pp_pair_counts: dict[str, int] = defaultdict(int)
    for trace in traces:
        if not trace.is_ping_pong or not trace.trace_sequence:
            continue
        # Find dominant A→B pair in this ping-pong trace
        pair_freqs: dict[tuple[str, str], int] = defaultdict(int)
        seq = trace.trace_sequence
        for i in range(len(seq) - 1):
            a, b = seq[i], seq[i + 1]
            if a != b:
                key = tuple(sorted([a, b]))  # type: ignore[assignment]
                pair_freqs[key] += 1  # type: ignore[index]
        if pair_freqs:
            dominant_pair = max(pair_freqs, key=lambda k: pair_freqs[k])
            label = f"{dominant_pair[0]}↔{dominant_pair[1]}"
            pp_pair_counts[label] += 1

    top_ping_pong_pairs = [
        {"pair": pair, "trace_count": count}
        for pair, count in sorted(pp_pair_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    ]

    return {
        "avg_friction_score": round(avg_friction, 4),
        "high_friction_traces": high_friction_traces,
        "top_ping_pong_pairs": top_ping_pong_pairs,
        "total_traces_analyzed": len(traces),
    }
