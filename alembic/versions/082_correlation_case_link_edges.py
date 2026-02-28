"""Add case_link_edges table and correlation fields on canonical_activity_events.

Revision ID: 082
Revises: 081
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON, UUID

revision = "082"
down_revision = "081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_link_edges",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            UUID(as_uuid=True),
            sa.ForeignKey("canonical_activity_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("case_id", sa.String(255), nullable=False),
        sa.Column("method", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("explainability", JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_case_links_engagement", "case_link_edges", ["engagement_id"])
    op.create_index("ix_case_links_case_id", "case_link_edges", ["case_id"])
    op.create_index("ix_case_links_event_id", "case_link_edges", ["event_id"])

    # Denormalised correlation outputs on canonical events for fast filtering
    op.add_column("canonical_activity_events", sa.Column("link_method", sa.String(50), nullable=True))
    op.add_column("canonical_activity_events", sa.Column("link_confidence", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("canonical_activity_events", "link_confidence")
    op.drop_column("canonical_activity_events", "link_method")

    op.drop_index("ix_case_links_event_id", table_name="case_link_edges")
    op.drop_index("ix_case_links_case_id", table_name="case_link_edges")
    op.drop_index("ix_case_links_engagement", table_name="case_link_edges")
    op.drop_table("case_link_edges")
