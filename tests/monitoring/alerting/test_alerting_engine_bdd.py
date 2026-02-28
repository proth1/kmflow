"""BDD tests for the real-time alerting engine (Story #366).

Tests cover all acceptance criteria from the story:
- High-severity process deviation triggers alert to configured channel
- Engagement-scoped alert rules fire when conditions match
- Duplicate alerts within window are aggregated
- Alert query API supports multi-dimensional filtering
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.monitoring.alerting.engine import (
    Alert,
    AlertDeduplicator,
    AlertEngine,
    AlertEvent,
    AlertRule,
    AlertType,
    NotificationChannel,
    RuleEvaluator,
    Severity,
)


def _make_event(
    event_type: str = AlertType.PROCESS_DEVIATION,
    engagement_id: str = "eng-1",
    severity: str = "high",
    source_id: str = "dev-001",
    process_element: str = "ReviewLoan",
    description: str = "Process deviation detected",
    metadata: dict | None = None,
    timestamp: datetime | None = None,
) -> AlertEvent:
    """Build a test alert event."""
    return AlertEvent(
        event_type=event_type,
        engagement_id=engagement_id,
        severity=severity,
        source_id=source_id,
        process_element=process_element,
        description=description,
        metadata=metadata or {},
        timestamp=timestamp or datetime(2026, 2, 15, 10, 0, 0, tzinfo=UTC),
    )


def _make_webhook_channel(
    engagement_id: str = "eng-1",
    min_severity: str = "info",
) -> NotificationChannel:
    """Build a test webhook notification channel."""
    return NotificationChannel(
        engagement_id=engagement_id,
        channel_type="webhook",
        config={"url": "https://hooks.example.com/alerts"},
        min_severity=min_severity,
    )


# ============================================================
# Scenario 1: High-severity process deviation triggers alert
# ============================================================


class TestProcessDeviationAlert:
    """Given a process deviation of severity HIGH has been detected,
    and a notification channel is configured, the alerting system
    generates and routes an alert."""

    def test_high_severity_deviation_generates_alert(self) -> None:
        """HIGH deviation creates an alert with correct type and severity."""
        channel = _make_webhook_channel()
        engine = AlertEngine(channels=[channel])

        event = _make_event(severity="high")
        alerts = engine.process_event(event)

        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.alert_type == AlertType.PROCESS_DEVIATION
        assert alert.severity == "high"

    def test_alert_routed_to_configured_channel(self) -> None:
        """Alert is dispatched to the webhook notification channel."""
        channel = _make_webhook_channel()
        engine = AlertEngine(channels=[channel])

        event = _make_event(severity="high")
        engine.process_event(event)

        log = engine.get_notification_log()
        assert len(log) == 1
        assert log[0]["channel_type"] == "webhook"
        assert log[0]["severity"] == "high"

    def test_alert_payload_includes_required_fields(self) -> None:
        """Alert payload includes deviation_id, process_element, severity, engagement_id."""
        channel = _make_webhook_channel()
        engine = AlertEngine(channels=[channel])

        event = _make_event(
            source_id="dev-123",
            process_element="ReviewLoan",
            severity="high",
            engagement_id="eng-42",
        )
        alerts = engine.process_event(event)

        alert = alerts[0]
        payload = alert.to_dict()
        assert payload["engagement_id"] == "eng-42"
        assert payload["severity"] == "high"
        assert payload["process_element"] == "ReviewLoan"
        assert "dev-123" in payload["source_ids"]

    def test_alert_has_unique_id_and_timestamp(self) -> None:
        """Each alert has a unique UUID and creation timestamp."""
        engine = AlertEngine(channels=[_make_webhook_channel()])
        alerts = engine.process_event(_make_event())

        alert = alerts[0]
        assert len(alert.id) == 36  # UUID format
        assert alert.created_at is not None

    def test_channel_min_severity_filters_low_alerts(self) -> None:
        """Channel with min_severity=high filters out LOW alerts."""
        channel = _make_webhook_channel(min_severity="high")
        engine = AlertEngine(channels=[channel])

        event = _make_event(severity="low")
        engine.process_event(event)

        log = engine.get_notification_log()
        assert len(log) == 0

    def test_disabled_channel_not_dispatched(self) -> None:
        """Disabled channels don't receive notifications."""
        channel = _make_webhook_channel()
        channel.enabled = False
        engine = AlertEngine(channels=[channel])

        engine.process_event(_make_event())

        assert len(engine.get_notification_log()) == 0

    def test_channel_engagement_scope_enforced(self) -> None:
        """Channel only receives alerts for its engagement."""
        channel = _make_webhook_channel(engagement_id="eng-1")
        engine = AlertEngine(channels=[channel])

        event = _make_event(engagement_id="eng-other")
        engine.process_event(event)

        assert len(engine.get_notification_log()) == 0


# ============================================================
# Scenario 2: Engagement-scoped alert rules fire on condition
# ============================================================


class TestAlertRuleFiring:
    """Given an alert rule configured for engagement E1 with a threshold,
    when the threshold is exceeded within the window, the rule fires."""

    def test_rule_fires_when_threshold_exceeded(self) -> None:
        """Rule with threshold=3 fires after 3 matching events in the window."""
        rule = AlertRule(
            engagement_id="eng-1",
            name="Timing anomalies spike",
            description="fire if timing anomaly deviations > 3 in 1 hour",
            event_type=AlertType.PROCESS_DEVIATION,
            condition_field="category",
            condition_value="timing_anomaly",
            threshold_count=3,
            window_minutes=60,
        )

        engine = AlertEngine(rules=[rule], channels=[_make_webhook_channel()])

        base_ts = datetime(2026, 2, 15, 10, 0, 0, tzinfo=UTC)

        # Send 3 events within the window (threshold = 3)
        for i in range(3):
            event = _make_event(
                source_id=f"dev-{i}",
                metadata={"category": "timing_anomaly"},
                timestamp=base_ts + timedelta(minutes=i * 10),
            )
            engine.process_event(event)

        # The rule should have fired after the threshold was met
        rule_alerts = [a for a in engine.alerts if a.rule_id == rule.id]
        assert len(rule_alerts) == 1

    def test_rule_alert_includes_rule_metadata(self) -> None:
        """Rule-triggered alert includes rule_id, matched_count, and window."""
        rule = AlertRule(
            engagement_id="eng-1",
            name="High deviation spike",
            description="3+ high deviations in 1h",
            event_type=AlertType.PROCESS_DEVIATION,
            threshold_count=2,
            window_minutes=60,
        )

        engine = AlertEngine(rules=[rule], channels=[_make_webhook_channel()])
        base_ts = datetime(2026, 2, 15, 10, 0, 0, tzinfo=UTC)

        for i in range(2):
            engine.process_event(
                _make_event(
                    source_id=f"dev-{i}",
                    timestamp=base_ts + timedelta(minutes=i * 5),
                )
            )

        rule_alerts = [a for a in engine.alerts if a.rule_id == rule.id]
        assert len(rule_alerts) == 1
        alert = rule_alerts[0]
        assert alert.matched_count == 2
        assert alert.window == "60m"
        assert alert.rule_description == "3+ high deviations in 1h"

    def test_rule_includes_matching_deviation_ids(self) -> None:
        """Rule-triggered alert includes IDs of matching deviations."""
        rule = AlertRule(
            engagement_id="eng-1",
            name="Multi-match",
            event_type=AlertType.PROCESS_DEVIATION,
            threshold_count=2,
            window_minutes=60,
        )

        engine = AlertEngine(rules=[rule])
        base_ts = datetime(2026, 2, 15, 10, 0, 0, tzinfo=UTC)

        engine.process_event(_make_event(source_id="dev-A", timestamp=base_ts))
        engine.process_event(
            _make_event(
                source_id="dev-B",
                timestamp=base_ts + timedelta(minutes=5),
            )
        )

        rule_alerts = [a for a in engine.alerts if a.rule_id == rule.id]
        assert len(rule_alerts) == 1
        assert "dev-A" in rule_alerts[0].source_ids
        assert "dev-B" in rule_alerts[0].source_ids

    def test_rule_not_fired_below_threshold(self) -> None:
        """Rule doesn't fire when event count is below threshold."""
        rule = AlertRule(
            engagement_id="eng-1",
            name="Need 5",
            event_type=AlertType.PROCESS_DEVIATION,
            threshold_count=5,
            window_minutes=60,
        )

        engine = AlertEngine(rules=[rule])
        for i in range(4):
            engine.process_event(
                _make_event(
                    source_id=f"dev-{i}",
                    timestamp=datetime(2026, 2, 15, 10, i, 0, tzinfo=UTC),
                )
            )

        rule_alerts = [a for a in engine.alerts if a.rule_id == rule.id]
        assert len(rule_alerts) == 0

    def test_events_outside_window_not_counted(self) -> None:
        """Events outside the rule window are pruned and don't count."""
        rule = AlertRule(
            engagement_id="eng-1",
            name="Short window",
            event_type=AlertType.PROCESS_DEVIATION,
            threshold_count=3,
            window_minutes=30,
        )

        engine = AlertEngine(rules=[rule])
        base_ts = datetime(2026, 2, 15, 10, 0, 0, tzinfo=UTC)

        # First event at T=0
        engine.process_event(_make_event(source_id="d-1", timestamp=base_ts))
        # Second at T=20 (within window)
        engine.process_event(
            _make_event(
                source_id="d-2",
                timestamp=base_ts + timedelta(minutes=20),
            )
        )
        # Third at T=50 (T=0 is now outside 30-min window)
        engine.process_event(
            _make_event(
                source_id="d-3",
                timestamp=base_ts + timedelta(minutes=50),
            )
        )

        # Rule shouldn't fire: only d-2 and d-3 are within window at T=50
        rule_alerts = [a for a in engine.alerts if a.rule_id == rule.id]
        assert len(rule_alerts) == 0

    def test_disabled_rule_not_evaluated(self) -> None:
        """Disabled rules are not evaluated."""
        rule = AlertRule(
            engagement_id="eng-1",
            event_type=AlertType.PROCESS_DEVIATION,
            threshold_count=1,
            enabled=False,
        )

        engine = AlertEngine(rules=[rule])
        engine.process_event(_make_event())

        rule_alerts = [a for a in engine.alerts if a.rule_id == rule.id]
        assert len(rule_alerts) == 0

    def test_rule_condition_field_filtering(self) -> None:
        """Rule only matches events with the specified condition field value."""
        rule = AlertRule(
            engagement_id="eng-1",
            event_type=AlertType.PROCESS_DEVIATION,
            condition_field="category",
            condition_value="timing_anomaly",
            threshold_count=1,
        )

        engine = AlertEngine(rules=[rule])

        # Non-matching event
        engine.process_event(
            _make_event(
                metadata={"category": "control_bypass"},
                source_id="d-1",
            )
        )
        rule_alerts = [a for a in engine.alerts if a.rule_id == rule.id]
        assert len(rule_alerts) == 0

        # Matching event
        engine.process_event(
            _make_event(
                metadata={"category": "timing_anomaly"},
                source_id="d-2",
            )
        )
        rule_alerts = [a for a in engine.alerts if a.rule_id == rule.id]
        assert len(rule_alerts) == 1


# ============================================================
# Scenario 3: Duplicate alerts aggregated within window
# ============================================================


class TestDuplicateAlertAggregation:
    """Given an alert fires for the same condition multiple times within
    the dedup window, duplicates are suppressed and aggregated."""

    def test_duplicate_suppressed_and_count_incremented(self) -> None:
        """Second alert with same dedup key within window is suppressed."""
        deduplicator = AlertDeduplicator(default_window_minutes=60)
        base_ts = datetime(2026, 2, 15, 10, 0, 0, tzinfo=UTC)

        alert1 = Alert(
            alert_type=AlertType.PROCESS_DEVIATION,
            engagement_id="eng-1",
            severity="high",
            dedup_key="eng-1:PROCESS_DEVIATION:ReviewLoan",
            created_at=base_ts,
        )
        alert2 = Alert(
            alert_type=AlertType.PROCESS_DEVIATION,
            engagement_id="eng-1",
            severity="high",
            dedup_key="eng-1:PROCESS_DEVIATION:ReviewLoan",
            source_ids=["dev-2"],
            created_at=base_ts + timedelta(minutes=15),
        )

        result1 = deduplicator.check_and_deduplicate(alert1)
        result2 = deduplicator.check_and_deduplicate(alert2)

        assert result1 is not None  # New alert
        assert result2 is None  # Suppressed
        assert result1.occurrence_count == 2

    def test_third_duplicate_increments_to_three(self) -> None:
        """Third duplicate within 45 minutes increments count to 3."""
        deduplicator = AlertDeduplicator(default_window_minutes=60)
        base_ts = datetime(2026, 2, 15, 10, 0, 0, tzinfo=UTC)
        key = "eng-1:PROCESS_DEVIATION:ReviewLoan"

        alerts = [
            Alert(dedup_key=key, engagement_id="eng-1", created_at=base_ts),
            Alert(dedup_key=key, engagement_id="eng-1", created_at=base_ts + timedelta(minutes=15)),
            Alert(dedup_key=key, engagement_id="eng-1", created_at=base_ts + timedelta(minutes=45)),
        ]

        results = [deduplicator.check_and_deduplicate(a) for a in alerts]

        assert results[0] is not None
        assert results[1] is None
        assert results[2] is None
        assert results[0].occurrence_count == 3

    def test_last_occurred_at_updated(self) -> None:
        """Aggregated alert's last_occurred_at is updated to latest timestamp."""
        deduplicator = AlertDeduplicator(default_window_minutes=60)
        base_ts = datetime(2026, 2, 15, 10, 0, 0, tzinfo=UTC)
        key = "eng-1:dedup-test"

        alert1 = Alert(dedup_key=key, engagement_id="eng-1", created_at=base_ts)
        alert2 = Alert(dedup_key=key, engagement_id="eng-1", created_at=base_ts + timedelta(minutes=30))

        deduplicator.check_and_deduplicate(alert1)
        deduplicator.check_and_deduplicate(alert2)

        stored = deduplicator.get_open_alert(key)
        assert stored is not None
        assert stored.last_occurred_at == base_ts + timedelta(minutes=30)

    def test_channel_receives_single_notification(self) -> None:
        """Channel receives only one notification despite 3 duplicate events."""
        channel = _make_webhook_channel()
        engine = AlertEngine(channels=[channel])
        base_ts = datetime(2026, 2, 15, 10, 0, 0, tzinfo=UTC)

        for i in range(3):
            engine.process_event(
                _make_event(
                    source_id=f"dev-{i}",
                    timestamp=base_ts + timedelta(minutes=i * 10),
                )
            )

        log = engine.get_notification_log()
        # Only the first event triggers a notification
        assert len(log) == 1

    def test_expired_window_allows_new_alert(self) -> None:
        """Alert after the dedup window expires creates a new alert."""
        deduplicator = AlertDeduplicator(default_window_minutes=60)
        base_ts = datetime(2026, 2, 15, 10, 0, 0, tzinfo=UTC)
        key = "eng-1:expired-test"

        alert1 = Alert(dedup_key=key, engagement_id="eng-1", created_at=base_ts)
        alert2 = Alert(dedup_key=key, engagement_id="eng-1", created_at=base_ts + timedelta(hours=2))

        result1 = deduplicator.check_and_deduplicate(alert1)
        result2 = deduplicator.check_and_deduplicate(alert2)

        # Both should be new (window expired)
        assert result1 is not None
        assert result2 is not None

    def test_dedup_key_auto_computed(self) -> None:
        """Dedup key is auto-computed if not provided."""
        deduplicator = AlertDeduplicator()
        alert = Alert(
            alert_type=AlertType.PROCESS_DEVIATION,
            engagement_id="eng-1",
            process_element="Submit",
        )
        result = deduplicator.check_and_deduplicate(alert)
        assert result is not None
        assert result.dedup_key == "eng-1:PROCESS_DEVIATION:Submit"

    def test_clear_expired_removes_old_alerts(self) -> None:
        """clear_expired removes alerts older than the window."""
        deduplicator = AlertDeduplicator(default_window_minutes=60)
        old_ts = datetime(2026, 2, 15, 8, 0, 0, tzinfo=UTC)
        now = datetime(2026, 2, 15, 10, 0, 0, tzinfo=UTC)

        alert = Alert(dedup_key="old-key", engagement_id="eng-1", created_at=old_ts)
        deduplicator.check_and_deduplicate(alert)

        removed = deduplicator.clear_expired(now=now)
        assert removed == 1
        assert deduplicator.get_open_alert("old-key") is None


# ============================================================
# Scenario 4: Alert query API with multi-dimensional filtering
# ============================================================


class TestAlertQueryFiltering:
    """Given multiple alerts exist across engagements and severities,
    the query API returns filtered, paginated results."""

    def _build_engine_with_alerts(self) -> AlertEngine:
        """Create an engine with diverse alerts for query testing."""
        engine = AlertEngine()
        base_ts = datetime(2026, 2, 15, 10, 0, 0, tzinfo=UTC)

        test_alerts = [
            Alert(
                id="a1",
                alert_type=AlertType.PROCESS_DEVIATION,
                engagement_id="eng-1",
                severity="high",
                acknowledged=False,
                created_at=base_ts,
            ),
            Alert(
                id="a2",
                alert_type=AlertType.PROCESS_DEVIATION,
                engagement_id="eng-1",
                severity="medium",
                acknowledged=True,
                created_at=base_ts + timedelta(hours=1),
            ),
            Alert(
                id="a3",
                alert_type=AlertType.SLA_BREACH,
                engagement_id="eng-2",
                severity="critical",
                acknowledged=False,
                created_at=base_ts + timedelta(hours=2),
            ),
            Alert(
                id="a4",
                alert_type=AlertType.EVIDENCE_QUALITY_DROP,
                engagement_id="eng-1",
                severity="high",
                acknowledged=False,
                created_at=base_ts + timedelta(hours=3),
            ),
            Alert(
                id="a5",
                alert_type=AlertType.PROCESS_DEVIATION,
                engagement_id="eng-2",
                severity="low",
                acknowledged=False,
                created_at=datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
            ),
        ]
        engine.alerts = test_alerts
        return engine

    def test_filter_by_severity(self) -> None:
        """Filter by severity=HIGH returns only HIGH alerts."""
        engine = self._build_engine_with_alerts()
        result = engine.query_alerts(severity="high")
        assert result["total"] == 2
        assert all(a["severity"] == "high" for a in result["alerts"])

    def test_filter_by_acknowledged_false(self) -> None:
        """Filter acknowledged=false returns unacknowledged alerts."""
        engine = self._build_engine_with_alerts()
        result = engine.query_alerts(acknowledged=False)
        assert result["total"] == 4
        assert all(not a["acknowledged"] for a in result["alerts"])

    def test_filter_by_from_date(self) -> None:
        """Filter from_date returns alerts after the specified date."""
        engine = self._build_engine_with_alerts()
        from_date = datetime(2026, 2, 1, 0, 0, 0, tzinfo=UTC)
        result = engine.query_alerts(from_date=from_date)
        assert result["total"] == 4  # Excludes a5 (Jan 15)

    def test_combined_filters(self) -> None:
        """Combined severity + acknowledged + from_date filters work together."""
        engine = self._build_engine_with_alerts()
        result = engine.query_alerts(
            severity="high",
            acknowledged=False,
            from_date=datetime(2026, 2, 1, 0, 0, 0, tzinfo=UTC),
        )
        assert result["total"] == 2  # a1, a4
        ids = [a["id"] for a in result["alerts"]]
        assert "a1" in ids
        assert "a4" in ids

    def test_filter_by_engagement(self) -> None:
        """Filter by engagement_id returns only that engagement's alerts."""
        engine = self._build_engine_with_alerts()
        result = engine.query_alerts(engagement_id="eng-2")
        assert result["total"] == 2
        assert all(a["engagement_id"] == "eng-2" for a in result["alerts"])

    def test_filter_by_alert_type(self) -> None:
        """Filter by alert_type returns only matching types."""
        engine = self._build_engine_with_alerts()
        result = engine.query_alerts(alert_type=AlertType.PROCESS_DEVIATION)
        assert result["total"] == 3

    def test_pagination_limit_and_offset(self) -> None:
        """Pagination returns correct page with limit/offset."""
        engine = self._build_engine_with_alerts()
        result = engine.query_alerts(limit=2, offset=0)
        assert len(result["alerts"]) == 2
        assert result["total"] == 5
        assert result["has_more"] is True

        result2 = engine.query_alerts(limit=2, offset=4)
        assert len(result2["alerts"]) == 1
        assert result2["has_more"] is False

    def test_each_alert_includes_required_fields(self) -> None:
        """Each alert in query results includes all required fields."""
        engine = self._build_engine_with_alerts()
        result = engine.query_alerts()
        required_fields = {
            "id",
            "alert_type",
            "severity",
            "acknowledged",
            "occurrence_count",
            "created_at",
            "last_occurred_at",
        }
        for alert_dict in result["alerts"]:
            assert required_fields.issubset(alert_dict.keys())


# ============================================================
# Alert acknowledgment
# ============================================================


class TestAlertAcknowledgment:
    """Tests for alert acknowledgment functionality."""

    def test_acknowledge_alert_by_id(self) -> None:
        """Acknowledging an alert sets acknowledged=True."""
        engine = AlertEngine()
        engine.alerts = [Alert(id="a1", engagement_id="eng-1")]

        result = engine.acknowledge_alert("a1", note="Reviewed by analyst")
        assert result is not None
        assert result.acknowledged is True
        assert result.acknowledge_note == "Reviewed by analyst"

    def test_acknowledge_nonexistent_returns_none(self) -> None:
        """Acknowledging a non-existent alert returns None."""
        engine = AlertEngine()
        result = engine.acknowledge_alert("nonexistent")
        assert result is None


# ============================================================
# Severity utility tests
# ============================================================


class TestSeverityUtilities:
    """Tests for severity ranking and threshold checking."""

    def test_severity_ranking_order(self) -> None:
        """Severity ranks are ordered: critical > high > medium > low > info."""
        assert Severity.rank("critical") > Severity.rank("high")
        assert Severity.rank("high") > Severity.rank("medium")
        assert Severity.rank("medium") > Severity.rank("low")
        assert Severity.rank("low") > Severity.rank("info")

    def test_meets_threshold_high_vs_medium(self) -> None:
        """HIGH meets a MEDIUM threshold."""
        assert Severity.meets_threshold("high", "medium") is True
        assert Severity.meets_threshold("low", "high") is False

    def test_meets_threshold_equal(self) -> None:
        """Same severity meets its own threshold."""
        assert Severity.meets_threshold("high", "high") is True

    def test_unknown_severity_ranks_zero(self) -> None:
        """Unknown severity string ranks as 0."""
        assert Severity.rank("unknown") == 0


# ============================================================
# AlertRule matching tests
# ============================================================


class TestAlertRuleMatching:
    """Tests for AlertRule.matches_event()."""

    def test_rule_matches_correct_engagement_and_type(self) -> None:
        """Rule matches event with correct engagement and type."""
        rule = AlertRule(
            engagement_id="eng-1",
            event_type=AlertType.PROCESS_DEVIATION,
        )
        event = _make_event(engagement_id="eng-1")
        assert rule.matches_event(event) is True

    def test_rule_rejects_wrong_engagement(self) -> None:
        """Rule rejects event from different engagement."""
        rule = AlertRule(engagement_id="eng-1")
        event = _make_event(engagement_id="eng-other")
        assert rule.matches_event(event) is False

    def test_rule_rejects_wrong_event_type(self) -> None:
        """Rule rejects event with wrong type."""
        rule = AlertRule(
            engagement_id="eng-1",
            event_type=AlertType.SLA_BREACH,
        )
        event = _make_event(event_type=AlertType.PROCESS_DEVIATION)
        assert rule.matches_event(event) is False

    def test_rule_with_no_type_matches_any(self) -> None:
        """Rule with empty event_type matches any event type."""
        rule = AlertRule(engagement_id="eng-1", event_type="")
        event = _make_event(event_type=AlertType.SLA_BREACH)
        assert rule.matches_event(event) is True


# ============================================================
# RuleEvaluator tests
# ============================================================


class TestRuleEvaluator:
    """Tests for the standalone rule evaluator."""

    def test_evaluator_clears_buffer_after_firing(self) -> None:
        """Rule buffer is cleared after the rule fires."""
        evaluator = RuleEvaluator()
        rule = AlertRule(
            engagement_id="eng-1",
            event_type=AlertType.PROCESS_DEVIATION,
            threshold_count=2,
            window_minutes=60,
        )
        base_ts = datetime(2026, 2, 15, 10, 0, 0, tzinfo=UTC)

        evaluator.evaluate(_make_event(timestamp=base_ts), [rule])
        alerts = evaluator.evaluate(
            _make_event(timestamp=base_ts + timedelta(minutes=5)),
            [rule],
        )

        assert len(alerts) == 1

        # After firing, buffer should be empty — need 2 more events to fire again
        alerts2 = evaluator.evaluate(
            _make_event(timestamp=base_ts + timedelta(minutes=10)),
            [rule],
        )
        assert len(alerts2) == 0

    def test_clear_rule_buffer(self) -> None:
        """clear_rule_buffer removes buffered events for a rule."""
        evaluator = RuleEvaluator()
        rule = AlertRule(
            id="rule-1",
            engagement_id="eng-1",
            event_type=AlertType.PROCESS_DEVIATION,
            threshold_count=3,
        )

        evaluator.evaluate(_make_event(), [rule])
        evaluator.clear_rule_buffer("rule-1")

        # Need 3 fresh events now
        alerts = evaluator.evaluate(_make_event(), [rule])
        assert len(alerts) == 0


# ============================================================
# Dataclass tests
# ============================================================


class TestAlertDataclass:
    """Tests for Alert dataclass."""

    def test_auto_generates_id(self) -> None:
        """Alert auto-generates UUID if not provided."""
        alert = Alert()
        assert len(alert.id) == 36

    def test_to_dict_all_fields(self) -> None:
        """to_dict includes all expected fields."""
        alert = Alert(
            id="test-id",
            alert_type=AlertType.PROCESS_DEVIATION,
            engagement_id="eng-1",
            severity="high",
            occurrence_count=3,
        )
        d = alert.to_dict()
        assert d["id"] == "test-id"
        assert d["alert_type"] == AlertType.PROCESS_DEVIATION
        assert d["occurrence_count"] == 3
        assert "created_at" in d
        assert "last_occurred_at" in d


class TestNotificationChannel:
    """Tests for NotificationChannel dataclass."""

    def test_auto_generates_id(self) -> None:
        """Channel auto-generates UUID if not provided."""
        channel = NotificationChannel()
        assert len(channel.id) == 36

    def test_default_values(self) -> None:
        """Channel has sensible defaults."""
        channel = NotificationChannel()
        assert channel.channel_type == "webhook"
        assert channel.min_severity == "info"
        assert channel.enabled is True
