"""Tests for Unity Catalog integration (src/governance/unity_catalog.py).

Tests cover:
- DDL generation from DataCatalogEntry instances
- Layer -> schema name mapping
- Schema inference from schema_definition dicts
- Column type mapping
- SQL identifier sanitization
- register_tables with mocked SDK client
- Error handling in register_tables (partial success)
- ImportError when databricks-sdk is absent
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.governance.unity_catalog import (
    _uc_schema_name,
    _safe_identifier,
    _map_column_type,
    _build_column_defs,
    generate_unity_catalog_ddl,
    register_tables,
)


# ---------------------------------------------------------------------------
# Minimal DataCatalogEntry stub (avoids DB dependency in unit tests)
# ---------------------------------------------------------------------------


class _DataLayer(str, enum.Enum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"


class _DataClassification(str, enum.Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


@dataclass
class _FakeEntry:
    """Minimal stand-in for DataCatalogEntry without SQLAlchemy."""

    dataset_name: str
    layer: _DataLayer
    schema_definition: dict[str, Any] | None = None
    owner: str | None = None
    classification: _DataClassification = _DataClassification.INTERNAL
    retention_days: int | None = None
    description: str | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)


# ---------------------------------------------------------------------------
# _uc_schema_name
# ---------------------------------------------------------------------------


class TestUCSchemaName:
    def test_bronze_maps_correctly(self) -> None:
        assert _uc_schema_name("evidence", "bronze") == "evidence_bronze"

    def test_silver_maps_correctly(self) -> None:
        assert _uc_schema_name("evidence", "silver") == "evidence_silver"

    def test_gold_maps_correctly(self) -> None:
        assert _uc_schema_name("data", "gold") == "data_gold"

    def test_case_insensitive(self) -> None:
        assert _uc_schema_name("evidence", "BRONZE") == "evidence_bronze"
        assert _uc_schema_name("evidence", "Silver") == "evidence_silver"

    def test_unknown_layer_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown data layer"):
            _uc_schema_name("evidence", "platinum")


# ---------------------------------------------------------------------------
# _safe_identifier
# ---------------------------------------------------------------------------


class TestSafeIdentifier:
    def test_simple_name_unchanged(self) -> None:
        assert _safe_identifier("evidence_files") == "evidence_files"

    def test_spaces_replaced(self) -> None:
        assert _safe_identifier("my dataset") == "my_dataset"

    def test_hyphens_replaced(self) -> None:
        assert _safe_identifier("my-dataset") == "my_dataset"

    def test_special_chars_stripped(self) -> None:
        result = _safe_identifier("table!@#name")
        assert "!" not in result
        assert "@" not in result
        assert "#" not in result

    def test_truncated_to_255(self) -> None:
        long_name = "a" * 300
        assert len(_safe_identifier(long_name)) == 255


# ---------------------------------------------------------------------------
# _map_column_type
# ---------------------------------------------------------------------------


class TestMapColumnType:
    def test_string_types(self) -> None:
        assert _map_column_type("str") == "STRING"
        assert _map_column_type("string") == "STRING"
        assert _map_column_type("text") == "STRING"
        assert _map_column_type("uuid") == "STRING"

    def test_numeric_types(self) -> None:
        assert _map_column_type("int") == "BIGINT"
        assert _map_column_type("integer") == "BIGINT"
        assert _map_column_type("bigint") == "BIGINT"
        assert _map_column_type("float") == "DOUBLE"
        assert _map_column_type("double") == "DOUBLE"

    def test_boolean(self) -> None:
        assert _map_column_type("bool") == "BOOLEAN"
        assert _map_column_type("boolean") == "BOOLEAN"

    def test_temporal_types(self) -> None:
        assert _map_column_type("date") == "DATE"
        assert _map_column_type("datetime") == "TIMESTAMP"
        assert _map_column_type("timestamp") == "TIMESTAMP"

    def test_json_maps_to_string(self) -> None:
        assert _map_column_type("json") == "STRING"

    def test_binary_type(self) -> None:
        assert _map_column_type("bytes") == "BINARY"
        assert _map_column_type("binary") == "BINARY"

    def test_unknown_defaults_to_string(self) -> None:
        result = _map_column_type("vector")
        assert result == "STRING"

    def test_case_insensitive(self) -> None:
        assert _map_column_type("INT") == "BIGINT"
        assert _map_column_type("String") == "STRING"


# ---------------------------------------------------------------------------
# _build_column_defs
# ---------------------------------------------------------------------------


class TestBuildColumnDefs:
    def test_none_returns_minimal_schema(self) -> None:
        cols = _build_column_defs(None)
        assert any("id" in c for c in cols)
        assert any("created_at" in c for c in cols)

    def test_empty_dict_returns_minimal_schema(self) -> None:
        cols = _build_column_defs({})
        assert len(cols) >= 1

    def test_typed_columns_mapped(self) -> None:
        cols = _build_column_defs({
            "id": "uuid",
            "size_bytes": "int",
            "content_hash": "str",
            "stored_at": "datetime",
        })
        joined = " ".join(cols)
        assert "STRING" in joined
        assert "BIGINT" in joined
        assert "TIMESTAMP" in joined


# ---------------------------------------------------------------------------
# generate_unity_catalog_ddl
# ---------------------------------------------------------------------------


class TestGenerateUCDDL:
    def test_single_bronze_entry(self) -> None:
        entry = _FakeEntry(
            dataset_name="evidence_files",
            layer=_DataLayer.BRONZE,
        )
        ddl = generate_unity_catalog_ddl([entry], "kmflow", "evidence")

        assert "CREATE TABLE IF NOT EXISTS" in ddl
        assert "`kmflow`" in ddl
        assert "`evidence_bronze`" in ddl
        assert "`evidence_files`" in ddl
        assert "USING DELTA" in ddl

    def test_layer_to_schema_suffix(self) -> None:
        entries = [
            _FakeEntry("bronze_table", _DataLayer.BRONZE),
            _FakeEntry("silver_table", _DataLayer.SILVER),
            _FakeEntry("gold_table", _DataLayer.GOLD),
        ]
        ddl = generate_unity_catalog_ddl(entries, "cat", "sch")

        assert "`sch_bronze`" in ddl
        assert "`sch_silver`" in ddl
        assert "`sch_gold`" in ddl

    def test_multiple_entries_separated_by_semicolon(self) -> None:
        entries = [
            _FakeEntry("table_a", _DataLayer.BRONZE),
            _FakeEntry("table_b", _DataLayer.SILVER),
        ]
        ddl = generate_unity_catalog_ddl(entries, "cat", "sch")

        # Statements separated by ";\n\n"
        parts = ddl.split(";\n\n")
        assert len(parts) == 2

    def test_schema_definition_columns_included(self) -> None:
        entry = _FakeEntry(
            dataset_name="typed_table",
            layer=_DataLayer.SILVER,
            schema_definition={"id": "uuid", "score": "float", "active": "bool"},
        )
        ddl = generate_unity_catalog_ddl([entry], "cat", "sch")

        assert "STRING" in ddl  # uuid -> STRING
        assert "DOUBLE" in ddl  # float -> DOUBLE
        assert "BOOLEAN" in ddl  # bool -> BOOLEAN

    def test_comment_includes_description(self) -> None:
        entry = _FakeEntry(
            dataset_name="doc_table",
            layer=_DataLayer.BRONZE,
            description="Stores raw document bytes",
            owner="alice@example.com",
        )
        ddl = generate_unity_catalog_ddl([entry], "cat", "sch")

        assert "Stores raw document bytes" in ddl
        assert "alice@example.com" in ddl

    def test_retention_days_adds_tblproperties(self) -> None:
        entry = _FakeEntry(
            dataset_name="retained_table",
            layer=_DataLayer.BRONZE,
            retention_days=90,
        )
        ddl = generate_unity_catalog_ddl([entry], "cat", "sch")

        assert "TBLPROPERTIES" in ddl
        assert "90 days" in ddl

    def test_empty_list_returns_empty_string(self) -> None:
        ddl = generate_unity_catalog_ddl([], "cat", "sch")
        assert ddl == ""

    def test_dataset_name_sanitized(self) -> None:
        entry = _FakeEntry(
            dataset_name="My Dataset With Spaces",
            layer=_DataLayer.BRONZE,
        )
        ddl = generate_unity_catalog_ddl([entry], "cat", "sch")

        assert "My_Dataset_With_Spaces" in ddl

    def test_single_quote_in_description_escaped(self) -> None:
        entry = _FakeEntry(
            dataset_name="test_table",
            layer=_DataLayer.BRONZE,
            description="It's a table",
        )
        ddl = generate_unity_catalog_ddl([entry], "cat", "sch")

        # Single quote must be escaped as '' in SQL string literal
        assert "It''s a table" in ddl


# ---------------------------------------------------------------------------
# register_tables
# ---------------------------------------------------------------------------


class TestRegisterTables:
    def _make_client(self, warehouse_id: str = "wh-001") -> MagicMock:
        client = MagicMock()
        mock_wh = MagicMock()
        mock_wh.id = warehouse_id
        mock_wh.state = "RUNNING"
        client.warehouses.list.return_value = [mock_wh]
        return client

    def test_successful_registration_returns_ok(self) -> None:
        client = self._make_client()
        entry = _FakeEntry("test_table", _DataLayer.BRONZE)

        with patch("src.governance.unity_catalog._HAS_DATABRICKS", True):
            results = register_tables(client, [entry], "cat", "sch")

        assert results["test_table"] == "ok"

    def test_creates_schema_before_table(self) -> None:
        client = self._make_client()
        entry = _FakeEntry("test_table", _DataLayer.SILVER)

        with patch("src.governance.unity_catalog._HAS_DATABRICKS", True):
            register_tables(client, [entry], "cat", "sch")

        calls = [call[1]["statement"] for call in client.statement_execution.execute.call_args_list]
        schema_ddl_calls = [c for c in calls if "CREATE SCHEMA IF NOT EXISTS" in c]
        assert len(schema_ddl_calls) >= 1
        assert "`cat`.`sch_silver`" in schema_ddl_calls[0]

    def test_partial_failure_continues(self) -> None:
        client = self._make_client()
        call_count = [0]

        def side_effect(*args: Any, **kwargs: Any) -> None:
            call_count[0] += 1
            stmt = kwargs.get("statement", "")
            if "CREATE TABLE" in stmt and call_count[0] == 4:
                raise Exception("permission denied")

        client.statement_execution.execute.side_effect = side_effect

        entries = [
            _FakeEntry("table_ok", _DataLayer.BRONZE),
            _FakeEntry("table_fail", _DataLayer.SILVER),
        ]

        with patch("src.governance.unity_catalog._HAS_DATABRICKS", True):
            results = register_tables(client, entries, "cat", "sch")

        # One should succeed, one should fail
        statuses = list(results.values())
        assert "ok" in statuses
        assert any(s.startswith("error:") for s in statuses)

    def test_empty_entries_returns_empty_dict(self) -> None:
        client = self._make_client()

        with patch("src.governance.unity_catalog._HAS_DATABRICKS", True):
            results = register_tables(client, [], "cat", "sch")

        assert results == {}

    def test_explicit_warehouse_id_used(self) -> None:
        client = self._make_client()
        entry = _FakeEntry("t", _DataLayer.BRONZE)

        with patch("src.governance.unity_catalog._HAS_DATABRICKS", True):
            register_tables(client, [entry], "cat", "sch", warehouse_id="wh-explicit")

        for call in client.statement_execution.execute.call_args_list:
            assert call[1]["warehouse_id"] == "wh-explicit"

    def test_missing_sdk_raises_import_error(self) -> None:
        client = MagicMock()
        entry = _FakeEntry("t", _DataLayer.BRONZE)

        with patch("src.governance.unity_catalog._HAS_DATABRICKS", False):
            with pytest.raises(ImportError, match="databricks-sdk is required"):
                register_tables(client, [entry], "cat", "sch")


# ---------------------------------------------------------------------------
# Module imports
# ---------------------------------------------------------------------------


class TestModuleImports:
    def test_governance_init_exports(self) -> None:
        from src.governance import generate_unity_catalog_ddl as g_ddl
        from src.governance import register_tables as g_reg

        assert callable(g_ddl)
        assert callable(g_reg)
