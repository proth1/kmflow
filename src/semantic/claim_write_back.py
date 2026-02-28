"""Survey claim write-back to Neo4j knowledge graph (Story #324).

Ingests SurveyClaims into Neo4j, creating SUPPORTS/CONTRADICTS edges
between claims and process elements, with EpistemicFrame metadata.
Confidence scores for affected activities are recomputed.
ConflictObjects are auto-created for contradicted claims.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.conflict import (
    ConflictObject,
    MismatchType,
    ResolutionStatus,
)
from src.core.models.survey import CertaintyTier, SurveyClaim
from src.semantic.graph import KnowledgeGraphService

logger = logging.getLogger(__name__)

# Edge weight mapping for certainty tiers
CERTAINTY_WEIGHTS: dict[CertaintyTier, float] = {
    CertaintyTier.KNOWN: 1.0,
    CertaintyTier.SUSPECTED: 0.6,
    CertaintyTier.UNKNOWN: 0.3,
    CertaintyTier.CONTRADICTED: -0.5,
}


class ClaimWriteBackService:
    """Writes SurveyClaims to the Neo4j knowledge graph."""

    def __init__(
        self,
        graph: KnowledgeGraphService,
        session: AsyncSession,
    ) -> None:
        self._graph = graph
        self._session = session

    async def ingest_claim(
        self,
        claim: SurveyClaim,
        target_activity_id: str | None = None,
    ) -> dict[str, Any]:
        """Ingest a SurveyClaim into the knowledge graph.

        Creates a Claim node, links it to the target activity via
        SUPPORTS or CONTRADICTS edge, and optionally creates a
        ConflictObject for contradicted claims.

        Args:
            claim: The SurveyClaim to ingest.
            target_activity_id: Neo4j node ID of the activity this
                claim relates to. If None, the claim node is created
                without a relationship.

        Returns:
            Dict with claim_node_id, edge_type, conflict_id (if any).
        """
        claim_node_id = str(claim.id).replace("-", "")[:16]
        weight = CERTAINTY_WEIGHTS.get(claim.certainty_tier, 0.3)

        # 1. Create SurveyClaim node in Neo4j
        await self._graph.run_write_query(
            """
            MERGE (c:Claim {id: $claim_id})
            SET c.claim_text = $claim_text,
                c.probe_type = $probe_type,
                c.certainty_tier = $certainty_tier,
                c.respondent_role = $respondent_role,
                c.engagement_id = $engagement_id,
                c.session_id = $session_id,
                c.weight = $weight,
                c.ingested_at = datetime()
            """,
            {
                "claim_id": claim_node_id,
                "claim_text": claim.claim_text,
                "probe_type": claim.probe_type.value,
                "certainty_tier": claim.certainty_tier.value,
                "respondent_role": claim.respondent_role,
                "engagement_id": str(claim.engagement_id),
                "session_id": str(claim.session_id),
                "weight": weight,
            },
        )

        result: dict[str, Any] = {
            "claim_node_id": claim_node_id,
            "edge_type": None,
            "conflict_id": None,
            "weight": weight,
        }

        # 2. Create EpistemicFrame node if claim has one
        if claim.epistemic_frame is not None:
            frame = claim.epistemic_frame
            frame_node_id = str(frame.id).replace("-", "")[:16]
            await self._graph.run_write_query(
                """
                MERGE (f:EpistemicFrame {session_id: $session_id, respondent_role: $respondent_role})
                SET f.id = $frame_id,
                    f.frame_kind = $frame_kind,
                    f.authority_scope = $authority_scope,
                    f.engagement_id = $engagement_id
                WITH f
                MATCH (c:Claim {id: $claim_id})
                MERGE (c)-[:HAS_FRAME]->(f)
                """,
                {
                    "frame_id": frame_node_id,
                    "session_id": str(claim.session_id),
                    "respondent_role": claim.respondent_role,
                    "frame_kind": frame.frame_kind.value,
                    "authority_scope": frame.authority_scope,
                    "engagement_id": str(claim.engagement_id),
                    "claim_id": claim_node_id,
                },
            )

        # 3. Link claim to target activity
        if target_activity_id is not None:
            if claim.certainty_tier == CertaintyTier.CONTRADICTED:
                edge_type = "CONTRADICTS"
            else:
                edge_type = "SUPPORTS"

            # Validate edge_type to prevent Cypher injection
            if edge_type not in ("SUPPORTS", "CONTRADICTS"):
                msg = f"Invalid edge_type: {edge_type}"
                raise ValueError(msg)

            await self._graph.run_write_query(
                f"""
                MATCH (c:Claim {{id: $claim_id}})
                MATCH (a {{id: $activity_id, engagement_id: $engagement_id}})
                MERGE (c)-[r:{edge_type}]->(a)
                SET r.weight = $weight,
                    r.probe_type = $probe_type,
                    r.claim_id = $claim_uuid,
                    r.ingested_at = datetime()
                """,
                {
                    "claim_id": claim_node_id,
                    "activity_id": target_activity_id,
                    "engagement_id": str(claim.engagement_id),
                    "weight": weight,
                    "probe_type": claim.probe_type.value,
                    "claim_uuid": str(claim.id),
                },
            )
            result["edge_type"] = edge_type

            # 4. Auto-create ConflictObject for contradicted claims
            if claim.certainty_tier == CertaintyTier.CONTRADICTED:
                conflict = await self._create_conflict_object(
                    claim, target_activity_id
                )
                result["conflict_id"] = str(conflict.id)

        logger.info(
            "Claim ingested: claim=%s, edge=%s, conflict=%s",
            claim_node_id,
            result["edge_type"],
            result["conflict_id"],
        )
        return result

    async def recompute_activity_confidence(
        self,
        activity_id: str,
        engagement_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Recompute confidence score for an activity based on all claim weights.

        Queries all SUPPORTS/CONTRADICTS edges to the activity and computes
        a weighted average claim confidence that can be factored into the
        overall confidence model.

        Returns:
            Dict with activity_id, claim_count, aggregate_weight, claim_confidence.
        """
        result = await self._graph.run_query(
            """
            MATCH (c:Claim)-[r]->(a {id: $activity_id, engagement_id: $engagement_id})
            WHERE type(r) IN ['SUPPORTS', 'CONTRADICTS']
              AND c.engagement_id = $engagement_id
            RETURN count(c) AS claim_count,
                   sum(r.weight) AS total_weight
            """,
            {
                "activity_id": activity_id,
                "engagement_id": str(engagement_id),
            },
        )

        if not result:
            return {
                "activity_id": activity_id,
                "claim_count": 0,
                "aggregate_weight": 0.0,
                "claim_confidence": 0.0,
            }

        row = result[0]
        claim_count = row.get("claim_count", 0)
        total_weight = row.get("total_weight", 0.0)

        # Normalize to 0-1 range: sigmoid-style bounded by claim count
        if claim_count > 0:
            claim_confidence = min(1.0, max(0.0, total_weight / claim_count))
        else:
            claim_confidence = 0.0

        # Update activity node with claim-derived confidence component
        await self._graph.run_write_query(
            """
            MATCH (a {id: $activity_id, engagement_id: $engagement_id})
            SET a.claim_confidence = $claim_confidence,
                a.claim_count = $claim_count,
                a.confidence_updated_at = datetime()
            """,
            {
                "activity_id": activity_id,
                "engagement_id": str(engagement_id),
                "claim_confidence": claim_confidence,
                "claim_count": claim_count,
            },
        )

        return {
            "activity_id": activity_id,
            "claim_count": claim_count,
            "aggregate_weight": total_weight,
            "claim_confidence": claim_confidence,
        }

    async def batch_ingest_claims(
        self,
        claims: list[SurveyClaim],
        target_activity_ids: dict[uuid.UUID, str] | None = None,
    ) -> dict[str, Any]:
        """Batch ingest multiple claims and recompute affected activities.

        Args:
            claims: List of SurveyClaims to ingest.
            target_activity_ids: Mapping of claim_id -> activity_id.
                Claims without a mapping are ingested without edges.

        Returns:
            Summary dict with counts.
        """
        targets = target_activity_ids or {}
        results = []
        affected_activities: set[str] = set()

        for claim in claims:
            activity_id = targets.get(claim.id)
            result = await self.ingest_claim(claim, activity_id)
            results.append(result)
            if activity_id:
                affected_activities.add(activity_id)

        # Recompute confidence for all affected activities
        recomputed = []
        engagement_id = claims[0].engagement_id if claims else None
        for activity_id in affected_activities:
            if engagement_id:
                conf = await self.recompute_activity_confidence(
                    activity_id, engagement_id
                )
                recomputed.append(conf)

        return {
            "claims_ingested": len(results),
            "edges_created": sum(1 for r in results if r["edge_type"]),
            "conflicts_created": sum(
                1 for r in results if r["conflict_id"]
            ),
            "activities_recomputed": len(recomputed),
            "recomputation_results": recomputed,
        }

    async def _create_conflict_object(
        self,
        claim: SurveyClaim,
        target_activity_id: str,
    ) -> ConflictObject:
        """Create a ConflictObject in PostgreSQL for a contradicted claim."""
        conflict = ConflictObject(
            engagement_id=claim.engagement_id,
            mismatch_type=MismatchType.EXISTENCE_MISMATCH,
            resolution_status=ResolutionStatus.UNRESOLVED,
            severity=0.7,
            escalation_flag=True,
            conflict_detail={
                "claim_id": str(claim.id),
                "claim_text": claim.claim_text,
                "probe_type": claim.probe_type.value,
                "target_activity_id": target_activity_id,
                "respondent_role": claim.respondent_role,
                "created_at": datetime.now(UTC).isoformat(),
            },
        )
        self._session.add(conflict)
        await self._session.flush()

        # Also create ConflictObject node in Neo4j
        conflict_node_id = str(conflict.id).replace("-", "")[:16]
        await self._graph.run_write_query(
            """
            CREATE (co:ConflictObject {
                id: $conflict_id,
                mismatch_type: $mismatch_type,
                severity: $severity,
                engagement_id: $engagement_id,
                created_at: datetime()
            })
            WITH co
            MATCH (c:Claim {id: $claim_id})
            MATCH (a {id: $activity_id, engagement_id: $engagement_id})
            MERGE (co)-[:INVOLVES]->(c)
            MERGE (co)-[:INVOLVES]->(a)
            """,
            {
                "conflict_id": conflict_node_id,
                "mismatch_type": MismatchType.EXISTENCE_MISMATCH.value,
                "severity": 0.7,
                "engagement_id": str(claim.engagement_id),
                "claim_id": str(claim.id).replace("-", "")[:16],
                "activity_id": target_activity_id,
            },
        )

        return conflict
