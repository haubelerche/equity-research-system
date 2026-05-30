-- Migration: 010_source_documents.sql
-- Purpose: Phase 1 of Data Trust Layer.
--   1. Add source_tier (0-4) column to ingest.sources.
--   2. Extend ingest.raw_payloads with connector metadata (connector_name,
--      connector_version, request_uri, request_params, response_path,
--      response_checksum).
--   3. Create parser_runs table.
--   4. Fix fact.accepted_financial_facts view to expose source_id and
--      connector_version (previously stripped, breaking downstream provenance).
--   5. Add causality_level to fact.catalyst_events.
--
-- Tier mapping policy (not a direct copy of reliability_tier):
--   Tier 0: audited BCTC, annual_report, regulatory_filing, exchange disclosure
--   Tier 1: company IR, manual upload
--   Tier 2: reputable media, industry_report, news
--   Tier 3: vnstock/API aggregator, tender/bidding, generic regulatory scrapers
--   Tier 4: LLM output (forbidden as fact source -- not stored here)
--
-- Transaction is owned by the migration runner; do not add BEGIN/COMMIT here.

-- ── 1. source_tier column on ingest.sources ───────────────────────────────────

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'ingest' AND table_name = 'sources'
          AND column_name = 'source_tier'
    ) THEN
        ALTER TABLE ingest.sources ADD COLUMN source_tier SMALLINT;
    END IF;
END $$;

-- Apply tier by source_type. Existing rows get a policy-driven default.
-- NOTE: financial_statement/disclosure rows fetched via vnstock API are mapped
-- to Tier 3 here, not Tier 0. When Phase 1B introduces bctc_audited/hose_filing
-- source_types backed by actual documents, those will receive Tier 0.
UPDATE ingest.sources SET source_tier = 3
WHERE source_type IN (
    'vnstock_financial', 'vnstock_price', 'vnstock_company', 'financial_statement',
    'market_reference', 'tender', 'bidding', 'regulatory'
) AND source_tier IS NULL;

UPDATE ingest.sources SET source_tier = 2
WHERE source_type IN ('news', 'industry_report')
AND source_tier IS NULL;

UPDATE ingest.sources SET source_tier = 1
WHERE source_type IN ('manual')
AND source_tier IS NULL;

-- annual_report and disclosure via HOSE/HNX connectors: Tier 0 (exchange filings)
-- regulatory_filing: Tier 0 (government documents)
UPDATE ingest.sources SET source_tier = 0
WHERE source_type IN ('annual_report', 'disclosure', 'regulatory_filing')
AND source_tier IS NULL;

-- Safe fallback for any remaining NULLs
UPDATE ingest.sources SET source_tier = 3 WHERE source_tier IS NULL;

-- Now enforce NOT NULL and range constraint
ALTER TABLE ingest.sources ALTER COLUMN source_tier SET NOT NULL;
ALTER TABLE ingest.sources ALTER COLUMN source_tier SET DEFAULT 3;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_schema = 'ingest' AND table_name = 'sources'
          AND constraint_name = 'chk_source_tier'
    ) THEN
        ALTER TABLE ingest.sources
            ADD CONSTRAINT chk_source_tier CHECK (source_tier BETWEEN 0 AND 3);
    END IF;
END $$;

-- Index for fast tier-based lookups (Gate 2 and Gate 5 queries)
CREATE INDEX IF NOT EXISTS idx_ingest_sources_tier
    ON ingest.sources(source_tier, ticker);

-- ── 2. Extend ingest.raw_payloads with connector metadata ─────────────────────

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'ingest' AND table_name = 'raw_payloads'
          AND column_name = 'connector_name'
    ) THEN
        ALTER TABLE ingest.raw_payloads ADD COLUMN connector_name VARCHAR(60);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'ingest' AND table_name = 'raw_payloads'
          AND column_name = 'connector_version'
    ) THEN
        ALTER TABLE ingest.raw_payloads ADD COLUMN connector_version VARCHAR(40);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'ingest' AND table_name = 'raw_payloads'
          AND column_name = 'request_uri'
    ) THEN
        ALTER TABLE ingest.raw_payloads ADD COLUMN request_uri TEXT;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'ingest' AND table_name = 'raw_payloads'
          AND column_name = 'request_params'
    ) THEN
        ALTER TABLE ingest.raw_payloads ADD COLUMN request_params JSONB;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'ingest' AND table_name = 'raw_payloads'
          AND column_name = 'response_path'
    ) THEN
        ALTER TABLE ingest.raw_payloads ADD COLUMN response_path TEXT;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'ingest' AND table_name = 'raw_payloads'
          AND column_name = 'response_checksum'
    ) THEN
        ALTER TABLE ingest.raw_payloads ADD COLUMN response_checksum VARCHAR(64);
    END IF;
END $$;

-- ── 3. parser_runs table ───────────────────────────────────────────────────────
-- Tracks which parser/version processed each source document and when.
-- Required for Gate 2 lineage: canonical_fact → observation → raw_payload → parser_run.

CREATE TABLE IF NOT EXISTS ingest.parser_runs (
    parser_run_id   BIGSERIAL    PRIMARY KEY,
    source_id       VARCHAR(64)  NOT NULL REFERENCES ingest.sources(source_id) ON DELETE CASCADE,
    parser_name     VARCHAR(60)  NOT NULL,
    parser_version  VARCHAR(40)  NOT NULL,
    started_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    status          VARCHAR(20)  NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'completed', 'failed', 'skipped')),
    rows_extracted  INTEGER      NOT NULL DEFAULT 0,
    error_message   TEXT,
    UNIQUE (source_id, parser_name, parser_version, started_at)
);

CREATE INDEX IF NOT EXISTS idx_ingest_parser_runs_source
    ON ingest.parser_runs(source_id);

CREATE INDEX IF NOT EXISTS idx_ingest_parser_runs_status
    ON ingest.parser_runs(status, started_at DESC);

-- ── 4. Fix fact.accepted_financial_facts view ─────────────────────────────────
-- Previous definition did not SELECT source_id or connector_version, meaning
-- all consumers of the view lost source provenance at the point of reading.

CREATE OR REPLACE VIEW fact.accepted_financial_facts AS
SELECT
    id,
    ticker,
    fiscal_year,
    fiscal_period,
    line_item_code,
    value,
    unit,
    currency,
    source_id,
    connector_version,
    confidence,
    effective_date,
    ingested_at
FROM fact.financial_facts
WHERE validation_status = 'accepted'
  AND fiscal_period      = 'FY'
  AND is_current         = TRUE;

COMMENT ON VIEW fact.accepted_financial_facts IS
    'Valuation-safe subset: accepted, FY, current facts only. '
    'Includes source_id and connector_version for downstream provenance. '
    'Valuation/reporting code must read from this view.';

-- ── 5. causality_level on fact.catalyst_events ────────────────────────────────
-- Required for catalyst narrative guardrails (Gate 6).
-- Default: contextual_event — the safest assumption until a driver is confirmed.

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fact' AND table_name = 'catalyst_events'
          AND column_name = 'causality_level'
    ) THEN
        ALTER TABLE fact.catalyst_events
            ADD COLUMN causality_level VARCHAR(40) NOT NULL DEFAULT 'contextual_event'
            CHECK (causality_level IN (
                'contextual_event',
                'potential_driver',
                'management_disclosed_driver',
                'validated_driver'
            ));
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fact' AND table_name = 'catalyst_events'
          AND column_name = 'fiscal_period_overlap'
    ) THEN
        ALTER TABLE fact.catalyst_events ADD COLUMN fiscal_period_overlap VARCHAR(10);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fact' AND table_name = 'catalyst_events'
          AND column_name = 'driver_type'
    ) THEN
        ALTER TABLE fact.catalyst_events ADD COLUMN driver_type VARCHAR(60);
    END IF;
END $$;
