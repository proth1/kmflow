"""Evidence materialization: converts classified actions into KM4Work evidence items.

Follows the Soroco connector pattern (src/integrations/soroco.py) for
persisting EvidenceItem records. First-party observed behavior gets the
highest reliability score (0.90) in the platform's confidence model.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from src.core.models.evidence import (
    DataClassification,
    EvidenceCategory,
    EvidenceItem,
    ValidationStatus,
)
from src.core.models.taskmining import ActionCategory, TaskMiningAction
from src.taskmining.aggregation.classifier import ClassificationResult
from src.taskmining.aggregation.session import AggregatedSession

logger = logging.getLogger(__name__)

# First-party observed behavior: highest source weight in the platform
TASK_MINING_RELIABILITY_SCORE = 0.90

# Minimum events required for materialization
MIN_EVENTS_FOR_MATERIALIZATION = 1


class EvidenceMaterializer:
    """Converts classified task mining sessions into EvidenceItem records."""

    def materialize_action(
        self,
        session: AggregatedSession,
        classification: ClassificationResult,
        action_id: uuid.UUID | None = None,
    ) -> EvidenceItem | None:
        """Create an EvidenceItem from a classified session.

        Returns None if the session should not be materialized (zero events
        or all actions UNKNOWN with no events).
        """
        if session.total_event_count < MIN_EVENTS_FOR_MATERIALIZATION:
            logger.warning(
                "Session %s produced no events — skipping materialization",
                session.app_bundle_id,
            )
            return None

        if classification.category == ActionCategory.UNKNOWN and session.total_event_count == 0:
            logger.warning(
                "Session %s produced no classifiable actions — skipping materialization",
                session.session_id or session.app_bundle_id,
            )
            return None

        engagement_id = session.engagement_id
        if not engagement_id:
            logger.error("Cannot materialize session without engagement_id")
            return None

        metadata = self._build_metadata(session, classification, action_id)
        content_hash = hashlib.sha256(
            json.dumps(metadata, sort_keys=True, default=str).encode()
        ).hexdigest()

        item = EvidenceItem(
            engagement_id=engagement_id,
            name=f"taskmining_{classification.category.value}_{session.app_bundle_id}_{_format_ts(session.started_at)}",
            category=EvidenceCategory.KM4WORK,
            format="task_mining_agent",
            source_system="kmflow_task_mining_agent",
            content_hash=content_hash,
            metadata_json=metadata,
            completeness_score=self._compute_completeness(session),
            reliability_score=TASK_MINING_RELIABILITY_SCORE,
            freshness_score=self._compute_freshness(session.ended_at or session.started_at),
            consistency_score=classification.confidence,
            validation_status=ValidationStatus.VALIDATED,
            classification=DataClassification.CONFIDENTIAL,
        )

        return item

    def materialize_batch(
        self,
        sessions: list[AggregatedSession],
        classifications: list[ClassificationResult],
        action_ids: list[uuid.UUID | None] | None = None,
    ) -> list[EvidenceItem]:
        """Materialize a batch of classified sessions. Returns non-None items."""
        if action_ids is None:
            action_ids = [None] * len(sessions)

        items = []
        for session, classification, aid in zip(sessions, classifications, action_ids):
            item = self.materialize_action(session, classification, aid)
            if item is not None:
                items.append(item)
        return items

    def should_materialize(
        self,
        session: AggregatedSession,
        classification: ClassificationResult,
    ) -> bool:
        """Check if a session should be materialized (pre-filter)."""
        if session.total_event_count < MIN_EVENTS_FOR_MATERIALIZATION:
            return False
        if not session.engagement_id:
            return False
        return True

    def _build_metadata(
        self,
        session: AggregatedSession,
        classification: ClassificationResult,
        action_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        """Build the metadata dict for the EvidenceItem."""
        return {
            "source": "kmflow_task_mining_agent",
            "session_id": str(session.session_id) if session.session_id else None,
            "action_id": str(action_id) if action_id else None,
            "action_category": classification.category.value,
            "classification_confidence": classification.confidence,
            "classification_rule": classification.rule_name,
            "application": session.app_bundle_id,
            "window_title_sample": session.window_title_sample,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
            "duration_ms": session.duration_ms,
            "active_duration_ms": session.active_duration_ms,
            "idle_duration_ms": session.idle_duration_ms,
            "event_count": session.total_event_count,
            "keyboard_event_count": session.keyboard_event_count,
            "mouse_event_count": session.mouse_event_count,
            "copy_paste_count": session.copy_paste_count,
            "scroll_count": session.scroll_count,
            "file_operation_count": session.file_operation_count,
            "url_navigation_count": session.url_navigation_count,
            "description": classification.description,
        }

    def _compute_completeness(self, session: AggregatedSession) -> float:
        """Compute completeness score based on session data richness.

        Factors: has window title, has reasonable duration, has multiple event types.
        """
        score = 0.5  # base

        if session.window_title_sample:
            score += 0.15

        if session.duration_ms > 10_000:  # > 10 seconds
            score += 0.15

        # Multiple interaction types indicate richer data
        active_types = sum([
            session.keyboard_event_count > 0,
            session.mouse_event_count > 0,
            session.scroll_count > 0,
            session.copy_paste_count > 0,
            session.file_operation_count > 0,
            session.url_navigation_count > 0,
        ])
        if active_types >= 2:
            score += 0.10
        if active_types >= 4:
            score += 0.10

        return min(score, 1.0)

    def _compute_freshness(self, end_time: datetime) -> float:
        """Compute freshness score based on recency.

        Score degrades linearly: 1.0 at capture time, 0.5 at 30 days, 0.0 at 365 days.
        """
        now = datetime.now(timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)
        age_days = (now - end_time).total_seconds() / 86400

        if age_days <= 0:
            return 1.0
        elif age_days <= 30:
            return 1.0 - (age_days / 30) * 0.5
        elif age_days <= 365:
            return 0.5 - ((age_days - 30) / 335) * 0.5
        else:
            return 0.0


def _format_ts(dt: datetime) -> str:
    """Format a datetime for use in evidence item names."""
    return dt.strftime("%Y%m%dT%H%M")
