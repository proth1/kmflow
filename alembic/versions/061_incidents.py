"""Add incidents and incident_events tables for incident response.

Revision ID: 061
Revises: 060
Create Date: 2026-02-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON, UUID

revision = "061"
down_revision = "060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id", UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("classification", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("reported_by", sa.String(255), nullable=False),
        sa.Column("notification_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_summary", sa.Text, nullable=True),
        sa.Column("timeline_json", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("contained_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_incidents_engagement_id", "incidents", ["engagement_id"])
    op.create_index("ix_incidents_classification", "incidents", ["classification"])
    op.create_index("ix_incidents_status", "incidents", ["status"])

    op.create_table(
        "incident_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "incident_id", UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("details_json", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_incident_events_incident_id", "incident_events", ["incident_id"])


def downgrade() -> None:
    op.drop_index("ix_incident_events_incident_id", table_name="incident_events")
    op.drop_table("incident_events")
    op.drop_index("ix_incidents_status", table_name="incidents")
    op.drop_index("ix_incidents_classification", table_name="incidents")
    op.drop_index("ix_incidents_engagement_id", table_name="incidents")
    op.drop_table("incidents")
