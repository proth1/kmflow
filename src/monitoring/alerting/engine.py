"""Alert engine: receives events, evaluates rules, generates/deduplicates alerts (Story #366).

The engine processes incoming alert events (deviations, quality drops, SLA breaches),
evaluates engagement-scoped rules, deduplicates alerts within configurable time windows,
and dispatches notifications to configured channels.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


# ── Alert types ──────────────────────────────────────────────────


class AlertType:
    """String constants for alert types."""

    PROCESS_DEVIATION = "PROCESS_DEVIATION"
    EVIDENCE_QUALITY_DROP = "EVIDENCE_QUALITY_DROP"
    EVIDENCE_CONTRADICTION = "EVIDENCE_CONTRADICTION"
    SLA_BREACH = "SLA_BREACH"


class Severity:
    """Severity ranking utilities. Values match AlertSeverity StrEnum in src.core.models.monitoring."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    _ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}

    @classmethod
    def rank(cls, severity: str) -> int:
        """Return numeric rank for severity comparison."""
        return cls._ORDER.get(severity.lower(), 0)

    @classmethod
    def meets_threshold(cls, severity: str, threshold: str) -> bool:
        """Check if severity meets or exceeds threshold."""
        return cls.rank(severity) >= cls.rank(threshold)


# ── Data structures ──────────────────────────────────────────────


@dataclass
class AlertEvent:
    """Incoming event that may trigger an alert.

    Attributes:
        event_type: Type of event (e.g., PROCESS_DEVIATION, SLA_BREACH).
        engagement_id: Engagement this event belongs to.
        severity: Event severity level.
        source_id: ID of the source object (deviation_id, evidence_id, etc.).
        process_element: Affected process element (if applicable).
        description: Human-readable event description.
        metadata: Additional event-specific data.
        timestamp: When the event occurred.
    """

    event_type: str
    engagement_id: str
    severity: str
    source_id: str = ""
    process_element: str = ""
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


@dataclass
class Alert:
    """A generated alert with deduplication tracking.

    Attributes:
        id: Unique alert identifier.
        alert_type: Type of alert.
        engagement_id: Engagement this alert belongs to.
        severity: Alert severity level.
        title: Human-readable alert title.
        description: Detailed description.
        source_ids: IDs of source objects that contributed to this alert.
        process_element: Affected process element.
        rule_id: ID of the rule that triggered this alert (if any).
        matched_count: Number of events that matched the rule condition.
        window: Rule evaluation window description (e.g., "1h").
        rule_description: Description of the triggering rule.
        acknowledged: Whether an analyst has acknowledged this alert.
        acknowledge_note: Note from the acknowledging analyst.
        occurrence_count: Number of duplicate occurrences aggregated.
        dedup_key: Deduplication key for aggregation.
        created_at: When the alert was first created.
        last_occurred_at: When the most recent occurrence happened.
    """

    id: str = ""
    alert_type: str = ""
    engagement_id: str = ""
    severity: str = ""
    title: str = ""
    description: str = ""
    source_ids: list[str] = field(default_factory=list)
    process_element: str = ""
    rule_id: str = ""
    matched_count: int = 0
    window: str = ""
    rule_description: str = ""
    acknowledged: bool = False
    acknowledge_note: str = ""
    occurrence_count: int = 1
    dedup_key: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    last_occurred_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

    def __post_init__(self) -> None:
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> dict[str, Any]:
        """Serialize alert for API response."""
        return {
            "id": self.id,
            "alert_type": self.alert_type,
            "engagement_id": self.engagement_id,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "source_ids": self.source_ids,
            "process_element": self.process_element,
            "rule_id": self.rule_id,
            "matched_count": self.matched_count,
            "window": self.window,
            "rule_description": self.rule_description,
            "acknowledged": self.acknowledged,
            "acknowledge_note": self.acknowledge_note,
            "occurrence_count": self.occurrence_count,
            "dedup_key": self.dedup_key,
            "created_at": self.created_at.isoformat(),
            "last_occurred_at": self.last_occurred_at.isoformat(),
        }


@dataclass
class AlertRule:
    """Engagement-scoped alert rule with condition and window.

    Attributes:
        id: Unique rule identifier.
        engagement_id: Engagement this rule applies to.
        name: Human-readable rule name.
        description: What this rule detects.
        event_type: Type of events to match.
        condition_field: Metadata field to match on (e.g., "category").
        condition_value: Required value for the field (e.g., "timing_anomaly").
        threshold_count: Number of matches required to fire.
        window_minutes: Time window in minutes for threshold evaluation.
        severity_override: Override severity when rule fires (optional).
        enabled: Whether the rule is active.
    """

    id: str = ""
    engagement_id: str = ""
    name: str = ""
    description: str = ""
    event_type: str = ""
    condition_field: str = ""
    condition_value: str = ""
    threshold_count: int = 1
    window_minutes: int = 60
    severity_override: str = ""
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.id:
            self.id = str(uuid.uuid4())

    def matches_event(self, event: AlertEvent) -> bool:
        """Check if an event matches this rule's condition.

        Args:
            event: Incoming alert event.

        Returns:
            True if the event matches the rule's type and condition.
        """
        if not self.enabled:
            return False
        if event.engagement_id != self.engagement_id:
            return False
        if self.event_type and event.event_type != self.event_type:
            return False
        if self.condition_field and self.condition_value:
            field_value = event.metadata.get(self.condition_field, "")
            if str(field_value) != self.condition_value:
                return False
        return True


@dataclass
class NotificationChannel:
    """Configuration for a notification channel.

    Attributes:
        id: Unique channel identifier.
        engagement_id: Engagement this channel serves.
        channel_type: Type of channel (webhook, slack, email).
        config: Channel-specific configuration (url, headers, etc.).
        min_severity: Minimum severity to trigger notification.
        enabled: Whether the channel is active.
    """

    id: str = ""
    engagement_id: str = ""
    channel_type: str = "webhook"
    config: dict[str, Any] = field(default_factory=dict)
    min_severity: str = "info"
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.id:
            self.id = str(uuid.uuid4())


# ── Deduplication store ──────────────────────────────────────────


class AlertDeduplicator:
    """In-memory alert deduplication with configurable time windows.

    Tracks open alerts by dedup_key and suppresses duplicates within
    the configured window, incrementing occurrence_count instead.
    """

    def __init__(self, default_window_minutes: int = 60) -> None:
        self._default_window = timedelta(minutes=default_window_minutes)
        self._open_alerts: dict[str, Alert] = {}

    def compute_dedup_key(
        self,
        engagement_id: str,
        alert_type: str,
        process_element: str = "",
        rule_id: str = "",
    ) -> str:
        """Compute a deduplication key for an alert.

        Args:
            engagement_id: Engagement ID.
            alert_type: Type of alert.
            process_element: Affected element (optional).
            rule_id: Triggering rule ID (optional).

        Returns:
            Dedup key string.
        """
        parts = [engagement_id, alert_type]
        if process_element:
            parts.append(process_element)
        if rule_id:
            parts.append(rule_id)
        return ":".join(parts)

    def check_and_deduplicate(
        self,
        alert: Alert,
        window: timedelta | None = None,
    ) -> Alert | None:
        """Check if an alert is a duplicate and handle deduplication.

        If a matching open alert exists within the window, increments its
        occurrence_count and updates last_occurred_at. Returns None to
        indicate the new alert was suppressed.

        If no match exists or the window has expired, stores the alert
        and returns it as a new alert.

        Args:
            alert: The candidate alert.
            window: Deduplication window (defaults to configured default).

        Returns:
            The alert if it's new, None if it was deduplicated (suppressed).
        """
        if not alert.dedup_key:
            alert.dedup_key = self.compute_dedup_key(
                alert.engagement_id,
                alert.alert_type,
                alert.process_element,
                alert.rule_id,
            )

        effective_window = window or self._default_window
        existing = self._open_alerts.get(alert.dedup_key)

        if existing is not None:
            elapsed = alert.created_at - existing.created_at
            if elapsed <= effective_window:
                # Suppress duplicate: update existing alert
                existing.occurrence_count += 1
                existing.last_occurred_at = alert.created_at
                existing.source_ids.extend(alert.source_ids)
                return None

        # New alert or expired window
        self._open_alerts[alert.dedup_key] = alert
        return alert

    def get_open_alert(self, dedup_key: str) -> Alert | None:
        """Get an open alert by dedup key."""
        return self._open_alerts.get(dedup_key)

    def clear_expired(self, now: datetime | None = None) -> int:
        """Remove alerts whose window has expired.

        Args:
            now: Current time (defaults to UTC now).

        Returns:
            Number of alerts removed.
        """
        if now is None:
            now = datetime.now(tz=UTC)

        expired_keys = [
            key for key, alert in self._open_alerts.items() if (now - alert.created_at) > self._default_window
        ]

        for key in expired_keys:
            del self._open_alerts[key]

        return len(expired_keys)


# ── Rule evaluator ───────────────────────────────────────────────


class RuleEvaluator:
    """Evaluates alert rules against incoming events with windowed counting.

    Tracks event occurrences per rule within the rule's time window.
    When the threshold is met, generates an alert.
    """

    def __init__(self) -> None:
        # rule_id -> list of (timestamp, event) within window
        self._event_buffer: dict[str, list[tuple[datetime, AlertEvent]]] = {}

    def evaluate(
        self,
        event: AlertEvent,
        rules: list[AlertRule],
    ) -> list[Alert]:
        """Evaluate an event against all applicable rules.

        Args:
            event: Incoming alert event.
            rules: List of rules to evaluate.

        Returns:
            List of alerts generated by rules whose thresholds were met.
        """
        alerts: list[Alert] = []

        for rule in rules:
            if not rule.matches_event(event):
                continue

            # Add event to rule's buffer
            if rule.id not in self._event_buffer:
                self._event_buffer[rule.id] = []

            buffer = self._event_buffer[rule.id]
            buffer.append((event.timestamp, event))

            # Prune events outside the window
            window = timedelta(minutes=rule.window_minutes)
            cutoff = event.timestamp - window
            buffer[:] = [(ts, ev) for ts, ev in buffer if ts > cutoff]

            # Check if threshold is met
            if len(buffer) >= rule.threshold_count:
                severity = rule.severity_override or event.severity
                matched_ids = [ev.source_id for _, ev in buffer if ev.source_id]

                alert = Alert(
                    alert_type=event.event_type,
                    engagement_id=event.engagement_id,
                    severity=severity,
                    title=f"Rule triggered: {rule.name}",
                    description=rule.description,
                    source_ids=matched_ids,
                    process_element=event.process_element,
                    rule_id=rule.id,
                    matched_count=len(buffer),
                    window=f"{rule.window_minutes}m",
                    rule_description=rule.description,
                    created_at=event.timestamp,
                    last_occurred_at=event.timestamp,
                )

                # Clear the buffer after firing
                self._event_buffer[rule.id] = []

                alerts.append(alert)

        return alerts

    def clear_rule_buffer(self, rule_id: str) -> None:
        """Clear the event buffer for a specific rule."""
        self._event_buffer.pop(rule_id, None)


# ── Alert engine ─────────────────────────────────────────────────


class AlertEngine:
    """Central alert engine orchestrating rule evaluation, deduplication, and dispatch.

    Attributes:
        rules: List of configured alert rules.
        channels: List of notification channels.
        alerts: In-memory alert store for query.
        deduplicator: Alert deduplication handler.
        rule_evaluator: Rule evaluation engine.
    """

    def __init__(
        self,
        rules: list[AlertRule] | None = None,
        channels: list[NotificationChannel] | None = None,
        dedup_window_minutes: int = 60,
    ) -> None:
        self.rules: list[AlertRule] = rules or []
        self.channels: list[NotificationChannel] = channels or []
        self.alerts: list[Alert] = []
        self.deduplicator = AlertDeduplicator(dedup_window_minutes)
        self.rule_evaluator = RuleEvaluator()
        self._notification_log: list[dict[str, Any]] = []

    def process_event(self, event: AlertEvent) -> list[Alert]:
        """Process an incoming alert event through the full pipeline.

        1. Create a direct alert from the event
        2. Evaluate rules to generate rule-triggered alerts
        3. Deduplicate all alerts
        4. Route non-suppressed alerts to notification channels

        Args:
            event: Incoming alert event.

        Returns:
            List of new (non-deduplicated) alerts that were created.
        """
        new_alerts: list[Alert] = []

        # Direct alert from event
        direct_alert = Alert(
            alert_type=event.event_type,
            engagement_id=event.engagement_id,
            severity=event.severity,
            title=f"{event.event_type}: {event.process_element or event.source_id}",
            description=event.description,
            source_ids=[event.source_id] if event.source_id else [],
            process_element=event.process_element,
            created_at=event.timestamp,
            last_occurred_at=event.timestamp,
        )

        deduped = self.deduplicator.check_and_deduplicate(direct_alert)
        if deduped is not None:
            self.alerts.append(deduped)
            new_alerts.append(deduped)
            self._dispatch_to_channels(deduped)

        # Rule-triggered alerts
        rule_alerts = self.rule_evaluator.evaluate(event, self.rules)
        for rule_alert in rule_alerts:
            deduped = self.deduplicator.check_and_deduplicate(rule_alert)
            if deduped is not None:
                self.alerts.append(deduped)
                new_alerts.append(deduped)
                self._dispatch_to_channels(deduped)

        return new_alerts

    def _dispatch_to_channels(self, alert: Alert) -> None:
        """Route an alert to applicable notification channels.

        Args:
            alert: Alert to dispatch.
        """
        for channel in self.channels:
            if not channel.enabled:
                continue
            if channel.engagement_id and channel.engagement_id != alert.engagement_id:
                continue
            if not Severity.meets_threshold(alert.severity, channel.min_severity):
                continue

            self._notification_log.append(
                {
                    "channel_id": channel.id,
                    "channel_type": channel.channel_type,
                    "alert_id": alert.id,
                    "severity": alert.severity,
                    "timestamp": alert.created_at.isoformat(),
                    "payload": alert.to_dict(),
                }
            )

            logger.info(
                "Alert %s dispatched to %s channel %s",
                alert.id,
                channel.channel_type,
                channel.id,
            )

    def acknowledge_alert(
        self,
        alert_id: str,
        note: str = "",
    ) -> Alert | None:
        """Acknowledge an alert by ID.

        Args:
            alert_id: ID of the alert to acknowledge.
            note: Optional analyst note.

        Returns:
            The acknowledged alert, or None if not found.
        """
        for alert in self.alerts:
            if alert.id == alert_id:
                alert.acknowledged = True
                alert.acknowledge_note = note
                return alert
        return None

    def query_alerts(
        self,
        engagement_id: str | None = None,
        severity: str | None = None,
        alert_type: str | None = None,
        acknowledged: bool | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Query alerts with filtering and pagination.

        Args:
            engagement_id: Filter by engagement.
            severity: Filter by severity level.
            alert_type: Filter by alert type.
            acknowledged: Filter by acknowledgment status.
            from_date: Filter alerts created after this date.
            to_date: Filter alerts created before this date.
            limit: Maximum results per page.
            offset: Starting position.

        Returns:
            Dict with alerts list, total count, and pagination info.
        """
        filtered = self.alerts

        if engagement_id is not None:
            filtered = [a for a in filtered if a.engagement_id == engagement_id]
        if severity is not None:
            filtered = [a for a in filtered if a.severity == severity]
        if alert_type is not None:
            filtered = [a for a in filtered if a.alert_type == alert_type]
        if acknowledged is not None:
            filtered = [a for a in filtered if a.acknowledged == acknowledged]
        if from_date is not None:
            filtered = [a for a in filtered if a.created_at >= from_date]
        if to_date is not None:
            filtered = [a for a in filtered if a.created_at <= to_date]

        total = len(filtered)
        page = filtered[offset : offset + limit]

        return {
            "alerts": [a.to_dict() for a in page],
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total,
        }

    def get_notification_log(self) -> list[dict[str, Any]]:
        """Get the notification dispatch log for testing/auditing."""
        return list(self._notification_log)
