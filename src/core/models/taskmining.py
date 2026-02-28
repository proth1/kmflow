"""Task mining models: agent registration, sessions, events, actions, and PII quarantine.

Supports the KMFlow native desktop agent for capturing and processing user
activity data with mandatory 4-layer PII filtering.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import ARRAY, Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AgentStatus(enum.StrEnum):
    """Lifecycle status of a task mining agent."""

    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    ACTIVE = "active"
    PAUSED = "paused"
    REVOKED = "revoked"
    EXPIRED = "expired"


class DeploymentMode(enum.StrEnum):
    """Agent deployment context."""

    ENGAGEMENT = "engagement"
    ENTERPRISE = "enterprise"


class CaptureGranularity(enum.StrEnum):
    """Level of keystroke capture detail."""

    ACTION_LEVEL = "action_level"
    CONTENT_LEVEL = "content_level"


class DesktopEventType(enum.StrEnum):
    """Types of desktop events captured by the agent."""

    APP_SWITCH = "app_switch"
    WINDOW_FOCUS = "window_focus"
    MOUSE_CLICK = "mouse_click"
    MOUSE_DOUBLE_CLICK = "mouse_double_click"
    MOUSE_DRAG = "mouse_drag"
    KEYBOARD_ACTION = "keyboard_action"
    KEYBOARD_SHORTCUT = "keyboard_shortcut"
    COPY_PASTE = "copy_paste"
    SCROLL = "scroll"
    TAB_SWITCH = "tab_switch"
    FILE_OPEN = "file_open"
    FILE_SAVE = "file_save"
    URL_NAVIGATION = "url_navigation"
    SCREEN_CAPTURE = "screen_capture"
    UI_ELEMENT_INTERACTION = "ui_element_interaction"
    IDLE_START = "idle_start"
    IDLE_END = "idle_end"


class SessionStatus(enum.StrEnum):
    """Status of a task mining capture session."""

    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"


class ActionCategory(enum.StrEnum):
    """High-level categories for aggregated user actions."""

    FILE_OPERATION = "file_operation"
    DATA_ENTRY = "data_entry"
    NAVIGATION = "navigation"
    COMMUNICATION = "communication"
    REVIEW = "review"
    SYSTEM_OPERATION = "system_operation"
    UNKNOWN = "unknown"


class PIIType(enum.StrEnum):
    """Types of PII detected and quarantined."""

    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    EMAIL = "email"
    PHONE = "phone"
    ADDRESS = "address"
    NAME = "name"
    DATE_OF_BIRTH = "date_of_birth"
    FINANCIAL = "financial"
    MEDICAL = "medical"
    OTHER = "other"


class QuarantineStatus(enum.StrEnum):
    """Status of a quarantined PII event."""

    PENDING_REVIEW = "pending_review"
    RELEASED = "released"
    DELETED = "deleted"
    AUTO_DELETED = "auto_deleted"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TaskMiningAgent(Base):
    """A registered desktop agent instance.

    Each physical machine running the agent gets one registration record.
    Agents must be approved before they can submit events.
    """

    __tablename__ = "task_mining_agents"
    __table_args__ = (
        Index("ix_task_mining_agents_engagement_id", "engagement_id"),
        Index("ix_task_mining_agents_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    os_version: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_version: Mapped[str] = mapped_column(String(50), nullable=False)
    machine_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    status: Mapped[AgentStatus] = mapped_column(
        Enum(AgentStatus, values_callable=lambda e: [x.value for x in e]), default=AgentStatus.PENDING_APPROVAL, nullable=False
    )
    deployment_mode: Mapped[DeploymentMode] = mapped_column(Enum(DeploymentMode, values_callable=lambda e: [x.value for x in e]), nullable=False)
    capture_granularity: Mapped[CaptureGranularity] = mapped_column(
        Enum(CaptureGranularity, values_callable=lambda e: [x.value for x in e]), default=CaptureGranularity.ACTION_LEVEL, nullable=False
    )
    config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    engagement_end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    engagement: Mapped["Engagement"] = relationship("Engagement")
    sessions: Mapped[list[TaskMiningSession]] = relationship("TaskMiningSession", back_populates="agent")

    def __repr__(self) -> str:
        return f"<TaskMiningAgent(id={self.id}, hostname='{self.hostname}', status={self.status})>"


class TaskMiningSession(Base):
    """A capture session (start → stop) on an agent.

    Sessions track continuous capture periods. An agent may have multiple
    sessions per day (e.g., user starts/stops capture).
    """

    __tablename__ = "task_mining_sessions"
    __table_args__ = (
        Index("ix_task_mining_sessions_agent_id", "agent_id"),
        Index("ix_task_mining_sessions_engagement_id", "engagement_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task_mining_agents.id", ondelete="CASCADE"), nullable=False
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, values_callable=lambda e: [x.value for x in e]), default=SessionStatus.ACTIVE, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    action_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pii_detections: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    agent: Mapped[TaskMiningAgent] = relationship("TaskMiningAgent", back_populates="sessions")

    def __repr__(self) -> str:
        return f"<TaskMiningSession(id={self.id}, agent_id={self.agent_id}, status={self.status})>"


class TaskMiningEvent(Base):
    """A single raw desktop event captured by the agent.

    Events are the atomic unit of capture: a click, a keystroke count,
    an app switch, etc. They arrive in batches and are processed into
    higher-level actions by the aggregation engine.
    """

    __tablename__ = "task_mining_events"
    __table_args__ = (
        Index("ix_task_mining_events_session_id", "session_id"),
        Index("ix_task_mining_events_engagement_id", "engagement_id"),
        Index("ix_task_mining_events_event_type", "event_type"),
        Index("ix_task_mining_events_timestamp", "timestamp"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task_mining_sessions.id", ondelete="CASCADE"), nullable=False
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[DesktopEventType] = mapped_column(Enum(DesktopEventType, values_callable=lambda e: [x.value for x in e]), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    application_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    window_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    event_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    pii_filtered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<TaskMiningEvent(id={self.id}, type={self.event_type}, app='{self.application_name}')>"


class TaskMiningAction(Base):
    """An aggregated user action derived from raw events.

    Actions represent meaningful user behaviors: "edited document for 5min",
    "navigated between 3 screens", "entered data into form fields". They
    are the unit of evidence materialization.
    """

    __tablename__ = "task_mining_actions"
    __table_args__ = (
        Index("ix_task_mining_actions_session_id", "session_id"),
        Index("ix_task_mining_actions_engagement_id", "engagement_id"),
        Index("ix_task_mining_actions_category", "category"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task_mining_sessions.id", ondelete="CASCADE"), nullable=False
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[ActionCategory] = mapped_column(Enum(ActionCategory, values_callable=lambda e: [x.value for x in e]), nullable=False)
    application_name: Mapped[str] = mapped_column(String(255), nullable=False)
    window_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    action_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evidence_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<TaskMiningAction(id={self.id}, category={self.category}, app='{self.application_name}')>"


class PIIQuarantine(Base):
    """Events quarantined due to suspected PII content.

    Layer 3 (server-side) PII detection flags events that pass L1/L2
    on-device filtering. Quarantined events are auto-deleted after 24h
    unless manually reviewed and released.
    """

    __tablename__ = "pii_quarantine"
    __table_args__ = (
        Index("ix_pii_quarantine_engagement_id", "engagement_id"),
        Index("ix_pii_quarantine_status", "status"),
        Index("ix_pii_quarantine_auto_delete_at", "auto_delete_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    original_event_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    pii_type: Mapped[PIIType] = mapped_column(Enum(PIIType, values_callable=lambda e: [x.value for x in e]), nullable=False)
    pii_field: Mapped[str] = mapped_column(String(255), nullable=False)
    detection_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[QuarantineStatus] = mapped_column(
        Enum(QuarantineStatus, values_callable=lambda e: [x.value for x in e]), default=QuarantineStatus.PENDING_REVIEW, nullable=False
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auto_delete_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<PIIQuarantine(id={self.id}, pii_type={self.pii_type}, status={self.status})>"


# ---------------------------------------------------------------------------
# VCE (Visual Context Event) Enums
# ---------------------------------------------------------------------------


class ScreenStateClass(enum.StrEnum):
    """Classified screen state from VLM or rule-based heuristics."""

    QUEUE = "queue"
    SEARCH = "search"
    DATA_ENTRY = "data_entry"
    REVIEW = "review"
    ERROR = "error"
    WAITING_LATENCY = "waiting_latency"
    NAVIGATION = "navigation"
    OTHER = "other"


class VCETriggerReason(enum.StrEnum):
    """Reason the VCE pipeline was triggered for this screen state."""

    HIGH_DWELL = "high_dwell"
    LOW_CONFIDENCE = "low_confidence"
    RECURRING_EXCEPTION = "recurring_exception"
    NOVEL_CLUSTER = "novel_cluster"
    TAXONOMY_BOUNDARY = "taxonomy_boundary"


# ---------------------------------------------------------------------------
# VCE Model
# ---------------------------------------------------------------------------


class VisualContextEvent(Base):
    """A visual context event capturing screen state during task mining.

    VCEs are triggered when the classification pipeline detects unusual
    dwell times, low-confidence classifications, recurring exceptions, or
    novel screen clusters. They capture a PII-redacted snapshot of the
    worker's screen state for later WGI alignment analysis.
    """

    __tablename__ = "visual_context_events"
    __table_args__ = (
        Index("ix_vce_engagement_id", "engagement_id"),
        Index("ix_vce_session_id", "session_id"),
        Index("ix_vce_screen_state_class", "screen_state_class"),
        Index("ix_vce_trigger_reason", "trigger_reason"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task_mining_sessions.id", ondelete="SET NULL"), nullable=True
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task_mining_agents.id", ondelete="SET NULL"), nullable=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    screen_state_class: Mapped[ScreenStateClass] = mapped_column(
        Enum(ScreenStateClass, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    system_guess: Mapped[str | None] = mapped_column(String(255), nullable=True)
    module_guess: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    trigger_reason: Mapped[VCETriggerReason] = mapped_column(
        Enum(VCETriggerReason, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    sensitivity_flags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    application_name: Mapped[str] = mapped_column(String(512), nullable=False)
    window_title_redacted: Mapped[str | None] = mapped_column(String(512), nullable=True)
    dwell_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    interaction_intensity: Mapped[float | None] = mapped_column(Float, nullable=True)
    snapshot_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    ocr_text_redacted: Mapped[str | None] = mapped_column(Text, nullable=True)
    classification_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    engagement: Mapped["Engagement"] = relationship("Engagement")
    session: Mapped["TaskMiningSession | None"] = relationship("TaskMiningSession")
    agent: Mapped["TaskMiningAgent | None"] = relationship("TaskMiningAgent")

    def __repr__(self) -> str:
        return (
            f"<VisualContextEvent(id={self.id}, screen_state={self.screen_state_class}, "
            f"trigger={self.trigger_reason}, confidence={self.confidence:.2f})>"
        )


# ---------------------------------------------------------------------------
# Switching Sequence Models
# ---------------------------------------------------------------------------


class SwitchingTrace(Base):
    """An observed sequence of application switches within a capture session.

    Represents a continuous chain of APP_SWITCH events where the user moved
    between applications within a bounded time window. Broken on idle gaps
    >5 minutes. Used to measure cognitive load, context-switching friction,
    and ping-pong patterns.
    """

    __tablename__ = "switching_traces"
    __table_args__ = (
        Index("ix_switching_traces_engagement_id", "engagement_id"),
        Index("ix_switching_traces_session_id", "session_id"),
        Index("ix_switching_traces_role_id", "role_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task_mining_sessions.id", ondelete="SET NULL"), nullable=True
    )
    role_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    trace_sequence: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    dwell_durations: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False)
    total_duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    friction_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_ping_pong: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ping_pong_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    app_count: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    engagement: Mapped["Engagement"] = relationship("Engagement")
    session: Mapped["TaskMiningSession | None"] = relationship("TaskMiningSession")

    def __repr__(self) -> str:
        return (
            f"<SwitchingTrace(id={self.id}, apps={self.app_count}, "
            f"friction={self.friction_score:.2f}, ping_pong={self.is_ping_pong})>"
        )


class TransitionMatrix(Base):
    """Aggregated application transition counts for an engagement period.

    Records how often users switch from one application to another within a
    given time window, optionally segmented by role. Used for heat-map
    visualizations and friction hotspot detection.
    """

    __tablename__ = "transition_matrices"
    __table_args__ = (
        Index("ix_transition_matrices_engagement_id", "engagement_id"),
        Index("ix_transition_matrices_role_id", "role_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    matrix_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    total_transitions: Mapped[int] = mapped_column(Integer, nullable=False)
    unique_apps: Mapped[int] = mapped_column(Integer, nullable=False)
    top_transitions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    engagement: Mapped["Engagement"] = relationship("Engagement")

    def __repr__(self) -> str:
        return (
            f"<TransitionMatrix(id={self.id}, engagement_id={self.engagement_id}, "
            f"transitions={self.total_transitions}, apps={self.unique_apps})>"
        )
