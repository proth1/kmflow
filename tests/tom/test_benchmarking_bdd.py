"""BDD tests for Best Practices Library and Industry Benchmarking (Story #363).

Tests all three acceptance scenarios from the GitHub issue.
"""

from __future__ import annotations

import pytest

from src.tom.benchmarking import (
    compute_percentile,
    match_gaps_to_practices,
    percentile_label,
    rank_client,
)

# ── Scenario 2: Percentile Ranking Against Industry Benchmark ────────


class TestPercentileComputation:
    """Given benchmark data with p25/p50/p75/p90
    When a client value is compared
    Then the correct percentile ranking is computed.
    """

    def test_better_than_p25(self) -> None:
        """Client value below p25 is top quartile."""
        pct = compute_percentile(client_value=2, p25=3, p50=5, p75=8, p90=12)
        assert pct < 25
        assert pct == pytest.approx(16.67, abs=0.1)

    def test_at_p25(self) -> None:
        """Client value exactly at p25."""
        pct = compute_percentile(client_value=3, p25=3, p50=5, p75=8, p90=12)
        assert pct == pytest.approx(25.0)

    def test_between_p25_and_p50(self) -> None:
        """Client value of 6 days (between p25=3 and p50=5) is between p25 and p50."""
        # Actually 6 > p50=5, so should be between p50 and p75
        pct = compute_percentile(client_value=4, p25=3, p50=5, p75=8, p90=12)
        assert 25 < pct < 50

    def test_between_p50_and_p75(self) -> None:
        """Client value of 6 days (between p50=5 and p75=8) from acceptance criteria."""
        pct = compute_percentile(client_value=6, p25=3, p50=5, p75=8, p90=12)
        assert 50 < pct < 75

    def test_between_p75_and_p90(self) -> None:
        """Client value between p75 and p90."""
        pct = compute_percentile(client_value=10, p25=3, p50=5, p75=8, p90=12)
        assert 75 < pct < 90

    def test_worse_than_p90(self) -> None:
        """Client value above p90."""
        pct = compute_percentile(client_value=15, p25=3, p50=5, p75=8, p90=12)
        assert pct >= 90
        assert pct <= 100

    def test_zero_client_value(self) -> None:
        """Client value of zero is best possible."""
        pct = compute_percentile(client_value=0, p25=3, p50=5, p75=8, p90=12)
        assert pct == pytest.approx(0.0)

    def test_equal_benchmarks(self) -> None:
        """When p25 == p50, avoids division by zero."""
        pct = compute_percentile(client_value=5, p25=5, p50=5, p75=8, p90=12)
        assert pct == pytest.approx(25.0)


class TestPercentileLabel:
    """Labels map percentile ranges to human-readable text."""

    def test_top_quartile(self) -> None:
        assert percentile_label(10) == "Top Quartile (p25)"

    def test_between_p25_p50(self) -> None:
        assert percentile_label(40) == "Between p25 and p50"

    def test_between_p50_p75(self) -> None:
        assert percentile_label(60) == "Between p50 and p75"

    def test_between_p75_p90(self) -> None:
        assert percentile_label(80) == "Between p75 and p90"

    def test_below_p90(self) -> None:
        assert percentile_label(95) == "Below p90"


class TestRankClient:
    """rank_client combines percentile computation with distribution context."""

    def test_full_ranking(self) -> None:
        """Acceptance criteria: client 6 days against p25=3/p50=5/p75=8/p90=12."""
        ranking = rank_client(
            metric_name="average_processing_time",
            client_value=6.0,
            p25=3.0,
            p50=5.0,
            p75=8.0,
            p90=12.0,
        )
        assert ranking.metric_name == "average_processing_time"
        assert ranking.client_value == 6.0
        assert ranking.percentile_label == "Between p50 and p75"
        assert ranking.distribution == {"p25": 3.0, "p50": 5.0, "p75": 8.0, "p90": 12.0}
        assert 50 < ranking.percentile < 75

    def test_top_performer(self) -> None:
        ranking = rank_client("error_rate", 0.5, p25=2.0, p50=5.0, p75=10.0, p90=15.0)
        assert ranking.percentile_label == "Top Quartile (p25)"

    def test_bottom_performer(self) -> None:
        ranking = rank_client("stp_rate", 20.0, p25=3.0, p50=5.0, p75=8.0, p90=12.0)
        assert ranking.percentile_label == "Below p90"


# ── Scenario 3: Gap Recommendation Links to Best Practice ────────────


class TestGapToPracticeMatching:
    """Given gaps and best practices
    When matching is performed
    Then relevant practices are linked by domain, dimension, and keywords.
    """

    def _make_gap(
        self,
        gap_id: str = "g1",
        description: str = "manual exception logging",
        domain: str = "Loan Origination",
        tom_dimension: str = "process_architecture",
    ) -> dict[str, str]:
        return {
            "id": gap_id,
            "description": description,
            "domain": domain,
            "tom_dimension": tom_dimension,
        }

    def _make_practice(
        self,
        practice_id: str = "bp1",
        title: str = "Automated Exception Handling and Alerting",
        description: str = "Implement automated exception handling and alerting for process deviations",
        domain: str = "Loan Origination",
        industry: str = "Financial Services",
        tom_dimension: str = "process_architecture",
    ) -> dict[str, str]:
        return {
            "id": practice_id,
            "title": title,
            "description": description,
            "domain": domain,
            "industry": industry,
            "tom_dimension": tom_dimension,
        }

    def test_exact_domain_match(self) -> None:
        """Practices with same domain score higher."""
        gap = self._make_gap()
        practice = self._make_practice()
        matches = match_gaps_to_practices([gap], [practice])
        assert len(matches) == 1
        assert matches[0].relevance_score > 0.5

    def test_dimension_match(self) -> None:
        """Practices with same TOM dimension get bonus score."""
        gap = self._make_gap(tom_dimension="process_architecture")
        practice = self._make_practice(tom_dimension="process_architecture")
        matches = match_gaps_to_practices([gap], [practice])
        assert len(matches) == 1
        assert "dimension match" in matches[0].match_reason

    def test_keyword_overlap(self) -> None:
        """Practices with keyword overlap in description get bonus."""
        gap = self._make_gap(description="exception handling is manual and error-prone")
        practice = self._make_practice(description="automated exception handling and alerting for errors")
        matches = match_gaps_to_practices([gap], [practice])
        assert len(matches) == 1
        assert "keyword overlap" in matches[0].match_reason

    def test_no_match_different_domain(self) -> None:
        """Practices with no domain overlap may not match."""
        gap = self._make_gap(domain="KYC", tom_dimension="governance", description="unique gap xyz")
        practice = self._make_practice(domain="Trade Settlement", tom_dimension="technology", description="unique practice abc")
        matches = match_gaps_to_practices([gap], [practice])
        assert len(matches) == 0

    def test_multiple_practices_sorted_by_relevance(self) -> None:
        """Multiple matches are sorted by relevance descending."""
        gap = self._make_gap()
        p1 = self._make_practice(practice_id="bp1", domain="Loan Origination", tom_dimension="process_architecture")
        p2 = self._make_practice(practice_id="bp2", domain="Loan Origination", tom_dimension="governance", description="general governance improvement")
        matches = match_gaps_to_practices([gap], [p1, p2])
        assert len(matches) >= 1
        # p1 should rank higher (domain + dimension match)
        if len(matches) >= 2:
            assert matches[0].relevance_score >= matches[1].relevance_score

    def test_acceptance_criteria_scenario(self) -> None:
        """Full acceptance criteria: manual exception logging gap matched to automated handling practice."""
        gap = self._make_gap(
            gap_id="gap-manual-logging",
            description="manual exception logging",
            domain="Loan Origination",
            tom_dimension="process_architecture",
        )
        practice = self._make_practice(
            practice_id="bp-auto-exception",
            title="Automated Exception Handling and Alerting",
            description="Implement automated exception handling and alerting for process deviations",
            domain="Loan Origination",
            industry="Financial Services",
            tom_dimension="process_architecture",
        )
        matches = match_gaps_to_practices([gap], [practice])
        assert len(matches) == 1
        assert matches[0].practice_id == "bp-auto-exception"
        assert matches[0].practice_title == "Automated Exception Handling and Alerting"
        assert matches[0].gap_id == "gap-manual-logging"
        assert matches[0].relevance_score > 0.1

    def test_match_includes_industry(self) -> None:
        """Matched practice includes industry information."""
        gap = self._make_gap()
        practice = self._make_practice(industry="Financial Services")
        matches = match_gaps_to_practices([gap], [practice])
        assert matches[0].practice_industry == "Financial Services"

    def test_partial_domain_match(self) -> None:
        """Substring domain match scores lower than exact match."""
        gap = self._make_gap(domain="Loan")
        practice = self._make_practice(domain="Loan Origination")
        matches = match_gaps_to_practices([gap], [practice])
        assert len(matches) >= 1
        assert "partial domain match" in matches[0].match_reason

    def test_empty_gaps(self) -> None:
        """No gaps produces no matches."""
        practice = self._make_practice()
        matches = match_gaps_to_practices([], [practice])
        assert len(matches) == 0

    def test_empty_practices(self) -> None:
        """No practices produces no matches."""
        gap = self._make_gap()
        matches = match_gaps_to_practices([gap], [])
        assert len(matches) == 0
