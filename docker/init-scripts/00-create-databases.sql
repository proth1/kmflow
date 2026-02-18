-- KMFlow Platform - PostgreSQL Multi-Database Initialization
-- Creates isolated databases: kmflow (app), camunda (BPMN engine)
-- Executed automatically on first container startup

-- Create users with dedicated passwords
CREATE USER kmflow WITH PASSWORD 'kmflow_dev_password';
CREATE USER camunda WITH PASSWORD 'camunda_dev';

-- =============================================================================
-- KMFLOW DATABASE (Application + Knowledge Base)
-- =============================================================================
CREATE DATABASE kmflow OWNER kmflow;

\c kmflow

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- Grant permissions
GRANT ALL ON SCHEMA public TO kmflow;

-- =============================================================================
-- CAMUNDA DATABASE (CIB7 BPMN Engine)
-- =============================================================================
\c postgres

CREATE DATABASE camunda OWNER camunda;

\c camunda

-- Grant permissions
GRANT ALL ON SCHEMA public TO camunda;

-- =============================================================================
-- SECURITY: Revoke cross-database access
-- =============================================================================
\c postgres

REVOKE ALL ON DATABASE kmflow FROM camunda, PUBLIC;
REVOKE ALL ON DATABASE camunda FROM kmflow, PUBLIC;

GRANT CONNECT ON DATABASE kmflow TO kmflow;
GRANT CONNECT ON DATABASE camunda TO camunda;

\echo 'Database initialization complete: kmflow and camunda databases created'
