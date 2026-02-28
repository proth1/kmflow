"""Tests for POV constants including task mining weight (Story #228)."""

from __future__ import annotations

import pytest

from src.pov.constants import (
    CONFIDENCE_FACTOR_WEIGHTS,
    CONFIDENCE_LEVELS,
    EVIDENCE_TYPE_WEIGHTS,
)


class TestEvidenceTypeWeights:
    def test_task_mining_weight_is_0_90(self):
        assert EVIDENCE_TYPE_WEIGHTS["task_mining"] == 0.90

    def test_task_mining_above_bpm_process_models(self):
        assert EVIDENCE_TYPE_WEIGHTS["task_mining"] > EVIDENCE_TYPE_WEIGHTS["bpm_process_models"]

    def test_task_mining_above_documents(self):
        assert EVIDENCE_TYPE_WEIGHTS["task_mining"] > EVIDENCE_TYPE_WEIGHTS["documents"]

    def test_task_mining_below_structured_data(self):
        assert EVIDENCE_TYPE_WEIGHTS["task_mining"] < EVIDENCE_TYPE_WEIGHTS["structured_data"]

    def test_existing_weights_unmodified(self):
        assert EVIDENCE_TYPE_WEIGHTS["structured_data"] == 1.0
        assert EVIDENCE_TYPE_WEIGHTS["bpm_process_models"] == 0.85
        assert EVIDENCE_TYPE_WEIGHTS["documents"] == 0.75
        assert EVIDENCE_TYPE_WEIGHTS["controls_evidence"] == 0.70
        assert EVIDENCE_TYPE_WEIGHTS["km4work"] == 0.35

    def test_all_weights_between_0_and_1(self):
        for key, weight in EVIDENCE_TYPE_WEIGHTS.items():
            assert 0.0 <= weight <= 1.0, f"Weight for {key} out of range: {weight}"


class TestConfidenceFactorWeights:
    def test_weights_sum_to_one(self):
        total = sum(CONFIDENCE_FACTOR_WEIGHTS.values())
        assert total == pytest.approx(1.0)


class TestConfidenceLevels:
    def test_descending_thresholds(self):
        thresholds = [t for _, t in CONFIDENCE_LEVELS]
        assert thresholds == sorted(thresholds, reverse=True)
