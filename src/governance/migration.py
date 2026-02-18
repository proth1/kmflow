"""Bulk migration job to populate Bronze and Silver Delta tables retroactively.

Migrates existing EvidenceItem records for an engagement into the medallion
architecture: writes raw files to Bronze storage, creates EvidenceLineage
records if absent, writes fragments/entities to Silver, and creates
DataCatalogEntry records if absent.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import (
    DataCatalogEntry,
    DataClassification,
    DataLayer,
    EvidenceItem,
    EvidenceLineage,
)
from src.datalake.backend import StorageBackend, StorageMetadata
from src.datalake.lineage import create_lineage_record
from src.datalake.silver import SilverLayerWriter
from src.governance.catalog import DataCatalogService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class MigrationResult:
    """Summary of a bulk migration run.

    Attributes:
        engagement_id: The engagement that was migrated.
        items_processed: Number of evidence items successfully processed.
        items_skipped: Number of items skipped (already migrated).
        items_failed: Number of items that raised errors.
        bronze_written: Number of files written to Bronze storage.
        silver_written: Number of Silver layer write operations completed.
        catalog_entries_created: Number of new DataCatalogEntry records.
        lineage_records_created: Number of new EvidenceLineage records.
        errors: List of error messages from failed items.
        dry_run: Whether this was a dry-run (no writes committed).
    """

    engagement_id: str
    items_processed: int = 0
    items_skipped: int = 0
    items_failed: int = 0
    bronze_written: int = 0
    silver_written: int = 0
    catalog_entries_created: int = 0
    lineage_records_created: int = 0
    errors: list[str] = field(default_factory=list)
    dry_run: bool = False


# ---------------------------------------------------------------------------
# Migration helpers
# ---------------------------------------------------------------------------


async def _has_lineage(session: AsyncSession, evidence_item: EvidenceItem) -> bool:
    """Return True if a lineage record already exists for *evidence_item*."""
    result = await session.execute(
        select(EvidenceLineage).where(
            EvidenceLineage.evidence_item_id == evidence_item.id
        )
    )
    return result.scalar_one_or_none() is not None


async def _has_catalog_entry(
    session: AsyncSession,
    evidence_item: EvidenceItem,
) -> bool:
    """Return True if a DataCatalogEntry already exists for *evidence_item*."""
    dataset_name = f"evidence_{evidence_item.id}"
    result = await session.execute(
        select(DataCatalogEntry).where(
            DataCatalogEntry.dataset_name == dataset_name,
            DataCatalogEntry.engagement_id == evidence_item.engagement_id,
        )
    )
    return result.scalar_one_or_none() is not None


def _build_fragments_from_item(evidence_item: EvidenceItem) -> list[dict[str, Any]]:
    """Build synthetic fragment records from an EvidenceItem for Silver writes.

    Generates a minimal text fragment representing the evidence item's
    name and category so that Silver tables are populated even when
    the full intelligence pipeline has not been run.
    """
    return [
        {
            "id": str(uuid.uuid4()),
            "fragment_type": "text",
            "content": f"{evidence_item.name} [{evidence_item.category}]",
            "metadata_json": {
                "migrated": True,
                "source": "migration_job",
                "evidence_name": evidence_item.name,
                "category": str(evidence_item.category),
            },
        }
    ]


def _quality_scores_from_item(evidence_item: EvidenceItem) -> dict[str, float]:
    """Extract quality dimension scores from an EvidenceItem."""
    return {
        "completeness": evidence_item.completeness_score or 0.0,
        "reliability": evidence_item.reliability_score or 0.0,
        "freshness": evidence_item.freshness_score or 0.0,
        "consistency": evidence_item.consistency_score or 0.0,
    }


# ---------------------------------------------------------------------------
# Core migration function
# ---------------------------------------------------------------------------


async def migrate_engagement(
    session: AsyncSession,
    engagement_id: str,
    storage_backend: StorageBackend,
    silver_writer: SilverLayerWriter,
    *,
    dry_run: bool = False,
) -> MigrationResult:
    """Migrate all existing evidence for an engagement to Delta Lake layers.

    For each EvidenceItem in the engagement:
    1. Read the file from the local filesystem (``evidence_store/{engagement_id}/``).
    2. Write to Bronze via ``storage_backend.write()`` if not already stored
       (determined by whether ``delta_path`` is set on the item).
    3. Create an EvidenceLineage record if none exists.
    4. Write fragments/quality events to Silver layer.
    5. Create a DataCatalogEntry for the evidence item if none exists.

    In dry-run mode, all steps are simulated without writing to storage,
    the database, or Silver tables.

    Args:
        session: Async database session.
        engagement_id: The engagement UUID as a string.
        storage_backend: Bronze storage backend implementation.
        silver_writer: Silver layer writer for fragment/quality events.
        dry_run: If True, simulate the migration without persisting anything.

    Returns:
        MigrationResult summarising what was processed, skipped, and failed.
    """
    result = MigrationResult(engagement_id=engagement_id, dry_run=dry_run)

    try:
        eng_uuid = uuid.UUID(engagement_id)
    except ValueError:
        result.errors.append(f"Invalid engagement_id: {engagement_id}")
        result.items_failed += 1
        return result

    # Fetch all evidence items for the engagement
    rows = await session.execute(
        select(EvidenceItem).where(EvidenceItem.engagement_id == eng_uuid)
    )
    items: list[EvidenceItem] = list(rows.scalars().all())

    logger.info(
        "Starting migration for engagement %s: %d evidence items (dry_run=%s)",
        engagement_id,
        len(items),
        dry_run,
    )

    catalog_svc = DataCatalogService(session)

    for item in items:
        item_id_str = str(item.id)
        try:
            await _migrate_item(
                session=session,
                item=item,
                engagement_id=engagement_id,
                storage_backend=storage_backend,
                silver_writer=silver_writer,
                catalog_svc=catalog_svc,
                result=result,
                dry_run=dry_run,
            )
        except Exception as exc:
            error_msg = f"Failed to migrate evidence item {item_id_str}: {exc!r}"
            logger.warning(error_msg)
            result.errors.append(error_msg)
            result.items_failed += 1
            # Roll back partial changes for this item; continue with next
            try:
                await session.rollback()
            except Exception:
                pass

    if not dry_run:
        await session.commit()

    logger.info(
        "Migration complete for engagement %s: processed=%d skipped=%d failed=%d",
        engagement_id,
        result.items_processed,
        result.items_skipped,
        result.items_failed,
    )
    return result


async def _migrate_item(
    session: AsyncSession,
    item: EvidenceItem,
    engagement_id: str,
    storage_backend: StorageBackend,
    silver_writer: SilverLayerWriter,
    catalog_svc: DataCatalogService,
    result: MigrationResult,
    dry_run: bool,
) -> None:
    """Process migration for a single EvidenceItem."""
    item_id_str = str(item.id)
    already_in_bronze = bool(item.delta_path)

    # --- Step 1: Bronze write ---
    if not already_in_bronze:
        content = _read_local_file(item, engagement_id)
        if content is not None and not dry_run:
            meta: StorageMetadata = await storage_backend.write(
                engagement_id=engagement_id,
                file_name=item.name,
                content=content,
                metadata={
                    "evidence_item_id": item_id_str,
                    "category": str(item.category),
                    "migrated": True,
                },
            )
            item.delta_path = meta.path
            result.bronze_written += 1
        elif content is not None:
            # dry_run: count but don't write
            result.bronze_written += 1
    # already in bronze — delta_path is set, nothing to do

    # --- Step 2: Lineage record ---
    has_lineage = await _has_lineage(session, item)
    if not has_lineage:
        if not dry_run:
            await create_lineage_record(
                session=session,
                evidence_item=item,
                source_system="migration_job",
                source_identifier=item_id_str,
            )
        result.lineage_records_created += 1

    # --- Step 3: Silver write ---
    if not dry_run:
        fragments = _build_fragments_from_item(item)
        await silver_writer.write_fragments(
            engagement_id=engagement_id,
            evidence_item_id=item_id_str,
            fragments=fragments,
        )
        scores = _quality_scores_from_item(item)
        await silver_writer.write_quality_event(
            engagement_id=engagement_id,
            evidence_item_id=item_id_str,
            scores=scores,
        )
    result.silver_written += 1

    # --- Step 4: Catalog entry ---
    has_catalog = await _has_catalog_entry(session, item)
    if not has_catalog:
        if not dry_run:
            await catalog_svc.create_entry(
                dataset_name=f"evidence_{item.id}",
                dataset_type="evidence",
                layer=DataLayer.BRONZE,
                engagement_id=item.engagement_id,
                owner="migration_job",
                classification=DataClassification.INTERNAL,
                description=(
                    f"Migrated evidence item: {item.name} "
                    f"(category={item.category})"
                ),
            )
        result.catalog_entries_created += 1

    if already_in_bronze and has_lineage and has_catalog:
        result.items_skipped += 1
    else:
        result.items_processed += 1


def _read_local_file(item: EvidenceItem, engagement_id: str) -> bytes | None:
    """Attempt to read the raw evidence file from the local filesystem.

    Looks in ``evidence_store/{engagement_id}/`` for a file matching
    ``item.file_path`` or ``item.name``. Returns None if not found so
    the migration can continue (skipping the Bronze write for this item).
    """
    # Try the stored file_path first
    if item.file_path:
        candidate = Path(item.file_path)
        if candidate.exists():
            try:
                return candidate.read_bytes()
            except OSError:
                pass

    # Fall back to evidence_store convention
    evidence_dir = Path("evidence_store") / engagement_id
    for candidate_name in (item.name, Path(item.name).name):
        candidate = evidence_dir / candidate_name
        if candidate.exists():
            try:
                return candidate.read_bytes()
            except OSError:
                pass

    logger.debug(
        "Local file not found for evidence item %s (%s); skipping Bronze write",
        item.id,
        item.name,
    )
    return None
