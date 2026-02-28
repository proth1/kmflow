"""E2E test seed wrapper — delegates to seed_demo.py.

Thin wrapper that re-uses the existing demo seeding infrastructure
for E2E test data. Supports environment variable overrides for
database connection and writes a JSON file with all deterministic
UUIDs for the Playwright test fixtures.

Usage:
    python -m scripts.seed_e2e          # seed (idempotent)
    python -m scripts.seed_e2e --reset  # wipe and reseed
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

# Allow env-var overrides for CI / Docker-in-Docker setups
_DB_URL_OVERRIDE = os.environ.get("E2E_DB_URL")
_NEO4J_URI_OVERRIDE = os.environ.get("E2E_NEO4J_URI")
_NEO4J_USER_OVERRIDE = os.environ.get("E2E_NEO4J_USER")
_NEO4J_PASSWORD_OVERRIDE = os.environ.get("E2E_NEO4J_PASSWORD")


def _write_seed_ids() -> None:
    """Write deterministic UUIDs to a JSON file for Playwright fixtures."""
    from scripts.seed_demo import (
        AGENT_IDS,
        BASELINE_ID,
        ENG_ID,
        EV_IDS,
        METRIC_IDS,
        MON_JOB_IDS,
        PM_ID,
        SCENARIO_IDS,
        SESSION_IDS,
        TOM_ID,
        USER_ADMIN_ID,
        USER_ANALYST_ID,
        USER_CLIENT_ID,
        USER_LEAD_ID,
    )

    ids = {
        "engagement_id": str(ENG_ID),
        "users": {
            "admin": {"id": str(USER_ADMIN_ID), "email": "admin@acme-demo.com"},
            "lead": {"id": str(USER_LEAD_ID), "email": "lead@acme-demo.com"},
            "analyst": {"id": str(USER_ANALYST_ID), "email": "analyst@acme-demo.com"},
            "viewer": {"id": str(USER_CLIENT_ID), "email": "viewer@acme-demo.com"},
        },
        "evidence_ids": {k: str(v) for k, v in EV_IDS.items()},
        "tom_id": str(TOM_ID),
        "process_model_id": str(PM_ID),
        "baseline_id": str(BASELINE_ID),
        "monitoring_job_ids": [str(j) for j in MON_JOB_IDS],
        "metric_ids": [str(m) for m in METRIC_IDS],
        "scenario_ids": [str(s) for s in SCENARIO_IDS],
        "agent_ids": [str(a) for a in AGENT_IDS],
        "session_ids": [str(s) for s in SESSION_IDS],
    }

    out_path = Path(__file__).resolve().parent.parent / "frontend" / "e2e" / "fixtures"
    out_path.mkdir(parents=True, exist_ok=True)
    json_file = out_path / "seed-ids.json"
    json_file.write_text(json.dumps(ids, indent=2) + "\n")
    logger.info("Seed IDs written to %s", json_file)


async def main(reset: bool = False) -> None:
    import scripts.seed_demo as seed_mod

    # Apply env-var overrides
    if _DB_URL_OVERRIDE:
        seed_mod.DB_URL = _DB_URL_OVERRIDE
        logger.info("Using E2E_DB_URL: %s", _DB_URL_OVERRIDE)
    if _NEO4J_URI_OVERRIDE:
        seed_mod.NEO4J_URI = _NEO4J_URI_OVERRIDE
        logger.info("Using E2E_NEO4J_URI: %s", _NEO4J_URI_OVERRIDE)
    if _NEO4J_USER_OVERRIDE:
        seed_mod.NEO4J_USER = _NEO4J_USER_OVERRIDE
    if _NEO4J_PASSWORD_OVERRIDE:
        seed_mod.NEO4J_PASSWORD = _NEO4J_PASSWORD_OVERRIDE

    logger.info("Running E2E seed (reset=%s)...", reset)
    await seed_mod.main(reset=reset)

    _write_seed_ids()
    logger.info("E2E seed complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed KMFlow E2E test data")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing demo data before seeding",
    )
    args = parser.parse_args()
    asyncio.run(main(reset=args.reset))
