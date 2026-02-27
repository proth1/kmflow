"""Agent registry for lifecycle management and health aggregation (Story #346).

Manages running monitoring agents, provides start/stop/health operations,
and aggregates health status across all agents.
"""

from __future__ import annotations

import logging
from typing import Any

from src.monitoring.agents.base import AgentHealth, BaseMonitoringAgent

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Registry of monitoring agents with lifecycle management.

    Thread-safe for concurrent agent start/stop operations within
    a single asyncio event loop.
    """

    def __init__(self) -> None:
        self._agents: dict[str, BaseMonitoringAgent] = {}

    def register(self, agent: BaseMonitoringAgent) -> None:
        """Register an agent without starting it.

        Args:
            agent: The monitoring agent to register.

        Raises:
            ValueError: If an agent with the same ID is already registered.
        """
        if agent.agent_id in self._agents:
            raise ValueError(f"Agent {agent.agent_id} is already registered")
        self._agents[agent.agent_id] = agent
        logger.info("Registered agent: %s", agent.agent_id)

    async def start_agent(self, agent_id: str) -> None:
        """Start a registered agent.

        Args:
            agent_id: The agent ID to start.

        Raises:
            KeyError: If agent is not registered.
        """
        agent = self._agents.get(agent_id)
        if agent is None:
            raise KeyError(f"Agent {agent_id} not found in registry")
        await agent.start()
        logger.info("Started agent: %s", agent_id)

    async def stop_agent(self, agent_id: str) -> None:
        """Stop a running agent.

        Args:
            agent_id: The agent ID to stop.

        Raises:
            KeyError: If agent is not registered.
        """
        agent = self._agents.get(agent_id)
        if agent is None:
            raise KeyError(f"Agent {agent_id} not found in registry")
        await agent.stop()
        logger.info("Stopped agent: %s", agent_id)

    async def stop_all(self) -> None:
        """Stop all running agents."""
        for agent in self._agents.values():
            if agent.health not in (AgentHealth.STOPPED,):
                await agent.stop()

    def unregister(self, agent_id: str) -> None:
        """Remove an agent from the registry.

        Args:
            agent_id: The agent ID to remove.

        Raises:
            KeyError: If agent is not registered.
        """
        if agent_id not in self._agents:
            raise KeyError(f"Agent {agent_id} not found in registry")
        del self._agents[agent_id]
        logger.info("Unregistered agent: %s", agent_id)

    def get_agent(self, agent_id: str) -> BaseMonitoringAgent | None:
        """Get an agent by ID."""
        return self._agents.get(agent_id)

    def get_all_health(self) -> list[dict[str, Any]]:
        """Get health status for all registered agents."""
        return [agent.get_health_status() for agent in self._agents.values()]

    def get_agent_count(self) -> int:
        """Get total number of registered agents."""
        return len(self._agents)

    def get_healthy_count(self) -> int:
        """Count agents in healthy states (CONNECTED or POLLING)."""
        return sum(1 for a in self._agents.values() if a.health in (AgentHealth.CONNECTED, AgentHealth.POLLING))

    def get_unhealthy_count(self) -> int:
        """Count agents in unhealthy state."""
        return sum(1 for a in self._agents.values() if a.health == AgentHealth.UNHEALTHY)

    def get_degraded_count(self) -> int:
        """Count agents in degraded state."""
        return sum(1 for a in self._agents.values() if a.health == AgentHealth.DEGRADED)
