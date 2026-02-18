"""Tests for PolicyEngine — policy loading and violation evaluation.

Uses mock DataCatalogEntry objects and a temporary YAML policy file to
exercise each policy type independently.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock

import yaml

from src.core.models import DataCatalogEntry, DataClassification, DataLayer
from src.governance.policy import PolicyEngine, PolicyViolation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    dataset_name: str = "valid_dataset",
    layer: DataLayer = DataLayer.BRONZE,
    classification: DataClassification = DataClassification.INTERNAL,
    retention_days: int | None = None,
    quality_sla: dict | None = None,
) -> MagicMock:
    """Build a mock DataCatalogEntry."""
    entry = MagicMock(spec=DataCatalogEntry)
    entry.id = uuid.uuid4()
    entry.dataset_name = dataset_name
    entry.layer = layer
    entry.classification = classification
    entry.retention_days = retention_days
    entry.quality_sla = quality_sla
    return entry


def _write_policy(tmp_path: Path, policy: dict) -> Path:
    """Write a YAML policy dict to a temp file and return its path."""
    p = tmp_path / "test_policy.yaml"
    p.write_text(yaml.dump(policy))
    return p


# ---------------------------------------------------------------------------
# PolicyEngine initialization
# ---------------------------------------------------------------------------


class TestPolicyEngineInit:
    """Tests for loading policies from file."""

    def test_loads_default_policy_file(self) -> None:
        engine = PolicyEngine()
        assert engine.policies  # non-empty dict

    def test_loads_custom_policy_file(self, tmp_path: Path) -> None:
        policy = {"retention": {"enabled": False}}
        path = _write_policy(tmp_path, policy)

        engine = PolicyEngine(policy_file=path)

        assert engine.policies == policy
        assert engine.policy_file == path

    def test_empty_yaml_gives_empty_dict(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.yaml"
        p.write_text("")
        engine = PolicyEngine(policy_file=p)
        assert engine.policies == {}


# ---------------------------------------------------------------------------
# Retention policy
# ---------------------------------------------------------------------------


class TestRetentionPolicy:
    """Tests for the retention policy checker."""

    def test_no_violation_when_within_limit(self, tmp_path: Path) -> None:
        policy = {
            "retention": {
                "enabled": True,
                "severity": "warning",
                "max_days_by_layer": {"bronze": 365},
            }
        }
        engine = PolicyEngine(_write_policy(tmp_path, policy))
        entry = _make_entry(layer=DataLayer.BRONZE, retention_days=200)

        violations = engine.evaluate(entry)

        assert not any(v.policy_name == "retention" for v in violations)

    def test_violation_when_over_limit(self, tmp_path: Path) -> None:
        policy = {
            "retention": {
                "enabled": True,
                "severity": "warning",
                "max_days_by_layer": {"bronze": 365},
            }
        }
        engine = PolicyEngine(_write_policy(tmp_path, policy))
        entry = _make_entry(layer=DataLayer.BRONZE, retention_days=500)

        violations = engine.evaluate(entry)

        retention_violations = [v for v in violations if v.policy_name == "retention"]
        assert len(retention_violations) == 1
        assert retention_violations[0].severity == "warning"
        assert "500" in retention_violations[0].message

    def test_no_violation_when_null_retention_days(self, tmp_path: Path) -> None:
        policy = {
            "retention": {
                "enabled": True,
                "max_days_by_layer": {"bronze": 365},
            }
        }
        engine = PolicyEngine(_write_policy(tmp_path, policy))
        entry = _make_entry(layer=DataLayer.BRONZE, retention_days=None)

        violations = engine.evaluate(entry)

        assert not any(v.policy_name == "retention" for v in violations)

    def test_no_violation_for_unlimited_gold_layer(self, tmp_path: Path) -> None:
        policy = {
            "retention": {
                "enabled": True,
                "max_days_by_layer": {"bronze": 365, "silver": 730, "gold": None},
            }
        }
        engine = PolicyEngine(_write_policy(tmp_path, policy))
        entry = _make_entry(layer=DataLayer.GOLD, retention_days=9999)

        violations = engine.evaluate(entry)

        assert not any(v.policy_name == "retention" for v in violations)

    def test_disabled_retention_policy_skipped(self, tmp_path: Path) -> None:
        policy = {
            "retention": {
                "enabled": False,
                "max_days_by_layer": {"bronze": 1},
            }
        }
        engine = PolicyEngine(_write_policy(tmp_path, policy))
        entry = _make_entry(layer=DataLayer.BRONZE, retention_days=9999)

        violations = engine.evaluate(entry)

        assert not any(v.policy_name == "retention" for v in violations)


# ---------------------------------------------------------------------------
# Classification required policy
# ---------------------------------------------------------------------------


class TestClassificationRequiredPolicy:
    """Tests for the classification_required policy checker."""

    def test_violation_when_public_on_silver(self, tmp_path: Path) -> None:
        policy = {
            "classification_required": {
                "enabled": True,
                "severity": "error",
                "layers": ["silver"],
                "allowed_values": ["internal", "confidential", "restricted"],
            }
        }
        engine = PolicyEngine(_write_policy(tmp_path, policy))
        entry = _make_entry(
            layer=DataLayer.SILVER,
            classification=DataClassification.PUBLIC,
        )

        violations = engine.evaluate(entry)

        cr_violations = [v for v in violations if v.policy_name == "classification_required"]
        assert len(cr_violations) == 1
        assert cr_violations[0].severity == "error"

    def test_no_violation_when_classification_allowed(self, tmp_path: Path) -> None:
        policy = {
            "classification_required": {
                "enabled": True,
                "severity": "error",
                "layers": ["silver"],
                "allowed_values": ["internal", "confidential", "restricted"],
            }
        }
        engine = PolicyEngine(_write_policy(tmp_path, policy))
        entry = _make_entry(
            layer=DataLayer.SILVER,
            classification=DataClassification.CONFIDENTIAL,
        )

        violations = engine.evaluate(entry)

        assert not any(v.policy_name == "classification_required" for v in violations)

    def test_bronze_exempt_from_classification_required(self, tmp_path: Path) -> None:
        policy = {
            "classification_required": {
                "enabled": True,
                "layers": ["silver", "gold"],
                "allowed_values": ["confidential"],
            }
        }
        engine = PolicyEngine(_write_policy(tmp_path, policy))
        entry = _make_entry(
            layer=DataLayer.BRONZE,
            classification=DataClassification.PUBLIC,
        )

        violations = engine.evaluate(entry)

        assert not any(v.policy_name == "classification_required" for v in violations)


# ---------------------------------------------------------------------------
# Quality SLA required policy
# ---------------------------------------------------------------------------


class TestQualitySLARequiredPolicy:
    """Tests for the quality_sla_required policy checker."""

    def test_violation_when_gold_has_no_sla(self, tmp_path: Path) -> None:
        policy = {
            "quality_sla_required": {
                "enabled": True,
                "severity": "error",
                "layers": ["gold"],
            }
        }
        engine = PolicyEngine(_write_policy(tmp_path, policy))
        entry = _make_entry(layer=DataLayer.GOLD, quality_sla=None)

        violations = engine.evaluate(entry)

        sla_violations = [v for v in violations if v.policy_name == "quality_sla_required"]
        assert len(sla_violations) == 1

    def test_no_violation_when_gold_has_sla(self, tmp_path: Path) -> None:
        policy = {
            "quality_sla_required": {
                "enabled": True,
                "layers": ["gold"],
            }
        }
        engine = PolicyEngine(_write_policy(tmp_path, policy))
        entry = _make_entry(layer=DataLayer.GOLD, quality_sla={"min_score": 0.9})

        violations = engine.evaluate(entry)

        assert not any(v.policy_name == "quality_sla_required" for v in violations)

    def test_silver_exempt_from_quality_sla_required(self, tmp_path: Path) -> None:
        policy = {
            "quality_sla_required": {
                "enabled": True,
                "layers": ["gold"],
            }
        }
        engine = PolicyEngine(_write_policy(tmp_path, policy))
        entry = _make_entry(layer=DataLayer.SILVER, quality_sla=None)

        violations = engine.evaluate(entry)

        assert not any(v.policy_name == "quality_sla_required" for v in violations)


# ---------------------------------------------------------------------------
# Naming convention policy
# ---------------------------------------------------------------------------


class TestNamingConventionPolicy:
    """Tests for the naming_convention policy checker."""

    def test_violation_when_name_has_uppercase(self, tmp_path: Path) -> None:
        policy = {
            "naming_convention": {
                "enabled": True,
                "severity": "warning",
                "pattern": "^[a-z][a-z0-9_]*$",
            }
        }
        engine = PolicyEngine(_write_policy(tmp_path, policy))
        entry = _make_entry(dataset_name="MyDataset")

        violations = engine.evaluate(entry)

        nc_violations = [v for v in violations if v.policy_name == "naming_convention"]
        assert len(nc_violations) == 1
        assert "MyDataset" in nc_violations[0].message

    def test_violation_when_name_has_spaces(self, tmp_path: Path) -> None:
        policy = {
            "naming_convention": {
                "enabled": True,
                "pattern": "^[a-z][a-z0-9_]*$",
            }
        }
        engine = PolicyEngine(_write_policy(tmp_path, policy))
        entry = _make_entry(dataset_name="my dataset")

        violations = engine.evaluate(entry)

        assert any(v.policy_name == "naming_convention" for v in violations)

    def test_violation_when_name_has_hyphens(self, tmp_path: Path) -> None:
        policy = {
            "naming_convention": {
                "enabled": True,
                "pattern": "^[a-z][a-z0-9_]*$",
            }
        }
        engine = PolicyEngine(_write_policy(tmp_path, policy))
        entry = _make_entry(dataset_name="my-dataset")

        violations = engine.evaluate(entry)

        assert any(v.policy_name == "naming_convention" for v in violations)

    def test_no_violation_for_valid_name(self, tmp_path: Path) -> None:
        policy = {
            "naming_convention": {
                "enabled": True,
                "pattern": "^[a-z][a-z0-9_]*$",
            }
        }
        engine = PolicyEngine(_write_policy(tmp_path, policy))
        entry = _make_entry(dataset_name="valid_dataset_v2")

        violations = engine.evaluate(entry)

        assert not any(v.policy_name == "naming_convention" for v in violations)

    def test_disabled_naming_convention_skipped(self, tmp_path: Path) -> None:
        policy = {
            "naming_convention": {
                "enabled": False,
                "pattern": "^[a-z]+$",
            }
        }
        engine = PolicyEngine(_write_policy(tmp_path, policy))
        entry = _make_entry(dataset_name="INVALID NAME!!!")

        violations = engine.evaluate(entry)

        assert not any(v.policy_name == "naming_convention" for v in violations)


# ---------------------------------------------------------------------------
# PolicyViolation dataclass
# ---------------------------------------------------------------------------


class TestPolicyViolation:
    """Tests for the PolicyViolation dataclass."""

    def test_can_create_violation(self) -> None:
        entry_id = uuid.uuid4()
        v = PolicyViolation(
            policy_name="retention",
            severity="warning",
            message="Retention exceeds limit",
            entry_id=entry_id,
        )
        assert v.policy_name == "retention"
        assert v.severity == "warning"
        assert v.entry_id == entry_id

    def test_violation_fields_are_accessible(self) -> None:
        v = PolicyViolation(
            policy_name="naming_convention",
            severity="error",
            message="Name is invalid",
            entry_id=uuid.uuid4(),
        )
        assert v.message == "Name is invalid"


# ---------------------------------------------------------------------------
# Default policy file
# ---------------------------------------------------------------------------


class TestDefaultPolicyFile:
    """Smoke tests for the bundled default.yaml policy file."""

    def test_default_policies_load_without_error(self) -> None:
        engine = PolicyEngine()
        assert "retention" in engine.policies
        assert "classification_required" in engine.policies
        assert "quality_sla_required" in engine.policies
        assert "naming_convention" in engine.policies

    def test_default_bronze_retention_limit(self) -> None:
        engine = PolicyEngine()
        bronze_limit = (
            engine.policies["retention"]["max_days_by_layer"]["bronze"]
        )
        assert bronze_limit == 365

    def test_default_gold_retention_unlimited(self) -> None:
        engine = PolicyEngine()
        gold_limit = engine.policies["retention"]["max_days_by_layer"]["gold"]
        assert gold_limit is None
