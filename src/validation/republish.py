"""POV republish and version diff engine (Story #361).

Regenerates a new POV version incorporating validation decisions,
computes structured diffs between versions, and provides BPMN
diff visualization data with color-coded change indicators.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ChangeType(StrEnum):
    """Type of change between POV versions."""

    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


# CSS color hints for BPMN diff visualization
DIFF_COLORS: dict[str, str] = {
    ChangeType.ADDED: "#28a745",      # green
    ChangeType.REMOVED: "#dc3545",    # red
    ChangeType.MODIFIED: "#ffc107",   # yellow
    ChangeType.UNCHANGED: "none",
}

# Fields compared for modification detection
COMPARED_FIELDS = frozenset({
    "name",
    "confidence_score",
    "evidence_grade",
    "brightness_classification",
    "element_type",
    "evidence_count",
})


@dataclass
class ElementSnapshot:
    """Snapshot of a process element for diff comparison."""

    element_id: str
    name: str
    element_type: str
    confidence_score: float = 0.0
    evidence_grade: str = "U"
    brightness_classification: str = "DARK"
    evidence_count: int = 0
    evidence_ids: list[str] = field(default_factory=list)
    metadata: dict[str, object] | None = None


@dataclass
class ElementChange:
    """A single change between two POV versions."""

    element_id: str
    element_name: str
    change_type: ChangeType
    changed_fields: list[str] = field(default_factory=list)
    color: str = "none"
    css_class: str = "unchanged"
    prior_values: dict[str, object] = field(default_factory=dict)
    current_values: dict[str, object] = field(default_factory=dict)


@dataclass
class VersionDiff:
    """Structured diff between two POV versions."""

    v1_id: str
    v2_id: str
    added: list[ElementChange] = field(default_factory=list)
    removed: list[ElementChange] = field(default_factory=list)
    modified: list[ElementChange] = field(default_factory=list)
    unchanged_count: int = 0
    dark_shrink_rate: float | None = None

    @property
    def total_changes(self) -> int:
        return len(self.added) + len(self.removed) + len(self.modified)


def compute_diff(
    v1_elements: list[ElementSnapshot],
    v2_elements: list[ElementSnapshot],
    v1_id: str = "",
    v2_id: str = "",
) -> VersionDiff:
    """Compute a structured diff between two POV versions.

    Uses element name as the matching key (element_id changes between versions).

    Args:
        v1_elements: Elements from the prior version.
        v2_elements: Elements from the current version.
        v1_id: Version 1 identifier.
        v2_id: Version 2 identifier.

    Returns:
        VersionDiff with categorized changes.
    """
    v1_by_name: dict[str, ElementSnapshot] = {e.name: e for e in v1_elements}
    v2_by_name: dict[str, ElementSnapshot] = {e.name: e for e in v2_elements}

    v1_names = set(v1_by_name.keys())
    v2_names = set(v2_by_name.keys())

    diff = VersionDiff(v1_id=v1_id, v2_id=v2_id)

    # Added elements: in v2 but not v1
    for name in sorted(v2_names - v1_names):
        el = v2_by_name[name]
        diff.added.append(ElementChange(
            element_id=el.element_id,
            element_name=name,
            change_type=ChangeType.ADDED,
            color=DIFF_COLORS[ChangeType.ADDED],
            css_class="diff-added",
        ))

    # Removed elements: in v1 but not v2
    for name in sorted(v1_names - v2_names):
        el = v1_by_name[name]
        diff.removed.append(ElementChange(
            element_id=el.element_id,
            element_name=name,
            change_type=ChangeType.REMOVED,
            color=DIFF_COLORS[ChangeType.REMOVED],
            css_class="diff-removed",
        ))

    # Modified or unchanged: in both
    for name in sorted(v1_names & v2_names):
        v1_el = v1_by_name[name]
        v2_el = v2_by_name[name]

        changed_fields: list[str] = []
        prior_values: dict[str, object] = {}
        current_values: dict[str, object] = {}

        for field_name in COMPARED_FIELDS:
            v1_val = getattr(v1_el, field_name, None)
            v2_val = getattr(v2_el, field_name, None)
            if v1_val != v2_val:
                changed_fields.append(field_name)
                prior_values[field_name] = v1_val
                current_values[field_name] = v2_val

        if changed_fields:
            diff.modified.append(ElementChange(
                element_id=v2_el.element_id,
                element_name=name,
                change_type=ChangeType.MODIFIED,
                changed_fields=sorted(changed_fields),
                color=DIFF_COLORS[ChangeType.MODIFIED],
                css_class="diff-modified",
                prior_values=prior_values,
                current_values=current_values,
            ))
        else:
            diff.unchanged_count += 1

    # Compute dark-room shrink rate if applicable
    v1_dark = sum(1 for e in v1_elements if e.brightness_classification == "DARK")
    v2_dark = sum(1 for e in v2_elements if e.brightness_classification == "DARK")
    if v1_dark > 0:
        diff.dark_shrink_rate = ((v1_dark - v2_dark) / v1_dark) * 100
    elif v2_dark == 0:
        diff.dark_shrink_rate = 0.0

    return diff


def apply_decisions_to_elements(
    source_elements: list[ElementSnapshot],
    decisions: list[dict[str, object]],
) -> list[ElementSnapshot]:
    """Apply validation decisions to produce elements for a new POV version.

    Args:
        source_elements: Elements from the prior POV version.
        decisions: List of decision dicts with keys:
            element_id, action (confirm/correct/reject/defer), payload.

    Returns:
        New list of ElementSnapshot for the republished version.
    """
    elements_by_name: dict[str, ElementSnapshot] = {e.name: e for e in source_elements}
    rejected_names: set[str] = set()

    # Group decisions by element name (matched via metadata or name)
    decision_by_element: dict[str, list[dict[str, object]]] = {}
    for dec in decisions:
        el_id = str(dec.get("element_id", ""))
        # Find element by ID
        matched_name = None
        for el in source_elements:
            if el.element_id == el_id:
                matched_name = el.name
                break
        if matched_name:
            decision_by_element.setdefault(matched_name, []).append(dec)

    # Process decisions
    for name, decs in decision_by_element.items():
        for dec in decs:
            action = str(dec.get("action", ""))
            payload = dec.get("payload") or {}

            if action == "reject":
                rejected_names.add(name)
            elif action == "correct" and isinstance(payload, dict):
                el = elements_by_name.get(name)
                if el:
                    # Apply corrections from payload
                    if "name" in payload:
                        new_name = str(payload["name"])
                        if new_name in elements_by_name and new_name != name:
                            msg = f"Cannot rename '{name}' to '{new_name}': element with that name already exists"
                            raise ValueError(msg)
                        elements_by_name[new_name] = ElementSnapshot(
                            element_id=el.element_id,
                            name=new_name,
                            element_type=el.element_type,
                            confidence_score=el.confidence_score,
                            evidence_grade=el.evidence_grade,
                            brightness_classification=el.brightness_classification,
                            evidence_count=el.evidence_count,
                            evidence_ids=list(el.evidence_ids),
                            metadata=dict(el.metadata) if el.metadata else None,
                        )
                        del elements_by_name[name]
                    # Apply other field corrections
                    target = elements_by_name.get(str(payload.get("name", name)), elements_by_name.get(name))
                    if target:
                        for field_name in ("confidence_score", "evidence_grade", "brightness_classification"):
                            if field_name in payload:
                                setattr(target, field_name, payload[field_name])

    # Build result: exclude rejected, include rest
    result: list[ElementSnapshot] = []
    for name, el in elements_by_name.items():
        if name not in rejected_names:
            result.append(el)

    return result
