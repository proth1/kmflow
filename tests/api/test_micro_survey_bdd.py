"""BDD tests for Story #398: Telemetry-Triggered Micro-Survey Generation.

Tests anomaly-triggered survey generation, micro-survey size constraints,
and survey response ingestion with SurveyClaim linkage.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.services.micro_survey import (
    DEFAULT_ANOMALY_THRESHOLD,
    DEVIATION_PROBE_MAP,
    MicroSurveyService,
    _generate_probe_question,
)
from src.core.models import (
    MicroSurvey,
    MicroSurveyStatus,
    ProbeType,
    ProcessDeviation,
    SurveyClaim,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENGAGEMENT_ID = uuid.uuid4()


def _mock_deviation(
    *,
    severity_score: float = 3.0,
    category: str = "frequency",
    element_name: str = "Wire Transfer Review",
    description: str = "Anomalous frequency spike detected",
) -> MagicMock:
    """Create a mock ProcessDeviation."""
    d = MagicMock(spec=ProcessDeviation)
    d.id = uuid.uuid4()
    d.element_id = str(uuid.uuid4())
    d.element_name = element_name
    d.severity_score = severity_score
    d.category = category
    d.description = description
    return d


# ---------------------------------------------------------------------------
# BDD Scenario 1: Anomaly-Triggered Survey Generation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_1_anomaly_triggered_survey() -> None:
    """Given telemetry detects a deviation exceeding the threshold,
    When the anomaly is processed,
    Then a micro-survey is generated targeting the relevant SME."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    deviation = _mock_deviation(severity_score=3.0)
    service = MicroSurveyService(session)

    survey = await service.generate_micro_survey(
        engagement_id=ENGAGEMENT_ID,
        deviation=deviation,
        target_sme_role="process_owner",
    )

    assert survey is not None
    assert isinstance(survey, MicroSurvey)
    assert survey.engagement_id == ENGAGEMENT_ID
    assert survey.triggering_deviation_id == deviation.id
    assert survey.target_sme_role == "process_owner"
    assert survey.status == MicroSurveyStatus.GENERATED
    assert len(survey.probes) >= 2
    assert len(survey.probes) <= 3
    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_scenario_1_below_threshold_no_survey() -> None:
    """Given a deviation below the anomaly threshold,
    When the anomaly is processed,
    Then no micro-survey is generated."""
    session = AsyncMock()
    session.add = MagicMock()

    deviation = _mock_deviation(severity_score=1.5)  # Below default 2.0
    service = MicroSurveyService(session)

    survey = await service.generate_micro_survey(
        engagement_id=ENGAGEMENT_ID,
        deviation=deviation,
    )

    assert survey is None
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_scenario_1_at_threshold_no_survey() -> None:
    """Given a deviation exactly at the threshold boundary,
    When the anomaly is processed,
    Then no survey is generated (must exceed, not equal)."""
    session = AsyncMock()
    session.add = MagicMock()

    deviation = _mock_deviation(severity_score=DEFAULT_ANOMALY_THRESHOLD)
    service = MicroSurveyService(session)

    survey = await service.generate_micro_survey(
        engagement_id=ENGAGEMENT_ID,
        deviation=deviation,
    )

    assert survey is None
    session.add.assert_not_called()


# ---------------------------------------------------------------------------
# BDD Scenario 2: Micro-Survey Size Constraint
# ---------------------------------------------------------------------------


def test_scenario_2_probe_count_constraint() -> None:
    """Given a micro-survey is generated,
    When the probes are inspected,
    Then it contains exactly 2-3 focused probes."""
    session = AsyncMock()
    service = MicroSurveyService(session)

    for category in ["frequency", "timing", "performer", "volume", "default", "unknown_type"]:
        probes = service.select_probes(
            deviation_category=category,
            anomaly_description="Test anomaly",
        )
        assert 2 <= len(probes) <= 3, f"Category '{category}' produced {len(probes)} probes"
        for p in probes:
            assert "probe_type" in p
            assert "question" in p
            assert "Test anomaly" in p["question"]


def test_scenario_2_probes_reference_anomaly_context() -> None:
    """Each probe references the specific telemetry anomaly context."""
    session = AsyncMock()
    service = MicroSurveyService(session)

    probes = service.select_probes(
        deviation_category="frequency",
        anomaly_description="Frequency spike at 3x normal rate",
    )

    for probe in probes:
        assert "Frequency spike at 3x normal rate" in probe["question"]


# ---------------------------------------------------------------------------
# BDD Scenario 3: Survey Response Ingestion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_3_response_creates_survey_claims() -> None:
    """Given a micro-survey has been sent to an SME,
    When the SME submits a response,
    Then SurveyClaim entities are created linked to the micro-survey."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    survey_id = uuid.uuid4()
    mock_survey = MagicMock(spec=MicroSurvey)
    mock_survey.id = survey_id
    mock_survey.engagement_id = ENGAGEMENT_ID
    mock_survey.status = MicroSurveyStatus.SENT

    result = MagicMock()
    result.scalar_one_or_none.return_value = mock_survey
    session.execute = AsyncMock(return_value=result)

    service = MicroSurveyService(session)
    responses = [
        {
            "probe_type": ProbeType.EXISTENCE,
            "claim_text": "Yes, this activity still occurs as described",
            "certainty_tier": "known",
        },
        {
            "probe_type": ProbeType.SEQUENCE,
            "claim_text": "The order changed last month due to new policy",
            "certainty_tier": "suspected",
        },
    ]

    claims = await service.submit_response(
        survey_id=survey_id,
        responses=responses,
        respondent_role="process_owner",
    )

    assert len(claims) == 2
    assert claims[0]["probe_type"] == ProbeType.EXISTENCE
    assert claims[0]["micro_survey_id"] == str(survey_id)
    assert claims[1]["certainty_tier"] == "suspected"

    # Verify survey status updated to RESPONDED
    assert mock_survey.status == MicroSurveyStatus.RESPONDED
    assert mock_survey.responded_at is not None

    # Verify SurveyClaims added to session
    assert session.add.call_count == 2
    for call_args in session.add.call_args_list:
        added = call_args[0][0]
        assert isinstance(added, SurveyClaim)
        assert added.micro_survey_id == survey_id


@pytest.mark.asyncio
async def test_scenario_3_survey_not_found_raises() -> None:
    """Given a non-existent micro-survey ID,
    When response submission is attempted,
    Then a ValueError is raised."""
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)

    service = MicroSurveyService(session)

    with pytest.raises(ValueError, match="not found"):
        await service.submit_response(
            survey_id=uuid.uuid4(),
            responses=[],
            respondent_role="process_owner",
        )


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------


def test_deviation_probe_map_complete() -> None:
    """All deviation categories have probe mappings."""
    for category in ["frequency", "timing", "performer", "volume", "default"]:
        probes = DEVIATION_PROBE_MAP[category]
        assert len(probes) == 3, f"Category '{category}' should have 3 probes"
        for p in probes:
            assert isinstance(p, ProbeType)


def test_probe_question_generation() -> None:
    """Probe questions are generated for all probe types."""
    for pt in ProbeType:
        question = _generate_probe_question(pt, "Test anomaly")
        assert isinstance(question, str)
        assert len(question) > 0
        assert "Test anomaly" in question


def test_micro_survey_status_values() -> None:
    """MicroSurveyStatus has correct enum values."""
    assert MicroSurveyStatus.GENERATED == "generated"
    assert MicroSurveyStatus.SENT == "sent"
    assert MicroSurveyStatus.RESPONDED == "responded"
