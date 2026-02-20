"""Add missing indexes on FK columns and unique constraints.

Revision ID: 022
Revises: 021
Create Date: 2026-02-20

Adds:
- Index on evidence_fragments.evidence_id
- Indexes on metric_readings.metric_id and metric_readings.engagement_id
- Index on annotations.engagement_id
- Index on monitoring_alerts.monitoring_job_id
- Indexes on pattern_access_rules.pattern_id and pattern_access_rules.engagement_id
- UniqueConstraint on best_practices(domain, industry, tom_dimension)
- UniqueConstraint on benchmarks(metric_name, industry)
- UniqueConstraint on success_metrics(name, category)
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # -- Missing FK indexes ------------------------------------------------------

    op.create_index(
        "ix_evidence_fragments_evidence_id",
        "evidence_fragments",
        ["evidence_id"],
    )

    op.create_index(
        "ix_metric_readings_metric_id",
        "metric_readings",
        ["metric_id"],
    )

    op.create_index(
        "ix_metric_readings_engagement_id",
        "metric_readings",
        ["engagement_id"],
    )

    op.create_index(
        "ix_annotations_engagement_id",
        "annotations",
        ["engagement_id"],
    )

    op.create_index(
        "ix_monitoring_alerts_monitoring_job_id",
        "monitoring_alerts",
        ["monitoring_job_id"],
    )

    op.create_index(
        "ix_pattern_access_rules_pattern_id",
        "pattern_access_rules",
        ["pattern_id"],
    )

    op.create_index(
        "ix_pattern_access_rules_engagement_id",
        "pattern_access_rules",
        ["engagement_id"],
    )

    # -- Unique constraints ------------------------------------------------------

    op.create_unique_constraint(
        "uq_best_practice_domain_industry_dimension",
        "best_practices",
        ["domain", "industry", "tom_dimension"],
    )

    op.create_unique_constraint(
        "uq_benchmark_metric_industry",
        "benchmarks",
        ["metric_name", "industry"],
    )

    op.create_unique_constraint(
        "uq_success_metric_name_category",
        "success_metrics",
        ["name", "category"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_success_metric_name_category", "success_metrics", type_="unique")

    op.drop_constraint("uq_benchmark_metric_industry", "benchmarks", type_="unique")

    op.drop_constraint("uq_best_practice_domain_industry_dimension", "best_practices", type_="unique")

    op.drop_index("ix_pattern_access_rules_engagement_id", table_name="pattern_access_rules")

    op.drop_index("ix_pattern_access_rules_pattern_id", table_name="pattern_access_rules")

    op.drop_index("ix_monitoring_alerts_monitoring_job_id", table_name="monitoring_alerts")

    op.drop_index("ix_annotations_engagement_id", table_name="annotations")

    op.drop_index("ix_metric_readings_engagement_id", table_name="metric_readings")

    op.drop_index("ix_metric_readings_metric_id", table_name="metric_readings")

    op.drop_index("ix_evidence_fragments_evidence_id", table_name="evidence_fragments")
