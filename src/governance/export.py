"""Governance package export.

Produces a ZIP archive containing the full governance state for an
engagement: catalog entries, active policies, lineage summary, and
quality SLA compliance report.

The exported package is designed to be shared with clients as a
portable artifact.
"""

from __future__ import annotations

import io
import json
import logging
import uuid
import zipfile
from datetime import UTC, datetime
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import DataCatalogEntry, EvidenceLineage
from src.governance.policy import PolicyEngine
from src.governance.quality import check_quality_sla

logger = logging.getLogger(__name__)


def _json_default(obj: Any) -> Any:
    """JSON serializer for types not handled by stdlib json."""
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _serialize(data: Any) -> str:
    return json.dumps(data, default=_json_default, indent=2)


async def export_governance_package(
    session: AsyncSession,
    engagement_id: uuid.UUID,
) -> bytes:
    """Build and return a governance package ZIP for an engagement.

    The ZIP contains four JSON/YAML files:

    - ``catalog.json``: All DataCatalogEntry records for this engagement.
    - ``policies.yaml``: The active policy definitions.
    - ``lineage_summary.json``: Lineage chains for each catalog entry's
      engagement scope (via EvidenceLineage records).
    - ``quality_report.json``: SLA compliance results for each catalog entry.

    Args:
        session: Async database session.
        engagement_id: Scope the package to this engagement.

    Returns:
        ZIP file contents as bytes.
    """
    logger.info("Building governance package for engagement %s", engagement_id)

    # ------------------------------------------------------------------ #
    # 1. Catalog entries
    # ------------------------------------------------------------------ #
    result = await session.execute(select(DataCatalogEntry).where(DataCatalogEntry.engagement_id == engagement_id))
    entries: list[DataCatalogEntry] = list(result.scalars().all())

    catalog_data = [
        {
            "id": entry.id,
            "dataset_name": entry.dataset_name,
            "dataset_type": entry.dataset_type,
            "layer": entry.layer.value,
            "classification": entry.classification.value,
            "owner": entry.owner,
            "retention_days": entry.retention_days,
            "quality_sla": entry.quality_sla,
            "schema_definition": entry.schema_definition,
            "description": entry.description,
            "row_count": entry.row_count,
            "size_bytes": entry.size_bytes,
            "delta_table_path": entry.delta_table_path,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }
        for entry in entries
    ]

    # ------------------------------------------------------------------ #
    # 2. Active policies (YAML)
    # ------------------------------------------------------------------ #
    engine = PolicyEngine()
    policies_yaml = yaml.dump(engine.policies, default_flow_style=False)

    # ------------------------------------------------------------------ #
    # 3. Lineage summary
    # ------------------------------------------------------------------ #
    lineage_result = await session.execute(
        select(EvidenceLineage)
        .join(
            EvidenceLineage.evidence_item,
        )
        .where(EvidenceLineage.evidence_item.has(engagement_id=engagement_id))
    )
    lineage_records = list(lineage_result.scalars().all())

    lineage_data = [
        {
            "lineage_id": rec.id,
            "evidence_item_id": rec.evidence_item_id,
            "source_system": rec.source_system,
            "source_url": rec.source_url,
            "source_identifier": rec.source_identifier,
            "version": rec.version,
            "version_hash": rec.version_hash,
            "transformation_steps": len(rec.transformation_chain or []),
            "created_at": rec.created_at,
        }
        for rec in lineage_records
    ]

    lineage_summary = {
        "engagement_id": engagement_id,
        "total_lineage_records": len(lineage_data),
        "generated_at": datetime.now(UTC),
        "records": lineage_data,
    }

    # ------------------------------------------------------------------ #
    # 4. Quality report
    # ------------------------------------------------------------------ #
    quality_results = []
    for entry in entries:
        sla_result = await check_quality_sla(session, entry)
        quality_results.append(
            {
                "entry_id": entry.id,
                "dataset_name": entry.dataset_name,
                "layer": entry.layer.value,
                "passing": sla_result.passing,
                "evidence_count": sla_result.evidence_count,
                "checked_at": sla_result.checked_at,
                "violations": [
                    {
                        "metric": v.metric,
                        "threshold": v.threshold,
                        "actual": v.actual,
                        "message": v.message,
                    }
                    for v in sla_result.violations
                ],
            }
        )

    quality_report = {
        "engagement_id": engagement_id,
        "generated_at": datetime.now(UTC),
        "total_entries": len(entries),
        "passing_entries": sum(1 for r in quality_results if r["passing"]),
        "failing_entries": sum(1 for r in quality_results if not r["passing"]),
        "results": quality_results,
    }

    # ------------------------------------------------------------------ #
    # 5. Assemble ZIP
    # ------------------------------------------------------------------ #
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("catalog.json", _serialize(catalog_data))
        zf.writestr("policies.yaml", policies_yaml)
        zf.writestr("lineage_summary.json", _serialize(lineage_summary))
        zf.writestr("quality_report.json", _serialize(quality_report))

    buf.seek(0)
    pkg_bytes = buf.read()

    logger.info(
        "Governance package for engagement %s: %d bytes, %d catalog entries",
        engagement_id,
        len(pkg_bytes),
        len(entries),
    )
    return pkg_bytes
