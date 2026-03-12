"""Add data_residency_restriction to engagements (KMFLOW-7).

Revision ID: 086
Revises: 085
Create Date: 2026-03-11

Adds an engagement-level data residency restriction column that controls
whether external API calls (LLM, embeddings, connectors) are permitted.
Values: NONE, EU_ONLY, UK_ONLY, CUSTOM.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "086"
down_revision = "085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "engagements",
        sa.Column(
            "data_residency_restriction",
            sa.String(20),
            server_default="none",
            nullable=False,
        ),
    )
    op.create_index(
        "ix_engagements_data_residency_restriction",
        "engagements",
        ["data_residency_restriction"],
    )


def downgrade() -> None:
    op.drop_index("ix_engagements_data_residency_restriction", table_name="engagements")
    op.drop_column("engagements", "data_residency_restriction")
