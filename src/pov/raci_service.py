"""RACI matrix derivation service (Story #351).

Derives a RACI matrix from the Neo4j knowledge graph by analyzing
relationship edges between Activity and Role nodes:

- PERFORMED_BY  -> R (Responsible)
- GOVERNED_BY   -> A (Accountable)
- CONSULTED_BY  -> C (Consulted)   (custom edge, may not exist)
- NOTIFIED_BY   -> I (Informed)    (custom edge, may not exist)
- REVIEWS       -> C (Consulted)   (fallback mapping)

Each cell is created with status='proposed' and confidence based on
the edge's weight property (defaults to 1.0).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from neo4j import AsyncDriver

from src.core.models.raci import RACIAssignment

logger = logging.getLogger(__name__)

# Maps Neo4j edge types to RACI assignment codes
EDGE_TO_RACI: dict[str, RACIAssignment] = {
    "PERFORMED_BY": RACIAssignment.RESPONSIBLE,
    "GOVERNED_BY": RACIAssignment.ACCOUNTABLE,
    "CONSULTED_BY": RACIAssignment.CONSULTED,
    "REVIEWS": RACIAssignment.CONSULTED,
    "NOTIFIED_BY": RACIAssignment.INFORMED,
}


@dataclass
class RACIDerivation:
    """A single derived RACI assignment from the graph.

    Attributes:
        activity_id: Neo4j node ID of the activity.
        activity_name: Human-readable activity name.
        role_id: Neo4j node ID of the role.
        role_name: Human-readable role name.
        assignment: RACI assignment type (R/A/C/I).
        confidence: Derivation confidence from edge weight (0-1).
        source_edge_type: The Neo4j edge type that produced this assignment.
    """

    activity_id: str = ""
    activity_name: str = ""
    role_id: str = ""
    role_name: str = ""
    assignment: str = "R"
    confidence: float = 1.0
    source_edge_type: str = ""


@dataclass
class RACIMatrix:
    """Complete derived RACI matrix for an engagement.

    Attributes:
        engagement_id: Engagement scope.
        cells: List of derived RACI assignments.
        activities: Unique activity names found.
        roles: Unique role names found.
    """

    engagement_id: str = ""
    cells: list[RACIDerivation] = field(default_factory=list)
    activities: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)


class RACIDerivationService:
    """Derives RACI matrices from the Neo4j knowledge graph.

    Queries PERFORMED_BY, GOVERNED_BY, NOTIFIED_BY, and REVIEWS edges
    between Activity and Role nodes within an engagement scope.
    """

    def __init__(self, driver: AsyncDriver) -> None:
        self._driver = driver

    async def derive_matrix(self, engagement_id: str) -> RACIMatrix:
        """Derive a complete RACI matrix for an engagement.

        Queries all activity-role edges in the engagement and maps
        each edge type to the corresponding RACI assignment.

        Args:
            engagement_id: The engagement to derive the matrix for.

        Returns:
            A RACIMatrix with all derived cells.
        """
        matrix = RACIMatrix(engagement_id=engagement_id)
        seen_keys: set[tuple[str, str, str]] = set()
        activity_names: set[str] = set()
        role_names: set[str] = set()

        for edge_type, raci_code in EDGE_TO_RACI.items():
            derivations = await self._query_edge_type(engagement_id, edge_type, raci_code)
            for d in derivations:
                key = (d.activity_id, d.role_id, d.assignment)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                matrix.cells.append(d)
                activity_names.add(d.activity_name)
                role_names.add(d.role_name)

        matrix.activities = sorted(activity_names)
        matrix.roles = sorted(role_names)

        logger.info(
            "Derived RACI matrix for engagement %s: %d cells, %d activities, %d roles",
            engagement_id,
            len(matrix.cells),
            len(matrix.activities),
            len(matrix.roles),
        )
        return matrix

    async def _query_edge_type(
        self,
        engagement_id: str,
        edge_type: str,
        raci_code: RACIAssignment,
    ) -> list[RACIDerivation]:
        """Query a specific edge type and convert to RACI derivations.

        Args:
            engagement_id: Engagement scope filter.
            edge_type: Neo4j relationship type to query.
            raci_code: RACI assignment to assign for this edge type.

        Returns:
            List of RACI derivations for this edge type.
        """
        query = f"""
        MATCH (a:Activity)-[r:{edge_type}]->(role:Role)
        WHERE a.engagement_id = $engagement_id
        RETURN a.id AS activity_id,
               a.name AS activity_name,
               role.id AS role_id,
               role.name AS role_name,
               r.weight AS weight
        """  # noqa: S608 — edge_type is from EDGE_TO_RACI constant, not user input

        async def _tx(tx: Any) -> list[dict[str, Any]]:
            result = await tx.run(query, {"engagement_id": engagement_id})
            return await result.data()

        try:
            async with self._driver.session() as session:
                records = await session.execute_read(_tx)
        except Exception:
            logger.debug("Edge type %s not found or query failed for engagement %s", edge_type, engagement_id)
            return []

        derivations: list[RACIDerivation] = []
        for record in records:
            derivations.append(
                RACIDerivation(
                    activity_id=str(record["activity_id"]),
                    activity_name=str(record["activity_name"]),
                    role_id=str(record["role_id"]),
                    role_name=str(record["role_name"]),
                    assignment=raci_code.value,
                    confidence=float(record.get("weight") or 1.0),
                    source_edge_type=edge_type,
                )
            )

        return derivations
