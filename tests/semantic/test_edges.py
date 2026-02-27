"""Tests for controlled edge vocabulary and constraint validation (Story #295).

Covers all 6 BDD scenarios plus unit tests for the EdgeConstraintValidator.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.semantic.edges import (
    ACYCLIC_EDGES,
    BIDIRECTIONAL_EDGES,
    CycleDetectedError,
    EdgeConstraintValidator,
    EdgeValidationError,
    EdgeVocabulary,
)


class TestEdgeVocabulary:
    """Tests for the EdgeVocabulary StrEnum."""

    def test_all_12_types_present(self):
        """All 12 PRD edge types are defined."""
        expected = {
            "PRECEDES",
            "TRIGGERS",
            "DEPENDS_ON",
            "CONSUMES",
            "PRODUCES",
            "GOVERNED_BY",
            "PERFORMED_BY",
            "EVIDENCED_BY",
            "CONTRADICTS",
            "SUPERSEDES",
            "DECOMPOSES_INTO",
            "VARIANT_OF",
        }
        actual = {e.value for e in EdgeVocabulary}
        assert actual == expected

    def test_str_enum_values(self):
        assert EdgeVocabulary.PRECEDES == "PRECEDES"
        assert EdgeVocabulary.CONSUMES == "CONSUMES"

    def test_bidirectional_set(self):
        assert {"CONTRADICTS", "VARIANT_OF"} == BIDIRECTIONAL_EDGES

    def test_acyclic_set(self):
        assert {"PRECEDES", "DEPENDS_ON"} == ACYCLIC_EDGES


class TestValidateEndpoints:
    """Unit tests for EdgeConstraintValidator.validate_endpoints."""

    @pytest.fixture()
    def validator(self):
        driver = MagicMock()
        return EdgeConstraintValidator(driver)

    def test_valid_precedes_activity_to_activity(self, validator):
        """Scenario 1: PRECEDES between Activity nodes is valid."""
        validator.validate_endpoints("PRECEDES", "Activity", "Activity")

    def test_valid_consumes_activity_to_dataobject(self, validator):
        """Scenario 2: CONSUMES from Activity to DataObject is valid."""
        validator.validate_endpoints("CONSUMES", "Activity", "DataObject")

    def test_invalid_consumes_activity_to_activity(self, validator):
        """Scenario 3: CONSUMES target must be DataObject, not Activity."""
        with pytest.raises(EdgeValidationError, match="CONSUMES target must be DataObject"):
            validator.validate_endpoints("CONSUMES", "Activity", "Activity")

    def test_governed_by_requires_policy_target(self, validator):
        """Scenario 6: GOVERNED_BY target must be Policy node."""
        with pytest.raises(EdgeValidationError, match="GOVERNED_BY target"):
            validator.validate_endpoints("GOVERNED_BY", "Activity", "Role")

    def test_governed_by_valid_with_policy(self, validator):
        validator.validate_endpoints("GOVERNED_BY", "Activity", "Policy")

    def test_governed_by_valid_with_regulation(self, validator):
        validator.validate_endpoints("GOVERNED_BY", "Activity", "Regulation")

    def test_triggers_requires_event_or_gateway_source(self, validator):
        validator.validate_endpoints("TRIGGERS", "Event", "Activity")
        validator.validate_endpoints("TRIGGERS", "Gateway", "Activity")
        with pytest.raises(EdgeValidationError, match="TRIGGERS source"):
            validator.validate_endpoints("TRIGGERS", "Activity", "Activity")

    def test_performed_by_target_must_be_role(self, validator):
        validator.validate_endpoints("PERFORMED_BY", "Activity", "Role")
        with pytest.raises(EdgeValidationError, match="PERFORMED_BY target"):
            validator.validate_endpoints("PERFORMED_BY", "Activity", "Activity")

    def test_evidenced_by_target_must_be_evidence(self, validator):
        validator.validate_endpoints("EVIDENCED_BY", "Assertion", "Evidence")
        with pytest.raises(EdgeValidationError, match="EVIDENCED_BY target"):
            validator.validate_endpoints("EVIDENCED_BY", "Assertion", "Activity")

    def test_produces_target_must_be_dataobject(self, validator):
        validator.validate_endpoints("PRODUCES", "Activity", "DataObject")
        with pytest.raises(EdgeValidationError, match="PRODUCES target"):
            validator.validate_endpoints("PRODUCES", "Activity", "Activity")

    def test_decomposes_into_valid(self, validator):
        validator.validate_endpoints("DECOMPOSES_INTO", "Process", "Subprocess")
        validator.validate_endpoints("DECOMPOSES_INTO", "Process", "Activity")

    def test_supersedes_assertion_to_assertion(self, validator):
        validator.validate_endpoints("SUPERSEDES", "Assertion", "Assertion")

    def test_variant_of_activity_to_activity(self, validator):
        validator.validate_endpoints("VARIANT_OF", "Activity", "Activity")

    def test_unknown_edge_type(self, validator):
        with pytest.raises(EdgeValidationError, match="Unknown edge type"):
            validator.validate_endpoints("NONEXISTENT", "Activity", "Activity")


def _mock_driver_with_labels(label_map: dict[str, str]) -> MagicMock:
    """Create a mock driver that returns node labels from a map.

    Args:
        label_map: Dict mapping node_id to label.
    """

    class FakeReadTx:
        def __init__(self, lmap: dict[str, str]) -> None:
            self._lmap = lmap

        async def run(self, query: str, params: dict):
            nid = params.get("nid")
            if nid and nid in self._lmap:
                return FakeResult([{"labels": [self._lmap[nid]]}])
            # Acyclicity check: return no path found by default
            if "has_path" in query:
                return FakeResult([{"has_path": False}])
            return FakeResult([])

    class FakeWriteTx:
        async def run(self, query: str, params: dict):
            if "fwd_id" in query:
                return FakeResult([{"fwd_id": "test-fwd", "rev_id": "test-rev"}])
            return FakeResult([{"id": "test-id"}])

    class FakeResult:
        def __init__(self, rows: list[dict]) -> None:
            self._rows = rows

        async def data(self) -> list[dict]:
            return self._rows

    class FakeSession:
        def __init__(self, lmap: dict[str, str]) -> None:
            self._lmap = lmap

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def execute_read(self, func):
            return await func(FakeReadTx(self._lmap))

        async def execute_write(self, func):
            return await func(FakeWriteTx())

    driver = MagicMock()
    driver.session.return_value = FakeSession(label_map)
    return driver


@pytest.mark.asyncio
class TestCreateValidatedEdgeScenario1:
    """Scenario 1: Valid PRECEDES edge between two Activity nodes."""

    async def test_precedes_stored_successfully(self):
        driver = _mock_driver_with_labels({"act-A": "Activity", "act-B": "Activity"})
        validator = EdgeConstraintValidator(driver)

        result = await validator.create_validated_edge(
            "act-A",
            "act-B",
            "PRECEDES",
            {"variant_id": "v1", "frequency": 42},
        )

        assert len(result) == 1
        assert result[0]["type"] == "PRECEDES"
        assert result[0]["from_id"] == "act-A"
        assert result[0]["to_id"] == "act-B"


@pytest.mark.asyncio
class TestCreateValidatedEdgeScenario2:
    """Scenario 2: Valid CONSUMES edge from Activity to DataObject."""

    async def test_consumes_stored_successfully(self):
        driver = _mock_driver_with_labels({"act-kyc": "Activity", "do-form": "DataObject"})
        validator = EdgeConstraintValidator(driver)

        result = await validator.create_validated_edge("act-kyc", "do-form", "CONSUMES")

        assert len(result) == 1
        assert result[0]["type"] == "CONSUMES"


@pytest.mark.asyncio
class TestCreateValidatedEdgeScenario3:
    """Scenario 3: Invalid CONSUMES rejected when target is not DataObject."""

    async def test_consumes_rejected_for_activity_target(self):
        driver = _mock_driver_with_labels({"act-kyc": "Activity", "act-aml": "Activity"})
        validator = EdgeConstraintValidator(driver)

        with pytest.raises(EdgeValidationError, match="CONSUMES target must be DataObject"):
            await validator.create_validated_edge("act-kyc", "act-aml", "CONSUMES")


@pytest.mark.asyncio
class TestCreateValidatedEdgeScenario4:
    """Scenario 4: Acyclicity enforcement for PRECEDES within a variant."""

    async def test_cycle_detected_and_rejected(self):
        """A→B→C exists, adding C→A should raise CycleDetectedError."""
        driver = _mock_driver_with_labels({"A": "Activity", "B": "Activity", "C": "Activity"})

        # Patch the acyclicity check to simulate an existing path
        validator = EdgeConstraintValidator(driver)

        with patch.object(validator, "_check_acyclicity", new_callable=AsyncMock) as mock_check:
            mock_check.side_effect = CycleDetectedError(
                "Creating PRECEDES edge C->A would create a cycle within variant 'v1'"
            )

            with pytest.raises(CycleDetectedError, match="cycle"):
                await validator.create_validated_edge(
                    "C",
                    "A",
                    "PRECEDES",
                    {"variant_id": "v1"},
                )

    async def test_no_cycle_allowed(self):
        """Non-cyclic PRECEDES edge is allowed."""
        driver = _mock_driver_with_labels({"A": "Activity", "B": "Activity"})
        validator = EdgeConstraintValidator(driver)

        result = await validator.create_validated_edge(
            "A",
            "B",
            "PRECEDES",
            {"variant_id": "v1"},
        )
        assert len(result) == 1


@pytest.mark.asyncio
class TestCreateValidatedEdgeScenario5:
    """Scenario 5: CONTRADICTS edge is bidirectional."""

    async def test_contradicts_creates_two_edges(self):
        driver = _mock_driver_with_labels({"X": "Assertion", "Y": "Assertion"})
        validator = EdgeConstraintValidator(driver)

        result = await validator.create_validated_edge(
            "X",
            "Y",
            "CONTRADICTS",
            {"severity": "high"},
        )

        assert len(result) == 2
        assert result[0] == {"from_id": "X", "to_id": "Y", "type": "CONTRADICTS"}
        assert result[1] == {"from_id": "Y", "to_id": "X", "type": "CONTRADICTS"}


@pytest.mark.asyncio
class TestCreateValidatedEdgeScenario6:
    """Scenario 6: GOVERNED_BY edge requires Policy target."""

    async def test_governed_by_rejected_for_role_target(self):
        driver = _mock_driver_with_labels({"act-1": "Activity", "role-1": "Role"})
        validator = EdgeConstraintValidator(driver)

        with pytest.raises(EdgeValidationError, match="GOVERNED_BY target"):
            await validator.create_validated_edge("act-1", "role-1", "GOVERNED_BY")


@pytest.mark.asyncio
class TestVariantOfBidirectional:
    """VARIANT_OF also creates bidirectional edges."""

    async def test_variant_of_creates_two_edges(self):
        driver = _mock_driver_with_labels({"A": "Activity", "B": "Activity"})
        validator = EdgeConstraintValidator(driver)

        result = await validator.create_validated_edge("A", "B", "VARIANT_OF")

        assert len(result) == 2
        assert result[0]["from_id"] == "A"
        assert result[1]["from_id"] == "B"


@pytest.mark.asyncio
class TestNodeNotFound:
    """Error when source or target node doesn't exist."""

    async def test_source_not_found(self):
        driver = _mock_driver_with_labels({"B": "Activity"})
        validator = EdgeConstraintValidator(driver)

        with pytest.raises(ValueError, match="Source node not found"):
            await validator.create_validated_edge("missing", "B", "PRECEDES")

    async def test_target_not_found(self):
        driver = _mock_driver_with_labels({"A": "Activity"})
        validator = EdgeConstraintValidator(driver)

        with pytest.raises(ValueError, match="Target node not found"):
            await validator.create_validated_edge("A", "missing", "PRECEDES")


@pytest.mark.asyncio
class TestEdgeTypeEnumValidation:
    """Edge type must be a valid EdgeVocabulary member before Cypher interpolation."""

    async def test_unknown_edge_type_rejected_at_create(self):
        driver = _mock_driver_with_labels({"A": "Activity", "B": "Activity"})
        validator = EdgeConstraintValidator(driver)

        with pytest.raises(EdgeValidationError, match="Unknown edge type"):
            await validator.create_validated_edge("A", "B", "MALICIOUS_TYPE")


@pytest.mark.asyncio
class TestRealAcyclicityCheck:
    """Test _check_acyclicity with the real method (not patched)."""

    async def test_cycle_detected_via_real_check(self):
        """When FakeReadTx returns has_path=True, CycleDetectedError is raised."""

        def _make_cycle_driver() -> MagicMock:
            """Driver where acyclicity check returns has_path=True."""

            class CycleFakeReadTx:
                def __init__(self, lmap: dict[str, str]) -> None:
                    self._lmap = lmap

                async def run(self, query: str, params: dict):
                    nid = params.get("nid")
                    if nid and nid in self._lmap:
                        return _FakeResult([{"labels": [self._lmap[nid]]}])
                    if "has_path" in query:
                        return _FakeResult([{"has_path": True}])
                    return _FakeResult([])

            class CycleFakeWriteTx:
                async def run(self, query: str, params: dict):
                    return _FakeResult([{"id": "test-id"}])

            class _FakeResult:
                def __init__(self, rows: list[dict]) -> None:
                    self._rows = rows

                async def data(self) -> list[dict]:
                    return self._rows

            class CycleFakeSession:
                def __init__(self, lmap: dict[str, str]) -> None:
                    self._lmap = lmap

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

                async def execute_read(self, func):
                    return await func(CycleFakeReadTx(self._lmap))

                async def execute_write(self, func):
                    return await func(CycleFakeWriteTx())

            d = MagicMock()
            d.session.return_value = CycleFakeSession({"C": "Activity", "A": "Activity"})
            return d

        driver = _make_cycle_driver()
        validator = EdgeConstraintValidator(driver)

        with pytest.raises(CycleDetectedError, match="cycle"):
            await validator.create_validated_edge("C", "A", "PRECEDES", {"variant_id": "v1"})

    async def test_acyclicity_without_variant_id(self):
        """Acyclicity check works without variant_id (no cycle)."""
        driver = _mock_driver_with_labels({"A": "Activity", "B": "Activity"})
        validator = EdgeConstraintValidator(driver)

        result = await validator.create_validated_edge("A", "B", "DEPENDS_ON")
        assert len(result) == 1
        assert result[0]["type"] == "DEPENDS_ON"
