"""Data Governance Framework for KMFlow.

Provides catalog management, policy enforcement, SLA checking,
governance package export, and Unity Catalog integration for
registering data assets in Databricks.
"""

from __future__ import annotations

from src.governance.catalog import DataCatalogService
from src.governance.export import export_governance_package
from src.governance.policy import PolicyEngine, PolicyViolation
from src.governance.quality import SLAResult, check_quality_sla
from src.governance.unity_catalog import (
    generate_unity_catalog_ddl,
    register_tables,
)

__all__ = [
    "DataCatalogService",
    "PolicyEngine",
    "PolicyViolation",
    "SLAResult",
    "check_quality_sla",
    "export_governance_package",
    "generate_unity_catalog_ddl",
    "register_tables",
]
