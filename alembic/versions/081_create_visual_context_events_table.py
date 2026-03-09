"""Create visual_context_events table for VCE pipeline.

Revision ID: 081
Revises: 080
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, UUID

revision = "081"
down_revision = "080"
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
        "visual_context_events",
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
        sa.Column(
            "agent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("task_mining_agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("screen_state_class", sa.String(50), nullable=False),
        sa.Column("system_guess", sa.String(255), nullable=True),
        sa.Column("module_guess", sa.String(255), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("trigger_reason", sa.String(50), nullable=False),
        sa.Column("sensitivity_flags", ARRAY(sa.String()), nullable=True),
        sa.Column("application_name", sa.String(512), nullable=False),
        sa.Column("window_title_redacted", sa.String(512), nullable=True),
        sa.Column("dwell_ms", sa.Integer(), nullable=False),
        sa.Column("interaction_intensity", sa.Float(), nullable=True),
        sa.Column("snapshot_ref", sa.String(1024), nullable=True),
        sa.Column("ocr_text_redacted", sa.Text(), nullable=True),
        sa.Column("classification_method", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index("ix_vce_engagement_id", "visual_context_events", ["engagement_id"])
    op.create_index("ix_vce_session_id", "visual_context_events", ["session_id"])
    op.create_index("ix_vce_screen_state_class", "visual_context_events", ["screen_state_class"])
    op.create_index("ix_vce_trigger_reason", "visual_context_events", ["trigger_reason"])
    op.create_index("ix_vce_timestamp", "visual_context_events", ["timestamp"])

    # Apply RLS to newly created engagement-scoped table
    for stmt in _apply_rls("visual_context_events"):
        op.execute(stmt)


def downgrade() -> None:
    for stmt in _remove_rls("visual_context_events"):
        op.execute(stmt)

    op.drop_index("ix_vce_timestamp", table_name="visual_context_events")
    op.drop_index("ix_vce_trigger_reason", table_name="visual_context_events")
    op.drop_index("ix_vce_screen_state_class", table_name="visual_context_events")
    op.drop_index("ix_vce_session_id", table_name="visual_context_events")
    op.drop_index("ix_vce_engagement_id", table_name="visual_context_events")
    op.drop_table("visual_context_events")
