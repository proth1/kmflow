"""Add Phase 5 tables: copilot_messages, retention_days.

Tables: copilot_messages.
Columns: retention_days on engagements.

Revision ID: 013
Revises: 012
Create Date: 2026-02-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- Add retention_days to engagements --
    op.add_column(
        "engagements",
        sa.Column("retention_days", sa.BigInteger(), nullable=True),
    )

    # -- copilot_messages --
    op.create_table(
        "copilot_messages",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("engagement_id", sa.UUID(), sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("query_type", sa.String(50), nullable=True),
        sa.Column("citations", sa.JSON(), nullable=True),
        sa.Column("context_tokens_used", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_copilot_messages_engagement_id", "copilot_messages", ["engagement_id"])
    op.create_index("ix_copilot_messages_user_id", "copilot_messages", ["user_id"])


def downgrade() -> None:
    op.drop_table("copilot_messages")
    op.drop_column("engagements", "retention_days")
