"""Governance flag detector for LLM suggestions (Story #381).

Detects governance implications when suggestions involve role changes:
- Segregation of duties risks (merging roles that should be separate)
- Regulatory compliance impacts (automating regulated activities)
- Authorization level changes (demoting approvers)

Flags are returned as dicts suitable for storing in
AlternativeSuggestion.governance_flags (JSONB).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from src.core.governance.templates import (
    AUTHORIZATION_DESCRIPTION,
    AUTHORIZATION_KNOWLEDGE_BOUNDARY,
    REGULATORY_DESCRIPTION,
    REGULATORY_KNOWLEDGE_BOUNDARY,
    SOD_DESCRIPTION,
    SOD_KNOWLEDGE_BOUNDARY,
)


@dataclass(frozen=True)
class GovernanceFlag:
    """A governance concern detected for an LLM suggestion."""

    flag_type: str
    description: str
    regulation_reference: str | None
    knowledge_boundary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Default roles that require segregation (approver vs processor/executor)
DEFAULT_SOD_PAIRS: list[tuple[str, str]] = [
    ("approver", "processor"),
    ("approver", "executor"),
    ("reviewer", "submitter"),
    ("auditor", "operator"),
]


class GovernanceFlagDetector:
    """Detects governance implications in LLM suggestions.

    Args:
        sod_pairs: Pairs of role names that require segregation.
                   Defaults to common financial/compliance patterns.
        regulated_elements: Dict mapping element_id to list of regulation names.
        approval_roles: Set of role names that are approval-gated.
    """

    def __init__(
        self,
        sod_pairs: list[tuple[str, str]] | None = None,
        regulated_elements: dict[str, list[str]] | None = None,
        approval_roles: set[str] | None = None,
    ) -> None:
        self.sod_pairs = sod_pairs or DEFAULT_SOD_PAIRS
        self.regulated_elements = regulated_elements or {}
        self.approval_roles = approval_roles or {"approver", "reviewer", "signatory"}

    def check(
        self,
        suggestion_data: dict[str, Any],
    ) -> list[GovernanceFlag]:
        """Run all governance checks against a suggestion.

        Args:
            suggestion_data: Dict containing:
                - role_changes: list of {type, roles, element_id, element_name,
                                         original_role, new_role}
                - affected_element_ids: list of element IDs the suggestion modifies

        Returns:
            List of governance flags. Empty if no concerns detected.
        """
        flags: list[GovernanceFlag] = []

        role_changes = suggestion_data.get("role_changes", [])
        affected_element_ids = suggestion_data.get("affected_element_ids", [])

        flags.extend(self._check_sod(role_changes))
        flags.extend(self._check_regulatory(role_changes, affected_element_ids))
        flags.extend(self._check_authorization(role_changes))

        return flags

    def _check_sod(self, role_changes: list[dict[str, Any]]) -> list[GovernanceFlag]:
        """Check for segregation of duties violations from role merges."""
        flags: list[GovernanceFlag] = []
        for change in role_changes:
            if change.get("type") != "merge":
                continue
            roles = change.get("roles", [])
            if len(roles) < 2:
                continue

            role_set = {r.lower() for r in roles}
            for role_a, role_b in self.sod_pairs:
                if role_a.lower() in role_set and role_b.lower() in role_set:
                    flags.append(
                        GovernanceFlag(
                            flag_type="segregation_of_duties",
                            description=SOD_DESCRIPTION.format(role_a=roles[0], role_b=roles[1]),
                            regulation_reference=None,
                            knowledge_boundary=SOD_KNOWLEDGE_BOUNDARY,
                        )
                    )
                    break

        return flags

    def _check_regulatory(
        self,
        role_changes: list[dict[str, Any]],
        affected_element_ids: list[str],
    ) -> list[GovernanceFlag]:
        """Check for regulatory compliance impacts from automation."""
        flags: list[GovernanceFlag] = []

        # Check role changes that automate (remove human actor)
        for change in role_changes:
            if change.get("type") != "automate":
                continue
            element_id = change.get("element_id", "")
            element_name = change.get("element_name", element_id)
            regulations = self.regulated_elements.get(element_id, [])
            for reg in regulations:
                flags.append(
                    GovernanceFlag(
                        flag_type="regulatory_compliance",
                        description=REGULATORY_DESCRIPTION.format(
                            element_name=element_name,
                            regulation=reg,
                        ),
                        regulation_reference=reg,
                        knowledge_boundary=REGULATORY_KNOWLEDGE_BOUNDARY,
                    )
                )

        # Check affected elements for regulatory tags
        for eid in affected_element_ids:
            regulations = self.regulated_elements.get(eid, [])
            for reg in regulations:
                # Avoid duplicate if already flagged via role change
                if not any(f.regulation_reference == reg and f.flag_type == "regulatory_compliance" for f in flags):
                    flags.append(
                        GovernanceFlag(
                            flag_type="regulatory_compliance",
                            description=REGULATORY_DESCRIPTION.format(
                                element_name=eid,
                                regulation=reg,
                            ),
                            regulation_reference=reg,
                            knowledge_boundary=REGULATORY_KNOWLEDGE_BOUNDARY,
                        )
                    )

        return flags

    def _check_authorization(self, role_changes: list[dict[str, Any]]) -> list[GovernanceFlag]:
        """Check for authorization level changes (demoting approvers)."""
        flags: list[GovernanceFlag] = []
        for change in role_changes:
            if change.get("type") != "reassign":
                continue
            original_role = change.get("original_role", "")
            new_role = change.get("new_role", "")
            if original_role.lower() in self.approval_roles and new_role.lower() not in self.approval_roles:
                element_name = change.get("element_name", change.get("element_id", ""))
                flags.append(
                    GovernanceFlag(
                        flag_type="authorization_change",
                        description=AUTHORIZATION_DESCRIPTION.format(
                            element_name=element_name,
                            original_role=original_role,
                            new_role=new_role,
                        ),
                        regulation_reference=None,
                        knowledge_boundary=AUTHORIZATION_KNOWLEDGE_BOUNDARY,
                    )
                )

        return flags
