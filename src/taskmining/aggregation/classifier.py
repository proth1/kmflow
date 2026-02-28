"""Action classification rules engine: assigns business categories to aggregated sessions.

Rule-based classifier (Phase 1) that evaluates feature thresholds to assign
one of ActionCategory values. Rules are configurable via YAML.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.core.models.taskmining import ActionCategory
from src.taskmining.aggregation.session import AggregatedSession

logger = logging.getLogger(__name__)

# Communication app bundle identifiers
_COMMUNICATION_APPS = {
    "com.microsoft.Outlook",
    "com.microsoft.teams",
    "com.microsoft.teams2",
    "com.apple.mail",
    "com.tinyspeck.slackmacgap",  # Slack
    "com.google.Gmail",
    "us.zoom.xos",
    "com.apple.FaceTime",
    "Outlook",
    "Teams",
    "Mail",
    "Slack",
    "Zoom",
    "Gmail",
}


@dataclass
class ClassificationResult:
    """Result of classifying an aggregated session."""

    category: ActionCategory
    confidence: float
    rule_name: str
    description: str


@dataclass
class ClassificationRule:
    """A single classification rule with feature thresholds."""

    name: str
    category: ActionCategory
    confidence: float
    conditions: dict[str, Any]

    def evaluate(self, session: AggregatedSession) -> float | None:
        """Evaluate this rule against a session. Returns confidence if matched, None if not."""
        total = session.total_event_count
        if total == 0:
            return None

        for condition, threshold in self.conditions.items():
            if not _check_condition(session, condition, threshold, total):
                return None

        return self.confidence


def _check_condition(
    session: AggregatedSession,
    condition: str,
    threshold: Any,
    total: int,
) -> bool:
    """Check a single condition against session features."""
    if condition == "file_operation_count_min":
        return session.file_operation_count >= threshold
    elif condition == "file_operation_ratio_min":
        return (session.file_operation_count / total) >= threshold if total else False
    elif condition == "keyboard_event_count_min":
        return session.keyboard_event_count >= threshold
    elif condition == "keyboard_ratio_min":
        return (session.keyboard_event_count / total) >= threshold if total else False
    elif condition == "url_navigation_count_min":
        return session.url_navigation_count >= threshold
    elif condition == "scroll_count_min":
        return session.scroll_count >= threshold
    elif condition == "keyboard_event_count_max":
        return session.keyboard_event_count <= threshold
    elif condition == "copy_paste_count_min":
        return session.copy_paste_count >= threshold
    elif condition == "app_in_communication_list":
        return session.app_bundle_id in _COMMUNICATION_APPS
    else:
        logger.error("Unknown classification condition: %s — rule will not match", condition)
        return False


# Default rules when no YAML config is provided
_DEFAULT_RULES = [
    # Communication first: app identity is the strongest signal
    ClassificationRule(
        name="communication",
        category=ActionCategory.COMMUNICATION,
        confidence=0.90,
        conditions={
            "app_in_communication_list": True,
        },
    ),
    ClassificationRule(
        name="file_operation",
        category=ActionCategory.FILE_OPERATION,
        confidence=0.85,
        conditions={
            "file_operation_count_min": 3,
            "file_operation_ratio_min": 0.15,
        },
    ),
    # Review before navigation_scroll: review is a stricter superset (adds copy_paste)
    ClassificationRule(
        name="review",
        category=ActionCategory.REVIEW,
        confidence=0.75,
        conditions={
            "scroll_count_min": 15,
            "keyboard_event_count_max": 10,
            "copy_paste_count_min": 2,
        },
    ),
    ClassificationRule(
        name="data_entry",
        category=ActionCategory.DATA_ENTRY,
        confidence=0.85,
        conditions={
            "keyboard_event_count_min": 30,
            "keyboard_ratio_min": 0.50,
        },
    ),
    ClassificationRule(
        name="navigation_url",
        category=ActionCategory.NAVIGATION,
        confidence=0.80,
        conditions={
            "url_navigation_count_min": 5,
        },
    ),
    ClassificationRule(
        name="navigation_scroll",
        category=ActionCategory.NAVIGATION,
        confidence=0.75,
        conditions={
            "scroll_count_min": 20,
            "keyboard_event_count_max": 10,
        },
    ),
]


class ActionClassifier:
    """Rule-based action classifier for aggregated sessions."""

    def __init__(self, rules: list[ClassificationRule] | None = None) -> None:
        self._rules = rules or list(_DEFAULT_RULES)

    @classmethod
    def from_yaml(cls, config_path: str | Path) -> ActionClassifier:
        """Load classification rules from a YAML file."""
        path = Path(config_path)
        with open(path) as f:
            data = yaml.safe_load(f)

        rules = []
        for rule_data in data.get("rules", []):
            rules.append(
                ClassificationRule(
                    name=rule_data["name"],
                    category=ActionCategory(rule_data["category"]),
                    confidence=rule_data.get("confidence", 0.80),
                    conditions=rule_data.get("conditions", {}),
                )
            )
        return cls(rules=rules)

    def classify(self, session: AggregatedSession) -> ClassificationResult:
        """Classify a single aggregated session.

        Evaluates rules in order. The first matching rule wins.
        If no rule matches, returns UNKNOWN.
        """
        if session.total_event_count == 0:
            return ClassificationResult(
                category=ActionCategory.UNKNOWN,
                confidence=1.0,
                rule_name="empty_session",
                description=f"Empty session in {session.app_bundle_id}",
            )

        for rule in self._rules:
            confidence = rule.evaluate(session)
            if confidence is not None:
                return ClassificationResult(
                    category=rule.category,
                    confidence=confidence,
                    rule_name=rule.name,
                    description=_build_description(session, rule.category),
                )

        return ClassificationResult(
            category=ActionCategory.UNKNOWN,
            confidence=0.50,
            rule_name="no_match",
            description=f"Unclassified activity in {session.app_bundle_id} ({session.total_event_count} events)",
        )

    def classify_batch(self, sessions: list[AggregatedSession]) -> list[ClassificationResult]:
        """Classify multiple sessions."""
        return [self.classify(s) for s in sessions]


def _build_description(session: AggregatedSession, category: ActionCategory) -> str:
    """Build a human-readable description for a classified action."""
    duration_s = session.duration_ms / 1000 if session.duration_ms else 0
    app = session.app_bundle_id

    if category == ActionCategory.FILE_OPERATION:
        return f"File operations in {app} ({session.file_operation_count} ops, {duration_s:.0f}s)"
    elif category == ActionCategory.DATA_ENTRY:
        return f"Data entry in {app} ({session.keyboard_event_count} keystrokes, {duration_s:.0f}s)"
    elif category == ActionCategory.NAVIGATION:
        return f"Navigation in {app} ({session.url_navigation_count} URLs, {session.scroll_count} scrolls, {duration_s:.0f}s)"
    elif category == ActionCategory.COMMUNICATION:
        return f"Communication via {app} ({duration_s:.0f}s)"
    elif category == ActionCategory.REVIEW:
        return f"Document review in {app} ({session.scroll_count} scrolls, {session.copy_paste_count} copies, {duration_s:.0f}s)"
    else:
        return f"Activity in {app} ({session.total_event_count} events, {duration_s:.0f}s)"
