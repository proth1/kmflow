#!/bin/bash
# KMFlow Platform - PostgreSQL Multi-Database Initialization
# Creates isolated databases: kmflow (app), camunda (BPMN engine)
# Executed automatically on first container startup
#
# Uses environment variables for passwords instead of hardcoded values.
# Falls back to dev defaults for local development only.

set -e

KMFLOW_PASSWORD="${KMFLOW_DB_PASSWORD:-kmflow_dev_password}"
CAMUNDA_PASSWORD="${CAMUNDA_DB_PASSWORD:-camunda_dev}"

# Create users with passwords from environment
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Create users with dedicated passwords
    CREATE USER kmflow WITH PASSWORD '${KMFLOW_PASSWORD}';
    CREATE USER camunda WITH PASSWORD '${CAMUNDA_PASSWORD}';

    -- =========================================================================
    -- KMFLOW DATABASE (Application + Knowledge Base)
    -- =========================================================================
    CREATE DATABASE kmflow OWNER kmflow;

    -- =========================================================================
    -- CAMUNDA DATABASE (CIB7 BPMN Engine)
    -- =========================================================================
    CREATE DATABASE camunda OWNER camunda;

    -- =========================================================================
    -- SECURITY: Revoke cross-database access
    -- =========================================================================
    REVOKE ALL ON DATABASE kmflow FROM camunda, PUBLIC;
    REVOKE ALL ON DATABASE camunda FROM kmflow, PUBLIC;

    GRANT CONNECT ON DATABASE kmflow TO kmflow;
    GRANT CONNECT ON DATABASE camunda TO camunda;
EOSQL

# Enable extensions on kmflow database
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "kmflow" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
    CREATE EXTENSION IF NOT EXISTS vector;
    GRANT ALL ON SCHEMA public TO kmflow;
EOSQL

# Grant permissions on camunda database
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "camunda" <<-EOSQL
    GRANT ALL ON SCHEMA public TO camunda;
EOSQL

echo 'Database initialization complete: kmflow and camunda databases created'
