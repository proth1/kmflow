"""Policy engine for data governance enforcement.

Loads YAML policy definitions and evaluates them against DataCatalogEntry
instances to surface violations. Supports retention, classification,
quality SLA, and naming convention policy types.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.core.models import DataCatalogEntry, DataLayer

logger = logging.getLogger(__name__)

# Default policies bundled with the module
_DEFAULT_POLICY_FILE = Path(__file__).parent / "policies" / "default.yaml"


@dataclass
class PolicyViolation:
    """A single policy violation detected against a catalog entry.

    Attributes:
        policy_name: Identifier of the violated policy rule.
        severity: One of 'error', 'warning', 'info'.
        message: Human-readable description of the violation.
        entry_id: The catalog entry that violated the policy.
    """

    policy_name: str
    severity: str
    message: str
    entry_id: uuid.UUID


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load and parse a YAML policy file."""
    with path.open("r") as fh:
        return yaml.safe_load(fh) or {}


class PolicyEngine:
    """Evaluates governance policies against DataCatalogEntry records.

    Policies are loaded from YAML files. The default policy set ships
    with the module at ``policies/default.yaml``. Custom policy files
    may be loaded on top of (or instead of) the defaults.

    Policy types supported:
    - ``retention``: Maximum retention_days per layer.
    - ``classification_required``: Entries must have an explicit classification.
    - ``quality_sla_required``: Entries must have quality_sla set.
    - ``naming_convention``: dataset_name must match a regex pattern.
    """

    def __init__(self, policy_file: Path | None = None) -> None:
        """Initialise the engine with an optional custom policy file.

        If *policy_file* is None, the bundled default.yaml is used.
        """
        path = policy_file or _DEFAULT_POLICY_FILE
        self._raw: dict[str, Any] = _load_yaml(path)
        self._policy_file = path
        logger.debug("Loaded policies from %s", path)

    @property
    def policies(self) -> dict[str, Any]:
        """Return the raw policy dictionary."""
        return self._raw

    @property
    def policy_file(self) -> Path:
        """Return the path of the loaded policy file."""
        return self._policy_file

    def evaluate(self, entry: DataCatalogEntry) -> list[PolicyViolation]:
        """Evaluate all active policies against a single catalog entry.

        Args:
            entry: The DataCatalogEntry to check.

        Returns:
            A list of PolicyViolation objects (empty means compliant).
        """
        violations: list[PolicyViolation] = []

        violations.extend(self._check_retention(entry))
        violations.extend(self._check_classification_required(entry))
        violations.extend(self._check_quality_sla_required(entry))
        violations.extend(self._check_naming_convention(entry))

        return violations

    # ------------------------------------------------------------------
    # Individual policy checkers
    # ------------------------------------------------------------------

    def _check_retention(self, entry: DataCatalogEntry) -> list[PolicyViolation]:
        """Check retention_days against per-layer maximums."""
        violations: list[PolicyViolation] = []
        retention_cfg: dict[str, Any] = self._raw.get("retention", {})

        if not retention_cfg.get("enabled", True):
            return violations

        layer_limits: dict[str, int | None] = retention_cfg.get("max_days_by_layer", {})
        layer_key = entry.layer.value  # 'bronze', 'silver', 'gold'
        max_days = layer_limits.get(layer_key)

        if max_days is None:
            # No limit configured for this layer (e.g. gold = unlimited)
            return violations

        if entry.retention_days is not None and entry.retention_days > max_days:
            violations.append(
                PolicyViolation(
                    policy_name="retention",
                    severity=retention_cfg.get("severity", "warning"),
                    message=(
                        f"Dataset '{entry.dataset_name}' has retention_days="
                        f"{entry.retention_days} which exceeds the {layer_key} "
                        f"layer maximum of {max_days} days."
                    ),
                    entry_id=entry.id,
                )
            )

        return violations

    def _check_classification_required(
        self, entry: DataCatalogEntry
    ) -> list[PolicyViolation]:
        """Check that classification is set for layers that require it."""
        violations: list[PolicyViolation] = []
        cfg: dict[str, Any] = self._raw.get("classification_required", {})

        if not cfg.get("enabled", True):
            return violations

        required_for: list[str] = cfg.get("layers", [])
        if entry.layer.value not in required_for:
            return violations

        # classification has a DB-level default of INTERNAL, but the policy
        # checks whether the caller explicitly set a meaningful value.
        # We flag 'public' or None as missing meaningful classification for
        # confidential layers — but the policy YAML drives the exact check.
        # Here we check whether classification is in the policy's allowed set.
        allowed: list[str] | None = cfg.get("allowed_values")
        if allowed is not None and entry.classification.value not in allowed:
            violations.append(
                PolicyViolation(
                    policy_name="classification_required",
                    severity=cfg.get("severity", "error"),
                    message=(
                        f"Dataset '{entry.dataset_name}' ({entry.layer.value} layer) "
                        f"has classification '{entry.classification.value}' but must "
                        f"be one of: {allowed}."
                    ),
                    entry_id=entry.id,
                )
            )

        return violations

    def _check_quality_sla_required(
        self, entry: DataCatalogEntry
    ) -> list[PolicyViolation]:
        """Check that quality_sla is set for layers that require it."""
        violations: list[PolicyViolation] = []
        cfg: dict[str, Any] = self._raw.get("quality_sla_required", {})

        if not cfg.get("enabled", True):
            return violations

        required_for: list[str] = cfg.get("layers", [])
        if entry.layer.value not in required_for:
            return violations

        if not entry.quality_sla:
            violations.append(
                PolicyViolation(
                    policy_name="quality_sla_required",
                    severity=cfg.get("severity", "error"),
                    message=(
                        f"Dataset '{entry.dataset_name}' ({entry.layer.value} layer) "
                        "must have quality_sla defined but none is set."
                    ),
                    entry_id=entry.id,
                )
            )

        return violations

    def _check_naming_convention(
        self, entry: DataCatalogEntry
    ) -> list[PolicyViolation]:
        """Check dataset_name against the configured regex pattern."""
        violations: list[PolicyViolation] = []
        cfg: dict[str, Any] = self._raw.get("naming_convention", {})

        if not cfg.get("enabled", True):
            return violations

        pattern: str | None = cfg.get("pattern")
        if not pattern:
            return violations

        if not re.fullmatch(pattern, entry.dataset_name):
            violations.append(
                PolicyViolation(
                    policy_name="naming_convention",
                    severity=cfg.get("severity", "warning"),
                    message=(
                        f"Dataset name '{entry.dataset_name}' does not match "
                        f"the required naming convention pattern: {pattern}"
                    ),
                    entry_id=entry.id,
                )
            )

        return violations
