-- Migration 026: rename rebuilt warehouse schemas to canonical production names.

ALTER SCHEMA v2_ref RENAME TO ref;
ALTER SCHEMA v2_ingest RENAME TO ingest;
ALTER SCHEMA v2_fact RENAME TO fact;
ALTER SCHEMA v2_research RENAME TO research;
ALTER SCHEMA v2_valuation RENAME TO valuation;
ALTER SCHEMA v2_report RENAME TO report;
ALTER SCHEMA v2_audit RENAME TO audit;

ALTER TABLE research.runs
    ADD COLUMN IF NOT EXISTS org_id VARCHAR(64);

ALTER TABLE research.run_artifacts
    ADD COLUMN IF NOT EXISTS section_key VARCHAR(120),
    ADD COLUMN IF NOT EXISTS payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS evidence_refs_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS confidence NUMERIC(5,4),
    ADD COLUMN IF NOT EXISTS created_by_agent VARCHAR(128);

CREATE TABLE IF NOT EXISTS research.run_steps (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL REFERENCES research.runs(run_id) ON DELETE CASCADE,
    step_name VARCHAR(100) NOT NULL,
    agent_name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,
    policy_reason TEXT,
    input_hash TEXT,
    output_hash TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    duration_ms BIGINT
);

CREATE TABLE IF NOT EXISTS research.run_audit_events (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL REFERENCES research.runs(run_id) ON DELETE CASCADE,
    actor VARCHAR(128) NOT NULL,
    action VARCHAR(128) NOT NULL,
    rule_reason TEXT,
    policy_reason TEXT,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE research.run_approvals
    ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;

CREATE OR REPLACE VIEW fact.production_facts AS
SELECT
    fact_id, ticker, period, period_type, canonical_version, metric, value, unit,
    currency, selected_observation_id, confidence, source_tier,
    official_document_id, reconciliation_status, created_at, updated_at
FROM fact.canonical_facts
WHERE quality_status = 'accepted'
  AND period_type = 'FY'
  AND (confidence IS NULL OR confidence >= 0.80);

INSERT INTO audit.events (event_type, actor, target_table, payload_json)
VALUES (
    'schema_migration',
    'migration_026',
    'ref,ingest,fact,research,valuation,report,audit',
    jsonb_build_object(
        'migration', '026_canonical_schema_cutover',
        'renamed_from_v2', true
    )
);
