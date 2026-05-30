-- Migration: 012_claim_citations.sql
-- Purpose: Phase 4 of Data Trust Layer — claim-level citation system.
--
--   1. reports            — report objects with version and status
--   2. report_sections    — per-section content tracking
--   3. report_claims      — each quantitative/qualitative claim as a tracked object
--   4. citation_records   — maps each claim → canonical_fact → source_document
--   5. quality_gate_results — deterministic gate pass/fail per report run
--   6. approval_records   — HITL approval trace
--
-- Transaction is owned by the migration runner; do not add BEGIN/COMMIT here.

CREATE SCHEMA IF NOT EXISTS report;

-- ── 1. report.reports ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS report.reports (
    report_id               VARCHAR(64)  PRIMARY KEY,
    ticker                  VARCHAR(10)  NOT NULL REFERENCES ref.companies(ticker),
    report_type             VARCHAR(40)  NOT NULL DEFAULT 'full_report',
    report_version          VARCHAR(20)  NOT NULL DEFAULT 'v1',
    valuation_artifact_id   VARCHAR(64),   -- optional FK to future valuation_artifacts table
    snapshot_id             VARCHAR(64),   -- FK to research.snapshots
    status                  VARCHAR(20)  NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'under_review', 'approved', 'exported', 'rejected')),
    report_path             TEXT,
    citation_artifact_path  TEXT,
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_report_reports_ticker
    ON report.reports(ticker, created_at DESC);

-- ── 2. report.report_sections ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS report.report_sections (
    section_id          BIGSERIAL       PRIMARY KEY,
    report_id           VARCHAR(64)     NOT NULL REFERENCES report.reports(report_id) ON DELETE CASCADE,
    section_name        VARCHAR(80)     NOT NULL,
    section_order       SMALLINT        NOT NULL,
    content_markdown    TEXT,
    generated_by        VARCHAR(40)     DEFAULT 'generate_report_v1',
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    UNIQUE (report_id, section_name)
);

-- ── 3. report.report_claims ───────────────────────────────────────────────────
-- Each quantitative/qualitative claim in a report is a first-class tracked object.
-- Gate 4 (numeric consistency) reads from this table rather than regex-parsing Markdown.
CREATE TABLE IF NOT EXISTS report.report_claims (
    claim_id            VARCHAR(64)     PRIMARY KEY,
    report_id           VARCHAR(64)     NOT NULL REFERENCES report.reports(report_id) ON DELETE CASCADE,
    section             VARCHAR(80),
    claim_text          TEXT,
    claim_type          VARCHAR(20)     NOT NULL DEFAULT 'quantitative'
        CHECK (claim_type IN ('quantitative', 'qualitative', 'valuation', 'contextual')),
    ticker              VARCHAR(10)     REFERENCES ref.companies(ticker),
    period              VARCHAR(10),
    metric              VARCHAR(100),
    value_mentioned     NUMERIC(20,4),
    unit                VARCHAR(40),
    generated_by        VARCHAR(40)     DEFAULT 'generate_report_v1',
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    -- claim_hash for idempotent upsert: sha256(report_id|section|metric|period|value)
    claim_hash          VARCHAR(64),
    UNIQUE (report_id, claim_hash)
);

CREATE INDEX IF NOT EXISTS idx_report_claims_report
    ON report.report_claims(report_id, claim_type);

CREATE INDEX IF NOT EXISTS idx_report_claims_metric
    ON report.report_claims(ticker, metric, period);

-- ── 4. report.citation_records ────────────────────────────────────────────────
-- Maps each claim → canonical fact → source document.
-- This is the machine-readable audit trail for every cited value.
CREATE TABLE IF NOT EXISTS report.citation_records (
    citation_id         VARCHAR(64)     PRIMARY KEY,
    claim_id            VARCHAR(64)     REFERENCES report.report_claims(claim_id) ON DELETE CASCADE,
    fact_id             VARCHAR(64),    -- soft FK to fact.canonical_facts
    source_id           VARCHAR(64)     REFERENCES ingest.sources(source_id),
    chunk_id            BIGINT,         -- FK to ingest.document_chunks when available
    support_type        VARCHAR(20)     NOT NULL DEFAULT 'direct_value'
        CHECK (support_type IN ('direct_value', 'contextual', 'corroborating')),
    source_tier         SMALLINT        CHECK (source_tier IS NULL OR source_tier BETWEEN 0 AND 3),
    support_score       NUMERIC(5,4)    CHECK (support_score IS NULL OR (support_score >= 0 AND support_score <= 1)),
    validation_status   VARCHAR(20)     NOT NULL DEFAULT 'unverified'
        CHECK (validation_status IN ('verified', 'unverified', 'disputed', 'needs_review')),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    UNIQUE (claim_id, fact_id, source_id)
);

CREATE INDEX IF NOT EXISTS idx_citation_records_claim
    ON report.citation_records(claim_id);

CREATE INDEX IF NOT EXISTS idx_citation_records_source_tier
    ON report.citation_records(source_tier, validation_status);

-- ── 5. report.quality_gate_results ────────────────────────────────────────────
-- One row per gate per report run.  Provides machine-readable audit of which
-- gates passed and what failed — used by the approval workflow.
CREATE TABLE IF NOT EXISTS report.quality_gate_results (
    gate_result_id      BIGSERIAL       PRIMARY KEY,
    report_id           VARCHAR(64)     NOT NULL REFERENCES report.reports(report_id) ON DELETE CASCADE,
    gate_name           VARCHAR(60)     NOT NULL,
    gate_number         SMALLINT,
    status              VARCHAR(10)     NOT NULL CHECK (status IN ('pass', 'warn', 'fail')),
    severity            VARCHAR(10)     NOT NULL DEFAULT 'medium'
        CHECK (severity IN ('critical', 'high', 'medium', 'low')),
    issue_count         INTEGER         NOT NULL DEFAULT 0,
    issues_json         JSONB           NOT NULL DEFAULT '[]'::jsonb,
    failed_claim_ids    VARCHAR(64)[],
    failed_fact_ids     VARCHAR(64)[],
    checked_count       INTEGER         NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    UNIQUE (report_id, gate_name)
);

-- ── 6. report.approval_records ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS report.approval_records (
    approval_id         BIGSERIAL       PRIMARY KEY,
    report_id           VARCHAR(64)     NOT NULL REFERENCES report.reports(report_id) ON DELETE CASCADE,
    artifact_version    VARCHAR(20),
    approved_by         VARCHAR(80),
    approval_type       VARCHAR(40)     NOT NULL DEFAULT 'final_export'
        CHECK (approval_type IN ('assumptions', 'report_draft', 'final_export')),
    status              VARCHAR(20)     NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected', 'escalated')),
    approved_at         TIMESTAMPTZ,
    comment             TEXT,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);
