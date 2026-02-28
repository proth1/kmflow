"""BDD tests for Evidence Confidence Overlay service (Story #385).

Scenarios:
  1. Dark Area Modification Warning
  2. Per-Element Brightness Coverage
  3. Comparative Risk Assessment
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.services.evidence_coverage import EvidenceCoverageService
from src.core.models.pov import BrightnessClassification
from src.core.models.simulation import ScenarioModification, SimulationScenario

ENGAGEMENT_ID = uuid.uuid4()
SCENARIO_A_ID = uuid.uuid4()
SCENARIO_B_ID = uuid.uuid4()


def _mock_scenario(scenario_id: uuid.UUID, engagement_id: uuid.UUID) -> SimulationScenario:
    s = MagicMock(spec=SimulationScenario)
    s.id = scenario_id
    s.engagement_id = engagement_id
    return s


def _mock_modification(element_id: str, element_name: str) -> ScenarioModification:
    m = MagicMock(spec=ScenarioModification)
    m.element_id = element_id
    m.element_name = element_name
    return m


def _setup_scenario_query(
    mock_session: AsyncMock,
    scenario: SimulationScenario | None,
) -> None:
    """Configure session to return a scenario from scalar_one_or_none."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = scenario
    mock_session.execute.return_value = result_mock


def _setup_multi_execute(
    mock_session: AsyncMock,
    scenario: SimulationScenario | None,
    modifications: list[ScenarioModification],
    brightness_rows: list[tuple[str, BrightnessClassification]],
) -> None:
    """Configure session.execute to return scenario, then mods, then brightness."""
    # Call 1: scenario query (scalar_one_or_none)
    scenario_result = MagicMock()
    scenario_result.scalar_one_or_none.return_value = scenario

    # Call 2: modifications query (scalars().all())
    mods_result = MagicMock()
    mods_scalars = MagicMock()
    mods_scalars.all.return_value = modifications
    mods_result.scalars.return_value = mods_scalars

    # Call 3: brightness query (all())
    brightness_result = MagicMock()
    brightness_result.all.return_value = brightness_rows

    mock_session.execute = AsyncMock(side_effect=[scenario_result, mods_result, brightness_result])


class TestDarkAreaModificationWarning:
    """Scenario 1: Dark Area Modification Warning.

    Given a scenario that modifies a process element with brightness="dark"
    When the evidence confidence overlay is loaded for that scenario
    Then a warning flag is returned for that element
      And the warning message states "Modifying area with insufficient evidence"
      And the element_id and current brightness are included in the warning
    """

    @pytest.mark.asyncio
    async def test_dark_element_generates_warning(self) -> None:
        mock_session = AsyncMock()
        scenario = _mock_scenario(SCENARIO_A_ID, ENGAGEMENT_ID)
        mods = [_mock_modification("elem-dark-1", "Verify Documents")]

        _setup_multi_execute(
            mock_session,
            scenario,
            mods,
            [("elem-dark-1", BrightnessClassification.DARK)],
        )

        service = EvidenceCoverageService(mock_session)
        result = await service.get_scenario_coverage(SCENARIO_A_ID, ENGAGEMENT_ID)

        elements = result["modified_elements"]
        assert len(elements) == 1
        elem = elements[0]
        assert elem["element_id"] == "elem-dark-1"
        assert elem["brightness"] == "dark"
        assert elem["warning"] is True
        assert elem["warning_message"] == "Modifying area with insufficient evidence"

    @pytest.mark.asyncio
    async def test_bright_element_no_warning(self) -> None:
        mock_session = AsyncMock()
        scenario = _mock_scenario(SCENARIO_A_ID, ENGAGEMENT_ID)
        mods = [_mock_modification("elem-bright-1", "Submit Application")]

        _setup_multi_execute(
            mock_session,
            scenario,
            mods,
            [("elem-bright-1", BrightnessClassification.BRIGHT)],
        )

        service = EvidenceCoverageService(mock_session)
        result = await service.get_scenario_coverage(SCENARIO_A_ID, ENGAGEMENT_ID)

        elem = result["modified_elements"][0]
        assert elem["warning"] is False
        assert elem["warning_message"] is None

    @pytest.mark.asyncio
    async def test_dim_element_no_warning(self) -> None:
        mock_session = AsyncMock()
        scenario = _mock_scenario(SCENARIO_A_ID, ENGAGEMENT_ID)
        mods = [_mock_modification("elem-dim-1", "Review Claims")]

        _setup_multi_execute(
            mock_session,
            scenario,
            mods,
            [("elem-dim-1", BrightnessClassification.DIM)],
        )

        service = EvidenceCoverageService(mock_session)
        result = await service.get_scenario_coverage(SCENARIO_A_ID, ENGAGEMENT_ID)

        elem = result["modified_elements"][0]
        assert elem["warning"] is False
        assert elem["warning_message"] is None


class TestPerElementBrightnessCoverage:
    """Scenario 2: Per-Element Brightness Coverage.

    Given a scenario with 8 modifications across Bright, Dim, and Dark elements
    When GET /api/v1/scenarios/{id}/evidence-coverage is called
    Then the response includes per-element brightness classification for each modified element
      And unmodified elements are not included in the response
    """

    @pytest.mark.asyncio
    async def test_eight_modifications_all_classified(self) -> None:
        mock_session = AsyncMock()
        scenario = _mock_scenario(SCENARIO_A_ID, ENGAGEMENT_ID)

        # 8 modifications: 3 bright, 3 dim, 2 dark
        mods = (
            [_mock_modification(f"bright-{i}", f"Bright Task {i}") for i in range(3)]
            + [_mock_modification(f"dim-{i}", f"Dim Task {i}") for i in range(3)]
            + [_mock_modification(f"dark-{i}", f"Dark Task {i}") for i in range(2)]
        )

        brightness_rows = (
            [(f"bright-{i}", BrightnessClassification.BRIGHT) for i in range(3)]
            + [(f"dim-{i}", BrightnessClassification.DIM) for i in range(3)]
            + [(f"dark-{i}", BrightnessClassification.DARK) for i in range(2)]
        )

        _setup_multi_execute(mock_session, scenario, mods, brightness_rows)

        service = EvidenceCoverageService(mock_session)
        result = await service.get_scenario_coverage(SCENARIO_A_ID, ENGAGEMENT_ID)

        assert len(result["modified_elements"]) == 8
        summary = result["coverage_summary"]
        assert summary["bright_count"] == 3
        assert summary["dim_count"] == 3
        assert summary["dark_count"] == 2

    @pytest.mark.asyncio
    async def test_only_modified_elements_returned(self) -> None:
        """Unmodified elements should not appear in the response."""
        mock_session = AsyncMock()
        scenario = _mock_scenario(SCENARIO_A_ID, ENGAGEMENT_ID)
        mods = [_mock_modification("elem-1", "Task 1")]

        _setup_multi_execute(
            mock_session,
            scenario,
            mods,
            [("elem-1", BrightnessClassification.BRIGHT)],
        )

        service = EvidenceCoverageService(mock_session)
        result = await service.get_scenario_coverage(SCENARIO_A_ID, ENGAGEMENT_ID)

        element_ids = [e["element_id"] for e in result["modified_elements"]]
        assert element_ids == ["elem-1"]

    @pytest.mark.asyncio
    async def test_empty_modifications_returns_empty(self) -> None:
        mock_session = AsyncMock()
        scenario = _mock_scenario(SCENARIO_A_ID, ENGAGEMENT_ID)

        # scenario found, but no modifications
        scenario_result = MagicMock()
        scenario_result.scalar_one_or_none.return_value = scenario

        mods_result = MagicMock()
        mods_scalars = MagicMock()
        mods_scalars.all.return_value = []
        mods_result.scalars.return_value = mods_scalars

        mock_session.execute = AsyncMock(side_effect=[scenario_result, mods_result])

        service = EvidenceCoverageService(mock_session)
        result = await service.get_scenario_coverage(SCENARIO_A_ID, ENGAGEMENT_ID)

        assert result["modified_elements"] == []
        assert result["coverage_summary"]["bright_count"] == 0
        assert result["coverage_summary"]["risk_score"] == 1.0

    @pytest.mark.asyncio
    async def test_unknown_element_defaults_to_dark(self) -> None:
        """Elements not found in ProcessElement should default to DARK."""
        mock_session = AsyncMock()
        scenario = _mock_scenario(SCENARIO_A_ID, ENGAGEMENT_ID)
        mods = [_mock_modification("unknown-elem", "Mystery Task")]

        # Brightness query returns empty — element not found
        _setup_multi_execute(mock_session, scenario, mods, [])

        service = EvidenceCoverageService(mock_session)
        result = await service.get_scenario_coverage(SCENARIO_A_ID, ENGAGEMENT_ID)

        elem = result["modified_elements"][0]
        assert elem["brightness"] == "dark"
        assert elem["warning"] is True


class TestComparativeRiskAssessment:
    """Scenario 3: Comparative Risk Assessment.

    Given Scenario A with 6 Bright modifications and 2 Dark modifications
      And Scenario B with 3 Bright modifications and 5 Dark modifications
    When evidence coverage is compared
    Then Scenario A is identified as lower risk
      And the comparison response includes a risk_score per scenario
    """

    @pytest.mark.asyncio
    async def test_scenario_a_lower_risk_than_b(self) -> None:
        mock_session = AsyncMock()

        # Scenario A: 6 bright, 2 dark -> risk = 6/8 = 0.75
        scenario_a = _mock_scenario(SCENARIO_A_ID, ENGAGEMENT_ID)
        mods_a = [_mock_modification(f"a-bright-{i}", f"A Bright {i}") for i in range(6)] + [
            _mock_modification(f"a-dark-{i}", f"A Dark {i}") for i in range(2)
        ]
        brightness_a = [(f"a-bright-{i}", BrightnessClassification.BRIGHT) for i in range(6)] + [
            (f"a-dark-{i}", BrightnessClassification.DARK) for i in range(2)
        ]

        # Scenario B: 3 bright, 5 dark -> risk = 3/8 = 0.375
        scenario_b = _mock_scenario(SCENARIO_B_ID, ENGAGEMENT_ID)
        mods_b = [_mock_modification(f"b-bright-{i}", f"B Bright {i}") for i in range(3)] + [
            _mock_modification(f"b-dark-{i}", f"B Dark {i}") for i in range(5)
        ]
        brightness_b = [(f"b-bright-{i}", BrightnessClassification.BRIGHT) for i in range(3)] + [
            (f"b-dark-{i}", BrightnessClassification.DARK) for i in range(5)
        ]

        # Set up mock for two get_scenario_coverage calls (6 execute calls total)
        scenario_a_result = MagicMock()
        scenario_a_result.scalar_one_or_none.return_value = scenario_a
        mods_a_result = MagicMock()
        mods_a_scalars = MagicMock()
        mods_a_scalars.all.return_value = mods_a
        mods_a_result.scalars.return_value = mods_a_scalars
        brightness_a_result = MagicMock()
        brightness_a_result.all.return_value = brightness_a

        scenario_b_result = MagicMock()
        scenario_b_result.scalar_one_or_none.return_value = scenario_b
        mods_b_result = MagicMock()
        mods_b_scalars = MagicMock()
        mods_b_scalars.all.return_value = mods_b
        mods_b_result.scalars.return_value = mods_b_scalars
        brightness_b_result = MagicMock()
        brightness_b_result.all.return_value = brightness_b

        mock_session.execute = AsyncMock(
            side_effect=[
                scenario_a_result,
                mods_a_result,
                brightness_a_result,
                scenario_b_result,
                mods_b_result,
                brightness_b_result,
            ]
        )

        service = EvidenceCoverageService(mock_session)
        results = await service.compare_scenarios([SCENARIO_A_ID, SCENARIO_B_ID], ENGAGEMENT_ID)

        assert len(results) == 2
        # Sorted by risk_score descending, so A (0.75) first, B (0.375) second
        assert results[0]["scenario_id"] == str(SCENARIO_A_ID)
        assert results[0]["coverage_summary"]["risk_score"] == 0.75
        assert results[1]["scenario_id"] == str(SCENARIO_B_ID)
        assert results[1]["coverage_summary"]["risk_score"] == 0.375


class TestRiskScoreComputation:
    """Unit tests for risk score edge cases."""

    def test_pure_bright_score_is_one(self) -> None:
        assert EvidenceCoverageService.compute_risk_score(10, 0) == 1.0

    def test_pure_dark_score_is_zero(self) -> None:
        assert EvidenceCoverageService.compute_risk_score(0, 5) == 0.0

    def test_mixed_proportional(self) -> None:
        # 3 bright, 1 dark -> 0.75
        assert EvidenceCoverageService.compute_risk_score(3, 1) == 0.75

    def test_no_bright_or_dark_returns_one(self) -> None:
        """When there are only dim elements, risk score should be 1.0."""
        assert EvidenceCoverageService.compute_risk_score(0, 0) == 1.0

    def test_equal_bright_and_dark(self) -> None:
        assert EvidenceCoverageService.compute_risk_score(4, 4) == 0.5


class TestScenarioNotFound:
    """Edge case: scenario does not exist."""

    @pytest.mark.asyncio
    async def test_nonexistent_scenario_raises(self) -> None:
        mock_session = AsyncMock()
        _setup_scenario_query(mock_session, None)

        service = EvidenceCoverageService(mock_session)
        with pytest.raises(ValueError, match="not found"):
            await service.get_scenario_coverage(SCENARIO_A_ID, ENGAGEMENT_ID)
