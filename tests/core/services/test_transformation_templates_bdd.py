"""BDD tests for transformation templates library (Story #376).

Tests the four template analysis functions against process model elements.
"""

from __future__ import annotations

from src.core.services.transformation_templates import (
    ProcessElement,
    SuggestionStatus,
    TemplateSuggestion,
    TemplateType,
    analyze_automate_gateway,
    analyze_consolidate_tasks,
    analyze_remove_control,
    analyze_shift_decision,
    apply_all_templates,
    get_template_registry,
)

# -- Scenario 1: Consolidate Adjacent Tasks --


class TestConsolidateAdjacentTasks:
    """Given the template 'Consolidate adjacent tasks in same swim lane'."""

    def test_three_adjacent_tasks_same_lane_and_performer(self) -> None:
        """3 adjacent tasks in the same lane performed by the same role → 2 pairs."""
        elements = [
            ProcessElement(
                id="t1",
                name="Review Application",
                element_type="task",
                lane="Processing",
                performer="Analyst",
                sequence_position=1,
            ),
            ProcessElement(
                id="t2",
                name="Validate Documents",
                element_type="task",
                lane="Processing",
                performer="Analyst",
                sequence_position=2,
            ),
            ProcessElement(
                id="t3",
                name="Check References",
                element_type="task",
                lane="Processing",
                performer="Analyst",
                sequence_position=3,
            ),
        ]

        suggestions = analyze_consolidate_tasks(elements)

        assert len(suggestions) == 2
        assert suggestions[0].element_ids == ["t1", "t2"]
        assert suggestions[1].element_ids == ["t2", "t3"]
        assert all(s.template_type == TemplateType.CONSOLIDATE_TASKS for s in suggestions)
        assert all(s.status == SuggestionStatus.PENDING for s in suggestions)

    def test_each_candidate_has_element_ids_and_rationale(self) -> None:
        """Each candidate is returned with element_ids and rationale."""
        elements = [
            ProcessElement(
                id="t1",
                name="Task A",
                element_type="task",
                lane="Lane1",
                performer="Role1",
                sequence_position=1,
            ),
            ProcessElement(
                id="t2",
                name="Task B",
                element_type="task",
                lane="Lane1",
                performer="Role1",
                sequence_position=2,
            ),
        ]

        suggestions = analyze_consolidate_tasks(elements)

        assert len(suggestions) == 1
        s = suggestions[0]
        assert s.element_ids == ["t1", "t2"]
        assert "Task A" in s.rationale
        assert "Task B" in s.rationale
        assert "Lane1" in s.rationale
        assert s.id  # Has a UUID

    def test_different_lanes_no_consolidation(self) -> None:
        """Tasks in different lanes should not be consolidated."""
        elements = [
            ProcessElement(
                id="t1",
                name="Task A",
                element_type="task",
                lane="Lane1",
                performer="Analyst",
                sequence_position=1,
            ),
            ProcessElement(
                id="t2",
                name="Task B",
                element_type="task",
                lane="Lane2",
                performer="Analyst",
                sequence_position=2,
            ),
        ]

        suggestions = analyze_consolidate_tasks(elements)
        assert len(suggestions) == 0

    def test_different_performers_no_consolidation(self) -> None:
        """Tasks with different performers should not be consolidated."""
        elements = [
            ProcessElement(
                id="t1",
                name="Task A",
                element_type="task",
                lane="Lane1",
                performer="Analyst",
                sequence_position=1,
            ),
            ProcessElement(
                id="t2",
                name="Task B",
                element_type="task",
                lane="Lane1",
                performer="Manager",
                sequence_position=2,
            ),
        ]

        suggestions = analyze_consolidate_tasks(elements)
        assert len(suggestions) == 0

    def test_non_tasks_are_excluded(self) -> None:
        """Only task elements are considered for consolidation."""
        elements = [
            ProcessElement(
                id="g1",
                name="Check",
                element_type="gateway",
                lane="Lane1",
                performer="Analyst",
                sequence_position=1,
            ),
            ProcessElement(
                id="t1",
                name="Task A",
                element_type="task",
                lane="Lane1",
                performer="Analyst",
                sequence_position=2,
            ),
        ]

        suggestions = analyze_consolidate_tasks(elements)
        assert len(suggestions) == 0

    def test_unsorted_elements_sorted_by_sequence(self) -> None:
        """Elements are sorted by sequence_position before analysis."""
        elements = [
            ProcessElement(
                id="t2",
                name="Task B",
                element_type="task",
                lane="Lane1",
                performer="Analyst",
                sequence_position=3,
            ),
            ProcessElement(
                id="t1",
                name="Task A",
                element_type="task",
                lane="Lane1",
                performer="Analyst",
                sequence_position=1,
            ),
        ]

        suggestions = analyze_consolidate_tasks(elements)
        # Not adjacent (positions 1 and 3), but they ARE the only tasks
        # so after sorting they are adjacent in the task list
        assert len(suggestions) == 1
        assert suggestions[0].element_ids == ["t1", "t2"]


# -- Scenario 2: Automate Gateway --


class TestAutomateGateway:
    """Given the template 'Automate gateway where inputs are system-provided'."""

    def test_all_system_inputs_identified(self) -> None:
        """Gateway with all system inputs is an automation candidate."""
        elements = [
            ProcessElement(
                id="gw1",
                name="Route Decision",
                element_type="gateway",
                input_sources=["System API", "Database Query"],
            ),
        ]

        suggestions = analyze_automate_gateway(elements)

        assert len(suggestions) == 1
        s = suggestions[0]
        assert s.element_ids == ["gw1"]
        assert s.template_type == TemplateType.AUTOMATE_GATEWAY
        assert "System API" in s.rationale
        assert "Database Query" in s.rationale

    def test_mixed_inputs_not_automated(self) -> None:
        """Gateway with both human and system inputs is NOT a candidate."""
        elements = [
            ProcessElement(
                id="gw1",
                name="Approval",
                element_type="gateway",
                input_sources=["System API", "Manager judgment"],
            ),
        ]

        suggestions = analyze_automate_gateway(elements)
        assert len(suggestions) == 0

    def test_no_inputs_skipped(self) -> None:
        """Gateway with no input sources is skipped."""
        elements = [
            ProcessElement(
                id="gw1",
                name="Merge",
                element_type="gateway",
                input_sources=[],
            ),
        ]

        suggestions = analyze_automate_gateway(elements)
        assert len(suggestions) == 0

    def test_integration_keyword_match(self) -> None:
        """All system indicator keywords are recognized."""
        elements = [
            ProcessElement(
                id="gw1",
                name="Check",
                element_type="gateway",
                input_sources=["Automated check", "Integration feed"],
            ),
        ]

        suggestions = analyze_automate_gateway(elements)
        assert len(suggestions) == 1

    def test_non_gateways_excluded(self) -> None:
        """Only gateway elements are analyzed."""
        elements = [
            ProcessElement(
                id="t1",
                name="Task",
                element_type="task",
                input_sources=["System API"],
            ),
        ]

        suggestions = analyze_automate_gateway(elements)
        assert len(suggestions) == 0


# -- Scenario 3: Shift Decision Boundary --


class TestShiftDecisionBoundary:
    """Given the template 'Shift decision boundary'."""

    def test_human_with_system_inputs_shifts(self) -> None:
        """Human decision point with system inputs recommends shift."""
        elements = [
            ProcessElement(
                id="gw1",
                name="Risk Assessment",
                element_type="gateway",
                autonomy_level="human",
                input_sources=["System risk model", "Database score"],
            ),
        ]

        suggestions = analyze_shift_decision(elements)

        assert len(suggestions) == 1
        s = suggestions[0]
        assert s.element_ids == ["gw1"]
        assert "system_assisted" in s.rationale
        assert s.template_type == TemplateType.SHIFT_DECISION

    def test_already_autonomous_no_suggestion(self) -> None:
        """Already autonomous elements are not suggested."""
        elements = [
            ProcessElement(
                id="gw1",
                name="Auto Route",
                element_type="gateway",
                autonomy_level="autonomous",
                input_sources=["System API"],
            ),
        ]

        suggestions = analyze_shift_decision(elements)
        assert len(suggestions) == 0

    def test_human_task_also_considered(self) -> None:
        """Tasks (not just gateways) at human level are candidates."""
        elements = [
            ProcessElement(
                id="t1",
                name="Manual Review",
                element_type="task",
                autonomy_level="human",
                input_sources=["API data feed"],
            ),
        ]

        suggestions = analyze_shift_decision(elements)
        assert len(suggestions) == 1

    def test_events_excluded(self) -> None:
        """Event elements are not considered for decision shift."""
        elements = [
            ProcessElement(
                id="e1",
                name="Timer",
                element_type="event",
                autonomy_level="human",
            ),
        ]

        suggestions = analyze_shift_decision(elements)
        assert len(suggestions) == 0


# -- Scenario 4: Remove Control --


class TestRemoveControl:
    """Given the template 'Remove control and assess impact'."""

    def test_low_risk_control_identified(self) -> None:
        """Low compliance risk controls are candidates for removal."""
        elements = [
            ProcessElement(
                id="c1",
                name="Duplicate Check",
                element_type="control",
                is_control=True,
                compliance_risk="low",
            ),
        ]

        suggestions = analyze_remove_control(elements)

        assert len(suggestions) == 1
        s = suggestions[0]
        assert s.element_ids == ["c1"]
        assert "low compliance risk" in s.rationale
        assert s.template_type == TemplateType.REMOVE_CONTROL

    def test_high_risk_control_not_suggested(self) -> None:
        """High compliance risk controls are NOT candidates."""
        elements = [
            ProcessElement(
                id="c1",
                name="SOX Control",
                element_type="control",
                is_control=True,
                compliance_risk="high",
            ),
        ]

        suggestions = analyze_remove_control(elements)
        assert len(suggestions) == 0

    def test_medium_risk_not_suggested(self) -> None:
        """Medium compliance risk controls are NOT candidates."""
        elements = [
            ProcessElement(
                id="c1",
                name="Audit Check",
                element_type="control",
                is_control=True,
                compliance_risk="medium",
            ),
        ]

        suggestions = analyze_remove_control(elements)
        assert len(suggestions) == 0

    def test_non_control_elements_excluded(self) -> None:
        """Elements that are not controls are excluded regardless of risk."""
        elements = [
            ProcessElement(
                id="t1",
                name="Task",
                element_type="task",
                is_control=False,
                compliance_risk="low",
            ),
        ]

        suggestions = analyze_remove_control(elements)
        assert len(suggestions) == 0


# -- Apply All Templates --


class TestApplyAllTemplates:
    """Run all four templates together."""

    def test_mixed_process_model(self) -> None:
        """A mixed process model produces suggestions from multiple templates."""
        elements = [
            # Consolidation candidates
            ProcessElement(
                id="t1",
                name="Review",
                element_type="task",
                lane="Ops",
                performer="Analyst",
                sequence_position=1,
            ),
            ProcessElement(
                id="t2",
                name="Validate",
                element_type="task",
                lane="Ops",
                performer="Analyst",
                sequence_position=2,
            ),
            # Automate gateway candidate
            ProcessElement(
                id="gw1",
                name="Auto Route",
                element_type="gateway",
                input_sources=["System API", "Database"],
            ),
            # Low-risk control
            ProcessElement(
                id="c1",
                name="Low Check",
                element_type="control",
                is_control=True,
                compliance_risk="low",
            ),
        ]

        suggestions = apply_all_templates(elements)

        template_types = {s.template_type for s in suggestions}
        assert TemplateType.CONSOLIDATE_TASKS in template_types
        assert TemplateType.AUTOMATE_GATEWAY in template_types
        assert TemplateType.REMOVE_CONTROL in template_types
        assert len(suggestions) >= 3

    def test_empty_elements_no_suggestions(self) -> None:
        """Empty elements list produces no suggestions."""
        suggestions = apply_all_templates([])
        assert suggestions == []


# -- Template Registry --


class TestTemplateRegistry:
    """Template registry returns all built-in templates."""

    def test_four_templates_registered(self) -> None:
        registry = get_template_registry()
        assert len(registry) == 4

    def test_all_types_present(self) -> None:
        registry = get_template_registry()
        types = {t.template_type for t in registry}
        assert types == {
            TemplateType.CONSOLIDATE_TASKS,
            TemplateType.AUTOMATE_GATEWAY,
            TemplateType.SHIFT_DECISION,
            TemplateType.REMOVE_CONTROL,
        }

    def test_to_dict_serialization(self) -> None:
        registry = get_template_registry()
        for t in registry:
            d = t.to_dict()
            assert "template_type" in d
            assert "name" in d
            assert "description" in d


# -- TemplateSuggestion --


class TestTemplateSuggestion:
    """TemplateSuggestion dataclass tests."""

    def test_default_status_is_pending(self) -> None:
        s = TemplateSuggestion(
            id="test-id",
            template_type=TemplateType.CONSOLIDATE_TASKS,
            element_ids=["t1", "t2"],
            rationale="Test rationale",
        )
        assert s.status == SuggestionStatus.PENDING

    def test_to_dict(self) -> None:
        s = TemplateSuggestion(
            id="test-id",
            template_type=TemplateType.AUTOMATE_GATEWAY,
            element_ids=["gw1"],
            rationale="Can be automated",
        )
        d = s.to_dict()
        assert d["id"] == "test-id"
        assert d["template_type"] == "automate_gateway"
        assert d["element_ids"] == ["gw1"]
        assert d["rationale"] == "Can be automated"
        assert d["status"] == "pending"
