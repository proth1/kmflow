"""Real-time alerting system for KMFlow monitoring (Story #366).

Re-exports from classification (legacy alerting) and engine (new alerting).
"""

from src.monitoring.alerting.classification import (
    CATEGORY_SEVERITY,
    classify_severity,
    create_alert_from_deviations,
    generate_dedup_key,
)
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

__all__ = [
    # Legacy classification
    "CATEGORY_SEVERITY",
    "classify_severity",
    "create_alert_from_deviations",
    "generate_dedup_key",
    # Engine
    "Alert",
    "AlertDeduplicator",
    "AlertEngine",
    "AlertEvent",
    "AlertRule",
    "AlertType",
    "NotificationChannel",
    "RuleEvaluator",
    "Severity",
]
