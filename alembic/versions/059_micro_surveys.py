"""Add micro_surveys table and telemetry_event_id to survey_claims.

Revision ID: 059
Revises: 058
Create Date: 2026-02-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON, UUID

revision = "059"
down_revision = "058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "micro_surveys",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id", UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "triggering_deviation_id", UUID(as_uuid=True),
            sa.ForeignKey("process_deviations.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("target_element_id", sa.String(512), nullable=False),
        sa.Column("target_element_name", sa.String(512), nullable=False),
        sa.Column("target_sme_role", sa.String(255), nullable=False),
        sa.Column("anomaly_description", sa.Text, nullable=False),
        sa.Column("probes", JSON, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="generated"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_micro_surveys_engagement_id", "micro_surveys", ["engagement_id"])
    op.create_index("ix_micro_surveys_triggering_deviation_id", "micro_surveys", ["triggering_deviation_id"])

    # Add telemetry_event_id to survey_claims for linking responses to telemetry events
    op.add_column(
        "survey_claims",
        sa.Column(
            "micro_survey_id", UUID(as_uuid=True),
            sa.ForeignKey("micro_surveys.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.create_index("ix_survey_claims_micro_survey_id", "survey_claims", ["micro_survey_id"])


def downgrade() -> None:
    op.drop_index("ix_survey_claims_micro_survey_id", table_name="survey_claims")
    op.drop_column("survey_claims", "micro_survey_id")
    op.drop_index("ix_micro_surveys_triggering_deviation_id", table_name="micro_surveys")
    op.drop_index("ix_micro_surveys_engagement_id", table_name="micro_surveys")
    op.drop_table("micro_surveys")
