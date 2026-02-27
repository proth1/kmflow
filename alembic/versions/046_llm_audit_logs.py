"""046: Add llm_audit_logs table for LLM interaction audit trail.

Revision ID: 046
Revises: 045
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, UUID

revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scenario_id",
            UUID(as_uuid=True),
            sa.ForeignKey("simulation_scenarios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("prompt_text", sa.Text, nullable=False),
        sa.Column("response_text", sa.Text, nullable=True),
        sa.Column("evidence_ids", JSON, nullable=True),
        sa.Column("prompt_tokens", sa.Integer, default=0, nullable=False),
        sa.Column("completion_tokens", sa.Integer, default=0, nullable=False),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_llm_audit_logs_scenario_id", "llm_audit_logs", ["scenario_id"])
    op.create_index("ix_llm_audit_logs_user_id", "llm_audit_logs", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_llm_audit_logs_user_id", table_name="llm_audit_logs")
    op.drop_index("ix_llm_audit_logs_scenario_id", table_name="llm_audit_logs")
    op.drop_table("llm_audit_logs")
