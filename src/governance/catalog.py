"""Data catalog CRUD service for governance.

Manages DataCatalogEntry records: creation, retrieval, filtering by
medallion layer and classification, and classification updates.
All operations use async SQLAlchemy sessions.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import DataCatalogEntry, DataClassification, DataLayer

logger = logging.getLogger(__name__)


class DataCatalogService:
    """CRUD service for data catalog entries.

    Provides async methods for managing DataCatalogEntry records.
    Designed to be instantiated per-request or used as a stateless
    helper via its methods directly.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_entry(
        self,
        dataset_name: str,
        dataset_type: str,
        layer: DataLayer,
        engagement_id: uuid.UUID | None = None,
        schema_definition: dict[str, Any] | None = None,
        owner: str | None = None,
        classification: DataClassification = DataClassification.INTERNAL,
        quality_sla: dict[str, Any] | None = None,
        retention_days: int | None = None,
        description: str | None = None,
    ) -> DataCatalogEntry:
        """Create a new data catalog entry.

        Args:
            dataset_name: Name of the dataset (should follow naming_convention policy).
            dataset_type: Type identifier (e.g., 'evidence', 'process_model').
            layer: Medallion layer (bronze/silver/gold).
            engagement_id: Optional engagement scope.
            schema_definition: JSON schema for the dataset.
            owner: Dataset owner (team or person).
            classification: Data sensitivity classification.
            quality_sla: Quality SLA thresholds as a dict.
            retention_days: How long to retain this dataset.
            description: Human-readable description.

        Returns:
            The created DataCatalogEntry.
        """
        entry = DataCatalogEntry(
            dataset_name=dataset_name,
            dataset_type=dataset_type,
            layer=layer,
            engagement_id=engagement_id,
            schema_definition=schema_definition,
            owner=owner,
            classification=classification,
            quality_sla=quality_sla,
            retention_days=retention_days,
            description=description,
        )
        self._session.add(entry)
        await self._session.flush()

        logger.info(
            "Created catalog entry %s: '%s' (%s/%s)",
            entry.id,
            dataset_name,
            layer.value,
            classification.value,
        )
        return entry

    async def get_entry(self, entry_id: uuid.UUID) -> DataCatalogEntry | None:
        """Get a single catalog entry by ID.

        Args:
            entry_id: The catalog entry UUID.

        Returns:
            The DataCatalogEntry, or None if not found.
        """
        result = await self._session.execute(
            select(DataCatalogEntry).where(DataCatalogEntry.id == entry_id)
        )
        return result.scalar_one_or_none()

    async def list_entries(
        self,
        engagement_id: uuid.UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DataCatalogEntry]:
        """List catalog entries with optional engagement filter.

        Args:
            engagement_id: Optional engagement scope to filter by.
            limit: Maximum entries to return.
            offset: Pagination offset.

        Returns:
            List of DataCatalogEntry records.
        """
        query = select(DataCatalogEntry).order_by(DataCatalogEntry.created_at.desc())

        if engagement_id is not None:
            query = query.where(DataCatalogEntry.engagement_id == engagement_id)

        query = query.limit(limit).offset(offset)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def update_entry(
        self,
        entry_id: uuid.UUID,
        **fields: Any,
    ) -> DataCatalogEntry | None:
        """Update fields on an existing catalog entry.

        Only the fields passed as keyword arguments are updated.
        Unknown or immutable fields (id, created_at) are ignored.

        Args:
            entry_id: The entry to update.
            **fields: Field names and new values.

        Returns:
            Updated DataCatalogEntry, or None if not found.
        """
        entry = await self.get_entry(entry_id)
        if entry is None:
            return None

        # Immutable fields that callers should not overwrite
        _immutable = {"id", "created_at"}
        for field_name, value in fields.items():
            if field_name in _immutable:
                continue
            if hasattr(entry, field_name):
                setattr(entry, field_name, value)

        await self._session.flush()
        logger.info("Updated catalog entry %s", entry_id)
        return entry

    async def delete_entry(self, entry_id: uuid.UUID) -> bool:
        """Delete a catalog entry.

        Args:
            entry_id: The entry to delete.

        Returns:
            True if deleted, False if not found.
        """
        entry = await self.get_entry(entry_id)
        if entry is None:
            return False

        await self._session.delete(entry)
        await self._session.flush()
        logger.info("Deleted catalog entry %s", entry_id)
        return True

    async def classify_entry(
        self,
        entry_id: uuid.UUID,
        classification: DataClassification,
    ) -> DataCatalogEntry | None:
        """Update the data classification of a catalog entry.

        Args:
            entry_id: The entry to classify.
            classification: The new classification level.

        Returns:
            Updated DataCatalogEntry, or None if not found.
        """
        return await self.update_entry(entry_id, classification=classification)

    async def get_entries_by_layer(
        self,
        layer: DataLayer,
        engagement_id: uuid.UUID | None = None,
    ) -> list[DataCatalogEntry]:
        """Get all catalog entries in a given medallion layer.

        Args:
            layer: The medallion layer to filter by.
            engagement_id: Optional engagement scope.

        Returns:
            List of matching DataCatalogEntry records.
        """
        query = select(DataCatalogEntry).where(DataCatalogEntry.layer == layer)

        if engagement_id is not None:
            query = query.where(DataCatalogEntry.engagement_id == engagement_id)

        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_entries_by_classification(
        self,
        classification: DataClassification,
        engagement_id: uuid.UUID | None = None,
    ) -> list[DataCatalogEntry]:
        """Get all catalog entries with a given classification.

        Args:
            classification: The data classification to filter by.
            engagement_id: Optional engagement scope.

        Returns:
            List of matching DataCatalogEntry records.
        """
        query = select(DataCatalogEntry).where(
            DataCatalogEntry.classification == classification
        )

        if engagement_id is not None:
            query = query.where(DataCatalogEntry.engagement_id == engagement_id)

        result = await self._session.execute(query)
        return list(result.scalars().all())
