"""BDD tests for Seed List Pipeline (Story #321).

Covers the 4-stage pipeline: vocabulary upload, NLP refinement,
probe generation, and extraction targeting.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models.seed_term import SeedTerm, TermCategory, TermSource, TermStatus
from src.core.services.seed_list_service import SeedListService, _normalize_term

ENGAGEMENT_ID = uuid.uuid4()


# ── Normalization ─────────────────────────────────────────────────────


class TestTermNormalization:
    """Deduplication normalization strips punctuation, lowercases."""

    def test_strips_punctuation(self) -> None:
        assert _normalize_term("KYC/AML Review") == "kycaml review"

    def test_lowercases(self) -> None:
        assert _normalize_term("Client Onboarding") == "client onboarding"

    def test_strips_whitespace(self) -> None:
        assert _normalize_term("  loan approval  ") == "loan approval"

    def test_handles_special_chars(self) -> None:
        assert _normalize_term("P&L (Statement)") == "pl statement"


# ── Stage 1: Consultant Vocabulary Upload ─────────────────────────────


class TestConsultantVocabularyUpload:
    """Scenario 1: Consultant-provided seed term creation."""

    @pytest.mark.asyncio
    async def test_creates_seed_terms_with_dedup(self) -> None:
        session = AsyncMock()

        # Existing terms query returns empty
        existing_result = MagicMock()
        existing_scalars = MagicMock()
        existing_scalars.all.return_value = []
        existing_result.scalars.return_value = existing_scalars
        session.execute = AsyncMock(return_value=existing_result)

        service = SeedListService(session)
        result = await service.create_seed_terms(
            engagement_id=ENGAGEMENT_ID,
            terms=[
                {"term": "KYC Review", "domain": "compliance", "category": "activity"},
                {"term": "Loan Approval", "domain": "lending", "category": "activity"},
            ],
            source=TermSource.CONSULTANT_PROVIDED,
        )

        assert result["created_count"] == 2
        assert result["skipped_count"] == 0
        assert "KYC Review" in result["created_terms"]
        assert "Loan Approval" in result["created_terms"]
        assert session.add.call_count == 2
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_duplicate_terms(self) -> None:
        session = AsyncMock()

        # Existing terms include "kyc review" (already stored)
        existing_result = MagicMock()
        existing_scalars = MagicMock()
        existing_scalars.all.return_value = ["KYC Review"]
        existing_result.scalars.return_value = existing_scalars
        session.execute = AsyncMock(return_value=existing_result)

        service = SeedListService(session)
        result = await service.create_seed_terms(
            engagement_id=ENGAGEMENT_ID,
            terms=[
                {"term": "kyc review", "domain": "compliance", "category": "activity"},
                {"term": "New Term", "domain": "general", "category": "activity"},
            ],
        )

        assert result["created_count"] == 1
        assert result["skipped_count"] == 1
        assert "kyc review" in result["skipped_terms"]
        assert "New Term" in result["created_terms"]

    @pytest.mark.asyncio
    async def test_no_flush_when_nothing_created(self) -> None:
        session = AsyncMock()

        existing_result = MagicMock()
        existing_scalars = MagicMock()
        existing_scalars.all.return_value = ["Existing Term"]
        existing_result.scalars.return_value = existing_scalars
        session.execute = AsyncMock(return_value=existing_result)

        service = SeedListService(session)
        result = await service.create_seed_terms(
            engagement_id=ENGAGEMENT_ID,
            terms=[{"term": "Existing Term", "domain": "general", "category": "activity"}],
        )

        assert result["created_count"] == 0
        assert result["skipped_count"] == 1
        session.flush.assert_not_awaited()


# ── Stage 2: NLP Refinement ──────────────────────────────────────────


class TestNLPRefinement:
    """Scenario 2: NLP-driven term discovery."""

    @pytest.mark.asyncio
    async def test_adds_discovered_terms_with_nlp_source(self) -> None:
        session = AsyncMock()

        existing_result = MagicMock()
        existing_scalars = MagicMock()
        existing_scalars.all.return_value = []
        existing_result.scalars.return_value = existing_scalars
        session.execute = AsyncMock(return_value=existing_result)

        service = SeedListService(session)
        result = await service.add_discovered_terms(
            engagement_id=ENGAGEMENT_ID,
            discovered=[
                {"term": "Risk Assessment", "domain": "compliance", "category": "activity"},
                {"term": "Document Verification", "domain": "operations", "category": "activity"},
            ],
        )

        assert result["created_count"] == 2
        # Verify source is NLP_DISCOVERED by checking session.add calls
        added_terms = [call.args[0] for call in session.add.call_args_list]
        for term in added_terms:
            assert term.source == TermSource.NLP_DISCOVERED

    @pytest.mark.asyncio
    async def test_deduplicates_against_existing_terms(self) -> None:
        session = AsyncMock()

        existing_result = MagicMock()
        existing_scalars = MagicMock()
        existing_scalars.all.return_value = ["Risk Assessment"]
        existing_result.scalars.return_value = existing_scalars
        session.execute = AsyncMock(return_value=existing_result)

        service = SeedListService(session)
        result = await service.add_discovered_terms(
            engagement_id=ENGAGEMENT_ID,
            discovered=[
                {"term": "risk assessment", "domain": "compliance", "category": "activity"},
                {"term": "New Discovery", "domain": "general", "category": "system"},
            ],
        )

        assert result["created_count"] == 1
        assert result["skipped_count"] == 1


# ── Stage 3: Probe Generation ───────────────────────────────────────


class TestProbeGeneration:
    """Scenario 3: Probe generation from seed terms."""

    @pytest.mark.asyncio
    async def test_generates_four_probes_per_term(self) -> None:
        session = AsyncMock()

        term = MagicMock(spec=SeedTerm)
        term.id = uuid.uuid4()
        term.term = "KYC Review"
        term.engagement_id = ENGAGEMENT_ID

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [term]
        result_mock.scalars.return_value = scalars_mock
        session.execute = AsyncMock(return_value=result_mock)

        service = SeedListService(session)
        result = await service.generate_probes(ENGAGEMENT_ID)

        assert result["terms_processed"] == 1
        assert result["probes_generated"] == 4

        probe_types = {p["probe_type"] for p in result["probes"]}
        assert probe_types == {"existence", "sequence", "dependency", "governance"}

        for probe in result["probes"]:
            assert probe["seed_term_id"] == str(term.id)
            assert "KYC Review" in probe["question"]

    @pytest.mark.asyncio
    async def test_generates_probes_for_specific_term(self) -> None:
        session = AsyncMock()
        term_id = uuid.uuid4()

        term = MagicMock(spec=SeedTerm)
        term.id = term_id
        term.term = "Loan Approval"

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [term]
        result_mock.scalars.return_value = scalars_mock
        session.execute = AsyncMock(return_value=result_mock)

        service = SeedListService(session)
        result = await service.generate_probes(ENGAGEMENT_ID, seed_term_id=term_id)

        assert result["probes_generated"] == 4
        assert all("Loan Approval" in p["question"] for p in result["probes"])

    @pytest.mark.asyncio
    async def test_no_probes_when_no_active_terms(self) -> None:
        session = AsyncMock()

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        session.execute = AsyncMock(return_value=result_mock)

        service = SeedListService(session)
        result = await service.generate_probes(ENGAGEMENT_ID)

        assert result["terms_processed"] == 0
        assert result["probes_generated"] == 0
        assert result["probes"] == []


# ── Stage 4: Extraction Targeting ────────────────────────────────────


class TestExtractionTargeting:
    """Scenario 4: Extraction targeting returns active terms."""

    @pytest.mark.asyncio
    async def test_returns_active_terms_for_targeting(self) -> None:
        session = AsyncMock()

        term1 = MagicMock(spec=SeedTerm)
        term1.id = uuid.uuid4()
        term1.term = "KYC Review"
        term1.domain = "compliance"
        term1.category = TermCategory.ACTIVITY

        term2 = MagicMock(spec=SeedTerm)
        term2.id = uuid.uuid4()
        term2.term = "Loan Origination"
        term2.domain = "lending"
        term2.category = TermCategory.ACTIVITY

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [term1, term2]
        result_mock.scalars.return_value = scalars_mock
        session.execute = AsyncMock(return_value=result_mock)

        service = SeedListService(session)
        result = await service.get_extraction_targets(ENGAGEMENT_ID)

        assert result["active_term_count"] == 2
        assert len(result["terms"]) == 2
        assert result["terms"][0]["term"] == "KYC Review"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_active_terms(self) -> None:
        session = AsyncMock()

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        session.execute = AsyncMock(return_value=result_mock)

        service = SeedListService(session)
        result = await service.get_extraction_targets(ENGAGEMENT_ID)

        assert result["active_term_count"] == 0
        assert result["terms"] == []


# ── Term Management ──────────────────────────────────────────────────


class TestTermDeprecation:
    """Soft delete (deprecation) of seed terms."""

    @pytest.mark.asyncio
    async def test_deprecates_existing_term(self) -> None:
        session = AsyncMock()

        term = MagicMock(spec=SeedTerm)
        term.id = uuid.uuid4()
        term.term = "Old Term"
        term.status = TermStatus.ACTIVE

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = term
        session.execute = AsyncMock(return_value=result_mock)

        service = SeedListService(session)
        result = await service.deprecate_term(term.id)

        assert result["status"] == "deprecated"
        assert term.status == TermStatus.DEPRECATED
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_not_found_for_missing_term(self) -> None:
        session = AsyncMock()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        service = SeedListService(session)
        result = await service.deprecate_term(uuid.uuid4())

        assert result["error"] == "not_found"


# ── Get Seed List ────────────────────────────────────────────────────


class TestGetSeedList:
    """Paginated, filtered seed list retrieval."""

    @pytest.mark.asyncio
    async def test_returns_paginated_list(self) -> None:
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 2

        term = MagicMock(spec=SeedTerm)
        term.id = uuid.uuid4()
        term.engagement_id = ENGAGEMENT_ID
        term.term = "KYC Review"
        term.domain = "compliance"
        term.category = TermCategory.ACTIVITY
        term.source = TermSource.CONSULTANT_PROVIDED
        term.status = TermStatus.ACTIVE
        term.created_at = datetime(2026, 2, 27, tzinfo=UTC)

        list_result = MagicMock()
        list_scalars = MagicMock()
        list_scalars.all.return_value = [term]
        list_result.scalars.return_value = list_scalars

        session.execute = AsyncMock(side_effect=[count_result, list_result])

        service = SeedListService(session)
        result = await service.get_seed_list(ENGAGEMENT_ID, limit=10, offset=0)

        assert result["total_count"] == 2
        assert len(result["items"]) == 1
        assert result["items"][0]["term"] == "KYC Review"
        assert result["limit"] == 10
        assert result["offset"] == 0
