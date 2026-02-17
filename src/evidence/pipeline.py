"""Evidence processing pipeline.

Orchestrates the upload -> classify -> parse -> fragment -> store workflow
for evidence files. Runs as async tasks after file upload.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import (
    AuditAction,
    AuditLog,
    EvidenceCategory,
    EvidenceFragment,
    EvidenceItem,
)
from src.evidence.parsers.base import ParseResult
from src.evidence.parsers.factory import classify_by_extension, detect_format, parse_file

logger = logging.getLogger(__name__)

# Default storage directory (relative to project root)
DEFAULT_EVIDENCE_STORE = "evidence_store"


def compute_content_hash(file_content: bytes) -> str:
    """Compute SHA-256 hash of file content for integrity verification.

    Args:
        file_content: The raw bytes of the file.

    Returns:
        Hex-encoded SHA-256 hash string (64 characters).
    """
    return hashlib.sha256(file_content).hexdigest()


async def check_duplicate(session: AsyncSession, content_hash: str, engagement_id: uuid.UUID) -> uuid.UUID | None:
    """Check if a file with the same hash already exists in the engagement.

    Args:
        session: Database session.
        content_hash: SHA-256 hash of the file content.
        engagement_id: The engagement to check within.

    Returns:
        The UUID of the existing evidence item if a duplicate is found, else None.
    """
    result = await session.execute(
        select(EvidenceItem.id).where(
            EvidenceItem.engagement_id == engagement_id,
            EvidenceItem.content_hash == content_hash,
        )
    )
    existing = result.scalar_one_or_none()
    return existing


async def store_file(
    file_content: bytes,
    file_name: str,
    engagement_id: uuid.UUID,
    evidence_store: str = DEFAULT_EVIDENCE_STORE,
) -> str:
    """Store an uploaded file to the local filesystem.

    Files are organized by engagement_id for easy management.

    Args:
        file_content: The raw bytes of the file.
        file_name: Original filename.
        engagement_id: The engagement this evidence belongs to.
        evidence_store: Base directory for evidence storage.

    Returns:
        The relative file path where the file was stored.
    """
    # Create directory structure: evidence_store/{engagement_id}/
    engagement_dir = Path(evidence_store) / str(engagement_id)
    engagement_dir.mkdir(parents=True, exist_ok=True)

    # Use a unique filename to avoid collisions
    unique_name = f"{uuid.uuid4().hex[:8]}_{file_name}"
    file_path = engagement_dir / unique_name

    with open(file_path, "wb") as f:
        f.write(file_content)

    return str(file_path)


async def process_evidence(
    session: AsyncSession,
    evidence_item: EvidenceItem,
) -> list[EvidenceFragment]:
    """Run the parsing pipeline on an evidence item.

    Parses the file, creates fragments, and stores them in the database.

    Args:
        session: Database session.
        evidence_item: The evidence item to process (must have file_path set).

    Returns:
        List of created EvidenceFragment records.
    """
    if not evidence_item.file_path or not os.path.exists(evidence_item.file_path):
        logger.warning("Evidence item %s has no valid file path", evidence_item.id)
        return []

    # Parse the file
    parse_result: ParseResult = await parse_file(evidence_item.file_path, evidence_item.name)

    if parse_result.error:
        logger.warning("Parse error for %s: %s", evidence_item.name, parse_result.error)

    # Create fragment records
    fragments: list[EvidenceFragment] = []
    for parsed_frag in parse_result.fragments:
        fragment = EvidenceFragment(
            evidence_id=evidence_item.id,
            fragment_type=parsed_frag.fragment_type,
            content=parsed_frag.content,
            metadata_json=json.dumps(parsed_frag.metadata) if parsed_frag.metadata else None,
        )
        session.add(fragment)
        fragments.append(fragment)

    return fragments


async def ingest_evidence(
    session: AsyncSession,
    engagement_id: uuid.UUID,
    file_content: bytes,
    file_name: str,
    category: EvidenceCategory | None = None,
    metadata: dict | None = None,
    mime_type: str | None = None,
    evidence_store: str = DEFAULT_EVIDENCE_STORE,
) -> tuple[EvidenceItem, list[EvidenceFragment], uuid.UUID | None]:
    """Full evidence ingestion pipeline: upload -> classify -> parse -> store.

    This is the main entry point for evidence ingestion.

    Args:
        session: Database session.
        engagement_id: The engagement to attach evidence to.
        file_content: Raw file bytes.
        file_name: Original filename.
        category: Evidence category (auto-detected if not provided).
        metadata: Additional metadata JSON.
        mime_type: MIME type of the file.
        evidence_store: Base directory for file storage.

    Returns:
        Tuple of (evidence_item, fragments, duplicate_of_id).
        duplicate_of_id is set if the file is a duplicate.
    """
    # Step 1: Compute content hash
    content_hash = compute_content_hash(file_content)

    # Step 2: Check for duplicates
    duplicate_of_id = await check_duplicate(session, content_hash, engagement_id)

    # Step 3: Auto-classify if category not provided
    if category is None:
        detected = classify_by_extension(file_name)
        category = EvidenceCategory(detected) if detected else EvidenceCategory.DOCUMENTS

    # Step 4: Detect format
    file_format = detect_format(file_name)

    # Step 5: Store file
    file_path = await store_file(file_content, file_name, engagement_id, evidence_store)

    # Step 6: Create evidence item
    evidence_item = EvidenceItem(
        engagement_id=engagement_id,
        name=file_name,
        category=category,
        format=file_format,
        content_hash=content_hash,
        file_path=file_path,
        size_bytes=len(file_content),
        mime_type=mime_type,
        metadata_json=metadata,
        duplicate_of_id=duplicate_of_id,
    )
    session.add(evidence_item)
    await session.flush()

    # Step 7: Parse and create fragments
    fragments = await process_evidence(session, evidence_item)

    # Step 8: Audit log
    audit = AuditLog(
        engagement_id=engagement_id,
        action=AuditAction.EVIDENCE_UPLOADED,
        details=json.dumps(
            {
                "evidence_id": str(evidence_item.id),
                "file_name": file_name,
                "category": str(category),
                "content_hash": content_hash,
                "is_duplicate": duplicate_of_id is not None,
            }
        ),
    )
    session.add(audit)

    return evidence_item, fragments, duplicate_of_id
