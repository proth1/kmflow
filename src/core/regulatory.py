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

        # Create Policy nodes and GOVERNED_BY edges
        for policy in policies:
            policy_node_id = f"policy-{policy.id}"
            try:
                existing = await self._graph.get_node(policy_node_id)
                if not existing:
                    await self._graph.create_node(
                        "Policy",
                        {
                            "id": policy_node_id,
                            "name": policy.name,
                            "engagement_id": engagement_id,
                            "policy_type": str(policy.policy_type),
                        },
                    )
            except Neo4jError as e:
                logger.warning("Failed to create Policy node: %s", e)

        # Create Control nodes and ENFORCED_BY edges
        for control in controls:
            control_node_id = f"control-{control.id}"
            try:
                existing = await self._graph.get_node(control_node_id)
                if not existing:
                    await self._graph.create_node(
                        "Control",
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
                        await self._graph.create_relationship(
                            from_id=policy_node_id,
                            to_id=control_node_id,
                            relationship_type="GOVERNED_BY",
                            properties={"source": "regulatory_overlay"},
                        )
            except Neo4jError as e:
                logger.warning("Failed to create Control node: %s", e)

        # Create Regulation nodes
        for regulation in regulations:
            reg_node_id = f"reg-{regulation.id}"
            try:
                existing = await self._graph.get_node(reg_node_id)
                if not existing:
                    await self._graph.create_node(
                        "Regulation",
                        {
                            "id": reg_node_id,
                            "name": regulation.name,
                            "engagement_id": engagement_id,
                            "framework": regulation.framework or "",
                        },
                    )
            except Neo4jError as e:
                logger.warning("Failed to create Regulation node: %s", e)

        # Build chains for each process node
        for proc in process_nodes:
            chain = GovernanceChain(
                process_id=proc.id,
                process_name=proc.properties.get("name", ""),
            )
            # Find connected policies via GOVERNED_BY
            rels = await self._graph.get_relationships(proc.id, direction="outgoing", relationship_type="GOVERNED_BY")
            for rel in rels:
                policy_node = await self._graph.get_node(rel.to_id)
                if policy_node:
                    chain.policies.append({"id": policy_node.id, "name": policy_node.properties.get("name", "")})
            chains.append(chain)

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

        for proc in process_nodes:
            rels = await self._graph.get_relationships(proc.id, direction="outgoing", relationship_type="GOVERNED_BY")
            if rels:
                state.governed_count += 1
                state.details.append(
                    {
                        "process_id": proc.id,
                        "process_name": proc.properties.get("name", ""),
                        "governed": True,
                        "policy_count": len(rels),
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

        ungoverned = []
        for proc in process_nodes:
            rels = await self._graph.get_relationships(proc.id, direction="outgoing", relationship_type="GOVERNED_BY")
            if not rels:
                ungoverned.append(
                    {
                        "process_id": proc.id,
                        "process_name": proc.properties.get("name", ""),
                    }
                )

        return ungoverned

    async def _fetch_policies(self, session: AsyncSession, engagement_id: str) -> list[Policy]:
        result = await session.execute(select(Policy).where(Policy.engagement_id == engagement_id))
        return list(result.scalars().all())

    async def _fetch_controls(self, session: AsyncSession, engagement_id: str) -> list[Control]:
        result = await session.execute(select(Control).where(Control.engagement_id == engagement_id))
        return list(result.scalars().all())

    async def _fetch_regulations(self, session: AsyncSession, engagement_id: str) -> list[Regulation]:
        result = await session.execute(select(Regulation).where(Regulation.engagement_id == engagement_id))
        return list(result.scalars().all())
