"""Gradient boosting task classifier for ML-powered action classification.

Uses scikit-learn's GradientBoostingClassifier with calibrated
probabilities for confident, interpretable predictions.

Story #234 — Part of Epic #231 (ML Task Segmentation).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.models.taskmining import ActionCategory
from src.taskmining.aggregation.session import AggregatedSession
from src.taskmining.ml.dataset import TrainingDataset
from src.taskmining.ml.features import (
    FEATURE_SCHEMA_VERSION,
    extract_features,
)

logger = logging.getLogger(__name__)


@dataclass
class MLPrediction:
    """Result of an ML classification prediction."""

    category: ActionCategory
    confidence: float
    probabilities: dict[str, float]


@dataclass
class TrainingMetrics:
    """Metrics from a training run."""

    accuracy: float
    weighted_f1: float
    per_class: dict[str, dict[str, float]]  # label -> {precision, recall, f1}
    sample_count: int
    feature_schema_version: int = FEATURE_SCHEMA_VERSION


class GradientBoostingTaskClassifier:
    """ML classifier for task mining action categories.

    Wraps scikit-learn's GradientBoostingClassifier with:
    - Calibrated probability estimates
    - Graceful fallback when no model is trained
    - Model persistence with schema version checking
    """

    def __init__(self) -> None:
        self._model: Any | None = None
        self._label_encoder: Any | None = None
        self._schema_version: int = FEATURE_SCHEMA_VERSION

    @property
    def is_trained(self) -> bool:
        """Whether a model has been trained or loaded."""
        return self._model is not None

    def train(self, dataset: TrainingDataset) -> TrainingMetrics:
        """Train the classifier on a labeled dataset.

        Args:
            dataset: Training dataset with labeled samples.

        Returns:
            TrainingMetrics with accuracy, F1, per-class scores.

        Raises:
            ValueError: If dataset has fewer than 10 samples.
        """
        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.metrics import (
            accuracy_score,
            classification_report,
            f1_score,
        )
        from sklearn.preprocessing import LabelEncoder

        if dataset.size < 10:
            raise ValueError(f"Need at least 10 samples, got {dataset.size}")

        split = dataset.stratified_split(test_ratio=0.2)

        # Encode labels
        le = LabelEncoder()
        all_labels = split.train_labels + split.test_labels
        le.fit(all_labels)

        y_train = le.transform(split.train_labels)
        y_test = le.transform(split.test_labels)

        # Train gradient boosting
        base_clf = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            min_samples_leaf=5,
            random_state=42,
        )

        # Calibrate probabilities using cross-validation on training data
        # Use 'sigmoid' for binary-like calibration, works well with boosting
        n_folds = min(3, len(set(y_train)))  # can't have more folds than classes
        if n_folds >= 2 and split.train_size >= 2 * n_folds:
            clf = CalibratedClassifierCV(base_clf, cv=n_folds, method="sigmoid")
        else:
            clf = base_clf

        clf.fit(split.train_features, y_train)

        # Evaluate on test set
        y_pred = clf.predict(split.test_features)
        accuracy = float(accuracy_score(y_test, y_pred))
        weighted_f1 = float(f1_score(y_test, y_pred, average="weighted", zero_division=0))

        # Per-class metrics
        report = classification_report(y_test, y_pred, target_names=le.classes_, output_dict=True, zero_division=0)
        per_class = {}
        for label_name in le.classes_:
            if label_name in report:
                per_class[label_name] = {
                    "precision": round(report[label_name]["precision"], 4),
                    "recall": round(report[label_name]["recall"], 4),
                    "f1": round(report[label_name]["f1-score"], 4),
                }

        self._model = clf
        self._label_encoder = le
        self._schema_version = FEATURE_SCHEMA_VERSION

        metrics = TrainingMetrics(
            accuracy=round(accuracy, 4),
            weighted_f1=round(weighted_f1, 4),
            per_class=per_class,
            sample_count=dataset.size,
        )
        logger.info(
            "Model trained: accuracy=%.4f, F1=%.4f, samples=%d",
            metrics.accuracy,
            metrics.weighted_f1,
            metrics.sample_count,
        )
        return metrics

    def predict(self, session: AggregatedSession) -> MLPrediction | None:
        """Predict action category for a session.

        Returns None if no model is trained (signals fallback to rules).

        Args:
            session: Aggregated session to classify.

        Returns:
            MLPrediction with category and confidence, or None.
        """
        if not self.is_trained:
            return None

        features = extract_features(session)
        return self._predict_from_features(features)

    def predict_batch(self, sessions: list[AggregatedSession]) -> list[MLPrediction | None]:
        """Predict categories for multiple sessions."""
        if not self.is_trained:
            return [None] * len(sessions)

        return [self.predict(s) for s in sessions]

    def _predict_from_features(self, features: list[float]) -> MLPrediction | None:
        """Predict from a pre-extracted feature vector."""
        if not self._model or not self._label_encoder:
            return None

        x_input = [features]

        # Get class probabilities
        if hasattr(self._model, "predict_proba"):
            probas = self._model.predict_proba(x_input)[0]
        else:
            # Fallback for non-calibrated model
            pred_idx = self._model.predict(x_input)[0]
            probas = [0.0] * len(self._label_encoder.classes_)
            probas[pred_idx] = 1.0

        # Build probability dict
        prob_dict = {
            label: round(float(prob), 4) for label, prob in zip(self._label_encoder.classes_, probas, strict=False)
        }

        # Find best prediction
        best_idx = int(probas.argmax())
        best_label = self._label_encoder.classes_[best_idx]
        best_confidence = float(probas[best_idx])

        return MLPrediction(
            category=ActionCategory(best_label),
            confidence=round(best_confidence, 4),
            probabilities=prob_dict,
        )

    def save_model(self, path: str | Path) -> None:
        """Persist trained model to disk.

        Args:
            path: File path for the serialized model.

        Raises:
            RuntimeError: If no model has been trained.
        """
        import joblib

        if not self.is_trained:
            raise RuntimeError("No trained model to save")

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "model": self._model,
            "label_encoder": self._label_encoder,
            "schema_version": self._schema_version,
        }
        joblib.dump(data, path)
        logger.info("Model saved to %s", path)

    def load_model(self, path: str | Path) -> bool:
        """Load a trained model from disk.

        Returns False if the file doesn't exist or has an incompatible
        schema version.

        Args:
            path: File path for the serialized model.

        Returns:
            True if loaded successfully, False otherwise.
        """
        import joblib

        path = Path(path)
        if not path.exists():
            logger.info("No model file at %s", path)
            return False

        data = joblib.load(path)
        saved_version = data.get("schema_version", 0)

        if saved_version != FEATURE_SCHEMA_VERSION:
            logger.warning(
                "Model schema version %d != current %d, ignoring saved model",
                saved_version,
                FEATURE_SCHEMA_VERSION,
            )
            return False

        self._model = data["model"]
        self._label_encoder = data["label_encoder"]
        self._schema_version = saved_version
        logger.info("Model loaded from %s (schema v%d)", path, saved_version)
        return True
