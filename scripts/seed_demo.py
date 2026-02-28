"""Seed script: populates KMFlow with realistic demo data.

Creates a complete "Acme Corp Loan Origination" engagement with evidence,
process models, knowledge graph, task mining data, monitoring, simulations,
governance, and TOM analysis.

Usage:
    python -m scripts.seed_demo          # seed everything
    python -m scripts.seed_demo --reset  # wipe and reseed

Requires: running PostgreSQL (port 5433) and Neo4j (port 7688).
"""

from __future__ import annotations

import argparse
import asyncio
import enum
import logging
import random
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

import sqlalchemy as sa

# Patch Enum before importing models: make StrEnum use .value (lowercase)
_original_enum_init = sa.Enum.__init__


def _patched_enum_init(self, *enums, **kw):
    if (
        len(enums) == 1
        and isinstance(enums[0], type)
        and issubclass(enums[0], enum.StrEnum)
        and "values_callable" not in kw
    ):
        kw["values_callable"] = lambda e: [x.value for x in e]
    _original_enum_init(self, *enums, **kw)


sa.Enum.__init__ = _patched_enum_init

import bcrypt  # noqa: E402

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

# Pre-hash "demo" password for all demo users
DEMO_PASSWORD_HASH = bcrypt.hashpw(b"demo", bcrypt.gensalt()).decode()

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Deterministic UUIDs for cross-referencing
# ---------------------------------------------------------------------------
# Use uuid5 with a fixed namespace so IDs are stable across runs.
NS = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def _uid(name: str) -> uuid.UUID:
    return uuid.uuid5(NS, name)


# Core IDs
ENG_ID = _uid("engagement-acme-loan")
USER_ADMIN_ID = _uid("user-admin")
USER_LEAD_ID = _uid("user-lead")
USER_ANALYST_ID = _uid("user-analyst")
USER_CLIENT_ID = _uid("user-client")

# Evidence IDs
EV_IDS = {cat: _uid(f"evidence-{cat}") for cat in [
    "loan-policy", "process-doc", "interview-ops-mgr", "interview-cro",
    "bpmn-as-is", "signavio-export", "screen-recording", "compliance-report",
    "audit-controls", "email-thread", "training-guide", "data-extract",
    "task-mining-obs-1", "task-mining-obs-2", "task-mining-obs-3",
]}

# Process model
PM_ID = _uid("process-model-loan-orig")
PM_ELEMENTS = {
    "Receive Application": _uid("pe-receive-app"),
    "Verify Identity": _uid("pe-verify-id"),
    "Credit Check": _uid("pe-credit-check"),
    "Income Verification": _uid("pe-income-verify"),
    "Risk Assessment": _uid("pe-risk-assess"),
    "Underwriting Decision": _uid("pe-underwrite"),
    "Generate Offer": _uid("pe-gen-offer"),
    "Notify Applicant": _uid("pe-notify"),
    "Loan Officer": _uid("pe-role-loan-officer"),
    "Credit Bureau API": _uid("pe-sys-credit-bureau"),
    "Core Banking System": _uid("pe-sys-core-banking"),
}

# TOM
TOM_ID = _uid("tom-acme-loan")

# Task mining
AGENT_IDS = [_uid(f"tm-agent-{i}") for i in range(3)]
SESSION_IDS = [_uid(f"tm-session-{i}") for i in range(6)]

# Monitoring
BASELINE_ID = _uid("baseline-loan-orig")
MON_JOB_IDS = [_uid(f"mon-job-{i}") for i in range(2)]
METRIC_IDS = [_uid(f"metric-{i}") for i in range(3)]

# Simulations
SCENARIO_IDS = [_uid(f"scenario-{i}") for i in range(3)]

# Switching sequences
SWITCHING_TRACE_IDS = [_uid(f"switching-trace-{i}") for i in range(3)]
TRANSITION_MATRIX_ID = _uid("transition-matrix-loan-orig")

# VCE
VCE_IDS = [_uid(f"vce-event-{i}") for i in range(5)]

# Correlation
CASE_LINK_IDS = [_uid(f"case-link-{i}") for i in range(4)]

NOW = datetime.now(timezone.utc)
TODAY = date.today()


# ---------------------------------------------------------------------------
# Database connection — matches docker-compose.yml defaults
# ---------------------------------------------------------------------------
DB_URL = "postgresql+asyncpg://kmflow:kmflow_dev_password@localhost:5433/kmflow"
NEO4J_URI = "bolt://localhost:7688"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "neo4j_dev_password"


async def reset_data(session: AsyncSession) -> None:
    """Delete all seeded data (cascades handle children)."""
    logger.info("Resetting demo data...")
    await session.execute(text("DELETE FROM engagements WHERE id = :id"), {"id": str(ENG_ID)})
    await session.execute(text("DELETE FROM users WHERE email LIKE '%@acme-demo.com'"))
    await session.execute(text("DELETE FROM best_practices WHERE industry = 'Financial Services'"))
    await session.execute(text("DELETE FROM benchmarks WHERE industry = 'Financial Services'"))
    await session.execute(text("DELETE FROM success_metrics WHERE name LIKE 'Loan%'"))
    await session.execute(text("DELETE FROM pattern_library_entries WHERE industry = 'Financial Services'"))
    await session.commit()
    logger.info("PostgreSQL demo data cleared.")

    # Clear Neo4j
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        with driver.session() as neo_session:
            neo_session.run(
                "MATCH (n) WHERE n.engagement_id = $eid DETACH DELETE n",
                eid=str(ENG_ID),
            )
        driver.close()
        logger.info("Neo4j demo data cleared.")
    except Exception as e:
        logger.warning("Could not clear Neo4j: %s", e)


# ---------------------------------------------------------------------------
# Seed functions — each returns a list of ORM instances
# ---------------------------------------------------------------------------


def seed_users() -> list:
    from src.core.models.auth import User, UserRole

    return [
        User(id=USER_ADMIN_ID, email="admin@acme-demo.com", name="Sarah Chen",
             role=UserRole.PLATFORM_ADMIN, hashed_password=DEMO_PASSWORD_HASH),
        User(id=USER_LEAD_ID, email="lead@acme-demo.com", name="Marcus Johnson",
             role=UserRole.ENGAGEMENT_LEAD, hashed_password=DEMO_PASSWORD_HASH),
        User(id=USER_ANALYST_ID, email="analyst@acme-demo.com", name="Priya Patel",
             role=UserRole.PROCESS_ANALYST, hashed_password=DEMO_PASSWORD_HASH),
        User(id=USER_CLIENT_ID, email="viewer@acme-demo.com", name="David Kim",
             role=UserRole.CLIENT_VIEWER, hashed_password=DEMO_PASSWORD_HASH),
    ]


def seed_engagement() -> list:
    from src.core.models.auth import EngagementMember
    from src.core.models.engagement import Engagement, EngagementStatus

    eng = Engagement(
        id=ENG_ID,
        name="Acme Corp — Loan Origination Transformation",
        client="Acme Financial Services",
        business_area="Retail Lending",
        description=(
            "End-to-end process intelligence engagement for Acme Corp's retail "
            "loan origination. Scope: application intake through funding, covering "
            "identity verification, credit assessment, income verification, "
            "underwriting, and offer generation. Target: 40% cycle time reduction "
            "and 99.5% regulatory compliance."
        ),
        status=EngagementStatus.ACTIVE,
        team=["Sarah Chen", "Marcus Johnson", "Priya Patel"],
        retention_days=365,
    )

    members = [
        EngagementMember(engagement_id=ENG_ID, user_id=USER_LEAD_ID, role_in_engagement="lead"),
        EngagementMember(engagement_id=ENG_ID, user_id=USER_ANALYST_ID, role_in_engagement="analyst"),
        EngagementMember(engagement_id=ENG_ID, user_id=USER_CLIENT_ID, role_in_engagement="client_viewer"),
    ]
    return [eng, *members]


def seed_evidence() -> list:
    from src.core.models.evidence import (
        DataCatalogEntry,
        DataClassification,
        DataLayer,
        EvidenceCategory,
        EvidenceItem,
        EvidenceLineage,
        ValidationStatus,
    )

    items = [
        # Documents
        EvidenceItem(
            id=EV_IDS["loan-policy"], engagement_id=ENG_ID,
            name="Retail Lending Policy v3.2", category=EvidenceCategory.DOCUMENTS,
            format="pdf", size_bytes=2_450_000, mime_type="application/pdf",
            completeness_score=0.95, reliability_score=0.92, freshness_score=0.88, consistency_score=0.90,
            validation_status=ValidationStatus.VALIDATED, classification=DataClassification.CONFIDENTIAL,
            source_date=date(2025, 11, 15),
            metadata_json={"author": "Risk Committee", "version": "3.2", "pages": 47},
        ),
        EvidenceItem(
            id=EV_IDS["process-doc"], engagement_id=ENG_ID,
            name="Loan Origination Process Narrative", category=EvidenceCategory.DOCUMENTS,
            format="docx", size_bytes=890_000, mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            completeness_score=0.82, reliability_score=0.78, freshness_score=0.70, consistency_score=0.75,
            validation_status=ValidationStatus.VALIDATED,
            source_date=date(2025, 6, 20),
            metadata_json={"author": "Operations", "version": "2.1"},
        ),
        # Audio — interviews
        EvidenceItem(
            id=EV_IDS["interview-ops-mgr"], engagement_id=ENG_ID,
            name="Interview: Operations Manager (J. Rivera)", category=EvidenceCategory.AUDIO,
            format="m4a", size_bytes=45_000_000, mime_type="audio/mp4",
            completeness_score=0.88, reliability_score=0.85, freshness_score=0.95, consistency_score=0.72,
            validation_status=ValidationStatus.VALIDATED,
            source_date=TODAY - timedelta(days=5),
        ),
        EvidenceItem(
            id=EV_IDS["interview-cro"], engagement_id=ENG_ID,
            name="Interview: Chief Risk Officer (T. Nakamura)", category=EvidenceCategory.AUDIO,
            format="m4a", size_bytes=38_000_000, mime_type="audio/mp4",
            completeness_score=0.90, reliability_score=0.88, freshness_score=0.95, consistency_score=0.80,
            validation_status=ValidationStatus.VALIDATED,
            source_date=TODAY - timedelta(days=3),
        ),
        # BPM Process Models
        EvidenceItem(
            id=EV_IDS["bpmn-as-is"], engagement_id=ENG_ID,
            name="Loan Origination As-Is BPMN", category=EvidenceCategory.BPM_PROCESS_MODELS,
            format="bpmn", size_bytes=125_000,
            completeness_score=0.75, reliability_score=0.82, freshness_score=0.60, consistency_score=0.70,
            validation_status=ValidationStatus.VALIDATED,
            source_date=date(2024, 9, 1),
        ),
        # SaaS Exports
        EvidenceItem(
            id=EV_IDS["signavio-export"], engagement_id=ENG_ID,
            name="SAP Signavio Process Mining Export", category=EvidenceCategory.SAAS_EXPORTS,
            format="csv", size_bytes=12_500_000,
            completeness_score=0.88, reliability_score=0.92, freshness_score=0.85, consistency_score=0.90,
            validation_status=ValidationStatus.VALIDATED,
            source_date=TODAY - timedelta(days=7),
        ),
        # Video
        EvidenceItem(
            id=EV_IDS["screen-recording"], engagement_id=ENG_ID,
            name="Screen Recording: Application Processing Walkthrough", category=EvidenceCategory.VIDEO,
            format="mp4", size_bytes=250_000_000,
            completeness_score=0.70, reliability_score=0.90, freshness_score=0.92, consistency_score=0.85,
            validation_status=ValidationStatus.VALIDATED,
            source_date=TODAY - timedelta(days=4),
        ),
        # Regulatory
        EvidenceItem(
            id=EV_IDS["compliance-report"], engagement_id=ENG_ID,
            name="OCC Compliance Examination Report 2025", category=EvidenceCategory.REGULATORY_POLICY,
            format="pdf", size_bytes=3_200_000,
            completeness_score=0.92, reliability_score=0.98, freshness_score=0.90, consistency_score=0.95,
            validation_status=ValidationStatus.VALIDATED, classification=DataClassification.RESTRICTED,
            source_date=date(2025, 8, 30),
        ),
        # Controls
        EvidenceItem(
            id=EV_IDS["audit-controls"], engagement_id=ENG_ID,
            name="Internal Audit: Lending Controls Matrix", category=EvidenceCategory.CONTROLS_EVIDENCE,
            format="xlsx", size_bytes=780_000,
            completeness_score=0.85, reliability_score=0.88, freshness_score=0.82, consistency_score=0.86,
            validation_status=ValidationStatus.VALIDATED,
            source_date=date(2025, 10, 1),
        ),
        # Communications
        EvidenceItem(
            id=EV_IDS["email-thread"], engagement_id=ENG_ID,
            name="Email Thread: Underwriting Escalation Process", category=EvidenceCategory.DOMAIN_COMMUNICATIONS,
            format="eml", size_bytes=120_000,
            completeness_score=0.60, reliability_score=0.65, freshness_score=0.90, consistency_score=0.55,
            validation_status=ValidationStatus.VALIDATED,
            source_date=TODAY - timedelta(days=10),
        ),
        # Job Aids
        EvidenceItem(
            id=EV_IDS["training-guide"], engagement_id=ENG_ID,
            name="New Hire Training: Loan Processing Quick Reference", category=EvidenceCategory.JOB_AIDS_EDGE_CASES,
            format="pdf", size_bytes=4_500_000,
            completeness_score=0.72, reliability_score=0.70, freshness_score=0.55, consistency_score=0.68,
            validation_status=ValidationStatus.VALIDATED,
            source_date=date(2024, 3, 15),
        ),
        # Structured data
        EvidenceItem(
            id=EV_IDS["data-extract"], engagement_id=ENG_ID,
            name="Core Banking: Loan Application Event Log (6 months)", category=EvidenceCategory.STRUCTURED_DATA,
            format="parquet", size_bytes=85_000_000,
            completeness_score=0.95, reliability_score=0.98, freshness_score=0.92, consistency_score=0.96,
            validation_status=ValidationStatus.VALIDATED,
            source_date=TODAY - timedelta(days=2),
        ),
        # KM4Work — task mining observations
        EvidenceItem(
            id=EV_IDS["task-mining-obs-1"], engagement_id=ENG_ID,
            name="Task Mining: Application Entry Sessions (Week 1)", category=EvidenceCategory.KM4WORK,
            format="json", size_bytes=2_100_000,
            completeness_score=0.90, reliability_score=0.92, freshness_score=0.98, consistency_score=0.88,
            validation_status=ValidationStatus.ACTIVE,
            source_date=TODAY - timedelta(days=5),
        ),
        EvidenceItem(
            id=EV_IDS["task-mining-obs-2"], engagement_id=ENG_ID,
            name="Task Mining: Credit Check Sessions (Week 1)", category=EvidenceCategory.KM4WORK,
            format="json", size_bytes=1_800_000,
            completeness_score=0.88, reliability_score=0.90, freshness_score=0.98, consistency_score=0.85,
            validation_status=ValidationStatus.ACTIVE,
            source_date=TODAY - timedelta(days=4),
        ),
        EvidenceItem(
            id=EV_IDS["task-mining-obs-3"], engagement_id=ENG_ID,
            name="Task Mining: Underwriting Sessions (Week 1)", category=EvidenceCategory.KM4WORK,
            format="json", size_bytes=2_400_000,
            completeness_score=0.85, reliability_score=0.88, freshness_score=0.98, consistency_score=0.82,
            validation_status=ValidationStatus.ACTIVE,
            source_date=TODAY - timedelta(days=3),
        ),
    ]

    lineage = [
        EvidenceLineage(
            evidence_item_id=EV_IDS["signavio-export"],
            source_system="SAP Signavio",
            source_url="https://editor.signavio.com/p/hub",
            source_identifier="acme-loan-orig-2025",
            transformation_chain=["csv_export", "column_mapping", "timestamp_normalization"],
            version=1,
        ),
        EvidenceLineage(
            evidence_item_id=EV_IDS["data-extract"],
            source_system="Core Banking (Temenos T24)",
            source_identifier="LN.LOAN.APPLICATION.EVENT.LOG",
            transformation_chain=["sql_extract", "pii_redaction", "parquet_conversion"],
            version=1,
        ),
    ]

    catalog = [
        DataCatalogEntry(
            engagement_id=ENG_ID, dataset_name="loan_application_events",
            dataset_type="event_log", layer=DataLayer.BRONZE,
            owner="Data Engineering", classification=DataClassification.CONFIDENTIAL,
            quality_sla={"completeness": 0.95, "freshness_hours": 24},
            retention_days=365, row_count=1_247_832, size_bytes=85_000_000,
            description="Raw event log from Temenos T24 core banking",
        ),
        DataCatalogEntry(
            engagement_id=ENG_ID, dataset_name="loan_application_events_clean",
            dataset_type="event_log", layer=DataLayer.SILVER,
            owner="Data Engineering", classification=DataClassification.CONFIDENTIAL,
            quality_sla={"completeness": 0.98, "freshness_hours": 48},
            retention_days=365, row_count=1_198_456, size_bytes=72_000_000,
            description="Cleaned event log: deduplication, timestamp normalization, PII masked",
        ),
        DataCatalogEntry(
            engagement_id=ENG_ID, dataset_name="process_mining_features",
            dataset_type="feature_store", layer=DataLayer.GOLD,
            owner="Process Intelligence", classification=DataClassification.INTERNAL,
            quality_sla={"completeness": 0.99},
            retention_days=180, row_count=45_672, size_bytes=8_500_000,
            description="Case-level features for process mining and conformance checking",
        ),
    ]

    return [*items, *lineage, *catalog]


def seed_process_model() -> list:
    from src.core.models.pov import (
        Contradiction,
        CorroborationLevel,
        EvidenceGap,
        GapSeverity,
        GapType,
        ProcessElement,
        ProcessElementType,
        ProcessModel,
        ProcessModelStatus,
    )

    pm = ProcessModel(
        id=PM_ID, engagement_id=ENG_ID, version=3,
        scope="Loan Origination: Application Intake through Offer Generation",
        status=ProcessModelStatus.COMPLETED,
        confidence_score=0.78,
        element_count=11, evidence_count=15, contradiction_count=2,
        generated_at=NOW - timedelta(hours=6),
        metadata_json={"lcd_version": "2.1", "triangulation_sources": 15, "iteration": 3},
    )

    elements_data = [
        ("Receive Application", ProcessElementType.ACTIVITY, 0.92, 0.88, CorroborationLevel.STRONGLY, 5),
        ("Verify Identity", ProcessElementType.ACTIVITY, 0.85, 0.80, CorroborationLevel.STRONGLY, 4),
        ("Credit Check", ProcessElementType.ACTIVITY, 0.88, 0.85, CorroborationLevel.STRONGLY, 6),
        ("Income Verification", ProcessElementType.ACTIVITY, 0.72, 0.65, CorroborationLevel.MODERATELY, 3),
        ("Risk Assessment", ProcessElementType.ACTIVITY, 0.68, 0.60, CorroborationLevel.MODERATELY, 2),
        ("Underwriting Decision", ProcessElementType.ACTIVITY, 0.82, 0.78, CorroborationLevel.STRONGLY, 5),
        ("Generate Offer", ProcessElementType.ACTIVITY, 0.75, 0.70, CorroborationLevel.MODERATELY, 3),
        ("Notify Applicant", ProcessElementType.ACTIVITY, 0.60, 0.50, CorroborationLevel.WEAKLY, 1),
        ("Loan Officer", ProcessElementType.ROLE, 0.90, 0.85, CorroborationLevel.STRONGLY, 4),
        ("Credit Bureau API", ProcessElementType.SYSTEM, 0.95, 0.90, CorroborationLevel.STRONGLY, 3),
        ("Core Banking System", ProcessElementType.SYSTEM, 0.88, 0.82, CorroborationLevel.STRONGLY, 5),
    ]

    elements = []
    for name, etype, conf, tri, corr, ev_cnt in elements_data:
        elements.append(ProcessElement(
            id=PM_ELEMENTS[name], model_id=PM_ID,
            element_type=etype, name=name,
            confidence_score=conf, triangulation_score=tri,
            corroboration_level=corr, evidence_count=ev_cnt,
        ))

    contradictions = [
        Contradiction(
            model_id=PM_ID, element_name="Income Verification",
            field_name="sequence_position",
            values=["Before Credit Check (Operations Manager)", "After Credit Check (Policy Document)"],
            resolution_value="After Credit Check",
            resolution_reason="Policy document (v3.2, 2025) supersedes interview (verbal, 2024 recollection)",
            evidence_ids=[str(EV_IDS["interview-ops-mgr"]), str(EV_IDS["loan-policy"])],
        ),
        Contradiction(
            model_id=PM_ID, element_name="Risk Assessment",
            field_name="responsible_role",
            values=["Senior Loan Officer (Policy)", "Underwriter (Interview)"],
            resolution_value="Senior Loan Officer with Underwriter escalation",
            resolution_reason="Combined from policy (primary) and operational practice (escalation path)",
            evidence_ids=[str(EV_IDS["loan-policy"]), str(EV_IDS["interview-cro"])],
        ),
    ]

    gaps = [
        EvidenceGap(
            model_id=PM_ID, gap_type=GapType.WEAK_EVIDENCE,
            description="Notify Applicant step supported by single email thread only",
            severity=GapSeverity.HIGH,
            recommendation="Conduct interview with Customer Service team or obtain notification SOP",
            related_element_id=PM_ELEMENTS["Notify Applicant"],
        ),
        EvidenceGap(
            model_id=PM_ID, gap_type=GapType.MISSING_DATA,
            description="No evidence for exception handling path (declined applications)",
            severity=GapSeverity.HIGH,
            recommendation="Request declined application processing documentation and interview exception handlers",
        ),
        EvidenceGap(
            model_id=PM_ID, gap_type=GapType.SINGLE_SOURCE,
            description="Risk Assessment process documented only in policy; no operational evidence",
            severity=GapSeverity.MEDIUM,
            recommendation="Observe risk assessment sessions via task mining or conduct analyst walkthrough",
            related_element_id=PM_ELEMENTS["Risk Assessment"],
        ),
        EvidenceGap(
            model_id=PM_ID, gap_type=GapType.WEAK_EVIDENCE,
            description="Income Verification duration and rework rate poorly documented",
            severity=GapSeverity.MEDIUM,
            recommendation="Extract income verification cycle time from event log data",
            related_element_id=PM_ELEMENTS["Income Verification"],
        ),
    ]

    return [pm, *elements, *contradictions, *gaps]


def seed_tom() -> list:
    from src.core.models.tom import (
        Benchmark,
        BestPractice,
        GapAnalysisResult,
        TargetOperatingModel,
        TOMDimension,
        TOMGapType,
    )

    tom = TargetOperatingModel(
        id=TOM_ID, engagement_id=ENG_ID,
        name="Acme Retail Lending Target State",
        dimensions={
            "process_architecture": {"current_maturity": 2, "target_maturity": 4},
            "people_and_organization": {"current_maturity": 3, "target_maturity": 4},
            "technology_and_data": {"current_maturity": 2, "target_maturity": 5},
            "governance_structures": {"current_maturity": 3, "target_maturity": 4},
            "performance_management": {"current_maturity": 1, "target_maturity": 4},
            "risk_and_compliance": {"current_maturity": 3, "target_maturity": 5},
        },
        maturity_targets={
            "overall_target": 4,
            "timeline_months": 18,
            "priority_dimensions": ["technology_and_data", "performance_management"],
        },
    )

    gap_data = [
        (TOMDimension.PROCESS_ARCHITECTURE, TOMGapType.PARTIAL_GAP, 0.7, 0.82,
         "Manual handoffs between application intake and verification cause 2-day delays",
         "Implement straight-through processing with automated verification triggers"),
        (TOMDimension.PEOPLE_AND_ORGANIZATION, TOMGapType.DEVIATION, 0.4, 0.75,
         "Loan officers performing both origination and underwriting creates segregation-of-duties risk",
         "Separate origination and underwriting roles with clear handoff protocols"),
        (TOMDimension.TECHNOLOGY_AND_DATA, TOMGapType.FULL_GAP, 0.9, 0.88,
         "No automated decisioning engine; all credit decisions manual despite rule-based criteria",
         "Deploy automated credit decisioning for applications meeting standard criteria (est. 65% of volume)"),
        (TOMDimension.GOVERNANCE_STRUCTURES, TOMGapType.PARTIAL_GAP, 0.5, 0.70,
         "Process change governance informal; no impact assessment required for procedure changes",
         "Establish process change advisory board with mandatory impact assessment"),
        (TOMDimension.PERFORMANCE_MANAGEMENT, TOMGapType.FULL_GAP, 0.85, 0.90,
         "No process-level KPIs tracked; only outcome metrics (approval rate, portfolio quality)",
         "Implement process mining dashboard with real-time cycle time, rework, and bottleneck KPIs"),
        (TOMDimension.RISK_AND_COMPLIANCE, TOMGapType.PARTIAL_GAP, 0.6, 0.85,
         "Compliance checks manual and post-hoc; no real-time regulatory screening",
         "Integrate real-time regulatory screening into application intake workflow"),
    ]

    gaps = [
        GapAnalysisResult(
            engagement_id=ENG_ID, tom_id=TOM_ID,
            gap_type=gt, dimension=dim, severity=sev, confidence=conf,
            rationale=rat, recommendation=rec,
        )
        for dim, gt, sev, conf, rat, rec in gap_data
    ]

    best_practices = [
        BestPractice(
            domain="Lending Operations", industry="Financial Services",
            description="Implement automated pre-screening with 90% straight-through processing target",
            source="McKinsey Banking Practice 2024",
            tom_dimension=TOMDimension.PROCESS_ARCHITECTURE,
        ),
        BestPractice(
            domain="Credit Risk", industry="Financial Services",
            description="Deploy ML credit scoring with human-in-the-loop for edge cases (15% of applications)",
            source="Basel Committee on Banking Supervision",
            tom_dimension=TOMDimension.TECHNOLOGY_AND_DATA,
        ),
        BestPractice(
            domain="Operational Excellence", industry="Financial Services",
            description="Real-time process dashboards with automated alerting for SLA breaches",
            source="APQC Process Classification Framework",
            tom_dimension=TOMDimension.PERFORMANCE_MANAGEMENT,
        ),
    ]

    benchmarks = [
        Benchmark(metric_name="Loan Application Cycle Time (days)", industry="Financial Services",
                  p25=12.0, p50=7.0, p75=4.0, p90=2.0, source="APQC 2024"),
        Benchmark(metric_name="Straight-Through Processing Rate (%)", industry="Financial Services",
                  p25=15.0, p50=35.0, p75=60.0, p90=85.0, source="McKinsey 2024"),
        Benchmark(metric_name="First-Contact Resolution Rate (%)", industry="Financial Services",
                  p25=55.0, p50=70.0, p75=82.0, p90=92.0, source="Forrester 2024"),
        Benchmark(metric_name="Application Abandonment Rate (%)", industry="Financial Services",
                  p25=40.0, p50=28.0, p75=18.0, p90=8.0, source="JD Power 2024"),
    ]

    return [tom, *gaps, *best_practices, *benchmarks]


def seed_task_mining() -> list:
    from src.core.models.taskmining import (
        ActionCategory,
        AgentStatus,
        CaptureGranularity,
        DeploymentMode,
        DesktopEventType,
        PIIQuarantine,
        PIIType,
        QuarantineStatus,
        SessionStatus,
        TaskMiningAction,
        TaskMiningAgent,
        TaskMiningEvent,
        TaskMiningSession,
    )

    agents = [
        TaskMiningAgent(
            id=AGENT_IDS[0], engagement_id=ENG_ID,
            hostname="ACME-LO-WS001", os_version="macOS 14.3",
            agent_version="1.0.0", machine_id="acme-demo-machine-001",
            status=AgentStatus.ACTIVE, deployment_mode=DeploymentMode.ENGAGEMENT,
            capture_granularity=CaptureGranularity.ACTION_LEVEL,
            last_heartbeat_at=NOW - timedelta(seconds=15),
            approved_by="admin@acme-demo.com", approved_at=NOW - timedelta(days=7),
            config_json={"allowed_apps": ["Excel", "Chrome", "Outlook", "Temenos T24"]},
        ),
        TaskMiningAgent(
            id=AGENT_IDS[1], engagement_id=ENG_ID,
            hostname="ACME-LO-WS002", os_version="macOS 14.2",
            agent_version="1.0.0", machine_id="acme-demo-machine-002",
            status=AgentStatus.ACTIVE, deployment_mode=DeploymentMode.ENGAGEMENT,
            capture_granularity=CaptureGranularity.ACTION_LEVEL,
            last_heartbeat_at=NOW - timedelta(seconds=30),
            approved_by="admin@acme-demo.com", approved_at=NOW - timedelta(days=7),
        ),
        TaskMiningAgent(
            id=AGENT_IDS[2], engagement_id=ENG_ID,
            hostname="ACME-LO-WS003", os_version="macOS 14.4",
            agent_version="1.0.0", machine_id="acme-demo-machine-003",
            status=AgentStatus.PENDING_APPROVAL, deployment_mode=DeploymentMode.ENGAGEMENT,
            capture_granularity=CaptureGranularity.ACTION_LEVEL,
        ),
    ]

    sessions = []
    events = []
    actions = []
    rng = random.Random(42)

    apps_windows = [
        ("Temenos T24", "Loan Application - New"),
        ("Temenos T24", "Customer Details - A. Smith"),
        ("Microsoft Excel", "Credit_Score_Calculator.xlsx"),
        ("Google Chrome", "Equifax Credit Bureau Portal"),
        ("Google Chrome", "LexisNexis Identity Verification"),
        ("Microsoft Outlook", "RE: Application #12847 - Docs Needed"),
        ("Microsoft Word", "Underwriting_Decision_Template.docx"),
        ("Adobe Acrobat", "Acme_Lending_Policy_v3.2.pdf"),
    ]

    event_types_by_action = {
        ActionCategory.DATA_ENTRY: [DesktopEventType.KEYBOARD_ACTION, DesktopEventType.MOUSE_CLICK],
        ActionCategory.NAVIGATION: [DesktopEventType.URL_NAVIGATION, DesktopEventType.TAB_SWITCH, DesktopEventType.SCROLL],
        ActionCategory.REVIEW: [DesktopEventType.SCROLL, DesktopEventType.MOUSE_CLICK],
        ActionCategory.COMMUNICATION: [DesktopEventType.KEYBOARD_ACTION, DesktopEventType.MOUSE_CLICK],
        ActionCategory.FILE_OPERATION: [DesktopEventType.FILE_OPEN, DesktopEventType.FILE_SAVE],
    }

    action_descriptions = {
        ActionCategory.DATA_ENTRY: [
            "Entered applicant personal information into T24",
            "Updated income verification fields",
            "Filled credit assessment form",
            "Entered collateral details into system",
        ],
        ActionCategory.NAVIGATION: [
            "Navigated between T24 screens for application review",
            "Switched between credit bureau tabs",
            "Browsed regulatory reference documentation",
        ],
        ActionCategory.REVIEW: [
            "Reviewed credit bureau report",
            "Examined lending policy requirements",
            "Reviewed prior application history",
            "Checked compliance checklist items",
        ],
        ActionCategory.COMMUNICATION: [
            "Composed email requesting missing documents",
            "Replied to underwriting escalation thread",
            "Sent application status update to branch",
        ],
        ActionCategory.FILE_OPERATION: [
            "Opened credit score calculator spreadsheet",
            "Saved underwriting decision document",
            "Opened lending policy PDF for reference",
        ],
    }

    # Create 2 sessions per active agent (6 total)
    for agent_idx in range(2):  # Only active agents
        for sess_offset in range(2):
            sess_idx = agent_idx * 2 + sess_offset + (0 if agent_idx == 0 else 0)
            if sess_idx >= len(SESSION_IDS):
                break
            sess_start = NOW - timedelta(days=sess_offset + 1, hours=rng.randint(1, 6))
            sess_end = sess_start + timedelta(hours=rng.randint(2, 6))
            n_events = rng.randint(80, 250)
            n_actions = rng.randint(12, 30)

            sess = TaskMiningSession(
                id=SESSION_IDS[sess_idx],
                agent_id=AGENT_IDS[agent_idx], engagement_id=ENG_ID,
                status=SessionStatus.ENDED,
                started_at=sess_start, ended_at=sess_end,
                event_count=n_events, action_count=n_actions, pii_detections=rng.randint(0, 3),
            )
            sessions.append(sess)

            # Generate events
            for ev_i in range(min(n_events, 50)):  # cap for DB size
                ev_time = sess_start + timedelta(seconds=ev_i * rng.randint(5, 60))
                if ev_time > sess_end:
                    break
                app, win = rng.choice(apps_windows)
                ev_type = rng.choice([
                    DesktopEventType.KEYBOARD_ACTION, DesktopEventType.MOUSE_CLICK,
                    DesktopEventType.APP_SWITCH, DesktopEventType.SCROLL,
                    DesktopEventType.URL_NAVIGATION, DesktopEventType.FILE_OPEN,
                    DesktopEventType.COPY_PASTE, DesktopEventType.TAB_SWITCH,
                ])
                events.append(TaskMiningEvent(
                    session_id=SESSION_IDS[sess_idx], engagement_id=ENG_ID,
                    event_type=ev_type, timestamp=ev_time,
                    application_name=app, window_title=win,
                    idempotency_key=f"demo-{sess_idx}-{ev_i}",
                    pii_filtered=True,
                ))

            # Generate actions
            for act_i in range(min(n_actions, 15)):  # cap for DB size
                act_start = sess_start + timedelta(minutes=act_i * rng.randint(8, 25))
                if act_start > sess_end:
                    break
                duration = rng.randint(30, 600)
                cat = rng.choice(list(event_types_by_action.keys()))
                app, win = rng.choice(apps_windows)
                desc = rng.choice(action_descriptions[cat])

                actions.append(TaskMiningAction(
                    session_id=SESSION_IDS[sess_idx], engagement_id=ENG_ID,
                    category=cat, application_name=app, window_title=win,
                    description=desc, event_count=rng.randint(5, 50),
                    duration_seconds=float(duration),
                    started_at=act_start, ended_at=act_start + timedelta(seconds=duration),
                ))

    # PII quarantine items
    quarantine = [
        PIIQuarantine(
            engagement_id=ENG_ID,
            original_event_data={"window_title": "SSN: [REDACTED]", "app": "Temenos T24"},
            pii_type=PIIType.SSN, pii_field="window_title",
            detection_confidence=0.98, status=QuarantineStatus.PENDING_REVIEW,
            auto_delete_at=NOW + timedelta(hours=18),
        ),
        PIIQuarantine(
            engagement_id=ENG_ID,
            original_event_data={"window_title": "Card ending [REDACTED]", "app": "Temenos T24"},
            pii_type=PIIType.CREDIT_CARD, pii_field="window_title",
            detection_confidence=0.95, status=QuarantineStatus.PENDING_REVIEW,
            auto_delete_at=NOW + timedelta(hours=20),
        ),
        PIIQuarantine(
            engagement_id=ENG_ID,
            original_event_data={"window_title": "Email: j***@example.com", "app": "Outlook"},
            pii_type=PIIType.EMAIL, pii_field="window_title",
            detection_confidence=0.92, status=QuarantineStatus.DELETED,
            reviewed_by="admin@acme-demo.com", reviewed_at=NOW - timedelta(hours=4),
            auto_delete_at=NOW - timedelta(hours=4),
        ),
    ]

    # Return in dependency order: agents first, then sessions, then events/actions
    return {
        "agents": agents,
        "sessions": sessions,
        "events": events,
        "actions": actions,
        "quarantine": quarantine,
    }


def seed_monitoring() -> list:
    from src.core.models.monitoring import (
        AlertSeverity,
        AlertStatus,
        DeviationCategory,
        MetricCategory,
        MetricReading,
        MonitoringAlert,
        MonitoringJob,
        MonitoringSourceType,
        MonitoringStatus,
        ProcessBaseline,
        ProcessDeviation,
        SuccessMetric,
    )

    baseline = ProcessBaseline(
        id=BASELINE_ID, engagement_id=ENG_ID, process_model_id=PM_ID,
        name="Loan Origination Baseline v1",
        snapshot_data={"element_count": 11, "activities": 8, "roles": 1, "systems": 2},
        element_count=11, is_active=True,
    )

    jobs = [
        MonitoringJob(
            id=MON_JOB_IDS[0], engagement_id=ENG_ID, baseline_id=BASELINE_ID,
            name="Core Banking Event Monitor",
            source_type=MonitoringSourceType.EVENT_LOG,
            status=MonitoringStatus.ACTIVE,
            schedule_cron="0 */4 * * *",
            last_run_at=NOW - timedelta(hours=2),
            next_run_at=NOW + timedelta(hours=2),
        ),
        MonitoringJob(
            id=MON_JOB_IDS[1], engagement_id=ENG_ID, baseline_id=BASELINE_ID,
            name="Task Mining Activity Monitor",
            source_type=MonitoringSourceType.TASK_MINING,
            status=MonitoringStatus.ACTIVE,
            schedule_cron="0 */6 * * *",
            last_run_at=NOW - timedelta(hours=4),
            next_run_at=NOW + timedelta(hours=2),
        ),
    ]

    deviations = [
        ProcessDeviation(
            engagement_id=ENG_ID, monitoring_job_id=MON_JOB_IDS[0], baseline_id=BASELINE_ID,
            category=DeviationCategory.SEQUENCE_CHANGE,
            description="Income verification performed before identity check in 12% of cases",
            affected_element="Income Verification", magnitude=0.12,
        ),
        ProcessDeviation(
            engagement_id=ENG_ID, monitoring_job_id=MON_JOB_IDS[0], baseline_id=BASELINE_ID,
            category=DeviationCategory.MISSING_ACTIVITY,
            description="Risk Assessment step skipped for pre-approved customers (8% of volume)",
            affected_element="Risk Assessment", magnitude=0.08,
        ),
        ProcessDeviation(
            engagement_id=ENG_ID, monitoring_job_id=MON_JOB_IDS[1], baseline_id=BASELINE_ID,
            category=DeviationCategory.TIMING_ANOMALY,
            description="Credit check duration 3.2x longer than baseline on Fridays",
            affected_element="Credit Check", magnitude=3.2,
        ),
        ProcessDeviation(
            engagement_id=ENG_ID, monitoring_job_id=MON_JOB_IDS[0], baseline_id=BASELINE_ID,
            category=DeviationCategory.CONTROL_BYPASS,
            description="Dual-approval control bypassed for loans under $50K (policy requires $100K threshold)",
            affected_element="Underwriting Decision", magnitude=0.35,
        ),
    ]

    alerts = [
        MonitoringAlert(
            engagement_id=ENG_ID, monitoring_job_id=MON_JOB_IDS[0],
            severity=AlertSeverity.CRITICAL, status=AlertStatus.NEW,
            title="Control Bypass: Dual-approval threshold violated",
            description="35% of loans under $50K processed without dual approval. Policy requires approval for all loans. Potential compliance exposure.",
        ),
        MonitoringAlert(
            engagement_id=ENG_ID, monitoring_job_id=MON_JOB_IDS[0],
            severity=AlertSeverity.HIGH, status=AlertStatus.ACKNOWLEDGED,
            title="Process Deviation: Income verification sequence anomaly",
            description="12% of applications have income verification before identity check, contrary to documented process.",
            acknowledged_by="lead@acme-demo.com", acknowledged_at=NOW - timedelta(hours=3),
        ),
        MonitoringAlert(
            engagement_id=ENG_ID, monitoring_job_id=MON_JOB_IDS[1],
            severity=AlertSeverity.MEDIUM, status=AlertStatus.NEW,
            title="Performance: Friday credit check bottleneck",
            description="Credit bureau API response time 3.2x slower on Fridays. Likely caused by batch processing overlap.",
        ),
        MonitoringAlert(
            engagement_id=ENG_ID, monitoring_job_id=MON_JOB_IDS[0],
            severity=AlertSeverity.LOW, status=AlertStatus.RESOLVED,
            title="Risk Assessment skip for pre-approved",
            description="8% of pre-approved applications bypass risk assessment. Confirmed as acceptable per policy exception.",
            resolved_at=NOW - timedelta(hours=8),
        ),
    ]

    metrics = [
        SuccessMetric(id=METRIC_IDS[0], name="Loan Application Cycle Time", unit="days", target_value=5.0,
                      category=MetricCategory.PROCESS_EFFICIENCY,
                      description="Average days from application submission to decision"),
        SuccessMetric(id=METRIC_IDS[1], name="Loan First-Pass Approval Rate", unit="percent", target_value=70.0,
                      category=MetricCategory.QUALITY,
                      description="Percentage of applications approved without rework"),
        SuccessMetric(id=METRIC_IDS[2], name="Loan Compliance Score", unit="percent", target_value=99.5,
                      category=MetricCategory.COMPLIANCE,
                      description="Percentage of applications meeting all regulatory requirements"),
    ]

    # Metric readings over the past 2 weeks
    readings = []
    for metric_idx, metric in enumerate(metrics):
        base_values = [8.5, 58.0, 97.2]  # starting values
        target_values = [5.0, 70.0, 99.5]
        for day in range(14, -1, -1):
            progress = (14 - day) / 14
            val = base_values[metric_idx] + (target_values[metric_idx] - base_values[metric_idx]) * progress * 0.4
            val += random.Random(42 + metric_idx * 100 + day).gauss(0, 0.3)
            readings.append(MetricReading(
                metric_id=metric.id, engagement_id=ENG_ID,
                value=round(val, 2),
                recorded_at=NOW - timedelta(days=day),
            ))

    return {
        "baselines": [baseline],
        "metrics": metrics,
        "jobs": jobs,
        "deviations": deviations,
        "alerts": alerts,
        "readings": readings,
    }


def seed_simulations() -> list:
    from src.core.models.simulation import (
        AlternativeSuggestion,
        FinancialAssumption,
        FinancialAssumptionType,
        SimulationResult,
        SimulationScenario,
        SimulationStatus,
        SimulationType,
        SuggestionDisposition,
    )

    scenarios = [
        SimulationScenario(
            id=SCENARIO_IDS[0], engagement_id=ENG_ID, process_model_id=PM_ID,
            name="Automated Credit Decisioning",
            simulation_type=SimulationType.PROCESS_CHANGE,
            description="Replace manual credit assessment with automated decisioning for standard applications (65% of volume)",
            parameters={"automation_rate": 0.65, "manual_threshold": "non_standard"},
            evidence_confidence_score=0.82,
        ),
        SimulationScenario(
            id=SCENARIO_IDS[1], engagement_id=ENG_ID, process_model_id=PM_ID,
            name="Straight-Through Processing",
            simulation_type=SimulationType.WHAT_IF,
            description="End-to-end automation for low-risk applications with score >720 and income verified",
            parameters={"credit_score_threshold": 720, "stp_rate": 0.40},
            evidence_confidence_score=0.75,
        ),
        SimulationScenario(
            id=SCENARIO_IDS[2], engagement_id=ENG_ID, process_model_id=PM_ID,
            name="Remove Manual Compliance Check",
            simulation_type=SimulationType.CONTROL_REMOVAL,
            description="Replace manual compliance review with automated regulatory screening",
            parameters={"automated_screening_accuracy": 0.99},
            evidence_confidence_score=0.68,
        ),
    ]

    results = [
        SimulationResult(
            scenario_id=SCENARIO_IDS[0], status=SimulationStatus.COMPLETED,
            metrics={
                "cycle_time_reduction_pct": 42, "cost_savings_annual": 1_250_000,
                "throughput_increase_pct": 35, "error_rate_change_pct": -15,
            },
            impact_analysis={
                "affected_roles": ["Loan Officer", "Credit Analyst"],
                "technology_requirements": ["ML credit model", "Decision engine"],
                "risk_level": "medium",
            },
            recommendations=["Start with pilot on standard personal loans", "Maintain human review for commercial loans"],
            execution_time_ms=1247, started_at=NOW - timedelta(hours=5),
            completed_at=NOW - timedelta(hours=5) + timedelta(seconds=1.2),
        ),
        SimulationResult(
            scenario_id=SCENARIO_IDS[1], status=SimulationStatus.COMPLETED,
            metrics={
                "cycle_time_reduction_pct": 68, "cost_savings_annual": 2_100_000,
                "throughput_increase_pct": 55, "customer_satisfaction_increase_pct": 22,
            },
            impact_analysis={
                "affected_roles": ["All lending staff"],
                "technology_requirements": ["STP engine", "API integrations", "Real-time decisioning"],
                "risk_level": "high",
            },
            recommendations=["Phase implementation: simple products first", "Maintain manual fallback for 6 months"],
            execution_time_ms=2103,
            started_at=NOW - timedelta(hours=4), completed_at=NOW - timedelta(hours=4) + timedelta(seconds=2.1),
        ),
        SimulationResult(
            scenario_id=SCENARIO_IDS[2], status=SimulationStatus.COMPLETED,
            metrics={
                "cycle_time_reduction_pct": 18, "cost_savings_annual": 380_000,
                "compliance_risk_increase_pct": 2,
            },
            impact_analysis={
                "affected_roles": ["Compliance Officer"],
                "technology_requirements": ["Regulatory screening API"],
                "risk_level": "high",
                "regulatory_concern": "OCC may require human review for certain loan types",
            },
            recommendations=["Do NOT remove human compliance review for commercial loans", "Implement for retail only with 100% audit trail"],
            execution_time_ms=892,
            started_at=NOW - timedelta(hours=3), completed_at=NOW - timedelta(hours=3) + timedelta(seconds=0.9),
        ),
    ]

    assumptions = [
        FinancialAssumption(
            engagement_id=ENG_ID, assumption_type=FinancialAssumptionType.COST_PER_ROLE,
            name="Loan Officer Fully-Loaded Cost", value=95000.0, unit="USD/year",
            confidence=0.90, confidence_explanation="Based on Acme HR data (2025 comp review)",
            notes="Based on Acme HR data (2025 comp review)",
        ),
        FinancialAssumption(
            engagement_id=ENG_ID, assumption_type=FinancialAssumptionType.TECHNOLOGY_COST,
            name="Credit Decisioning Engine License", value=180000.0, unit="USD/year",
            confidence=0.75, confidence_explanation="Vendor quote from FICO; may negotiate lower",
            notes="Vendor quote from FICO; may negotiate lower",
        ),
        FinancialAssumption(
            engagement_id=ENG_ID, assumption_type=FinancialAssumptionType.VOLUME_FORECAST,
            name="Annual Loan Applications", value=45000.0, unit="applications/year",
            confidence=0.85, confidence_explanation="Based on 3-year trend with 8% YoY growth",
            notes="Based on 3-year trend with 8% YoY growth",
        ),
        FinancialAssumption(
            engagement_id=ENG_ID, assumption_type=FinancialAssumptionType.IMPLEMENTATION_COST,
            name="STP Implementation Program", value=2_500_000.0, unit="USD",
            confidence=0.60, confidence_explanation="Rough estimate; requires detailed scoping",
            notes="Rough estimate; requires detailed scoping",
        ),
    ]

    suggestions = [
        AlternativeSuggestion(
            scenario_id=SCENARIO_IDS[0], engagement_id=ENG_ID,
            suggestion_text="Consider a phased approach: automate identity verification first (quick win), then credit decisioning",
            rationale="Identity verification automation has higher evidence confidence (0.85 vs 0.72) and lower regulatory risk",
            governance_flags={"regulatory_review_required": False, "data_privacy_impact": "low"},
            evidence_gaps={"income_verification": "Single source evidence"},
            disposition=SuggestionDisposition.ACCEPTED,
            disposition_notes="Agreed — identity verification first, credit decisioning in phase 2",
            llm_prompt="Given the evidence confidence scores and regulatory constraints, suggest an alternative sequencing...",
            llm_response="Based on analysis of confidence scores across process elements...",
        ),
    ]

    return {
        "scenarios": scenarios,
        "assumptions": assumptions,
        "results": results,
        "suggestions": suggestions,
    }


def seed_governance() -> list:
    from src.core.models.governance import (
        Control,
        ControlEffectiveness,
        Policy,
        PolicyType,
        Regulation,
    )

    policies = [
        Policy(
            engagement_id=ENG_ID, name="Retail Lending Credit Policy",
            policy_type=PolicyType.ORGANIZATIONAL,
            source_evidence_id=EV_IDS["loan-policy"],
            description="Governs all retail lending credit decisions, risk appetite, and approval authority",
            clauses={"max_ltv": 0.80, "min_credit_score": 620, "dual_approval_threshold": 100000},
        ),
        Policy(
            engagement_id=ENG_ID, name="Anti-Money Laundering (AML) Policy",
            policy_type=PolicyType.REGULATORY,
            description="BSA/AML compliance requirements for customer identification and transaction monitoring",
            clauses={"cdd_required": True, "edd_threshold": 50000, "sar_filing_days": 30},
        ),
        Policy(
            engagement_id=ENG_ID, name="Data Handling and Privacy Policy",
            policy_type=PolicyType.SECURITY,
            description="Controls for handling personally identifiable information in lending operations",
            clauses={"encryption_at_rest": True, "retention_years": 7, "access_review_quarterly": True},
        ),
    ]

    controls = [
        Control(
            engagement_id=ENG_ID, name="Dual Approval for High-Value Loans",
            description="Loans above $100K require approval from both loan officer and senior underwriter",
            effectiveness=ControlEffectiveness.MODERATELY_EFFECTIVE,
            effectiveness_score=0.65,
        ),
        Control(
            engagement_id=ENG_ID, name="Identity Verification (KYC)",
            description="Automated + manual identity verification using LexisNexis and document review",
            effectiveness=ControlEffectiveness.HIGHLY_EFFECTIVE,
            effectiveness_score=0.92,
        ),
        Control(
            engagement_id=ENG_ID, name="Credit Bureau Pull Authorization",
            description="Documented customer consent required before credit bureau inquiry",
            effectiveness=ControlEffectiveness.EFFECTIVE,
            effectiveness_score=0.85,
        ),
        Control(
            engagement_id=ENG_ID, name="Income Documentation Review",
            description="Manual review of income documentation (pay stubs, tax returns, employer verification)",
            effectiveness=ControlEffectiveness.MODERATELY_EFFECTIVE,
            effectiveness_score=0.70,
        ),
    ]

    regulations = [
        Regulation(
            engagement_id=ENG_ID, name="Truth in Lending Act (TILA)",
            framework="Consumer Financial Protection",
            jurisdiction="United States",
            obligations={"disclosure_required": True, "apr_calculation": "required", "right_of_rescission": "3_business_days"},
        ),
        Regulation(
            engagement_id=ENG_ID, name="Equal Credit Opportunity Act (ECOA)",
            framework="Fair Lending",
            jurisdiction="United States",
            obligations={"adverse_action_notice": "required", "prohibited_factors": ["race", "religion", "national_origin", "sex"]},
        ),
        Regulation(
            engagement_id=ENG_ID, name="Bank Secrecy Act / AML",
            framework="Anti-Money Laundering",
            jurisdiction="United States",
            obligations={"cip_required": True, "cdd_required": True, "sar_reporting": "mandatory"},
        ),
    ]

    return [*policies, *controls, *regulations]


def seed_shelf_requests() -> list:
    from src.core.models.engagement import (
        ShelfDataRequest,
        ShelfDataRequestItem,
        ShelfRequestItemPriority,
        ShelfRequestItemStatus,
        ShelfRequestStatus,
    )
    from src.core.models.evidence import EvidenceCategory

    req1 = ShelfDataRequest(
        id=_uid("shelf-req-1"),
        engagement_id=ENG_ID,
        title="Initial Evidence Collection — Loan Origination",
        description="First batch of evidence needed for process discovery phase",
        status=ShelfRequestStatus.IN_PROGRESS,
        due_date=TODAY + timedelta(days=5),
    )

    items1 = [
        ShelfDataRequestItem(
            request_id=req1.id, category=EvidenceCategory.DOCUMENTS,
            item_name="Loan Origination Standard Operating Procedures",
            priority=ShelfRequestItemPriority.HIGH,
            status=ShelfRequestItemStatus.RECEIVED,
            matched_evidence_id=EV_IDS["process-doc"],
        ),
        ShelfDataRequestItem(
            request_id=req1.id, category=EvidenceCategory.STRUCTURED_DATA,
            item_name="6-Month Event Log Export (Core Banking)",
            priority=ShelfRequestItemPriority.HIGH,
            status=ShelfRequestItemStatus.RECEIVED,
            matched_evidence_id=EV_IDS["data-extract"],
        ),
        ShelfDataRequestItem(
            request_id=req1.id, category=EvidenceCategory.CONTROLS_EVIDENCE,
            item_name="Internal Audit Report — Lending Controls",
            priority=ShelfRequestItemPriority.MEDIUM,
            status=ShelfRequestItemStatus.RECEIVED,
            matched_evidence_id=EV_IDS["audit-controls"],
        ),
        ShelfDataRequestItem(
            request_id=req1.id, category=EvidenceCategory.REGULATORY_POLICY,
            item_name="OCC Examination Report (latest)",
            priority=ShelfRequestItemPriority.HIGH,
            status=ShelfRequestItemStatus.RECEIVED,
            matched_evidence_id=EV_IDS["compliance-report"],
        ),
        ShelfDataRequestItem(
            request_id=req1.id, category=EvidenceCategory.DOCUMENTS,
            item_name="Exception Handling Procedures (Declined Applications)",
            priority=ShelfRequestItemPriority.HIGH,
            status=ShelfRequestItemStatus.PENDING,
            description="Critical gap — no evidence for exception/decline processing path",
        ),
        ShelfDataRequestItem(
            request_id=req1.id, category=EvidenceCategory.BPM_PROCESS_MODELS,
            item_name="Customer Onboarding Sub-Process Model",
            priority=ShelfRequestItemPriority.MEDIUM,
            status=ShelfRequestItemStatus.PENDING,
        ),
    ]

    return [req1, *items1]


def seed_patterns() -> list:
    from src.core.models.pattern import PatternCategory, PatternLibraryEntry

    return [
        PatternLibraryEntry(
            source_engagement_id=ENG_ID,
            category=PatternCategory.PROCESS_OPTIMIZATION,
            title="Automated Pre-Screening for Lending",
            description="Implement automated pre-screening using credit score + income ratio to route 60-70% of applications through fast track",
            industry="Financial Services",
            tags=["lending", "automation", "pre-screening", "STP"],
            usage_count=3, effectiveness_score=0.85,
        ),
        PatternLibraryEntry(
            source_engagement_id=ENG_ID,
            category=PatternCategory.CONTROL_IMPROVEMENT,
            title="Risk-Based Dual Approval Thresholds",
            description="Dynamic dual-approval thresholds based on risk score rather than fixed dollar amount",
            industry="Financial Services",
            tags=["controls", "risk-based", "approval", "lending"],
            usage_count=1, effectiveness_score=0.72,
        ),
        PatternLibraryEntry(
            category=PatternCategory.TECHNOLOGY_ENABLEMENT,
            title="Real-Time Process Mining Dashboard",
            description="Continuously monitors process execution using event log streaming with automated deviation detection and SLA alerting",
            industry="Financial Services",
            tags=["monitoring", "process-mining", "real-time", "dashboards"],
            usage_count=5, effectiveness_score=0.90,
        ),
    ]


# ---------------------------------------------------------------------------
# Neo4j knowledge graph seeding
# ---------------------------------------------------------------------------


def seed_neo4j() -> None:
    """Populate Neo4j with process graph nodes and relationships."""
    try:
        from neo4j import GraphDatabase
    except ImportError:
        logger.warning("neo4j driver not installed; skipping graph seeding")
        return

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    eid = str(ENG_ID)

    with driver.session() as session:
        # Process node
        session.run(
            "MERGE (p:Process {id: $id}) SET p.name = $name, p.engagement_id = $eid",
            id="process-loan-origination", name="Loan Origination", eid=eid,
        )

        # Activity nodes
        activities = [
            ("act-receive-app", "Receive Application"),
            ("act-verify-id", "Verify Identity"),
            ("act-credit-check", "Credit Check"),
            ("act-income-verify", "Income Verification"),
            ("act-risk-assess", "Risk Assessment"),
            ("act-underwrite", "Underwriting Decision"),
            ("act-gen-offer", "Generate Offer"),
            ("act-notify", "Notify Applicant"),
        ]
        for aid, aname in activities:
            session.run(
                "MERGE (a:Activity {id: $id}) SET a.name = $name, a.engagement_id = $eid, a.process_id = $pid",
                id=aid, name=aname, eid=eid, pid="process-loan-origination",
            )

        # FOLLOWED_BY chain
        for i in range(len(activities) - 1):
            session.run(
                """MATCH (a:Activity {id: $from_id}), (b:Activity {id: $to_id})
                   MERGE (a)-[:FOLLOWED_BY]->(b)""",
                from_id=activities[i][0], to_id=activities[i + 1][0],
            )

        # Role nodes
        roles = [
            ("role-loan-officer", "Loan Officer"),
            ("role-credit-analyst", "Credit Analyst"),
            ("role-underwriter", "Senior Underwriter"),
            ("role-compliance", "Compliance Officer"),
        ]
        for rid, rname in roles:
            session.run(
                "MERGE (r:Role {id: $id}) SET r.name = $name, r.engagement_id = $eid",
                id=rid, name=rname, eid=eid,
            )

        # HAS_ROLE
        role_assignments = [
            ("act-receive-app", "role-loan-officer"),
            ("act-verify-id", "role-loan-officer"),
            ("act-credit-check", "role-credit-analyst"),
            ("act-income-verify", "role-loan-officer"),
            ("act-risk-assess", "role-underwriter"),
            ("act-underwrite", "role-underwriter"),
            ("act-gen-offer", "role-loan-officer"),
            ("act-notify", "role-loan-officer"),
        ]
        for aid, rid in role_assignments:
            session.run(
                """MATCH (a:Activity {id: $aid}), (r:Role {id: $rid})
                   MERGE (a)-[:HAS_ROLE]->(r)""",
                aid=aid, rid=rid,
            )

        # System nodes
        systems = [
            ("sys-t24", "Temenos T24 Core Banking"),
            ("sys-equifax", "Equifax Credit Bureau API"),
            ("sys-lexisnexis", "LexisNexis Identity Verification"),
            ("sys-outlook", "Microsoft Outlook"),
        ]
        for sid, sname in systems:
            session.run(
                "MERGE (s:System {id: $id}) SET s.name = $name, s.engagement_id = $eid",
                id=sid, name=sname, eid=eid,
            )

        # USES_SYSTEM
        system_usage = [
            ("act-receive-app", "sys-t24"),
            ("act-verify-id", "sys-lexisnexis"),
            ("act-credit-check", "sys-equifax"),
            ("act-income-verify", "sys-t24"),
            ("act-underwrite", "sys-t24"),
            ("act-gen-offer", "sys-t24"),
            ("act-notify", "sys-outlook"),
        ]
        for aid, sid in system_usage:
            session.run(
                """MATCH (a:Activity {id: $aid}), (s:System {id: $sid})
                   MERGE (a)-[:USES_SYSTEM]->(s)""",
                aid=aid, sid=sid,
            )

        # Evidence nodes
        ev_nodes = [
            ("ev-loan-policy", "Retail Lending Policy v3.2", "documents"),
            ("ev-event-log", "Core Banking Event Log", "structured_data"),
            ("ev-signavio", "SAP Signavio Process Mining Export", "saas_exports"),
            ("ev-interview-ops", "Interview: Operations Manager", "audio"),
            ("ev-interview-cro", "Interview: Chief Risk Officer", "audio"),
            ("ev-task-mining", "Task Mining Observations (Week 1)", "km4work"),
        ]
        for eid_node, ename, ecat in ev_nodes:
            session.run(
                "MERGE (e:Evidence {id: $id}) SET e.name = $name, e.engagement_id = $eid, e.category = $cat",
                id=eid_node, name=ename, eid=eid, cat=ecat,
            )

        # EVIDENCED_BY links
        evidence_links = [
            ("act-receive-app", "ev-event-log"),
            ("act-receive-app", "ev-loan-policy"),
            ("act-receive-app", "ev-task-mining"),
            ("act-verify-id", "ev-event-log"),
            ("act-verify-id", "ev-interview-ops"),
            ("act-credit-check", "ev-signavio"),
            ("act-credit-check", "ev-event-log"),
            ("act-credit-check", "ev-task-mining"),
            ("act-income-verify", "ev-interview-ops"),
            ("act-income-verify", "ev-loan-policy"),
            ("act-risk-assess", "ev-loan-policy"),
            ("act-risk-assess", "ev-interview-cro"),
            ("act-underwrite", "ev-event-log"),
            ("act-underwrite", "ev-loan-policy"),
            ("act-underwrite", "ev-interview-cro"),
            ("act-gen-offer", "ev-event-log"),
            ("act-gen-offer", "ev-task-mining"),
            ("act-notify", "ev-interview-ops"),
        ]
        for aid, evid in evidence_links:
            session.run(
                """MATCH (a:Activity {id: $aid}), (e:Evidence {id: $evid})
                   MERGE (a)-[:EVIDENCED_BY]->(e)""",
                aid=aid, evid=evid,
            )

        # Application and UserAction nodes (task mining layer)
        tm_apps = [
            ("app-t24", "Temenos T24", "enterprise"),
            ("app-excel", "Microsoft Excel", "spreadsheet"),
            ("app-chrome", "Google Chrome", "browser"),
            ("app-outlook", "Microsoft Outlook", "email"),
        ]
        for app_id, app_name, app_cat in tm_apps:
            session.run(
                "MERGE (a:Application {id: $id}) SET a.name = $name, a.engagement_id = $eid, a.category = $cat",
                id=app_id, name=app_name, eid=eid, cat=app_cat,
            )

        # UserAction nodes
        user_actions = [
            ("ua-data-entry-t24", "Data Entry in T24", "data_entry", "app-t24"),
            ("ua-credit-lookup", "Credit Bureau Lookup", "navigation", "app-chrome"),
            ("ua-review-policy", "Policy Document Review", "review", "app-chrome"),
            ("ua-email-docs", "Email: Request Documents", "communication", "app-outlook"),
            ("ua-calc-score", "Credit Score Calculation", "data_entry", "app-excel"),
        ]
        for ua_id, ua_name, ua_cat, app_id in user_actions:
            session.run(
                """MERGE (ua:UserAction {id: $id})
                   SET ua.name = $name, ua.engagement_id = $eid, ua.category = $cat
                   WITH ua
                   MATCH (app:Application {id: $app_id})
                   MERGE (ua)-[:PERFORMED_IN]->(app)""",
                id=ua_id, name=ua_name, eid=eid, cat=ua_cat, app_id=app_id,
            )

        # PRECEDED_BY chain for user actions
        ua_chain = ["ua-data-entry-t24", "ua-credit-lookup", "ua-calc-score", "ua-review-policy", "ua-email-docs"]
        for i in range(1, len(ua_chain)):
            session.run(
                """MATCH (a:UserAction {id: $a_id}), (b:UserAction {id: $b_id})
                   MERGE (a)-[:PRECEDED_BY]->(b)""",
                a_id=ua_chain[i], b_id=ua_chain[i - 1],
            )

        # SUPPORTS links (UserAction -> Activity)
        supports = [
            ("ua-data-entry-t24", "act-receive-app"),
            ("ua-credit-lookup", "act-credit-check"),
            ("ua-calc-score", "act-credit-check"),
            ("ua-review-policy", "act-risk-assess"),
            ("ua-email-docs", "act-income-verify"),
        ]
        for ua_id, act_id in supports:
            session.run(
                """MATCH (ua:UserAction {id: $ua_id}), (a:Activity {id: $act_id})
                   MERGE (ua)-[:SUPPORTS]->(a)""",
                ua_id=ua_id, act_id=act_id,
            )

        # MAPS_TO links (Application -> System)
        maps_to = [
            ("app-t24", "sys-t24"),
            ("app-outlook", "sys-outlook"),
        ]
        for app_id, sys_id in maps_to:
            session.run(
                """MATCH (app:Application {id: $app_id}), (s:System {id: $sys_id})
                   MERGE (app)-[:MAPS_TO]->(s)""",
                app_id=app_id, sys_id=sys_id,
            )

    driver.close()
    logger.info("Neo4j knowledge graph seeded: 30+ nodes, 50+ relationships")


# ---------------------------------------------------------------------------
# WGI Features (switching sequences, VCEs, correlation)
# ---------------------------------------------------------------------------


def seed_wgi_features() -> dict:
    """Seed WGI-specific features: switching sequences, VCEs, correlation."""
    from src.core.models.taskmining import (
        ScreenStateClass,
        SwitchingTrace,
        TransitionMatrix,
        VCETriggerReason,
        VisualContextEvent,
    )
    from src.core.models.correlation import CaseLinkEdge

    traces = [
        SwitchingTrace(
            id=SWITCHING_TRACE_IDS[0], engagement_id=ENG_ID,
            agent_id=AGENT_IDS[0], session_id=SESSION_IDS[0],
            trace_sequence=["Temenos T24", "Microsoft Excel", "Temenos T24"],
            dwell_durations=[45000, 12000, 38000],
            friction_score=0.72, is_ping_pong=True, ping_pong_count=1, app_count=2,
        ),
        SwitchingTrace(
            id=SWITCHING_TRACE_IDS[1], engagement_id=ENG_ID,
            agent_id=AGENT_IDS[0], session_id=SESSION_IDS[1],
            trace_sequence=["Google Chrome", "Microsoft Outlook", "Google Chrome", "Temenos T24"],
            dwell_durations=[30000, 8000, 15000, 52000],
            friction_score=0.45, is_ping_pong=True, ping_pong_count=1, app_count=3,
        ),
        SwitchingTrace(
            id=SWITCHING_TRACE_IDS[2], engagement_id=ENG_ID,
            agent_id=AGENT_IDS[1], session_id=SESSION_IDS[2],
            trace_sequence=["Temenos T24", "Microsoft Excel"],
            dwell_durations=[120000, 25000],
            friction_score=0.15, is_ping_pong=False, ping_pong_count=0, app_count=2,
        ),
    ]

    matrix = TransitionMatrix(
        id=TRANSITION_MATRIX_ID, engagement_id=ENG_ID,
        role_id="role-loan-officer", period_start=TODAY - timedelta(days=7),
        period_end=TODAY,
        matrix_data={
            "Temenos T24": {"Microsoft Excel": 45, "Google Chrome": 30, "Microsoft Outlook": 12},
            "Microsoft Excel": {"Temenos T24": 42, "Google Chrome": 8},
            "Google Chrome": {"Temenos T24": 28, "Microsoft Outlook": 5},
            "Microsoft Outlook": {"Google Chrome": 6, "Temenos T24": 10},
        },
        total_transitions=186, unique_apps=4,
        top_transitions=[
            {"from": "Temenos T24", "to": "Microsoft Excel", "count": 45},
            {"from": "Microsoft Excel", "to": "Temenos T24", "count": 42},
            {"from": "Temenos T24", "to": "Google Chrome", "count": 30},
        ],
    )

    vce_events = [
        VisualContextEvent(
            id=VCE_IDS[0], engagement_id=ENG_ID,
            agent_id=AGENT_IDS[0], session_id=SESSION_IDS[0],
            screen_state_class=ScreenStateClass.DATA_ENTRY,
            system_guess="Temenos T24", module_guess="Loan Application Entry",
            confidence=0.85, trigger_reason=VCETriggerReason.HIGH_DWELL,
            application_name="Temenos T24", window_title_redacted="T24 - New Application [PII_REDACTED]",
            dwell_ms=45000, interaction_intensity=0.08,
        ),
        VisualContextEvent(
            id=VCE_IDS[1], engagement_id=ENG_ID,
            agent_id=AGENT_IDS[0], session_id=SESSION_IDS[0],
            screen_state_class=ScreenStateClass.SEARCH,
            system_guess="Equifax", module_guess="Credit Bureau Lookup",
            confidence=0.72, trigger_reason=VCETriggerReason.LOW_CONFIDENCE,
            application_name="Google Chrome", window_title_redacted="Credit Report - [PII_REDACTED]",
            dwell_ms=18000, interaction_intensity=0.25,
        ),
        VisualContextEvent(
            id=VCE_IDS[2], engagement_id=ENG_ID,
            agent_id=AGENT_IDS[0], session_id=SESSION_IDS[1],
            screen_state_class=ScreenStateClass.ERROR,
            system_guess="Temenos T24", module_guess="Validation Error",
            confidence=0.92, trigger_reason=VCETriggerReason.RECURRING_EXCEPTION,
            application_name="Temenos T24", window_title_redacted="T24 - Error: Missing Field",
            dwell_ms=5000, interaction_intensity=0.02,
        ),
        VisualContextEvent(
            id=VCE_IDS[3], engagement_id=ENG_ID,
            agent_id=AGENT_IDS[1], session_id=SESSION_IDS[2],
            screen_state_class=ScreenStateClass.REVIEW,
            system_guess="Microsoft Excel", module_guess="Credit Score Calculation",
            confidence=0.68, trigger_reason=VCETriggerReason.HIGH_DWELL,
            application_name="Microsoft Excel", window_title_redacted="Loan_Score_Calculator.xlsx",
            dwell_ms=62000, interaction_intensity=0.12,
        ),
        VisualContextEvent(
            id=VCE_IDS[4], engagement_id=ENG_ID,
            agent_id=AGENT_IDS[1], session_id=SESSION_IDS[3],
            screen_state_class=ScreenStateClass.WAITING_LATENCY,
            system_guess="Temenos T24", module_guess="System Loading",
            confidence=0.95, trigger_reason=VCETriggerReason.HIGH_DWELL,
            application_name="Temenos T24", window_title_redacted="T24 - Processing...",
            dwell_ms=32000, interaction_intensity=0.0,
        ),
    ]

    case_links = [
        CaseLinkEdge(
            id=CASE_LINK_IDS[0], engagement_id=ENG_ID,
            endpoint_event_id=str(SESSION_IDS[0]), case_id="LOAN-2025-001",
            method="deterministic", confidence=0.98,
            explainability={"method": "window_title_regex", "pattern": r"LOAN-\d{4}-\d{3}", "match": "LOAN-2025-001"},
        ),
        CaseLinkEdge(
            id=CASE_LINK_IDS[1], engagement_id=ENG_ID,
            endpoint_event_id=str(SESSION_IDS[1]), case_id="LOAN-2025-002",
            method="deterministic", confidence=0.95,
            explainability={"method": "window_title_regex", "pattern": r"LOAN-\d{4}-\d{3}", "match": "LOAN-2025-002"},
        ),
        CaseLinkEdge(
            id=CASE_LINK_IDS[2], engagement_id=ENG_ID,
            endpoint_event_id=str(SESSION_IDS[2]), case_id="LOAN-2025-001",
            method="assisted", confidence=0.72,
            explainability={
                "method": "probabilistic", "features": {
                    "time_proximity": 0.85, "role_match": 0.90, "system_overlap": 0.60,
                },
            },
        ),
        CaseLinkEdge(
            id=CASE_LINK_IDS[3], engagement_id=ENG_ID,
            endpoint_event_id=str(SESSION_IDS[3]), case_id="LOAN-2025-003",
            method="role_association", confidence=0.45,
            explainability={"method": "role_fallback", "role": "Loan Officer", "period": "2025-02-20"},
        ),
    ]

    return {
        "traces": traces,
        "matrix": [matrix],
        "vce_events": vce_events,
        "case_links": case_links,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main(reset: bool = False) -> None:
    engine = create_async_engine(DB_URL, echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        if reset:
            await reset_data(session)

        # Check if already seeded
        result = await session.execute(
            text("SELECT id FROM engagements WHERE id = :id"), {"id": str(ENG_ID)}
        )
        if result.first():
            logger.info("Demo engagement already exists. Use --reset to reseed.")
            await engine.dispose()
            return

        logger.info("Seeding demo data for 'Acme Corp Loan Origination'...")

        # Temporarily disable FK trigger checks on all tables so we can insert in any order
        result = await session.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ))
        tables = [row[0] for row in result.fetchall()]
        for t in tables:
            await session.execute(text(f'ALTER TABLE "{t}" DISABLE TRIGGER ALL'))

        mon = seed_monitoring()
        sim = seed_simulations()
        tm = seed_task_mining()
        wgi = seed_wgi_features()

        all_objects = [
            *seed_users(),
            *seed_engagement(),
            *seed_evidence(),
            *seed_process_model(),
            *seed_tom(),
            *mon["baselines"], *mon["metrics"], *mon["jobs"],
            *mon["deviations"], *mon["alerts"], *mon["readings"],
            *sim["scenarios"], *sim["assumptions"], *sim["results"], *sim["suggestions"],
            *seed_governance(),
            *seed_shelf_requests(),
            *seed_patterns(),
            *tm["agents"], *tm["sessions"], *tm["events"], *tm["actions"], *tm["quarantine"],
            *wgi["traces"], *wgi["matrix"], *wgi["vce_events"], *wgi["case_links"],
        ]

        session.add_all(all_objects)
        await session.commit()

        # Re-enable FK trigger checks on all tables
        for t in tables:
            await session.execute(text(f'ALTER TABLE "{t}" ENABLE TRIGGER ALL'))
        await session.commit()
        total = len(all_objects)
        logger.info("PostgreSQL seeded: %d objects", total)

    await engine.dispose()

    # Neo4j
    seed_neo4j()

    logger.info("Demo data seeding complete.")
    logger.info("")
    logger.info("  Engagement: Acme Corp — Loan Origination Transformation")
    logger.info("  Engagement ID: %s", ENG_ID)
    logger.info("")
    logger.info("  Demo users:")
    logger.info("    admin@acme-demo.com   (Platform Admin)")
    logger.info("    lead@acme-demo.com    (Engagement Lead)")
    logger.info("    analyst@acme-demo.com (Process Analyst)")
    logger.info("    viewer@acme-demo.com  (Client Viewer)")
    logger.info("")
    logger.info("  Data seeded:")
    logger.info("    15 evidence items across 10 categories")
    logger.info("    1 process model with 11 elements, 2 contradictions, 4 gaps")
    logger.info("    1 TOM with 6 gap analysis results")
    logger.info("    3 task mining agents, 4 sessions, ~200 events, ~60 actions")
    logger.info("    2 monitoring jobs, 4 deviations, 4 alerts")
    logger.info("    3 simulation scenarios with results")
    logger.info("    3 policies, 4 controls, 3 regulations")
    logger.info("    1 shelf data request with 6 items (4 received, 2 pending)")
    logger.info("    3 cross-engagement patterns")
    logger.info("    3 data catalog entries (bronze/silver/gold)")
    logger.info("    30+ Neo4j nodes, 50+ relationships")
    logger.info("    3 switching traces, 1 transition matrix")
    logger.info("    5 visual context events across 4 screen states")
    logger.info("    4 case link edges (2 deterministic, 1 assisted, 1 role)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed KMFlow demo data")
    parser.add_argument("--reset", action="store_true", help="Delete existing demo data before seeding")
    args = parser.parse_args()
    asyncio.run(main(reset=args.reset))
