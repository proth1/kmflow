"""Seed list pipeline service (Story #321).

Implements the 4-stage seed list pipeline:
1. Consultant vocabulary upload (manual seed terms)
2. NLP refinement (async term discovery from evidence)
3. Probe generation (domain-specific probes from seed terms)
4. Extraction targeting (prioritize document sections mentioning seed terms)
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.seed_term import SeedTerm, TermCategory, TermSource, TermStatus

logger = logging.getLogger(__name__)

# Probe types generated per seed term (Stage 3)
PROBE_TEMPLATES = [
    {"probe_type": "existence", "template": "Does the activity '{term}' exist in the current process?"},
    {"probe_type": "sequence", "template": "Where does '{term}' fit in the process sequence?"},
    {"probe_type": "dependency", "template": "What does '{term}' depend on to start or complete?"},
    {"probe_type": "governance", "template": "What rules or criteria govern '{term}'?"},
]


def _normalize_term(term: str) -> str:
    """Normalize a term for deduplication: lowercase, strip punctuation."""
    return re.sub(r"[^\w\s]", "", term.strip().lower())


class SeedListService:
    """Manages the seed list pipeline."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Stage 1: Consultant Vocabulary Upload ──────────────────────────

    async def create_seed_terms(
        self,
        *,
        engagement_id: uuid.UUID,
        terms: list[dict[str, str]],
        source: TermSource = TermSource.CONSULTANT_PROVIDED,
    ) -> dict[str, Any]:
        """Bulk create seed terms with deduplication.

        Each term dict should have: term, domain, category.
        """
        # Get existing terms for this engagement for dedup
        existing_stmt = select(SeedTerm.term).where(
            SeedTerm.engagement_id == engagement_id,
            SeedTerm.status == TermStatus.ACTIVE,
        )
        result = await self._session.execute(existing_stmt)
        existing_normalized = {_normalize_term(t) for t in result.scalars().all()}

        created = []
        skipped = []
        for term_data in terms:
            normalized = _normalize_term(term_data["term"])
            if normalized in existing_normalized:
                skipped.append(term_data["term"])
                continue

            seed_term = SeedTerm(
                engagement_id=engagement_id,
                term=term_data["term"],
                domain=term_data.get("domain", "general"),
                category=TermCategory(term_data.get("category", "activity")),
                source=source,
                status=TermStatus.ACTIVE,
            )
            self._session.add(seed_term)
            existing_normalized.add(normalized)
            created.append(term_data["term"])

        if created:
            await self._session.flush()

        logger.info(
            "Seed terms created: engagement=%s, created=%d, skipped=%d",
            engagement_id, len(created), len(skipped),
        )
        return {
            "engagement_id": str(engagement_id),
            "created_count": len(created),
            "skipped_count": len(skipped),
            "created_terms": created,
            "skipped_terms": skipped,
        }

    async def get_seed_list(
        self,
        engagement_id: uuid.UUID,
        *,
        status: TermStatus | None = None,
        source: TermSource | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Get the seed list for an engagement with optional filters."""
        base_filter = [SeedTerm.engagement_id == engagement_id]
        if status is not None:
            base_filter.append(SeedTerm.status == status)
        if source is not None:
            base_filter.append(SeedTerm.source == source)

        count_stmt = (
            select(sa_func.count())
            .select_from(SeedTerm)
            .where(*base_filter)
        )
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar() or 0

        query = (
            select(SeedTerm)
            .where(*base_filter)
            .order_by(SeedTerm.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(query)
        terms = result.scalars().all()

        return {
            "items": [
                {
                    "id": str(t.id),
                    "engagement_id": str(t.engagement_id),
                    "term": t.term,
                    "domain": t.domain,
                    "category": t.category.value,
                    "source": t.source.value,
                    "status": t.status.value,
                    "created_at": t.created_at.isoformat(),
                }
                for t in terms
            ],
            "total_count": total,
            "limit": limit,
            "offset": offset,
        }

    # ── Stage 2: NLP Refinement ────────────────────────────────────────

    async def add_discovered_terms(
        self,
        *,
        engagement_id: uuid.UUID,
        discovered: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Add NLP-discovered terms to the seed list with deduplication.

        Each discovered dict: term, domain, category, frequency_score (optional).
        """
        return await self.create_seed_terms(
            engagement_id=engagement_id,
            terms=discovered,
            source=TermSource.NLP_DISCOVERED,
        )

    # ── Stage 3: Probe Generation ──────────────────────────────────────

    async def generate_probes(
        self,
        engagement_id: uuid.UUID,
        seed_term_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Generate probes from active seed terms.

        If seed_term_id is provided, generates probes for that specific term.
        Otherwise, generates for all active terms in the engagement.
        """
        base_filter = [
            SeedTerm.engagement_id == engagement_id,
            SeedTerm.status == TermStatus.ACTIVE,
        ]
        if seed_term_id is not None:
            base_filter.append(SeedTerm.id == seed_term_id)

        stmt = select(SeedTerm).where(*base_filter)
        result = await self._session.execute(stmt)
        terms = result.scalars().all()

        probes = []
        for term in terms:
            for template in PROBE_TEMPLATES:
                probes.append({
                    "seed_term_id": str(term.id),
                    "seed_term": term.term,
                    "probe_type": template["probe_type"],
                    "question": template["template"].format(term=term.term),
                })

        logger.info(
            "Probes generated: engagement=%s, terms=%d, probes=%d",
            engagement_id, len(terms), len(probes),
        )
        return {
            "engagement_id": str(engagement_id),
            "terms_processed": len(terms),
            "probes_generated": len(probes),
            "probes": probes,
        }

    # ── Stage 4: Extraction Targeting ──────────────────────────────────

    async def get_extraction_targets(
        self, engagement_id: uuid.UUID
    ) -> dict[str, Any]:
        """Get active seed terms for extraction targeting.

        Returns the active terms that the extraction pipeline should use
        to prioritize document sections during evidence ingestion.
        """
        stmt = (
            select(SeedTerm)
            .where(
                SeedTerm.engagement_id == engagement_id,
                SeedTerm.status == TermStatus.ACTIVE,
            )
            .order_by(SeedTerm.term)
        )
        result = await self._session.execute(stmt)
        terms = result.scalars().all()

        return {
            "engagement_id": str(engagement_id),
            "active_term_count": len(terms),
            "terms": [
                {
                    "id": str(t.id),
                    "term": t.term,
                    "domain": t.domain,
                    "category": t.category.value,
                }
                for t in terms
            ],
        }

    async def deprecate_term(
        self, term_id: uuid.UUID
    ) -> dict[str, Any]:
        """Deprecate a seed term (soft delete)."""
        stmt = select(SeedTerm).where(SeedTerm.id == term_id)
        result = await self._session.execute(stmt)
        term = result.scalar_one_or_none()

        if term is None:
            return {"error": "not_found"}

        term.status = TermStatus.DEPRECATED
        await self._session.flush()

        return {
            "id": str(term.id),
            "term": term.term,
            "status": "deprecated",
        }
