"""Create task mining tables.

Revision ID: 027
Revises: 026
Create Date: 2026-02-25

Creates the task mining infrastructure tables:
- task_mining_agents: registered desktop agent instances
- task_mining_sessions: capture sessions per agent
- task_mining_events: raw desktop events (clicks, keystrokes, app switches)
- task_mining_actions: aggregated user actions derived from events
- pii_quarantine: events flagged by Layer 3 PII detection
"""

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON, UUID


def upgrade() -> None:
    # -- task_mining_agents ----------------------------------------------------
    op.create_table(
        "task_mining_agents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("hostname", sa.String(255), nullable=False),
        sa.Column("os_version", sa.String(100), nullable=False),
        sa.Column("agent_version", sa.String(50), nullable=False),
        sa.Column("machine_id", sa.String(255), nullable=False, unique=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending_approval"),
        sa.Column("deployment_mode", sa.String(50), nullable=False),
        sa.Column("capture_granularity", sa.String(50), nullable=False, server_default="action_level"),
        sa.Column("config_json", JSON, nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("engagement_end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_task_mining_agents_engagement_id", "task_mining_agents", ["engagement_id"])
    op.create_index("ix_task_mining_agents_status", "task_mining_agents", ["status"])

    # -- task_mining_sessions --------------------------------------------------
    op.create_table(
        "task_mining_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "agent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("task_mining_agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "engagement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("action_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("pii_detections", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_task_mining_sessions_agent_id", "task_mining_sessions", ["agent_id"])
    op.create_index(
        "ix_task_mining_sessions_engagement_id", "task_mining_sessions", ["engagement_id"]
    )

    # -- task_mining_events ----------------------------------------------------
    op.create_table(
        "task_mining_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("task_mining_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "engagement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("application_name", sa.String(255), nullable=True),
        sa.Column("window_title", sa.String(512), nullable=True),
        sa.Column("event_data", JSON, nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=True, unique=True),
        sa.Column("pii_filtered", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_task_mining_events_session_id", "task_mining_events", ["session_id"])
    op.create_index(
        "ix_task_mining_events_engagement_id", "task_mining_events", ["engagement_id"]
    )
    op.create_index("ix_task_mining_events_event_type", "task_mining_events", ["event_type"])
    op.create_index("ix_task_mining_events_timestamp", "task_mining_events", ["timestamp"])

    # -- task_mining_actions ---------------------------------------------------
    op.create_table(
        "task_mining_actions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("task_mining_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "engagement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("application_name", sa.String(255), nullable=False),
        sa.Column("window_title", sa.String(512), nullable=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("event_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action_data", JSON, nullable=True),
        sa.Column(
            "evidence_item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("evidence_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_task_mining_actions_session_id", "task_mining_actions", ["session_id"])
    op.create_index(
        "ix_task_mining_actions_engagement_id", "task_mining_actions", ["engagement_id"]
    )
    op.create_index("ix_task_mining_actions_category", "task_mining_actions", ["category"])

    # -- pii_quarantine --------------------------------------------------------
    op.create_table(
        "pii_quarantine",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("original_event_data", JSON, nullable=False),
        sa.Column("pii_type", sa.String(50), nullable=False),
        sa.Column("pii_field", sa.String(255), nullable=False),
        sa.Column("detection_confidence", sa.Float, nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending_review"),
        sa.Column("reviewed_by", sa.String(255), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auto_delete_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_pii_quarantine_engagement_id", "pii_quarantine", ["engagement_id"])
    op.create_index("ix_pii_quarantine_status", "pii_quarantine", ["status"])
    op.create_index("ix_pii_quarantine_auto_delete_at", "pii_quarantine", ["auto_delete_at"])


def downgrade() -> None:
    op.drop_table("pii_quarantine")
    op.drop_table("task_mining_actions")
    op.drop_table("task_mining_events")
    op.drop_table("task_mining_sessions")
    op.drop_table("task_mining_agents")
