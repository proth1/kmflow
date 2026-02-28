"""Assisted (probabilistic) correlation: links events to cases via scoring.

Uses three feature dimensions to build an explainability vector:
- time_proximity: how close the event timestamp is to the case's known activity window
- role_match: whether the event performer role matches roles seen on the case
- system_match: whether the application context matches systems associated with the case

A combined score is computed as a weighted average.  Events below the confidence
threshold are not linked and are left for RoleAssociator to aggregate.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.canonical_event import CanonicalActivityEvent
from src.core.models.correlation import CaseLinkEdge

logger = logging.getLogger(__name__)

# Weights for the combined score
_TIME_WEIGHT = 0.5
_ROLE_WEIGHT = 0.3
_SYSTEM_WEIGHT = 0.2

# Links below this threshold are not persisted
CONFIDENCE_THRESHOLD = 0.4


def _time_proximity_score(event_ts: Any, case_timestamps: list[Any], window_minutes: int) -> float:
    """Score how close event_ts is to any known case timestamp.

    Returns 1.0 if within window_minutes of at least one timestamp,
    decaying linearly to 0.0 at 2× the window.
    """
    if not case_timestamps:
        return 0.0

    window = timedelta(minutes=window_minutes)
    min_delta: timedelta | None = None

    for ts in case_timestamps:
        delta = abs(event_ts - ts)
        if min_delta is None or delta < min_delta:
            min_delta = delta

    if min_delta is None:
        return 0.0

    if min_delta <= window:
        return 1.0 - (min_delta / window) * 0.5  # 0.5..1.0 within window

    double_window = window * 2
    if min_delta <= double_window:
        fraction = (min_delta - window) / window
        return max(0.0, 0.5 - fraction * 0.5)

    return 0.0


def _role_match_score(event_role: str | None, case_roles: set[str]) -> float:
    """Score whether the event performer role appears on the case."""
    if not event_role or not case_roles:
        return 0.0
    return 1.0 if event_role in case_roles else 0.0


def _system_match_score(event_source: str, case_systems: set[str]) -> float:
    """Score whether the event source system matches case-associated systems."""
    if not case_systems:
        return 0.0
    return 1.0 if event_source in case_systems else 0.0


def _combined_score(time_prox: float, role_match: float, system_match: float) -> float:
    return _TIME_WEIGHT * time_prox + _ROLE_WEIGHT * role_match + _SYSTEM_WEIGHT * system_match


class AssistedLinker:
    """Probabilistic case linker using time, role, and system features."""

    def __init__(self, confidence_threshold: float = CONFIDENCE_THRESHOLD) -> None:
        self._threshold = confidence_threshold

    async def link_probabilistic(
        self,
        session: AsyncSession,
        engagement_id: uuid.UUID,
        events: list[CanonicalActivityEvent],
        time_window_minutes: int = 30,
    ) -> list[CaseLinkEdge]:
        """Match unlinked events to cases using probabilistic scoring.

        Queries existing deterministic CaseLinkEdge records to build a feature
        index of known case timestamps, roles, and systems.  Each unlinked event
        is scored against every known case and linked to the best match above the
        confidence threshold.

        Args:
            session: Async database session.
            engagement_id: Engagement context.
            events: Events that did NOT receive a deterministic link.
            time_window_minutes: Half-window for time proximity scoring.

        Returns:
            List of newly created CaseLinkEdge records.
        """
        # Build feature index from deterministically-linked events
        known_case_features = await self._build_case_feature_index(
            session, engagement_id
        )

        if not known_case_features:
            logger.info(
                "AssistedLinker: no known cases for engagement %s; skipping probabilistic pass",
                engagement_id,
            )
            return []

        edges: list[CaseLinkEdge] = []

        for event in events:
            best_case_id: str | None = None
            best_score = 0.0
            best_explainability: dict[str, Any] = {}

            for case_id, features in known_case_features.items():
                time_prox = _time_proximity_score(
                    event.timestamp_utc,
                    features["timestamps"],
                    time_window_minutes,
                )
                role_match = _role_match_score(event.performer_role_ref, features["roles"])
                system_match = _system_match_score(event.source_system, features["systems"])
                combined = _combined_score(time_prox, role_match, system_match)

                if combined > best_score:
                    best_score = combined
                    best_case_id = case_id
                    best_explainability = {
                        "time_proximity": round(time_prox, 4),
                        "role_match": round(role_match, 4),
                        "system_match": round(system_match, 4),
                        "combined": round(combined, 4),
                        "time_window_minutes": time_window_minutes,
                    }

            if best_case_id is not None and best_score >= self._threshold:
                edge = CaseLinkEdge(
                    id=uuid.uuid4(),
                    engagement_id=engagement_id,
                    event_id=event.id,
                    case_id=best_case_id,
                    method="assisted",
                    confidence=best_score,
                    explainability=best_explainability,
                )
                session.add(edge)
                edges.append(edge)

        if edges:
            logger.info(
                "AssistedLinker: created %d probabilistic edges for engagement %s",
                len(edges),
                engagement_id,
            )

        return edges

    async def _build_case_feature_index(
        self,
        session: AsyncSession,
        engagement_id: uuid.UUID,
    ) -> dict[str, dict[str, Any]]:
        """Build a feature index keyed by case_id from existing deterministic links.

        Returns a dict: {case_id: {timestamps: [...], roles: set, systems: set}}
        """
        from sqlalchemy import select as sa_select

        stmt = (
            sa_select(CaseLinkEdge, CanonicalActivityEvent)
            .join(CanonicalActivityEvent, CaseLinkEdge.event_id == CanonicalActivityEvent.id)
            .where(
                CaseLinkEdge.engagement_id == engagement_id,
                CaseLinkEdge.method == "deterministic",
            )
        )
        result = await session.execute(stmt)
        rows = result.all()

        index: dict[str, dict[str, Any]] = {}
        for link, event in rows:
            features = index.setdefault(
                link.case_id,
                {"timestamps": [], "roles": set(), "systems": set()},
            )
            features["timestamps"].append(event.timestamp_utc)
            if event.performer_role_ref:
                features["roles"].add(event.performer_role_ref)
            features["systems"].add(event.source_system)

        return index
