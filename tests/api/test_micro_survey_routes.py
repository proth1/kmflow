"""Route-level tests for micro-survey API endpoints (Story #398)."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.deps import get_session
from src.api.main import create_app
from src.core.models import MicroSurvey, MicroSurveyStatus, ProbeType, User, UserRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENGAGEMENT_ID = uuid.uuid4()
DEVIATION_ID = uuid.uuid4()


def _mock_user() -> MagicMock:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.role = UserRole.PLATFORM_ADMIN
    return user


def _make_app(mock_session: AsyncMock) -> Any:
    from src.api.routes.auth import get_current_user

    app = create_app()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    app.state.neo4j_driver = MagicMock()
    return app


def _mock_deviation() -> MagicMock:
    from src.core.models import ProcessDeviation

    d = MagicMock(spec=ProcessDeviation)
    d.id = DEVIATION_ID
    d.engagement_id = ENGAGEMENT_ID
    d.element_id = str(uuid.uuid4())
    d.element_name = "Wire Transfer Review"
    d.severity_score = 3.0
    d.category = "frequency"
    d.description = "Anomalous frequency spike detected"
    return d


def _mock_survey() -> MagicMock:
    s = MagicMock(spec=MicroSurvey)
    s.id = uuid.uuid4()
    s.engagement_id = ENGAGEMENT_ID
    s.triggering_deviation_id = DEVIATION_ID
    s.target_element_id = str(uuid.uuid4())
    s.target_element_name = "Wire Transfer Review"
    s.target_sme_role = "process_owner"
    s.anomaly_description = "Anomalous frequency spike detected"
    s.probes = [
        {"probe_type": "existence", "question": "Does this activity occur?"},
        {"probe_type": "sequence", "question": "Has the order changed?"},
    ]
    s.status = MicroSurveyStatus.GENERATED
    return s


# ---------------------------------------------------------------------------
# POST /api/v1/micro-surveys — Generate micro-survey
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_micro_survey_success() -> None:
    """POST returns 201 with generated micro-survey."""
    session = AsyncMock()
    deviation_result = MagicMock()
    deviation_result.scalar_one_or_none.return_value = _mock_deviation()
    session.execute = AsyncMock(return_value=deviation_result)
    session.flush = AsyncMock()
    session.add = MagicMock()

    app = _make_app(session)
    survey = _mock_survey()

    with patch(
        "src.api.services.micro_survey.MicroSurveyService.generate_micro_survey",
        new_callable=AsyncMock,
        return_value=survey,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/micro-surveys",
                json={
                    "engagement_id": str(ENGAGEMENT_ID),
                    "deviation_id": str(DEVIATION_ID),
                    "target_sme_role": "process_owner",
                },
            )

    assert resp.status_code == 201
    data = resp.json()
    assert data["target_sme_role"] == "process_owner"
    assert data["status"] == "generated"


@pytest.mark.asyncio
async def test_generate_micro_survey_deviation_not_found() -> None:
    """POST returns 404 when deviation does not exist."""
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)

    app = _make_app(session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/micro-surveys",
            json={
                "engagement_id": str(ENGAGEMENT_ID),
                "deviation_id": str(DEVIATION_ID),
            },
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_generate_micro_survey_below_threshold() -> None:
    """POST returns 422 when deviation is below threshold."""
    session = AsyncMock()
    deviation_result = MagicMock()
    deviation_result.scalar_one_or_none.return_value = _mock_deviation()
    session.execute = AsyncMock(return_value=deviation_result)

    app = _make_app(session)

    with patch(
        "src.api.services.micro_survey.MicroSurveyService.generate_micro_survey",
        new_callable=AsyncMock,
        return_value=None,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/micro-surveys",
                json={
                    "engagement_id": str(ENGAGEMENT_ID),
                    "deviation_id": str(DEVIATION_ID),
                },
            )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/v1/micro-surveys/{survey_id}/respond — Submit response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_response_success() -> None:
    """POST respond returns claims and RESPONDED status."""
    session = AsyncMock()
    app = _make_app(session)
    survey_id = uuid.uuid4()

    claims = [
        {
            "probe_type": ProbeType.EXISTENCE,
            "claim_text": "Yes, this still occurs",
            "certainty_tier": "known",
            "micro_survey_id": str(survey_id),
        },
    ]

    with patch(
        "src.api.services.micro_survey.MicroSurveyService.submit_response",
        new_callable=AsyncMock,
        return_value=claims,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/micro-surveys/{survey_id}/respond",
                json={
                    "responses": [
                        {
                            "probe_type": "existence",
                            "claim_text": "Yes, this still occurs",
                            "certainty_tier": "known",
                        },
                    ],
                    "respondent_role": "process_owner",
                },
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["survey_status"] == "responded"
    assert len(data["claims"]) == 1


@pytest.mark.asyncio
async def test_submit_response_survey_not_found() -> None:
    """POST respond returns 404 when survey does not exist."""
    session = AsyncMock()
    app = _make_app(session)
    survey_id = uuid.uuid4()

    with patch(
        "src.api.services.micro_survey.MicroSurveyService.submit_response",
        new_callable=AsyncMock,
        side_effect=ValueError(f"Micro-survey {survey_id} not found"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/micro-surveys/{survey_id}/respond",
                json={
                    "responses": [],
                    "respondent_role": "process_owner",
                },
            )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/micro-surveys — List micro-surveys
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_micro_surveys_success() -> None:
    """GET returns list of micro-surveys for an engagement."""
    session = AsyncMock()
    app = _make_app(session)

    survey = _mock_survey()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [survey]
    session.execute = AsyncMock(return_value=result)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/micro-surveys",
            params={"engagement_id": str(ENGAGEMENT_ID)},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["target_sme_role"] == "process_owner"
