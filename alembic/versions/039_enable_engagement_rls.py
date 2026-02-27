"""Enable Row-Level Security on all engagement-scoped tables.

Implements database-level data isolation per engagement using PostgreSQL RLS.
Each table gets SELECT, INSERT, UPDATE, DELETE policies that filter by
the session variable `app.current_engagement_id`.

Story #311 — Engagement-Level Data Isolation via PostgreSQL Row-Level Security.

Revision ID: 039
Revises: 038
Create Date: 2026-02-27
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from src.core.rls import ENGAGEMENT_SCOPED_TABLES, apply_engagement_rls, remove_engagement_rls

# revision identifiers, used by Alembic
revision: str = "039"
down_revision: str | None = "038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Enable RLS on all engagement-scoped tables."""
    for table_name in ENGAGEMENT_SCOPED_TABLES:
        for stmt in apply_engagement_rls(table_name):
            op.execute(stmt)


def downgrade() -> None:
    """Disable RLS and remove all policies."""
    for table_name in ENGAGEMENT_SCOPED_TABLES:
        for stmt in remove_engagement_rls(table_name):
            op.execute(stmt)
