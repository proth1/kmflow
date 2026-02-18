"""Add Phase 8 tables: success_metrics, metric_readings, annotations.

Tables: success_metrics, metric_readings, annotations.
Enum: metriccategory (PostgreSQL).

Revision ID: 014
Revises: 013
Create Date: 2026-02-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# MetricCategory enum values
METRIC_CATEGORY_VALUES = (
    "process_efficiency",
    "quality",
    "compliance",
    "customer_satisfaction",
    "cost",
    "timeliness",
)

metric_category_enum = sa.Enum(
    *METRIC_CATEGORY_VALUES,
    name="metriccategory",
)


def upgrade() -> None:
    # -- Create the MetricCategory PostgreSQL enum --
    metric_category_enum.create(op.get_bind(), checkfirst=True)

    # -- success_metrics --
    op.create_table(
        "success_metrics",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("unit", sa.String(100), nullable=False),
        sa.Column("target_value", sa.Float(), nullable=False),
        sa.Column("category", metric_category_enum, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # -- metric_readings --
    op.create_table(
        "metric_readings",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "metric_id",
            sa.UUID(),
            sa.ForeignKey("success_metrics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "engagement_id",
            sa.UUID(),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_metric_readings_metric_id", "metric_readings", ["metric_id"])
    op.create_index("ix_metric_readings_engagement_id", "metric_readings", ["engagement_id"])

    # -- annotations --
    op.create_table(
        "annotations",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "engagement_id",
            sa.UUID(),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_type", sa.String(100), nullable=False),
        sa.Column("target_id", sa.String(255), nullable=False),
        sa.Column("author_id", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_annotations_engagement_id", "annotations", ["engagement_id"])
    op.create_index("ix_annotations_target", "annotations", ["target_type", "target_id"])


def downgrade() -> None:
    op.drop_table("annotations")
    op.drop_table("metric_readings")
    op.drop_table("success_metrics")
    metric_category_enum.drop(op.get_bind(), checkfirst=True)
