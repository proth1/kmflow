"""Add switching_traces and transition_matrices tables.

Revision ID: 080
Revises: 079
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSON, UUID

revision = "080"
down_revision = "079"
branch_labels = None
depends_on = None

_RLS_VAR = "app.current_engagement_id"


def _apply_rls(table: str) -> list[str]:
    policy = f"engagement_isolation_{table}"
    cond = f"engagement_id = NULLIF(current_setting('{_RLS_VAR}', true), '')::uuid"
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"CREATE POLICY {policy}_select ON {table} FOR SELECT USING ({cond})",
        f"CREATE POLICY {policy}_insert ON {table} FOR INSERT WITH CHECK ({cond})",
        f"CREATE POLICY {policy}_update ON {table} FOR UPDATE USING ({cond}) WITH CHECK ({cond})",
        f"CREATE POLICY {policy}_delete ON {table} FOR DELETE USING ({cond})",
    ]


def _remove_rls(table: str) -> list[str]:
    policy = f"engagement_isolation_{table}"
    return [
        f"DROP POLICY IF EXISTS {policy}_select ON {table}",
        f"DROP POLICY IF EXISTS {policy}_insert ON {table}",
        f"DROP POLICY IF EXISTS {policy}_update ON {table}",
        f"DROP POLICY IF EXISTS {policy}_delete ON {table}",
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY",
    ]


def upgrade() -> None:
    op.create_table(
        "switching_traces",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("task_mining_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("role_id", UUID(as_uuid=True), nullable=True),
        sa.Column("trace_sequence", ARRAY(sa.String()), nullable=False),
        sa.Column("dwell_durations", ARRAY(sa.Integer()), nullable=False),
        sa.Column("total_duration_ms", sa.Integer(), nullable=False),
        sa.Column("friction_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("is_ping_pong", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("ping_pong_count", sa.Integer(), nullable=True),
        sa.Column("app_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_switching_traces_engagement_id", "switching_traces", ["engagement_id"])
    op.create_index("ix_switching_traces_session_id", "switching_traces", ["session_id"])
    op.create_index("ix_switching_traces_role_id", "switching_traces", ["role_id"])

    op.create_table(
        "transition_matrices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role_id", UUID(as_uuid=True), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("matrix_data", JSON(), nullable=False),
        sa.Column("total_transitions", sa.Integer(), nullable=False),
        sa.Column("unique_apps", sa.Integer(), nullable=False),
        sa.Column("top_transitions", JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_transition_matrices_engagement_id", "transition_matrices", ["engagement_id"])
    op.create_index("ix_transition_matrices_role_id", "transition_matrices", ["role_id"])

    # Apply RLS to newly created engagement-scoped tables
    for table in ("switching_traces", "transition_matrices"):
        for stmt in _apply_rls(table):
            op.execute(stmt)


def downgrade() -> None:
    for table in ("transition_matrices", "switching_traces"):
        for stmt in _remove_rls(table):
            op.execute(stmt)

    op.drop_index("ix_transition_matrices_role_id", table_name="transition_matrices")
    op.drop_index("ix_transition_matrices_engagement_id", table_name="transition_matrices")
    op.drop_table("transition_matrices")

    op.drop_index("ix_switching_traces_role_id", table_name="switching_traces")
    op.drop_index("ix_switching_traces_session_id", table_name="switching_traces")
    op.drop_index("ix_switching_traces_engagement_id", table_name="switching_traces")
    op.drop_table("switching_traces")
