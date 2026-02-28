"""Create monitoring tables.

Tables: integration_connections, process_baselines, monitoring_jobs,
        process_deviations, monitoring_alerts.

Revision ID: 009
Revises: 008
Create Date: 2026-02-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- integration_connections --
    op.create_table(
        "integration_connections",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("engagement_id", sa.UUID(), sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connector_type", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="configured"),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("field_mappings", sa.JSON(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_integration_connections_engagement_id", "integration_connections", ["engagement_id"])

    # -- process_baselines --
    op.create_table(
        "process_baselines",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("engagement_id", sa.UUID(), sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("process_model_id", sa.UUID(), sa.ForeignKey("process_models.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("snapshot_data", sa.JSON(), nullable=True),
        sa.Column("element_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("process_hash", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_process_baselines_engagement_id", "process_baselines", ["engagement_id"])

    # -- monitoring_jobs --
    op.create_table(
        "monitoring_jobs",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("engagement_id", sa.UUID(), sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_id", sa.UUID(), sa.ForeignKey("integration_connections.id", ondelete="SET NULL"), nullable=True),
        sa.Column("baseline_id", sa.UUID(), sa.ForeignKey("process_baselines.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source_type", sa.Enum("event_log", "task_mining", "system_api", "file_watch", name="monitoringsourcetype", create_type=True), nullable=False),
        sa.Column("status", sa.Enum("configuring", "active", "paused", "error", "stopped", name="monitoringstatus", create_type=True), nullable=False, server_default="configuring"),
        sa.Column("schedule_cron", sa.String(100), nullable=False, server_default="0 0 * * *"),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_monitoring_jobs_engagement_id", "monitoring_jobs", ["engagement_id"])

    # -- process_deviations --
    op.create_table(
        "process_deviations",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("engagement_id", sa.UUID(), sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("monitoring_job_id", sa.UUID(), sa.ForeignKey("monitoring_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("baseline_id", sa.UUID(), sa.ForeignKey("process_baselines.id", ondelete="SET NULL"), nullable=True),
        sa.Column("category", sa.Enum("sequence_change", "missing_activity", "new_activity", "role_change", "timing_anomaly", "frequency_change", "control_bypass", name="deviationcategory", create_type=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("affected_element", sa.String(512), nullable=True),
        sa.Column("magnitude", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_process_deviations_job_id", "process_deviations", ["monitoring_job_id"])
    op.create_index("ix_process_deviations_engagement_id", "process_deviations", ["engagement_id"])

    # -- monitoring_alerts --
    op.create_table(
        "monitoring_alerts",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("engagement_id", sa.UUID(), sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("monitoring_job_id", sa.UUID(), sa.ForeignKey("monitoring_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("severity", sa.Enum("critical", "high", "medium", "low", "info", name="alertseverity", create_type=True), nullable=False),
        sa.Column("status", sa.Enum("new", "acknowledged", "resolved", "dismissed", name="alertstatus", create_type=True), nullable=False, server_default="new"),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("deviation_ids", sa.JSON(), nullable=True),
        sa.Column("dedup_key", sa.String(255), nullable=True),
        sa.Column("acknowledged_by", sa.String(255), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_monitoring_alerts_engagement_id", "monitoring_alerts", ["engagement_id"])
    op.create_index("ix_monitoring_alerts_status", "monitoring_alerts", ["status"])
    op.create_index("ix_monitoring_alerts_dedup_key", "monitoring_alerts", ["dedup_key"])


def downgrade() -> None:
    op.drop_table("monitoring_alerts")
    op.drop_table("process_deviations")
    op.drop_table("monitoring_jobs")
    op.drop_table("process_baselines")
    op.drop_table("integration_connections")

    op.execute("DROP TYPE IF EXISTS monitoringsourcetype")
    op.execute("DROP TYPE IF EXISTS deviationcategory")
    op.execute("DROP TYPE IF EXISTS alertstatus")
    op.execute("DROP TYPE IF EXISTS alertseverity")
    op.execute("DROP TYPE IF EXISTS monitoringstatus")
