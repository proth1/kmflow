"""Monitoring models: status/alert enums, SuccessMetric, MetricReading, Annotation, IntegrationConnection,
ProcessBaseline, MonitoringJob, ProcessDeviation, MonitoringAlert."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.core.models.engagement import Engagement


class MetricCategory(enum.StrEnum):
    """Categories for success metrics."""

    PROCESS_EFFICIENCY = "process_efficiency"
    QUALITY = "quality"
    COMPLIANCE = "compliance"
    CUSTOMER_SATISFACTION = "customer_satisfaction"
    COST = "cost"
    TIMELINESS = "timeliness"


class MonitoringStatus(enum.StrEnum):
    """Status of a monitoring job."""

    CONFIGURING = "configuring"
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    STOPPED = "stopped"


class AlertSeverity(enum.StrEnum):
    """Severity levels for monitoring alerts."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AlertStatus(enum.StrEnum):
    """Lifecycle status of a monitoring alert."""

    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class DeviationCategory(enum.StrEnum):
    """Categories of process deviations."""

    SEQUENCE_CHANGE = "sequence_change"
    MISSING_ACTIVITY = "missing_activity"
    NEW_ACTIVITY = "new_activity"
    ROLE_CHANGE = "role_change"
    TIMING_ANOMALY = "timing_anomaly"
    FREQUENCY_CHANGE = "frequency_change"
    CONTROL_BYPASS = "control_bypass"
    SKIPPED_ACTIVITY = "skipped_activity"
    UNDOCUMENTED_ACTIVITY = "undocumented_activity"
    ROLE_REASSIGNMENT = "role_reassignment"
    MISSING_EXPECTED_ACTIVITY = "missing_expected_activity"


class DeviationSeverity(enum.StrEnum):
    """Severity classification for deviations."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class MonitoringSourceType(enum.StrEnum):
    """Types of monitoring data sources."""

    EVENT_LOG = "event_log"
    TASK_MINING = "task_mining"
    SYSTEM_API = "system_api"
    FILE_WATCH = "file_watch"


class SuccessMetric(Base):
    """Definition of a success metric for engagement measurement."""

    __tablename__ = "success_metrics"
    __table_args__ = (UniqueConstraint("name", "category", name="uq_success_metric_name_category"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(100), nullable=False)
    target_value: Mapped[float] = mapped_column(Float, nullable=False)
    category: Mapped[MetricCategory] = mapped_column(
        Enum(MetricCategory, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    readings: Mapped[list[MetricReading]] = relationship("MetricReading", back_populates="metric")

    def __repr__(self) -> str:
        return f"<SuccessMetric(id={self.id}, name='{self.name}', category='{self.category}')>"


class MetricReading(Base):
    """A recorded value for a success metric at a point in time."""

    __tablename__ = "metric_readings"
    __table_args__ = (
        Index("ix_metric_readings_metric_id", "metric_id"),
        Index("ix_metric_readings_engagement_id", "engagement_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    metric_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("success_metrics.id", ondelete="CASCADE"), nullable=False
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    value: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    metric: Mapped[SuccessMetric] = relationship("SuccessMetric", back_populates="readings")

    def __repr__(self) -> str:
        return f"<MetricReading(id={self.id}, metric_id={self.metric_id}, value={self.value})>"


class Annotation(Base):
    """SME annotation attached to engagement artifacts."""

    __tablename__ = "annotations"
    __table_args__ = (Index("ix_annotations_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False)
    author_id: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Annotation(id={self.id}, target_type='{self.target_type}', target_id='{self.target_id}')>"


class IntegrationConnection(Base):
    """Persisted integration connection configuration (replaces in-memory dict)."""

    __tablename__ = "integration_connections"
    __table_args__ = (Index("ix_integration_connections_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    connector_type: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="configured", nullable=False)
    config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    encrypted_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_mappings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_records: Mapped[int] = mapped_column(default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    engagement: Mapped[Engagement] = relationship("Engagement")

    def __repr__(self) -> str:
        return f"<IntegrationConnection(id={self.id}, type='{self.connector_type}', name='{self.name}')>"


class ProcessBaseline(Base):
    """Frozen snapshot of process model state for comparison."""

    __tablename__ = "process_baselines"
    __table_args__ = (Index("ix_process_baselines_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    process_model_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("process_models.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    snapshot_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    element_count: Mapped[int] = mapped_column(default=0, nullable=False)
    process_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    engagement: Mapped[Engagement] = relationship("Engagement")

    def __repr__(self) -> str:
        return f"<ProcessBaseline(id={self.id}, name='{self.name}')>"


class MonitoringJob(Base):
    """Monitoring configuration per engagement+source."""

    __tablename__ = "monitoring_jobs"
    __table_args__ = (Index("ix_monitoring_jobs_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integration_connections.id", ondelete="SET NULL"), nullable=True
    )
    baseline_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("process_baselines.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[MonitoringSourceType] = mapped_column(
        Enum(MonitoringSourceType, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    status: Mapped[MonitoringStatus] = mapped_column(
        Enum(MonitoringStatus, values_callable=lambda e: [x.value for x in e]),
        default=MonitoringStatus.CONFIGURING,
        nullable=False,
    )
    schedule_cron: Mapped[str] = mapped_column(String(100), default="0 0 * * *", nullable=False)
    config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    engagement: Mapped[Engagement] = relationship("Engagement")

    def __repr__(self) -> str:
        return f"<MonitoringJob(id={self.id}, name='{self.name}', status={self.status})>"


class ProcessDeviation(Base):
    """A detected deviation from baseline process model.

    Enhanced by Story #350 with severity classification, process element
    tracking, and telemetry reference for the deviation detection engine.
    """

    __tablename__ = "process_deviations"
    __table_args__ = (
        Index("ix_process_deviations_job_id", "monitoring_job_id"),
        Index("ix_process_deviations_engagement_id", "engagement_id"),
        Index("ix_process_deviations_severity_detected", "engagement_id", "detected_at", "severity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    monitoring_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("monitoring_jobs.id", ondelete="CASCADE"), nullable=True
    )
    baseline_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("process_baselines.id", ondelete="SET NULL"), nullable=True
    )
    category: Mapped[DeviationCategory] = mapped_column(
        Enum(DeviationCategory, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    severity: Mapped[DeviationSeverity | None] = mapped_column(String(20), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    affected_element: Mapped[str | None] = mapped_column(String(512), nullable=True)
    process_element_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telemetry_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    magnitude: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    severity_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    details_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    engagement: Mapped[Engagement] = relationship("Engagement")

    def __repr__(self) -> str:
        return f"<ProcessDeviation(id={self.id}, category={self.category}, severity={self.severity})>"


class MonitoringAlert(Base):
    """An alert triggered by process deviations."""

    __tablename__ = "monitoring_alerts"
    __table_args__ = (
        Index("ix_monitoring_alerts_engagement_id", "engagement_id"),
        Index("ix_monitoring_alerts_monitoring_job_id", "monitoring_job_id"),
        Index("ix_monitoring_alerts_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    monitoring_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("monitoring_jobs.id", ondelete="CASCADE"), nullable=False
    )
    severity: Mapped[AlertSeverity] = mapped_column(
        Enum(AlertSeverity, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    status: Mapped[AlertStatus] = mapped_column(
        Enum(AlertStatus, values_callable=lambda e: [x.value for x in e]), default=AlertStatus.NEW, nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    deviation_ids: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    dedup_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    engagement: Mapped[Engagement] = relationship("Engagement")

    def __repr__(self) -> str:
        return f"<MonitoringAlert(id={self.id}, severity={self.severity}, status={self.status})>"
