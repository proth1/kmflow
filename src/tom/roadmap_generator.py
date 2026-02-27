"""Gap-Prioritized Transformation Roadmap Generator (Story #368).

Generates 3-4 phase roadmaps from gap analysis results with:
- Composite scoring (priority_score as composite)
- Effort estimation from remediation_cost (1-5 scale → weeks)
- Dependency resolution via topological sort
- Threshold-based phase bucketing
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import (
    GapAnalysisResult,
    RoadmapStatus,
    TOMGapType,
    TransformationRoadmapModel,
)

logger = logging.getLogger(__name__)

# Effort mapping: remediation_cost (1-5) → weeks
EFFORT_WEEKS_MAP: dict[int, float] = {1: 0.5, 2: 1.0, 3: 2.0, 4: 4.0, 5: 8.0}


def _topological_sort(gaps: list[GapAnalysisResult]) -> list[GapAnalysisResult]:
    """Sort gaps respecting dependency ordering via topological sort.

    Gaps with depends_on_ids are placed after their prerequisites.
    Gaps without dependencies are ordered by priority_score descending.
    """
    gap_map = {str(g.id): g for g in gaps}
    gap_ids = set(gap_map.keys())

    # Build adjacency list (gap_id → set of dependents)
    in_degree: dict[str, int] = defaultdict(int)
    dependents: dict[str, list[str]] = defaultdict(list)

    for gap in gaps:
        gid = str(gap.id)
        if gid not in in_degree:
            in_degree[gid] = 0
        deps = gap.depends_on_ids or []
        for dep_id in deps:
            dep_str = str(dep_id)
            if dep_str in gap_ids:
                in_degree[gid] += 1
                dependents[dep_str].append(gid)

    # Kahn's algorithm
    queue = sorted(
        [gid for gid, deg in in_degree.items() if deg == 0],
        key=lambda gid: gap_map[gid].priority_score,
        reverse=True,
    )
    result: list[GapAnalysisResult] = []

    while queue:
        current = queue.pop(0)
        result.append(gap_map[current])
        for dep in sorted(dependents[current], key=lambda gid: gap_map[gid].priority_score, reverse=True):
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                queue.append(dep)
        queue.sort(key=lambda gid: gap_map[gid].priority_score, reverse=True)

    # Add any remaining (cycle or missing deps)
    visited = {str(g.id) for g in result}
    for gap in gaps:
        if str(gap.id) not in visited:
            result.append(gap)

    return result


def _assign_phases(sorted_gaps: list[GapAnalysisResult]) -> list[list[GapAnalysisResult]]:
    """Assign gaps to 3-4 phases using threshold-based bucketing.

    Phase 1: High priority (score > 0.5) AND low effort (cost <= 2) — Quick Wins
    Phase 2: High priority (score > 0.5) AND higher effort (cost > 2) — Foundation
    Phase 3: Lower priority (score <= 0.5) AND any effort — Transformation
    Phase 4: Remaining (NO_GAP type filtered, overflow) — Optimization

    Dependencies are respected: if A depends on B, A is placed in a later phase.
    """
    phases: list[list[GapAnalysisResult]] = [[], [], [], []]
    gap_phase_map: dict[str, int] = {}  # gap_id → phase_index

    for gap in sorted_gaps:
        if gap.gap_type == TOMGapType.NO_GAP:
            continue

        score = gap.priority_score
        cost = gap.remediation_cost or 3  # Default to medium effort

        # Determine base phase
        if score > 0.5 and cost <= 2:
            phase_idx = 0  # Phase 1: Quick wins
        elif score > 0.5:
            phase_idx = 1  # Phase 2: Foundation
        elif score > 0.25:
            phase_idx = 2  # Phase 3: Transformation
        else:
            phase_idx = 3  # Phase 4: Optimization

        # Respect dependencies: place after all prerequisites
        deps = gap.depends_on_ids or []
        for dep_id in deps:
            dep_str = str(dep_id)
            if dep_str in gap_phase_map:
                dep_phase = gap_phase_map[dep_str]
                # Must be in a strictly later phase
                if phase_idx <= dep_phase:
                    phase_idx = min(dep_phase + 1, 3)

        phases[phase_idx].append(gap)
        gap_phase_map[str(gap.id)] = phase_idx

    # Remove empty trailing phases (but keep at least 3)
    while len(phases) > 3 and not phases[-1]:
        phases.pop()

    return phases


def _build_phase_data(
    phase_idx: int,
    gaps: list[GapAnalysisResult],
) -> dict[str, Any]:
    """Build serializable phase data for JSONB storage."""
    phase_names = ["Quick Wins", "Foundation Building", "Transformation", "Optimization"]
    name = phase_names[phase_idx] if phase_idx < len(phase_names) else f"Phase {phase_idx + 1}"

    recommendations = []
    total_weeks = 0.0
    for gap in gaps:
        effort = EFFORT_WEEKS_MAP.get(gap.remediation_cost or 3, 2.0)
        total_weeks += effort
        recommendations.append(
            {
                "gap_id": str(gap.id),
                "title": gap.recommendation or "Assessment needed",
                "dimension": str(gap.dimension),
                "gap_type": str(gap.gap_type),
                "composite_score": gap.priority_score,
                "effort_weeks": effort,
                "remediation_cost": gap.remediation_cost or 3,
                "rationale_summary": (gap.rationale or "")[:200],
                "depends_on": [str(d) for d in (gap.depends_on_ids or [])],
            }
        )

    return {
        "phase_number": phase_idx + 1,
        "name": name,
        "duration_weeks_estimate": max(1, round(total_weeks)),
        "recommendation_count": len(recommendations),
        "recommendation_ids": [r["gap_id"] for r in recommendations],
        "recommendations": recommendations,
    }


async def generate_roadmap(
    session: AsyncSession,
    engagement_id: uuid.UUID,
) -> TransformationRoadmapModel:
    """Generate a prioritized transformation roadmap from gap analysis results.

    Args:
        session: Database session.
        engagement_id: The engagement to generate for.

    Returns:
        Persisted TransformationRoadmapModel.
    """
    # Fetch all gaps for the engagement
    result = await session.execute(
        select(GapAnalysisResult)
        .where(GapAnalysisResult.engagement_id == engagement_id)
        .where(GapAnalysisResult.gap_type != TOMGapType.NO_GAP)
    )
    gaps = list(result.scalars().all())

    # Topological sort respecting dependencies
    sorted_gaps = _topological_sort(gaps)

    # Assign to phases
    phase_groups = _assign_phases(sorted_gaps)

    # Build phase data
    phases_data = []
    total_weeks = 0
    total_initiatives = 0
    for idx, phase_gaps in enumerate(phase_groups):
        if phase_gaps:
            phase = _build_phase_data(idx, phase_gaps)
            phases_data.append(phase)
            total_weeks += phase["duration_weeks_estimate"]
            total_initiatives += phase["recommendation_count"]

    # Persist roadmap
    roadmap = TransformationRoadmapModel(
        engagement_id=engagement_id,
        status=RoadmapStatus.DRAFT,
        phases=phases_data,
        total_initiatives=total_initiatives,
        estimated_duration_weeks=total_weeks,
        generated_at=datetime.now(UTC),
    )
    session.add(roadmap)
    await session.flush()
    await session.refresh(roadmap)
    return roadmap
