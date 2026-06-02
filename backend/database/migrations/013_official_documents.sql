-- Migration: 013_official_documents.sql
-- Purpose: Source-Provenance Rebuild, Phase 1 — Dual-Source Schema (ADAPTED).
--
-- The provenance plan asks for four tables: acquisition_sources, official_documents,
-- verified_financial_facts, fact_reconciliation_results. Three of those already exist
-- in the Data Trust Layer under different names:
--
--   plan: acquisition_sources         -> ingest.sources + ingest.raw_payloads + ingest.parser_runs
--   plan: verified_financial_facts    -> fact.canonical_facts (this migration adds the verification link + view)
--   plan: fact_reconciliation_results -> fact.fact_reconciliation (Phase 4 extends it for API-vs-official)
--
-- The genuinely MISSING piece is the official-document layer. This migration adds it:
--
--   1. ingest.official_documents — Tier 0/1 official documents (BCTC/BCTN/exchange/IR).
--   2. fact.fact_observations    — add official-source extraction provenance columns
--      (official_document_id, page_number, table_name, extracted_text). An official
--      fact is just an observation with extraction_method='pdf_ocr'/'manual' that links
--      to an official_document, so the existing observation→canonical model is reused.
--   3. fact.canonical_facts      — add verification linkage (official_document_id,
--      reconciliation_status, verified_by, verified_at) + a CHECK that a fact cannot be
--      marked matched_official/manual_reviewed without an official_document_id.
--   4. fact.verified_financial_facts — view = canonical facts that are safe for FINAL
--      reports (have an official_document_id AND an acceptable reconciliation status).
--
-- Transaction is owned by the migration runner; do not add BEGIN/COMMIT here.

-- ── 1. ingest.official_documents ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ingest.official_documents (
    official_document_id  BIGSERIAL    PRIMARY KEY,
    ticker                VARCHAR(10)  REFERENCES ref.companies(ticker),
    company_name          TEXT,
    source_type           VARCHAR(40)  NOT NULL
        CHECK (source_type IN (
            'audited_financial_statement',
            'annual_report',
            'exchange_disclosure',
            'company_ir',
            'regulatory_notice',
            'official_tender',
            'bhyt_policy',
            'news_article',
            'broker_report'
        )),
    -- Tier 0 = official/audited/exchange/regulatory; Tier 1 = company IR;
    -- Tier 2 = reputable media / broker. Tier 3 is NOT allowed here (this table is
    -- the verification layer, not the acquisition layer).
    source_tier           SMALLINT     NOT NULL DEFAULT 0
        CHECK (source_tier BETWEEN 0 AND 2),
    issuer                TEXT,
    title                 TEXT         NOT NULL,
    url                   TEXT,
    local_path            TEXT,
    published_date        DATE,
    fiscal_year           INTEGER,
    language              VARCHAR(5)   NOT NULL DEFAULT 'vi',
    file_hash             VARCHAR(64),
    fetched_at            TIMESTAMPTZ,
    status                VARCHAR(20)  NOT NULL DEFAULT 'registered'
        CHECK (status IN ('registered', 'fetched', 'extracted', 'verified', 'failed')),
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    -- Same official document is unique per (ticker, source_type, fiscal_year, title).
    UNIQUE (ticker, source_type, fiscal_year, title)
);

CREATE INDEX IF NOT EXISTS idx_official_documents_ticker_year
    ON ingest.official_documents(ticker, fiscal_year);

CREATE INDEX IF NOT EXISTS idx_official_documents_tier
    ON ingest.official_documents(source_tier);

COMMENT ON TABLE ingest.official_documents IS
    'Official verification-layer documents (BCTC/BCTN/exchange/IR/regulatory). '
    'A FINAL-report quantitative claim must cite a row here, never an API/provider source.';

-- ── 2. fact.fact_observations — official extraction provenance ────────────────
-- An official-source fact is an observation with extraction_method pdf_ocr/manual that
-- links to an official_document. These columns are NULL for ordinary API observations.

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='fact' AND table_name='fact_observations'
          AND column_name='official_document_id'
    ) THEN
        ALTER TABLE fact.fact_observations
            ADD COLUMN official_document_id BIGINT
                REFERENCES ingest.official_documents(official_document_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='fact' AND table_name='fact_observations'
          AND column_name='page_number'
    ) THEN
        ALTER TABLE fact.fact_observations ADD COLUMN page_number INTEGER;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='fact' AND table_name='fact_observations'
          AND column_name='table_name'
    ) THEN
        ALTER TABLE fact.fact_observations ADD COLUMN table_name VARCHAR(120);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='fact' AND table_name='fact_observations'
          AND column_name='extracted_text'
    ) THEN
        ALTER TABLE fact.fact_observations ADD COLUMN extracted_text TEXT;
    END IF;
END $$;

-- ── 3. fact.canonical_facts — verification linkage ────────────────────────────

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='fact' AND table_name='canonical_facts'
          AND column_name='official_document_id'
    ) THEN
        ALTER TABLE fact.canonical_facts
            ADD COLUMN official_document_id BIGINT
                REFERENCES ingest.official_documents(official_document_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='fact' AND table_name='canonical_facts'
          AND column_name='reconciliation_status'
    ) THEN
        ALTER TABLE fact.canonical_facts
            ADD COLUMN reconciliation_status VARCHAR(30) NOT NULL DEFAULT 'missing_official'
            CHECK (reconciliation_status IN (
                'matched_official',
                'mismatch',
                'missing_official',
                'missing_api',
                'manual_review_required',
                'manual_reviewed'
            ));
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='fact' AND table_name='canonical_facts'
          AND column_name='verified_by'
    ) THEN
        ALTER TABLE fact.canonical_facts ADD COLUMN verified_by VARCHAR(80);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='fact' AND table_name='canonical_facts'
          AND column_name='verified_at'
    ) THEN
        ALTER TABLE fact.canonical_facts ADD COLUMN verified_at TIMESTAMPTZ;
    END IF;
END $$;

-- Core invariant (plan Phase 1 test 3 & 5): a fact cannot be marked verified against an
-- official source unless it actually links to one. A provider-only fact therefore cannot
-- carry reconciliation_status matched_official / manual_reviewed.
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_schema='fact' AND table_name='canonical_facts'
          AND constraint_name='chk_verified_requires_official_doc'
    ) THEN
        ALTER TABLE fact.canonical_facts
            ADD CONSTRAINT chk_verified_requires_official_doc
            CHECK (
                reconciliation_status NOT IN ('matched_official', 'manual_reviewed')
                OR official_document_id IS NOT NULL
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_canonical_facts_official_doc
    ON fact.canonical_facts(official_document_id)
    WHERE official_document_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_canonical_facts_reconciliation
    ON fact.canonical_facts(reconciliation_status, ticker);

-- ── 4. fact.verified_financial_facts view ─────────────────────────────────────
-- The plan's "verified_financial_facts" as an adapted view: the subset of canonical
-- facts that are SAFE TO CITE IN A FINAL REPORT. Must (a) link to an official document
-- and (b) have an acceptable reconciliation status. Tier-3-only facts are excluded by
-- construction (they have no official_document_id).

CREATE OR REPLACE VIEW fact.verified_financial_facts AS
SELECT
    cf.fact_id,
    cf.ticker,
    cf.period,
    cf.period_type,
    cf.canonical_version,
    cf.metric,
    cf.value,
    cf.unit,
    cf.currency,
    cf.official_document_id,
    od.source_type        AS official_source_type,
    od.source_tier        AS official_source_tier,
    od.title              AS official_document_title,
    od.issuer             AS official_issuer,
    od.fiscal_year        AS official_fiscal_year,
    cf.reconciliation_status,
    cf.confidence,
    cf.verified_by,
    cf.verified_at,
    cf.selected_observation_id
FROM fact.canonical_facts cf
JOIN ingest.official_documents od
    ON od.official_document_id = cf.official_document_id
WHERE cf.official_document_id IS NOT NULL
  AND cf.reconciliation_status IN ('matched_official', 'manual_reviewed')
  AND cf.quality_status = 'accepted';

COMMENT ON VIEW fact.verified_financial_facts IS
    'FINAL-report-safe facts: canonical facts linked to a Tier 0/1/2 official document '
    'with reconciliation_status matched_official or manual_reviewed. '
    'scripts/generate_report.py --mode final must read numeric claims from this view.';
