"""BDD tests for Seed List Coverage and Dark Room Backlog (Story #367).

Tests all three acceptance scenarios from the GitHub issue.
"""

from __future__ import annotations

from src.core.services.coverage_service import (
    build_dark_room_backlog,
    compute_coverage,
    estimate_uplift,
)

# ── Scenario 1: Seed list coverage percentage report ─────────────────


class TestSeedListCoverage:
    """Given an engagement with seed terms and evidence links
    When the coverage report is computed
    Then correct counts and percentages are returned.
    """

    def _make_terms(self, count: int) -> list[dict[str, str]]:
        return [
            {"id": f"t{i}", "term": f"Term {i}", "domain": "general", "category": "activity", "status": "active"}
            for i in range(count)
        ]

    def test_acceptance_criteria_50_terms_38_covered(self) -> None:
        """50 seed terms, 38 covered → 76% coverage, 12 uncovered."""
        terms = self._make_terms(50)
        covered_ids = {f"t{i}" for i in range(38)}
        report = compute_coverage(terms, covered_ids)

        assert report.total_terms == 50
        assert report.covered_count == 38
        assert report.uncovered_count == 12
        assert report.coverage_percentage == 76.0
        assert len(report.uncovered_terms) == 12

    def test_all_covered(self) -> None:
        terms = self._make_terms(10)
        covered = {f"t{i}" for i in range(10)}
        report = compute_coverage(terms, covered)
        assert report.coverage_percentage == 100.0
        assert report.uncovered_count == 0
        assert len(report.uncovered_terms) == 0

    def test_none_covered(self) -> None:
        terms = self._make_terms(5)
        report = compute_coverage(terms, set())
        assert report.coverage_percentage == 0.0
        assert report.uncovered_count == 5
        assert len(report.uncovered_terms) == 5

    def test_empty_seed_list(self) -> None:
        report = compute_coverage([], set())
        assert report.total_terms == 0
        assert report.coverage_percentage == 0.0

    def test_deprecated_terms_excluded(self) -> None:
        """Deprecated terms should not count toward total."""
        terms = [
            {"id": "t1", "term": "Active", "domain": "d", "category": "activity", "status": "active"},
            {"id": "t2", "term": "Deprecated", "domain": "d", "category": "activity", "status": "deprecated"},
        ]
        report = compute_coverage(terms, {"t1"})
        assert report.total_terms == 1
        assert report.covered_count == 1
        assert report.coverage_percentage == 100.0

    def test_uncovered_terms_include_metadata(self) -> None:
        """Uncovered terms list includes term, domain, and category."""
        terms = [{"id": "t1", "term": "Login", "domain": "Auth", "category": "activity", "status": "active"}]
        report = compute_coverage(terms, set())
        assert len(report.uncovered_terms) == 1
        ut = report.uncovered_terms[0]
        assert ut["term"] == "Login"
        assert ut["domain"] == "Auth"
        assert ut["category"] == "activity"


# ── Scenario 2: Dark Room backlog ranked by estimated uplift ─────────


class TestDarkRoomBacklog:
    """Given an engagement with dark process segments
    When the backlog is built
    Then segments are listed ranked by estimated uplift.
    """

    def _make_element(
        self,
        element_id: str = "e1",
        name: str = "Task A",
        confidence: float = 0.2,
        evidence_count: int = 0,
        evidence_grade: str = "U",
    ) -> dict:
        return {
            "id": element_id,
            "name": name,
            "element_type": "activity",
            "confidence_score": confidence,
            "evidence_count": evidence_count,
            "evidence_grade": evidence_grade,
            "related_seed_terms": [],
        }

    def test_acceptance_criteria_10_dark_segments(self) -> None:
        """10 dark segments are listed sorted by uplift descending."""
        elements = [
            self._make_element(f"e{i}", f"Task {i}", confidence=i * 0.03)
            for i in range(10)
        ]
        backlog = build_dark_room_backlog(elements)
        assert len(backlog) == 10
        # Verify sorted descending by uplift
        for i in range(len(backlog) - 1):
            assert backlog[i].estimated_uplift >= backlog[i + 1].estimated_uplift

    def test_includes_confidence_and_uplift(self) -> None:
        """Each segment shows confidence and estimated uplift."""
        elements = [self._make_element("e1", "Task A", confidence=0.2)]
        backlog = build_dark_room_backlog(elements)
        assert len(backlog) == 1
        seg = backlog[0]
        assert seg.confidence_score == 0.2
        assert seg.estimated_uplift > 0

    def test_filters_above_threshold(self) -> None:
        """Elements with confidence >= 0.40 are excluded."""
        elements = [
            self._make_element("e1", "Dark", confidence=0.1),
            self._make_element("e2", "Bright", confidence=0.8),
            self._make_element("e3", "Borderline", confidence=0.40),
        ]
        backlog = build_dark_room_backlog(elements)
        assert len(backlog) == 1
        assert backlog[0].name == "Dark"

    def test_lowest_confidence_has_highest_uplift(self) -> None:
        """Elements with lowest confidence get highest uplift estimates."""
        elements = [
            self._make_element("e1", "Low", confidence=0.05),
            self._make_element("e2", "Mid", confidence=0.25),
        ]
        backlog = build_dark_room_backlog(elements)
        assert backlog[0].name == "Low"
        assert backlog[0].estimated_uplift > backlog[1].estimated_uplift

    def test_empty_elements(self) -> None:
        backlog = build_dark_room_backlog([])
        assert len(backlog) == 0

    def test_no_dark_elements(self) -> None:
        """All elements above threshold → empty backlog."""
        elements = [self._make_element("e1", "Bright", confidence=0.9)]
        backlog = build_dark_room_backlog(elements)
        assert len(backlog) == 0


# ── Scenario 3: Evidence acquisition actions ─────────────────────────


class TestEvidenceAcquisitionActions:
    """Given a dark segment
    When actions are generated
    Then missing knowledge forms and recommended actions are provided.
    """

    def _make_element(
        self,
        confidence: float = 0.1,
        evidence_count: int = 0,
        evidence_grade: str = "U",
    ) -> dict:
        return {
            "id": "e1",
            "name": "Dark Task",
            "element_type": "activity",
            "confidence_score": confidence,
            "evidence_count": evidence_count,
            "evidence_grade": evidence_grade,
            "related_seed_terms": ["login", "auth"],
        }

    def test_no_evidence_generates_full_actions(self) -> None:
        """Zero evidence → full set of acquisition recommendations."""
        elements = [self._make_element(evidence_count=0)]
        backlog = build_dark_room_backlog(elements)
        seg = backlog[0]
        assert len(seg.missing_knowledge_forms) >= 2
        assert len(seg.recommended_actions) >= 2
        assert any("walkthrough" in a.lower() for a in seg.recommended_actions)
        assert any("policy" in a.lower() or "document" in a.lower() for a in seg.recommended_actions)

    def test_single_source_evidence_suggests_corroboration(self) -> None:
        """Single-source evidence → suggest corroborating second source."""
        elements = [self._make_element(evidence_count=1, evidence_grade="D")]
        backlog = build_dark_room_backlog(elements)
        seg = backlog[0]
        assert any("corroborat" in f.lower() for f in seg.missing_knowledge_forms)

    def test_grade_c_suggests_sme_validation(self) -> None:
        """Grade C → suggest SME validation."""
        elements = [self._make_element(evidence_count=3, evidence_grade="C", confidence=0.35)]
        backlog = build_dark_room_backlog(elements)
        seg = backlog[0]
        assert any("sme" in f.lower() for f in seg.missing_knowledge_forms)

    def test_related_seed_terms_preserved(self) -> None:
        """Segment preserves related seed terms for cross-reference."""
        elements = [self._make_element()]
        backlog = build_dark_room_backlog(elements)
        seg = backlog[0]
        assert seg.related_seed_terms == ["login", "auth"]

    def test_uplift_estimation(self) -> None:
        """Verify uplift formula: (1.0 - confidence) * 0.5."""
        assert estimate_uplift(0.0) == 0.5
        assert estimate_uplift(0.2) == 0.4
        assert estimate_uplift(0.5) == 0.25
        assert estimate_uplift(1.0) == 0.0
