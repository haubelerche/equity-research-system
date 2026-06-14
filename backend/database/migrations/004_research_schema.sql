-- Migration: 004_research_schema.sql
-- Purpose: Research runtime, metrics, valuation, report claims, evidence, evaluation, approvals.
-- Transaction is owned by the migration runner; do not add BEGIN/COMMIT here.
-- Key design decisions:
--   - research.document_chunks is intentionally absent; chunks live in ingest.
--   - idempotency_key, request_json, config_snapshot_json on runs.
--   - retry_count, input_hash, output_hash, error_message on run_steps.
--   - run_artifacts: version, storage_path, checksum, is_locked with COALESCE unique index.
--   - valuation_results.assumption_set_id is NOT NULL.
--   - UNIQUE(run_id, method, scenario) on both valuation tables.
--   - quantitative_claims_without_evidence view enforces citation discipline.
--   - final_report_approval_guard trigger blocks unevidenced approvals.

CREATE SCHEMA IF NOT EXISTS research;

-- Run lifecycle table.
CREATE TABLE IF NOT EXISTS research.runs (
    run_id               VARCHAR(64)  PRIMARY KEY,
    ticker               VARCHAR(10)  NOT NULL REFERENCES ref.companies(ticker),
    run_type             VARCHAR(32)  NOT NULL CHECK (
        run_type IN ('full_report', 'flash_memo', 'catalyst_refresh', 'valuation_only', 'data_refresh')
    ),
    objective            TEXT         NOT NULL,
    status               VARCHAR(32)  NOT NULL CHECK (
        status IN (
            'initialized', 'running', 'data_ready', 'analysis_ready', 'valuation_ready',
            'report_ready', 'needs_human_review', 'approved', 'failed', 'cancelled'
        )
    ),
    current_stage        VARCHAR(64)  NOT NULL DEFAULT 'initialized',
    idempotency_key      VARCHAR(128) UNIQUE,
    org_id               VARCHAR(64),
    requested_by         VARCHAR(128),
    request_json         JSONB        NOT NULL DEFAULT '{}'::jsonb,
    config_snapshot_json JSONB        NOT NULL DEFAULT '{}'::jsonb,
    flags_json           JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    finished_at          TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_research_runs_ticker
    ON research.runs(ticker, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_research_runs_status
    ON research.runs(status, created_at DESC);

-- Individual steps within a run.
CREATE TABLE IF NOT EXISTS research.run_steps (
    id             BIGSERIAL    PRIMARY KEY,
    run_id         VARCHAR(64)  NOT NULL REFERENCES research.runs(run_id) ON DELETE CASCADE,
    step_name      VARCHAR(64)  NOT NULL,
    agent_name     VARCHAR(64)  NOT NULL,
    status         VARCHAR(32)  NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'skipped')),
    retry_count    INTEGER      NOT NULL DEFAULT 0,
    input_hash     TEXT,
    output_hash    TEXT,
    policy_reason  TEXT,
    error_message  TEXT,
    started_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    ended_at       TIMESTAMPTZ,
    duration_ms    BIGINT,
    metadata_json  JSONB        NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_research_run_steps_run
    ON research.run_steps(run_id, started_at DESC);

-- Run artifacts: report files, inventory summaries, evaluation exports.
-- NOT for metrics, valuation results, or claims — use dedicated tables.
CREATE TABLE IF NOT EXISTS research.run_artifacts (
    artifact_id        VARCHAR(64)  PRIMARY KEY,
    run_id             VARCHAR(64)  NOT NULL REFERENCES research.runs(run_id) ON DELETE CASCADE,
    artifact_type      VARCHAR(64)  NOT NULL CHECK (
        artifact_type IN (
            'data_inventory', 'metric_table', 'valuation_input_pack_json', 'valuation_result_json', 'source_manifest_json',
            'claim_ledger_json', 'eval_result_json', 'run_log_json', 'report_md',
            'report_html', 'report_pdf', 'other'
        )
    ),
    section_key        VARCHAR(64),
    version            INTEGER      NOT NULL DEFAULT 1,
    payload_json       JSONB        NOT NULL DEFAULT '{}'::jsonb,
    evidence_refs_json JSONB        NOT NULL DEFAULT '[]'::jsonb,
    storage_path       TEXT,
    checksum           CHAR(64),
    is_locked          BOOLEAN      NOT NULL DEFAULT FALSE,
    confidence         NUMERIC(6,4) CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    created_by_agent   VARCHAR(64),
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_run_artifacts_run
    ON research.run_artifacts(run_id, artifact_type);

-- Prevent duplicate artifact_type+section_key+version per run.
CREATE UNIQUE INDEX IF NOT EXISTS uq_research_run_artifact_version
    ON research.run_artifacts(run_id, artifact_type, COALESCE(section_key, ''), version);

-- Human approval records.
CREATE TABLE IF NOT EXISTS research.run_approvals (
    id                  BIGSERIAL    PRIMARY KEY,
    run_id              VARCHAR(64)  NOT NULL REFERENCES research.runs(run_id) ON DELETE CASCADE,
    approval_stage      VARCHAR(32)  NOT NULL CHECK (
        approval_stage IN ('valuation_assumptions', 'report_draft', 'final_report')
    ),
    decision            VARCHAR(16)  NOT NULL CHECK (decision IN ('approved', 'rejected', 'needs_revision')),
    reviewer            VARCHAR(128),
    feedback_patch_json JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- LLM cost ledger per step.
CREATE TABLE IF NOT EXISTS research.run_budget_ledger (
    id                BIGSERIAL     PRIMARY KEY,
    run_id            VARCHAR(64)   NOT NULL REFERENCES research.runs(run_id) ON DELETE CASCADE,
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

CREATE INDEX IF NOT EXISTS idx_research_budget_run
    ON research.run_budget_ledger(run_id);

-- Audit trail for significant run events.
CREATE TABLE IF NOT EXISTS research.run_audit_events (
    id            BIGSERIAL    PRIMARY KEY,
    run_id        VARCHAR(64)  NOT NULL REFERENCES research.runs(run_id) ON DELETE CASCADE,
    actor         VARCHAR(128) NOT NULL,
    action        VARCHAR(64)  NOT NULL,
    rule_reason   TEXT,
    policy_reason TEXT,
    payload_json  JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_audit_run
    ON research.run_audit_events(run_id, created_at DESC);

-- Deterministic metric values computed by Python from accepted facts.
-- ROE, ROA, margins, growth rates, P/E, EV/EBITDA, WACC, FCFF, etc.
-- Must NOT be stored in fact.financial_facts.
CREATE TABLE IF NOT EXISTS research.metric_values (
    id                BIGSERIAL    PRIMARY KEY,
    run_id            VARCHAR(64)  NOT NULL REFERENCES research.runs(run_id) ON DELETE CASCADE,
    ticker            VARCHAR(10)  NOT NULL REFERENCES ref.companies(ticker),
    fiscal_year       SMALLINT,
    fiscal_period     VARCHAR(4)   CHECK (fiscal_period IN ('FY', 'Q1', 'Q2', 'Q3', 'Q4', 'TTM')),
    formula_id        VARCHAR(20)  NOT NULL REFERENCES ref.formulas(formula_id),
    metric_key        VARCHAR(100) NOT NULL,
    value             NUMERIC(28,8),
    unit              VARCHAR(40)  NOT NULL,
    input_fact_ids    BIGINT[]     NOT NULL DEFAULT '{}',
    input_values_json JSONB        NOT NULL DEFAULT '{}'::jsonb,
    warnings_json     JSONB        NOT NULL DEFAULT '[]'::jsonb,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_metric_values_run
    ON research.metric_values(run_id, metric_key);
CREATE INDEX IF NOT EXISTS idx_research_metric_values_ticker
    ON research.metric_values(ticker, fiscal_year, formula_id);

-- Valuation assumption sets: one row per method × scenario.
-- Human approval required before moving from 'draft' to 'approved'.
CREATE TABLE IF NOT EXISTS research.valuation_assumption_sets (
    id               BIGSERIAL    PRIMARY KEY,
    run_id           VARCHAR(64)  NOT NULL REFERENCES research.runs(run_id) ON DELETE CASCADE,
    method           VARCHAR(32)  NOT NULL CHECK (method IN ('dcf', 'pe', 'pb', 'ev_ebitda', 'mixed')),
    scenario         VARCHAR(20)  NOT NULL CHECK (scenario IN ('bear', 'base', 'bull')),
    assumptions_json JSONB        NOT NULL,
    status           VARCHAR(20)  NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'rejected')),
    approved_by      VARCHAR(128),
    approved_at      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, method, scenario)
);

-- Valuation results: assumption_set_id is NOT NULL — every result must trace to an assumption set.
CREATE TABLE IF NOT EXISTS research.valuation_results (
    id                   BIGSERIAL     PRIMARY KEY,
    run_id               VARCHAR(64)   NOT NULL REFERENCES research.runs(run_id) ON DELETE CASCADE,
    assumption_set_id    BIGINT        NOT NULL REFERENCES research.valuation_assumption_sets(id),
    method               VARCHAR(32)   NOT NULL CHECK (method IN ('dcf', 'pe', 'pb', 'ev_ebitda', 'mixed')),
    scenario             VARCHAR(20)   NOT NULL CHECK (scenario IN ('bear', 'base', 'bull')),
    target_price         NUMERIC(18,4),
    valuation_range_low  NUMERIC(18,4),
    valuation_range_high NUMERIC(18,4),
    enterprise_value     NUMERIC(28,4),
    equity_value         NUMERIC(28,4),
    result_json          JSONB         NOT NULL DEFAULT '{}'::jsonb,
    created_at           TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, method, scenario)
);

CREATE INDEX IF NOT EXISTS idx_research_valuation_results_run
    ON research.valuation_results(run_id, method, scenario);

-- Report sections: one row per section per version.
CREATE TABLE IF NOT EXISTS research.report_sections (
    section_id       BIGSERIAL    PRIMARY KEY,
    run_id           VARCHAR(64)  NOT NULL REFERENCES research.runs(run_id) ON DELETE CASCADE,
    section_key      VARCHAR(64)  NOT NULL,
    section_title    TEXT         NOT NULL,
    section_order    INTEGER      NOT NULL,
    content_markdown TEXT         NOT NULL,
    version          INTEGER      NOT NULL DEFAULT 1,
    status           VARCHAR(20)  NOT NULL DEFAULT 'draft' CHECK (
        status IN ('draft', 'approved', 'rejected', 'needs_revision')
    ),
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, section_key, version)
);

-- Normalized report claim ledger.
CREATE TABLE IF NOT EXISTS research.report_claims (
    claim_id          BIGSERIAL    PRIMARY KEY,
    run_id            VARCHAR(64)  NOT NULL REFERENCES research.runs(run_id) ON DELETE CASCADE,
    section_id        BIGINT       REFERENCES research.report_sections(section_id) ON DELETE SET NULL,
    section_key       VARCHAR(64),
    claim_text        TEXT         NOT NULL,
    claim_type        VARCHAR(20)  NOT NULL CHECK (claim_type IN ('quantitative', 'qualitative', 'inference')),
    numbers_used_json JSONB        NOT NULL DEFAULT '[]'::jsonb,
    confidence        NUMERIC(5,4) CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    verdict           VARCHAR(20)  NOT NULL CHECK (verdict IN ('pass', 'fail', 'needs_review')),
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_report_claims_run
    ON research.report_claims(run_id, verdict, claim_type);

-- Claim-to-evidence mapping (polymorphic: evidence_id references different tables by type).
CREATE TABLE IF NOT EXISTS research.claim_evidence (
    id              BIGSERIAL    PRIMARY KEY,
    claim_id        BIGINT       NOT NULL REFERENCES research.report_claims(claim_id) ON DELETE CASCADE,
    evidence_type   VARCHAR(32)  NOT NULL CHECK (
        evidence_type IN (
            'financial_fact', 'metric_value', 'valuation_result',
            'source', 'document_chunk', 'catalyst_event'
        )
    ),
    evidence_id     TEXT         NOT NULL,
    source_id       VARCHAR(64)  REFERENCES ingest.sources(source_id),
    quote_text      TEXT,
    relevance_score NUMERIC(5,4) CHECK (relevance_score IS NULL OR (relevance_score >= 0 AND relevance_score <= 1)),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_claim_evidence_claim
    ON research.claim_evidence(claim_id);

-- Evaluation results: one row per eval gate per run.
CREATE TABLE IF NOT EXISTS research.evaluation_results (
    id           BIGSERIAL    PRIMARY KEY,
    run_id       VARCHAR(64)  NOT NULL REFERENCES research.runs(run_id) ON DELETE CASCADE,
    eval_name    VARCHAR(80)  NOT NULL CHECK (
        eval_name IN (
            'numeric_consistency', 'citation_coverage', 'citation_validity', 'claim_evidence_validity',
            'quantitative_claim_evidence', 'stale_data', 'valuation_reproducibility', 'unsupported_claims', 'overall'
        )
    ),
    score        NUMERIC(8,4),
    threshold    NUMERIC(8,4),
    passed       BOOLEAN      NOT NULL,
    details_json JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_evaluation_results_run
    ON research.evaluation_results(run_id, eval_name);

-- View: quantitative claims with no evidence (used by approval guard and evaluation gate).
CREATE OR REPLACE VIEW research.quantitative_claims_without_evidence AS
SELECT rc.run_id, rc.claim_id, rc.claim_text
FROM research.report_claims rc
LEFT JOIN research.claim_evidence ce ON ce.claim_id = rc.claim_id
WHERE rc.claim_type = 'quantitative'
GROUP BY rc.run_id, rc.claim_id, rc.claim_text
HAVING COUNT(ce.id) = 0;

-- View: claim evidence rows that reference non-existent rows (polymorphic integrity check).
CREATE OR REPLACE VIEW research.invalid_claim_evidence AS
SELECT ce.*
FROM research.claim_evidence ce
WHERE
    (ce.evidence_type = 'financial_fact'
        AND NOT (ce.evidence_id ~ '^[0-9]+$'
            AND EXISTS (SELECT 1 FROM fact.financial_facts ff WHERE ff.id = ce.evidence_id::BIGINT)))
    OR (ce.evidence_type = 'metric_value'
        AND NOT (ce.evidence_id ~ '^[0-9]+$'
            AND EXISTS (SELECT 1 FROM research.metric_values mv WHERE mv.id = ce.evidence_id::BIGINT)))
    OR (ce.evidence_type = 'valuation_result'
        AND NOT (ce.evidence_id ~ '^[0-9]+$'
            AND EXISTS (SELECT 1 FROM research.valuation_results vr WHERE vr.id = ce.evidence_id::BIGINT)))
    OR (ce.evidence_type = 'source'
        AND NOT EXISTS (SELECT 1 FROM ingest.sources s WHERE s.source_id = ce.evidence_id))
    OR (ce.evidence_type = 'document_chunk'
        AND NOT (ce.evidence_id ~ '^[0-9]+$'
            AND EXISTS (SELECT 1 FROM ingest.document_chunks dc WHERE dc.chunk_id = ce.evidence_id::BIGINT)))
    OR (ce.evidence_type = 'catalyst_event'
        AND NOT EXISTS (SELECT 1 FROM fact.catalyst_events ev WHERE ev.event_id = ce.evidence_id));

-- Trigger: block final_report approval when quantitative claims lack evidence or have invalid evidence.
CREATE OR REPLACE FUNCTION research.final_report_approval_guard()
RETURNS TRIGGER AS $$
DECLARE
    missing_count INTEGER;
    invalid_count INTEGER;
BEGIN
    IF NEW.approval_stage = 'final_report' AND NEW.decision = 'approved' THEN
        SELECT COUNT(*) INTO missing_count
        FROM research.quantitative_claims_without_evidence
        WHERE run_id = NEW.run_id;

        IF missing_count > 0 THEN
            RAISE EXCEPTION 'Cannot approve final_report: % quantitative claim(s) have no evidence', missing_count;
        END IF;

        SELECT COUNT(*) INTO invalid_count
        FROM research.invalid_claim_evidence ce
        JOIN research.report_claims rc ON rc.claim_id = ce.claim_id
        WHERE rc.run_id = NEW.run_id;

        IF invalid_count > 0 THEN
            RAISE EXCEPTION 'Cannot approve final_report: % claim evidence row(s) are invalid', invalid_count;
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_final_report_approval_guard ON research.run_approvals;

CREATE TRIGGER trg_final_report_approval_guard
BEFORE INSERT OR UPDATE ON research.run_approvals
FOR EACH ROW
EXECUTE FUNCTION research.final_report_approval_guard();
