"""Audit models: AuditAction enum, AuditLog, HttpAuditEvent."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class AuditAction(enum.StrEnum):
    """Audit log action types for engagement mutations."""

    ENGAGEMENT_CREATED = "engagement_created"
    ENGAGEMENT_UPDATED = "engagement_updated"
    ENGAGEMENT_ARCHIVED = "engagement_archived"
    EVIDENCE_UPLOADED = "evidence_uploaded"
    EVIDENCE_VALIDATED = "evidence_validated"
    SHELF_REQUEST_CREATED = "shelf_request_created"
    SHELF_REQUEST_UPDATED = "shelf_request_updated"
    LOGIN = "login"
    LOGOUT = "logout"
    PERMISSION_DENIED = "permission_denied"
    DATA_ACCESS = "data_access"
    POV_GENERATED = "pov_generated"
    POLICY_CREATED = "policy_created"
    CONTROL_CREATED = "control_created"
    REGULATION_CREATED = "regulation_created"
    TOM_CREATED = "tom_created"
    GAP_ANALYSIS_RUN = "gap_analysis_run"
    REPORT_GENERATED = "report_generated"
    # -- Phase 3: Monitoring / Alerting / Patterns / Simulation -----------------
    INTEGRATION_CONNECTED = "integration_connected"
    INTEGRATION_SYNCED = "integration_synced"
    MONITORING_CONFIGURED = "monitoring_configured"
    MONITORING_ACTIVATED = "monitoring_activated"
    MONITORING_STOPPED = "monitoring_stopped"
    ALERT_GENERATED = "alert_generated"
    ALERT_ACKNOWLEDGED = "alert_acknowledged"
    ALERT_RESOLVED = "alert_resolved"
    AGENT_GAP_SCAN = "agent_gap_scan"
    PATTERN_CREATED = "pattern_created"
    PATTERN_APPLIED = "pattern_applied"
    SIMULATION_CREATED = "simulation_created"
    SIMULATION_EXECUTED = "simulation_executed"
    SCENARIO_MODIFIED = "scenario_modified"
    SCENARIO_COMPARED = "scenario_compared"
    EPISTEMIC_PLAN_GENERATED = "epistemic_plan_generated"
    # -- Phase 4: Financial / Suggestions ----------------------------------------
    SUGGESTION_CREATED = "suggestion_created"
    SUGGESTION_ACCEPTED = "suggestion_accepted"
    SUGGESTION_REJECTED = "suggestion_rejected"
    FINANCIAL_ASSUMPTION_CREATED = "financial_assumption_created"
    # -- Cross-cutting audit actions ---------------------------------------------
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    MEMBER_ADDED = "member_added"
    MEMBER_REMOVED = "member_removed"
    ANNOTATION_CREATED = "annotation_created"
    ANNOTATION_UPDATED = "annotation_updated"
    ANNOTATION_DELETED = "annotation_deleted"
    CONFORMANCE_MODEL_CREATED = "conformance_model_created"
    CONFORMANCE_CHECK_RUN = "conformance_check_run"
    METRIC_DEFINED = "metric_defined"
    METRIC_READING_RECORDED = "metric_reading_recorded"
    METRICS_SEEDED = "metrics_seeded"
    PATTERN_UPDATED = "pattern_updated"
    PATTERN_DELETED = "pattern_deleted"
    PORTAL_UPLOAD = "portal_upload"
    BASELINE_CREATED = "baseline_created"
    # -- Task mining: agent lifecycle --------------------------------------------
    TASK_MINING_STARTED = "task_mining_started"
    TASK_MINING_STOPPED = "task_mining_stopped"
    AGENT_APPROVED = "agent_approved"
    AGENT_REVOKED = "agent_revoked"
    AGENT_CONSENT_GRANTED = "agent_consent_granted"
    AGENT_CONSENT_REVOKED = "agent_consent_revoked"
    CAPTURE_MODE_CHANGED = "capture_mode_changed"
    # -- Task mining: PII --------------------------------------------------------
    PII_DETECTED = "pii_detected"
    PII_QUARANTINED = "pii_quarantined"
    PII_QUARANTINE_RELEASED = "pii_quarantine_released"
    PII_QUARANTINE_AUTO_DELETED = "pii_quarantine_auto_deleted"
    # -- Conflict resolution workflow (Story #388) --------------------------------
    CONFLICT_ASSIGNED = "conflict_assigned"
    CONFLICT_RESOLVED = "conflict_resolved"
    CONFLICT_ESCALATED = "conflict_escalated"


class AuditLog(Base):
    """Audit log for tracking engagement mutation operations.

    Append-only: a PostgreSQL trigger prevents UPDATE and DELETE on this table.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_engagement_id", "engagement_id"),
        Index("ix_audit_logs_user_id_created_at", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    actor: Mapped[str] = mapped_column(String(255), nullable=False, default="system")
    details: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Columns added by Story #314 ---
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    before_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    result_status: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    engagement: Mapped[Engagement | None] = relationship("Engagement", back_populates="audit_logs")  # noqa: F821

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action={self.action}, engagement_id={self.engagement_id})>"


class HttpAuditEvent(Base):
    """HTTP request audit events for compliance (no engagement FK required).

    Stores all mutating HTTP requests without requiring a valid engagement
    foreign key, enabling audit logging for requests that are not tied to
    a specific engagement (e.g. login, user creation).
    """

    __tablename__ = "http_audit_events"
    __table_args__ = (
        Index("ix_http_audit_events_user_id", "user_id"),
        Index("ix_http_audit_events_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(2048), nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, default="anonymous")
    status_code: Mapped[int] = mapped_column(nullable=False)
    engagement_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # No FK - just string reference
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<HttpAuditEvent(id={self.id}, method='{self.method}', path='{self.path}', user='{self.user_id}')>"
