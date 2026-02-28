"""Transformation templates library (Story #376).

Pre-built templates that analyze as-is process models and suggest
candidate modifications to consultants. Four initial templates:

1. Consolidate adjacent tasks (same lane, same performer)
2. Automate gateway (all inputs system-provided)
3. Shift decision boundary (human → system-assisted → autonomous)
4. Remove control and assess impact
"""

from __future__ import annotations

import enum
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class TemplateType(enum.StrEnum):
    """Built-in transformation template types."""

    CONSOLIDATE_TASKS = "consolidate_tasks"
    AUTOMATE_GATEWAY = "automate_gateway"
    SHIFT_DECISION = "shift_decision"
    REMOVE_CONTROL = "remove_control"


class SuggestionStatus(enum.StrEnum):
    """Lifecycle status of a template suggestion.

    Distinct from SuggestionDisposition (models/simulation.py) which includes
    MODIFIED and is tied to the AlternativeSuggestion ORM model. This enum is
    for in-memory template suggestions that are not persisted to the database.
    """

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class TemplateSuggestion:
    """A suggestion produced by applying a template to a process model."""

    id: str
    template_type: str
    element_ids: list[str]
    rationale: str
    status: str = SuggestionStatus.PENDING

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "template_type": self.template_type,
            "element_ids": self.element_ids,
            "rationale": self.rationale,
            "status": self.status,
        }


@dataclass(frozen=True)
class TemplateDefinition:
    """Definition of a transformation template."""

    template_type: str
    name: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_type": self.template_type,
            "name": self.name,
            "description": self.description,
        }


# Registry of built-in templates
TEMPLATE_REGISTRY: list[TemplateDefinition] = [
    TemplateDefinition(
        template_type=TemplateType.CONSOLIDATE_TASKS,
        name="Consolidate adjacent tasks",
        description="Identify adjacent tasks in the same swim lane performed by the same role that can be consolidated into a single activity.",
    ),
    TemplateDefinition(
        template_type=TemplateType.AUTOMATE_GATEWAY,
        name="Automate gateway",
        description="Identify gateways where all decision inputs are sourced from system integrations, making them candidates for automated routing.",
    ),
    TemplateDefinition(
        template_type=TemplateType.SHIFT_DECISION,
        name="Shift decision boundary",
        description="Identify human decision points that could be shifted toward system-assisted or fully autonomous operation.",
    ),
    TemplateDefinition(
        template_type=TemplateType.REMOVE_CONTROL,
        name="Remove control and assess impact",
        description="Identify controls whose removal would have minimal compliance risk while improving cycle time.",
    ),
]


@dataclass
class ProcessElement:
    """Simplified process element for template analysis."""

    id: str
    name: str
    element_type: str  # task, gateway, control, event
    lane: str = ""
    performer: str = ""
    input_sources: list[str] = field(default_factory=list)
    autonomy_level: str = "human"  # human, system_assisted, autonomous
    is_control: bool = False
    compliance_risk: str = "low"  # low, medium, high
    sequence_position: int = 0


def analyze_consolidate_tasks(elements: list[ProcessElement]) -> list[TemplateSuggestion]:
    """Template 1: Find adjacent tasks in the same lane with same performer.

    Adjacent tasks by the same performer in the same lane can often be
    merged into a single activity, reducing handoff overhead.
    """
    # Filter to tasks only, sorted by sequence
    tasks = sorted(
        [e for e in elements if e.element_type == "task"],
        key=lambda e: e.sequence_position,
    )

    suggestions: list[TemplateSuggestion] = []
    i = 0
    while i < len(tasks) - 1:
        current = tasks[i]
        next_task = tasks[i + 1]

        if current.lane == next_task.lane and current.performer == next_task.performer:
            suggestions.append(
                TemplateSuggestion(
                    id=str(uuid.uuid4()),
                    template_type=TemplateType.CONSOLIDATE_TASKS,
                    element_ids=[current.id, next_task.id],
                    rationale=(
                        f"Tasks '{current.name}' and '{next_task.name}' are adjacent in lane "
                        f"'{current.lane}' and performed by '{current.performer}'. "
                        f"Consider consolidating to reduce handoff overhead."
                    ),
                )
            )
        i += 1

    return suggestions


def analyze_automate_gateway(elements: list[ProcessElement]) -> list[TemplateSuggestion]:
    """Template 2: Find gateways where all inputs are system-provided.

    If every input to a gateway comes from a system integration (not
    human judgment), the gateway can be automated.
    """
    gateways = [e for e in elements if e.element_type == "gateway"]

    suggestions: list[TemplateSuggestion] = []
    for gw in gateways:
        if not gw.input_sources:
            continue

        system_indicators = {"system", "api", "database", "automated", "integration"}
        all_system = all(any(ind in src.lower() for ind in system_indicators) for src in gw.input_sources)

        if all_system:
            suggestions.append(
                TemplateSuggestion(
                    id=str(uuid.uuid4()),
                    template_type=TemplateType.AUTOMATE_GATEWAY,
                    element_ids=[gw.id],
                    rationale=(
                        f"Gateway '{gw.name}' has all inputs sourced from system integrations: "
                        f"{', '.join(gw.input_sources)}. This gateway can be fully automated."
                    ),
                )
            )

    return suggestions


def analyze_shift_decision(elements: list[ProcessElement]) -> list[TemplateSuggestion]:
    """Template 3: Find human decision points that could shift toward autonomy.

    Identifies gateways/tasks at 'human' autonomy level that have potential
    to shift to system_assisted or autonomous.
    """
    candidates = [e for e in elements if e.element_type in ("gateway", "task") and e.autonomy_level == "human"]

    suggestions: list[TemplateSuggestion] = []
    for elem in candidates:
        target_level = "system_assisted"  # conservative: always recommend system_assisted first

        if elem.autonomy_level != target_level:
            suggestions.append(
                TemplateSuggestion(
                    id=str(uuid.uuid4()),
                    template_type=TemplateType.SHIFT_DECISION,
                    element_ids=[elem.id],
                    rationale=(
                        f"'{elem.name}' is currently at '{elem.autonomy_level}' autonomy level. "
                        f"Consider shifting to '{target_level}' to reduce manual decision-making."
                    ),
                )
            )

    return suggestions


def analyze_remove_control(elements: list[ProcessElement]) -> list[TemplateSuggestion]:
    """Template 4: Find controls with low compliance risk for potential removal.

    Controls marked as low compliance risk are candidates for removal
    to improve cycle time without significant regulatory exposure.
    """
    controls = [e for e in elements if e.is_control and e.compliance_risk == "low"]

    suggestions: list[TemplateSuggestion] = []
    for ctrl in controls:
        suggestions.append(
            TemplateSuggestion(
                id=str(uuid.uuid4()),
                template_type=TemplateType.REMOVE_CONTROL,
                element_ids=[ctrl.id],
                rationale=(
                    f"Control '{ctrl.name}' has low compliance risk. "
                    f"Removing it would improve cycle time with minimal regulatory exposure."
                ),
            )
        )

    return suggestions


def apply_all_templates(elements: list[ProcessElement]) -> list[TemplateSuggestion]:
    """Run all four templates against a process model."""
    suggestions: list[TemplateSuggestion] = []
    suggestions.extend(analyze_consolidate_tasks(elements))
    suggestions.extend(analyze_automate_gateway(elements))
    suggestions.extend(analyze_shift_decision(elements))
    suggestions.extend(analyze_remove_control(elements))
    return suggestions


def get_template_registry() -> list[TemplateDefinition]:
    """Return the list of available transformation templates."""
    return TEMPLATE_REGISTRY
