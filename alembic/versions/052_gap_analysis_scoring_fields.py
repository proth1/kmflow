"""Add composite scoring fields to gap_analysis_results.

Revision ID: 052
Revises: 051
Create Date: 2026-02-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "052"
down_revision = "051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("gap_analysis_results", sa.Column("business_criticality", sa.Integer(), nullable=True))
    op.add_column("gap_analysis_results", sa.Column("risk_exposure", sa.Integer(), nullable=True))
    op.add_column("gap_analysis_results", sa.Column("regulatory_impact", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("gap_analysis_results", "regulatory_impact")
    op.drop_column("gap_analysis_results", "risk_exposure")
    op.drop_column("gap_analysis_results", "business_criticality")
