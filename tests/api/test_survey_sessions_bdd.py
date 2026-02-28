"""BDD tests for Survey Bot / Session management (Story #319)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models.survey import CertaintyTier, ProbeType, SurveyClaim
from src.core.models.survey_session import SurveySession, SurveySessionStatus
from src.core.services.survey_bot_service import (
    PROBE_ORDER,
    PROBE_TEMPLATES,
    SurveyBotService,
)

ENGAGEMENT_ID = uuid.uuid4()
SESSION_ID = uuid.uuid4()


# ── Probe Generation ─────────────────────────────────────────────────


class TestProbeGeneration:
    """Scenario 1 & 3: Probes generated from seed terms."""

    def test_generates_all_8_probe_types(self) -> None:
        service = SurveyBotService(AsyncMock())
        terms = [
            {"id": str(uuid.uuid4()), "term": "KYC Review", "domain": "compliance", "category": "activity"},
        ]

        probes = service.generate_probes_for_terms(terms, session_id=SESSION_ID)

        assert len(probes) == 8
        probe_types = {p["probe_type"] for p in probes}
        assert probe_types == {pt.value for pt in ProbeType}

    def test_existence_probe_text(self) -> None:
        service = SurveyBotService(AsyncMock())
        terms = [{"id": str(uuid.uuid4()), "term": "KYC Review", "domain": "compliance", "category": "activity"}]

        probes = service.generate_probes_for_terms(terms, session_id=SESSION_ID, probe_types=[ProbeType.EXISTENCE])

        assert len(probes) == 1
        assert probes[0]["question"] == "Does 'KYC Review' happen in your area?"
        assert "exists" in probes[0]["expected_response"]

    def test_probes_ordered_by_fatigue_minimization(self) -> None:
        service = SurveyBotService(AsyncMock())
        terms = [{"id": str(uuid.uuid4()), "term": "Test", "domain": "general", "category": "activity"}]

        probes = service.generate_probes_for_terms(terms, session_id=SESSION_ID)

        actual_order = [p["probe_type"] for p in probes]
        expected_order = [pt.value for pt in PROBE_ORDER]
        assert actual_order == expected_order

    def test_probes_for_multiple_terms(self) -> None:
        service = SurveyBotService(AsyncMock())
        terms = [
            {"id": str(uuid.uuid4()), "term": "KYC Review", "domain": "compliance", "category": "activity"},
            {"id": str(uuid.uuid4()), "term": "Loan Approval", "domain": "lending", "category": "activity"},
        ]

        probes = service.generate_probes_for_terms(terms, session_id=SESSION_ID)

        # 8 probe types * 2 terms = 16 probes
        assert len(probes) == 16

    def test_all_8_template_keys_exist(self) -> None:
        assert len(PROBE_TEMPLATES) == 8
        for pt in ProbeType:
            assert pt in PROBE_TEMPLATES


# ── Session Lifecycle ─────────────────────────────────────────────────


class TestSessionLifecycle:
    """Scenario 5: Session creation, completion, and summary."""

    @pytest.mark.asyncio
    async def test_creates_session(self) -> None:
        session = AsyncMock()
        service = SurveyBotService(session)

        result = await service.create_session(
            engagement_id=ENGAGEMENT_ID,
            respondent_role="operations_team",
        )

        assert result["status"] == "active"
        assert result["respondent_role"] == "operations_team"
        session.add.assert_called_once()
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_completes_session_with_summary(self) -> None:
        session = AsyncMock()

        session_obj = MagicMock(spec=SurveySession)
        session_obj.id = SESSION_ID
        session_obj.engagement_id = ENGAGEMENT_ID
        session_obj.status = SurveySessionStatus.ACTIVE

        claim1 = MagicMock(spec=SurveyClaim)
        claim1.probe_type = ProbeType.EXISTENCE
        claim1.certainty_tier = CertaintyTier.KNOWN

        claim2 = MagicMock(spec=SurveyClaim)
        claim2.probe_type = ProbeType.SEQUENCE
        claim2.certainty_tier = CertaintyTier.SUSPECTED

        claim3 = MagicMock(spec=SurveyClaim)
        claim3.probe_type = ProbeType.EXISTENCE
        claim3.certainty_tier = CertaintyTier.CONTRADICTED

        # First execute: get_session, second: get claims
        session_result = MagicMock()
        session_result.scalar_one_or_none.return_value = session_obj

        claims_result = MagicMock()
        claims_scalars = MagicMock()
        claims_scalars.all.return_value = [claim1, claim2, claim3]
        claims_result.scalars.return_value = claims_scalars

        session.execute = AsyncMock(side_effect=[session_result, claims_result])

        service = SurveyBotService(session)
        result = await service.complete_session(SESSION_ID)

        assert result["status"] == "completed"
        assert result["claims_count"] == 3
        summary = result["summary"]
        assert summary["total_claims"] == 3
        assert summary["by_probe_type"]["existence"] == 2
        assert summary["by_probe_type"]["sequence"] == 1
        assert summary["by_certainty_tier"]["known"] == 1
        assert summary["by_certainty_tier"]["suspected"] == 1
        assert summary["by_certainty_tier"]["contradicted"] == 1
        assert summary["contradicted_count"] == 1

    @pytest.mark.asyncio
    async def test_complete_returns_error_for_non_active(self) -> None:
        session = AsyncMock()

        session_obj = MagicMock(spec=SurveySession)
        session_obj.id = SESSION_ID
        session_obj.status = SurveySessionStatus.COMPLETED

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = session_obj
        session.execute = AsyncMock(return_value=result_mock)

        service = SurveyBotService(session)
        result = await service.complete_session(SESSION_ID)

        assert result["error"] == "invalid_status"
        assert result["current_status"] == "completed"

    @pytest.mark.asyncio
    async def test_complete_returns_error_for_missing(self) -> None:
        session = AsyncMock()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        service = SurveyBotService(session)
        result = await service.complete_session(uuid.uuid4())

        assert result["error"] == "not_found"


# ── Claim Creation ────────────────────────────────────────────────────


class TestClaimCreation:
    """Scenario 2: SurveyClaim creation from SME response."""

    @pytest.mark.asyncio
    async def test_creates_claim_with_correct_fields(self) -> None:
        session = AsyncMock()
        service = SurveyBotService(session)

        result = await service.create_claim(
            engagement_id=ENGAGEMENT_ID,
            session_id=SESSION_ID,
            probe_type=ProbeType.SEQUENCE,
            respondent_role="operations_team",
            claim_text="Credit assessment happens after KYC review",
            certainty_tier=CertaintyTier.SUSPECTED,
            proof_expectation="Process flow diagram",
            related_seed_terms=["KYC Review", "Credit Assessment"],
        )

        assert result["probe_type"] == "sequence"
        assert result["certainty_tier"] == "suspected"
        assert result["requires_conflict_check"] is False
        session.add.assert_called_once()
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_contradicted_claim_flags_conflict_check(self) -> None:
        session = AsyncMock()
        service = SurveyBotService(session)

        result = await service.create_claim(
            engagement_id=ENGAGEMENT_ID,
            session_id=SESSION_ID,
            probe_type=ProbeType.EXISTENCE,
            respondent_role="operations_team",
            claim_text="KYC review does NOT happen in our area",
            certainty_tier=CertaintyTier.CONTRADICTED,
        )

        assert result["requires_conflict_check"] is True


# ── Session Summary ───────────────────────────────────────────────────


class TestSessionSummary:
    """Session summary generation."""

    def test_builds_summary_from_claims(self) -> None:
        claims = []
        for pt in [ProbeType.EXISTENCE, ProbeType.EXISTENCE, ProbeType.SEQUENCE]:
            claim = MagicMock(spec=SurveyClaim)
            claim.probe_type = pt
            claim.certainty_tier = CertaintyTier.KNOWN
            claims.append(claim)

        summary = SurveyBotService._build_session_summary(claims)

        assert summary["total_claims"] == 3
        assert summary["by_probe_type"]["existence"] == 2
        assert summary["by_probe_type"]["sequence"] == 1
        assert summary["probe_type_coverage"] == 2
        assert summary["contradicted_count"] == 0

    def test_empty_summary(self) -> None:
        summary = SurveyBotService._build_session_summary([])
        assert summary["total_claims"] == 0
        assert summary["by_probe_type"] == {}
        assert summary["contradicted_count"] == 0


# ── List Sessions ─────────────────────────────────────────────────────


class TestListSessions:
    @pytest.mark.asyncio
    async def test_lists_sessions_with_pagination(self) -> None:
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 1

        s = MagicMock(spec=SurveySession)
        s.id = SESSION_ID
        s.engagement_id = ENGAGEMENT_ID
        s.respondent_role = "operations_team"
        s.status = SurveySessionStatus.ACTIVE
        s.claims_count = 5
        s.created_at = datetime(2026, 2, 27, tzinfo=UTC)
        s.completed_at = None

        list_result = MagicMock()
        list_scalars = MagicMock()
        list_scalars.all.return_value = [s]
        list_result.scalars.return_value = list_scalars

        session.execute = AsyncMock(side_effect=[count_result, list_result])

        service = SurveyBotService(session)
        result = await service.list_sessions(ENGAGEMENT_ID)

        assert result["total_count"] == 1
        assert result["items"][0]["respondent_role"] == "operations_team"
