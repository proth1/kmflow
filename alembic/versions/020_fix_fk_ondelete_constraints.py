"""Fix missing ondelete constraints on FK columns.

Revision ID: 020
Revises: 019
Create Date: 2026-02-20
"""
from typing import Union

from alembic import op

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # MetricReading.metric_id -> CASCADE
    op.drop_constraint("metric_readings_metric_id_fkey", "metric_readings", type_="foreignkey")
    op.create_foreign_key(
        "metric_readings_metric_id_fkey", "metric_readings", "success_metrics",
        ["metric_id"], ["id"], ondelete="CASCADE"
    )

    # MetricReading.engagement_id -> CASCADE
    op.drop_constraint("metric_readings_engagement_id_fkey", "metric_readings", type_="foreignkey")
    op.create_foreign_key(
        "metric_readings_engagement_id_fkey", "metric_readings", "engagements",
        ["engagement_id"], ["id"], ondelete="CASCADE"
    )

    # Annotation.engagement_id -> CASCADE
    op.drop_constraint("annotations_engagement_id_fkey", "annotations", type_="foreignkey")
    op.create_foreign_key(
        "annotations_engagement_id_fkey", "annotations", "engagements",
        ["engagement_id"], ["id"], ondelete="CASCADE"
    )

    # AlternativeSuggestion.created_by -> SET NULL (make nullable)
    op.alter_column("alternative_suggestions", "created_by", nullable=True)
    op.drop_constraint("alternative_suggestions_created_by_fkey", "alternative_suggestions", type_="foreignkey")
    op.create_foreign_key(
        "alternative_suggestions_created_by_fkey", "alternative_suggestions", "users",
        ["created_by"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    # Revert AlternativeSuggestion.created_by
    op.drop_constraint("alternative_suggestions_created_by_fkey", "alternative_suggestions", type_="foreignkey")
    op.create_foreign_key(
        "alternative_suggestions_created_by_fkey", "alternative_suggestions", "users",
        ["created_by"], ["id"]
    )
    op.alter_column("alternative_suggestions", "created_by", nullable=False)

    # Revert Annotation.engagement_id
    op.drop_constraint("annotations_engagement_id_fkey", "annotations", type_="foreignkey")
    op.create_foreign_key(
        "annotations_engagement_id_fkey", "annotations", "engagements",
        ["engagement_id"], ["id"]
    )

    # Revert MetricReading.engagement_id
    op.drop_constraint("metric_readings_engagement_id_fkey", "metric_readings", type_="foreignkey")
    op.create_foreign_key(
        "metric_readings_engagement_id_fkey", "metric_readings", "engagements",
        ["engagement_id"], ["id"]
    )

    # Revert MetricReading.metric_id
    op.drop_constraint("metric_readings_metric_id_fkey", "metric_readings", type_="foreignkey")
    op.create_foreign_key(
        "metric_readings_metric_id_fkey", "metric_readings", "success_metrics",
        ["metric_id"], ["id"]
    )
