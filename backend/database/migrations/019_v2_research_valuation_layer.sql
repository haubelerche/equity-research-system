-- Migration: 019_v2_research_valuation_layer.sql
-- Purpose: Data Warehouse v2, Step 4 — create v2_research and v2_valuation schemas.
-- Fixes the critical snapshot integrity bug: snapshot_items now reference
-- v2_fact.canonical_facts.fact_id (VARCHAR) not financial_facts.id (BIGSERIAL).
-- Does NOT touch any legacy table.
-- Transaction is owned by the migration runner; do not add BEGIN/COMMIT here.

CREATE SCHEMA IF NOT EXISTS v2_research;
CREATE SCHEMA IF NOT EXISTS v2_valuation;

-- ── v2_research.runs ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS v2_research.runs (
    run_id               VARCHAR(64)  PRIMARY KEY,
    ticker               VARCHAR(10)  NOT NULL REFERENCES v2_ref.companies(ticker),
    run_type             VARCHAR(32)  NOT NULL CHECK (
        run_type IN ('full_report', 'flash_memo', 'catalyst_refresh', 'valuation_only', 'data_refresh')
    ),
    objective            TEXT         NOT NULL DEFAULT '',
    status               VARCHAR(32)  NOT NULL CHECK (
        status IN (
            'initialized', 'running', 'data_ready', 'analysis_ready', 'valuation_ready',
            'report_ready', 'needs_human_review', 'approved', 'failed', 'cancelled'
        )
    ),
    current_stage        VARCHAR(64)  NOT NULL DEFAULT 'initialized',
    idempotency_key      VARCHAR(128) UNIQUE,
    snapshot_id          VARCHAR(64),   -- FK set after snapshot is created
    requested_by         VARCHAR(128),
    request_json         JSONB        NOT NULL DEFAULT '{}'::jsonb,
    config_snapshot_json JSONB        NOT NULL DEFAULT '{}'::jsonb,
    flags_json           JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    finished_at          TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_v2_runs_ticker
    ON v2_research.runs(ticker, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_v2_runs_status
    ON v2_research.runs(status, created_at DESC);

-- ── v2_research.snapshots ─────────────────────────────────────────────────────
-- Fixed: canonical_version field ensures snapshots always reference a specific fact version.
CREATE TABLE IF NOT EXISTS v2_research.snapshots (
    snapshot_id       VARCHAR(64)  PRIMARY KEY,
    ticker            VARCHAR(10)  NOT NULL REFERENCES v2_ref.companies(ticker),
    canonical_version VARCHAR(40)  NOT NULL DEFAULT 'v2_prod',
    as_of_date        DATE         NOT NULL,
    from_year         SMALLINT     NOT NULL,
    to_year           SMALLINT     NOT NULL,
    periods_json      JSONB        NOT NULL DEFAULT '[]'::jsonb,
    facts_count       INTEGER      NOT NULL DEFAULT 0
        CHECK (facts_count >= 0),
    status            VARCHAR(20)  NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'stale', 'archived')),
    created_by        VARCHAR(128),
    metadata_json     JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_v2_snapshots_ticker
    ON v2_research.snapshots(ticker, created_at DESC);

-- ── v2_research.snapshot_items ────────────────────────────────────────────────
-- CRITICAL FIX: fact_id is VARCHAR(64) FK to v2_fact.canonical_facts.fact_id.
-- Legacy had item_id as TEXT storing BIGSERIAL cast — broken and incompatible.

CREATE TABLE IF NOT EXISTS v2_research.snapshot_items (
    id              BIGSERIAL    PRIMARY KEY,
    snapshot_id     VARCHAR(64)  NOT NULL REFERENCES v2_research.snapshots(snapshot_id) ON DELETE CASCADE,
    item_type       VARCHAR(32)  NOT NULL CHECK (
        item_type IN ('canonical_fact', 'price_row', 'document_chunk', 'catalyst_event')
    ),
    -- For canonical_fact items, fact_id is a proper FK to v2_fact.canonical_facts.
    fact_id         VARCHAR(64)  REFERENCES v2_fact.canonical_facts(fact_id) ON DELETE SET NULL,
    -- For non-fact items (price_row, document_chunk, catalyst_event), use item_ref.
    item_ref        TEXT,
    source_doc_id   VARCHAR(64)  REFERENCES v2_ingest.source_documents(source_doc_id),
    included_reason TEXT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_v2_snapshot_items_snapshot
    ON v2_research.snapshot_items(snapshot_id, item_type);

CREATE INDEX IF NOT EXISTS idx_v2_snapshot_items_fact
    ON v2_research.snapshot_items(fact_id) WHERE fact_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_v2_snapshot_items_identity
    ON v2_research.snapshot_items
    (snapshot_id, item_type, COALESCE(fact_id, ''), COALESCE(item_ref, ''));

COMMENT ON TABLE v2_research.snapshot_items IS
    'v2: FIXED snapshot items. fact_id is a proper FK to v2_fact.canonical_facts. '
    'Legacy research.snapshot_items stored financial_facts.id::TEXT which was broken.';

-- ── v2_research.run_artifacts ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS v2_research.run_artifacts (
    artifact_id    VARCHAR(64)  PRIMARY KEY,
    run_id         VARCHAR(64)  NOT NULL REFERENCES v2_research.runs(run_id) ON DELETE CASCADE,
    artifact_type  VARCHAR(64)  NOT NULL CHECK (
        artifact_type IN (
            'facts_json', 'valuation_input_pack_json', 'valuation_fcff_json', 'valuation_fcfe_json',
            'valuation_blend_json', 'valuation_pe_json', 'citation_json',
            'report_html', 'report_pdf', 'dq_report_json', 'other'
        )
    ),
    storage_path   TEXT         NOT NULL,
    checksum       CHAR(64),
    is_locked      BOOLEAN      NOT NULL DEFAULT FALSE,
    version        INTEGER      NOT NULL DEFAULT 1,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, artifact_type, version)
);

CREATE INDEX IF NOT EXISTS idx_v2_run_artifacts_run
    ON v2_research.run_artifacts(run_id, artifact_type);

-- ── v2_research.run_approvals ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS v2_research.run_approvals (
    id                  BIGSERIAL    PRIMARY KEY,
    run_id              VARCHAR(64)  NOT NULL REFERENCES v2_research.runs(run_id) ON DELETE CASCADE,
    approval_stage      VARCHAR(32)  NOT NULL CHECK (
        approval_stage IN ('valuation_assumptions', 'report_draft', 'final_report')
    ),
    decision            VARCHAR(16)  NOT NULL CHECK (decision IN ('approved', 'rejected', 'needs_revision')),
    reviewer            VARCHAR(128),
    feedback_patch_json JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Migrate legacy run approvals.
INSERT INTO v2_research.run_approvals (
    run_id, approval_stage, decision, reviewer, feedback_patch_json, created_at
)
SELECT
    ra.run_id,
    ra.approval_stage,
    ra.decision,
    ra.reviewer,
    ra.feedback_patch_json,
    ra.created_at
FROM research.run_approvals ra
WHERE ra.run_id IN (SELECT run_id FROM v2_research.runs)
ON CONFLICT DO NOTHING;

-- ── FK: v2_research.runs.snapshot_id → v2_research.snapshots ─────────────────
ALTER TABLE v2_research.runs
    ADD CONSTRAINT fk_v2_runs_snapshot
    FOREIGN KEY (snapshot_id)
    REFERENCES v2_research.snapshots(snapshot_id)
    DEFERRABLE INITIALLY DEFERRED;

-- ── v2_valuation.runs ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS v2_valuation.runs (
    valuation_run_id  VARCHAR(64)   PRIMARY KEY,
    research_run_id   VARCHAR(64)   REFERENCES v2_research.runs(run_id),
    snapshot_id       VARCHAR(64)   NOT NULL REFERENCES v2_research.snapshots(snapshot_id),
    ticker            VARCHAR(10)   NOT NULL REFERENCES v2_ref.companies(ticker),
    method            VARCHAR(32)   NOT NULL CHECK (
        method IN ('fcff', 'fcfe', 'blend', 'pe_forward', 'pe_net_cash')
    ),
    model_version     VARCHAR(40)   NOT NULL DEFAULT 'v2',
    status            VARCHAR(20)   NOT NULL DEFAULT 'draft' CHECK (
        status IN ('draft', 'approved', 'locked', 'superseded')
    ),
    artifact_id       VARCHAR(64)   REFERENCES v2_research.run_artifacts(artifact_id),
    target_price_vnd  NUMERIC(18,4),
    upside_pct        NUMERIC(8,4),
    blend_formula     TEXT,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    UNIQUE (research_run_id, method)
);

CREATE INDEX IF NOT EXISTS idx_v2_val_runs_ticker
    ON v2_valuation.runs(ticker, created_at DESC);

-- ── v2_valuation.assumptions ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS v2_valuation.assumptions (
    id                BIGSERIAL    PRIMARY KEY,
    valuation_run_id  VARCHAR(64)  NOT NULL REFERENCES v2_valuation.runs(valuation_run_id) ON DELETE CASCADE,
    assumption_key    VARCHAR(100) NOT NULL,
    assumption_value  NUMERIC,
    assumption_text   TEXT,
    source            VARCHAR(80)  NOT NULL DEFAULT 'analyst_input',
    approved_by       VARCHAR(128),
    approved_at       TIMESTAMPTZ,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (valuation_run_id, assumption_key)
);

COMMENT ON TABLE v2_valuation.assumptions IS
    'v2: Valuation assumptions per run and method. '
    'approved_by must be non-null before valuation_run.status can advance to ''approved''. '
    'Covers: wacc, terminal_growth, fcff_weight, fcfe_weight, target_pe, peer_median_pe, etc.';
