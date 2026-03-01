"""Tests for the evidence quality scoring engine."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from src.evidence.quality import (
    FRESHNESS_THRESHOLD_DAYS,
    calculate_freshness,
    calculate_reliability,
)


class TestFreshness:
    """Test suite for freshness calculation."""

    def test_freshness_today(self) -> None:
        """A document dated today should have freshness close to 1.0."""
        score = calculate_freshness(date.today(), date.today())
        assert abs(score - 1.0) < 0.01

    def test_freshness_at_threshold(self) -> None:
        """A document at FRESHNESS_THRESHOLD_DAYS old should have freshness ~0.5."""
        ref = date.today()
        source = ref - timedelta(days=FRESHNESS_THRESHOLD_DAYS)
        score = calculate_freshness(source, ref)
        assert abs(score - 0.5) < 0.05

    def test_freshness_very_old(self) -> None:
        """A very old document (>5000 days) should have freshness close to 0."""
        ref = date.today()
        source = ref - timedelta(days=5100)
        score = calculate_freshness(source, ref)
        assert score < 0.01

    def test_freshness_future_date(self) -> None:
        """Future-dated documents should have freshness 1.0."""
        ref = date.today()
        source = ref + timedelta(days=30)
        score = calculate_freshness(source, ref)
        assert score == 1.0

    def test_freshness_none_date(self) -> None:
        """Unknown dates should return default freshness."""
        score = calculate_freshness(None)
        assert score == 0.3

    def test_freshness_datetime_input(self) -> None:
        """Should accept datetime objects."""
        ref = date.today()
        source = datetime(ref.year, ref.month, ref.day)
        score = calculate_freshness(source, ref)
        assert abs(score - 1.0) < 0.01

    def test_freshness_decreases_with_age(self) -> None:
        """Freshness should decrease as the document gets older."""
        ref = date.today()
        score_30 = calculate_freshness(ref - timedelta(days=30), ref)
        score_180 = calculate_freshness(ref - timedelta(days=180), ref)
        score_365 = calculate_freshness(ref - timedelta(days=365), ref)
        assert score_30 > score_180 > score_365


class TestReliability:
    """Test suite for reliability calculation."""

    def test_reliability_official(self) -> None:
        """Official sources should score 1.0."""
        score = calculate_reliability({"source_type": "official"})
        assert score == 1.0

    def test_reliability_verified(self) -> None:
        """Verified sources should score 0.9."""
        score = calculate_reliability({"source_type": "verified"})
        assert score == 0.9

    def test_reliability_unknown(self) -> None:
        """Unknown sources should score 0.4."""
        score = calculate_reliability({"source_type": "unknown"})
        assert score == 0.4

    def test_reliability_none_metadata(self) -> None:
        """None metadata should return unknown score."""
        score = calculate_reliability(None)
        assert score == 0.4

    def test_reliability_empty_metadata(self) -> None:
        """Empty metadata should return unknown score."""
        score = calculate_reliability({})
        assert score == 0.4

    def test_reliability_verified_bonus(self) -> None:
        """Verified flag should add 0.1 bonus."""
        score = calculate_reliability({"source_type": "client_provided", "verified": True})
        assert abs(score - 0.7) < 0.01

    def test_reliability_author_bonus(self) -> None:
        """Author attribution should add 0.05 bonus."""
        score = calculate_reliability({"source_type": "client_provided", "author": "Jane"})
        assert abs(score - 0.65) < 0.01

    def test_reliability_combined_bonuses(self) -> None:
        """Both bonuses should stack up to 1.0 max."""
        score = calculate_reliability(
            {
                "source_type": "verified",
                "verified": True,
                "author": "John",
            }
        )
        assert score == 1.0  # 0.9 + 0.1 + 0.05 = 1.05 -> capped at 1.0

    def test_reliability_client_provided(self) -> None:
        """Client-provided sources should score 0.6."""
        score = calculate_reliability({"source_type": "client_provided"})
        assert abs(score - 0.6) < 0.01
