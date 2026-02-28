"""Correlation Engine: links canonical activity events to business cases.

The engine runs in two passes:
1. Deterministic — regex-based extraction of case/ticket IDs from window titles.
2. Assisted — probabilistic scoring using time-window proximity, role alignment,
   and system context when a deterministic match cannot be found.

Events that cannot be linked to a specific case are aggregated to a role cohort
by RoleAssociator. CorrelationDiagnostics produces daily quality reports and
surfaces uncertainty items for analyst review.
"""

from src.taskmining.correlation.assisted import AssistedLinker
from src.taskmining.correlation.deterministic import DeterministicLinker
from src.taskmining.correlation.diagnostics import CorrelationDiagnostics
from src.taskmining.correlation.role_association import RoleAssociator

__all__ = [
    "AssistedLinker",
    "CorrelationDiagnostics",
    "DeterministicLinker",
    "RoleAssociator",
]
