"""Add Phase 4 security tables and encrypted config.

Adds encrypted_config column to integration_connections,
creates mcp_api_keys table for DB-persisted MCP API keys.

Revision ID: 011
Revises: 010
Create Date: 2026-02-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- Add encrypted_config to integration_connections --
    op.add_column(
        "integration_connections",
        sa.Column("encrypted_config", sa.Text(), nullable=True),
    )

    # -- mcp_api_keys --
    op.create_table(
        "mcp_api_keys",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key_id", sa.String(64), nullable=False),
        sa.Column("key_hash", sa.String(128), nullable=False),
        sa.Column("client_name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key_id", name="uq_mcp_api_keys_key_id"),
    )
    op.create_index("ix_mcp_api_keys_user_id", "mcp_api_keys", ["user_id"])


def downgrade() -> None:
    op.drop_table("mcp_api_keys")
    op.drop_column("integration_connections", "encrypted_config")
