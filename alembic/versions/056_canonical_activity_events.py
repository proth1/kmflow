"""056: Add canonical_activity_events table for event spine.

Revision ID: 056
Revises: 055
Create Date: 2026-02-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSON, UUID

revision = "056"
down_revision = "055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "canonical_activity_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id", UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("case_id", sa.String(255), nullable=False),
        sa.Column("activity_name", sa.String(512), nullable=False),
        sa.Column("timestamp_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_system", sa.String(255), nullable=False),
        sa.Column("performer_role_ref", sa.String(255), nullable=True),
        sa.Column("evidence_refs", ARRAY(UUID(as_uuid=True)), nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("brightness", sa.String(50), nullable=True),
        sa.Column(
            "mapping_status",
            sa.Enum("mapped", "unmapped", name="eventmappingstatus", create_type=True),
            nullable=False,
            server_default="mapped",
        ),
        sa.Column("process_element_id", UUID(as_uuid=True), nullable=True),
        sa.Column("raw_payload", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_canonical_events_case_id_ts", "canonical_activity_events", ["case_id", "timestamp_utc"])
    op.create_index("ix_canonical_events_engagement_id", "canonical_activity_events", ["engagement_id"])


def downgrade() -> None:
    op.drop_index("ix_canonical_events_engagement_id", table_name="canonical_activity_events")
    op.drop_index("ix_canonical_events_case_id_ts", table_name="canonical_activity_events")
    op.drop_table("canonical_activity_events")
    op.execute("DROP TYPE IF EXISTS eventmappingstatus")
