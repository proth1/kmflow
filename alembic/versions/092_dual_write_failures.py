"""092: Add dual_write_failures table for cross-store write compensation.

Records failed Neo4j (or other secondary store) writes so a compensation
job can retry them after the primary PostgreSQL write has committed.

Revision ID: 092
Revises: 091
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "092"
down_revision = "091"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dual_write_failures",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_table", sa.String(100), nullable=False),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("target", sa.String(50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retried", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_dual_write_failures_source_table_id",
        "dual_write_failures",
        ["source_table", "source_id"],
    )
    op.create_index(
        "ix_dual_write_failures_retried_created",
        "dual_write_failures",
        ["retried", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_dual_write_failures_retried_created", table_name="dual_write_failures")
    op.drop_index("ix_dual_write_failures_source_table_id", table_name="dual_write_failures")
    op.drop_table("dual_write_failures")
