"""Bootstrap the database by creating all tables from SQLAlchemy metadata.

Bypasses Alembic migrations which have a known asyncpg enum compatibility issue.
Uses psycopg2 (sync) to avoid asyncpg type cache issues.

Patches SQLAlchemy Enum to use .value (lowercase) for StrEnum types, matching
what Alembic migrations expect in PostgreSQL.

Usage:
    python -m scripts.bootstrap_db
    python -m scripts.bootstrap_db --drop  # drop all tables first
"""

from __future__ import annotations

import argparse
import enum
import logging

import sqlalchemy as sa
from sqlalchemy import create_engine, text

# Patch Enum before importing models: make StrEnum use .value (lowercase)
_original_enum_init = sa.Enum.__init__


def _patched_enum_init(self, *enums, **kw):
    """Ensure Python StrEnum types use .value (lowercase) not .name (UPPERCASE)."""
    if (
        len(enums) == 1
        and isinstance(enums[0], type)
        and issubclass(enums[0], enum.StrEnum)
        and "values_callable" not in kw
    ):
        kw["values_callable"] = lambda e: [x.value for x in e]
    _original_enum_init(self, *enums, **kw)


sa.Enum.__init__ = _patched_enum_init

from src.core.database import Base  # noqa: E402

# Import ALL models so they register with Base.metadata
from src.core.models import (  # noqa: E402, F401
    Annotation,
    AuditLog,
    Benchmark,
    BestPractice,
    ConformanceResult,
    Contradiction,
    Control,
    CopilotMessage,
    Engagement,
    EngagementMember,
    EvidenceFragment,
    EvidenceGap,
    EvidenceItem,
    GapAnalysisResult,
    IntegrationConnection,
    MCPAPIKey,
    MetricReading,
    MonitoringAlert,
    MonitoringJob,
    PatternAccessRule,
    PatternLibraryEntry,
    Policy,
    ProcessBaseline,
    ProcessDeviation,
    ProcessElement,
    ProcessModel,
    ReferenceProcessModel,
    Regulation,
    ShelfDataRequest,
    ShelfDataRequestItem,
    SimulationResult,
    SimulationScenario,
    SuccessMetric,
    TargetOperatingModel,
    User,
)
# Task mining models
from src.core.models.taskmining import (  # noqa: E402, F401
    PIIQuarantine,
    TaskMiningAction,
    TaskMiningAgent,
    TaskMiningEvent,
    TaskMiningSession,
)
# Simulation extras
from src.core.models.simulation import (  # noqa: E402, F401
    AlternativeSuggestion,
    EpistemicAction,
    FinancialAssumption,
    ScenarioModification,
)
# Consent records
from src.core.models.auth import UserConsent  # noqa: E402, F401
# Evidence extras
from src.core.models.evidence import DataCatalogEntry, EvidenceLineage  # noqa: E402, F401
# Audit extras
from src.core.models.audit import HttpAuditEvent  # noqa: E402, F401

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

# Use psycopg2 (sync) for DDL operations
DB_URL = "postgresql+psycopg2://kmflow:kmflow_dev_password@localhost:5433/kmflow"


def main(drop: bool = False) -> None:
    engine = create_engine(DB_URL, echo=False)

    with engine.begin() as conn:
        if drop:
            logger.info("Dropping all tables and types...")
            Base.metadata.drop_all(conn)
            # Also drop orphan enum types
            conn.execute(text(
                "DO $$ DECLARE r RECORD; BEGIN "
                "FOR r IN (SELECT typname FROM pg_type WHERE typtype='e') LOOP "
                "EXECUTE 'DROP TYPE IF EXISTS ' || r.typname || ' CASCADE'; "
                "END LOOP; END $$;"
            ))

        logger.info("Creating all tables from SQLAlchemy metadata...")
        Base.metadata.create_all(conn)

        # Stamp alembic_version to latest so future alembic commands work
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"
        ))
        conn.execute(text("DELETE FROM alembic_version"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('028')"))

    engine.dispose()

    table_count = len(Base.metadata.tables)
    logger.info("Database bootstrapped: %d tables created", table_count)
    logger.info("Alembic version stamped to 028 (latest)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bootstrap KMFlow database")
    parser.add_argument("--drop", action="store_true", help="Drop all tables first")
    args = parser.parse_args()
    main(drop=args.drop)
