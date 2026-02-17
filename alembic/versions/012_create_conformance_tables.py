"""Create conformance checking tables.

Tables: reference_process_models, conformance_results.

Revision ID: 012
Revises: 011
Create Date: 2026-02-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- reference_process_models --
    op.create_table(
        "reference_process_models",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("industry", sa.String(255), nullable=False),
        sa.Column("process_area", sa.String(255), nullable=False),
        sa.Column("bpmn_xml", sa.Text(), nullable=False),
        sa.Column("graph_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_reference_process_models_industry", "reference_process_models", ["industry"])

    # -- conformance_results --
    op.create_table(
        "conformance_results",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("engagement_id", sa.UUID(), sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reference_model_id", sa.UUID(), sa.ForeignKey("reference_process_models.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pov_model_id", sa.UUID(), sa.ForeignKey("process_models.id", ondelete="SET NULL"), nullable=True),
        sa.Column("fitness_score", sa.Float(), nullable=False),
        sa.Column("precision_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("deviations", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_conformance_results_engagement_id", "conformance_results", ["engagement_id"])
    op.create_index("ix_conformance_results_reference_model_id", "conformance_results", ["reference_model_id"])


def downgrade() -> None:
    op.drop_table("conformance_results")
    op.drop_table("reference_process_models")
