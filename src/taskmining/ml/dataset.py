"""Training data infrastructure for ML task classifier.

Manages labeled datasets for training and evaluating the gradient
boosting classifier. Supports dataset versioning, stratified splits,
and JSON export/import.

Story #233 — Part of Epic #231 (ML Task Segmentation).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from src.core.models.taskmining import ActionCategory
from src.taskmining.aggregation.session import AggregatedSession
from src.taskmining.ml.features import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_VERSION,
    extract_features,
)

logger = logging.getLogger(__name__)


@dataclass
class LabeledSample:
    """A single labeled training sample."""

    features: list[float]
    label: str  # ActionCategory value
    session_id: str | None = None
    source: str = "rule_based"  # rule_based | human | corrected


@dataclass
class DatasetSplit:
    """Train/test split of labeled samples."""

    train_features: list[list[float]] = field(default_factory=list)
    train_labels: list[str] = field(default_factory=list)
    test_features: list[list[float]] = field(default_factory=list)
    test_labels: list[str] = field(default_factory=list)

    @property
    def train_size(self) -> int:
        return len(self.train_labels)

    @property
    def test_size(self) -> int:
        return len(self.test_labels)


@dataclass
class TrainingDataset:
    """A versioned collection of labeled training samples."""

    samples: list[LabeledSample] = field(default_factory=list)
    version: int = 1
    feature_schema_version: int = FEATURE_SCHEMA_VERSION
    feature_names: list[str] = field(default_factory=lambda: list(FEATURE_NAMES))
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def size(self) -> int:
        return len(self.samples)

    @property
    def label_distribution(self) -> dict[str, int]:
        """Count samples per label."""
        dist: dict[str, int] = {}
        for s in self.samples:
            dist[s.label] = dist.get(s.label, 0) + 1
        return dist

    def add_sample(self, sample: LabeledSample) -> None:
        """Add a sample to the dataset."""
        self.samples.append(sample)

    def add_samples(self, samples: list[LabeledSample]) -> None:
        """Add multiple samples and bump version."""
        self.samples.extend(samples)
        self.version += 1

    def stratified_split(
        self, test_ratio: float = 0.2, seed: int = 42
    ) -> DatasetSplit:
        """Split dataset into train/test with stratified sampling.

        Ensures each label has proportional representation in both sets.

        Args:
            test_ratio: Fraction of samples for test set (0.0–1.0).
            seed: Random seed for reproducibility.

        Returns:
            DatasetSplit with train and test partitions.
        """
        import random

        rng = random.Random(seed)

        # Group by label
        by_label: dict[str, list[LabeledSample]] = {}
        for s in self.samples:
            by_label.setdefault(s.label, []).append(s)

        split = DatasetSplit()

        for label, samples in sorted(by_label.items()):
            shuffled = list(samples)
            rng.shuffle(shuffled)
            n_test = max(1, int(len(shuffled) * test_ratio))

            test_samples = shuffled[:n_test]
            train_samples = shuffled[n_test:]

            for s in train_samples:
                split.train_features.append(s.features)
                split.train_labels.append(s.label)
            for s in test_samples:
                split.test_features.append(s.features)
                split.test_labels.append(s.label)

        return split


class DatasetBuilder:
    """Builds training datasets from classified sessions."""

    def build_from_sessions(
        self,
        sessions: list[AggregatedSession],
        labels: list[ActionCategory],
        source: str = "rule_based",
    ) -> TrainingDataset:
        """Build a dataset from sessions with their labels.

        Args:
            sessions: Aggregated sessions.
            labels: Corresponding labels (same length as sessions).
            source: Label source identifier.

        Returns:
            TrainingDataset ready for splitting and training.
        """
        if len(sessions) != len(labels):
            raise ValueError(
                f"Sessions ({len(sessions)}) and labels ({len(labels)}) "
                f"must have same length"
            )

        dataset = TrainingDataset()
        for session, label in zip(sessions, labels):
            features = extract_features(session)
            dataset.add_sample(LabeledSample(
                features=features,
                label=label.value,
                session_id=session.session_id,
                source=source,
            ))

        logger.info(
            "Built dataset with %d samples, distribution: %s",
            dataset.size,
            dataset.label_distribution,
        )
        return dataset


def export_dataset(dataset: TrainingDataset, path: str | Path) -> None:
    """Export dataset to JSON file.

    Args:
        dataset: The dataset to export.
        path: Output file path.
    """
    data = {
        "version": dataset.version,
        "feature_schema_version": dataset.feature_schema_version,
        "feature_names": dataset.feature_names,
        "created_at": dataset.created_at,
        "sample_count": dataset.size,
        "label_distribution": dataset.label_distribution,
        "samples": [
            {
                "features": s.features,
                "label": s.label,
                "session_id": s.session_id,
                "source": s.source,
            }
            for s in dataset.samples
        ],
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    logger.info("Exported dataset v%d (%d samples) to %s", dataset.version, dataset.size, path)


def import_dataset(path: str | Path) -> TrainingDataset:
    """Import dataset from JSON file.

    Args:
        path: Input file path.

    Returns:
        Loaded TrainingDataset.
    """
    with open(path) as f:
        data = json.load(f)

    dataset = TrainingDataset(
        version=data["version"],
        feature_schema_version=data["feature_schema_version"],
        feature_names=data["feature_names"],
        created_at=data["created_at"],
    )
    for s in data["samples"]:
        dataset.add_sample(LabeledSample(
            features=s["features"],
            label=s["label"],
            session_id=s.get("session_id"),
            source=s.get("source", "imported"),
        ))
    logger.info("Imported dataset v%d (%d samples) from %s", dataset.version, dataset.size, path)
    return dataset
