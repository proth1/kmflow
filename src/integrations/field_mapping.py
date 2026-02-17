"""Field mapping engine for integration connectors.

Maps fields from external system schemas to KMFlow evidence
and process element fields.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


DEFAULT_MAPPINGS: dict[str, dict[str, str]] = {
    "salesforce": {
        "Id": "external_id",
        "Name": "name",
        "Description": "description",
        "CreatedDate": "source_date",
        "LastModifiedDate": "updated_at",
    },
    "sap": {
        "MANDT": "client_id",
        "BELNR": "document_number",
        "BUKRS": "company_code",
        "ERDAT": "source_date",
        "ERNAM": "created_by",
    },
    "servicenow": {
        "sys_id": "external_id",
        "short_description": "name",
        "description": "description",
        "sys_created_on": "source_date",
        "sys_updated_on": "updated_at",
    },
}


def get_default_mapping(connector_type: str) -> dict[str, str]:
    """Get default field mapping for a connector type."""
    return dict(DEFAULT_MAPPINGS.get(connector_type, {}))


def apply_field_mapping(
    record: dict[str, Any],
    mapping: dict[str, str],
) -> dict[str, Any]:
    """Apply a field mapping to transform a source record.

    Args:
        record: Source record from the external system.
        mapping: Mapping from source field names to target field names.

    Returns:
        Transformed record with mapped field names.
    """
    result: dict[str, Any] = {}
    for source_field, target_field in mapping.items():
        if source_field in record:
            result[target_field] = record[source_field]
    # Include unmapped fields under their original names
    for key, value in record.items():
        if key not in mapping:
            result[key] = value
    return result


def validate_mapping(
    mapping: dict[str, str],
    source_schema: list[str],
) -> list[str]:
    """Validate that mapping source fields exist in the schema.

    Args:
        mapping: Field mapping to validate.
        source_schema: List of available source fields.

    Returns:
        List of error messages (empty if valid).
    """
    errors: list[str] = []
    for source_field in mapping:
        if source_field not in source_schema:
            errors.append(f"Source field '{source_field}' not in schema")
    return errors
