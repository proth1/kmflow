"""Three-Way Distinction Classifier (Story #384).

Processes ConflictObject records and assigns a resolution_type:
- NAMING_VARIANT: same activity referenced by different names (seed list match)
- TEMPORAL_SHIFT: both views valid but apply to different time periods
- GENUINE_DISAGREEMENT: no naming or temporal explanation (preserve both)

Classification order: NAMING_VARIANT first (fastest), then TEMPORAL_SHIFT,
default to GENUINE_DISAGREEMENT. The classifier is idempotent.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import (
    ConflictObject,
    ResolutionStatus,
    ResolutionType,
    SeedTerm,
    TermStatus,
)

logger = logging.getLogger(__name__)

CLASSIFIER_VERSION = "1.0.0"


class ThreeWayDistinctionClassifier:
    """Classify ConflictObjects into NAMING_VARIANT, TEMPORAL_SHIFT, or GENUINE_DISAGREEMENT.

    Uses seed list lookup for naming variants, effective date metadata for
    temporal shifts, and defaults to genuine disagreement with epistemic
    frame tagging.

    The classifier is idempotent: re-classifying a ConflictObject with
    the same inputs produces the same resolution_type.
    """

    def __init__(self, graph_service: Any, session: AsyncSession) -> None:
        self._graph = graph_service
        self._session = session

    async def classify(self, conflict: ConflictObject) -> ConflictObject:
        """Classify a single ConflictObject and update its resolution metadata.

        Classification order:
        1. Check NAMING_VARIANT (fastest — seed list lookup)
        2. Check TEMPORAL_SHIFT (effective date metadata)
        3. Default to GENUINE_DISAGREEMENT

        Args:
            conflict: The ConflictObject to classify.

        Returns:
            The updated ConflictObject (also mutated in-place).
        """
        now = datetime.now(UTC)

        # 1. Check for naming variant
        naming_result = await self._check_naming_variant(conflict)
        if naming_result is not None:
            conflict.resolution_type = ResolutionType.NAMING_VARIANT
            conflict.resolution_status = ResolutionStatus.RESOLVED
            conflict.resolution_details = naming_result
            conflict.classified_at = now
            conflict.classifier_version = CLASSIFIER_VERSION
            conflict.resolved_at = now
            return conflict

        # 2. Check for temporal shift
        temporal_result = await self._check_temporal_shift(conflict)
        if temporal_result is not None:
            conflict.resolution_type = ResolutionType.TEMPORAL_SHIFT
            conflict.resolution_status = ResolutionStatus.RESOLVED
            conflict.resolution_details = temporal_result
            conflict.classified_at = now
            conflict.classifier_version = CLASSIFIER_VERSION
            conflict.resolved_at = now
            return conflict

        # 3. Default to genuine disagreement
        disagreement_result = await self._tag_genuine_disagreement(conflict)
        conflict.resolution_type = ResolutionType.GENUINE_DISAGREEMENT
        conflict.resolution_status = ResolutionStatus.UNRESOLVED  # Open for SME review
        conflict.resolution_details = disagreement_result
        conflict.classified_at = now
        conflict.classifier_version = CLASSIFIER_VERSION
        return conflict

    async def classify_batch(self, engagement_id: UUID) -> list[ConflictObject]:
        """Classify all unclassified ConflictObjects for an engagement.

        Args:
            engagement_id: The engagement to process.

        Returns:
            List of classified ConflictObjects.
        """
        result = await self._session.execute(
            select(ConflictObject).where(
                ConflictObject.engagement_id == engagement_id,
                ConflictObject.resolution_type.is_(None),
            )
        )
        conflicts = list(result.scalars().all())

        classified = []
        for conflict in conflicts:
            await self.classify(conflict)
            classified.append(conflict)

        if classified:
            await self._session.flush()

        logger.info(
            "Classified %d ConflictObjects for engagement %s",
            len(classified),
            engagement_id,
        )
        return classified

    async def _check_naming_variant(self, conflict: ConflictObject) -> dict[str, Any] | None:
        """Check if the conflict is a naming variant using seed list aliases.

        Queries the knowledge graph for the activity names involved in the
        conflict, then checks if both names map to the same canonical seed
        term (or one is an alias of the other).
        """
        # Get activity names from the conflict's graph context
        names = await self._get_conflicting_names(conflict)
        if not names or len(names) < 2:
            return None

        name_a, name_b = names[0], names[1]

        # Check seed list for alias relationship
        canonical = await self._find_canonical_match(conflict.engagement_id, name_a, name_b)
        if canonical is None:
            return None

        # Merge nodes in the graph
        merge_result = await self._merge_graph_nodes(conflict.engagement_id, name_a, name_b, canonical)

        return {
            "merged_from": [name_a, name_b],
            "canonical_name": canonical,
            "merge_result": merge_result,
            "resolution_note": (
                f"Entities '{name_a}' and '{name_b}' merged into canonical term '{canonical}' from seed list"
            ),
        }

    async def _check_temporal_shift(self, conflict: ConflictObject) -> dict[str, Any] | None:
        """Check if the conflict is explained by non-overlapping effective dates.

        Queries the evidence items' effective date metadata to determine
        if the contradiction can be explained by temporal separation.
        """
        if not conflict.source_a_id or not conflict.source_b_id:
            return None

        dates = await self._get_effective_dates(conflict.source_a_id, conflict.source_b_id)
        if dates is None:
            return None

        from_a, to_a, from_b, to_b = dates

        if from_a is None or from_b is None:
            return None

        # Check for non-overlapping ranges
        far_future = datetime(9999, 12, 31, tzinfo=UTC)
        end_a = to_a or far_future
        end_b = to_b or far_future

        if from_a <= end_b and from_b <= end_a:
            # Overlapping → not a temporal shift
            return None

        range_a = f"{from_a.date().isoformat()}" + (f" to {to_a.date().isoformat()}" if to_a else "–present")
        range_b = f"{from_b.date().isoformat()}" + (f" to {to_b.date().isoformat()}" if to_b else "–present")

        # Set bitemporal validity on conflicting edges
        await self._set_bitemporal_validity(conflict, from_a, to_a, from_b, to_b)

        return {
            "source_a_range": {
                "from": from_a.date().isoformat(),
                "to": to_a.date().isoformat() if to_a else None,
            },
            "source_b_range": {
                "from": from_b.date().isoformat(),
                "to": to_b.date().isoformat() if to_b else None,
            },
            "annotation": f"Source A valid {range_a}; Source B valid {range_b}",
            "resolution_note": "Both views preserved with bitemporal validity ranges",
        }

    async def _tag_genuine_disagreement(self, conflict: ConflictObject) -> dict[str, Any]:
        """Tag a genuine disagreement with epistemic frame information.

        Queries the graph for the epistemic frames of each source and
        records which frames are in conflict.
        """
        frames = await self._get_epistemic_frames(conflict)

        return {
            "conflicting_frames": frames,
            "resolution_note": (
                "Genuine disagreement — both views preserved in knowledge graph. "
                "Tagged with source epistemic frames for SME review."
            ),
            "requires_sme_review": True,
        }

    # -----------------------------------------------------------------------
    # Graph and database helper methods
    # -----------------------------------------------------------------------

    async def _get_conflicting_names(self, conflict: ConflictObject) -> list[str]:
        """Retrieve the activity/entity names involved in the conflict from the graph."""
        try:
            records = await self._graph.run_query(
                """
                MATCH (a:Activity)-[r:EVIDENCED_BY]->(e:Evidence)
                WHERE e.source_id IN [$source_a, $source_b]
                  AND r.engagement_id = $engagement_id
                RETURN DISTINCT a.name AS name, e.source_id AS source_id
                ORDER BY e.source_id
                LIMIT 10
                """,
                {
                    "source_a": str(conflict.source_a_id) if conflict.source_a_id else "",
                    "source_b": str(conflict.source_b_id) if conflict.source_b_id else "",
                    "engagement_id": str(conflict.engagement_id),
                },
            )
            return [r["name"] for r in records if r.get("name")]
        except Exception:
            logger.exception("Failed to get conflicting names for %s", conflict.id)
            return []

    async def _find_canonical_match(self, engagement_id: UUID, name_a: str, name_b: str) -> str | None:
        """Check if both names map to the same canonical seed term.

        Checks:
        1. Direct match: one name is a canonical term, the other is an alias
        2. Both names are aliases of the same canonical term
        """
        # Look for seed terms matching either name
        result = await self._session.execute(
            select(SeedTerm).where(
                SeedTerm.engagement_id == engagement_id,
                SeedTerm.status == TermStatus.ACTIVE,
                SeedTerm.term.in_([name_a, name_b]),
            )
        )
        terms = list(result.scalars().all())

        if len(terms) >= 1:
            # One of the names is a canonical term — the other is the alias
            return terms[0].term

        # Check via graph aliases
        try:
            records = await self._graph.run_query(
                """
                MATCH (a:Activity {name: $name_a})-[:VARIANT_OF]-(b:Activity {name: $name_b})
                WHERE a.engagement_id = $engagement_id
                RETURN a.name AS name_a, b.name AS name_b
                LIMIT 1
                """,
                {
                    "name_a": name_a,
                    "name_b": name_b,
                    "engagement_id": str(engagement_id),
                },
            )
            if records:
                # They're already linked as variants — default to name_a as canonical
                return name_a
        except Exception:
            logger.exception("Failed to check variant relationship for %s", engagement_id)

        return None

    async def _merge_graph_nodes(
        self,
        engagement_id: UUID,
        name_a: str,
        name_b: str,
        canonical: str,
    ) -> dict[str, Any]:
        """Merge two activity nodes into a single canonical node in Neo4j.

        Transfers all edges from the non-canonical node to the canonical one.
        """
        non_canonical = name_b if canonical == name_a else name_a

        try:
            await self._graph.run_write_query(
                """
                MATCH (canonical:Activity {name: $canonical, engagement_id: $eid})
                MATCH (other:Activity {name: $other, engagement_id: $eid})
                WITH canonical, other
                CALL {
                    WITH canonical, other
                    MATCH (other)-[r]->(target)
                    MERGE (canonical)-[nr:MERGED_EDGE]->(target)
                    SET nr = properties(r), nr.merged_from = other.name
                    DELETE r
                }
                CALL {
                    WITH canonical, other
                    MATCH (source)-[r]->(other)
                    MERGE (source)-[nr:MERGED_EDGE]->(canonical)
                    SET nr = properties(r), nr.merged_from = other.name
                    DELETE r
                }
                SET canonical.aliases = coalesce(canonical.aliases, []) + [$other]
                DELETE other
                """,
                {
                    "canonical": canonical,
                    "other": non_canonical,
                    "eid": str(engagement_id),
                },
            )
            return {"status": "merged", "canonical": canonical, "removed": non_canonical}
        except Exception:
            logger.exception("Failed to merge graph nodes %s into %s", non_canonical, canonical)
            return {"status": "merge_failed", "canonical": canonical, "removed": non_canonical}

    async def _get_effective_dates(
        self, source_a_id: UUID, source_b_id: UUID
    ) -> tuple[datetime | None, datetime | None, datetime | None, datetime | None] | None:
        """Retrieve effective date metadata for two evidence sources from the graph."""
        try:
            records = await self._graph.run_query(
                """
                MATCH (e:Evidence)
                WHERE e.source_id IN [$source_a, $source_b]
                RETURN e.source_id AS source_id,
                       e.effective_from AS effective_from,
                       e.effective_to AS effective_to
                """,
                {
                    "source_a": str(source_a_id),
                    "source_b": str(source_b_id),
                },
            )

            dates: dict[str, tuple] = {}
            for r in records:
                sid = r.get("source_id")
                dates[sid] = (r.get("effective_from"), r.get("effective_to"))

            a_dates = dates.get(str(source_a_id), (None, None))
            b_dates = dates.get(str(source_b_id), (None, None))

            return (a_dates[0], a_dates[1], b_dates[0], b_dates[1])
        except Exception:
            logger.exception("Failed to get effective dates for sources")
            return None

    async def _set_bitemporal_validity(
        self,
        conflict: ConflictObject,
        from_a: datetime,
        to_a: datetime | None,
        from_b: datetime,
        to_b: datetime | None,
    ) -> None:
        """Set valid_from and valid_to properties on conflicting graph edges."""
        try:
            await self._graph.run_write_query(
                """
                MATCH ()-[r]->()
                WHERE r.source_id = $source_a AND r.engagement_id = $eid
                SET r.valid_from = $from_a, r.valid_to = $to_a
                """,
                {
                    "source_a": str(conflict.source_a_id),
                    "eid": str(conflict.engagement_id),
                    "from_a": from_a.isoformat(),
                    "to_a": to_a.isoformat() if to_a else None,
                },
            )
            await self._graph.run_write_query(
                """
                MATCH ()-[r]->()
                WHERE r.source_id = $source_b AND r.engagement_id = $eid
                SET r.valid_from = $from_b, r.valid_to = $to_b
                """,
                {
                    "source_b": str(conflict.source_b_id),
                    "eid": str(conflict.engagement_id),
                    "from_b": from_b.isoformat(),
                    "to_b": to_b.isoformat() if to_b else None,
                },
            )
        except Exception:
            logger.exception("Failed to set bitemporal validity for conflict %s", conflict.id)

    async def _get_epistemic_frames(self, conflict: ConflictObject) -> list[dict[str, Any]]:
        """Retrieve epistemic frame information for the conflicting sources."""
        try:
            records = await self._graph.run_query(
                """
                MATCH (e:Evidence)
                WHERE e.source_id IN [$source_a, $source_b]
                  AND e.engagement_id = $eid
                RETURN e.source_id AS source_id,
                       e.epistemic_frame AS frame,
                       e.evidence_type AS evidence_type
                """,
                {
                    "source_a": str(conflict.source_a_id) if conflict.source_a_id else "",
                    "source_b": str(conflict.source_b_id) if conflict.source_b_id else "",
                    "eid": str(conflict.engagement_id),
                },
            )
            return [
                {
                    "source_id": r.get("source_id"),
                    "frame": r.get("frame", "unknown"),
                    "evidence_type": r.get("evidence_type", "unknown"),
                }
                for r in records
            ]
        except Exception:
            logger.exception("Failed to get epistemic frames for conflict %s", conflict.id)
            return [
                {"source_id": str(conflict.source_a_id), "frame": "unknown", "evidence_type": "unknown"},
                {"source_id": str(conflict.source_b_id), "frame": "unknown", "evidence_type": "unknown"},
            ]
