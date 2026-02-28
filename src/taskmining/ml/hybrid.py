"""Hybrid ML + rule-based classification.

Combines ML predictions with rule-based fallback for robust
classification even with limited training data.

Story #235 — Part of Epic #231 (ML Task Segmentation).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.core.models.taskmining import ActionCategory
from src.taskmining.aggregation.classifier import (
    ActionClassifier,
)
from src.taskmining.aggregation.session import AggregatedSession
from src.taskmining.ml.classifier import GradientBoostingTaskClassifier

logger = logging.getLogger(__name__)

# Default ML confidence threshold — below this, fall back to rules
_DEFAULT_ML_THRESHOLD = 0.75


@dataclass
class HybridResult:
    """Result of hybrid classification."""

    category: ActionCategory
    confidence: float
    source: str  # "ml" | "rule_based"
    rule_name: str
    description: str
    ml_confidence: float | None = None
    ml_category: str | None = None


class HybridClassifier:
    """Classifier combining ML predictions with rule-based fallback.

    Strategy:
    1. If ML model is trained, predict with ML
    2. If ML confidence >= threshold, use ML result
    3. Otherwise, fall back to rule-based classifier
    """

    def __init__(
        self,
        ml_classifier: GradientBoostingTaskClassifier | None = None,
        rule_classifier: ActionClassifier | None = None,
        ml_threshold: float = _DEFAULT_ML_THRESHOLD,
    ) -> None:
        self._ml = ml_classifier or GradientBoostingTaskClassifier()
        self._rules = rule_classifier or ActionClassifier()
        self._ml_threshold = ml_threshold

    @property
    def ml_available(self) -> bool:
        """Whether the ML model is trained and ready."""
        return self._ml.is_trained

    def classify(self, session: AggregatedSession) -> HybridResult:
        """Classify a session using hybrid ML + rules strategy.

        Args:
            session: Aggregated session to classify.

        Returns:
            HybridResult with source indicator.
        """
        # Try ML first
        ml_prediction = self._ml.predict(session)

        if ml_prediction and ml_prediction.confidence >= self._ml_threshold:
            return HybridResult(
                category=ml_prediction.category,
                confidence=ml_prediction.confidence,
                source="ml",
                rule_name="ml_model",
                description=f"ML classified as {ml_prediction.category.value} "
                f"(confidence: {ml_prediction.confidence:.2f})",
                ml_confidence=ml_prediction.confidence,
                ml_category=ml_prediction.category.value,
            )

        # Fall back to rules
        rule_result = self._rules.classify(session)

        return HybridResult(
            category=rule_result.category,
            confidence=rule_result.confidence,
            source="rule_based",
            rule_name=rule_result.rule_name,
            description=rule_result.description,
            ml_confidence=ml_prediction.confidence if ml_prediction else None,
            ml_category=ml_prediction.category.value if ml_prediction else None,
        )

    def classify_batch(self, sessions: list[AggregatedSession]) -> list[HybridResult]:
        """Classify multiple sessions."""
        return [self.classify(s) for s in sessions]
