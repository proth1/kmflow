"""BDD tests for Governance Flag Detection (Story #381).

Tests the 4 acceptance scenarios:
1. Merging Approver and Processor roles triggers SoD flag
2. Automating a regulated decision triggers compliance impact flag
3. Governance flags explicitly acknowledge knowledge boundaries
4. Suggestions with no governance concerns produce no false positive flags
"""

from __future__ import annotations

from src.core.governance.flag_detector import GovernanceFlagDetector


class TestSoDDetection:
    """Scenario 1: Merging Approver and Processor roles triggers SoD flag."""

    def test_merge_triggers_sod_flag(self) -> None:
        """Merging Approver and Processor produces segregation_of_duties flag."""
        detector = GovernanceFlagDetector()
        flags = detector.check(
            {
                "role_changes": [{"type": "merge", "roles": ["Approver", "Processor"], "element_id": "task_1"}],
                "affected_element_ids": [],
            }
        )

        assert len(flags) == 1
        assert flags[0].flag_type == "segregation_of_duties"

    def test_sod_flag_names_both_roles(self) -> None:
        """Flag description names the two roles being merged."""
        detector = GovernanceFlagDetector()
        flags = detector.check(
            {
                "role_changes": [{"type": "merge", "roles": ["Approver", "Processor"], "element_id": "task_1"}],
                "affected_element_ids": [],
            }
        )

        assert "Approver" in flags[0].description
        assert "Processor" in flags[0].description

    def test_sod_flag_states_known_constraint(self) -> None:
        """Flag explicitly states this is a known constraint identified by the system."""
        detector = GovernanceFlagDetector()
        flags = detector.check(
            {
                "role_changes": [{"type": "merge", "roles": ["Approver", "Processor"], "element_id": "task_1"}],
                "affected_element_ids": [],
            }
        )

        assert "known constraint" in flags[0].description.lower()


class TestRegulatoryDetection:
    """Scenario 2: Automating a regulated decision triggers compliance impact flag."""

    def test_automate_regulated_element_triggers_flag(self) -> None:
        """Automating an element tagged with SOX Section 302 produces regulatory flag."""
        detector = GovernanceFlagDetector(
            regulated_elements={"task_approve": ["SOX Section 302"]},
        )
        flags = detector.check(
            {
                "role_changes": [
                    {
                        "type": "automate",
                        "element_id": "task_approve",
                        "element_name": "Final Approval",
                    }
                ],
                "affected_element_ids": [],
            }
        )

        assert len(flags) == 1
        assert flags[0].flag_type == "regulatory_compliance"

    def test_regulatory_flag_references_regulation(self) -> None:
        """Flag references SOX Section 302 as the relevant regulation."""
        detector = GovernanceFlagDetector(
            regulated_elements={"task_approve": ["SOX Section 302"]},
        )
        flags = detector.check(
            {
                "role_changes": [
                    {
                        "type": "automate",
                        "element_id": "task_approve",
                        "element_name": "Final Approval",
                    }
                ],
                "affected_element_ids": [],
            }
        )

        assert flags[0].regulation_reference == "SOX Section 302"

    def test_regulatory_flag_distinguishes_constraint_types(self) -> None:
        """Flag text distinguishes 'known constraint' from 'possible impact'."""
        detector = GovernanceFlagDetector(
            regulated_elements={"task_approve": ["SOX Section 302"]},
        )
        flags = detector.check(
            {
                "role_changes": [
                    {
                        "type": "automate",
                        "element_id": "task_approve",
                        "element_name": "Final Approval",
                    }
                ],
                "affected_element_ids": [],
            }
        )

        assert "possible impact" in flags[0].description.lower() or "requiring" in flags[0].description.lower()


class TestKnowledgeBoundaries:
    """Scenario 3: Governance flags explicitly acknowledge knowledge boundaries."""

    def test_sod_flag_has_knowledge_boundary(self) -> None:
        """SoD flag includes a knowledge_boundary field."""
        detector = GovernanceFlagDetector()
        flags = detector.check(
            {
                "role_changes": [{"type": "merge", "roles": ["Approver", "Processor"], "element_id": "task_1"}],
                "affected_element_ids": [],
            }
        )

        assert flags[0].knowledge_boundary
        assert len(flags[0].knowledge_boundary) > 0

    def test_knowledge_boundary_states_limitations(self) -> None:
        """Knowledge boundary states what the system cannot assess."""
        detector = GovernanceFlagDetector()
        flags = detector.check(
            {
                "role_changes": [{"type": "merge", "roles": ["Approver", "Processor"], "element_id": "task_1"}],
                "affected_element_ids": [],
            }
        )

        boundary = flags[0].knowledge_boundary.lower()
        assert "cannot" in boundary or "not" in boundary

    def test_no_flag_claims_full_enforcement(self) -> None:
        """No flag claims to fully enforce or clear a compliance constraint."""
        detector = GovernanceFlagDetector(
            regulated_elements={"task_approve": ["SOX Section 302"]},
        )
        flags = detector.check(
            {
                "role_changes": [
                    {"type": "merge", "roles": ["Approver", "Processor"]},
                    {"type": "automate", "element_id": "task_approve", "element_name": "Approval"},
                ],
                "affected_element_ids": [],
            }
        )

        for flag in flags:
            desc_lower = flag.description.lower()
            boundary_lower = flag.knowledge_boundary.lower()
            # Should not claim "compliant" or "approved"
            assert "is compliant" not in desc_lower
            assert "is approved" not in desc_lower
            # Knowledge boundary should acknowledge limitations
            assert "cannot" in boundary_lower or "not" in boundary_lower

    def test_regulatory_flag_has_knowledge_boundary(self) -> None:
        """Regulatory flag includes knowledge_boundary text."""
        detector = GovernanceFlagDetector(
            regulated_elements={"task_approve": ["SOX Section 302"]},
        )
        flags = detector.check(
            {
                "role_changes": [{"type": "automate", "element_id": "task_approve", "element_name": "Approval"}],
                "affected_element_ids": [],
            }
        )

        assert flags[0].knowledge_boundary
        assert "cannot" in flags[0].knowledge_boundary.lower()


class TestNoFalsePositives:
    """Scenario 4: No governance concerns produce no false positive flags."""

    def test_clean_suggestion_produces_no_flags(self) -> None:
        """Non-regulated, non-approval task produces empty flag list."""
        detector = GovernanceFlagDetector()
        flags = detector.check(
            {
                "role_changes": [
                    {
                        "type": "add",
                        "element_id": "task_data_entry",
                        "element_name": "Enter Data",
                    }
                ],
                "affected_element_ids": ["task_data_entry"],
            }
        )

        assert flags == []

    def test_empty_suggestion_produces_no_flags(self) -> None:
        """Suggestion with no role changes and no affected elements → empty."""
        detector = GovernanceFlagDetector()
        flags = detector.check(
            {
                "role_changes": [],
                "affected_element_ids": [],
            }
        )

        assert flags == []

    def test_reassign_non_approval_role_no_flag(self) -> None:
        """Reassigning a non-approval role does not trigger authorization flag."""
        detector = GovernanceFlagDetector()
        flags = detector.check(
            {
                "role_changes": [
                    {
                        "type": "reassign",
                        "element_id": "task_1",
                        "element_name": "Process Data",
                        "original_role": "Junior Analyst",
                        "new_role": "Senior Analyst",
                    }
                ],
                "affected_element_ids": [],
            }
        )

        assert flags == []


class TestAuthorizationChanges:
    """Authorization level change detection (not a BDD scenario but spec'd in technical notes)."""

    def test_demoting_approver_triggers_flag(self) -> None:
        """Changing from Approver to Processor triggers authorization_change flag."""
        detector = GovernanceFlagDetector()
        flags = detector.check(
            {
                "role_changes": [
                    {
                        "type": "reassign",
                        "element_id": "task_approve",
                        "element_name": "Final Sign-Off",
                        "original_role": "Approver",
                        "new_role": "Processor",
                    }
                ],
                "affected_element_ids": [],
            }
        )

        assert len(flags) == 1
        assert flags[0].flag_type == "authorization_change"
        assert "Approver" in flags[0].description
        assert "Processor" in flags[0].description

    def test_flag_to_dict(self) -> None:
        """GovernanceFlag serializes to dict correctly."""
        detector = GovernanceFlagDetector()
        flags = detector.check(
            {
                "role_changes": [{"type": "merge", "roles": ["Approver", "Processor"]}],
                "affected_element_ids": [],
            }
        )

        d = flags[0].to_dict()
        assert d["flag_type"] == "segregation_of_duties"
        assert isinstance(d["description"], str)
        assert d["regulation_reference"] is None
        assert isinstance(d["knowledge_boundary"], str)
