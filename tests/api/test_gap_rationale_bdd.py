"""BDD tests for Story #352 — Gap Analysis with LLM-Powered Rationale Generation.

Scenario 1: LLM Rationale Generated for FULL_GAP
Scenario 2: Gap Prioritization by Composite Score
Scenario 3: Regulatory Gaps Weighted Higher in Prioritization
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest import mock
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import create_app
from src.core.auth import get_current_user
from src.core.models import (
    User,
    UserRole,
)
from src.tom.rationale_generator import (
    RationaleGeneratorService,
    build_rationale_prompt,
    compute_composite_score,
)

ENGAGEMENT_ID = uuid.uuid4()
TOM_ID = uuid.uuid4()
GAP_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _mock_user() -> User:
    u = MagicMock(spec=User)
    u.id = USER_ID
    u.role = UserRole.PLATFORM_ADMIN
    return u


def _make_plain_mock(**kwargs: Any) -> MagicMock:
    """Create a MagicMock that stores kwargs as regular attributes."""
    m = MagicMock()
    if "id" not in kwargs:
        m.id = uuid.uuid4()
    for k, v in kwargs.items():
        setattr(m, k, v)
    return m


def _make_gap_mock(
    *,
    gap_type: str = "full_gap",
    dimension: str = "process_architecture",
    severity: float = 0.8,
    confidence: float = 0.9,
    rationale: str | None = None,
    recommendation: str | None = None,
    business_criticality: int | None = None,
    risk_exposure: int | None = None,
    regulatory_impact: int | None = None,
    remediation_cost: int | None = None,
) -> MagicMock:
    """Create a mock GapAnalysisResult with composite_score property."""
    gap = _make_plain_mock(
        id=uuid.uuid4(),
        engagement_id=ENGAGEMENT_ID,
        tom_id=TOM_ID,
        gap_type=gap_type,
        dimension=dimension,
        severity=severity,
        confidence=confidence,
        rationale=rationale,
        recommendation=recommendation,
        business_criticality=business_criticality,
        risk_exposure=risk_exposure,
        regulatory_impact=regulatory_impact,
        remediation_cost=remediation_cost,
    )
    # Compute composite_score like the model property
    crit = business_criticality or 3
    risk = risk_exposure or 3
    reg = regulatory_impact or 3
    cost = remediation_cost or 1
    gap.composite_score = round((crit * risk * reg) / max(cost, 1), 4)
    gap.priority_score = round(severity * confidence, 4)
    gap.created_at = "2026-02-27T00:00:00+00:00"
    return gap


def _make_app_with_session(mock_session: AsyncMock) -> Any:
    """Create app with overridden dependencies."""
    from src.api.deps import get_session

    app = create_app()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    return app


# ---------------------------------------------------------------------------
# Unit tests for composite_score computation
# ---------------------------------------------------------------------------


class TestCompositeScore:
    """Tests for the composite score formula."""

    def test_basic_computation(self) -> None:
        """composite_score = (criticality × risk × regulatory) / cost."""
        score = compute_composite_score(
            business_criticality=4,
            risk_exposure=3,
            regulatory_impact=5,
            remediation_cost=2,
        )
        assert score == 30.0  # (4*3*5) / 2

    def test_high_regulatory_produces_higher_score(self) -> None:
        """Regulatory impact 5 produces higher score than 2 (all else equal)."""
        score_high = compute_composite_score(
            business_criticality=3,
            risk_exposure=3,
            regulatory_impact=5,
            remediation_cost=2,
        )
        score_low = compute_composite_score(
            business_criticality=3,
            risk_exposure=3,
            regulatory_impact=2,
            remediation_cost=2,
        )
        assert score_high > score_low

    def test_higher_cost_reduces_score(self) -> None:
        """Higher remediation cost reduces composite score."""
        score_low_cost = compute_composite_score(
            business_criticality=3,
            risk_exposure=3,
            regulatory_impact=3,
            remediation_cost=1,
        )
        score_high_cost = compute_composite_score(
            business_criticality=3,
            risk_exposure=3,
            regulatory_impact=3,
            remediation_cost=5,
        )
        assert score_low_cost > score_high_cost

    def test_cost_zero_treated_as_one(self) -> None:
        """Remediation cost of 0 uses max(cost, 1) to avoid division by zero."""
        score = compute_composite_score(
            business_criticality=3,
            risk_exposure=3,
            regulatory_impact=3,
            remediation_cost=0,
        )
        assert score == 27.0  # (3*3*3) / 1


class TestBuildRationalePrompt:
    """Tests for the prompt builder."""

    def test_prompt_contains_few_shot_examples(self) -> None:
        prompt = build_rationale_prompt(
            gap_type="full_gap",
            dimension="process_architecture",
            activity_description="Manual Exception Logging",
            tom_specification="Automated exception handling",
            severity=0.8,
            confidence=0.9,
        )
        assert "FULL_GAP" in prompt
        assert "Manual Exception Logging" in prompt
        assert "Automated exception handling" in prompt
        assert "Example" in prompt

    def test_prompt_wraps_user_input_in_xml(self) -> None:
        """Activity and TOM spec are wrapped in XML tags for injection prevention."""
        prompt = build_rationale_prompt(
            gap_type="partial_gap",
            dimension="technology_and_data",
            activity_description="Credit Risk Assessment",
            tom_specification="Automated credit scoring",
            severity=0.6,
            confidence=0.7,
        )
        assert "<activity>Credit Risk Assessment</activity>" in prompt
        assert "<tom_spec>Automated credit scoring</tom_spec>" in prompt


# ---------------------------------------------------------------------------
# Unit tests for RationaleGeneratorService
# ---------------------------------------------------------------------------


class TestRationaleGenerator:
    """Tests for the rationale generator service."""

    @pytest.mark.asyncio
    async def test_generate_rationale_with_llm(self) -> None:
        """Generates rationale via LLM call."""
        service = RationaleGeneratorService()

        gap = _make_gap_mock(gap_type="full_gap", dimension="process_architecture")

        with mock.patch.object(
            service,
            "_call_llm",
            new_callable=AsyncMock,
            return_value='{"rationale": "This is a full gap because...", "recommendation": "Implement automation"}',
        ):
            result = await service.generate_rationale(gap, "Automated exception handling")

        assert result["rationale"] == "This is a full gap because..."
        assert result["recommendation"] == "Implement automation"

    @pytest.mark.asyncio
    async def test_generate_rationale_fallback_on_error(self) -> None:
        """Falls back to template rationale when LLM fails."""
        service = RationaleGeneratorService()

        gap = _make_gap_mock(
            gap_type="partial_gap",
            dimension="technology_and_data",
            severity=0.6,
            confidence=0.7,
        )

        with mock.patch.object(
            service,
            "_call_llm",
            new_callable=AsyncMock,
            side_effect=RuntimeError("API error"),
        ):
            result = await service.generate_rationale(gap)

        assert "Partial Gap" in result["rationale"]
        assert "Technology And Data" in result["rationale"]
        assert result["recommendation"] != ""

    def test_parse_response_valid_json(self) -> None:
        """Parses valid JSON response."""
        service = RationaleGeneratorService()
        result = service._parse_response(
            '{"rationale": "Gap found", "recommendation": "Fix it"}'
        )
        assert result["rationale"] == "Gap found"
        assert result["recommendation"] == "Fix it"

    def test_parse_response_markdown_json(self) -> None:
        """Parses JSON wrapped in markdown code blocks."""
        service = RationaleGeneratorService()
        result = service._parse_response(
            '```json\n{"rationale": "Gap found", "recommendation": "Fix it"}\n```'
        )
        assert result["rationale"] == "Gap found"
        assert result["recommendation"] == "Fix it"

    def test_parse_response_invalid_json_fallback(self) -> None:
        """Falls back to raw text when JSON parsing fails."""
        service = RationaleGeneratorService()
        result = service._parse_response("This is a plain text rationale")
        assert result["rationale"] == "This is a plain text rationale"
        assert result["recommendation"] == ""


# ---------------------------------------------------------------------------
# API endpoint tests — Scenario 2: Gap Prioritization
# ---------------------------------------------------------------------------


class TestGapPrioritySorting:
    """Scenario 2: Gap Prioritization by Composite Score."""

    @pytest.mark.asyncio
    async def test_gaps_sorted_by_composite_score_desc(self) -> None:
        """When sort=priority, gaps are returned in descending composite_score order."""
        mock_session = AsyncMock()

        # Create 3 gaps with different composite scores
        gap_low = _make_gap_mock(
            business_criticality=1,
            risk_exposure=1,
            regulatory_impact=1,
            remediation_cost=5,
        )
        gap_mid = _make_gap_mock(
            business_criticality=3,
            risk_exposure=3,
            regulatory_impact=3,
            remediation_cost=2,
        )
        gap_high = _make_gap_mock(
            business_criticality=5,
            risk_exposure=5,
            regulatory_impact=5,
            remediation_cost=1,
        )

        # Return gaps in scrambled order
        count_result = MagicMock()
        count_result.scalar.return_value = 3

        gaps_result = MagicMock()
        gaps_result.scalars.return_value.all.return_value = [gap_mid, gap_low, gap_high]

        mock_session.execute = AsyncMock(side_effect=[count_result, gaps_result])

        app = _make_app_with_session(mock_session)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                f"/api/v1/tom/gaps?engagement_id={ENGAGEMENT_ID}&sort=priority",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3

        scores = [item["composite_score"] for item in data["items"]]
        assert scores == sorted(scores, reverse=True), "Gaps should be sorted by composite_score desc"

    @pytest.mark.asyncio
    async def test_gaps_without_sort_returns_default_order(self) -> None:
        """Without sort parameter, gaps are returned in database order."""
        mock_session = AsyncMock()

        gap1 = _make_gap_mock(business_criticality=1, risk_exposure=1, regulatory_impact=1, remediation_cost=1)
        gap2 = _make_gap_mock(business_criticality=5, risk_exposure=5, regulatory_impact=5, remediation_cost=1)

        count_result = MagicMock()
        count_result.scalar.return_value = 2

        gaps_result = MagicMock()
        gaps_result.scalars.return_value.all.return_value = [gap1, gap2]

        mock_session.execute = AsyncMock(side_effect=[count_result, gaps_result])

        app = _make_app_with_session(mock_session)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                f"/api/v1/tom/gaps?engagement_id={ENGAGEMENT_ID}",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2


# ---------------------------------------------------------------------------
# API endpoint tests — Scenario 3: Regulatory Gaps Weighted Higher
# ---------------------------------------------------------------------------


class TestRegulatoryGapWeighting:
    """Scenario 3: Regulatory Gaps Weighted Higher in Prioritization."""

    @pytest.mark.asyncio
    async def test_regulatory_gap_higher_composite_score(self) -> None:
        """Gap with regulatory_impact=5 has higher composite_score than regulatory_impact=2."""
        mock_session = AsyncMock()

        # Same business_criticality and risk_exposure, different regulatory_impact
        gap_a = _make_gap_mock(
            business_criticality=4,
            risk_exposure=4,
            regulatory_impact=5,
            remediation_cost=2,
        )
        gap_b = _make_gap_mock(
            business_criticality=4,
            risk_exposure=4,
            regulatory_impact=2,
            remediation_cost=2,
        )

        count_result = MagicMock()
        count_result.scalar.return_value = 2

        gaps_result = MagicMock()
        gaps_result.scalars.return_value.all.return_value = [gap_b, gap_a]  # B first (wrong order)

        mock_session.execute = AsyncMock(side_effect=[count_result, gaps_result])

        app = _make_app_with_session(mock_session)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                f"/api/v1/tom/gaps?engagement_id={ENGAGEMENT_ID}&sort=priority",
            )

        assert resp.status_code == 200
        data = resp.json()
        items = data["items"]
        assert len(items) == 2
        # Gap A (regulatory_impact=5) should come first
        assert items[0]["composite_score"] > items[1]["composite_score"]

    def test_composite_score_regulatory_weighting_unit(self) -> None:
        """Unit test: identical criticality/risk, higher regulatory → higher score."""
        score_reg5 = compute_composite_score(
            business_criticality=4,
            risk_exposure=4,
            regulatory_impact=5,
            remediation_cost=2,
        )
        score_reg2 = compute_composite_score(
            business_criticality=4,
            risk_exposure=4,
            regulatory_impact=2,
            remediation_cost=2,
        )
        assert score_reg5 > score_reg2
        # Gap A: (4*4*5)/2 = 40, Gap B: (4*4*2)/2 = 16
        assert score_reg5 == 40.0
        assert score_reg2 == 16.0


# ---------------------------------------------------------------------------
# API endpoint tests — Scenario 1: Rationale Generation
# ---------------------------------------------------------------------------


class TestRationaleGeneration:
    """Scenario 1: LLM Rationale Generated for FULL_GAP."""

    @pytest.mark.asyncio
    async def test_generate_rationale_for_gap(self) -> None:
        """POST /gaps/{gap_id}/generate-rationale generates and stores rationale."""
        mock_session = AsyncMock()

        gap = _make_gap_mock(
            gap_type="full_gap",
            dimension="process_architecture",
            rationale=None,
        )
        gap.id = GAP_ID

        # First: gap lookup
        gap_result = MagicMock()
        gap_result.scalar_one_or_none.return_value = gap

        # Second: TOM lookup
        tom = _make_plain_mock(id=TOM_ID)
        dim_rec = _make_plain_mock(
            dimension_type="process_architecture",
            description="Automated exception handling with alerting",
        )
        tom.dimension_records = [dim_rec]
        tom_result = MagicMock()
        tom_result.scalar_one_or_none.return_value = tom

        mock_session.execute = AsyncMock(side_effect=[gap_result, tom_result])
        mock_session.commit = AsyncMock()

        app = _make_app_with_session(mock_session)

        with mock.patch(
            "src.tom.rationale_generator.RationaleGeneratorService"
        ) as mock_service_cls:
            instance = mock_service_cls.return_value
            instance.generate_rationale = AsyncMock(
                return_value={
                    "rationale": "Manual exception logging creates a full gap.",
                    "recommendation": "Implement automated exception handling.",
                }
            )

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    f"/api/v1/tom/gaps/{GAP_ID}/generate-rationale",
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["gap_id"] == str(GAP_ID)
        assert "full gap" in data["rationale"]
        assert "automated" in data["recommendation"].lower()

    @pytest.mark.asyncio
    async def test_generate_rationale_404_gap_not_found(self) -> None:
        """Returns 404 when gap does not exist."""
        mock_session = AsyncMock()

        gap_result = MagicMock()
        gap_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=gap_result)

        app = _make_app_with_session(mock_session)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                f"/api/v1/tom/gaps/{uuid.uuid4()}/generate-rationale",
            )

        assert resp.status_code == 404


class TestBulkRationaleGeneration:
    """Tests for bulk rationale generation endpoint."""

    @pytest.mark.asyncio
    async def test_bulk_generate_rationales(self) -> None:
        """POST /gaps/engagement/{id}/generate-rationales processes all gaps."""
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        app = _make_app_with_session(mock_session)

        with mock.patch(
            "src.tom.rationale_generator.RationaleGeneratorService"
        ) as mock_service_cls:
            instance = mock_service_cls.return_value
            instance.generate_bulk_rationales = AsyncMock(
                return_value=[
                    {
                        "gap_id": str(uuid.uuid4()),
                        "rationale": "Gap 1 rationale",
                        "recommendation": "Fix gap 1",
                    },
                    {
                        "gap_id": str(uuid.uuid4()),
                        "rationale": "Gap 2 rationale",
                        "recommendation": "Fix gap 2",
                    },
                ]
            )

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    f"/api/v1/tom/gaps/engagement/{ENGAGEMENT_ID}/generate-rationales",
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["engagement_id"] == str(ENGAGEMENT_ID)
        assert data["gaps_processed"] == 2
        assert len(data["results"]) == 2
