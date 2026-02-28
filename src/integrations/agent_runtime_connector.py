"""Category E connector for AI agent runtime tool call ingestion.

Captures structured tool call events from AI agent frameworks (LangChain,
AutoGen, CrewAI, etc.) and maps them to the canonical event spine for
correlation with human process activities.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.integrations.base_connector import BaseConnector

logger = logging.getLogger(__name__)

# Default field mapping from common agent frameworks to canonical schema
DEFAULT_AGENT_FIELD_MAP: dict[str, str] = {
    "tool_name": "activity_name",
    "invocation_id": "case_id",
    "timestamp": "timestamp_utc",
    "agent_name": "performer_role_ref",
    "input_data": "raw_payload",
}


class AgentRuntimeConnector(BaseConnector):
    """Connector for AI agent tool call event ingestion (Category E).

    Ingests structured events from agent orchestration frameworks and
    maps them to the canonical event spine. Supports LangChain callbacks,
    AutoGen message logs, and generic JSON tool call records.

    Attributes:
        connector_type: Identifier for this connector class.
        config: Configuration dict with endpoint, auth, and field mapping.
    """

    connector_type = "agent_runtime"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._field_map = config.get("field_map", DEFAULT_AGENT_FIELD_MAP)
        self._framework = config.get("framework", "generic")

    async def test_connection(self) -> bool:
        """Verify connectivity to the agent runtime endpoint."""
        endpoint = self.config.get("endpoint")
        if not endpoint:
            logger.warning("No endpoint configured for agent runtime connector")
            return False
        # For push-based ingestion, connection test verifies config validity
        return True

    async def get_schema(self) -> list[str]:
        """Return the expected fields for this connector's events."""
        return list(self._field_map.keys())

    async def sync_data(
        self,
        engagement_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Ingest agent tool call events.

        Accepts a list of tool call records and maps them to canonical events.

        Args:
            engagement_id: Target engagement.
            **kwargs: Must include 'events' (list of tool call dicts).

        Returns:
            Dict with records_synced count and any errors.
        """
        events = kwargs.get("events", [])
        if not events:
            return {"records_synced": 0, "errors": []}

        mapped_events = []
        errors: list[str] = []

        for i, event in enumerate(events):
            try:
                mapped = self._map_event(event, engagement_id)
                mapped_events.append(mapped)
            except (KeyError, ValueError) as exc:
                errors.append(f"Event {i}: {exc}")

        return {
            "records_synced": len(mapped_events),
            "mapped_events": mapped_events,
            "errors": errors,
        }

    async def sync_incremental(
        self,
        engagement_id: str,
        since: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Incremental sync — filters events by timestamp."""
        events = kwargs.get("events", [])
        if since and events:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            events = [
                e
                for e in events
                if datetime.fromisoformat(str(e.get("timestamp", "")).replace("Z", "+00:00")) > since_dt
            ]
        return await self.sync_data(engagement_id, events=events, **kwargs)

    async def disconnect(self) -> None:
        """No persistent connection to close for push-based connector."""

    def _map_event(self, event: dict[str, Any], engagement_id: str) -> dict[str, Any]:
        """Map a raw agent tool call to canonical event format."""
        mapped: dict[str, Any] = {"engagement_id": engagement_id}

        for src_field, dest_field in self._field_map.items():
            if src_field in event:
                mapped[dest_field] = event[src_field]

        # Ensure required canonical fields
        if "activity_name" not in mapped:
            mapped["activity_name"] = event.get("tool_name", event.get("action", "unknown_tool"))
        if "timestamp_utc" not in mapped:
            mapped["timestamp_utc"] = datetime.now(UTC).isoformat()
        if "source_system" not in mapped:
            mapped["source_system"] = f"agent_runtime:{self._framework}"

        # Preserve full raw event
        mapped["raw_payload"] = event
        mapped["confidence_score"] = 0.9  # Agent tool calls are high-confidence
        mapped["brightness"] = "bright"

        return mapped
