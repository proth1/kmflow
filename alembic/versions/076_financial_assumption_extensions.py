"""Extend financial assumptions with version history and confidence fields.

Revision ID: 076
Revises: 075
Create Date: 2026-02-27

Story #354: Financial data model and assumption management.

Adds confidence_explanation, confidence_range, updated_at to FinancialAssumption.
Creates FinancialAssumptionVersion table for audit trail on updates.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers
revision = "076"
down_revision = "075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extend FinancialAssumption
    op.add_column("financial_assumptions", sa.Column("confidence_explanation", sa.Text(), nullable=True))
    op.add_column("financial_assumptions", sa.Column("confidence_range", sa.Float(), nullable=True))
    op.add_column(
        "financial_assumptions",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Create version history table
    op.create_table(
        "financial_assumption_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "assumption_id",
            UUID(as_uuid=True),
            sa.ForeignKey("financial_assumptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("confidence_range", sa.Float(), nullable=True),
        sa.Column("source_evidence_id", UUID(as_uuid=True), nullable=True),
        sa.Column("confidence_explanation", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "changed_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_fa_versions_assumption_id", "financial_assumption_versions", ["assumption_id"])


def downgrade() -> None:
    op.drop_index("ix_fa_versions_assumption_id", "financial_assumption_versions")
    op.drop_table("financial_assumption_versions")
    op.drop_column("financial_assumptions", "updated_at")
    op.drop_column("financial_assumptions", "confidence_range")
    op.drop_column("financial_assumptions", "confidence_explanation")
