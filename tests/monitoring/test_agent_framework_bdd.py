"""BDD tests for Story #346: Monitoring Agent Framework.

Covers all 4 acceptance scenarios:
1. Agent starts and begins polling a configured log source
2. New data detected during polling triggers extraction
3. Connection failure triggers retry with exponential backoff
4. Health check returns status for all running agents
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.monitoring.agents.base import (
    AgentHealth,
    BaseMonitoringAgent,
)
from src.monitoring.agents.config import AgentConfig, RetryConfig
from src.monitoring.agents.registry import AgentRegistry

# ---------------------------------------------------------------------------
# Concrete test agent implementation
# ---------------------------------------------------------------------------


class MockMonitoringAgent(BaseMonitoringAgent):
    """Concrete agent for testing the base class."""

    def __init__(self, config: AgentConfig) -> None:
        super().__init__(config)
        self.connect_calls: int = 0
        self.poll_calls: int = 0
        self.extract_calls: int = 0
        self.alert_calls: list[tuple[str, str]] = []
        self._poll_data: Any = None
        self._connect_error: Exception | None = None
        self._poll_error: Exception | None = None
        self._extract_count: int = 5

    async def connect(self) -> None:
        self.connect_calls += 1
        if self._connect_error:
            raise self._connect_error

    async def poll(self) -> Any:
        self.poll_calls += 1
        if self._poll_error:
            raise self._poll_error
        return self._poll_data

    async def extract(self, raw_data: Any) -> int:
        self.extract_calls += 1
        return self._extract_count

    async def alert(self, message: str, severity: str = "warning") -> None:
        self.alert_calls.append((message, severity))


def make_config(
    agent_id: str = "test-agent-1",
    polling_interval: float = 0.05,
    **kwargs: Any,
) -> AgentConfig:
    """Create a test agent config with fast polling."""
    return AgentConfig(
        agent_id=agent_id,
        source_type="log_source",
        polling_interval_seconds=polling_interval,
        connection_params={"host": "localhost", "port": "5432"},
        **kwargs,
    )


# ===========================================================================
# Scenario 1: Agent starts and begins polling a configured log source
# ===========================================================================


class TestAgentStartsAndPolls:
    """Given a monitoring agent configured for a log source."""

    @pytest.mark.asyncio
    async def test_agent_connects_on_start(self) -> None:
        """Agent establishes connection to the log source on start."""
        config = make_config()
        agent = MockMonitoringAgent(config)

        await agent.start()
        await asyncio.sleep(0.1)
        await agent.stop()

        assert agent.connect_calls == 1

    @pytest.mark.asyncio
    async def test_agent_emits_connected_health_event(self) -> None:
        """Agent emits CONNECTED health status event after successful connection."""
        config = make_config()
        agent = MockMonitoringAgent(config)

        await agent.start()
        await asyncio.sleep(0.1)
        await agent.stop()

        health_statuses = [e.status for e in agent._health_events]
        assert AgentHealth.STARTING in health_statuses
        assert AgentHealth.CONNECTED in health_statuses

    @pytest.mark.asyncio
    async def test_agent_begins_polling_at_interval(self) -> None:
        """Agent polls at the configured interval."""
        config = make_config(polling_interval=0.05)
        agent = MockMonitoringAgent(config)
        agent._poll_data = None  # No new data

        await agent.start()
        await asyncio.sleep(0.2)
        await agent.stop()

        # Should have polled at least twice in 0.2s with 0.05s interval
        assert agent.poll_calls >= 2

    @pytest.mark.asyncio
    async def test_agent_transitions_to_polling_state(self) -> None:
        """Agent transitions to POLLING state during poll cycles."""
        config = make_config()
        agent = MockMonitoringAgent(config)

        await agent.start()
        await asyncio.sleep(0.1)
        await agent.stop()

        health_statuses = [e.status for e in agent._health_events]
        assert AgentHealth.POLLING in health_statuses

    def test_agent_config_polling_interval(self) -> None:
        """Agent config stores the polling interval."""
        config = make_config(polling_interval=60.0)
        assert config.polling_interval_seconds == 60.0

    def test_agent_config_connection_params(self) -> None:
        """Agent config stores connection parameters."""
        config = make_config()
        assert config.connection_params["host"] == "localhost"
        assert config.connection_params["port"] == "5432"


# ===========================================================================
# Scenario 2: New data detected during polling triggers extraction
# ===========================================================================


class TestDataExtraction:
    """Given a monitoring agent actively polling a data source."""

    @pytest.mark.asyncio
    async def test_new_data_triggers_extraction(self) -> None:
        """When new data is detected, it is extracted and passed to pipeline."""
        config = make_config()
        agent = MockMonitoringAgent(config)
        agent._poll_data = [{"event": "test"}]  # Simulate new data
        agent._extract_count = 3

        await agent.start()
        await asyncio.sleep(0.15)
        await agent.stop()

        assert agent.extract_calls >= 1
        assert agent.items_processed_total >= 3

    @pytest.mark.asyncio
    async def test_watermark_advances_after_extraction(self) -> None:
        """Agent advances watermark after successful extraction."""
        config = make_config()
        agent = MockMonitoringAgent(config)
        agent._poll_data = [{"event": "test"}]

        assert agent.watermark is None

        await agent.start()
        await asyncio.sleep(0.15)
        await agent.stop()

        assert agent.watermark is not None

    @pytest.mark.asyncio
    async def test_extraction_event_emitted(self) -> None:
        """Extraction event includes item count and source metadata."""
        config = make_config()
        agent = MockMonitoringAgent(config)
        agent._poll_data = [{"event": "test"}]
        agent._extract_count = 7

        await agent.start()
        await asyncio.sleep(0.15)
        await agent.stop()

        assert len(agent._extraction_events) >= 1
        event = agent._extraction_events[0]
        assert event.item_count == 7
        assert event.source_metadata.get("source_type") == "log_source"

    @pytest.mark.asyncio
    async def test_no_data_skips_extraction(self) -> None:
        """When poll returns None, no extraction occurs."""
        config = make_config()
        agent = MockMonitoringAgent(config)
        agent._poll_data = None

        await agent.start()
        await asyncio.sleep(0.15)
        await agent.stop()

        assert agent.extract_calls == 0

    @pytest.mark.asyncio
    async def test_last_poll_time_updated(self) -> None:
        """last_poll_time is updated after each poll cycle."""
        config = make_config()
        agent = MockMonitoringAgent(config)
        agent._poll_data = None

        assert agent.last_poll_time is None

        await agent.start()
        await asyncio.sleep(0.15)
        await agent.stop()

        assert agent.last_poll_time is not None


# ===========================================================================
# Scenario 3: Connection failure triggers retry with exponential backoff
# ===========================================================================


class TestRetryWithBackoff:
    """Given a monitoring agent that encounters failures."""

    @pytest.mark.asyncio
    async def test_connection_failure_reports_unhealthy(self) -> None:
        """Agent reports UNHEALTHY after connection failure."""
        config = make_config()
        agent = MockMonitoringAgent(config)
        agent._connect_error = ConnectionError("Connection refused")

        await agent.start()
        await asyncio.sleep(0.1)
        await agent.stop()

        assert agent.health == AgentHealth.STOPPED  # Stop sets STOPPED
        health_statuses = [e.status for e in agent._health_events]
        assert AgentHealth.UNHEALTHY in health_statuses

    @pytest.mark.asyncio
    async def test_connection_failure_raises_alert(self) -> None:
        """Alert raised with failure details on connection error."""
        config = make_config()
        agent = MockMonitoringAgent(config)
        agent._connect_error = ConnectionError("Connection refused")

        await agent.start()
        await asyncio.sleep(0.1)
        await agent.stop()

        assert len(agent.alert_calls) >= 1
        assert "Connection refused" in agent.alert_calls[0][0]
        assert agent.alert_calls[0][1] == "critical"

    def test_exponential_backoff_computation(self) -> None:
        """Backoff doubles: 1s, 2s, 4s, 8s, up to max 60s."""
        config = make_config(
            retry=RetryConfig(
                initial_delay_seconds=1.0,
                max_delay_seconds=60.0,
                backoff_multiplier=2.0,
            )
        )
        agent = MockMonitoringAgent(config)

        agent.consecutive_failures = 1
        assert agent._compute_backoff() == 1.0

        agent.consecutive_failures = 2
        assert agent._compute_backoff() == 2.0

        agent.consecutive_failures = 3
        assert agent._compute_backoff() == 4.0

        agent.consecutive_failures = 4
        assert agent._compute_backoff() == 8.0

    def test_backoff_capped_at_max(self) -> None:
        """Backoff never exceeds max_delay_seconds."""
        config = make_config(
            retry=RetryConfig(
                initial_delay_seconds=1.0,
                max_delay_seconds=60.0,
                backoff_multiplier=2.0,
            )
        )
        agent = MockMonitoringAgent(config)

        agent.consecutive_failures = 100
        assert agent._compute_backoff() == 60.0

    @pytest.mark.asyncio
    async def test_poll_failure_degrades_before_unhealthy(self) -> None:
        """Agent enters DEGRADED state before UNHEALTHY on poll failures."""
        config = make_config(
            retry=RetryConfig(
                max_consecutive_failures=3,
                initial_delay_seconds=0.01,
                max_delay_seconds=0.02,
            )
        )
        agent = MockMonitoringAgent(config)
        agent._poll_error = RuntimeError("Timeout")

        await agent.start()
        await asyncio.sleep(0.3)
        await agent.stop()

        health_statuses = [e.status for e in agent._health_events]
        assert AgentHealth.DEGRADED in health_statuses

    @pytest.mark.asyncio
    async def test_unhealthy_after_max_failures(self) -> None:
        """Agent reports UNHEALTHY after max consecutive failures."""
        config = make_config(
            retry=RetryConfig(
                max_consecutive_failures=3,
                initial_delay_seconds=0.01,
                max_delay_seconds=0.02,
            )
        )
        agent = MockMonitoringAgent(config)
        agent._poll_error = RuntimeError("Timeout")

        await agent.start()
        await asyncio.sleep(0.5)
        await agent.stop()

        health_statuses = [e.status for e in agent._health_events]
        assert AgentHealth.UNHEALTHY in health_statuses

    @pytest.mark.asyncio
    async def test_watermark_preserved_on_failure(self) -> None:
        """Watermark is not discarded on failure."""
        config = make_config()
        agent = MockMonitoringAgent(config)
        agent._poll_data = [{"event": "test"}]

        await agent.start()
        await asyncio.sleep(0.15)

        # Record watermark
        watermark_before = agent.watermark
        assert watermark_before is not None

        # Now make polling fail
        agent._poll_error = RuntimeError("Failure")
        agent._poll_data = None
        await asyncio.sleep(0.15)
        await agent.stop()

        # Watermark should NOT be cleared
        assert agent.watermark == watermark_before

    @pytest.mark.asyncio
    async def test_consecutive_failures_reset_on_success(self) -> None:
        """Consecutive failure count resets after a successful poll."""
        config = make_config()
        agent = MockMonitoringAgent(config)
        agent._poll_data = None  # No data but no error = success

        await agent.start()
        await asyncio.sleep(0.1)
        await agent.stop()

        assert agent.consecutive_failures == 0


# ===========================================================================
# Scenario 4: Health check returns status for all running agents
# ===========================================================================


class TestHealthEndpoint:
    """Given multiple monitoring agents are running concurrently."""

    def test_registry_tracks_agents(self) -> None:
        """Registry stores registered agents."""
        registry = AgentRegistry()
        agent = MockMonitoringAgent(make_config("agent-1"))
        registry.register(agent)

        assert registry.get_agent_count() == 1
        assert registry.get_agent("agent-1") is agent

    def test_registry_rejects_duplicate_ids(self) -> None:
        """Registry rejects duplicate agent IDs."""
        registry = AgentRegistry()
        agent1 = MockMonitoringAgent(make_config("agent-1"))
        agent2 = MockMonitoringAgent(make_config("agent-1"))

        registry.register(agent1)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(agent2)

    def test_registry_unregister(self) -> None:
        """Registry removes agents on unregister."""
        registry = AgentRegistry()
        agent = MockMonitoringAgent(make_config("agent-1"))
        registry.register(agent)
        registry.unregister("agent-1")

        assert registry.get_agent_count() == 0

    def test_health_status_includes_required_fields(self) -> None:
        """Health status includes id, status, last_poll_time, items_processed."""
        config = make_config()
        agent = MockMonitoringAgent(config)
        status = agent.get_health_status()

        assert "agent_id" in status
        assert "status" in status
        assert "last_poll_time" in status
        assert "items_processed_total" in status

    def test_get_all_health_returns_list(self) -> None:
        """get_all_health returns status for all registered agents."""
        registry = AgentRegistry()
        for i in range(3):
            agent = MockMonitoringAgent(make_config(f"agent-{i}"))
            registry.register(agent)

        health = registry.get_all_health()
        assert len(health) == 3
        ids = {h["agent_id"] for h in health}
        assert ids == {"agent-0", "agent-1", "agent-2"}

    def test_healthy_count(self) -> None:
        """get_healthy_count counts CONNECTED and POLLING agents."""
        registry = AgentRegistry()
        a1 = MockMonitoringAgent(make_config("a1"))
        a1.health = AgentHealth.POLLING
        a2 = MockMonitoringAgent(make_config("a2"))
        a2.health = AgentHealth.CONNECTED
        a3 = MockMonitoringAgent(make_config("a3"))
        a3.health = AgentHealth.DEGRADED

        registry.register(a1)
        registry.register(a2)
        registry.register(a3)

        assert registry.get_healthy_count() == 2
        assert registry.get_degraded_count() == 1
        assert registry.get_unhealthy_count() == 0

    def test_health_endpoint_exists_in_router(self) -> None:
        """Router should have /agents/health route."""
        from src.api.routes.monitoring import router

        route_paths = [r.path for r in router.routes]
        assert any(p.endswith("/agents/health") for p in route_paths)

    def test_health_response_model_fields(self) -> None:
        """AgentHealthResponse should have required fields."""
        from src.api.routes.monitoring import AgentHealthResponse

        fields = AgentHealthResponse.model_fields
        assert "agents" in fields
        assert "total" in fields
        assert "healthy" in fields
        assert "degraded" in fields
        assert "unhealthy" in fields


# ===========================================================================
# Config model tests
# ===========================================================================


class TestAgentConfig:
    """Test Pydantic config models."""

    def test_default_config(self) -> None:
        """AgentConfig has sensible defaults."""
        config = AgentConfig(agent_id="test", source_type="log")
        assert config.polling_interval_seconds == 60.0
        assert config.enabled is True
        assert config.connection_params == {}

    def test_retry_config_defaults(self) -> None:
        """RetryConfig has correct defaults."""
        retry = RetryConfig()
        assert retry.initial_delay_seconds == 1.0
        assert retry.max_delay_seconds == 60.0
        assert retry.max_consecutive_failures == 3
        assert retry.backoff_multiplier == 2.0

    def test_custom_retry_config(self) -> None:
        """Custom retry config overrides defaults."""
        retry = RetryConfig(
            initial_delay_seconds=0.5,
            max_delay_seconds=30.0,
            max_consecutive_failures=5,
        )
        assert retry.max_consecutive_failures == 5
        assert retry.max_delay_seconds == 30.0

    def test_config_validation_min_interval(self) -> None:
        """Polling interval must be >= 0.01 seconds."""
        with pytest.raises(ValueError):
            AgentConfig(
                agent_id="test",
                source_type="log",
                polling_interval_seconds=0.001,
            )

    def test_agent_health_enum_values(self) -> None:
        """AgentHealth enum has all expected states."""
        assert AgentHealth.STARTING == "starting"
        assert AgentHealth.CONNECTED == "connected"
        assert AgentHealth.POLLING == "polling"
        assert AgentHealth.DEGRADED == "degraded"
        assert AgentHealth.UNHEALTHY == "unhealthy"
        assert AgentHealth.STOPPED == "stopped"


# ===========================================================================
# Lifecycle tests
# ===========================================================================


class TestAgentLifecycle:
    """Test agent lifecycle transitions."""

    @pytest.mark.asyncio
    async def test_start_then_stop(self) -> None:
        """Agent can be started and stopped cleanly."""
        config = make_config()
        agent = MockMonitoringAgent(config)

        await agent.start()
        assert agent._running is True
        await asyncio.sleep(0.05)
        await agent.stop()
        assert agent._running is False
        assert agent.health == AgentHealth.STOPPED

    @pytest.mark.asyncio
    async def test_double_start_is_noop(self) -> None:
        """Starting an already running agent is a no-op."""
        config = make_config()
        agent = MockMonitoringAgent(config)

        await agent.start()
        await agent.start()  # Second start
        await asyncio.sleep(0.05)
        await agent.stop()

        assert agent.connect_calls == 1  # Only connected once

    @pytest.mark.asyncio
    async def test_stop_without_start(self) -> None:
        """Stopping a non-started agent sets STOPPED cleanly."""
        config = make_config()
        agent = MockMonitoringAgent(config)

        await agent.stop()
        assert agent.health == AgentHealth.STOPPED
