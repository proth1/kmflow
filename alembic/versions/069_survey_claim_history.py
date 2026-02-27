"""Add survey_claim_history table for certainty tier audit trail.

Revision ID: 069
Revises: 068
Create Date: 2026-02-27

Story #322: Certainty Tier Tracking and SurveyClaim Management — records
tier transitions with timestamp and changed_by for audit trail.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "069"
down_revision = "068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "survey_claim_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "claim_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("survey_claims.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "previous_tier",
            sa.Enum(
                "known", "suspected", "unknown", "contradicted",
                name="certaintytier",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "new_tier",
            sa.Enum(
                "known", "suspected", "unknown", "contradicted",
                name="certaintytier",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("changed_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_survey_claim_history_claim_id",
        "survey_claim_history",
        ["claim_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_survey_claim_history_claim_id", table_name="survey_claim_history")
    op.drop_table("survey_claim_history")
