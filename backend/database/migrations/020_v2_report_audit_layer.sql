-- Migration: 020_v2_report_audit_layer.sql
-- Purpose: Data Warehouse v2, Step 5 — create v2_report and v2_audit schemas.
-- v2_report adopts the existing report.* table structure but with proper FKs to v2_fact.
-- v2_audit is an append-only governance log.
-- Does NOT touch any legacy table.
-- Transaction is owned by the migration runner; do not add BEGIN/COMMIT here.

CREATE SCHEMA IF NOT EXISTS v2_report;
CREATE SCHEMA IF NOT EXISTS v2_audit;

-- ── v2_report.reports ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS v2_report.reports (
    report_id         VARCHAR(64)  PRIMARY KEY,
    run_id            VARCHAR(64)  REFERENCES v2_research.runs(run_id),
    ticker            VARCHAR(10)  NOT NULL REFERENCES v2_ref.companies(ticker),
    report_type       VARCHAR(40)  NOT NULL DEFAULT 'full_report',
    report_mode       VARCHAR(20)  NOT NULL DEFAULT 'analyst_draft' CHECK (
        report_mode IN ('analyst_draft', 'client_final', 'internal_debug')
    ),
    status            VARCHAR(20)  NOT NULL DEFAULT 'draft' CHECK (
        status IN ('draft', 'under_review', 'approved', 'exported', 'rejected')
    ),
    html_artifact_id  VARCHAR(64)  REFERENCES v2_research.run_artifacts(artifact_id),
    pdf_artifact_id   VARCHAR(64)  REFERENCES v2_research.run_artifacts(artifact_id),
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_v2_report_ticker
    ON v2_report.reports(ticker, created_at DESC);

-- ── v2_report.claims ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS v2_report.claims (
    claim_id        VARCHAR(64)  PRIMARY KEY,
    report_id       VARCHAR(64)  NOT NULL REFERENCES v2_report.reports(report_id) ON DELETE CASCADE,
    section         VARCHAR(80),
    claim_text      TEXT,
    claim_type      VARCHAR(20)  NOT NULL DEFAULT 'quantitative' CHECK (
        claim_type IN ('quantitative', 'qualitative', 'valuation', 'contextual')
    ),
    ticker          VARCHAR(10)  REFERENCES v2_ref.companies(ticker),
    period          VARCHAR(10),
    metric          VARCHAR(100) REFERENCES v2_ref.line_items(line_item_code),
    value_mentioned NUMERIC(20,4),
    unit            VARCHAR(40),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_v2_claims_report
    ON v2_report.claims(report_id, claim_type);

CREATE INDEX IF NOT EXISTS idx_v2_claims_metric
    ON v2_report.claims(ticker, metric, period);

-- ── v2_report.citation_records ────────────────────────────────────────────────
-- Maps each claim → canonical fact → source document.
-- fact_id is a proper FK to v2_fact.canonical_facts (not just a text field).

CREATE TABLE IF NOT EXISTS v2_report.citation_records (
    citation_id       VARCHAR(64)  PRIMARY KEY,
    claim_id          VARCHAR(64)  NOT NULL REFERENCES v2_report.claims(claim_id) ON DELETE CASCADE,
    -- Proper FK to v2 canonical facts (unlike legacy report.citation_records.fact_id TEXT)
    fact_id           VARCHAR(64)  REFERENCES v2_fact.canonical_facts(fact_id),
    source_doc_id     VARCHAR(64)  REFERENCES v2_ingest.source_documents(source_doc_id),
    chunk_id          BIGINT,
    support_type      VARCHAR(20)  NOT NULL DEFAULT 'direct_value' CHECK (
        support_type IN ('direct_value', 'contextual', 'corroborating')
    ),
    source_tier       SMALLINT     CHECK (source_tier IS NULL OR source_tier BETWEEN 0 AND 3),
    validation_status VARCHAR(20)  NOT NULL DEFAULT 'unverified' CHECK (
        validation_status IN ('verified', 'unverified', 'disputed', 'needs_review')
    ),
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_v2_citation_claim
    ON v2_report.citation_records(claim_id);

CREATE INDEX IF NOT EXISTS idx_v2_citation_fact
    ON v2_report.citation_records(fact_id) WHERE fact_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_v2_citation_identity
    ON v2_report.citation_records
    (claim_id, COALESCE(fact_id, ''), COALESCE(source_doc_id, ''));

COMMENT ON TABLE v2_report.citation_records IS
    'v2: Maps report claims to canonical facts. '
    'fact_id is a proper FK to v2_fact.canonical_facts — not a soft TEXT reference. '
    'A quantitative claim must have at least one citation before report approval.';

-- ── v2_report.gate_results ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS v2_report.gate_results (
    id             BIGSERIAL    PRIMARY KEY,
    report_id      VARCHAR(64)  NOT NULL REFERENCES v2_report.reports(report_id) ON DELETE CASCADE,
    gate_name      VARCHAR(60)  NOT NULL,
    status         VARCHAR(10)  NOT NULL CHECK (status IN ('pass', 'warn', 'fail')),
    severity       VARCHAR(10)  NOT NULL DEFAULT 'medium' CHECK (
        severity IN ('critical', 'high', 'medium', 'low')
    ),
    issue_count    INTEGER      NOT NULL DEFAULT 0,
    issues_json    JSONB        NOT NULL DEFAULT '[]'::jsonb,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (report_id, gate_name)
);

-- ── v2_report.approval_records ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS v2_report.approval_records (
    id             BIGSERIAL    PRIMARY KEY,
    report_id      VARCHAR(64)  NOT NULL REFERENCES v2_report.reports(report_id) ON DELETE CASCADE,
    approval_type  VARCHAR(40)  NOT NULL DEFAULT 'final_export' CHECK (
        approval_type IN ('assumptions', 'report_draft', 'final_export')
    ),
    status         VARCHAR(20)  NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending', 'approved', 'rejected', 'escalated')
    ),
    approved_by    VARCHAR(80),
    approved_at    TIMESTAMPTZ,
    comment        TEXT,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ── Citation completeness view ────────────────────────────────────────────────
-- View: quantitative claims without any citation. Used by export gate.
CREATE OR REPLACE VIEW v2_report.uncited_quantitative_claims AS
SELECT rc.report_id, rc.claim_id, rc.claim_text
FROM v2_report.claims rc
LEFT JOIN v2_report.citation_records cr ON cr.claim_id = rc.claim_id
WHERE rc.claim_type = 'quantitative'
GROUP BY rc.report_id, rc.claim_id, rc.claim_text
HAVING COUNT(cr.citation_id) = 0;

COMMENT ON VIEW v2_report.uncited_quantitative_claims IS
    'v2: Quantitative claims with no citation record. '
    'Used by export_gate to block client_final reports.';

-- ── v2_audit.events ───────────────────────────────────────────────────────────
-- Immutable append-only governance log. No UPDATE or DELETE ever.
CREATE TABLE IF NOT EXISTS v2_audit.events (
    id             BIGSERIAL    PRIMARY KEY,
    event_type     VARCHAR(60)  NOT NULL CHECK (
        event_type IN (
            'schema_migration', 'data_promotion', 'approval', 'gate_result',
            'deletion', 'cost_ledger', 'run_event', 'override_warning'
        )
    ),
    actor          VARCHAR(128) NOT NULL,
    run_id         VARCHAR(64),
    target_table   VARCHAR(80),
    target_id      TEXT,
    payload_json   JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_v2_audit_events_type
    ON v2_audit.events(event_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_v2_audit_events_run
    ON v2_audit.events(run_id) WHERE run_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_v2_audit_events_target
    ON v2_audit.events(target_table, target_id) WHERE target_table IS NOT NULL;

COMMENT ON TABLE v2_audit.events IS
    'v2: Immutable governance log. Append-only — no UPDATE or DELETE. '
    'Covers schema migrations, data promotions, approvals, gate results, and cost tracking.';

-- ── v2_audit.cost_ledger ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS v2_audit.cost_ledger (
    id                BIGSERIAL     PRIMARY KEY,
    run_id            VARCHAR(64),
    step_name         VARCHAR(64)   NOT NULL,
    model_name        VARCHAR(80)   NOT NULL,
    prompt_tokens     INTEGER       NOT NULL DEFAULT 0,
    completion_tokens INTEGER       NOT NULL DEFAULT 0,
    cost_usd          NUMERIC(12,6) NOT NULL DEFAULT 0,
    budget_policy     VARCHAR(32),
    fallback_model    VARCHAR(80),
    stop_reason       VARCHAR(80),
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_v2_cost_run
    ON v2_audit.cost_ledger(run_id) WHERE run_id IS NOT NULL;

-- Migrate legacy cost ledger entries.
INSERT INTO v2_audit.cost_ledger (
    run_id, step_name, model_name, prompt_tokens, completion_tokens,
    cost_usd, budget_policy, fallback_model, stop_reason, created_at
)
SELECT
    run_id, step_name, model_name, prompt_tokens, completion_tokens,
    cost_usd, budget_policy, fallback_model, stop_reason, created_at
FROM research.run_budget_ledger
ON CONFLICT DO NOTHING;

-- ── v2_audit.schema_changes ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS v2_audit.schema_changes (
    id                BIGSERIAL    PRIMARY KEY,
    migration_version VARCHAR(80)  NOT NULL UNIQUE,
    applied_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    description       TEXT
);

-- Record this migration set.
INSERT INTO v2_audit.schema_changes (migration_version, description)
VALUES
    ('016_v2_ref_layer', 'v2_ref schema: companies, line_items, formulas, peer_groups'),
    ('017_v2_ingest_layer', 'v2_ingest schema: source_documents, observations, connector_runs'),
    ('018_v2_fact_layer', 'v2_fact schema: canonical_facts, price_history, catalyst_events + backfill'),
    ('019_v2_research_valuation_layer', 'v2_research + v2_valuation schemas: runs, snapshots, valuation'),
    ('020_v2_report_audit_layer', 'v2_report + v2_audit schemas: claims, citations, gate_results, audit log')
ON CONFLICT (migration_version) DO NOTHING;
