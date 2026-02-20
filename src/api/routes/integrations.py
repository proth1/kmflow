"""Integration connector management routes.

Provides connection management API for external system connectors
with DB persistence, field mapping, and incremental sync support.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import IntegrationConnection, User
from src.core.permissions import require_permission
from src.integrations.base import ConnectionConfig, ConnectorRegistry
from src.integrations.field_mapping import get_default_mapping

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


# -- Request/Response Schemas ------------------------------------------------


class ConnectionCreate(BaseModel):
    """Schema for creating a connection."""

    engagement_id: UUID
    connector_type: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    config: dict[str, Any] = Field(default_factory=dict)
    field_mappings: dict[str, str] | None = None


class ConnectionUpdate(BaseModel):
    """Schema for updating a connection."""

    name: str | None = None
    config: dict[str, Any] | None = None
    field_mappings: dict[str, str] | None = None


class ConnectionResponse(BaseModel):
    """Schema for connection responses."""

    id: str
    engagement_id: str
    connector_type: str
    name: str
    status: str
    config: dict[str, Any]
    field_mappings: dict[str, str] | None = None
    last_sync: str | None = None
    last_sync_records: int = 0
    error_message: str | None = None


class ConnectionList(BaseModel):
    """Schema for listing connections."""

    items: list[ConnectionResponse]
    total: int


class TestResult(BaseModel):
    """Schema for connection test results."""

    connection_id: str
    success: bool
    message: str


class SyncResult(BaseModel):
    """Schema for sync results."""

    connection_id: str
    records_synced: int
    errors: list[str]


class FieldMappingResponse(BaseModel):
    """Schema for field mapping responses."""

    connector_type: str
    default_mapping: dict[str, str]
    current_mapping: dict[str, str] | None = None
    available_fields: list[str]


def _conn_to_response(conn: IntegrationConnection) -> dict[str, Any]:
    """Convert an IntegrationConnection model to response dict."""
    return {
        "id": str(conn.id),
        "engagement_id": str(conn.engagement_id),
        "connector_type": conn.connector_type,
        "name": conn.name,
        "status": conn.status,
        "config": conn.config_json or {},
        "field_mappings": conn.field_mappings,
        "last_sync": conn.last_sync_at.isoformat() if conn.last_sync_at else None,
        "last_sync_records": conn.last_sync_records,
        "error_message": conn.error_message,
    }


# -- Routes -------------------------------------------------------------------


@router.get("/connectors", response_model=list[dict[str, str]])
async def list_connectors(
    user: User = Depends(require_permission("engagement:read")),
) -> list[dict[str, str]]:
    """List available connector types."""
    return [
        {"type": name, "description": connector.description}
        for name, connector in ConnectorRegistry.list_connectors().items()
    ]


@router.post("/connections", response_model=ConnectionResponse, status_code=status.HTTP_201_CREATED)
async def create_connection(
    payload: ConnectionCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> dict[str, Any]:
    """Create a new integration connection (persisted to database)."""
    connector_cls = ConnectorRegistry.get(payload.connector_type)
    if not connector_cls:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown connector type: {payload.connector_type}. "
            f"Available: {list(ConnectorRegistry.list_connectors().keys())}",
        )

    mappings = payload.field_mappings
    if mappings is None:
        mappings = get_default_mapping(payload.connector_type)

    conn = IntegrationConnection(
        engagement_id=payload.engagement_id,
        connector_type=payload.connector_type,
        name=payload.name,
        status="configured",
        config_json=payload.config,
        field_mappings=mappings if mappings else None,
    )
    session.add(conn)
    await session.commit()
    await session.refresh(conn)
    return _conn_to_response(conn)


@router.get("/connections", response_model=ConnectionList)
async def list_connections(
    engagement_id: UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """List all connections, optionally filtered by engagement."""
    query = select(IntegrationConnection)
    count_query = select(func.count(IntegrationConnection.id))
    if engagement_id:
        query = query.where(IntegrationConnection.engagement_id == engagement_id)
        count_query = count_query.where(IntegrationConnection.engagement_id == engagement_id)
    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    items = [_conn_to_response(c) for c in result.scalars().all()]
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0
    return {"items": items, "total": total}


@router.get("/connections/{connection_id}", response_model=ConnectionResponse)
async def get_connection(
    connection_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Get a single connection by ID."""
    result = await session.execute(select(IntegrationConnection).where(IntegrationConnection.id == connection_id))
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Connection {connection_id} not found")
    return _conn_to_response(conn)


@router.patch("/connections/{connection_id}", response_model=ConnectionResponse)
async def update_connection(
    connection_id: UUID,
    payload: ConnectionUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> dict[str, Any]:
    """Update a connection's config or field mappings."""
    result = await session.execute(select(IntegrationConnection).where(IntegrationConnection.id == connection_id))
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Connection {connection_id} not found")

    if payload.name is not None:
        conn.name = payload.name
    if payload.config is not None:
        conn.config_json = payload.config
    if payload.field_mappings is not None:
        conn.field_mappings = payload.field_mappings

    await session.commit()
    await session.refresh(conn)
    return _conn_to_response(conn)


@router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(
    connection_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> None:
    """Delete a connection."""
    result = await session.execute(select(IntegrationConnection).where(IntegrationConnection.id == connection_id))
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Connection {connection_id} not found")
    await session.delete(conn)
    await session.commit()


@router.post("/connections/{connection_id}/test", response_model=TestResult)
async def test_connection(
    connection_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Test connectivity for an existing connection."""
    result = await session.execute(select(IntegrationConnection).where(IntegrationConnection.id == connection_id))
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Connection {connection_id} not found")

    connector_cls = ConnectorRegistry.get(conn.connector_type)
    if not connector_cls:
        return {"connection_id": str(connection_id), "success": False, "message": "Connector type not found"}

    config = ConnectionConfig(
        base_url=(conn.config_json or {}).get("base_url", ""),
        api_key=(conn.config_json or {}).get("api_key"),
        extra=conn.config_json or {},
    )
    connector = connector_cls(config)
    try:
        success = await connector.test_connection()
        conn.status = "connected" if success else "error"
        await session.commit()
        return {
            "connection_id": str(connection_id),
            "success": success,
            "message": "Connection successful" if success else "Connection failed",
        }
    except Exception as e:
        conn.status = "error"
        conn.error_message = str(e)
        await session.commit()
        return {"connection_id": str(connection_id), "success": False, "message": str(e)}


@router.post("/connections/{connection_id}/sync", response_model=SyncResult)
async def sync_connection(
    connection_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> dict[str, Any]:
    """Trigger a data sync for a connection."""
    result = await session.execute(select(IntegrationConnection).where(IntegrationConnection.id == connection_id))
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Connection {connection_id} not found")

    connector_cls = ConnectorRegistry.get(conn.connector_type)
    if not connector_cls:
        return {"connection_id": str(connection_id), "records_synced": 0, "errors": ["Connector type not found"]}

    config = ConnectionConfig(
        base_url=(conn.config_json or {}).get("base_url", ""),
        api_key=(conn.config_json or {}).get("api_key"),
        extra=conn.config_json or {},
    )
    connector = connector_cls(config)
    try:
        sync_result = await connector.sync_data(
            engagement_id=str(conn.engagement_id),
            db_session=session,
        )
        conn.last_sync_at = datetime.now(UTC)
        conn.last_sync_records = sync_result.get("records_synced", 0)
        conn.status = "connected"
        conn.error_message = None
        await session.commit()
        return {
            "connection_id": str(connection_id),
            "records_synced": sync_result.get("records_synced", 0),
            "errors": sync_result.get("errors", []),
        }
    except Exception as e:
        conn.status = "error"
        conn.error_message = str(e)
        await session.commit()
        return {"connection_id": str(connection_id), "records_synced": 0, "errors": [str(e)]}


@router.get("/connections/{connection_id}/field-mapping", response_model=FieldMappingResponse)
async def get_field_mapping(
    connection_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Get field mapping config for a connection."""
    result = await session.execute(select(IntegrationConnection).where(IntegrationConnection.id == connection_id))
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Connection {connection_id} not found")

    connector_cls = ConnectorRegistry.get(conn.connector_type)
    available_fields: list[str] = []
    if connector_cls:
        config = ConnectionConfig(
            base_url=(conn.config_json or {}).get("base_url", ""),
            api_key=(conn.config_json or {}).get("api_key"),
            extra=conn.config_json or {},
        )
        connector = connector_cls(config)
        available_fields = await connector.get_schema()

    return {
        "connector_type": conn.connector_type,
        "default_mapping": get_default_mapping(conn.connector_type),
        "current_mapping": conn.field_mappings,
        "available_fields": available_fields,
    }


@router.put("/connections/{connection_id}/field-mapping", response_model=FieldMappingResponse)
async def update_field_mapping(
    connection_id: UUID,
    mapping: dict[str, str],
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> dict[str, Any]:
    """Update field mapping for a connection."""
    result = await session.execute(select(IntegrationConnection).where(IntegrationConnection.id == connection_id))
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Connection {connection_id} not found")

    conn.field_mappings = mapping
    await session.commit()
    await session.refresh(conn)

    connector_cls = ConnectorRegistry.get(conn.connector_type)
    available_fields: list[str] = []
    if connector_cls:
        config = ConnectionConfig(
            base_url=(conn.config_json or {}).get("base_url", ""),
            api_key=(conn.config_json or {}).get("api_key"),
            extra=conn.config_json or {},
        )
        connector = connector_cls(config)
        available_fields = await connector.get_schema()

    return {
        "connector_type": conn.connector_type,
        "default_mapping": get_default_mapping(conn.connector_type),
        "current_mapping": conn.field_mappings,
        "available_fields": available_fields,
    }
