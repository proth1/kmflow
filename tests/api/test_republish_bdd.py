"""BDD tests for Republish Cycle and Version Diff (Story #361).

Tests all four acceptance scenarios from the GitHub issue.
"""

from __future__ import annotations

import pytest

from src.validation.republish import (
    COMPARED_FIELDS,
    DIFF_COLORS,
    ChangeType,
    ElementSnapshot,
    apply_decisions_to_elements,
    compute_diff,
)

# ── Scenario 1: POV Republish from Validation Decisions ─────────────


class TestRepublishFromDecisions:
    """Given POV v1 with validation feedback (CONFIRM, CORRECT, REJECT)
    When decisions are applied
    Then the new version incorporates all accepted decisions.
    """

    def _make_elements(self) -> list[ElementSnapshot]:
        return [
            ElementSnapshot(
                element_id="e1",
                name="Login",
                element_type="activity",
                confidence_score=0.8,
                evidence_grade="C",
                brightness_classification="DIM",
            ),
            ElementSnapshot(
                element_id="e2",
                name="Validate Input",
                element_type="activity",
                confidence_score=0.6,
                evidence_grade="D",
                brightness_classification="DARK",
            ),
            ElementSnapshot(
                element_id="e3",
                name="Process Order",
                element_type="activity",
                confidence_score=0.4,
                evidence_grade="U",
                brightness_classification="DARK",
            ),
            ElementSnapshot(
                element_id="e4",
                name="Send Notification",
                element_type="activity",
                confidence_score=0.7,
                evidence_grade="C",
                brightness_classification="DIM",
            ),
        ]

    def test_confirm_preserves_element(self) -> None:
        """CONFIRM decisions keep elements unchanged."""
        elements = self._make_elements()
        decisions = [{"element_id": "e1", "action": "confirm", "payload": {}}]
        result = apply_decisions_to_elements(elements, decisions)
        names = {e.name for e in result}
        assert "Login" in names

    def test_reject_removes_element(self) -> None:
        """REJECT decisions exclude elements from new version."""
        elements = self._make_elements()
        decisions = [{"element_id": "e3", "action": "reject", "payload": {}}]
        result = apply_decisions_to_elements(elements, decisions)
        names = {e.name for e in result}
        assert "Process Order" not in names
        assert len(result) == 3

    def test_correct_updates_element(self) -> None:
        """CORRECT decisions apply payload corrections."""
        elements = self._make_elements()
        decisions = [
            {
                "element_id": "e2",
                "action": "correct",
                "payload": {"confidence_score": 0.9},
            }
        ]
        result = apply_decisions_to_elements(elements, decisions)
        corrected = next(e for e in result if e.name == "Validate Input")
        assert corrected.confidence_score == 0.9

    def test_defer_carries_forward(self) -> None:
        """DEFER decisions leave elements unchanged in new version."""
        elements = self._make_elements()
        decisions = [{"element_id": "e4", "action": "defer", "payload": {}}]
        result = apply_decisions_to_elements(elements, decisions)
        deferred = next(e for e in result if e.name == "Send Notification")
        assert deferred.confidence_score == 0.7

    def test_combined_decisions(self) -> None:
        """Multiple decision types applied together."""
        elements = self._make_elements()
        decisions = [
            {"element_id": "e1", "action": "confirm", "payload": {}},
            {"element_id": "e2", "action": "correct", "payload": {"confidence_score": 0.95}},
            {"element_id": "e3", "action": "reject", "payload": {}},
            {"element_id": "e4", "action": "defer", "payload": {}},
        ]
        result = apply_decisions_to_elements(elements, decisions)
        assert len(result) == 3  # e3 rejected
        names = {e.name for e in result}
        assert names == {"Login", "Validate Input", "Send Notification"}

    def test_no_decisions_preserves_all(self) -> None:
        """No decisions leaves all elements unchanged."""
        elements = self._make_elements()
        result = apply_decisions_to_elements(elements, [])
        assert len(result) == 4

    def test_correct_with_name_change(self) -> None:
        """CORRECT decision can rename an element."""
        elements = self._make_elements()
        decisions = [
            {
                "element_id": "e2",
                "action": "correct",
                "payload": {"name": "Validate User Input"},
            }
        ]
        result = apply_decisions_to_elements(elements, decisions)
        names = {e.name for e in result}
        assert "Validate User Input" in names
        assert "Validate Input" not in names

    def test_correct_rename_collision_raises(self) -> None:
        """CORRECT rename to an existing element name raises ValueError."""
        elements = self._make_elements()
        decisions = [
            {
                "element_id": "e2",
                "action": "correct",
                "payload": {"name": "Login"},  # e1 already named "Login"
            }
        ]
        with pytest.raises(ValueError, match="element with that name already exists"):
            apply_decisions_to_elements(elements, decisions)


# ── Scenario 2: Version Diff Computation ─────────────────────────────


class TestVersionDiff:
    """Given POV v1 and POV v2 in the same engagement
    When the diff is computed
    Then added, removed, and modified elements are identified.
    """

    def test_added_elements(self) -> None:
        """Elements in v2 but not v1 are classified as added."""
        v1 = [ElementSnapshot(element_id="e1", name="Login", element_type="activity")]
        v2 = [
            ElementSnapshot(element_id="e1", name="Login", element_type="activity"),
            ElementSnapshot(element_id="e2", name="Register", element_type="activity"),
        ]
        diff = compute_diff(v1, v2)
        assert len(diff.added) == 1
        assert diff.added[0].element_name == "Register"

    def test_removed_elements(self) -> None:
        """Elements in v1 but not v2 are classified as removed."""
        v1 = [
            ElementSnapshot(element_id="e1", name="Login", element_type="activity"),
            ElementSnapshot(element_id="e2", name="Logout", element_type="activity"),
        ]
        v2 = [ElementSnapshot(element_id="e1", name="Login", element_type="activity")]
        diff = compute_diff(v1, v2)
        assert len(diff.removed) == 1
        assert diff.removed[0].element_name == "Logout"

    def test_modified_elements(self) -> None:
        """Elements in both with changed attributes are classified as modified."""
        v1 = [ElementSnapshot(element_id="e1", name="Login", element_type="activity", confidence_score=0.5)]
        v2 = [ElementSnapshot(element_id="e1", name="Login", element_type="activity", confidence_score=0.9)]
        diff = compute_diff(v1, v2)
        assert len(diff.modified) == 1
        assert "confidence_score" in diff.modified[0].changed_fields

    def test_unchanged_elements_counted(self) -> None:
        """Elements with no changes are counted but not listed."""
        v1 = [ElementSnapshot(element_id="e1", name="Login", element_type="activity", confidence_score=0.5)]
        v2 = [ElementSnapshot(element_id="e1", name="Login", element_type="activity", confidence_score=0.5)]
        diff = compute_diff(v1, v2)
        assert diff.unchanged_count == 1
        assert len(diff.added) == 0
        assert len(diff.removed) == 0
        assert len(diff.modified) == 0

    def test_total_changes_property(self) -> None:
        """total_changes counts added + removed + modified."""
        v1 = [
            ElementSnapshot(element_id="e1", name="A", element_type="activity"),
            ElementSnapshot(element_id="e2", name="B", element_type="activity", confidence_score=0.5),
        ]
        v2 = [
            ElementSnapshot(element_id="e2", name="B", element_type="activity", confidence_score=0.9),
            ElementSnapshot(element_id="e3", name="C", element_type="activity"),
        ]
        diff = compute_diff(v1, v2)
        assert diff.total_changes == 3  # 1 added (C), 1 removed (A), 1 modified (B)

    def test_empty_versions(self) -> None:
        """Both versions empty produces no changes."""
        diff = compute_diff([], [])
        assert diff.total_changes == 0
        assert diff.unchanged_count == 0

    def test_version_ids_in_diff(self) -> None:
        """Diff preserves version IDs."""
        diff = compute_diff([], [], v1_id="version-1", v2_id="version-2")
        assert diff.v1_id == "version-1"
        assert diff.v2_id == "version-2"


# ── Scenario 3: BPMN Diff Visualization Color-Coding ────────────────


class TestBPMNDiffColors:
    """Given a computed diff
    When BPMN visualization data is produced
    Then elements are color-coded: green=added, red=removed, yellow=modified.
    """

    def test_added_elements_green(self) -> None:
        v1: list[ElementSnapshot] = []
        v2 = [ElementSnapshot(element_id="e1", name="New Task", element_type="activity")]
        diff = compute_diff(v1, v2)
        assert diff.added[0].color == "#28a745"
        assert diff.added[0].css_class == "diff-added"

    def test_removed_elements_red(self) -> None:
        v1 = [ElementSnapshot(element_id="e1", name="Old Task", element_type="activity")]
        v2: list[ElementSnapshot] = []
        diff = compute_diff(v1, v2)
        assert diff.removed[0].color == "#dc3545"
        assert diff.removed[0].css_class == "diff-removed"

    def test_modified_elements_yellow(self) -> None:
        v1 = [ElementSnapshot(element_id="e1", name="Task", element_type="activity", confidence_score=0.3)]
        v2 = [ElementSnapshot(element_id="e1", name="Task", element_type="activity", confidence_score=0.8)]
        diff = compute_diff(v1, v2)
        assert diff.modified[0].color == "#ffc107"
        assert diff.modified[0].css_class == "diff-modified"

    def test_diff_colors_constant(self) -> None:
        assert DIFF_COLORS[ChangeType.ADDED] == "#28a745"
        assert DIFF_COLORS[ChangeType.REMOVED] == "#dc3545"
        assert DIFF_COLORS[ChangeType.MODIFIED] == "#ffc107"
        assert DIFF_COLORS[ChangeType.UNCHANGED] == "none"


# ── Scenario 4: Dark-Room Shrink Rate ────────────────────────────────


class TestDarkRoomShrinkRate:
    """Given POV v1 has 15 Dark segments and v2 has 10
    Then the shrink rate is 33% (5 of 15 illuminated).
    """

    def test_shrink_rate_computation(self) -> None:
        v1 = [
            ElementSnapshot(
                element_id=f"e{i}",
                name=f"Task {i}",
                element_type="activity",
                brightness_classification="DARK",
            )
            for i in range(15)
        ]
        v2_dark = [
            ElementSnapshot(
                element_id=f"e{i}",
                name=f"Task {i}",
                element_type="activity",
                brightness_classification="DARK",
            )
            for i in range(10)
        ]
        v2_bright = [
            ElementSnapshot(
                element_id=f"e{i}",
                name=f"Task {i}",
                element_type="activity",
                brightness_classification="BRIGHT",
            )
            for i in range(10, 15)
        ]
        diff = compute_diff(v1, v2_dark + v2_bright)
        assert diff.dark_shrink_rate == pytest.approx(33.33, abs=0.1)

    def test_no_dark_elements_zero_rate(self) -> None:
        """No dark elements in v1 means 0% shrink rate."""
        v1 = [ElementSnapshot(element_id="e1", name="A", element_type="activity", brightness_classification="BRIGHT")]
        v2 = [ElementSnapshot(element_id="e1", name="A", element_type="activity", brightness_classification="BRIGHT")]
        diff = compute_diff(v1, v2)
        assert diff.dark_shrink_rate == pytest.approx(0.0)

    def test_all_dark_removed_100_rate(self) -> None:
        """All dark elements illuminated = 100% shrink rate."""
        v1 = [
            ElementSnapshot(element_id="e1", name="A", element_type="activity", brightness_classification="DARK"),
            ElementSnapshot(element_id="e2", name="B", element_type="activity", brightness_classification="DARK"),
        ]
        v2 = [
            ElementSnapshot(element_id="e1", name="A", element_type="activity", brightness_classification="BRIGHT"),
            ElementSnapshot(element_id="e2", name="B", element_type="activity", brightness_classification="BRIGHT"),
        ]
        diff = compute_diff(v1, v2)
        assert diff.dark_shrink_rate == pytest.approx(100.0)


# ── Edge Cases and Field Comparison ──────────────────────────────────


class TestFieldComparison:
    """Verify the set of compared fields is correct."""

    def test_compared_fields_set(self) -> None:
        expected = {
            "name",
            "confidence_score",
            "evidence_grade",
            "brightness_classification",
            "element_type",
            "evidence_count",
        }
        assert expected == COMPARED_FIELDS

    def test_modified_tracks_changed_values(self) -> None:
        """Modified elements include prior and current values."""
        v1 = [ElementSnapshot(element_id="e1", name="Task", element_type="activity", evidence_grade="C")]
        v2 = [ElementSnapshot(element_id="e1", name="Task", element_type="activity", evidence_grade="B")]
        diff = compute_diff(v1, v2)
        change = diff.modified[0]
        assert change.prior_values.get("evidence_grade") == "C"
        assert change.current_values.get("evidence_grade") == "B"
