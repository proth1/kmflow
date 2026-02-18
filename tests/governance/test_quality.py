"""Tests for the SLA quality checker.

Verifies that check_quality_sla correctly compares evidence quality
scores against catalog entry SLA thresholds and produces the right
violations.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models import DataCatalogEntry, DataClassification, DataLayer
from src.governance.quality import SLAResult, SLAViolation, check_quality_sla

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_catalog_entry(
    quality_sla: dict | None = None,
    engagement_id: uuid.UUID | None = None,
) -> MagicMock:
    """Build a mock DataCatalogEntry."""
    entry = MagicMock(spec=DataCatalogEntry)
    entry.id = uuid.uuid4()
    entry.dataset_name = "test_dataset"
    entry.layer = DataLayer.GOLD
    entry.classification = DataClassification.CONFIDENTIAL
    entry.quality_sla = quality_sla
    entry.engagement_id = engagement_id
    return entry


def _make_evidence_item(quality_score: float | None = None) -> MagicMock:
    """Build a mock EvidenceItem with an optional quality_score."""
    item = MagicMock()
    item.id = uuid.uuid4()
    item.quality_score = quality_score
    return item


def _make_session(items: list) -> AsyncMock:
    """Build a mock AsyncSession that returns *items* from execute."""
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    session.execute = AsyncMock(return_value=result)
    return session


# ---------------------------------------------------------------------------
# No-SLA scenarios
# ---------------------------------------------------------------------------


class TestNoSLADefined:
    """When quality_sla is None or empty, the check trivially passes."""

    @pytest.mark.asyncio
    async def test_passes_when_no_sla_defined(self) -> None:
        entry = _make_catalog_entry(quality_sla=None)
        session = _make_session(items=[])

        result = await check_quality_sla(session, entry)

        assert result.passing is True
        assert result.violations == []
        assert result.evidence_count == 0

    @pytest.mark.asyncio
    async def test_passes_when_sla_is_empty_dict(self) -> None:
        entry = _make_catalog_entry(quality_sla={})
        session = _make_session(items=[])

        result = await check_quality_sla(session, entry)

        assert result.passing is True


# ---------------------------------------------------------------------------
# No evidence items
# ---------------------------------------------------------------------------


class TestNoEvidenceItems:
    """When there are no evidence items, the check trivially passes."""

    @pytest.mark.asyncio
    async def test_passes_with_no_evidence_items(self) -> None:
        entry = _make_catalog_entry(quality_sla={"min_score": 0.8})
        session = _make_session(items=[])

        result = await check_quality_sla(session, entry)

        assert result.passing is True
        assert result.evidence_count == 0


# ---------------------------------------------------------------------------
# min_score violations
# ---------------------------------------------------------------------------


class TestMinScore:
    """Tests for the min_score SLA threshold."""

    @pytest.mark.asyncio
    async def test_passes_when_average_above_threshold(self) -> None:
        items = [
            _make_evidence_item(quality_score=0.9),
            _make_evidence_item(quality_score=0.85),
        ]
        entry = _make_catalog_entry(quality_sla={"min_score": 0.8})
        session = _make_session(items=items)

        result = await check_quality_sla(session, entry)

        assert result.passing is True
        assert not any(v.metric == "min_score" for v in result.violations)

    @pytest.mark.asyncio
    async def test_violation_when_average_below_threshold(self) -> None:
        items = [
            _make_evidence_item(quality_score=0.5),
            _make_evidence_item(quality_score=0.4),
        ]
        entry = _make_catalog_entry(quality_sla={"min_score": 0.8})
        session = _make_session(items=items)

        result = await check_quality_sla(session, entry)

        assert result.passing is False
        assert any(v.metric == "min_score" for v in result.violations)
        score_violation = next(v for v in result.violations if v.metric == "min_score")
        assert score_violation.threshold == 0.8
        assert score_violation.actual == pytest.approx(0.45)


# ---------------------------------------------------------------------------
# min_completeness violations
# ---------------------------------------------------------------------------


class TestMinCompleteness:
    """Tests for the min_completeness SLA threshold."""

    @pytest.mark.asyncio
    async def test_passes_when_completeness_above_threshold(self) -> None:
        items = [
            _make_evidence_item(quality_score=0.9),
            _make_evidence_item(quality_score=0.8),
            _make_evidence_item(quality_score=None),  # unscored
        ]
        entry = _make_catalog_entry(quality_sla={"min_completeness": 0.5})
        session = _make_session(items=items)

        result = await check_quality_sla(session, entry)

        # 2/3 = 0.67 > 0.5: passes
        assert not any(v.metric == "min_completeness" for v in result.violations)

    @pytest.mark.asyncio
    async def test_violation_when_completeness_below_threshold(self) -> None:
        items = [
            _make_evidence_item(quality_score=0.9),
            _make_evidence_item(quality_score=None),
            _make_evidence_item(quality_score=None),
            _make_evidence_item(quality_score=None),
        ]
        entry = _make_catalog_entry(quality_sla={"min_completeness": 0.8})
        session = _make_session(items=items)

        result = await check_quality_sla(session, entry)

        assert result.passing is False
        completeness_violations = [
            v for v in result.violations if v.metric == "min_completeness"
        ]
        assert len(completeness_violations) == 1
        assert completeness_violations[0].threshold == 0.8
        assert completeness_violations[0].actual == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# max_failing_fraction violations
# ---------------------------------------------------------------------------


class TestMaxFailingFraction:
    """Tests for the max_failing_fraction SLA threshold."""

    @pytest.mark.asyncio
    async def test_passes_when_failing_fraction_below_threshold(self) -> None:
        items = [
            _make_evidence_item(quality_score=0.9),
            _make_evidence_item(quality_score=0.85),
            _make_evidence_item(quality_score=0.2),  # fails min_score
        ]
        entry = _make_catalog_entry(
            quality_sla={"min_score": 0.5, "max_failing_fraction": 0.5}
        )
        session = _make_session(items=items)

        result = await check_quality_sla(session, entry)

        # 1/3 = 0.33 <= 0.5: passes
        assert not any(v.metric == "max_failing_fraction" for v in result.violations)

    @pytest.mark.asyncio
    async def test_violation_when_failing_fraction_over_threshold(self) -> None:
        items = [
            _make_evidence_item(quality_score=0.1),
            _make_evidence_item(quality_score=0.1),
            _make_evidence_item(quality_score=0.9),
        ]
        entry = _make_catalog_entry(
            quality_sla={"min_score": 0.5, "max_failing_fraction": 0.1}
        )
        session = _make_session(items=items)

        result = await check_quality_sla(session, entry)

        assert any(v.metric == "max_failing_fraction" for v in result.violations)


# ---------------------------------------------------------------------------
# SLAResult dataclass
# ---------------------------------------------------------------------------


class TestSLAResult:
    """Tests for the SLAResult dataclass."""

    def test_fields_are_accessible(self) -> None:
        result = SLAResult(passing=True, evidence_count=5, entry_id=uuid.uuid4())
        assert result.passing is True
        assert result.evidence_count == 5
        assert result.violations == []
        assert result.checked_at is not None

    def test_failing_result(self) -> None:
        violation = SLAViolation(
            metric="min_score",
            threshold=0.8,
            actual=0.5,
            message="Score too low",
        )
        result = SLAResult(passing=False, violations=[violation], evidence_count=10)
        assert result.passing is False
        assert len(result.violations) == 1


# ---------------------------------------------------------------------------
# Evidence count in results
# ---------------------------------------------------------------------------


class TestEvidenceCount:
    """Tests that evidence_count is populated correctly."""

    @pytest.mark.asyncio
    async def test_evidence_count_reflects_items(self) -> None:
        items = [
            _make_evidence_item(quality_score=0.8),
            _make_evidence_item(quality_score=0.9),
            _make_evidence_item(quality_score=0.7),
        ]
        entry = _make_catalog_entry(quality_sla={"min_score": 0.5})
        session = _make_session(items=items)

        result = await check_quality_sla(session, entry)

        assert result.evidence_count == 3
