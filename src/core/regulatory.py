"""Regulatory Overlay Engine.

Builds governance chains in the knowledge graph (GOVERNED_BY->ENFORCED_BY->SATISFIES).
Calculates compliance state and detects ungoverned processes.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass, field
from typing import Any

from neo4j.exceptions import Neo4jError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import ComplianceLevel, Control, Policy, Regulation
from src.semantic.graph import KnowledgeGraphService

logger = logging.getLogger(__name__)


@dataclass
class ComplianceState:
    """Compliance assessment for an engagement.

    Attributes:
        engagement_id: The engagement assessed.
        level: Overall compliance level.
        governed_count: Number of governed processes.
        ungoverned_count: Number of ungoverned processes.
        total_processes: Total processes in the engagement.
        policy_coverage: Percentage of processes with policy links.
        details: Per-process compliance details.
    """

    engagement_id: str = ""
    level: ComplianceLevel = ComplianceLevel.NOT_ASSESSED
    governed_count: int = 0
    ungoverned_count: int = 0
    total_processes: int = 0
    policy_coverage: float = 0.0
    details: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class GovernanceChain:
    """A governance chain linking process -> policy -> control -> regulation.

    Attributes:
        process_id: The governed process node ID.
        process_name: Process name.
        policies: Policies governing this process.
        controls: Controls enforcing the policies.
        regulations: Regulations satisfied by the controls.
    """

    process_id: str = ""
    process_name: str = ""
    policies: list[dict[str, Any]] = field(default_factory=list)
    controls: list[dict[str, Any]] = field(default_factory=list)
    regulations: list[dict[str, Any]] = field(default_factory=list)


class RegulatoryOverlayEngine:
    """Engine for building and querying regulatory governance overlays.

    Builds graph relationships linking processes to policies, controls,
    and regulations. Provides compliance assessment and ungoverned
    process detection.
    """

    def __init__(self, graph_service: KnowledgeGraphService) -> None:
        self._graph = graph_service

    async def build_governance_chains(
        self,
        session: AsyncSession,
        engagement_id: str,
    ) -> list[GovernanceChain]:
        """Build governance chains in Neo4j for an engagement.

        Creates GOVERNED_BY relationships from processes to policies,
        ENFORCED_BY from policies to controls, and SATISFIES from
        controls to regulations.

        Args:
            session: Database session for querying policies/controls.
            engagement_id: The engagement to build chains for.

        Returns:
            List of governance chains created.
        """
        # Fetch all policies, controls, regulations for the engagement
        policies = await self._fetch_policies(session, engagement_id)
        controls = await self._fetch_controls(session, engagement_id)
        regulations = await self._fetch_regulations(session, engagement_id)

        # Get all Process nodes in the engagement
        process_nodes = await self._graph.find_nodes("Process", filters={"engagement_id": engagement_id})

        chains: list[GovernanceChain] = []

        # Upsert Policy nodes via MERGE (avoids get_node + create_node round-trips)
        for policy in policies:
            policy_node_id = f"policy-{policy.id}"
            try:
                await self._graph.run_write_query(
                    """
                    MERGE (n {id: $id})
                    ON CREATE SET n:Policy, n.name = $name,
                                  n.engagement_id = $engagement_id,
                                  n.policy_type = $policy_type
                    ON MATCH SET  n.name = $name,
                                  n.policy_type = $policy_type
                    """,
                    {
                        "id": policy_node_id,
                        "name": policy.name,
                        "engagement_id": engagement_id,
                        "policy_type": str(policy.policy_type),
                    },
                )
            except Neo4jError as e:
                logger.warning("Failed to upsert Policy node: %s", e)

        # Upsert Control nodes and GOVERNED_BY edges via MERGE
        for control in controls:
            control_node_id = f"control-{control.id}"
            try:
                await self._graph.run_write_query(
                    """
                    MERGE (n {id: $id})
                    ON CREATE SET n:Control, n.name = $name,
                                  n.engagement_id = $engagement_id,
                                  n.effectiveness = $effectiveness
                    ON MATCH SET  n.name = $name,
                                  n.effectiveness = $effectiveness
                    """,
                    {
                        "id": control_node_id,
                        "name": control.name,
                        "engagement_id": engagement_id,
                        "effectiveness": str(control.effectiveness),
                    },
                )

                # Link control to its policies
                for pid in control.linked_policy_ids or []:
                    policy_node_id = f"policy-{pid}"
                    with contextlib.suppress(Neo4jError):
                        await self._graph.run_write_query(
                            """
                            MATCH (pol {id: $pol_id}), (ctrl {id: $ctrl_id})
                            MERGE (pol)-[r:GOVERNED_BY]->(ctrl)
                            ON CREATE SET r.source = 'regulatory_overlay'
                            """,
                            {"pol_id": policy_node_id, "ctrl_id": control_node_id},
                        )
            except Neo4jError as e:
                logger.warning("Failed to upsert Control node: %s", e)

        # Upsert Regulation nodes via MERGE
        for regulation in regulations:
            reg_node_id = f"reg-{regulation.id}"
            try:
                await self._graph.run_write_query(
                    """
                    MERGE (n {id: $id})
                    ON CREATE SET n:Regulation, n.name = $name,
                                  n.engagement_id = $engagement_id,
                                  n.framework = $framework
                    ON MATCH SET  n.name = $name,
                                  n.framework = $framework
                    """,
                    {
                        "id": reg_node_id,
                        "name": regulation.name,
                        "engagement_id": engagement_id,
                        "framework": regulation.framework or "",
                    },
                )
            except Neo4jError as e:
                logger.warning("Failed to upsert Regulation node: %s", e)

        # Fetch all governance chains in a single batch query instead of
        # N get_relationships() + N*M get_node() calls (was 250+ sessions for
        # 50 processes × 5 policies each).
        try:
            rows = await self._graph.run_query(
                """
                MATCH (p {engagement_id: $eid})-[r:GOVERNED_BY]->(pol)
                WHERE p.id IS NOT NULL
                RETURN p.id AS process_id, p.name AS process_name,
                       pol.id AS policy_id, pol.name AS policy_name,
                       type(r) AS rel_type
                """,
                {"eid": engagement_id},
            )
        except Neo4jError as e:
            logger.warning("Failed to fetch governance chains: %s", e)
            rows = []

        # Index batch results by process_id, then append ungoverned processes
        chains_by_process: dict[str, GovernanceChain] = {}
        for row in rows:
            pid = row["process_id"]
            if pid not in chains_by_process:
                chains_by_process[pid] = GovernanceChain(
                    process_id=pid,
                    process_name=row.get("process_name") or "",
                )
            chains_by_process[pid].policies.append({"id": row["policy_id"], "name": row.get("policy_name") or ""})

        # Include processes that have no governance links
        governed_ids = set(chains_by_process)
        for proc in process_nodes:
            if proc.id not in governed_ids:
                chains_by_process[proc.id] = GovernanceChain(
                    process_id=proc.id,
                    process_name=proc.properties.get("name", ""),
                )

        chains = list(chains_by_process.values())
        return chains

    async def assess_compliance(
        self,
        session: AsyncSession,
        engagement_id: str,
    ) -> ComplianceState:
        """Assess compliance state for an engagement.

        Examines which processes have governance chains and calculates
        overall compliance level.

        Args:
            session: Database session.
            engagement_id: The engagement to assess.

        Returns:
            ComplianceState with assessment results.
        """
        process_nodes = await self._graph.find_nodes("Process", filters={"engagement_id": engagement_id})

        state = ComplianceState(engagement_id=engagement_id)
        state.total_processes = len(process_nodes)

        # Single batch query: count GOVERNED_BY relationships per process
        try:
            rows = await self._graph.run_query(
                """
                MATCH (p {engagement_id: $eid})
                WHERE p.id IS NOT NULL
                OPTIONAL MATCH (p)-[:GOVERNED_BY]->(pol)
                RETURN p.id AS process_id, p.name AS process_name,
                       count(pol) AS policy_count
                """,
                {"eid": engagement_id},
            )
        except Neo4jError as e:
            logger.warning("Failed to fetch compliance data: %s", e)
            rows = []

        # Build a lookup from process_id -> policy_count for the batch results
        policy_count_by_id: dict[str, int] = {
            row["process_id"]: int(row["policy_count"]) for row in rows if row["process_id"]
        }

        for proc in process_nodes:
            policy_count = policy_count_by_id.get(proc.id, 0)
            if policy_count > 0:
                state.governed_count += 1
                state.details.append(
                    {
                        "process_id": proc.id,
                        "process_name": proc.properties.get("name", ""),
                        "governed": True,
                        "policy_count": policy_count,
                    }
                )
            else:
                state.ungoverned_count += 1
                state.details.append(
                    {
                        "process_id": proc.id,
                        "process_name": proc.properties.get("name", ""),
                        "governed": False,
                        "policy_count": 0,
                    }
                )

        if state.total_processes > 0:
            state.policy_coverage = round(state.governed_count / state.total_processes * 100, 2)

        # Determine overall level
        if state.policy_coverage >= 90:
            state.level = ComplianceLevel.FULLY_COMPLIANT
        elif state.policy_coverage >= 50:
            state.level = ComplianceLevel.PARTIALLY_COMPLIANT
        elif state.total_processes > 0:
            state.level = ComplianceLevel.NON_COMPLIANT
        else:
            state.level = ComplianceLevel.NOT_ASSESSED

        return state

    async def find_ungoverned_processes(
        self,
        engagement_id: str,
    ) -> list[dict[str, Any]]:
        """Find processes without any governance links.

        Args:
            engagement_id: The engagement to scan.

        Returns:
            List of ungoverned process details.
        """
        process_nodes = await self._graph.find_nodes("Process", filters={"engagement_id": engagement_id})

        # Single batch query: find processes with no outgoing GOVERNED_BY edges
        try:
            rows = await self._graph.run_query(
                """
                MATCH (p {engagement_id: $eid})
                WHERE p.id IS NOT NULL
                  AND NOT (p)-[:GOVERNED_BY]->()
                RETURN p.id AS process_id, p.name AS process_name
                """,
                {"eid": engagement_id},
            )
            return [
                {
                    "process_id": row["process_id"],
                    "process_name": row.get("process_name") or "",
                }
                for row in rows
            ]
        except Neo4jError as e:
            logger.warning("Failed to fetch ungoverned processes: %s", e)
            # Fallback: derive from in-memory process_nodes list
            return [
                {
                    "process_id": proc.id,
                    "process_name": proc.properties.get("name", ""),
                }
                for proc in process_nodes
            ]

    async def _fetch_policies(self, session: AsyncSession, engagement_id: str) -> list[Policy]:
        result = await session.execute(select(Policy).where(Policy.engagement_id == engagement_id))
        return list(result.scalars().all())

    async def _fetch_controls(self, session: AsyncSession, engagement_id: str) -> list[Control]:
        result = await session.execute(select(Control).where(Control.engagement_id == engagement_id))
        return list(result.scalars().all())

    async def _fetch_regulations(self, session: AsyncSession, engagement_id: str) -> list[Regulation]:
        result = await session.execute(select(Regulation).where(Regulation.engagement_id == engagement_id))
        return list(result.scalars().all())
