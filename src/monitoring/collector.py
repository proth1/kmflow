"""Evidence collection from integration connectors.

Pulls data from configured connectors and stores as evidence items,
applying field mappings and quality scoring.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.integrations.base import ConnectionConfig, ConnectorRegistry
from src.integrations.field_mapping import apply_field_mapping

logger = logging.getLogger(__name__)


async def collect_evidence(
    connector_type: str,
    config: dict[str, Any],
    engagement_id: str,
    field_mappings: dict[str, str] | None = None,
    incremental: bool = False,
    since: str | None = None,
) -> dict[str, Any]:
    """Collect evidence from an integration connector.

    Args:
        connector_type: Type of connector (salesforce, sap, etc.).
        config: Connection configuration.
        engagement_id: Engagement to associate evidence with.
        field_mappings: Optional field mapping overrides.
        incremental: Whether to do incremental sync.
        since: Timestamp for incremental sync.

    Returns:
        Collection result with records_collected and any errors.
    """
    connector_cls = ConnectorRegistry.get(connector_type)
    if not connector_cls:
        return {
            "records_collected": 0,
            "errors": [f"Unknown connector type: {connector_type}"],
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

    conn_config = ConnectionConfig(
        base_url=config.get("base_url", ""),
        api_key=config.get("api_key"),
        extra=config,
    )
    connector = connector_cls(conn_config)

    try:
        if incremental and hasattr(connector, "sync_incremental"):
            result = await connector.sync_incremental(
                engagement_id=engagement_id, since=since
            )
        else:
            result = await connector.sync_data(engagement_id=engagement_id)

        records = result.get("raw_records", [])
        if field_mappings and records:
            records = [apply_field_mapping(r, field_mappings) for r in records]

        return {
            "records_collected": result.get("records_synced", 0),
            "mapped_records": len(records),
            "errors": result.get("errors", []),
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.exception("Evidence collection failed for %s", connector_type)
        return {
            "records_collected": 0,
            "errors": [str(e)],
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }
