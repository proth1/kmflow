"""Tests for evidence gap scanner agent."""

from __future__ import annotations

from datetime import UTC, datetime

from src.agents.gap_scanner import scan_evidence_gaps


class TestScanEvidenceGaps:
    """Tests for scan_evidence_gaps function."""

    def test_finds_elements_with_no_evidence(self):
        evidence_items = [
            {"id": "e1", "category": "documents"},
        ]
        process_elements = [
            {"id": "p1", "name": "Task1", "evidence_ids": ["e1"]},
            {"id": "p2", "name": "Task2", "evidence_ids": []},
        ]
        gaps = scan_evidence_gaps(evidence_items, process_elements)
        missing_gaps = [g for g in gaps if g["gap_type"] == "missing_evidence"]
        assert len(missing_gaps) == 1
        assert missing_gaps[0]["element_name"] == "Task2"
        assert missing_gaps[0]["severity"] == "high"

    def test_finds_elements_with_single_source(self):
        evidence_items = [
            {"id": "e1", "category": "documents"},
        ]
        process_elements = [
            {"id": "p1", "name": "Task1", "evidence_ids": ["e1"]},
        ]
        gaps = scan_evidence_gaps(evidence_items, process_elements)
        single_source_gaps = [g for g in gaps if g["gap_type"] == "single_source"]
        assert len(single_source_gaps) == 1
        assert single_source_gaps[0]["element_name"] == "Task1"
        assert single_source_gaps[0]["severity"] == "medium"

    def test_finds_low_quality_evidence_below_threshold(self):
        evidence_items = [
            {"id": "e1", "name": "WeakDoc", "category": "documents", "quality_score": 0.3},
        ]
        process_elements = []
        gaps = scan_evidence_gaps(evidence_items, process_elements, coverage_threshold=0.6)
        weak_gaps = [g for g in gaps if g["gap_type"] == "weak_evidence"]
        assert len(weak_gaps) == 1
        assert "WeakDoc" in weak_gaps[0]["description"]

    def test_finds_missing_expected_categories(self):
        evidence_items = [
            {"id": "e1", "category": "documents"},
        ]
        process_elements = []
        gaps = scan_evidence_gaps(evidence_items, process_elements)
        category_gaps = [g for g in gaps if g["gap_type"] == "missing_category"]
        # Expected: structured_data, bpm_process_models, controls_evidence, domain_communications
        assert len(category_gaps) == 4
        missing_cats = {g["element_name"] for g in category_gaps}
        assert "structured_data" in missing_cats
        assert "bpm_process_models" in missing_cats

    def test_finds_stale_evidence_older_than_one_year(self):
        # Create date that's over a year old (2 years to be safe)
        old_date = datetime.now(UTC).replace(year=datetime.now(UTC).year - 2)
        evidence_items = [
            {"id": "e1", "name": "OldDoc", "category": "documents", "source_date": old_date},
        ]
        process_elements = []
        gaps = scan_evidence_gaps(evidence_items, process_elements)
        stale_gaps = [g for g in gaps if g["gap_type"] == "stale_evidence"]
        assert len(stale_gaps) == 1
        assert "OldDoc" in stale_gaps[0]["description"]

    def test_returns_empty_list_when_all_evidence_is_good(self):
        evidence_items = [
            {"id": "e1", "category": "documents", "quality_score": 0.9},
            {"id": "e2", "category": "structured_data", "quality_score": 0.9},
            {"id": "e3", "category": "bpm_process_models", "quality_score": 0.9},
            {"id": "e4", "category": "controls_evidence", "quality_score": 0.9},
            {"id": "e5", "category": "domain_communications", "quality_score": 0.9},
        ]
        process_elements = [
            {"id": "p1", "name": "Task1", "evidence_ids": ["e1", "e2"]},
        ]
        gaps = scan_evidence_gaps(evidence_items, process_elements)
        # No missing evidence, no single source, no weak evidence, no missing categories, no stale
        assert len(gaps) == 0

    def test_handles_empty_evidence_items(self):
        evidence_items = []
        process_elements = [
            {"id": "p1", "name": "Task1", "evidence_ids": ["e1"]},
        ]
        gaps = scan_evidence_gaps(evidence_items, process_elements)
        # All elements should have missing evidence
        missing_gaps = [g for g in gaps if g["gap_type"] == "missing_evidence"]
        assert len(missing_gaps) == 1

    def test_handles_empty_process_elements(self):
        evidence_items = [
            {"id": "e1", "category": "documents", "quality_score": 0.9},
        ]
        process_elements = []
        gaps = scan_evidence_gaps(evidence_items, process_elements)
        # Should still check for missing categories
        category_gaps = [g for g in gaps if g["gap_type"] == "missing_category"]
        assert len(category_gaps) > 0

    def test_iso_date_string_parsing_for_source_date(self):
        old_date_str = "2023-01-01T00:00:00+00:00"
        evidence_items = [
            {"id": "e1", "name": "OldDoc", "category": "documents", "source_date": old_date_str},
        ]
        process_elements = []
        gaps = scan_evidence_gaps(evidence_items, process_elements)
        stale_gaps = [g for g in gaps if g["gap_type"] == "stale_evidence"]
        assert len(stale_gaps) == 1

    def test_handles_invalid_date_strings_gracefully(self):
        evidence_items = [
            {"id": "e1", "name": "Doc", "category": "documents", "source_date": "invalid-date"},
        ]
        process_elements = []
        # Should not raise an exception
        gaps = scan_evidence_gaps(evidence_items, process_elements)
        # Invalid date should be skipped, no stale evidence gap
        stale_gaps = [g for g in gaps if g["gap_type"] == "stale_evidence"]
        assert len(stale_gaps) == 0

    def test_handles_none_evidence_ids(self):
        evidence_items = [
            {"id": "e1", "category": "documents"},
        ]
        process_elements = [
            {"id": "p1", "name": "Task1", "evidence_ids": None},
        ]
        gaps = scan_evidence_gaps(evidence_items, process_elements)
        missing_gaps = [g for g in gaps if g["gap_type"] == "missing_evidence"]
        assert len(missing_gaps) == 1

    def test_recommendation_includes_element_name(self):
        evidence_items = []
        process_elements = [
            {"id": "p1", "name": "ImportantTask", "evidence_ids": []},
        ]
        gaps = scan_evidence_gaps(evidence_items, process_elements)
        missing_gaps = [g for g in gaps if g["gap_type"] == "missing_evidence"]
        assert "ImportantTask" in missing_gaps[0]["recommendation"]

    def test_quality_score_displayed_in_weak_evidence_gap(self):
        evidence_items = [
            {"id": "e1", "name": "WeakDoc", "category": "documents", "quality_score": 0.35},
        ]
        process_elements = []
        gaps = scan_evidence_gaps(evidence_items, process_elements, coverage_threshold=0.6)
        weak_gaps = [g for g in gaps if g["gap_type"] == "weak_evidence"]
        assert "0.35" in weak_gaps[0]["description"]
