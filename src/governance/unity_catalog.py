"""Unity Catalog integration for KMFlow data governance.

Provides helpers for generating Unity Catalog DDL from ``DataCatalogEntry``
records and for bulk-registering those tables in a live Databricks workspace.

The ``databricks-sdk`` package is an optional dependency. All functions that
require the SDK raise ``ImportError`` at call time (not import time) if the
package is absent.

Layer-to-schema mapping (medallion convention):
    bronze -> ``{schema}_bronze``
    silver -> ``{schema}_silver``
    gold   -> ``{schema}_gold``
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.core.models import DataCatalogEntry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional SDK import guard
# ---------------------------------------------------------------------------

try:
    import databricks.sdk  # type: ignore[import-untyped]  # noqa: F401

    _HAS_DATABRICKS = True
except ImportError:
    _HAS_DATABRICKS = False


# ---------------------------------------------------------------------------
# Layer -> UC schema name mapping
# ---------------------------------------------------------------------------

_LAYER_SCHEMA_SUFFIX: dict[str, str] = {
    "bronze": "bronze",
    "silver": "silver",
    "gold": "gold",
}


def _uc_schema_name(base_schema: str, layer: str) -> str:
    """Map a DataLayer enum value to a Unity Catalog schema name.

    Args:
        base_schema: The base schema name (e.g. ``"evidence"``).
        layer: A ``DataLayer`` value: ``"bronze"``, ``"silver"``, or ``"gold"``.

    Returns:
        Unity Catalog schema name, e.g. ``"evidence_bronze"``.

    Raises:
        ValueError: If ``layer`` is not a recognised medallion layer.
    """
    layer_str = str(layer).lower()
    if layer_str not in _LAYER_SCHEMA_SUFFIX:
        raise ValueError(
            f"Unknown data layer: {layer!r}. "
            f"Must be one of: {list(_LAYER_SCHEMA_SUFFIX)}"
        )
    return f"{base_schema}_{_LAYER_SCHEMA_SUFFIX[layer_str]}"


# ---------------------------------------------------------------------------
# Type mapping: Python / SQLAlchemy types -> Spark/UC SQL types
# ---------------------------------------------------------------------------

_TYPE_MAP: dict[str, str] = {
    "str": "STRING",
    "string": "STRING",
    "int": "BIGINT",
    "integer": "BIGINT",
    "bigint": "BIGINT",
    "float": "DOUBLE",
    "double": "DOUBLE",
    "bool": "BOOLEAN",
    "boolean": "BOOLEAN",
    "bytes": "BINARY",
    "binary": "BINARY",
    "date": "DATE",
    "datetime": "TIMESTAMP",
    "timestamp": "TIMESTAMP",
    "json": "STRING",  # UC stores JSON as STRING
    "uuid": "STRING",
    "text": "STRING",
}


def _map_column_type(python_type: str) -> str:
    """Map a Python / schema type string to a Unity Catalog SQL type.

    Unknown types default to ``STRING`` with a warning.
    """
    mapped = _TYPE_MAP.get(python_type.lower())
    if mapped is None:
        logger.warning(
            "Unknown column type %r; defaulting to STRING in UC DDL", python_type
        )
        return "STRING"
    return mapped


# ---------------------------------------------------------------------------
# DDL generation
# ---------------------------------------------------------------------------


def generate_unity_catalog_ddl(
    catalog_entries: list[DataCatalogEntry],
    catalog: str,
    schema: str,
) -> str:
    """Generate Unity Catalog ``CREATE TABLE`` DDL for a list of catalog entries.

    Each ``DataCatalogEntry`` becomes one ``CREATE TABLE IF NOT EXISTS``
    statement targeted at the appropriate medallion sub-schema
    (``{schema}_bronze``, ``{schema}_silver``, ``{schema}_gold``).

    Column definitions are derived from the ``schema_definition`` field if
    present. The ``schema_definition`` is expected to be a dict mapping
    column name to type string, e.g.::

        {"id": "str", "engagement_id": "uuid", "size_bytes": "int"}

    If ``schema_definition`` is absent or empty, a minimal schema with an
    ``id STRING NOT NULL`` column is generated as a placeholder.

    Args:
        catalog_entries: List of ``DataCatalogEntry`` ORM instances.
        catalog: Unity Catalog catalog name.
        schema: Base schema name (layer suffix is appended automatically).

    Returns:
        Multi-statement DDL string, with statements separated by ``;\n\n``.
        Suitable for passing to ``workspace_client.statement_execution.execute``
        or saving to a migration file.
    """
    statements: list[str] = []

    for entry in catalog_entries:
        # Use .value when available (StrEnum / Enum) to get the raw string,
        # then fall back to str() for plain strings or test stubs.
        layer_raw = getattr(entry.layer, "value", str(entry.layer))
        layer_str = layer_raw.lower()
        uc_schema = _uc_schema_name(schema, layer_str)
        table_name = _safe_identifier(entry.dataset_name)
        fqn = f"`{catalog}`.`{uc_schema}`.`{table_name}`"

        columns = _build_column_defs(entry.schema_definition)

        comment_parts: list[str] = []
        if entry.description:
            comment_parts.append(entry.description)
        if entry.owner:
            comment_parts.append(f"Owner: {entry.owner}")
        if entry.classification:
            comment_parts.append(f"Classification: {entry.classification}")
        comment = " | ".join(comment_parts) if comment_parts else f"Managed by KMFlow ({layer_str} layer)"

        tblprops: list[str] = []
        if entry.retention_days:
            tblprops.append(f"    'delta.deletedFileRetentionDuration' = 'interval {entry.retention_days} days'")

        ddl_lines: list[str] = [
            f"CREATE TABLE IF NOT EXISTS {fqn} (",
        ]
        for col_line in columns:
            ddl_lines.append(f"    {col_line}")
        ddl_lines.append(")")
        ddl_lines.append("USING DELTA")
        ddl_lines.append(f"COMMENT '{_escape_sql_string(comment)}'")

        if tblprops:
            ddl_lines.append("TBLPROPERTIES (")
            ddl_lines.append(",\n".join(tblprops))
            ddl_lines.append(")")

        statements.append("\n".join(ddl_lines))

    return ";\n\n".join(statements)


def _safe_identifier(name: str) -> str:
    """Convert a dataset name to a safe SQL identifier.

    Replaces spaces and hyphens with underscores; strips non-alphanumeric
    characters (except underscores). Truncates to 255 characters.
    """
    safe = name.replace(" ", "_").replace("-", "_")
    safe = "".join(c for c in safe if c.isalnum() or c == "_")
    return safe[:255]


def _escape_sql_string(value: str) -> str:
    """Escape single quotes in a SQL string literal."""
    return value.replace("'", "''")


def _build_column_defs(schema_definition: dict[str, Any] | None) -> list[str]:
    """Build SQL column definition lines from a schema dict.

    Args:
        schema_definition: Mapping of column_name -> type_string, or ``None``.

    Returns:
        List of column definition strings, e.g.
        ``["id STRING NOT NULL", "size_bytes BIGINT"]``.
    """
    if not schema_definition:
        return ["id STRING NOT NULL", "created_at TIMESTAMP"]

    column_defs: list[str] = []
    for col_name, col_type in schema_definition.items():
        safe_col = _safe_identifier(col_name)
        sql_type = _map_column_type(str(col_type))
        column_defs.append(f"{safe_col} {sql_type}")

    return column_defs


# ---------------------------------------------------------------------------
# Table registration
# ---------------------------------------------------------------------------


def register_tables(
    client: Any,
    catalog_entries: list[DataCatalogEntry],
    catalog: str,
    schema: str,
    warehouse_id: str = "",
) -> dict[str, str]:
    """Bulk-register DataCatalogEntry records as Unity Catalog tables.

    Generates DDL for each entry and executes it against the Databricks SQL
    warehouse. Entries that fail to register are logged as warnings; a
    partial success is still returned.

    Args:
        client: A ``databricks.sdk.WorkspaceClient`` instance. Must be
            authenticated and have ``CREATE TABLE`` privilege on the target
            catalog and schema.
        catalog_entries: List of ``DataCatalogEntry`` ORM instances to register.
        catalog: Unity Catalog catalog name.
        schema: Base schema name (layer suffix appended automatically).
        warehouse_id: SQL warehouse ID for DDL execution. If empty, this
            function attempts to discover a running warehouse automatically.

    Returns:
        Dict mapping ``dataset_name`` -> ``"ok"`` or ``"error: {message}"``.

    Raises:
        ImportError: If ``databricks-sdk`` is not installed.
    """
    if not _HAS_DATABRICKS:
        raise ImportError(
            "databricks-sdk is required for register_tables. "
            "Install with: pip install 'kmflow[databricks]'"
        ) from None

    # Resolve warehouse ID if not supplied
    wh_id = warehouse_id or _discover_warehouse(client)

    results: dict[str, str] = {}

    for entry in catalog_entries:
        try:
            layer_raw = getattr(entry.layer, "value", str(entry.layer))
            layer_str = layer_raw.lower()
            uc_schema = _uc_schema_name(schema, layer_str)

            # Ensure the schema exists before creating the table
            _ensure_schema(client, wh_id, catalog, uc_schema)

            # Generate and execute single-table DDL
            single_entry_ddl = generate_unity_catalog_ddl([entry], catalog, schema)
            client.statement_execution.execute(
                warehouse_id=wh_id,
                statement=single_entry_ddl,
            )
            results[entry.dataset_name] = "ok"
            logger.info(
                "Registered Unity Catalog table: %s.%s.%s",
                catalog,
                uc_schema,
                entry.dataset_name,
            )
        except Exception as exc:
            error_msg = f"error: {exc}"
            results[entry.dataset_name] = error_msg
            logger.warning(
                "Failed to register table %s: %s",
                entry.dataset_name,
                exc,
            )

    return results


def _ensure_schema(client: Any, warehouse_id: str, catalog: str, schema: str) -> None:
    """Create a Unity Catalog schema if it does not already exist.

    Args:
        client: Authenticated ``WorkspaceClient``.
        warehouse_id: SQL warehouse ID for DDL execution.
        catalog: Catalog to create the schema in.
        schema: Schema name to create.
    """
    ddl = f"CREATE SCHEMA IF NOT EXISTS `{catalog}`.`{schema}`"
    try:
        client.statement_execution.execute(
            warehouse_id=warehouse_id,
            statement=ddl,
        )
    except Exception as exc:
        logger.warning("Could not ensure schema %s.%s: %s", catalog, schema, exc)


def _discover_warehouse(client: Any) -> str:
    """Return the ID of the first available SQL warehouse.

    Falls back to empty string if no warehouses are accessible.
    """
    try:
        warehouses = list(client.warehouses.list())
        for wh in warehouses:
            state = getattr(wh, "state", None)
            if state in ("RUNNING", "STOPPED", "STARTING"):
                return str(wh.id)
    except Exception as exc:
        logger.warning("Could not discover SQL warehouse: %s", exc)
    return ""
