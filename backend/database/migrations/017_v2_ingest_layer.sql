-- Migration: 017_v2_ingest_layer.sql
-- Purpose: Data Warehouse v2, Step 2 — create v2_ingest schema.
-- Creates: source_documents (replaces ingest.sources + ingest.official_documents),
--          observations (replaces fact.financial_facts + fact.fact_observations),
--          connector_runs.
-- Does NOT touch any legacy table.
-- Transaction is owned by the migration runner; do not add BEGIN/COMMIT here.

CREATE SCHEMA IF NOT EXISTS v2_ingest;

-- ── v2_ingest.source_documents ────────────────────────────────────────────────
-- Unified source document registry. Replaces ingest.sources + ingest.official_documents.
-- source_doc_id: SHA256-based deterministic ID computed by the Python DAL.
-- Tier policy enforced at application level (see data_contracts.md).

CREATE TABLE IF NOT EXISTS v2_ingest.source_documents (
    source_doc_id     VARCHAR(64)  PRIMARY KEY,
    ticker            VARCHAR(10)  REFERENCES v2_ref.companies(ticker),
    source_type       VARCHAR(50)  NOT NULL CHECK (
        source_type IN (
            'audited_financial_statement', 'annual_report', 'exchange_disclosure',
            'company_ir', 'regulatory_notice', 'vnstock_financial', 'vnstock_price',
            'vnstock_company', 'golden_csv', 'manual', 'news', 'industry_report'
        )
    ),
    source_tier       SMALLINT     NOT NULL DEFAULT 3
                          CHECK (source_tier BETWEEN 0 AND 3),
    source_uri        TEXT         NOT NULL,
    source_title      TEXT,
    issuer            TEXT,
    published_at      TIMESTAMPTZ,
    fiscal_year       SMALLINT,
    fiscal_period     VARCHAR(4)   CHECK (fiscal_period IN ('FY', 'Q1', 'Q2', 'Q3', 'Q4')),
    checksum          CHAR(64)     NOT NULL,
    local_path        TEXT,
    language          VARCHAR(5)   NOT NULL DEFAULT 'vi',
    fetch_status      VARCHAR(20)  NOT NULL DEFAULT 'registered' CHECK (
        fetch_status IN ('registered', 'fetched', 'extracted', 'verified', 'failed')
    ),
    connector_name    VARCHAR(60),
    connector_version VARCHAR(40),
    metadata_json     JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    -- Dedup by content: same ticker + type + fiscal_year + content checksum
    UNIQUE (ticker, source_type, fiscal_year, checksum)
);

CREATE INDEX IF NOT EXISTS idx_v2_src_docs_ticker
    ON v2_ingest.source_documents(ticker, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_v2_src_docs_tier
    ON v2_ingest.source_documents(source_tier, ticker);

CREATE INDEX IF NOT EXISTS idx_v2_src_docs_checksum
    ON v2_ingest.source_documents(checksum);

CREATE INDEX IF NOT EXISTS idx_v2_src_docs_type_year
    ON v2_ingest.source_documents(source_type, fiscal_year);

COMMENT ON TABLE v2_ingest.source_documents IS
    'v2: Unified source document registry. '
    'Replaces ingest.sources + ingest.official_documents. '
    'source_doc_id = SHA256(source_type||source_uri||checksum). '
    'tier 0 = audited official, tier 3 = API aggregator.';

-- ── v2_ingest.observations ────────────────────────────────────────────────────
-- One row per (ticker, period, metric, source_doc_id). All candidates before winner selection.
-- Replaces fact.financial_facts (legacy write target) and fact.fact_observations (backfill only).
-- Production code must write here first; canonical facts are promoted from observations.

CREATE TABLE IF NOT EXISTS v2_ingest.observations (
    observation_id    BIGSERIAL       PRIMARY KEY,
    ticker            VARCHAR(10)     NOT NULL REFERENCES v2_ref.companies(ticker),
    period            VARCHAR(10)     NOT NULL
        CHECK (period ~ '^[0-9]{4}(FY|Q[1-4])$'),
    period_type       VARCHAR(5)      NOT NULL DEFAULT 'FY'
        CHECK (period_type IN ('FY', 'Q')),
    metric            VARCHAR(100)    NOT NULL REFERENCES v2_ref.line_items(line_item_code),
    value             NUMERIC         NOT NULL,
    unit              VARCHAR(40)     NOT NULL,
    currency          CHAR(3)         NOT NULL DEFAULT 'VND',
    source_doc_id     VARCHAR(64)     REFERENCES v2_ingest.source_documents(source_doc_id),
    source_tier       SMALLINT        NOT NULL DEFAULT 3
        CHECK (source_tier BETWEEN 0 AND 3),
    extraction_method VARCHAR(40)     NOT NULL DEFAULT 'api_structured'
        CHECK (extraction_method IN ('api_structured', 'pdf_ocr', 'manual', 'csv', 'legacy_import')),
    confidence        NUMERIC(5,4)    CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    page_number       INTEGER,
    table_name        VARCHAR(120),
    extracted_text    TEXT,
    created_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    -- One value per source per metric per period (source deduplication)
    UNIQUE (ticker, period, metric, source_doc_id)
);

CREATE INDEX IF NOT EXISTS idx_v2_obs_ticker_period
    ON v2_ingest.observations(ticker, period);

CREATE INDEX IF NOT EXISTS idx_v2_obs_metric
    ON v2_ingest.observations(ticker, metric, period);

CREATE INDEX IF NOT EXISTS idx_v2_obs_source_tier
    ON v2_ingest.observations(source_tier, ticker);

COMMENT ON TABLE v2_ingest.observations IS
    'v2: All candidate fact values before winner selection. '
    'Replaces fact.financial_facts (legacy) and fact.fact_observations (backfill). '
    'Connectors write here. Canonical promotion reads from here. '
    'NEVER write here from valuation or report modules.';

-- ── v2_ingest.connector_runs ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS v2_ingest.connector_runs (
    run_id               VARCHAR(64)  PRIMARY KEY,
    ticker               VARCHAR(10)  REFERENCES v2_ref.companies(ticker),
    connector_name       VARCHAR(100) NOT NULL,
    status               VARCHAR(20)  NOT NULL DEFAULT 'running' CHECK (
        status IN ('running', 'completed', 'failed', 'partial', 'skipped')
    ),
    started_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    finished_at          TIMESTAMPTZ,
    observations_created INTEGER      NOT NULL DEFAULT 0,
    error_message        TEXT,
    stats_json           JSONB        NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_v2_connector_runs_ticker
    ON v2_ingest.connector_runs(ticker, started_at DESC);

-- ── Migrate legacy ingest.sources → v2_ingest.source_documents ───────────────
-- Compute a deterministic source_doc_id from existing data.
-- Legacy source_id is stored in metadata_json for traceability.
-- Only migrate rows that have a valid ticker reference in v2_ref.companies.

INSERT INTO v2_ingest.source_documents (
    source_doc_id,
    ticker,
    source_type,
    source_tier,
    source_uri,
    source_title,
    published_at,
    fiscal_year,
    fiscal_period,
    checksum,
    fetch_status,
    connector_name,
    connector_version,
    metadata_json,
    created_at
)
SELECT
    -- Deterministic ID: hex of sha256(legacy source_id || checksum)
    encode(digest(s.source_id || s.checksum, 'sha256'), 'hex') AS source_doc_id,
    s.ticker,
    -- Map legacy source_type to v2 source_type
    CASE s.source_type
        WHEN 'financial_statement' THEN
            CASE WHEN COALESCE(s.source_tier, 3) = 0 THEN 'audited_financial_statement'
                 ELSE 'vnstock_financial' END
        WHEN 'annual_report'         THEN 'annual_report'
        WHEN 'disclosure'            THEN 'exchange_disclosure'
        WHEN 'regulatory_filing'     THEN 'regulatory_notice'
        WHEN 'vnstock_financial'     THEN 'vnstock_financial'
        WHEN 'vnstock_price'         THEN 'vnstock_price'
        WHEN 'vnstock_company'       THEN 'vnstock_company'
        WHEN 'manual'                THEN 'manual'
        WHEN 'news'                  THEN 'news'
        WHEN 'industry_report'       THEN 'industry_report'
        ELSE 'vnstock_financial'
    END AS source_type,
    COALESCE(s.source_tier, 3)      AS source_tier,
    s.source_uri,
    s.source_title,
    s.published_at,
    s.fiscal_year,
    s.fiscal_period,
    s.checksum,
    'verified'                      AS fetch_status,
    s.metadata_json->>'connector_name' AS connector_name,
    s.connector_version,
    jsonb_build_object(
        'legacy_source_id', s.source_id,
        'legacy_logical_id', s.logical_id,
        'migrated_from', 'ingest.sources'
    ) || s.metadata_json             AS metadata_json,
    s.ingested_at                   AS created_at
FROM ingest.sources s
WHERE s.ticker IN (SELECT ticker FROM v2_ref.companies)
   OR s.ticker IS NULL
ON CONFLICT (ticker, source_type, fiscal_year, checksum) DO NOTHING;

-- ── Migrate ingest.official_documents → v2_ingest.source_documents ────────────
-- Official documents are a second source type that should merge into source_documents.

INSERT INTO v2_ingest.source_documents (
    source_doc_id,
    ticker,
    source_type,
    source_tier,
    source_uri,
    source_title,
    issuer,
    published_at,
    fiscal_year,
    checksum,
    local_path,
    language,
    fetch_status,
    metadata_json,
    created_at
)
SELECT
    encode(digest(
        'official_doc_' || od.official_document_id::TEXT || COALESCE(od.file_hash, ''),
        'sha256'
    ), 'hex')                       AS source_doc_id,
    od.ticker,
    CASE od.source_type
        WHEN 'audited_financial_statement' THEN 'audited_financial_statement'
        WHEN 'annual_report'               THEN 'annual_report'
        WHEN 'exchange_disclosure'         THEN 'exchange_disclosure'
        WHEN 'company_ir'                  THEN 'company_ir'
        WHEN 'regulatory_notice'           THEN 'regulatory_notice'
        ELSE 'manual'
    END                             AS source_type,
    od.source_tier,
    COALESCE(od.url, od.local_path, 'unknown') AS source_uri,
    od.title                        AS source_title,
    od.issuer,
    od.published_date::TIMESTAMPTZ  AS published_at,
    od.fiscal_year,
    COALESCE(od.file_hash, encode(digest(od.title, 'sha256'), 'hex')) AS checksum,
    od.local_path,
    od.language,
    CASE od.status
        WHEN 'verified'   THEN 'verified'
        WHEN 'extracted'  THEN 'extracted'
        WHEN 'fetched'    THEN 'fetched'
        WHEN 'failed'     THEN 'failed'
        ELSE 'registered'
    END                             AS fetch_status,
    jsonb_build_object(
        'legacy_official_document_id', od.official_document_id,
        'migrated_from', 'ingest.official_documents'
    )                               AS metadata_json,
    od.created_at
FROM ingest.official_documents od
WHERE od.ticker IN (SELECT ticker FROM v2_ref.companies)
   OR od.ticker IS NULL
ON CONFLICT (ticker, source_type, fiscal_year, checksum) DO NOTHING;
