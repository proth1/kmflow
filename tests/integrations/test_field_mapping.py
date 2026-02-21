"""Tests for the field mapping engine (src.integrations.field_mapping)."""

from __future__ import annotations

import pytest

from src.integrations.field_mapping import (
    DEFAULT_MAPPINGS,
    apply_field_mapping,
    get_default_mapping,
    validate_mapping,
)


# =============================================================================
# get_default_mapping
# =============================================================================


class TestGetDefaultMapping:
    """Tests for get_default_mapping()."""

    def test_salesforce_mapping_returns_correct_keys(self) -> None:
        mapping = get_default_mapping("salesforce")
        assert mapping["Id"] == "external_id"
        assert mapping["Name"] == "name"
        assert mapping["Description"] == "description"
        assert mapping["CreatedDate"] == "source_date"
        assert mapping["LastModifiedDate"] == "updated_at"

    def test_sap_mapping_returns_correct_keys(self) -> None:
        mapping = get_default_mapping("sap")
        assert mapping["MANDT"] == "client_id"
        assert mapping["BELNR"] == "document_number"
        assert mapping["BUKRS"] == "company_code"
        assert mapping["ERDAT"] == "source_date"
        assert mapping["ERNAM"] == "created_by"

    def test_servicenow_mapping_returns_correct_keys(self) -> None:
        mapping = get_default_mapping("servicenow")
        assert mapping["sys_id"] == "external_id"
        assert mapping["short_description"] == "name"
        assert mapping["description"] == "description"
        assert mapping["sys_created_on"] == "source_date"
        assert mapping["sys_updated_on"] == "updated_at"

    def test_unknown_connector_returns_empty_dict(self) -> None:
        mapping = get_default_mapping("nonexistent_connector")
        assert mapping == {}

    def test_empty_string_connector_returns_empty_dict(self) -> None:
        mapping = get_default_mapping("")
        assert mapping == {}

    def test_returns_independent_copy(self) -> None:
        """Mutating the returned dict must not affect DEFAULT_MAPPINGS."""
        mapping = get_default_mapping("salesforce")
        mapping["NewField"] = "new_target"
        # Original must be untouched
        assert "NewField" not in DEFAULT_MAPPINGS.get("salesforce", {})

    def test_returns_independent_copy_on_second_call(self) -> None:
        """Two calls return independent copies."""
        first = get_default_mapping("sap")
        second = get_default_mapping("sap")
        first["EXTRA"] = "extra_value"
        assert "EXTRA" not in second

    def test_case_sensitive_connector_name(self) -> None:
        """Connector name lookup is case-sensitive."""
        assert get_default_mapping("Salesforce") == {}
        assert get_default_mapping("SAP") == {}
        assert get_default_mapping("ServiceNow") == {}


# =============================================================================
# apply_field_mapping
# =============================================================================


class TestApplyFieldMapping:
    """Tests for apply_field_mapping()."""

    def test_maps_single_field(self) -> None:
        record = {"Id": "123"}
        mapping = {"Id": "external_id"}
        result = apply_field_mapping(record, mapping)
        assert result["external_id"] == "123"
        assert "Id" not in result

    def test_maps_multiple_fields(self) -> None:
        record = {"Id": "abc", "Name": "Test Case", "Status": "Open"}
        mapping = {"Id": "external_id", "Name": "name"}
        result = apply_field_mapping(record, mapping)
        assert result["external_id"] == "abc"
        assert result["name"] == "Test Case"

    def test_unmapped_fields_are_passed_through(self) -> None:
        record = {"Id": "abc", "Name": "Test", "CustomField": "custom-value"}
        mapping = {"Id": "external_id"}
        result = apply_field_mapping(record, mapping)
        assert result["external_id"] == "abc"
        assert result["CustomField"] == "custom-value"
        # Name is not in the mapping, so it is passed through under its original key
        assert result["Name"] == "Test"

    def test_empty_mapping_returns_original_record_unchanged(self) -> None:
        record = {"foo": 1, "bar": "baz"}
        result = apply_field_mapping(record, {})
        assert result == {"foo": 1, "bar": "baz"}

    def test_empty_record_with_non_empty_mapping_returns_empty(self) -> None:
        result = apply_field_mapping({}, {"Id": "external_id"})
        assert result == {}

    def test_source_field_absent_from_record_is_skipped(self) -> None:
        """Mapping entries whose source field is missing from the record are silently skipped."""
        record = {"Name": "Test"}
        mapping = {"Id": "external_id", "Name": "name"}
        result = apply_field_mapping(record, mapping)
        assert "external_id" not in result
        assert result["name"] == "Test"

    def test_preserves_value_types(self) -> None:
        record = {"Count": 42, "Active": True, "Score": 3.14, "Tags": ["a", "b"]}
        mapping = {"Count": "record_count"}
        result = apply_field_mapping(record, mapping)
        assert result["record_count"] == 42
        assert result["Active"] is True
        assert result["Score"] == pytest.approx(3.14)
        assert result["Tags"] == ["a", "b"]

    def test_none_values_are_mapped(self) -> None:
        record = {"Status": None}
        mapping = {"Status": "state"}
        result = apply_field_mapping(record, mapping)
        assert result["state"] is None

    def test_applies_salesforce_default_mapping(self) -> None:
        """Integration-style test using get_default_mapping + apply_field_mapping."""
        from src.integrations.field_mapping import get_default_mapping

        record = {
            "Id": "0012345",
            "Name": "My Case",
            "Description": "A description",
            "CreatedDate": "2024-01-01",
            "LastModifiedDate": "2024-06-01",
            "ExtraField": "extra",
        }
        mapping = get_default_mapping("salesforce")
        result = apply_field_mapping(record, mapping)

        assert result["external_id"] == "0012345"
        assert result["name"] == "My Case"
        assert result["description"] == "A description"
        assert result["source_date"] == "2024-01-01"
        assert result["updated_at"] == "2024-06-01"
        assert result["ExtraField"] == "extra"

    def test_applies_sap_default_mapping(self) -> None:
        from src.integrations.field_mapping import get_default_mapping

        record = {
            "MANDT": "100",
            "BELNR": "DOC-001",
            "BUKRS": "1000",
            "ERDAT": "20240101",
            "ERNAM": "SAPUSER",
            "GJAHR": "2024",
        }
        mapping = get_default_mapping("sap")
        result = apply_field_mapping(record, mapping)

        assert result["client_id"] == "100"
        assert result["document_number"] == "DOC-001"
        assert result["company_code"] == "1000"
        assert result["source_date"] == "20240101"
        assert result["created_by"] == "SAPUSER"
        # GJAHR is not in the mapping, so it passes through
        assert result["GJAHR"] == "2024"

    def test_applies_servicenow_default_mapping(self) -> None:
        from src.integrations.field_mapping import get_default_mapping

        record = {
            "sys_id": "abc123",
            "short_description": "Printer broken",
            "description": "The printer on floor 2 is jammed.",
            "sys_created_on": "2024-05-01T10:00:00",
            "sys_updated_on": "2024-05-02T09:00:00",
            "priority": "2",
        }
        mapping = get_default_mapping("servicenow")
        result = apply_field_mapping(record, mapping)

        assert result["external_id"] == "abc123"
        assert result["name"] == "Printer broken"
        assert result["description"] == "The printer on floor 2 is jammed."
        assert result["source_date"] == "2024-05-01T10:00:00"
        assert result["updated_at"] == "2024-05-02T09:00:00"
        assert result["priority"] == "2"


# =============================================================================
# validate_mapping
# =============================================================================


class TestValidateMapping:
    """Tests for validate_mapping()."""

    def test_valid_mapping_returns_empty_list(self) -> None:
        mapping = {"Id": "external_id", "Name": "name"}
        schema = ["Id", "Name", "Status", "Description"]
        errors = validate_mapping(mapping, schema)
        assert errors == []

    def test_single_invalid_field_returns_one_error(self) -> None:
        mapping = {"NonExistent": "target"}
        schema = ["Id", "Name"]
        errors = validate_mapping(mapping, schema)
        assert len(errors) == 1
        assert "NonExistent" in errors[0]
        assert "not in schema" in errors[0]

    def test_multiple_invalid_fields_returns_multiple_errors(self) -> None:
        mapping = {"Bad1": "t1", "Bad2": "t2", "Good": "t3"}
        schema = ["Good", "Other"]
        errors = validate_mapping(mapping, schema)
        assert len(errors) == 2
        field_names = [e for e in errors]
        assert any("Bad1" in e for e in field_names)
        assert any("Bad2" in e for e in field_names)

    def test_empty_mapping_is_always_valid(self) -> None:
        errors = validate_mapping({}, ["Id", "Name"])
        assert errors == []

    def test_empty_schema_makes_all_fields_invalid(self) -> None:
        mapping = {"Id": "external_id", "Name": "name"}
        errors = validate_mapping(mapping, [])
        assert len(errors) == 2

    def test_empty_mapping_and_empty_schema_is_valid(self) -> None:
        errors = validate_mapping({}, [])
        assert errors == []

    def test_target_field_name_not_checked_against_schema(self) -> None:
        """validate_mapping only checks source fields, not target field names."""
        mapping = {"Id": "some_arbitrary_target_that_doesnt_exist"}
        schema = ["Id", "Name"]
        errors = validate_mapping(mapping, schema)
        assert errors == []

    def test_partial_match_is_invalid(self) -> None:
        """Field names must match exactly, not as substrings."""
        mapping = {"I": "external_id"}  # "I" is not the same as "Id"
        schema = ["Id", "Name"]
        errors = validate_mapping(mapping, schema)
        assert len(errors) == 1
        assert "I" in errors[0]

    def test_error_message_format(self) -> None:
        """Error messages follow the pattern: Source field 'X' not in schema."""
        mapping = {"MissingField": "target"}
        schema = ["OtherField"]
        errors = validate_mapping(mapping, schema)
        assert len(errors) == 1
        assert errors[0] == "Source field 'MissingField' not in schema"
