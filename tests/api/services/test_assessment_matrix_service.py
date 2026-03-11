"""Tests for Assessment Overlay Matrix computation service."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from src.api.services.assessment_matrix import (
    ABILITY_WEIGHTS,
    QUADRANT_ABILITY_THRESHOLD,
    QUADRANT_VALUE_THRESHOLD,
    VALUE_WEIGHTS,
    AssessmentMatrixService,
    classify_quadrant,
)
from src.core.models.assessment_matrix import Quadrant


class TestClassifyQuadrant:
    def test_transform(self) -> None:
        assert classify_quadrant(75.0, 75.0) == Quadrant.TRANSFORM

    def test_invest(self) -> None:
        assert classify_quadrant(75.0, 25.0) == Quadrant.INVEST

    def test_maintain(self) -> None:
        assert classify_quadrant(25.0, 75.0) == Quadrant.MAINTAIN

    def test_deprioritize(self) -> None:
        assert classify_quadrant(25.0, 25.0) == Quadrant.DEPRIORITIZE

    def test_boundary_transform(self) -> None:
        assert classify_quadrant(50.0, 50.0) == Quadrant.TRANSFORM

    def test_boundary_invest(self) -> None:
        assert classify_quadrant(50.0, 49.9) == Quadrant.INVEST

    def test_boundary_maintain(self) -> None:
        assert classify_quadrant(49.9, 50.0) == Quadrant.MAINTAIN

    def test_boundary_deprioritize(self) -> None:
        assert classify_quadrant(49.9, 49.9) == Quadrant.DEPRIORITIZE


class TestWeights:
    def test_value_weights_sum_to_one(self) -> None:
        assert abs(sum(VALUE_WEIGHTS.values()) - 1.0) < 1e-9

    def test_ability_weights_sum_to_one(self) -> None:
        assert abs(sum(ABILITY_WEIGHTS.values()) - 1.0) < 1e-9


class TestComputeValueComponents:
    def setup_method(self) -> None:
        self.service = AssessmentMatrixService(AsyncMock())

    def test_volume_impact_scales_with_elements(self) -> None:
        elements = [self._mock_element() for _ in range(7)]
        result = self.service._compute_value_components(elements, {})
        assert result["volume_impact"] == 100.0  # 7 * 15 = 105, capped at 100

    def test_volume_impact_single_element(self) -> None:
        elements = [self._mock_element()]
        result = self.service._compute_value_components(elements, {})
        assert result["volume_impact"] == 15.0

    def test_cost_savings_default_without_simulations(self) -> None:
        elements = [self._mock_element()]
        result = self.service._compute_value_components(elements, {})
        assert result["cost_savings_potential"] == 50.0

    def test_cost_savings_from_simulation_metrics(self) -> None:
        elements = [self._mock_element()]
        sim_metrics = {"scenario1": {"fte_delta": -3.0}}
        result = self.service._compute_value_components(elements, sim_metrics)
        assert result["cost_savings_potential"] == 60.0  # 3 * 20

    def test_risk_reduction_from_evidence_grade(self) -> None:
        elem_a = self._mock_element(evidence_grade="A")
        elem_d = self._mock_element(evidence_grade="D")
        result = self.service._compute_value_components([elem_a, elem_d], {})
        assert result["risk_reduction"] == 60.0  # (90 + 30) / 2

    def test_strategic_alignment_from_confidence(self) -> None:
        elem = self._mock_element(confidence_score=0.8)
        result = self.service._compute_value_components([elem], {})
        assert result["strategic_alignment"] == 80.0

    @staticmethod
    def _mock_element(
        evidence_grade: str = "B",
        confidence_score: float = 0.7,
    ) -> MagicMock:
        elem = MagicMock()
        elem.evidence_grade = evidence_grade
        elem.confidence_score = confidence_score
        elem.element_type = "ACTIVITY"
        elem.name = "Test Activity"
        elem.id = uuid.uuid4()
        elem.brightness_classification = "DIM"
        return elem


class TestComputeAbilityComponents:
    def setup_method(self) -> None:
        self.service = AssessmentMatrixService(AsyncMock())

    def test_process_maturity_from_scores(self) -> None:
        elements = [self._mock_element()]
        maturity = {"process_architecture": 4.0, "technology_and_data": 3.0}
        result = self.service._compute_ability_components(elements, maturity, {})
        # avg maturity = 3.5, (3.5/5)*100 = 70
        assert result["process_maturity"] == 70.0

    def test_process_maturity_default_without_data(self) -> None:
        elements = [self._mock_element()]
        result = self.service._compute_ability_components(elements, {}, {})
        assert result["process_maturity"] == 50.0

    def test_evidence_confidence(self) -> None:
        elem = self._mock_element(confidence_score=0.9)
        result = self.service._compute_ability_components([elem], {}, {})
        assert result["evidence_confidence"] == 90.0

    def test_compliance_readiness_with_data(self) -> None:
        elem = self._mock_element()
        elem_id = str(elem.id)
        compliance = {elem_id: 85.0}
        result = self.service._compute_ability_components([elem], {}, compliance)
        assert result["compliance_readiness"] == 85.0

    def test_resource_availability_bright(self) -> None:
        elem = self._mock_element(brightness="BRIGHT")
        result = self.service._compute_ability_components([elem], {}, {})
        assert result["resource_availability"] == 90.0

    def test_resource_availability_dark(self) -> None:
        elem = self._mock_element(brightness="DARK")
        result = self.service._compute_ability_components([elem], {}, {})
        assert result["resource_availability"] == 20.0

    @staticmethod
    def _mock_element(
        confidence_score: float = 0.7,
        brightness: str = "DIM",
    ) -> MagicMock:
        elem = MagicMock()
        elem.confidence_score = confidence_score
        elem.brightness_classification = brightness
        elem.element_type = "ACTIVITY"
        elem.name = "Test Activity"
        elem.id = uuid.uuid4()
        elem.evidence_grade = "B"
        return elem


class TestQuadrantModel:
    def test_quadrant_values(self) -> None:
        assert Quadrant.TRANSFORM.value == "transform"
        assert Quadrant.INVEST.value == "invest"
        assert Quadrant.MAINTAIN.value == "maintain"
        assert Quadrant.DEPRIORITIZE.value == "deprioritize"

    def test_all_quadrants(self) -> None:
        assert len(Quadrant) == 4

    def test_thresholds_are_midpoint(self) -> None:
        assert QUADRANT_VALUE_THRESHOLD == 50.0
        assert QUADRANT_ABILITY_THRESHOLD == 50.0
