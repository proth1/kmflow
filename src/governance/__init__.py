"""KMFlow Governance module (Phase F stub).

Provides Unity Catalog integration for registering data assets in
Databricks. The full governance implementation (data quality, lineage
dashboards, access policy enforcement) is developed in Phase D.
"""

from src.governance.unity_catalog import (
    generate_unity_catalog_ddl,
    register_tables,
)

__all__ = [
    "generate_unity_catalog_ddl",
    "register_tables",
]
