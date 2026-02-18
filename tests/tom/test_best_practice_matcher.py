"""Tests for BestPracticeMatcher.

Validates gap-to-best-practice matching by TOM dimension and
optional embedding similarity ranking.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models import TOMDimension
from src.tom.best_practice_matcher import BestPracticeMatcher


def _make_gap(dimension: TOMDimension, recommendation: str = "Improve the process") -> MagicMock:
    gap = MagicMock()
    gap.id = uuid.uuid4()
    gap.dimension = dimension
    gap.recommendation = recommendation
    gap.severity = 0.7
    gap.confidence = 0.8
    return gap


def _make_bp(dimension: TOMDimension, description: str = "Best practice description") -> MagicMock:
    bp = MagicMock()
    bp.id = uuid.uuid4()
    bp.domain = "Finance"
    bp.industry = "Banking"
    bp.description = description
    bp.source = "KPMG"
    bp.tom_dimension = dimension
    return bp


# =============================================================================
# Dimension-based matching (no embedding service)
# =============================================================================


@pytest.mark.asyncio
async def test_match_by_dimension():
    """Gaps are matched to best practices with the same TOM dimension."""
    matcher = BestPracticeMatcher()
    session = AsyncMock()
    engagement_id = str(uuid.uuid4())
    tom_id = str(uuid.uuid4())

    gap = _make_gap(TOMDimension.PROCESS_ARCHITECTURE)
    bp_match = _make_bp(TOMDimension.PROCESS_ARCHITECTURE)
    bp_no_match = _make_bp(TOMDimension.RISK_AND_COMPLIANCE)

    gap_scalars = MagicMock()
    gap_scalars.all.return_value = [gap]
    gap_result = MagicMock()
    gap_result.scalars.return_value = gap_scalars

    bp_scalars = MagicMock()
    bp_scalars.all.return_value = [bp_match, bp_no_match]
    bp_result = MagicMock()
    bp_result.scalars.return_value = bp_scalars

    session.execute = AsyncMock(side_effect=[gap_result, bp_result])

    result = await matcher.match_gaps_to_practices(session, engagement_id, tom_id)

    gap_id = str(gap.id)
    assert gap_id in result
    assert len(result[gap_id]) == 1
    assert result[gap_id][0]["tom_dimension"] == str(TOMDimension.PROCESS_ARCHITECTURE)


@pytest.mark.asyncio
async def test_no_match_different_dimension():
    """Gaps with no matching dimension return empty list."""
    matcher = BestPracticeMatcher()
    session = AsyncMock()

    gap = _make_gap(TOMDimension.PEOPLE_AND_ORGANIZATION)
    bp = _make_bp(TOMDimension.TECHNOLOGY_AND_DATA)

    gap_scalars = MagicMock()
    gap_scalars.all.return_value = [gap]
    gap_result = MagicMock()
    gap_result.scalars.return_value = gap_scalars

    bp_scalars = MagicMock()
    bp_scalars.all.return_value = [bp]
    bp_result = MagicMock()
    bp_result.scalars.return_value = bp_scalars

    session.execute = AsyncMock(side_effect=[gap_result, bp_result])

    result = await matcher.match_gaps_to_practices(session, "eng-1", "tom-1")

    gap_id = str(gap.id)
    assert gap_id in result
    assert result[gap_id] == []


@pytest.mark.asyncio
async def test_empty_gaps_returns_empty_dict():
    """No gaps → empty result dict."""
    matcher = BestPracticeMatcher()
    session = AsyncMock()

    gap_scalars = MagicMock()
    gap_scalars.all.return_value = []
    gap_result = MagicMock()
    gap_result.scalars.return_value = gap_scalars

    bp_scalars = MagicMock()
    bp_scalars.all.return_value = [_make_bp(TOMDimension.PROCESS_ARCHITECTURE)]
    bp_result = MagicMock()
    bp_result.scalars.return_value = bp_scalars

    session.execute = AsyncMock(side_effect=[gap_result, bp_result])

    result = await matcher.match_gaps_to_practices(session, "eng-1", "tom-1")
    assert result == {}


@pytest.mark.asyncio
async def test_multiple_gaps_matched():
    """Multiple gaps each get their own matching best practices."""
    matcher = BestPracticeMatcher()
    session = AsyncMock()

    gap1 = _make_gap(TOMDimension.PROCESS_ARCHITECTURE, "Streamline workflow")
    gap2 = _make_gap(TOMDimension.GOVERNANCE_STRUCTURES, "Establish governance board")
    bp_proc = _make_bp(TOMDimension.PROCESS_ARCHITECTURE, "Automate manual steps")
    bp_gov = _make_bp(TOMDimension.GOVERNANCE_STRUCTURES, "Create oversight committee")

    gap_scalars = MagicMock()
    gap_scalars.all.return_value = [gap1, gap2]
    gap_result = MagicMock()
    gap_result.scalars.return_value = gap_scalars

    bp_scalars = MagicMock()
    bp_scalars.all.return_value = [bp_proc, bp_gov]
    bp_result = MagicMock()
    bp_result.scalars.return_value = bp_scalars

    session.execute = AsyncMock(side_effect=[gap_result, bp_result])

    result = await matcher.match_gaps_to_practices(session, "eng-1", "tom-1")

    assert str(gap1.id) in result
    assert str(gap2.id) in result
    assert len(result[str(gap1.id)]) == 1
    assert len(result[str(gap2.id)]) == 1


@pytest.mark.asyncio
async def test_bp_dict_structure():
    """Returned best practice dict has expected keys."""
    matcher = BestPracticeMatcher()
    session = AsyncMock()

    gap = _make_gap(TOMDimension.TECHNOLOGY_AND_DATA, "Upgrade data platform")
    bp = _make_bp(TOMDimension.TECHNOLOGY_AND_DATA, "Implement data mesh")

    gap_scalars = MagicMock()
    gap_scalars.all.return_value = [gap]
    gap_result = MagicMock()
    gap_result.scalars.return_value = gap_scalars

    bp_scalars = MagicMock()
    bp_scalars.all.return_value = [bp]
    bp_result = MagicMock()
    bp_result.scalars.return_value = bp_scalars

    session.execute = AsyncMock(side_effect=[gap_result, bp_result])

    result = await matcher.match_gaps_to_practices(session, "eng-1", "tom-1")

    bp_entry = result[str(gap.id)][0]
    assert "id" in bp_entry
    assert "domain" in bp_entry
    assert "industry" in bp_entry
    assert "description" in bp_entry
    assert "tom_dimension" in bp_entry
    assert "score" in bp_entry


# =============================================================================
# Embedding-based ranking
# =============================================================================


def _make_embedding_service(similarities: list[float]) -> MagicMock:
    """Mock embedding service returning preset cosine similarities."""
    import math

    svc = MagicMock()
    query_vec = [1.0, 0.0]
    bp_vecs = []
    for sim in similarities:
        angle = math.acos(max(-1.0, min(1.0, sim)))
        bp_vecs.append([math.cos(angle), math.sin(angle)])

    svc.embed_text.return_value = query_vec
    svc.embed_texts.return_value = bp_vecs
    return svc


@pytest.mark.asyncio
async def test_embedding_ranking_filters_below_threshold():
    """Embedding scores below 0.5 are excluded from results."""
    embedding_service = _make_embedding_service([0.3])
    matcher = BestPracticeMatcher(embedding_service=embedding_service)
    session = AsyncMock()

    gap = _make_gap(TOMDimension.PROCESS_ARCHITECTURE, "Automate review steps")
    bp = _make_bp(TOMDimension.PROCESS_ARCHITECTURE, "Use workflow automation")

    gap_scalars = MagicMock()
    gap_scalars.all.return_value = [gap]
    gap_result = MagicMock()
    gap_result.scalars.return_value = gap_scalars

    bp_scalars = MagicMock()
    bp_scalars.all.return_value = [bp]
    bp_result = MagicMock()
    bp_result.scalars.return_value = bp_scalars

    session.execute = AsyncMock(side_effect=[gap_result, bp_result])

    result = await matcher.match_gaps_to_practices(session, "eng-1", "tom-1")
    # Below threshold → excluded
    assert result[str(gap.id)] == []


@pytest.mark.asyncio
async def test_embedding_ranking_includes_above_threshold():
    """Embedding scores >= 0.5 are included with score attached."""
    embedding_service = _make_embedding_service([0.8])
    matcher = BestPracticeMatcher(embedding_service=embedding_service)
    session = AsyncMock()

    gap = _make_gap(TOMDimension.PROCESS_ARCHITECTURE, "Automate review steps")
    bp = _make_bp(TOMDimension.PROCESS_ARCHITECTURE, "Use workflow automation")

    gap_scalars = MagicMock()
    gap_scalars.all.return_value = [gap]
    gap_result = MagicMock()
    gap_result.scalars.return_value = gap_scalars

    bp_scalars = MagicMock()
    bp_scalars.all.return_value = [bp]
    bp_result = MagicMock()
    bp_result.scalars.return_value = bp_scalars

    session.execute = AsyncMock(side_effect=[gap_result, bp_result])

    result = await matcher.match_gaps_to_practices(session, "eng-1", "tom-1")
    assert len(result[str(gap.id)]) == 1
    assert result[str(gap.id)][0]["score"] == pytest.approx(0.8, abs=0.01)


@pytest.mark.asyncio
async def test_embedding_ranking_sorted_by_score():
    """Multiple BPs sorted descending by similarity score."""
    embedding_service = _make_embedding_service([0.9, 0.6, 0.75])
    matcher = BestPracticeMatcher(embedding_service=embedding_service)
    session = AsyncMock()

    gap = _make_gap(TOMDimension.PROCESS_ARCHITECTURE, "Improve process")
    bp1 = _make_bp(TOMDimension.PROCESS_ARCHITECTURE, "BP with score 0.9")
    bp2 = _make_bp(TOMDimension.PROCESS_ARCHITECTURE, "BP with score 0.6")
    bp3 = _make_bp(TOMDimension.PROCESS_ARCHITECTURE, "BP with score 0.75")

    gap_scalars = MagicMock()
    gap_scalars.all.return_value = [gap]
    gap_result = MagicMock()
    gap_result.scalars.return_value = gap_scalars

    bp_scalars = MagicMock()
    bp_scalars.all.return_value = [bp1, bp2, bp3]
    bp_result = MagicMock()
    bp_result.scalars.return_value = bp_scalars

    session.execute = AsyncMock(side_effect=[gap_result, bp_result])

    result = await matcher.match_gaps_to_practices(session, "eng-1", "tom-1")

    scores = [r["score"] for r in result[str(gap.id)]]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == pytest.approx(0.9, abs=0.01)
