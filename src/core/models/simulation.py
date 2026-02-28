"""Simulation models: status/type enums, SimulationScenario, SimulationResult, ScenarioModification,
EpistemicAction, FinancialAssumption, AlternativeSuggestion."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class SimulationStatus(enum.StrEnum):
    """Lifecycle status of a simulation run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SimulationType(enum.StrEnum):
    """Types of process simulation scenarios."""

    WHAT_IF = "what_if"
    CAPACITY = "capacity"
    PROCESS_CHANGE = "process_change"
    CONTROL_REMOVAL = "control_removal"


class ModificationType(enum.StrEnum):
    """Types of scenario modifications for the Scenario Comparison Workbench."""

    TASK_ADD = "task_add"
    TASK_REMOVE = "task_remove"
    TASK_MODIFY = "task_modify"
    ROLE_REASSIGN = "role_reassign"
    GATEWAY_RESTRUCTURE = "gateway_restructure"
    CONTROL_ADD = "control_add"
    CONTROL_REMOVE = "control_remove"


class FinancialAssumptionType(enum.StrEnum):
    """Types of financial assumptions."""

    COST_PER_ROLE = "cost_per_role"
    TECHNOLOGY_COST = "technology_cost"
    VOLUME_FORECAST = "volume_forecast"
    IMPLEMENTATION_COST = "implementation_cost"


class SuggestionDisposition(enum.StrEnum):
    """Disposition states for alternative suggestions."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    MODIFIED = "modified"
    REJECTED = "rejected"


class SimulationScenario(Base):
    """A what-if simulation scenario definition."""

    __tablename__ = "simulation_scenarios"
    __table_args__ = (Index("ix_simulation_scenarios_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    process_model_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("process_models.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    simulation_type: Mapped[SimulationType] = mapped_column(Enum(SimulationType, values_callable=lambda e: [x.value for x in e]), nullable=False)
    parameters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True, server_default="draft")
    evidence_confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    engagement: Mapped["Engagement"] = relationship("Engagement")
    modifications: Mapped[list[ScenarioModification]] = relationship(
        "ScenarioModification", back_populates="scenario", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<SimulationScenario(id={self.id}, name='{self.name}', type={self.simulation_type})>"


class SimulationResult(Base):
    """Output from a simulation run."""

    __tablename__ = "simulation_results"
    __table_args__ = (Index("ix_simulation_results_scenario_id", "scenario_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulation_scenarios.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[SimulationStatus] = mapped_column(
        Enum(SimulationStatus, values_callable=lambda e: [x.value for x in e]), default=SimulationStatus.PENDING, nullable=False
    )
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    impact_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recommendations: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    execution_time_ms: Mapped[int] = mapped_column(default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    scenario: Mapped[SimulationScenario] = relationship("SimulationScenario")

    def __repr__(self) -> str:
        return f"<SimulationResult(id={self.id}, status={self.status})>"


class ScenarioModification(Base):
    """A modification applied to a simulation scenario."""

    __tablename__ = "scenario_modifications"
    __table_args__ = (Index("ix_scenario_modifications_scenario_id", "scenario_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulation_scenarios.id", ondelete="CASCADE"), nullable=False
    )
    modification_type: Mapped[ModificationType] = mapped_column(Enum(ModificationType, values_callable=lambda e: [x.value for x in e]), nullable=False)
    element_id: Mapped[str] = mapped_column(String(512), nullable=False)
    element_name: Mapped[str] = mapped_column(String(512), nullable=False)
    change_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    template_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    template_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    suggestion_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alternative_suggestions.id", ondelete="SET NULL"), nullable=True
    )
    original_suggestion_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alternative_suggestions.id", ondelete="SET NULL"), nullable=True
    )
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    scenario: Mapped[SimulationScenario] = relationship("SimulationScenario", back_populates="modifications")

    def __repr__(self) -> str:
        return f"<ScenarioModification(id={self.id}, type={self.modification_type}, element='{self.element_name}')>"


class EpistemicAction(Base):
    """A ranked evidence gap action for epistemic planning."""

    __tablename__ = "epistemic_actions"
    __table_args__ = (Index("ix_epistemic_actions_scenario_id", "scenario_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulation_scenarios.id", ondelete="CASCADE"), nullable=False
    )
    target_element_id: Mapped[str] = mapped_column(String(512), nullable=False)
    target_element_name: Mapped[str] = mapped_column(String(512), nullable=False)
    evidence_gap_description: Mapped[str] = mapped_column(Text, nullable=False)
    current_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    estimated_confidence_uplift: Mapped[float] = mapped_column(Float, nullable=False)
    projected_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    information_gain_score: Mapped[float] = mapped_column(Float, nullable=False)
    recommended_evidence_category: Mapped[str] = mapped_column(String(100), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    shelf_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shelf_data_requests.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    scenario: Mapped[SimulationScenario] = relationship("SimulationScenario")

    def __repr__(self) -> str:
        return (
            f"<EpistemicAction(id={self.id}, element='{self.target_element_name}', gain={self.information_gain_score})>"
        )


class FinancialAssumption(Base):
    """A financial assumption for scenario cost modelling."""

    __tablename__ = "financial_assumptions"
    __table_args__ = (Index("ix_financial_assumptions_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    assumption_type: Mapped[FinancialAssumptionType] = mapped_column(Enum(FinancialAssumptionType, values_callable=lambda e: [x.value for x in e]), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source_evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence_items.id", ondelete="SET NULL"), nullable=True
    )
    confidence_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_range: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    engagement: Mapped["Engagement"] = relationship("Engagement")

    def __repr__(self) -> str:
        return f"<FinancialAssumption(id={self.id}, name='{self.name}', type={self.assumption_type})>"


class FinancialAssumptionVersion(Base):
    """Version history entry for a financial assumption."""

    __tablename__ = "financial_assumption_versions"
    __table_args__ = (Index("ix_fa_versions_assumption_id", "assumption_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assumption_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_assumptions.id", ondelete="CASCADE"), nullable=False
    )
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_range: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_evidence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    confidence_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    assumption: Mapped[FinancialAssumption] = relationship("FinancialAssumption")

    def __repr__(self) -> str:
        return f"<FinancialAssumptionVersion(id={self.id}, assumption={self.assumption_id})>"


class AlternativeSuggestion(Base):
    """An LLM-generated alternative scenario suggestion."""

    __tablename__ = "alternative_suggestions"
    __table_args__ = (
        Index("ix_alternative_suggestions_scenario_id", "scenario_id"),
        Index("ix_alternative_suggestions_engagement_id", "engagement_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulation_scenarios.id", ondelete="CASCADE"), nullable=False
    )
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=True
    )
    suggestion_text: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    governance_flags: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evidence_gaps: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    disposition: Mapped[SuggestionDisposition] = mapped_column(
        Enum(SuggestionDisposition, values_callable=lambda e: [x.value for x in e]), default=SuggestionDisposition.PENDING, nullable=False
    )
    disposition_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    modified_content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    disposed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disposed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    llm_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    llm_response: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    scenario: Mapped[SimulationScenario] = relationship("SimulationScenario")

    def __repr__(self) -> str:
        return f"<AlternativeSuggestion(id={self.id}, disposition={self.disposition})>"
