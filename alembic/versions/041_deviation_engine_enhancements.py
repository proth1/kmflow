"""Deviation engine enhancements for Story #350.

Adds severity classification, process element tracking, and telemetry
reference to process_deviations table. Adds new deviation categories
and a composite index for filtered queries.

Revision ID: 041
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to process_deviations
    op.add_column("process_deviations", sa.Column("severity", sa.String(20), nullable=True))
    op.add_column("process_deviations", sa.Column("process_element_id", sa.String(255), nullable=True))
    op.add_column("process_deviations", sa.Column("telemetry_ref", sa.String(255), nullable=True))
    op.add_column("process_deviations", sa.Column("severity_score", sa.Float(), nullable=True, server_default="0.0"))

    # Make monitoring_job_id nullable (deviations can come from the engine without a monitoring job)
    op.alter_column("process_deviations", "monitoring_job_id", existing_type=sa.UUID(), nullable=True)

    # Create composite index for filtered deviation queries
    op.create_index(
        "ix_process_deviations_severity_detected",
        "process_deviations",
        ["engagement_id", "detected_at", "severity"],
    )


def downgrade() -> None:
    op.drop_index("ix_process_deviations_severity_detected", table_name="process_deviations")
    op.alter_column("process_deviations", "monitoring_job_id", existing_type=sa.UUID(), nullable=False)
    op.drop_column("process_deviations", "severity_score")
    op.drop_column("process_deviations", "telemetry_ref")
    op.drop_column("process_deviations", "process_element_id")
    op.drop_column("process_deviations", "severity")
