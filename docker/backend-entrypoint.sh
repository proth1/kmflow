#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head

# Seed demo data if AUTH_DEV_MODE is enabled (idempotent — skips if already seeded)
if [ "${AUTH_DEV_MODE}" = "true" ] || [ "${AUTH_DEV_MODE}" = "True" ]; then
    echo "Dev mode: seeding demo data..."
    # Use postgres superuser for seeding (needs session_replication_role for FK bypass)
    export SEED_DB_URL="postgresql+asyncpg://postgres:${POSTGRES_SUPERUSER_PASSWORD:-postgres_dev}@${POSTGRES_HOST:-postgres}:${POSTGRES_PORT:-5432}/${POSTGRES_DB:-kmflow}"
    export SEED_NEO4J_URI="${NEO4J_URI:-bolt://neo4j:7687}"
    export SEED_NEO4J_USER="${NEO4J_USER:-neo4j}"
    export SEED_NEO4J_PASSWORD="${NEO4J_PASSWORD:-neo4j_dev_password}"
    python -m scripts.seed_demo || echo "WARNING: seed_demo failed (non-fatal)"
fi

echo "Starting application..."
exec uvicorn src.api.main:app --host 0.0.0.0 --port 8000
