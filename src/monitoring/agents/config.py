"""Pydantic configuration models for monitoring agents (Story #346).

Provides typed configuration for each agent type with defaults
for polling intervals, retry behavior, and health thresholds.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RetryConfig(BaseModel):
    """Exponential backoff retry configuration."""

    initial_delay_seconds: float = Field(default=1.0, ge=0.001)
    max_delay_seconds: float = Field(default=60.0, ge=0.01)
    max_consecutive_failures: int = Field(default=3, ge=1)
    backoff_multiplier: float = Field(default=2.0, ge=1.0)


class AgentConfig(BaseModel):
    """Base configuration for a monitoring agent."""

    agent_id: str = Field(..., min_length=1)
    source_type: str = Field(..., min_length=1)
    polling_interval_seconds: float = Field(default=60.0, ge=0.01)
    connection_params: dict[str, str] = Field(default_factory=dict)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    enabled: bool = True
