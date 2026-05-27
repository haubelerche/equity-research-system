-- Migration: 008_research_snapshots.sql
-- Purpose: Add research.snapshots, research.snapshot_items, research.data_quality_reports.
--
-- Background: The execution plan requires that valuation and reporting read from a
-- frozen snapshot of accepted facts rather than the live database. This ensures
-- reproducibility: a report generated on 2025-01-15 can always be re-derived from
-- the same set of fact IDs that existed at snapshot creation time.
--
-- Also adds research.data_quality_reports to persist build_facts.py gate results,
-- and a snapshot_id FK on research.runs so every research run records which
-- frozen dataset it used.
--
-- Transaction is owned by the migration runner; do not add BEGIN/COMMIT here.

-- 1. research.snapshots — snapshot header per ticker × year-range.
CREATE TABLE IF NOT EXISTS research.snapshots (
    snapshot_id   VARCHAR(64)  PRIMARY KEY,
    ticker        VARCHAR(10)  NOT NULL REFERENCES ref.companies(ticker),
    as_of_date    DATE         NOT NULL,
    from_year     SMALLINT     NOT NULL,
    to_year       SMALLINT     NOT NULL,
    periods_json  JSONB        NOT NULL DEFAULT '[]'::jsonb,
    facts_count   INTEGER      NOT NULL DEFAULT 0,
    status        VARCHAR(20)  NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active', 'stale', 'archived')),
    created_by    VARCHAR(128),
    metadata_json JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_snapshots_ticker
    ON research.snapshots(ticker, created_at DESC);

-- 2. research.snapshot_items — one row per fact/source included in the snapshot.
--    item_type + item_id is a polymorphic reference:
--      'financial_fact' → fact.financial_facts.id (BIGINT cast)
--      'source'         → ingest.sources.source_id
--    More types can be added as the pipeline grows.
CREATE TABLE IF NOT EXISTS research.snapshot_items (
    id              BIGSERIAL    PRIMARY KEY,
    snapshot_id     VARCHAR(64)  NOT NULL REFERENCES research.snapshots(snapshot_id) ON DELETE CASCADE,
    item_type       VARCHAR(32)  NOT NULL CHECK (
        item_type IN ('financial_fact', 'price_row', 'document_chunk', 'catalyst_event', 'source')
    ),
    item_id         TEXT         NOT NULL,
    source_id       VARCHAR(64)  REFERENCES ingest.sources(source_id),
    included_reason TEXT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (snapshot_id, item_type, item_id)
);

CREATE INDEX IF NOT EXISTS idx_research_snapshot_items_snapshot
    ON research.snapshot_items(snapshot_id, item_type);

-- 3. research.data_quality_reports — summary DQ gate result per build_facts run.
--    Persists the output of build_fy_validation_report() so the pipeline has an
--    auditable record of which data quality gates passed before valuation ran.
CREATE TABLE IF NOT EXISTS research.data_quality_reports (
    id                      BIGSERIAL    PRIMARY KEY,
    ticker                  VARCHAR(10)  NOT NULL REFERENCES ref.companies(ticker),
    run_type                VARCHAR(32)  NOT NULL DEFAULT 'build_facts'
                                CHECK (run_type IN ('build_facts', 'ingest', 'manual')),
    from_year               SMALLINT,
    to_year                 SMALLINT,
    annual_reports_collected INTEGER     NOT NULL DEFAULT 0,
    coverage_gate           VARCHAR(10)  NOT NULL CHECK (coverage_gate IN ('pass', 'fail', 'skip')),
    core_keys_gate          VARCHAR(10)  NOT NULL CHECK (core_keys_gate IN ('pass', 'fail', 'skip')),
    source_validation_gate  VARCHAR(10)  NOT NULL CHECK (source_validation_gate IN ('pass', 'fail', 'skip')),
    valuation_gate          VARCHAR(10)  NOT NULL CHECK (valuation_gate IN ('pass', 'fail', 'skip')),
    valuation_ready         BOOLEAN      NOT NULL DEFAULT FALSE,
    run_status              VARCHAR(40)  NOT NULL,
    blocking_reasons_json   JSONB        NOT NULL DEFAULT '[]'::jsonb,
    periods_available_json  JSONB        NOT NULL DEFAULT '[]'::jsonb,
    periods_missing_json    JSONB        NOT NULL DEFAULT '[]'::jsonb,
    details_json            JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_dq_reports_ticker
    ON research.data_quality_reports(ticker, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_research_dq_reports_gate
    ON research.data_quality_reports(valuation_gate, ticker);

-- 4. Link research.runs to a snapshot (nullable — data_refresh runs may not have one).
ALTER TABLE research.runs
    ADD COLUMN IF NOT EXISTS snapshot_id VARCHAR(64)
        REFERENCES research.snapshots(snapshot_id);

CREATE INDEX IF NOT EXISTS idx_research_runs_snapshot
    ON research.runs(snapshot_id) WHERE snapshot_id IS NOT NULL;
