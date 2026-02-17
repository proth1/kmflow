-- PostgreSQL initialization script for KMFlow.
-- Runs on first container start to enable required extensions.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";
