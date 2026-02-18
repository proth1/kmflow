"""Abstract base connector for external system integrations.

Provides the interface and connection lifecycle management for
all integration connectors (Celonis, Soroco, etc.).
"""

from __future__ import annotations

import abc
import enum
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class ConnectionStatus(enum.StrEnum):
    """Status of a connector connection."""

    CONFIGURED = "configured"
    CONNECTED = "connected"
    ERROR = "error"
    DISCONNECTED = "disconnected"


@dataclass
class ConnectionConfig:
    """Configuration for a connector connection.

    Attributes:
        base_url: The base URL for the external API.
        api_key: Optional API key for authentication.
        extra: Additional configuration parameters.
    """

    base_url: str = ""
    api_key: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class BaseConnector(abc.ABC):
    """Abstract base class for integration connectors.

    Subclasses must implement:
    - description: Class-level string describing the connector.
    - test_connection(): Verify connectivity.
    - sync_data(): Pull data from the external system.
    """

    description: str = "Base connector"

    def __init__(self, config: ConnectionConfig) -> None:
        self._config = config

    @abc.abstractmethod
    async def test_connection(self) -> bool:
        """Test connectivity to the external system.

        Returns:
            True if the connection is successful.
        """
        ...

    @abc.abstractmethod
    async def sync_data(self, engagement_id: str, **kwargs: Any) -> dict[str, Any]:
        """Sync data from the external system.

        Args:
            engagement_id: The engagement to sync data for.
            **kwargs: Additional sync parameters.

        Returns:
            Dict with 'records_synced' count and optional 'errors' list.
        """
        ...

    async def get_schema(self) -> list[str]:
        """Return available source fields for field mapping.

        Returns:
            List of field names available from the external system.
        """
        return []

    async def sync_incremental(
        self, engagement_id: str, since: str | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        """Incremental sync - only records modified since a timestamp.

        Default implementation falls back to full sync.
        """
        return await self.sync_data(engagement_id, **kwargs)

    async def disconnect(self) -> None:  # noqa: B027
        """Clean up connection resources."""


class ConnectorRegistry:
    """Registry of available connector types."""

    _connectors: dict[str, type[BaseConnector]] = {}

    @classmethod
    def register(cls, name: str, connector_cls: type[BaseConnector]) -> None:
        """Register a connector type."""
        cls._connectors[name] = connector_cls

    @classmethod
    def get(cls, name: str) -> type[BaseConnector] | None:
        """Get a connector class by name."""
        return cls._connectors.get(name)

    @classmethod
    def list_connectors(cls) -> dict[str, type[BaseConnector]]:
        """List all registered connectors."""
        return dict(cls._connectors)


def _register_builtin_connectors() -> None:
    """Register built-in connectors."""
    from src.integrations.celonis import CelonisConnector
    from src.integrations.salesforce import SalesforceConnector
    from src.integrations.sap import SAPConnector
    from src.integrations.servicenow import ServiceNowConnector
    from src.integrations.soroco import SorocoConnector

    ConnectorRegistry.register("celonis", CelonisConnector)
    ConnectorRegistry.register("soroco", SorocoConnector)
    ConnectorRegistry.register("salesforce", SalesforceConnector)
    ConnectorRegistry.register("sap", SAPConnector)
    ConnectorRegistry.register("servicenow", ServiceNowConnector)


_register_builtin_connectors()
