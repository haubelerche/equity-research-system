-- Migration: 004_schema_versioning.sql
-- Purpose: Add migration version tracking table.
-- Idempotent: uses IF NOT EXISTS / ON CONFLICT DO NOTHING.

BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     VARCHAR(80)  NOT NULL PRIMARY KEY,
    applied_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    description TEXT
);

-- Seed all migrations that were already applied to this database
-- before versioning was introduced (migrations 001-003), and record this migration itself.
INSERT INTO schema_migrations (version, description) VALUES
    ('001_initial_schema',       'Core fact/price/company/source tables')
  , ('002_backend_runtime',      'research_runs, run_steps, run_artifacts, approvals, budget, audit')
  , ('003_lineage_enhancements', 'Add run_id and embedding_version to fact/source/catalyst tables')
  , ('004_schema_versioning',    'Add schema_migrations versioning table, seed migrations 001-003')
ON CONFLICT (version) DO NOTHING;

COMMIT;
