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
from sqlalchemy import text

# revision identifiers, used by Alembic
revision: str = "039"
down_revision: str | None = "038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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


# Tables that existed at the time of this migration (up to revision 038).
# Tables created in later migrations (080+) apply their own RLS.
_TABLES_AT_039: list[str] = [
    "annotations",
    "audit_logs",
    "conflict_objects",
    "conformance_results",
    "controls",
    "copilot_messages",
    "data_catalog_entries",
    "epistemic_frames",
    "evidence_items",
    "financial_assumptions",
    "gap_analysis_results",
    "integration_connections",
    "metric_readings",
    "monitoring_alerts",
    "monitoring_jobs",
    "pattern_access_rules",
    "pii_quarantine",
    "policies",
    "process_baselines",
    "process_deviations",
    "process_models",
    "regulations",
    "seed_terms",
    "semantic_relationships",
    "shelf_data_requests",
    "simulation_scenarios",
    "survey_claims",
    "target_operating_models",
    "task_mining_actions",
    "task_mining_agents",
    "task_mining_events",
    "task_mining_sessions",
]


def _table_exists(table_name: str) -> bool:
    """Check if a table exists in the current database."""
    conn = op.get_bind()
    result = conn.execute(
        text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :t)"),
        {"t": table_name},
    )
    return result.scalar()


def upgrade() -> None:
    """Enable RLS on all engagement-scoped tables that exist at this revision."""
    for table_name in _TABLES_AT_039:
        if _table_exists(table_name):
            for stmt in _apply_rls(table_name):
                op.execute(stmt)


def downgrade() -> None:
    """Disable RLS and remove all policies."""
    for table_name in _TABLES_AT_039:
        if _table_exists(table_name):
            for stmt in _remove_rls(table_name):
                op.execute(stmt)
